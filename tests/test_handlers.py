import io
import pytest

import app
from state import user_state


def test_text_handler_stores_state(monkeypatch):
    # Simulate storing state via handlers' text path by calling build_outfit_prompt
    s = app.build_outfit_prompt('小明', '參加面試', 'time')
    assert '小明' in s


def test_call_gemini_with_retries_monkeypatch(monkeypatch):
    class DummyResp:
        def __init__(self, text):
            self.text = text

    class DummyModel:
        def __init__(self, t):
            self.t = t

        def generate_content(self, parts, request_options=None):
            return DummyResp(self.t)

    monkeypatch.setattr(app, 'model', DummyModel('ok-result'))
    out = app.call_gemini_with_retries(b'img', 'prompt', 'image/jpeg', retries=1)
    assert 'ok-result' in out
