import types
import pytest

from gemini_client import text_generate


class FakeResponse:
    def __init__(self, text):
        self.text = text


def test_text_generate_with_object_like(monkeypatch):
    """Test with new SDK structure returning object response."""
    
    class FakeModels:
        @staticmethod
        def generate_content(model, contents):
            return FakeResponse('object result')
    
    class FakeClient:
        models = FakeModels()
    
    class FakeGenai:
        @staticmethod
        def Client(api_key):
            return FakeClient()
    
    monkeypatch.setattr('gemini_client.genai', FakeGenai)
    monkeypatch.setattr('gemini_client.types', types.SimpleNamespace())
    monkeypatch.setenv('GENAI_API_KEY', 'x')
    
    # Reset client
    import gemini_client
    gemini_client._GENAI_CLIENT = None

    out = text_generate('hello')
    assert 'object result' in out


def test_text_generate_with_dict_like(monkeypatch):
    """Test with dict-like response (for compatibility)."""
    
    class FakeModels:
        @staticmethod
        def generate_content(model, contents):
            return FakeResponse('dict result')
    
    class FakeClient:
        models = FakeModels()
    
    class FakeGenai:
        @staticmethod
        def Client(api_key):
            return FakeClient()
    
    monkeypatch.setattr('gemini_client.genai', FakeGenai)
    monkeypatch.setattr('gemini_client.types', types.SimpleNamespace())
    monkeypatch.setenv('GENAI_API_KEY', 'x')
    
    # Reset client
    import gemini_client
    gemini_client._GENAI_CLIENT = None

    out = text_generate('hello')
    assert 'dict result' in out

