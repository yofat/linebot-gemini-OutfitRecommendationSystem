import sys
import pathlib
import builtins
import types
import pytest

# 確保可以 import workspace 根目錄的 app.py
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app


def test_truncate_for_line_short():
    s = "hello"
    assert app.truncate_for_line(s, limit=10) == "hello"


def test_truncate_for_line_long():
    s = "a" * 50
    out = app.truncate_for_line(s, limit=20)
    assert "...(內容過長已截斷)" in out


def test_build_outfit_prompt_contains_fields():
    p = app.build_outfit_prompt("小明", "參加面試", "2025-09-23 12:00:00")
    assert "小明" in p
    assert "參加面試" in p


class DummyResp:
    def __init__(self, text):
        self.text = text


class DummyModel:
    def __init__(self, result_text):
        self.result_text = result_text

    def generate_content(self, parts, request_options=None):
        return DummyResp(self.result_text)


def test_call_gemini_with_retries_success(monkeypatch):
    dummy = DummyModel("這是結果")
    monkeypatch.setattr(app, 'model', dummy)
    txt = app.call_gemini_with_retries(b"bytes", "prompt", "image/jpeg", retries=1)
    assert "這是結果" in txt


def test_call_gemini_with_retries_failure(monkeypatch):
    class BadModel:
        def generate_content(self, parts, request_options=None):
            raise RuntimeError("bad")

    monkeypatch.setattr(app, 'model', BadModel())
    with pytest.raises(RuntimeError):
        app.call_gemini_with_retries(b"bytes", "prompt", "image/jpeg", retries=2, backoff=0.1)
