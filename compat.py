from typing import Any
import time

from gemini_client import image_analyze, text_generate
from utils import truncate as truncate_for_line


def build_outfit_prompt(user_name: str, user_text: str, user_state_time: str) -> str:
    return f"使用者：{user_name}\n描述：{user_text}\n時間：{user_state_time}"


class _DefaultModel:
    def generate_content(self, parts: Any, request_options=None):
        # parts can be [ {mime_type,data}, prompt ] or prompt string
        if isinstance(parts, (list, tuple)) and parts and isinstance(parts[0], dict) and parts[0].get('data'):
            img = parts[0].get('data')
            prompt = parts[1] if len(parts) > 1 else ''
            text = image_analyze(img, prompt)
            return type('Resp', (), {'text': text})()
        else:
            prompt = parts if isinstance(parts, str) else ''
            text = text_generate(prompt)
            return type('Resp', (), {'text': text})()


# exportable model variable so tests can monkeypatch
model = _DefaultModel()


def call_gemini_with_retries(image_bytes: bytes, prompt: str, mime_type: str, retries: int = 3, backoff: float = 1.5) -> str:
    parts = [{"mime_type": mime_type, "data": image_bytes}, prompt]
    last_exc = None
    for attempt in range(max(1, retries)):
        try:
            resp = model.generate_content(parts, request_options=None)
            if hasattr(resp, 'text'):
                return resp.text
            if getattr(resp, 'output', None):
                return resp.output[0].get('content', [{}])[0].get('text', '')
            return str(resp)
        except Exception as e:
            last_exc = e
            if attempt == retries - 1:
                raise
            time.sleep(backoff * (2 ** attempt))
    if last_exc:
        raise last_exc
    raise RuntimeError('unknown gemini error')
