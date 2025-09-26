from typing import List, Dict, Any, Tuple, Optional
from duckduckgo_search import ddg
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
SHOP_DOMAINS_TW = os.getenv('SHOP_DOMAINS_TW', 'shopee.tw,momo.com.tw,24h.pchome.com.tw,uniqlo.com,hm.com,tw.buy.yahoo.com,zara.com')
SHOP_DOMAINS = [d.strip().lower() for d in SHOP_DOMAINS_TW.split(',') if d.strip()]

SHOP_MAX_RESULTS = int(os.getenv('SHOP_MAX_RESULTS', '8'))
SHOP_REGION = os.getenv('SHOP_REGION', 'tw')
SHOP_CURRENCY = os.getenv('SHOP_CURRENCY', 'TWD')

# user-level throttle state (simple in-memory timestamps)
_user_last_trigger: Dict[str, float] = {}
_user_lock = RLock()
USER_THROTTLE_SECONDS = int(os.getenv('SHOP_USER_THROTTLE_SEC', '60'))


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
    """
    terms = []
    _seen_terms = set()
    # naive tokenization: split by punctuation and whitespace, keep CJK characters groups
    for s in suggestions:
        s = s.strip()
        # split on common punctuation
        parts = re.split(r'[,;，；/\|\\\-\(\)\[\]：:]+', s)
        for p in parts:
            p = p.strip()
            if not p:
                continue
            # split on whitespace to capture individual tokens (e.g., '白色 素T')
            subparts = re.split(r'\s+', p)
            for sp in subparts:
                sp = sp.strip()
                if not sp:
                    continue
                # remove filler words
                sp = re.sub(r"(的|、|款|款式|風格|類型|材質|顏色)", '', sp)
                # keep short phrases
                if 1 <= len(sp) <= 40:
                    if sp not in _seen_terms:
                        _seen_terms.add(sp)
                        terms.append(sp)

    # also include scene/purpose/time
    context_terms = [t for t in (scene, purpose, time_weather) if t]

    queries = []
    # generate up to 5 base queries combining top terms
    term_list = list(terms)[:8]
    combos = []
    # single-term queries
    for t in term_list:
        combos.append([t])
    # two-term combos
    for i in range(len(term_list)):
        for j in range(i + 1, len(term_list)):
            combos.append([term_list[i], term_list[j]])
            if len(combos) >= 12:
                break
        if len(combos) >= 12:
            break

    # Build final query strings, add context and site: for each domain
    # Also ensure single-term queries for tokens are present (so colors/items appear)
    for t in term_list:
        base = ' '.join([t] + context_terms)
        base = re.sub(r'\s+', ' ', base).strip()
        if not base:
            continue
        for domain in SHOP_DOMAINS:
            q = f"{base} site:{domain} {SHOP_REGION}"
            queries.append(q)
            if len(queries) >= 10:
                break
        if len(queries) >= 10:
            break

    for combo in combos[:5]:
        base = ' '.join(combo + context_terms)
        base = re.sub(r'\s+', ' ', base).strip()
        if not base:
            continue
        # add site variants
        for domain in SHOP_DOMAINS:
            q = f"{base} site:{domain} {SHOP_REGION}"
            queries.append(q)
            if len(queries) >= 10:
                break
        if len(queries) >= 10:
            break

    # also include original suggestion phrases (to preserve multi-token phrases like '白色 素T')
    for s in suggestions:
        s = s.strip()
        if not s:
            continue
        base = ' '.join([s] + context_terms)
        base = re.sub(r'\s+', ' ', base).strip()
        for domain in SHOP_DOMAINS:
            q = f"{base} site:{domain} {SHOP_REGION}"
            queries.append(q)
            if len(queries) >= 10:
                break
        if len(queries) >= 10:
            break

    # fallback: if no queries, use plain context
    if not queries:
        for domain in SHOP_DOMAINS:
            queries.append(f"{purpose} {scene} site:{domain} {SHOP_REGION}")
            if len(queries) >= 5:
                break

    # dedupe while preserving order
    seen = set()
    out = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out[:10]


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
                    last_exc = None
                    break
                except Exception as e:
                    # duckduckgo_search internals sometimes fail to extract vqd; retry with backoff
                    last_exc = e
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
