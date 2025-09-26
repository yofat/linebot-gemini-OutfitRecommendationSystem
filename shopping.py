from typing import List, Dict, Any, Tuple, Optional
from duckduckgo_search import ddg
import logging
import re
import time
import os
import urllib.parse
import random
from threading import RLock

Price = Tuple[str, int]  # (原字串, 整數價格)

# Simple in-memory TTL cache (thread-safe)
_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = RLock()
CACHE_TTL_SECONDS = int(os.getenv('SHOP_CACHE_TTL_SEC', str(12 * 3600)))  # default 12 hours

# Domain whitelist from env
# Per user request, restrict default search to Lativ only (use netloc form)
# user explicitly requested the WWW host form
SHOP_DOMAINS_TW = os.getenv('SHOP_DOMAINS_TW', 'www.lativ.com.tw')
_all_domains = [d.strip().lower() for d in SHOP_DOMAINS_TW.split(',') if d.strip()]
# If any lativ domain present, restrict to lativ only (user requested)
if any('lativ' in d for d in _all_domains):
    SHOP_DOMAINS = [d for d in _all_domains if 'lativ' in d]
    SHOP_BRANDS = SHOP_DOMAINS[:]
    SHOP_MARKETPLACES = []
else:
    # classify into marketplaces (general ecommerce) vs brands
    SHOP_MARKETPLACES = [d for d in _all_domains if any(k in d for k in ('shopee', 'momo', 'pchome', 'yahoo'))]
    SHOP_BRANDS = [d for d in _all_domains if d not in SHOP_MARKETPLACES]
    # prefer brands first (focus on clothing) then marketplaces
    SHOP_DOMAINS = SHOP_BRANDS + SHOP_MARKETPLACES

SHOP_MAX_RESULTS = int(os.getenv('SHOP_MAX_RESULTS', '8'))
SHOP_REGION = os.getenv('SHOP_REGION', 'tw')
SHOP_CURRENCY = os.getenv('SHOP_CURRENCY', 'TWD')

# user-level throttle state (simple in-memory timestamps)
_user_last_trigger: Dict[str, float] = {}
_user_lock = RLock()
USER_THROTTLE_SECONDS = int(os.getenv('SHOP_USER_THROTTLE_SEC', '60'))


# DuckDuckGo ddg() failure circuit-breaker state to avoid log spam
_ddg_failure_count = 0
_ddg_failure_window_start = 0.0
_DDG_FAILURE_THRESHOLD = int(os.getenv('SHOP_DDG_FAIL_THRESHOLD', '8'))
_DDG_COOLDOWN_SEC = int(os.getenv('SHOP_DDG_COOLDOWN_SEC', '300'))  # cooldown after threshold
_ddg_disabled_until = 0.0

# reduce noisy logs from duckduckgo_search internals
try:
    logging.getLogger('duckduckgo_search.utils').setLevel(logging.CRITICAL)
except Exception:
    pass


def _cache_get(key: str) -> Optional[Any]:
    with _cache_lock:
        ent = _cache.get(key)
        if not ent:
            return None
        if time.time() - ent['ts'] > ent['ttl']:
            del _cache[key]
            return None
        return ent['value']


def _cache_set(key: str, value: Any, ttl: int = CACHE_TTL_SECONDS) -> None:
    with _cache_lock:
        _cache[key] = {'value': value, 'ts': time.time(), 'ttl': ttl}


def build_queries_from_suggestions(suggestions: List[str], scene: str, purpose: str, time_weather: str) -> List[str]:
    """
    將模型的 suggestions[]（中文）解析出單品、顏色、版型、材質等詞，並組合查詢。
    會加上場景/目的詞與 site:domain 標註，產生多個查詢字串，最多 10 條。
    新增同義詞擴展與品牌前綴查詢以提高命中率。
    """
    # simple synonyms map to expand queries (domain-specific clothing synonyms)
    SYNONYMS = {
        '素T': ['T恤', '短袖', '素面T恤'],
        '牛仔褲': ['牛仔褲', '牛仔 長褲', '牛仔 直筒'],
        '皮革': ['皮革', '皮質', '皮面'],
        '洋裝': ['連衣裙', '洋裝', '裙子'],
        '襯衫': ['襯衫', '長袖襯衫', '短袖襯衫'],
    }

    terms: List[str] = []
    _seen_terms = set()
    # naive tokenization: split by punctuation and whitespace
    for s in suggestions:
        if not s:
            continue
        s = s.strip()
        parts = re.split(r'[，,;；/\|\\\-\(\)\[\]：:]+', s)
        for p in parts:
            p = p.strip()
            if not p:
                continue
            for sp in re.split(r'\s+', p):
                sp = sp.strip()
                if not sp:
                    continue
                sp = re.sub(r"(的|、|款|款式|風格|類型|材質|顏色)", '', sp)
                if 1 <= len(sp) <= 40 and sp not in _seen_terms:
                    _seen_terms.add(sp)
                    terms.append(sp)

    # include scene/purpose/time
    context_terms = [t for t in (scene, purpose, time_weather) if t]

    queries: List[str] = []

    def _append(q: str):
        if len(queries) >= 10:
            return
        queries.append(q)

    term_list = terms[:8]
    # prioritize item-like tokens (in SYNONYMS or containing ASCII letters) so we don't
    # exhaust the query slots with colors only
    prioritized = []
    rest = []
    for t in term_list:
        if t in SYNONYMS or re.search(r'[A-Za-z0-9]', t):
            prioritized.append(t)
        else:
            rest.append(t)
    # interleave prioritized and rest so we keep both item tokens and colors
    term_list = []
    pi = 0
    ri = 0
    while pi < len(prioritized) or ri < len(rest):
        if pi < len(prioritized):
            term_list.append(prioritized[pi])
            pi += 1
        if ri < len(rest):
            term_list.append(rest[ri])
            ri += 1

    # Helper to add site-scoped and brand-prefixed variants for a base phrase
    def add_variants(base_phrase: str):
        base = re.sub(r'\s+', ' ', (base_phrase + ' ' + ' '.join(context_terms)).strip())
        if not base:
            return
        # prefer brand domains first, then marketplaces
        for domain in SHOP_DOMAINS:
            _append(f"{base} site:{domain} {SHOP_REGION}")
            if len(queries) >= 10:
                return
        # synonyms expansion for the base phrase (if matches a key)
        syns = SYNONYMS.get(base_phrase, [])
        for sterm in syns:
            base2 = re.sub(r'\s+', ' ', (sterm + ' ' + ' '.join(context_terms)).strip())
            for domain in SHOP_DOMAINS:
                _append(f"{base2} site:{domain} {SHOP_REGION}")
                if len(queries) >= 10:
                    return
        # brand-prefixed variants (brand name token + base)
        for brand_domain in SHOP_BRANDS:
            brand_name = brand_domain.split('.')[0]
            bp = re.sub(r'\s+', ' ', (brand_name + ' ' + base).strip())
            _append(f"{bp} site:{brand_domain} {SHOP_REGION}")
            if len(queries) >= 10:
                return

    # add single-term variants
    for t in term_list:
        add_variants(t)
        if len(queries) >= 10:
            break

    # two-term combos for more specific queries
    if len(term_list) >= 2 and len(queries) < 10:
        combos = []
        for i in range(len(term_list)):
            for j in range(i + 1, len(term_list)):
                combos.append((term_list[i], term_list[j]))
                if len(combos) >= 12:
                    break
            if len(combos) >= 12:
                break
        for a, b in combos:
            add_variants(f"{a} {b}")
            if len(queries) >= 10:
                break

    # include original suggestion phrases (preserve multi-token suggestions)
    for s in suggestions:
        if not s:
            continue
        add_variants(s)
        if len(queries) >= 10:
            break

    # fallback: if still empty, use plain context + some domains
    if not queries:
        for domain in SHOP_DOMAINS:
            _append(f"{purpose} {scene} site:{domain} {SHOP_REGION}")
            if len(queries) >= 5:
                break

    # dedupe while preserving order
    seen = set()
    out = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            out.append(q)
        if len(out) >= 10:
            break
    return out


PRICE_RE = re.compile(r'(NT\$|NT\s*|\$|＄)\s*([0-9]{1,3}(?:[,，][0-9]{3})*(?:\.[0-9]+)?)', re.I)


def extract_price(text: str) -> Optional[Price]:
    """
    從文字中抽價格字串，如 'NT$1,290' => ('NT$1,290', 1290)
    """
    if not text:
        return None
    m = PRICE_RE.search(text)
    if not m:
        return None
    price_text = m.group(0)
    num = m.group(2)
    num_clean = int(re.sub(r'[,，]', '', num).split('.')[0])
    return (price_text, num_clean)


def _normalize_url(u: str) -> str:
    try:
        p = urllib.parse.urlparse(u)
        # remove query & fragment for dedupe
        norm = urllib.parse.urlunparse((p.scheme, p.netloc.lower(), p.path.rstrip('/'), '', '', ''))
        return norm
    except Exception:
        return u


def search_products(queries: List[str], max_results: int = None) -> List[Dict[str, Any]]:
    """
    使用 DDGS().text 逐條查詢，每條取前 5~8 筆，過濾 domain 白名單並做快取與去重。
    """
    # use ddg() function from duckduckgo_search which returns a list of hits
    if max_results is None:
        max_results = SHOP_MAX_RESULTS
    results: List[Dict[str, Any]] = []
    seen_urls = set()

    for q in queries:
        # circuit-breaker: if ddg has been failing, skip heavy calls until cooldown
        now = time.time()
        global _ddg_failure_count, _ddg_failure_window_start, _ddg_disabled_until
        if _ddg_disabled_until and now < _ddg_disabled_until:
            # short-circuit: ddg currently disabled, return empty quickly
            _cache_set(f"ddg:{q}", [], ttl=60)
            continue
        # cache key per query
        ck = f"ddg:{q}"
        cached = _cache_get(ck)
        if cached is not None:
            hits = cached
        else:
            # throttle per query
            delay = random.uniform(0.6, 1.0)
            time.sleep(delay)
            hits = []
            # try ddg with a couple retries/backoff to handle transient parser failures in ddg utils
            last_exc = None
            for attempt in range(3):
                try:
                    ddg_hits = ddg(q, region=SHOP_REGION, safesearch='Off', max_results=8)
                    if not ddg_hits:
                        # empty result set
                        hits = []
                    else:
                        for r in ddg_hits:
                            title = r.get('title') or ''
                            url = r.get('href') or r.get('url') or ''
                            if not url:
                                continue
                            parsed = urllib.parse.urlparse(url)
                            domain = parsed.netloc.lower()
                            # domain filter: allow if any whitelist domain is substring
                            allowed = any(d in domain for d in SHOP_DOMAINS)
                            if not allowed:
                                continue
                            price = extract_price(title) or extract_price(r.get('body', '') or '')
                            hit = {
                                'title': title,
                                'url': url,
                                'source': domain,
                                'price_text': price[0] if price else None,
                                'price_value': price[1] if price else None,
                                'query': q,
                            }
                            hits.append(hit)
                    # reset failure window on success
                    _ddg_failure_count = 0
                    _ddg_failure_window_start = 0.0
                    last_exc = None
                    break
                except Exception as e:
                    # duckduckgo_search internals sometimes fail to extract vqd; retry with backoff
                    last_exc = e
                    # on first error, set a very short cooldown to avoid immediate repeated attempts
                    tnow = time.time()
                    if _ddg_failure_count == 0 and _ddg_disabled_until < tnow:
                        # short immediate cooldown (30s) to reduce log spam
                        _ddg_disabled_until = tnow + 30
                    # increment failure counter (windowed)
                    tnow = time.time()
                    if _ddg_failure_window_start == 0.0 or tnow - _ddg_failure_window_start > 60:
                        _ddg_failure_window_start = tnow
                        _ddg_failure_count = 1
                    else:
                        _ddg_failure_count += 1
                    # if failures exceed threshold, set cooldown
                    if _ddg_failure_count >= _DDG_FAILURE_THRESHOLD:
                        _ddg_disabled_until = tnow + _DDG_COOLDOWN_SEC
                    backoff = 0.4 * (2 ** attempt)
                    time.sleep(backoff)
            if last_exc is not None and not hits:
                # final fallback: try a simplified query without site: filters once
                try:
                    simple_q = re.sub(r"\s+site:[^\s]+", '', q)
                    simple_q = simple_q.replace(SHOP_REGION, '').strip()
                    ddg_hits = ddg(simple_q, region=SHOP_REGION, safesearch='Off', max_results=8)
                    for r in (ddg_hits or []):
                        title = r.get('title') or ''
                        url = r.get('href') or r.get('url') or ''
                        if not url:
                            continue
                        parsed = urllib.parse.urlparse(url)
                        domain = parsed.netloc.lower()
                        allowed = any(d in domain for d in SHOP_DOMAINS)
                        if not allowed:
                            continue
                        price = extract_price(title) or extract_price(r.get('body', '') or '')
                        hit = {
                            'title': title,
                            'url': url,
                            'source': domain,
                            'price_text': price[0] if price else None,
                            'price_value': price[1] if price else None,
                            'query': simple_q,
                        }
                        hits.append(hit)
                except Exception:
                    # completely give up for this query; negative-cache for short time to avoid log spam
                    _cache_set(ck, [], ttl=60)
                    hits = []
            else:
                # normal cache set for successful or empty result
                _cache_set(ck, hits)
        # append hits, dedupe
        for h in hits:
            nu = _normalize_url(h['url'])
            if nu in seen_urls:
                continue
            seen_urls.add(nu)
            results.append(h)
            if len(results) >= max_results:
                return results
    return results


def format_for_flex(products: List[Dict[str, Any]], currency: str = SHOP_CURRENCY) -> Dict[str, Any]:
    """
    生成 LINE Flex Carousel（最多 10 卡）
    每卡包含：title, source, price_text, action button
    返回整個 bubble carousel JSON 結構
    """
    cards = []
    for p in products[:10]:
        title = p.get('title') or p.get('url')
        if len(title) > 40:
            title_short = title[:37] + '...'
        else:
            title_short = title
        domain = p.get('source') or ''
        price_text = p.get('price_text')
        footer_text = domain
        if price_text:
            footer_text = f"{footer_text} • {price_text}"
        bubble = {
            'type': 'bubble',
            'size': 'kilo',
            'body': {
                'type': 'box',
                'layout': 'vertical',
                'contents': [
                    {'type': 'text', 'text': title_short, 'wrap': True, 'weight': 'bold', 'size': 'md'},
                    {'type': 'text', 'text': footer_text, 'wrap': True, 'size': 'xs', 'color': '#8c8c8c', 'margin': 'md'},
                ]
            },
            'footer': {
                'type': 'box',
                'layout': 'vertical',
                'contents': [
                    {'type': 'button', 'style': 'link', 'action': {'type': 'uri', 'label': '查看商品', 'uri': p.get('url')}},
                ]
            }
        }
        cards.append(bubble)
    if not cards:
        # return simple text bubble
        return {'type': 'text', 'text': '暫時找不到符合建議的單品，請改用品牌或顏色關鍵字再試。'}
    carousel = {'type': 'carousel', 'contents': cards}
    return carousel


# helper: check user throttle
def user_allowed(user_id: str) -> bool:
    with _user_lock:
        last = _user_last_trigger.get(user_id)
        now = time.time()
        if last and now - last < USER_THROTTLE_SECONDS:
            return False
        _user_last_trigger[user_id] = now
        return True
