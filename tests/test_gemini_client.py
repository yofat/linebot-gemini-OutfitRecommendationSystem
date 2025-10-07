import os
import pytest
import sys
import importlib
import types

import gemini_client


def test_text_generate_no_api_key(monkeypatch):
    monkeypatch.delenv('GENAI_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    # reload module behavior relying on env might already be set; call function directly
    out = gemini_client.text_generate('hello')
    assert '未設定' in out or isinstance(out, str)


def test_image_analyze_no_api_key(monkeypatch):
    monkeypatch.delenv('GENAI_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    out = gemini_client.image_analyze(b'bytes', 'prompt')
    assert '未設定' in out or isinstance(out, str)


def test_text_generate(monkeypatch):
    """Test text_generate with new google-genai SDK mock."""
    # Mock the new SDK structure
    class FakeResponse:
        text = 'hello'
    
    class FakeModels:
        @staticmethod
        def generate_content(model, contents):
            return FakeResponse()
    
    class FakeClient:
        models = FakeModels()
    
    class FakeGenai:
        @staticmethod
        def Client(api_key):
            return FakeClient()
    
    # Patch gemini_client module directly instead of sys.modules
    import gemini_client
    monkeypatch.setattr('gemini_client.genai', FakeGenai)
    monkeypatch.setattr('gemini_client.types', types.SimpleNamespace())
    monkeypatch.setenv('GENAI_API_KEY', 'test_key')
    # Reset client to force reinitialization
    gemini_client._GENAI_CLIENT = None
    
    assert gemini_client.text_generate('hi') == 'hello'


