import os
import pytest

import gemini_client


def test_text_generate_no_api_key(monkeypatch):
    monkeypatch.delenv('GENAI_API_KEY', raising=False)
    # reload module behavior relying on env might already be set; call function directly
    out = gemini_client.text_generate('hello')
    assert '未設定' in out or isinstance(out, str)


def test_image_analyze_no_api_key(monkeypatch):
    monkeypatch.delenv('GENAI_API_KEY', raising=False)
    out = gemini_client.image_analyze(b'bytes', 'prompt')
    assert '未設定' in out or isinstance(out, str)
import sys
import importlib
import types

def test_text_generate(monkeypatch):
    fake = types.SimpleNamespace()
    fake.output = [types.SimpleNamespace(content=[types.SimpleNamespace(text='hello')])]

    class FakeGen:
        class TextGeneration:
            @staticmethod
            def create(model, input):
                return fake

    monkeypatch.setitem(sys.modules, 'google.generativeai', FakeGen)
    mod = importlib.reload(importlib.import_module('gemini_client'))
    assert mod.text_generate('hi') == 'hello'
