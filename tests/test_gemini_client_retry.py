import pytest
import types

from gemini_client import text_generate


class DummyGenAI:
    class TextGeneration:
        @staticmethod
        def create(model, input):
            class Resp:
                output = [{'content': [{'text': 'ok result'}]}]

            return Resp()


@pytest.fixture(autouse=True)
def patch_genai(monkeypatch):
    dummy = types.SimpleNamespace(TextGeneration=DummyGenAI.TextGeneration)
    monkeypatch.setattr('gemini_client.genai', dummy)
    monkeypatch.setenv('GENAI_API_KEY', 'test')
    yield


def test_text_generate_success():
    r = text_generate('hello')
    assert 'ok result' in r