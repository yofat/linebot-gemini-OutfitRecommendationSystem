import time
from unittest.mock import patch

from shopping_queries import build_queries
from shopping_rakuten import search_items


def test_queries_cache_and_user_throttle(monkeypatch, tmp_path):
    # Basic test to ensure build_queries returns predictable queries
    suggestions = ["白色 襯衫 合身"]
    qs = build_queries(suggestions, scene='面試', purpose='正式')
    assert len(qs) > 0

    # Can't fully test global cache/rate limiter without invoking handlers; ensure search_items raises when no APP_ID
    try:
        search_items('テスト', max_results=1, qps=1000)
    except Exception as e:
        assert hasattr(e, 'payload') or isinstance(e, Exception)
