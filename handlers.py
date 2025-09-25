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
from prompts import SYSTEM_RULES, USER_CONTEXT_TEMPLATE, TASK_INSTRUCTION
from security.pi_guard import sanitize_user_text, scan_prompt_injection
from security.messages import SAFE_REFUSAL

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
        raw_text = (getattr(event.message, 'text', '') or '')
        text = sanitize_user_text(raw_text)
        pi = scan_prompt_injection(text)
        if pi.get('detected'):
            # tag and respond with safe refusal
            if sentry_sdk:
                sentry_sdk.set_tag('pi_detected', 'true')
                sentry_sdk.set_extra('pi_reason', pi.get('reason'))
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=SAFE_REFUSAL))
            return
        safe_log_event(logger, 'received_text', user_id=user_id, event_type='text')

        st = get_state(user_id) or {}
        phase = st.get('phase')

        # state machine: Q1 -> Q2 -> Q3 -> WAIT_IMAGE
        if not phase:
            # start Q1
            set_state(user_id, phase='Q1')
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='請描述地點或場景（例如：上班、聚會、海邊）'))
            return
        if phase == 'Q1':
            if not text:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text='請輸入地點或場景'))
                return
            set_state(user_id, location=text, phase='Q2')
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='請描述穿搭目的（例如：正式、休閒）'))
            return
        if phase == 'Q2':
            if not text:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text='請輸入穿搭目的'))
                return
            set_state(user_id, purpose=text, phase='Q3')
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='請描述時間或天氣（例如：夏天、傍晚）'))
            return
        if phase == 'Q3':
            if not text:
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text='請輸入時間或天氣'))
                return
            set_state(user_id, time_weather=text, phase='WAIT_IMAGE')
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='已完成設定，請上傳圖片（JPG/PNG，最大 %d MB）' % MAX_IMAGE_MB))
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
        safe_log_event(logger, 'received_image', user_id=user_id, event_type='image')
        st = get_state(user_id)
        if not st or st.get('phase') != 'WAIT_IMAGE':
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='請先完成問答流程（地點/目的/時間），再上傳圖片'))
            return

        try:
            content = line_bot_api.get_message_content(event.message.id)
            data = b''.join(content) if hasattr(content, '__iter__') else content
        except Exception as e:
            logger.exception('failed to download image')
            if sentry_sdk:
                sentry_sdk.capture_exception(e)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='下載圖片失敗'))
            return

        size = len(data) if data else 0
        safe_log_event(logger, 'image_meta', user_id=user_id, event_type='image', image_size=size)

        mime = _detect_image_mime(data)
        if not mime:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='不支援的圖片格式，請上傳 JPG 或 PNG'))
            return
        if not data or size > MAX_IMAGE:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f'圖片過大或為空（限制 {MAX_IMAGE_MB}MB）'))
            return

        prompt = _build_prompt_from_state(st)
        start = time.time()
        try:
            resp_text = image_analyze(data, prompt)
            latency = int((time.time() - start) * 1000)
        except GeminiTimeoutError as e:
            logger.exception('gemini timeout')
            if sentry_sdk:
                sentry_sdk.set_tag('user_hash', _hash_user(user_id))
                sentry_sdk.set_tag('event_type', 'image')
                sentry_sdk.set_extra('image_size', size)
                sentry_sdk.set_extra('latency', None)
                sentry_sdk.capture_exception(e)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='系統忙碌，請稍後再試'))
            return
        except GeminiAPIError as e:
            logger.exception('gemini api error')
            if sentry_sdk:
                sentry_sdk.set_tag('user_hash', _hash_user(user_id))
                sentry_sdk.set_tag('event_type', 'image')
                sentry_sdk.set_extra('image_size', size)
                sentry_sdk.set_extra('latency', None)
                sentry_sdk.capture_exception(e)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='分析失敗，請稍後再試'))
            return
        except Exception as e:
            logger.exception('unexpected error during image analyze')
            if sentry_sdk:
                sentry_sdk.set_tag('user_hash', _hash_user(user_id))
                sentry_sdk.set_tag('event_type', 'image')
                sentry_sdk.set_extra('image_size', size)
                sentry_sdk.set_extra('latency', None)
                sentry_sdk.capture_exception(e)
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
            flex = _make_flex_message(overall_int, subs, summary, suggestions)
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
