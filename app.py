#!/usr/bin/env python3
import os
import logging
import threading
import time
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError

from handlers import register_handlers
from state import cleanup
from sentry_init import init_sentry

app = Flask(__name__)
LINE_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
LINE_SECRET = os.getenv('LINE_CHANNEL_SECRET')

# logging configuration (env: LOG_LEVEL, LOG_FILE)
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
log_file = os.getenv('LOG_FILE')
handlers = []
if log_file:
    handlers = [logging.FileHandler(log_file), logging.StreamHandler()]
else:
    handlers = [logging.StreamHandler()]
logging.basicConfig(level=getattr(logging, log_level, logging.INFO), format='%(asctime)s %(levelname)s %(message)s', handlers=handlers)
logger = logging.getLogger(__name__)

# Sentry initialization (if configured)
try:
    if init_sentry():
        logger.info('Sentry initialized')
except Exception:
    logger.exception('failed to init sentry')

line_bot_api = LineBotApi(LINE_TOKEN) if LINE_TOKEN else None
handler = WebhookHandler(LINE_SECRET) if LINE_SECRET else None

if line_bot_api and handler:
    register_handlers(line_bot_api, handler)


def _start_cleanup(interval: int = 300):
    def _job():
        while True:
            try:
                cleanup()
            except Exception:
                logger.exception('cleanup failed')
            time.sleep(interval)

    t = threading.Thread(target=_job, daemon=True)
    t.start()


@app.route('/healthz', methods=['GET'])
def healthz():
    return 'ok', 200


@app.route('/callback', methods=['POST'])
def callback():
    if not handler:
        abort(500)
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK', 200


if __name__ == '__main__':
    _start_cleanup()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))

import compat
from compat import truncate_for_line, build_outfit_prompt

# expose model in app namespace so tests can monkeypatch `app.model`
model = compat.model


def call_gemini_with_retries(image_bytes: bytes, prompt: str, mime_type: str, retries: int = 3, backoff: float = 1.5) -> str:
    # ensure compat.call_gemini_with_retries uses the current app.model (which tests may monkeypatch)
    orig = getattr(compat, 'model', None)
    compat.model = model
    try:
        return compat.call_gemini_with_retries(image_bytes, prompt, mime_type, retries, backoff)
    finally:
        if orig is None:
            try:
                delattr(compat, 'model')
            except Exception:
                pass
        else:
            compat.model = orig


