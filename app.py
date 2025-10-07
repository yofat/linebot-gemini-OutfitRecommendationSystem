#!/usr/bin/env python3
import os
import logging
import threading
import time
import json
import re
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
    'LINE_CHANNEL_ACCESS_TOKEN',
    'LINE_CHANNEL_SECRET',
    'GENAI_API_KEY',
    'SENTRY_DSN',
    'REDIS_URL',
    'RAKUTEN_APP_ID',
    'RAKUTEN_AFFILIATE_ID'
])

# Ensure genai is configured as early as possible to avoid races where
# lower-level google clients call google.auth.default() during import/init
# before our lazy configure runs. This is best-effort and won't expose
# secrets in logs.
try:
    from gemini_client import _ensure_configured
    _ensure_configured()
except Exception:
    # Don't fail startup for diagnostics; errors will be visible in logs
    logging.getLogger(__name__).debug('early genai configure failed', exc_info=True)

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
    keys = [
        'LINE_CHANNEL_SECRET',
        'LINE_CHANNEL_ACCESS_TOKEN',
        'GENAI_API_KEY',
        'SENTRY_DSN',
        'REDIS_URL',
        'RAKUTEN_APP_ID',
        'RAKUTEN_AFFILIATE_ID'
    ]
    result = {k: (os.getenv(k) is not None) for k in keys}
    return result, 200


@app.route('/_debug/genai_caps', methods=['GET'])
def _debug_genai_caps():
    """Return information about the installed google.generativeai module and available APIs.

    Useful to verify whether GenerativeModel or Image APIs are present in the deployed environment.
    """
    try:
        import importlib
        genai = importlib.import_module('google.generativeai')
        ver = getattr(genai, '__version__', None) or getattr(genai, 'VERSION', None)
        images_attr = hasattr(genai, 'images') and hasattr(getattr(genai, 'images'), 'generate')
        caps = {
            'module_loaded': True,
            'version': ver,
            'has_configure': hasattr(genai, 'configure'),
            'has_GenerativeModel': hasattr(genai, 'GenerativeModel'),
            'has_ImageGeneration': hasattr(genai, 'ImageGeneration'),
            'has_images_generate': bool(images_attr)
        }
    except Exception as e:
        caps = {'module_loaded': False, 'error': str(e)}

    # If the caller explicitly requests probing (slow, network calls), perform a lightweight probe
    probe_param = request.args.get('probe', '').lower()
    if probe_param in ('1', 'true', 'yes'):
        try:
            from gemini_client import probe_model_availability
            env = os.getenv('GEMINI_MODEL_CANDIDATES', '')
            if env:
                model_names = [m.strip() for m in env.split(',') if m.strip()]
            else:
                model_names = [
                    'gemini-2.5-flash',
                    'gemini-2.5-flash-preview',
                    'gemini-2.5-flash-lite',
                    'gemini-2.0-flash',
                    'gemini-2.0-flash-lite',
                    'gemini-2.0-flash-001',
                ]
            probe_results = {}
            for m in model_names:
                ok, reason = probe_model_availability(m, timeout=6.0)
                probe_results[m] = {'available': bool(ok), 'reason': reason}
            caps['probe'] = probe_results
        except Exception as e:
            caps['probe_error'] = str(e)

    return caps, 200


@app.route('/_debug/build_info', methods=['GET'])
def _debug_build_info():
    """Return lightweight build/deploy info and genai caps.

    Tries (in order):
    - environment variable COMMIT_HASH (can be set during CI/build)
    - read from .git if available
    - fallback to 'unknown'
    """
    commit = os.getenv('COMMIT_HASH')
    if not commit:
        # try to read git HEAD (best-effort; may not exist in some build setups)
        try:
            import subprocess
            p = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True, check=True)
            commit = p.stdout.strip()
        except Exception:
            commit = 'unknown'

    # reuse genai_caps endpoint logic
    try:
        import importlib
        genai = importlib.import_module('google.generativeai')
        ver = getattr(genai, '__version__', None) or getattr(genai, 'VERSION', None)
        images_attr = hasattr(genai, 'images') and hasattr(getattr(genai, 'images'), 'generate')
        caps = {
            'module_loaded': True,
            'version': ver,
            'has_configure': hasattr(genai, 'configure'),
            'has_GenerativeModel': hasattr(genai, 'GenerativeModel'),
            'has_ImageGeneration': hasattr(genai, 'ImageGeneration'),
            'has_images_generate': bool(images_attr)
        }
    except Exception as e:
        caps = {'module_loaded': False, 'error': str(e)}

    return {'commit': commit, 'genai_caps': caps}, 200


@app.route('/_debug/shop_test', methods=['GET', 'POST'])
def debug_shop_test():
    """Simple HTML form to test shopping pipeline without calling Gemini.
    GET: return form
    POST: run shopping.build_queries_from_suggestions + search_products and return JSON + Flex JSON
    """
    # use Rakuten-based shopping pipeline
    try:
        from shopping_queries import build_queries
        from shopping_rakuten import search_items, resolve_genre_ids
        from utils_flex import flex_rakuten_carousel
        from shopping import SHOP_CURRENCY
        SHOP_MAX_RESULTS = int(os.getenv('RAKUTEN_MAX_RESULTS', '8'))
    except Exception:
        return 'rakuten shopping modules not available', 500

    if request.method == 'GET':
        html = '''
        <html><body>
        <h3>Shop Test (no Gemini)</h3>
        <form method="post">
        Suggestions (one per line):<br>
        <textarea name="suggestions" rows="6" cols="60">白色 素T\n牛仔褲 直筒\n皮革 樂福鞋</textarea><br>
        Scene: <input name="scene" value="上班"><br>
        Purpose: <input name="purpose" value="正式"><br>
        Time/Weather: <input name="time_weather" value="白天"><br>
        Gender: <input name="gender" value="女性"><br>
        Preferences (space/comma separated): <input name="preferences" value="蕾絲 合身"><br>
        Max Results: <input name="max_results" value="8"><br>
        <input type="submit" value="Search">
        </form>
        </body></html>
        '''
        return html

    # POST
    suggestions_raw = request.form.get('suggestions', '')
    scene = request.form.get('scene', '')
    purpose = request.form.get('purpose', '')
    time_weather = request.form.get('time_weather', '')
    try:
        max_results = int(request.form.get('max_results') or SHOP_MAX_RESULTS)
    except Exception:
        max_results = SHOP_MAX_RESULTS

    suggestions = [s.strip() for s in suggestions_raw.splitlines() if s.strip()]
    # accept optional gender and preferences fields
    gender = request.form.get('gender', '')
    prefs_raw = request.form.get('preferences', '')
    preferences = [p.strip() for p in re.split(r'[，,;；\s]+', prefs_raw) if p.strip()]

    # build JP queries using shopping_queries.build_queries
    queries = build_queries(suggestions, scene, purpose, time_weather=time_weather, gender=gender, preferences=preferences)

    rate_limit_qps = float(os.getenv('RAKUTEN_RATE_LIMIT_QPS', '1'))
    genre_ids = resolve_genre_ids(gender, preferences)

    diagnostics = {
        'rakuten_app_id_present': bool(os.getenv('RAKUTEN_APP_ID')),
        'max_results': max_results,
        'rate_limit_qps': rate_limit_qps,
        'genre_ids': genre_ids,
        'gender': gender,
        'per_query': []
    }

    # call Rakuten search per query and aggregate up to max_results
    products = []
    for q in queries:
        entry = {'query': q, 'genre_ids': genre_ids}
        try:
            items, meta = search_items(q, max_results=max_results, qps=rate_limit_qps, return_meta=True, genre_ids=genre_ids)
            entry['items_count'] = len(items)
            if meta:
                entry['meta'] = meta
        except Exception as exc:
            entry['items_count'] = 0
            entry['error'] = str(exc)
            entry['exception_type'] = exc.__class__.__name__
            items = []
        diagnostics['per_query'].append(entry)
        for it in items:
            if len(products) >= max_results:
                break
            products.append(it)
        if len(products) >= max_results:
            break

    flex = flex_rakuten_carousel(products)
    out = {
        'queries': queries,
        'products': products,
        'flex': flex,
        'diagnostics': diagnostics,
        'genre_ids': genre_ids,
    }
    return app.response_class(json.dumps(out, ensure_ascii=False), mimetype='application/json')


@app.route('/_debug/shop_run_json', methods=['POST'])
def debug_shop_run_json():
    """Accept a Gemini-like JSON payload and run the Rakuten pipeline.
    Expected JSON body keys: suggestions (list of strings) OR suggestions_text (newline-separated string),
    optional: gender (str), preferences (list or string).
    Returns: { queries, products, flex }
    """
    try:
        payload = request.get_json(force=True)
    except Exception:
        return 'invalid json', 400

    if not payload:
        return 'empty json', 400

    suggestions = payload.get('suggestions')
    if suggestions is None:
        stxt = payload.get('suggestions_text', '') or ''
        suggestions = [s.strip() for s in stxt.splitlines() if s.strip()]

    if not isinstance(suggestions, list):
        return 'suggestions must be a list', 400

    gender = payload.get('gender', '')
    prefs = payload.get('preferences', [])
    if isinstance(prefs, str):
        import re as _re
        prefs = [p.strip() for p in _re.split(r'[，,;；\s]+', prefs) if p.strip()]

    # build queries and call Rakuten search
    try:
        from shopping_queries import build_queries
        from shopping_rakuten import search_items, resolve_genre_ids
        from utils_flex import flex_rakuten_carousel
    except Exception:
        return 'rakuten modules unavailable', 500

    queries = build_queries(suggestions, payload.get('scene', ''), payload.get('purpose', ''), time_weather=payload.get('time_weather',''), gender=gender, preferences=prefs)
    max_results = int(payload.get('max_results', os.getenv('RAKUTEN_MAX_RESULTS', '8')))
    rate_limit_qps = float(os.getenv('RAKUTEN_RATE_LIMIT_QPS', '1'))

    genre_ids = resolve_genre_ids(gender, prefs)

    diagnostics = {
        'rakuten_app_id_present': bool(os.getenv('RAKUTEN_APP_ID')),
        'max_results': max_results,
        'rate_limit_qps': rate_limit_qps,
        'genre_ids': genre_ids,
        'gender': gender,
        'per_query': []
    }

    products = []
    for q in queries:
        entry = {'query': q, 'genre_ids': genre_ids}
        try:
            items, meta = search_items(q, max_results=max_results, qps=rate_limit_qps, return_meta=True, genre_ids=genre_ids)
            entry['items_count'] = len(items)
            if meta:
                entry['meta'] = meta
        except Exception as exc:
            entry['items_count'] = 0
            entry['error'] = str(exc)
            entry['exception_type'] = exc.__class__.__name__
            items = []
        diagnostics['per_query'].append(entry)
        for it in items:
            if len(products) >= max_results:
                break
            products.append(it)
        if len(products) >= max_results:
            break

    flex = flex_rakuten_carousel(products)
    out = {
        'queries': queries,
        'products': products,
        'flex': flex,
        'diagnostics': diagnostics,
        'genre_ids': genre_ids,
    }
    return app.response_class(json.dumps(out, ensure_ascii=False), mimetype='application/json')


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


