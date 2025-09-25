import os
import time
import json
import hashlib
import logging
from typing import Dict, Optional
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
from utils import validate_image
from prompts import SYSTEM_RULES, USER_CONTEXT_TEMPLATE, TASK_INSTRUCTION
from security.pi_guard import sanitize_user_text, scan_prompt_injection
from security.messages import SAFE_REFUSAL
from sentry_init import set_user as sentry_set_user, set_tag as sentry_set_tag, capture_exception as sentry_capture_exception, set_extra as sentry_set_extra
from templates.flex_outfit import build_flex_payload
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
            # set final phase and stage and expiry
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
            data = b''.join(content) if hasattr(content, '__iter__') else content
        except Exception as e:
            logger.exception('failed to download image')
            sentry_capture_exception(e)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='下載圖片失敗'))
            return

        size = len(data) if data else 0
        sentry_set_tag('image_size_bytes', size)
        safe_log_event(logger, 'image_meta', user_id=user_id, event_type='image', image_size=size)
        mime = _detect_image_mime(data)
        ok, reason = validate_image(mime, size, max_mb=MAX_IMAGE_MB)
        if not ok:
            if reason == 'format':
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text='目前僅支援 JPG/PNG，請轉檔後重傳 🙏'))
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f'檔案太大了，請壓到 {MAX_IMAGE_MB}MB 以內（JPG/PNG）再傳一次喔～'))
            return

        prompt = _build_prompt_from_state(st)
        start = time.time()
        try:
            resp_text = image_analyze(data, prompt)
            latency = int((time.time() - start) * 1000)
            sentry_set_tag('latency_ms', latency)
        except GeminiTimeoutError as e:
            logger.exception('gemini timeout')
            sentry_set_tag('user_hash', _hash_user(user_id))
            sentry_set_extra('image_size', size)
            sentry_set_extra('latency_ms', None)
            sentry_capture_exception(e)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='系統忙碌，請稍後再試'))
            return
        except GeminiAPIError as e:
            logger.exception('gemini api error')
            sentry_set_tag('user_hash', _hash_user(user_id))
            sentry_set_extra('image_size', size)
            sentry_set_extra('latency_ms', None)
            sentry_capture_exception(e)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='分析失敗，請稍後再試'))
            return
        except Exception as e:
            logger.exception('unexpected error during image analyze')
            sentry_set_tag('user_hash', _hash_user(user_id))
            sentry_set_extra('image_size', size)
            sentry_set_extra('latency_ms', None)
            sentry_capture_exception(e)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='發生錯誤，請稍後再試'))
            return

        # try parse JSON schema from model
        try:
            parsed = json.loads(resp_text)
        except Exception:
            # if model returned plain text, wrap
            parsed = None

        clear_state(user_id)

        if not parsed:
            # fallback to sending raw text split
            parts = split_message(resp_text)
            if not parts:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text='分析結果為空'))
                return
            messages = [TextSendMessage(text=truncate(p)) for p in parts]
            try:
                line_bot_api.reply_message(event.reply_token, messages[:5])
                for m in messages[5:]:
                    line_bot_api.push_message(user_id, m)
            except Exception:
                logger.exception('failed to send messages')
            return

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
            line_bot_api.reply_message(event.reply_token, flex)
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
            set_state(user_id, stage='ASK_CONTEXT', context=ctx)
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
            set_state(user_id, stage='ASK_CONTEXT', context=ctx)
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
            set_state(user_id, stage='WAIT_IMAGE', context=ctx, expires_at=int(time.time()) + 3600)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f'已完成設定，請上傳圖片（JPG/PNG，最大 {MAX_IMAGE_MB} MB）'))
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
