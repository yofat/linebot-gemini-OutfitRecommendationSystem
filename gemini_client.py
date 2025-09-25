import os
import time
import random
import logging
from typing import Optional, Any

try:
    import google.generativeai as genai
except Exception:
    genai = None

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
