import types
import pytest

from gemini_client import text_generate


class ObjResp:
    class Content:
        def __init__(self, text):
            self.text = text

    class Out:
        def __init__(self, content):
            self.content = content

    def __init__(self, text):
        self.output = [ObjResp.Out([ObjResp.Content(text)])]


def test_text_generate_with_object_like(monkeypatch):
    def fake_create(model, input):
        return ObjResp('object result')

    dummy = types.SimpleNamespace(TextGeneration=types.SimpleNamespace(create=fake_create))
    monkeypatch.setattr('gemini_client.genai', dummy)
    monkeypatch.setenv('GENAI_API_KEY', 'x')

    out = text_generate('hello')
    assert 'object result' in out


def test_text_generate_with_dict_like(monkeypatch):
    def fake_create(model, input):
        return {'output': [{'content': [{'text': 'dict result'}]}]}

    dummy = types.SimpleNamespace(TextGeneration=types.SimpleNamespace(create=fake_create))
    monkeypatch.setattr('gemini_client.genai', dummy)
    monkeypatch.setenv('GENAI_API_KEY', 'x')

    out = text_generate('hello')
    assert 'dict result' in out
