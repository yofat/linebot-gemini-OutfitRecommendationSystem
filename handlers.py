import os
import time
import logging
from typing import Dict
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
from linebot import LineBotApi
from gemini_client import text_generate, image_analyze, GeminiTimeoutError, GeminiAPIError
from state import set_state, get_state, clear_state
from utils import truncate, split_message, safe_log_event

logger = logging.getLogger(__name__)

MAX_IMAGE = 10 * 1024 * 1024

# simple in-memory idempotency cache for event IDs with TTL
_event_cache: Dict[str, float] = {}
_EVENT_TTL = 60 * 60  # 1 hour


def _is_duplicate(event_id: str) -> bool:
    now = time.time()
    # cleanup expired
    for k, ts in list(_event_cache.items()):
        if now - ts > _EVENT_TTL:
            _event_cache.pop(k, None)
    if event_id in _event_cache:
        return True
    _event_cache[event_id] = now
    return False


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
        text = (getattr(event.message, 'text', '') or '').strip()
        safe_log_event(logger, 'received_text', user_id=user_id, event_type='text')
        if not text:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='請輸入描述'))
            return
        set_state(user_id, text=text)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text='收到描述，請上傳圖片'))

    @handler.add(MessageEvent, message=ImageMessage)
    def on_image(event):
        event_id = getattr(event, 'id', None) or getattr(event, 'timestamp', None)
        if event_id and _is_duplicate(event_id):
            logger.info('duplicate image event skipped: %s', event_id)
            return
        user_id = event.source.user_id
        safe_log_event(logger, 'received_image', user_id=user_id, event_type='image')
        st = get_state(user_id)
        if not st or not st.get('text'):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='請先輸入描述'))
            return
        try:
            content = line_bot_api.get_message_content(event.message.id)
            data = b''.join(content) if hasattr(content, '__iter__') else content
        except Exception:
            logger.exception('failed to download image')
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='下載圖片失敗'))
            return
        size = len(data) if data else 0
        safe_log_event(logger, 'image_meta', user_id=user_id, event_type='image', image_size=size)
        if not data or size > MAX_IMAGE:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='圖片檔案過大或為空（限制 10MB）'))
            return
        prompt = f"使用者描述：{st.get('text')}"
        try:
            txt = image_analyze(data, prompt)
        except GeminiTimeoutError:
            logger.exception('gemini timeout')
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='系統忙碌，請稍後再試'))
            return
        except GeminiAPIError:
            logger.exception('gemini api error')
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='分析失敗，請稍後再試'))
            return
        except Exception:
            logger.exception('unexpected error during image analyze')
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='發生錯誤，請稍後再試'))
            return
        clear_state(user_id)
        # split into multiple messages if too long
        parts = split_message(txt)
        if not parts:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='分析結果為空'))
            return
        messages = [TextSendMessage(text=truncate(p)) for p in parts]
        # if many messages, reply with the first and then push remaining
        try:
            line_bot_api.reply_message(event.reply_token, messages[:5])
            # push the rest as push messages (best-effort)
            for m in messages[5:]:
                line_bot_api.push_message(user_id, m)
        except Exception:
            logger.exception('failed to send messages')
