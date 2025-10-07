import os
import time
import json
import re
import hashlib
import logging
from typing import Dict, Optional, Any, List, Tuple
try:
    import redis
except Exception:
    redis = None

from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
try:
    from linebot.models import PostbackEvent, FollowEvent
except Exception:
    try:
        from linebot.models.events import PostbackEvent, FollowEvent  # type: ignore
    except Exception:
        PostbackEvent = None  # type: ignore
        FollowEvent = None  # type: ignore
try:
    from linebot.models import FlexSendMessage
except Exception:
    # minimal shim for environments without the SDK's FlexSendMessage
    class FlexSendMessage:
        def __init__(self, alt_text: str, contents: dict):
            self.alt_text = alt_text
            self.contents = contents
from linebot import LineBotApi
from gemini_client import text_generate, image_analyze, GeminiTimeoutError, GeminiAPIError
from state import set_state, get_state, clear_state
from utils import truncate, split_message, safe_log_event
from utils import validate_image, compress_image_to_jpeg
from prompts import SYSTEM_RULES, USER_CONTEXT_TEMPLATE, TASK_INSTRUCTION
from security.pi_guard import sanitize_user_text, scan_prompt_injection
from security.messages import SAFE_REFUSAL
from sentry_init import set_user as sentry_set_user, set_tag as sentry_set_tag, capture_exception as sentry_capture_exception, set_extra as sentry_set_extra
from templates.flex_outfit import build_flex_payload
try:
    from shopping_queries import build_queries
    from shopping_rakuten import search_items, RakutenAPIError, resolve_genre_ids
    from utils_flex import flex_rakuten_carousel

    # in-memory keyword cache: keyword -> (ts, results)
    _shopping_cache: Dict[str, Any] = {}
    SHOP_CACHE_TTL = int(os.getenv('RAKUTEN_CACHE_TTL', str(12 * 3600)))  # 12 hours default

    # per-user throttle for triggering shopping (seconds)
    _user_shopping_ts: Dict[str, float] = {}
    SHOP_USER_COOLDOWN = int(os.getenv('RAKUTEN_USER_COOLDOWN_SEC', '60'))

    def _cache_get(keyword: str):
        now = time.time()
        rec = _shopping_cache.get(keyword)
        if rec:
            ts, val = rec
            if now - ts < SHOP_CACHE_TTL:
                return val
            else:
                _shopping_cache.pop(keyword, None)
        return None

    def _cache_set(keyword: str, val):
        _shopping_cache[keyword] = (time.time(), val)

    def user_allowed(uid: str) -> bool:
        now = time.time()
        last = _user_shopping_ts.get(uid)
        if last and now - last < SHOP_USER_COOLDOWN:
            return False
        _user_shopping_ts[uid] = now
        return True

    def search_products(queries: list, max_results: int = 8, *, gender: str = '', preferences: Optional[List[str]] = None):
        """Orchestrate Rakuten searches for multiple queries until max_results collected.

        Uses per-keyword cache and global rate-limit implemented in shopping_rakuten.
        Returns list of normalized products.
        """
        provider_qps = 1.0
        try:
            provider_qps = float(os.getenv('RAKUTEN_RATE_LIMIT_QPS', '1'))
        except Exception:
            provider_qps = 1.0

        genre_ids = resolve_genre_ids(gender, preferences)
        genre_key = ','.join(genre_ids) if genre_ids else 'none'

        results = []
        for q in queries:
            if len(results) >= max_results:
                break
            # check cache
            cache_key = f"{q}|g={genre_key}"
            cached = _cache_get(cache_key)
            if cached is not None:
                results.extend(cached)
                if len(results) >= max_results:
                    break
                continue

            try:
                items = search_items(q, max_results=max_results, qps=provider_qps, genre_ids=genre_ids)
                # store in cache
                _cache_set(cache_key, items)
                results.extend(items)
            except RakutenAPIError as e:
                # bubble up to caller
                raise
            except Exception as e:
                # on unexpected errors, capture and continue to next query
                sentry_capture_exception(e)
                continue

        # dedupe by url
        seen = set()
        out = []
        for p in results:
            u = p.get('url')
            if u in seen:
                continue
            seen.add(u)
            out.append(p)
            if len(out) >= max_results:
                break
        return out

    def format_for_flex(products: list, currency: str = 'JPY'):
        # add price_text for fallback listing
        for p in products:
            try:
                if p.get('price') is not None:
                    p['price_text'] = f"¥{int(p['price']):,}"
                else:
                    p['price_text'] = None
            except Exception:
                p['price_text'] = None
        return flex_rakuten_carousel(products)

    SHOP_MAX_RESULTS = int(os.getenv('RAKUTEN_MAX_RESULTS', '8'))
    SHOP_CURRENCY = os.getenv('SHOP_CURRENCY', 'JPY')
except Exception:
    # allow tests to run even if shopping deps missing
    build_queries = None  # type: ignore
    search_items = None  # type: ignore
    format_for_flex = None  # type: ignore
    user_allowed = None  # type: ignore
    SHOP_MAX_RESULTS = int(os.getenv('SHOP_MAX_RESULTS', '8'))
    SHOP_CURRENCY = os.getenv('SHOP_CURRENCY', 'TWD')
try:
    from linebot.models import QuickReply, QuickReplyButton, MessageAction, PostbackAction
except Exception:
    # Provide minimal shims so module can be imported in test environments without full SDK
    class QuickReply:
        def __init__(self, items=None):
            self.items = items or []

    class QuickReplyButton:
        def __init__(self, action=None):
            self.action = action

    class MessageAction:
        def __init__(self, label: str = '', text: str = ''):
            self.label = label
            self.text = text

    class PostbackAction:
        def __init__(self, label: str = '', data: str = ''):
            self.label = label
            self.data = data

try:
    import sentry_sdk
except Exception:
    sentry_sdk = None

logger = logging.getLogger(__name__)

# configurable limits
MAX_IMAGE_MB = int(os.getenv('MAX_IMAGE_MB', '10'))
MAX_IMAGE = MAX_IMAGE_MB * 1024 * 1024

# event dedup store (in-memory fallback, Redis optional)
_event_cache: Dict[str, float] = {}
_EVENT_TTL = int(os.getenv('EVENT_TTL_SECONDS', str(60 * 60)))
_redis_client = None
if os.getenv('REDIS_URL') and redis:
    try:
        _redis_client = redis.from_url(os.getenv('REDIS_URL'))
    except Exception:
        _redis_client = None

# simple per-user recent message dedupe (memory fallback; optional Redis-backed)
_recent_user_msg: Dict[str, float] = {}
_RECENT_MSG_TTL = float(os.getenv('USER_MSG_DEDUPE_SEC', '2'))


def _is_recent_same_message(uid: str, msg_hash: str, ttl: float = None) -> bool:
    """Return True if the same message hash from the same user was seen within ttl seconds.

    Uses Redis if available (SET NX with expire), otherwise an in-memory dict.
    """
    if ttl is None:
        ttl = _RECENT_MSG_TTL
    now = time.time()
    if _redis_client:
        try:
            key = f'lastmsg:{uid}:{msg_hash}'
            added = _redis_client.set(key, '1', nx=True, ex=int(max(1, ttl)))
            return not bool(added)
        except Exception:
            # fall back to memory
            pass
    # cleanup expired entries
    for k, ts in list(_recent_user_msg.items()):
        if now - ts > ttl:
            _recent_user_msg.pop(k, None)
    key = f'{uid}:{msg_hash}'
    if key in _recent_user_msg:
        return True
    _recent_user_msg[key] = now
    return False


def _is_duplicate(event_id: str) -> bool:
    """Return True if event_id already seen within TTL."""
    now = time.time()
    if _redis_client:
        try:
            key = f'evt:{event_id}'
            # SETNX with expire
            added = _redis_client.set(key, str(now), nx=True, ex=_EVENT_TTL)
            return not bool(added)
        except Exception:
            # fallback to memory
            pass
    # memory fallback
    for k, ts in list(_event_cache.items()):
        if now - ts > _EVENT_TTL:
            _event_cache.pop(k, None)
    if event_id in _event_cache:
        return True
    _event_cache[event_id] = now
    return False


def _hash_user(user_id: str) -> str:
    return hashlib.sha256(user_id.encode('utf-8')).hexdigest()[:16]


def _detect_image_mime(data: bytes) -> Optional[str]:
    if not data or len(data) < 10:
        return None
    if data.startswith(b'\xff\xd8'):
        return 'image/jpeg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    return None


_user_image_timestamps: Dict[str, float] = {}

# short debounce for prompts to avoid duplicate replies (seconds)
_recent_prompt_ts: Dict[str, float] = {}


_GENDER_KEYWORDS = {
    '男性': ['男性', '男', '男生', '先生', '紳士', 'men', 'man', 'male', 'boy', '男裝'],
    '女性': ['女性', '女', '女生', '小姐', 'lady', 'woman', 'female', 'girl', '女裝'],
    '不公開': ['不公開', '不限', '都可以', '皆可', '男女皆可', '男女皆宜', '通用', '任何', '任意', 'any', '無特別', '沒特別', '都行', '無偏好']
}
_PREFERENCE_SKIP_WORDS = {'無', '沒有', 'none', '無偏好', '不特別', '沒特別', '隨便', '都可以', '皆可', '不限', '沒有特別', 'nothing'}
_PREFERENCE_SPLIT_RE = re.compile(r'[，,；;、/\s]+')


def _normalize_gender_input(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    lowered = text.strip().lower()
    if not lowered:
        return None
    for canonical, keywords in _GENDER_KEYWORDS.items():
        for kw in keywords:
            if not kw:
                continue
            if lowered == kw.lower() or kw.lower() in lowered:
                return canonical
    return None


def _parse_preferences_input(text: Optional[str]) -> Tuple[List[str], bool]:
    """Parse preference free-text; return (prefs, skip_flag)."""
    if text is None:
        return [], False
    raw = text.strip()
    if not raw:
        return [], False
    lowered = raw.lower()
    if lowered in _PREFERENCE_SKIP_WORDS:
        return [], True
    parts = [p.strip() for p in _PREFERENCE_SPLIT_RE.split(raw) if p.strip()]
    if not parts:
        return [], False
    prefs: List[str] = []
    skip_flag = False
    seen = set()
    for part in parts:
        low = part.lower()
        if low in _PREFERENCE_SKIP_WORDS:
            skip_flag = True
            continue
        if part not in seen:
            prefs.append(part)
            seen.add(part)
    if prefs:
        return prefs, skip_flag
    return [], skip_flag


def _default_suggestions(gender: Optional[str]) -> List[str]:
    norm = _normalize_gender_input(gender)
    if norm == '男性':
        return ['メンズ シャツ スリムフィット', 'メンズ スラックス テーパード', 'メンズ レザー ローファー']
    if norm == '女性':
        return ['レディース ブラウス フェミニン', 'レディース ミディスカート', 'レディース パンプス ベーシック']
    return ['ユニセックス トップス ベーシック', 'ユニセックス ワイドパンツ', 'ユニセックス スニーカー']


def allow_user_image_infer(user_id: str, cooldown_sec: int = None) -> bool:
    """Per-user cooldown: return True if allowed, False if still in cooldown."""
    if cooldown_sec is None:
        try:
            cooldown_sec = int(os.getenv('PER_USER_IMAGE_COOLDOWN_SEC', '15'))
        except Exception:
            cooldown_sec = 15
    now = time.time()
    last = _user_image_timestamps.get(user_id)
    if last and now - last < cooldown_sec:
        return False
    _user_image_timestamps[user_id] = now
    return True


def _read_message_content_to_bytes(content) -> Optional[bytes]:
    """Normalize various return types from LineBotApi.get_message_content to bytes.

    Handles:
    - bytes/bytearray
    - iterable of bytes chunks
    - objects with .content (requests.Response-like)
    - objects with .read() (file-like)
    - objects with .iter_content(chunk_size) (requests.Response-like)
    - SDK Content objects that are iterable
    Returns bytes or None on failure.
    """
    try:
        # bytes or bytearray
        if isinstance(content, (bytes, bytearray)):
            return bytes(content)

        # iterable of bytes chunks
        if hasattr(content, '__iter__') and not isinstance(content, (str, dict, bytes, bytearray)):
            try:
                parts = []
                for part in content:
                    if isinstance(part, (bytes, bytearray)):
                        parts.append(bytes(part))
                    elif isinstance(part, str):
                        parts.append(part.encode('utf-8'))
                    else:
                        # skip unknown types
                        continue
                if parts:
                    return b''.join(parts)
            except TypeError:
                # not actually iterable
                pass

        # requests.Response-like with .content
        if hasattr(content, 'content'):
            c = getattr(content, 'content')
            if isinstance(c, (bytes, bytearray)):
                return bytes(c)

        # requests.Response-like with iter_content
        if hasattr(content, 'iter_content'):
            try:
                parts = [bytes(chunk) for chunk in content.iter_content(1024) if chunk]
                if parts:
                    return b''.join(parts)
            except Exception:
                pass

        # file-like with read()
        if hasattr(content, 'read'):
            try:
                data = content.read()
                if isinstance(data, (bytes, bytearray)):
                    return bytes(data)
                if isinstance(data, str):
                    return data.encode('utf-8')
            except Exception:
                pass

    except Exception:
        return None
    return None


def _build_prompt_from_state(st: Dict[str, str]) -> str:
    # instruct model to return strict JSON matching schema
    instruct = (
        '請根據以下資訊與圖片來評分穿搭，並僅回傳符合 JSON schema 的結果（不要有額外文字）：\n'
        '{"overall_score": 0, "subscores": {"fit": 0, "color": 0, "occasion": 0, "balance": 0, "shoes_bag": 0, "grooming": 0}, "summary": "", "suggestions": ["", "", ""]}\n'
    )
    body = (
        f"地點/場景: {st.get('location','')}\n"
        f"目的: {st.get('purpose','')}\n"
        f"時間/天氣: {st.get('time_weather','')}\n"
    )
    return instruct + body


def _make_flex_message(overall: int, subs: Dict[str, int], summary: str, suggestions: list) -> FlexSendMessage:
    # simple Flex payload
    contents = {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": f"總分: {overall}", "weight": "bold", "size": "lg"},
                {"type": "text", "text": f"子分數: {json.dumps(subs, ensure_ascii=False)}", "wrap": True},
                {"type": "text", "text": f"摘要: {summary}", "wrap": True},
            ]
        },
        "footer": {"type": "box", "layout": "vertical", "contents": [{"type": "text", "text": "建議:"}]}
    }
    # append suggestions as separate text blocks
    sug_blocks = []
    for s in suggestions[:3]:
        sug_blocks.append({"type": "text", "text": s, "wrap": True})
    # insert suggestions into body
    contents['body']['contents'].extend(sug_blocks)
    return FlexSendMessage(alt_text=f'穿搭評分 {overall}', contents=contents)


def register_handlers(line_bot_api: LineBotApi, handler):
    if not line_bot_api or not handler:
        return

    @handler.add(MessageEvent, message=TextMessage)
    def on_text(event):
        event_id = getattr(event, 'id', None) or getattr(event, 'timestamp', None)
        if event_id and _is_duplicate(event_id):
            logger.info('duplicate text event skipped: %s', event_id)
            return
        user_id = event.source.user_id
        # set obfuscated user id for Sentry
        try:
            sentry_set_user({"id": _hash_user(user_id)})
        except Exception:
            pass
        raw_text = (getattr(event.message, 'text', '') or '')
        text = sanitize_user_text(raw_text)
        
        # Check for duplicate message content (user repeatedly asking same question)
        import hashlib
        msg_hash = hashlib.md5(text.encode('utf-8')).hexdigest()[:8]
        if _is_recent_same_message(user_id, msg_hash):
            logger.info('duplicate message content from user %s, ignoring', user_id[:8])
            # Silently ignore duplicate messages within the dedupe window
            return
        
        pi = scan_prompt_injection(text)
        if pi.get('detected'):
            # tag and respond with safe refusal
            sentry_set_tag('pi_detected', 'true')
            sentry_set_extra('pi_reason', pi.get('reason'))
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=SAFE_REFUSAL))
            return
        safe_log_event(logger, 'received_text', user_id=user_id, event_type='text')

        st = get_state(user_id) or {}
        phase = st.get('phase')

        # state machine: Q1 -> Q2 -> Q3 -> WAIT_IMAGE
        if not phase:
            # debounce to avoid duplicate prompts from webhook retries or fast re-entrancy
            now = time.time()
            last = _recent_prompt_ts.get(user_id)
            if last and now - last < 5:
                # already asked recently; skip duplicate
                return
            _recent_prompt_ts[user_id] = now
            # start Q1 (keep legacy 'phase' for compatibility, also set new 'stage' and 'context')
            set_state(user_id, phase='Q1', stage='ASK_CONTEXT', context={'scene': None, 'purpose': None, 'time_weather': None})
            # ask for scene/location as before
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='請描述地點或場景（例如：上班、聚會、海邊）'))
            return
        if phase == 'Q1':
            if not text:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text='請輸入地點或場景'))
                return
            # store scene and ask purpose (use postback suggestions)
            st = get_state(user_id) or {}
            ctx = st.get('context', {'scene': None, 'purpose': None, 'time_weather': None})
            ctx['scene'] = text
            # advance phase
            set_state(user_id, phase='Q2', stage='ASK_CONTEXT', context=ctx)
            # offer some postback choices for purpose
            qr = QuickReply(items=[
                QuickReplyButton(action=PostbackAction(label='正式', data='q2=正式')),
                QuickReplyButton(action=PostbackAction(label='休閒', data='q2=休閒')),
                QuickReplyButton(action=PostbackAction(label='其他', data='q2=其他')),
            ])
            msg = TextSendMessage(text='請描述穿搭目的（例如：正式、休閒）')
            try:
                setattr(msg, 'quick_reply', qr)
            except Exception:
                pass
            line_bot_api.reply_message(event.reply_token, msg)
            return
        if phase == 'Q2':
            if not text:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text='請輸入穿搭目的'))
                return
            st = get_state(user_id) or {}
            ctx = st.get('context', {'scene': None, 'purpose': None, 'time_weather': None})
            ctx['purpose'] = text
            set_state(user_id, phase='Q3', stage='ASK_CONTEXT', context=ctx)
            qr = QuickReply(items=[
                QuickReplyButton(action=PostbackAction(label='白天/晴', data='q3=白天/晴')),
                QuickReplyButton(action=PostbackAction(label='傍晚/涼爽', data='q3=傍晚/涼爽')),
                QuickReplyButton(action=PostbackAction(label='夜晚/寒冷', data='q3=夜晚/寒冷')),
            ])
            msg = TextSendMessage(text='請描述時間或天氣（例如：夏天、傍晚）')
            try:
                setattr(msg, 'quick_reply', qr)
            except Exception:
                pass
            line_bot_api.reply_message(event.reply_token, msg)
            return
        if phase == 'Q3':
            if not text:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text='請輸入時間或天氣'))
                return
            st = get_state(user_id) or {}
            ctx = st.get('context', {'scene': None, 'purpose': None, 'time_weather': None})
            ctx['time_weather'] = text
            # advance to Q4 to collect gender and preferences
            set_state(user_id, phase='Q4', stage='ASK_PREFERENCES', context=ctx)
            # ask gender first with quick replies
            qr = QuickReply(items=[
                QuickReplyButton(action=PostbackAction(label='男性', data='q4_gender=男性')),
                QuickReplyButton(action=PostbackAction(label='女性', data='q4_gender=女性')),
                QuickReplyButton(action=PostbackAction(label='不公開', data='q4_gender=不公開')),
            ])
            msg = TextSendMessage(text='請問你的性別或偏好族群（例如：男性/女性/不公開），或直接輸入；接著會詢問衣著偏好（例如：合身、蕾絲、一件式洋裝）')
            try:
                setattr(msg, 'quick_reply', qr)
            except Exception:
                pass
            line_bot_api.reply_message(event.reply_token, msg)
            return
        if phase == 'Q4':
            st = get_state(user_id) or {}
            ctx = st.get('context', {'scene': None, 'purpose': None, 'time_weather': None})
            gender = ctx.get('gender')
            if not gender:
                normalized = _normalize_gender_input(text)
                if not normalized:
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text='請輸入男性、女性或不公開，或使用快速選項。'))
                    return
                ctx['gender'] = normalized
                set_state(user_id, phase='Q4', stage='ASK_PREFERENCES', context=ctx)
                qr = QuickReply(items=[
                    QuickReplyButton(action=PostbackAction(label='合身', data='q4_pref=合身')),
                    QuickReplyButton(action=PostbackAction(label='寬鬆', data='q4_pref=寬鬆')),
                    QuickReplyButton(action=PostbackAction(label='蕾絲', data='q4_pref=蕾絲')),
                    QuickReplyButton(action=PostbackAction(label='一件式洋裝', data='q4_pref=一件式洋裝')),
                ])
                msg = TextSendMessage(text='請輸入你偏好的款式或材質（可多個，用空白或逗號分隔），若沒有請輸入「無」。')
                try:
                    setattr(msg, 'quick_reply', qr)
                except Exception:
                    pass
                line_bot_api.reply_message(event.reply_token, msg)
                return
            prefs, skipped = _parse_preferences_input(text)
            if prefs:
                ctx['preferences'] = prefs
            elif skipped:
                ctx['preferences'] = []
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text='請輸入偏好的款式或材質關鍵字（例如：合身、蕾絲），或輸入「無」。'))
                return
            set_state(user_id, phase='WAIT_IMAGE', stage='WAIT_IMAGE', context=ctx, expires_at=int(time.time()) + 3600)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f'已完成設定，請上傳圖片（JPG/PNG，最大 {MAX_IMAGE_MB} MB）'))
            return
        if phase == 'WAIT_IMAGE':
            # allow user to restart flow by sending 'restart'
            if text.lower() in ('restart', '重新開始', '重新'):
                clear_state(user_id)
                set_state(user_id, phase='Q1')
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text='已重新開始，請描述地點或場景'))
                return
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='已等待圖片上傳，請直接上傳圖片'))

    @handler.add(MessageEvent, message=ImageMessage)
    def on_image(event):
        event_id = getattr(event, 'id', None) or getattr(event, 'timestamp', None)
        if event_id and _is_duplicate(event_id):
            logger.info('duplicate image event skipped: %s', event_id)
            return
        user_id = event.source.user_id
        # set obfuscated user id for Sentry and tag
        try:
            sentry_set_user({"id": _hash_user(user_id)})
        except Exception:
            pass
        sentry_set_tag('event_type', 'image')
        safe_log_event(logger, 'received_image', user_id=user_id, event_type='image')
        st = get_state(user_id)
        if not st or st.get('stage') != 'WAIT_IMAGE' and st.get('phase') != 'WAIT_IMAGE':
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='請先完成問答流程（地點/目的/時間），再上傳圖片'))
            return

        try:
            content = line_bot_api.get_message_content(event.message.id)
            data = _read_message_content_to_bytes(content)
        except Exception as e:
            logger.exception('failed to download image')
            sentry_capture_exception(e)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='下載圖片失敗'))
            return

        # ensure size only measured for bytes-like
        size = len(data) if isinstance(data, (bytes, bytearray)) else 0
        sentry_set_tag('image_size_bytes', size)
        safe_log_event(logger, 'image_meta', user_id=user_id, event_type='image', image_size=size)

        # 1) DISABLE_IMAGE_ANALYZE quick path
        if os.getenv('DISABLE_IMAGE_ANALYZE', '').lower() in ('1', 'true', 'yes'):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='目前僅支援文字描述，請描述上衣/下著/鞋款與顏色、版型（合身/寬鬆）等，我會以文字給分與建議。'))
            clear_state(user_id)
            return

        # 2) per-user cooldown
        if not allow_user_image_infer(user_id):
            try:
                cooldown = int(os.getenv('PER_USER_IMAGE_COOLDOWN_SEC', '15'))
            except Exception:
                cooldown = 15
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f'圖片分析稍後再試，請在 {cooldown} 秒後再試，或改以文字描述。'))
            return

        mime = _detect_image_mime(data)
        ok, reason = validate_image(mime, size, max_mb=MAX_IMAGE_MB)
        if not ok:
            if reason == 'format':
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text='目前僅支援 JPG/PNG，請轉檔後重傳 🙏'))
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f'檔案太大了，請壓到 {MAX_IMAGE_MB}MB 以內（JPG/PNG）再傳一次喔～'))
            return

        # 3) compress to JPEG to save tokens
        try:
            comp_bytes, comp_mime = compress_image_to_jpeg(data)
        except Exception:
            logger.exception('compression failed, using original bytes')
            comp_bytes, comp_mime = data, mime

        prompt = _build_prompt_from_state(st)
        start = time.time()
        try:
            # call new multimodal analyzer
            from gemini_client import analyze_outfit_image
            parsed = analyze_outfit_image(st.get('context', {}).get('scene', ''), st.get('context', {}).get('purpose', ''), st.get('context', {}).get('time_weather', ''), comp_bytes, mime=comp_mime)
            latency = int((time.time() - start) * 1000)
            sentry_set_tag('latency_ms', latency)
        except GeminiTimeoutError as e:
            logger.exception('gemini timeout')
            sentry_set_tag('user_hash', _hash_user(user_id))
            sentry_set_extra('image_size', size)
            sentry_set_extra('latency_ms', None)
            sentry_capture_exception(e)
            # downgrade to text guidance
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='目前圖片分析較忙碌，請改用文字描述（上衣/下著/鞋款與顏色、版型），我一樣會給分與建議喔！'))
            return
        except GeminiAPIError as e:
            logger.exception('gemini api error')
            sentry_set_tag('user_hash', _hash_user(user_id))
            sentry_set_extra('image_size', size)
            sentry_set_extra('latency_ms', None)
            sentry_capture_exception(e)
            # downgrade to text guidance
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='現在圖片分析較忙碌，請改用文字描述（上衣/下著/鞋款與顏色、版型），我會改用文字給分與建議。'))
            return
        except Exception as e:
            logger.exception('unexpected error during multimodal image analyze')
            sentry_set_tag('user_hash', _hash_user(user_id))
            sentry_set_extra('image_size', size)
            sentry_set_extra('latency_ms', None)
            sentry_capture_exception(e)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='發生錯誤，請稍後再試或改用文字描述'))
            return

        if not parsed or not isinstance(parsed, dict):
            # parsed should be a dict matching expected schema; if not, inform user and fallback to text guidance
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='分析結果為空或格式不正確，請改以文字描述（上衣/下著/鞋款與顏色、版型）我會用文字給分與建議。'))
            return

        ctx = st.get('context', {}) or {}
        if not isinstance(ctx, dict):
            ctx = {}

        model_gender = parsed.get('gender') if isinstance(parsed.get('gender'), str) else None
        norm_gender = _normalize_gender_input(model_gender)
        if norm_gender:
            ctx['gender'] = norm_gender
        else:
            existing_gender = ctx.get('gender') if isinstance(ctx.get('gender'), str) else None
            norm_existing = _normalize_gender_input(existing_gender)
            if norm_existing:
                ctx['gender'] = norm_existing
                norm_gender = norm_existing

        model_prefs = parsed.get('preferences')
        parsed_prefs: List[str] = []
        if isinstance(model_prefs, list):
            parsed_prefs = [p.strip() for p in model_prefs if isinstance(p, str) and p.strip()]
        elif isinstance(model_prefs, str):
            parsed_prefs, _ = _parse_preferences_input(model_prefs)
        if parsed_prefs:
            ctx['preferences'] = parsed_prefs

        suggestions_raw = parsed.get('suggestions')
        if not isinstance(suggestions_raw, list):
            suggestions_raw = []
        suggestions = [s.strip() for s in suggestions_raw if isinstance(s, str) and s.strip()]
        if not suggestions:
            suggestions = _default_suggestions(ctx.get('gender'))
        parsed['suggestions'] = suggestions
        parsed['gender'] = ctx.get('gender', parsed.get('gender', ''))
        parsed['preferences'] = ctx.get('preferences', parsed.get('preferences', []))

        try:
            set_state(user_id, phase='DONE', last_analysis=parsed, context=ctx, analysis_ts=int(time.time()))
        except Exception:
            clear_state(user_id)

        # expected schema fields
        subs = parsed.get('subscores', {})
        summary = parsed.get('summary', '')
        suggestions = parsed.get('suggestions', [])

        # compute overall score by weights
        weights = {
            'fit': 0.25, 'color': 0.2, 'occasion': 0.15,
            'balance': 0.15, 'shoes_bag': 0.15, 'grooming': 0.1
        }
        overall = 0.0
        for k, w in weights.items():
            try:
                v = float(subs.get(k, 0))
            except Exception:
                v = 0.0
            overall += v * w
        overall_int = int(round(overall))

        # build Flex and reply (split long suggestions)
        try:
            flex_payload = build_flex_payload(overall_int, subs, summary, suggestions)
            flex = FlexSendMessage(alt_text=f'穿搭評分 {overall_int}', contents=flex_payload)
            # prepare reply items; include quick-reply as an additional message so user can opt-in to shopping
            reply_items = [flex]
            try:
                if build_queries is not None:
                    qr = QuickReply(items=[QuickReplyButton(action=PostbackAction(label='看推薦單品', data='action=shop'))])
                    qr_msg = TextSendMessage(text='要看推薦單品嗎？')
                    try:
                        setattr(qr_msg, 'quick_reply', qr)
                    except Exception:
                        pass
                    # append quick-reply as the second message (LINE allows up to 5 in one reply)
                    reply_items.append(qr_msg)
            except Exception:
                # non-fatal; continue without quick-reply
                pass
            line_bot_api.reply_message(event.reply_token, reply_items)
        except Exception:
            logger.exception('failed to send flex message, fallback to text')
            # fallback to text messages
            body = f"總分: {overall_int}\n摘要: {summary}\n建議:\n" + '\n'.join(suggestions[:3])
            parts = split_message(body)
            messages = [TextSendMessage(text=truncate(p)) for p in parts]
            try:
                line_bot_api.reply_message(event.reply_token, messages[:5])
                for m in messages[5:]:
                    line_bot_api.push_message(user_id, m)
            except Exception:
                logger.exception('failed to send fallback messages')
            # also offer quick-reply even on fallback text, but include in the same reply to avoid extra push
            try:
                    if build_queries is not None:
                        qr = QuickReply(items=[QuickReplyButton(action=PostbackAction(label='看推薦單品', data='action=shop'))])
                        quick_msg = TextSendMessage(text='要看推薦單品嗎？')
                        try:
                            setattr(quick_msg, 'quick_reply', qr)
                        except Exception:
                            pass
                    # assemble reply batch with quick_msg while respecting LINE's 5-message reply limit
                    if len(messages) >= 5:
                        reply_batch = messages[:4] + [quick_msg]
                        remaining = messages[4:]
                    else:
                        reply_batch = messages[:]
                        reply_batch.append(quick_msg)
                        remaining = []
                    try:
                        line_bot_api.reply_message(event.reply_token, reply_batch)
                        for m in remaining:
                            line_bot_api.push_message(user_id, m)
                    except Exception:
                        # if reply fails, fallback to previous behavior
                        try:
                            line_bot_api.reply_message(event.reply_token, messages[:5])
                            for m in messages[5:]:
                                line_bot_api.push_message(user_id, m)
                        except Exception:
                            logger.exception('failed to send fallback messages')
                    return
            except Exception:
                pass

    @handler.add(PostbackEvent)
    def on_postback(event):
        # parse postback data like 'q2=正式' or 'q1=餐廳'
        if not hasattr(event, 'postback') or not getattr(event, 'postback'):
            return
        data = getattr(event.postback, 'data', '') or ''
        user_id = event.source.user_id
        st = get_state(user_id) or {}
        ctx = st.get('context', {'scene': None, 'purpose': None, 'time_weather': None})
        if data.startswith('q1='):
            ctx['scene'] = data.split('=', 1)[1]
            set_state(user_id, phase='Q2', stage='ASK_CONTEXT', context=ctx)
            # ask q2
            qr = QuickReply(items=[
                QuickReplyButton(action=PostbackAction(label='正式', data='q2=正式')),
                QuickReplyButton(action=PostbackAction(label='休閒', data='q2=休閒')),
                QuickReplyButton(action=PostbackAction(label='其他', data='q2=其他')),
            ])
            msg = TextSendMessage(text='請描述穿搭目的（例如：正式、休閒）')
            try:
                setattr(msg, 'quick_reply', qr)
            except Exception:
                pass
            line_bot_api.reply_message(event.reply_token, msg)
            return
        if data.startswith('q2='):
            ctx['purpose'] = data.split('=', 1)[1]
            set_state(user_id, phase='Q3', stage='ASK_CONTEXT', context=ctx)
            qr = QuickReply(items=[
                QuickReplyButton(action=PostbackAction(label='白天/晴', data='q3=白天/晴')),
                QuickReplyButton(action=PostbackAction(label='傍晚/涼爽', data='q3=傍晚/涼爽')),
                QuickReplyButton(action=PostbackAction(label='夜晚/寒冷', data='q3=夜晚/寒冷')),
            ])
            msg = TextSendMessage(text='請描述時間/天氣（例如：夏天、傍晚）')
            try:
                setattr(msg, 'quick_reply', qr)
            except Exception:
                pass
            line_bot_api.reply_message(event.reply_token, msg)
            return
        if data.startswith('q3='):
            ctx['time_weather'] = data.split('=', 1)[1]
            set_state(user_id, phase='Q4', stage='ASK_PREFERENCES', context=ctx)
            qr = QuickReply(items=[
                QuickReplyButton(action=PostbackAction(label='男性', data='q4_gender=男性')),
                QuickReplyButton(action=PostbackAction(label='女性', data='q4_gender=女性')),
                QuickReplyButton(action=PostbackAction(label='不公開', data='q4_gender=不公開')),
            ])
            msg = TextSendMessage(text='請問你的性別或偏好族群（例如：男性/女性/不公開），或直接輸入；接著會詢問衣著偏好（例如：合身、蕾絲、一件式洋裝）')
            try:
                setattr(msg, 'quick_reply', qr)
            except Exception:
                pass
            line_bot_api.reply_message(event.reply_token, msg)
            return
        if data.startswith('q4_gender='):
            # store gender and ask for preferences
            raw_gender = data.split('=', 1)[1]
            ctx['gender'] = _normalize_gender_input(raw_gender) or raw_gender
            set_state(user_id, phase='Q4', stage='ASK_PREFERENCES', context=ctx)
            qr = QuickReply(items=[
                QuickReplyButton(action=PostbackAction(label='合身', data='q4_pref=合身')),
                QuickReplyButton(action=PostbackAction(label='寬鬆', data='q4_pref=寬鬆')),
                QuickReplyButton(action=PostbackAction(label='蕾絲', data='q4_pref=蕾絲')),
                QuickReplyButton(action=PostbackAction(label='一件式洋裝', data='q4_pref=一件式洋裝')),
            ])
            msg = TextSendMessage(text='請輸入你偏好的款式或材質（可多個，用空白或逗號分隔），若沒有請輸入「無」，或選擇下列常見選項')
            try:
                setattr(msg, 'quick_reply', qr)
            except Exception:
                pass
            line_bot_api.reply_message(event.reply_token, msg)
            return
        if data.startswith('q4_pref='):
            # add a single preference from postback and move to WAIT_IMAGE
            pref = data.split('=', 1)[1]
            prev_prefs = ctx.get('preferences', []) or []
            if pref not in prev_prefs:
                prev_prefs.append(pref)
            ctx['preferences'] = prev_prefs
            # now set WAIT_IMAGE
            set_state(user_id, phase='WAIT_IMAGE', stage='WAIT_IMAGE', context=ctx, expires_at=int(time.time()) + 3600)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f'已完成設定，請上傳圖片（JPG/PNG，最大 {MAX_IMAGE_MB} MB）'))
            return
        # shopping action trigger (quick-reply)
        if data == 'action=shop':
            # check feature flag
            if os.getenv('ENABLE_SHOPPING', '1').lower() not in ('1', 'true', 'yes'):
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text='目前未開啟單品推薦功能。'))
                return
            # user throttle
            if user_allowed is None:
                # shopping module not available
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text='購物推薦功能暫時無法使用'))
                return
            if not user_allowed(user_id):
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text='排隊中，請稍後再試'))
                return
            st = get_state(user_id) or {}
            last = st.get('last_analysis')
            ctx = st.get('context', {})
            if not last or not isinstance(last, dict):
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text='找不到先前的分析結果，請先上傳圖片或重新執行評分流程'))
                return
            suggestions = last.get('suggestions', [])
            scene = ctx.get('scene', '')
            purpose = ctx.get('purpose', '')
            time_weather = ctx.get('time_weather', '')
            gender = last.get('gender') or ctx.get('gender', '')
            preferences = last.get('preferences') or ctx.get('preferences') or []
            if isinstance(preferences, str):
                preferences = [p.strip() for p in preferences.split(',') if p.strip()]
            
            # Translate Chinese suggestions to Japanese keywords for Rakuten API
            # Keep original Chinese suggestions for display, use Japanese for search
            try:
                from gemini_client import translate_to_japanese_keywords
                japanese_keywords = translate_to_japanese_keywords(suggestions)
                logger.info('Using Japanese keywords for search: %s', japanese_keywords)
            except Exception as e:
                logger.warning('Failed to translate suggestions, using original: %s', e)
                japanese_keywords = suggestions  # Fallback to original
            
            try:
                # Use Japanese keywords for Rakuten search
                queries = build_queries(japanese_keywords, scene, purpose, time_weather=time_weather, gender=gender, preferences=preferences)
                products = search_products(queries, max_results=SHOP_MAX_RESULTS, gender=gender, preferences=preferences)
                if not products:
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text='暫時找不到符合建議的單品，請改用品牌或顏色關鍵字再試。'))
                    return
                carousel = format_for_flex(products, currency=SHOP_CURRENCY)
                # prepend a disclaimer
                disclaimer = TextSendMessage(text='連結資訊與價格可能有變動，請以目標頁面為準。')
                try:
                    # if carousel is text fallback
                    if isinstance(carousel, dict) and carousel.get('type') == 'text':
                        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=carousel.get('text')))
                        return
                    fs = FlexSendMessage(alt_text='推薦單品', contents=carousel)
                    line_bot_api.reply_message(event.reply_token, [disclaimer, fs])
                except Exception:
                    # fallback to text list
                    lines = []
                    for p in products[:5]:
                        t = f"{p.get('title')} - {p.get('price_text') or ''} \n{p.get('url')}"
                        lines.append(t)
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text='\n\n'.join(lines)))
            except Exception as e:
                logger.exception('shopping pipeline failed')
                sentry_capture_exception(e)
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text='搜尋時發生錯誤，請稍後再試'))
            return

    if FollowEvent is not None:
        @handler.add(FollowEvent)
        def on_follow(event):
            # welcome message with quick reply buttons
            user_id = event.source.user_id
            try:
                sentry_set_user({"id": _hash_user(user_id)})
            except Exception:
                pass
            qr = QuickReply(items=[
                QuickReplyButton(action=MessageAction(label='開始評分', text='開始評分')),
                QuickReplyButton(action=MessageAction(label='使用說明', text='使用說明')),
                QuickReplyButton(action=MessageAction(label='隱私說明', text='隱私說明')),
            ])
            msg = TextSendMessage(text='歡迎加入穿搭評分 Bot！按下下方按鈕開始吧～')
            try:
                setattr(msg, 'quick_reply', qr)
            except Exception:
                pass
            line_bot_api.reply_message(event.reply_token, msg)
