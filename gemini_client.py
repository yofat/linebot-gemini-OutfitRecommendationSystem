import os
import time
import random
import logging
from typing import Optional, Any

try:
    import google.generativeai as genai
except Exception:
    genai = None

try:
    from prompts import TASK_INSTRUCTION
except Exception:
    TASK_INSTRUCTION = ''

logger = logging.getLogger(__name__)


def _get_api_key() -> Optional[str]:
    return os.getenv('GENAI_API_KEY')


def _get_timeout() -> float:
    try:
        return float(os.getenv('GEMINI_TIMEOUT_SECONDS', '15'))
    except Exception:
        return 15.0


def _ensure_configured():
    """Configure genai SDK lazily if possible."""
    key = _get_api_key()
    if key and genai and hasattr(genai, 'configure'):
        try:
            genai.configure(api_key=key)
        except Exception:
            # best-effort configuration
            logger.debug('genai.configure failed', exc_info=True)


class GeminiError(Exception):
    pass


class GeminiTimeoutError(GeminiError):
    pass


class GeminiAPIError(GeminiError):
    pass


def _retry_backoff(attempt: int, base: float = 0.5, cap: float = 10.0) -> float:
    # exponential backoff with jitter
    exp = min(cap, base * (2 ** (attempt - 1)))
    return exp * (0.8 + random.random() * 0.4)


def _call_with_retries(func, *args, retries: int = 3, timeout: float = 10.0, **kwargs):
    """Call func with retries, exponential backoff + jitter, and per-call timeout.

    If the underlying call times out, raise GeminiTimeoutError. Other failures
    after retries raise GeminiAPIError.
    """
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            # run the potentially blocking func in a thread and enforce timeout
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(func, *args, **kwargs)
                return fut.result(timeout=timeout)
        except FutureTimeout as e:
            last_exc = e
            logger.warning('Gemini call timeout on attempt %d: %s', attempt, e)
            if attempt == retries:
                raise GeminiTimeoutError(str(e)) from e
        except Exception as e:
            last_exc = e
            logger.warning('Gemini call failed on attempt %d: %s', attempt, e)
            msg = str(e).lower()
            # hard quota/type checks
            if 'quota' in msg or 'rate limit' in msg:
                raise GeminiAPIError(str(e)) from e
        # backoff between attempts if not last
        if attempt < retries:
            wait = _retry_backoff(attempt)
            time.sleep(wait)
            continue
    raise GeminiAPIError(str(last_exc)) from last_exc


def text_generate(prompt: str, retries: int = 3, timeout: Optional[float] = None) -> str:
    if not _get_api_key() or not genai:
        return '未設定 GENAI_API_KEY'

    _ensure_configured()
    if timeout is None:
        timeout = _get_timeout()

    def _extract_text_from_resp(resp: Any) -> str:
        # Support both object-like and dict-like responses
        out = getattr(resp, 'output', None)
        if out is None and isinstance(resp, dict):
            out = resp.get('output')
        if not out:
            return str(resp)

        first = out[0]
        # try object attribute access
        content = getattr(first, 'content', None)
        if content is None and isinstance(first, dict):
            content = first.get('content')
        if not content:
            return str(resp)
        first_c = content[0]
        text = getattr(first_c, 'text', None)
        if text is None and isinstance(first_c, dict):
            text = first_c.get('text')
        return text if text is not None else str(resp)

    def _call():
        resp = genai.TextGeneration.create(model='gemini-lite', input=prompt)
        return _extract_text_from_resp(resp)

    try:
        return _call_with_retries(_call, retries=retries, timeout=timeout)
    except GeminiTimeoutError:
        logger.exception('Gemini text generation timeout')
        raise
    except GeminiAPIError:
        logger.exception('Gemini API error for text generation')
        raise
    except Exception:
        logger.exception('Unexpected error in text_generate')
        raise GeminiAPIError('Unexpected error')


def image_analyze(image_bytes: bytes, prompt: str, retries: int = 3, timeout: Optional[float] = None) -> str:
    if not _get_api_key() or not genai:
        return '未設定 GENAI_API_KEY'

    _ensure_configured()
    if timeout is None:
        timeout = _get_timeout()

    # Allow disabling image analysis via env for environments without image API support
    if os.getenv('DISABLE_IMAGE_ANALYZE', '').lower() in ('1', 'true', 'yes'):
        logger.info('Image analysis disabled via DISABLE_IMAGE_ANALYZE')
        raise GeminiAPIError('Image analysis disabled')

    def _extract_text_from_image_resp(resp: Any) -> str:
        out = getattr(resp, 'output', None)
        if out is None and isinstance(resp, dict):
            out = resp.get('output')
        if not out:
            return str(resp)
        first = out[0]
        # first may be dict or object
        content = getattr(first, 'content', None)
        if content is None and isinstance(first, dict):
            content = first.get('content')
        if not content:
            return str(resp)
        first_c = content[0]
        text = getattr(first_c, 'text', None)
        if text is None and isinstance(first_c, dict):
            text = first_c.get('text')
        return text if text is not None else str(resp)

    # Determine the available SDK entrypoint for image generation/analysis.
    # Prefer genai.ImageGeneration.create, otherwise try common older shapes.
    if hasattr(genai, 'ImageGeneration'):
        def _call():
            resp = genai.ImageGeneration.create(model='gemini-image-beta', input=[{'mime_type': 'image/jpeg', 'data': image_bytes}, prompt])
            return _extract_text_from_image_resp(resp)
    elif hasattr(genai, 'images') and hasattr(genai.images, 'generate'):
        # Some versions expose an images.generate API
        def _call():
            # attempt a reasonable call shape for images.generate
            try:
                resp = genai.images.generate(model='gemini-image-beta', image=[{'mime_type': 'image/jpeg', 'data': image_bytes}], prompt=prompt)
            except TypeError:
                # fallback: try positional args
                resp = genai.images.generate([{'mime_type': 'image/jpeg', 'data': image_bytes}], prompt)
            return _extract_text_from_image_resp(resp)
    else:
        # Clear, actionable error instead of ambiguous AttributeError + retries
        msg = (
            "google.generativeai does not expose ImageGeneration/images.generate in this environment. "
            "Please upgrade the google-generativeai package to a version that supports image APIs, or set "
            "DISABLE_IMAGE_ANALYZE=1 to skip image analysis."
        )
        logger.error(msg)
        raise GeminiAPIError(msg)

    try:
        return _call_with_retries(_call, retries=retries, timeout=timeout)
    except GeminiTimeoutError:
        logger.exception('Gemini image analyze timeout')
        raise
    except GeminiAPIError:
        logger.exception('Gemini API error for image analyze')
        raise
    except Exception:
        logger.exception('Unexpected error in image_analyze')
        raise GeminiAPIError('Unexpected error')


def analyze_outfit_image(scene: str, purpose: str, time_weather: str,
                        image_bytes: bytes, mime: str = 'image/jpeg',
                        timeout: int = 15) -> dict:
    """
    Multimodal image->JSON analyzer using the GenerativeModel content API (Free-tier friendly).

    Returns a dict matching the expected schema. On failure, returns a fallback dict with summary
    describing the reason.
    """
    if not _get_api_key() or not genai:
        raise GeminiAPIError('未設定 GENAI_API_KEY or genai not available')

    _ensure_configured()

    # Build prompt from provided context
    prompt = (
        TASK_INSTRUCTION if 'TASK_INSTRUCTION' in globals() else ''
    )
    # minimal context text
    context_text = f"場景：{scene}\n目的：{purpose}\n時間/天氣：{time_weather}\n"
    # Compose parts: first instruction/context, then image part
    parts = [
        {'type': 'input_text', 'text': prompt + '\n' + context_text},
        {'mime_type': mime, 'data': image_bytes}
    ]

    def _create_generative_model(preferred_model_name: str = 'gemini-1.5-flash'):
        """Attempt to instantiate a GenerativeModel in a way compatible with
        multiple google.generativeai SDK versions. Try common constructor
        signatures and fall back to returning an instance created without
        keyword args.
        """
        GM = getattr(genai, 'GenerativeModel', None)
        if GM is None:
            return None
        # Try common constructor signatures
        for kwargs in ({'model': preferred_model_name}, {'name': preferred_model_name}, {}):
            try:
                return GM(**kwargs) if kwargs else GM()
            except TypeError:
                # constructor didn't like kwargs, try next
                continue
        # last resort: try no-arg constructor
        try:
            return GM()
        except Exception:
            return None

    def _normalize_parts_for_sdk(parts):
        """Return a list of possible parts shapes to try for different SDKs.

        The google.generativeai SDK has changed shape expectations across
        versions. We prepare several candidate representations and try them in
        order until one succeeds.
        """
        candidates = []
        # Newer SDK shape: Content with 'parts' where each Part has either 'text' or 'inline_data'
        try:
            # Some SDK variants expect a Part with a text/message including a role
            # Ensure 'text' is a plain string and 'role' is a sibling key on the Part
            prompt_str = prompt + '\n' + context_text
            content_shape = [
                {'parts': [{'text': prompt_str, 'role': 'user'}]},
                {'parts': [{'inline_data': {'mime_type': mime, 'data': image_bytes}}]}
            ]
            candidates.append(content_shape)
        except Exception:
            # If prompt/mime/image_bytes are not available for some reason, skip
            pass
        # Original shape used in this project: [{'type':'input_text','text':...}, {'mime_type':..., 'data': ...}]
        candidates.append(parts)

        # Variant A: remove explicit 'type' key for text parts, use {'text':...}
        try:
            alt = []
            for p in parts:
                if isinstance(p, dict) and p.get('type') == 'input_text':
                    alt.append({'text': p.get('text')})
                elif isinstance(p, dict) and 'mime_type' in p and 'data' in p:
                    alt.append({'mime_type': p.get('mime_type'), 'data': p.get('data')})
                else:
                    alt.append(p)
            candidates.append(alt)
        except Exception:
            pass

        # Variant B: wrap text as content field (some SDKs expect content list)
        try:
            alt2 = []
            for p in parts:
                if isinstance(p, dict) and 'text' in p:
                    alt2.append({'content': [{'type': 'text', 'text': p.get('text')}]})
                elif isinstance(p, dict) and 'data' in p:
                    alt2.append({'image': {'mime_type': p.get('mime_type'), 'data': p.get('data')}})
                else:
                    alt2.append(p)
            candidates.append(alt2)
        except Exception:
            pass

        # Variant C: mixed simplified mapping
        try:
            alt3 = []
            for p in parts:
                if isinstance(p, dict) and p.get('type') == 'input_text':
                    alt3.append(p.get('text'))
                elif isinstance(p, dict) and 'data' in p:
                    # some sdks accept the image as bytes directly in a tuple
                    alt3.append(('image/jpeg', p.get('data')))
                else:
                    alt3.append(p)
            candidates.append(alt3)
        except Exception:
            pass

        return candidates

    def _strip_type_keys(obj):
        """Recursively remove any 'type' keys from dicts inside obj.

        Some SDKs reject any Part dict containing a 'type' field. This helper
        produces a sanitized copy suitable as a final aggressive fallback.
        """
        import copy

        def _rec(o):
            if isinstance(o, dict):
                new = {}
                for k, v in o.items():
                    if k == 'type':
                        # skip
                        continue
                    new[k] = _rec(v)
                return new
            if isinstance(o, list):
                return [_rec(i) for i in o]
            return copy.copy(o)

        return _rec(parts)

    try:
        # Prefer GenerativeModel API if available
        if hasattr(genai, 'GenerativeModel'):
            model = _create_generative_model('gemini-1.5-flash')
            if model is None:
                raise GeminiAPIError('Unable to instantiate GenerativeModel with this google.generativeai version')

            # Try multiple candidate parts shapes until one works
            last_exc = None
            tried_candidates = list(_normalize_parts_for_sdk(parts))
            # aggressive sanitized candidate (strip 'type' keys) as higher priority when unknown-field errors occur
            sanitized = _strip_type_keys(parts)
            if sanitized not in tried_candidates:
                tried_candidates.append(sanitized)

            for candidate in tried_candidates:
                try:
                    # generate_content may accept parts and request_options
                    resp = model.generate_content(candidate, generation_config={'response_mime_type': 'application/json'}, request_options={'timeout': timeout})
                    last_exc = None
                    break
                except TypeError as te:
                    # signature mismatch; try next
                    last_exc = te
                    continue
                except Exception as e:
                    # Some SDKs raise descriptive API errors (e.g. Unknown field for Part)
                    msg = str(e)
                    if 'Unknown field for Part' in msg or 'Unknown field' in msg or 'Invalid Part' in msg:
                        # if unknown field, try sanitized candidate next
                        last_exc = e
                        continue
                    # otherwise surface the error
                    raise
            if last_exc:
                # If the SDK rejects Part due to unexpected fields (common when
                # SDK/Proto definitions differ), prefer graceful fallback to
                # raising an exception which bubbles to the handler. This keeps
                # the bot responsive and allows the UI to guide the user to
                # a text-based fallback.
                msg = str(last_exc)
                logger.warning('All parts candidates failed: %s', msg)
                if 'Unknown field' in msg or 'Unknown field for Part' in msg:
                    # return a friendly fallback JSON explaining the reason
                    return _fallback_outfit_json(f'Image analysis not supported in this deployment: {msg}')
                # otherwise re-raise the last exception
                raise last_exc
            # try to extract JSON string from response
            # support object-like and dict-like
            out = getattr(resp, 'output', None) or (resp if isinstance(resp, dict) and 'output' in resp else None)
            if out and len(out) > 0:
                first = out[0]
                # content may hold the json text
                content = getattr(first, 'content', None) or (first.get('content') if isinstance(first, dict) else None)
                if content and len(content) > 0:
                    first_c = content[0]
                    text = getattr(first_c, 'text', None) or (first_c.get('text') if isinstance(first_c, dict) else None)
                    if text:
                        try:
                            import json as _json
                            parsed = _json.loads(text)
                            # Ensure shape
                            if isinstance(parsed, dict) and 'overall_score' in parsed:
                                return parsed
                            # otherwise raise to go to fallback
                            raise ValueError('invalid schema')
                        except Exception:
                            # fallthrough to fallback below
                            pass
        # If no supported API or parse failed, raise
        raise GeminiAPIError('Failed to obtain valid JSON from generative model')
    except GeminiAPIError:
        raise
    except Exception as e:
        # If the SDK/proto rejects certain Part fields (e.g. 'type'), prefer
        # to return a graceful fallback rather than raising and causing a 500
        # in the webhook handler. Log full exception for debugging.
        msg = str(e)
        logger.exception('Unexpected error during analyze_outfit_image')
        if 'Unknown field' in msg or 'Unknown field for Part' in msg:
            logger.warning('Detected SDK Part schema mismatch; returning fallback JSON')
            return _fallback_outfit_json(f'Image analysis not supported in this deployment: {msg}')
        raise GeminiAPIError(str(e))


def _fallback_outfit_json(reason: str) -> dict:
    return {
        'overall_score': 0,
        'subscores': {'fit': 0, 'color': 0, 'occasion': 0, 'balance': 0, 'shoes_bag': 0, 'grooming': 0},
        'summary': f'分析失敗: {reason}',
        'suggestions': ['', '', '']
    }
