import pytest
import types

from gemini_client import text_generate


class FakeResponse:
    text = 'ok result'


class FakeModels:
    @staticmethod
    def generate_content(model, contents):
        return FakeResponse()


class FakeClient:
    models = FakeModels()


class DummyGenAI:
    @staticmethod
    def Client(api_key):
        return FakeClient()


@pytest.fixture(autouse=True)
def patch_genai(monkeypatch):
    monkeypatch.setattr('gemini_client.genai', DummyGenAI)
    monkeypatch.setattr('gemini_client.types', types.SimpleNamespace())
    monkeypatch.setenv('GENAI_API_KEY', 'test')
    # Reset client to None to force re-initialization
    import gemini_client
    gemini_client._GENAI_CLIENT = None
    yield


def test_text_generate_success():
    r = text_generate('hello')
    assert 'ok result' in r
