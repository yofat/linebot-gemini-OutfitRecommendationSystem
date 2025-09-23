import os
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
from linebot import LineBotApi
from gemini_client import text_generate, image_analyze
from state import set_state, get_state, clear_state
from utils import truncate

MAX_IMAGE = 10 * 1024 * 1024

def register_handlers(line_bot_api: LineBotApi, handler):
    if not line_bot_api or not handler:
        return

    @handler.add(MessageEvent, message=TextMessage)
    def on_text(event):
        user_id = event.source.user_id
        text = (getattr(event.message, 'text', '') or '').strip()
        if not text:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='請輸入描述'))
            return
        set_state(user_id, text=text)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text='收到描述，請上傳圖片'))

    @handler.add(MessageEvent, message=ImageMessage)
    def on_image(event):
        user_id = event.source.user_id
        st = get_state(user_id)
        if not st or not st.get('text'):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='請先輸入描述'))
            return
        try:
            content = line_bot_api.get_message_content(event.message.id)
            data = b''.join(content) if hasattr(content, '__iter__') else content
        except Exception:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='下載圖片失敗'))
            return
        if not data or len(data) > MAX_IMAGE:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='圖片檔案過大或為空'))
            return
        prompt = f"使用者描述：{st.get('text')}"
        txt = image_analyze(data, prompt)
        clear_state(user_id)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=truncate(txt)))
