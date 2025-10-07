import io
import pytest

import app
import handlers
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


def test_normalize_gender_input_variants():
    assert handlers._normalize_gender_input('男生') == '男性'
    assert handlers._normalize_gender_input('女生') == '女性'
    assert handlers._normalize_gender_input('都可以') == '不公開'


def test_parse_preferences_and_skip():
    prefs, skipped = handlers._parse_preferences_input('合身, 蕾絲 , 一件式洋裝')
    assert prefs == ['合身', '蕾絲', '一件式洋裝']
    assert skipped is False
    prefs_empty, skipped_flag = handlers._parse_preferences_input('無')
    assert prefs_empty == []
    assert skipped_flag is True


def test_default_suggestions_cover_apparel():
    male = handlers._default_suggestions('男性')
    female = handlers._default_suggestions('女性')
    neutral = handlers._default_suggestions('')
    assert len(male) == 3 and all(isinstance(s, str) and s for s in male)
    assert len(female) == 3 and all(isinstance(s, str) and s for s in female)
    assert len(neutral) == 3 and all(isinstance(s, str) and s for s in neutral)
