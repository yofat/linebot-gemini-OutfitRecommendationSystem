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
# Render's Secret Files feature writes plaintext files to /etc/secrets/<NAME>.
# If the deploy used Secret Files instead of environment variables, try to load
# those file contents into os.environ so the rest of the app (which uses
# os.getenv) works without changes.
def _load_secrets_from_files(keys, base_path='/etc/secrets'):
    for k in keys:
        if os.getenv(k) is None:
            p = os.path.join(base_path, k)
            try:
                if os.path.exists(p):
                    with open(p, 'r', encoding='utf-8') as f:
                        v = f.read().strip()
                        if v:
                            os.environ[k] = v
            except Exception:
                # best-effort logging; don't fail app startup
                try:
                    logging.getLogger(__name__).exception('failed loading secret file %s', p)
                except Exception:
                    pass


# load commonly-used secrets from files if present
_load_secrets_from_files([
    'LINE_CHANNEL_ACCESS_TOKEN', 'LINE_CHANNEL_SECRET', 'GENAI_API_KEY', 'SENTRY_DSN', 'REDIS_URL'
])

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


# --- Debug endpoints (safe: do NOT return secrets) ---
@app.route('/_debug/handler_status', methods=['GET'])
def _debug_handler_status():
    # Return whether handler and line_bot_api are initialized (boolean only)
    return {
        'handler_initialized': bool(handler),
        'line_bot_api_initialized': bool(line_bot_api)
    }, 200


@app.route('/_debug/env_presence', methods=['GET'])
def _debug_env_presence():
    # Check presence (not values) of important env vars used by the app
    keys = ['LINE_CHANNEL_SECRET', 'LINE_CHANNEL_ACCESS_TOKEN', 'GENAI_API_KEY', 'SENTRY_DSN', 'REDIS_URL']
    result = {k: (os.getenv(k) is not None) for k in keys}
    return result, 200


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


