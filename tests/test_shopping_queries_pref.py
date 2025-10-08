from shopping_queries import build_queries, APPAREL_KEYWORDS, FOOTWEAR_KEYWORDS


def test_build_queries_with_gender_and_preferences():
    """Test that build_queries generates focused queries with gender.
    
    New strategy (simplified):
    - Focus on clothing items + colors + gender
    - Ignore scene/purpose/time_weather to avoid mixed language issues
    - Preferences are optional and not always included in final queries
    """
    suggestions = ["白色 襯衫 合身", "牛仔褲"]
    queries = build_queries(suggestions, scene='上班', purpose='正式', time_weather='白天', gender='女性', preferences=['蕾絲', '合身'])
    joined = ' '.join(queries)
    
    # Should include gender
    assert 'レディース' in joined or 'メンズ' in joined
    
    # New strategy: preferences may not be included (focusing on items only)
    # assert 'レース' in joined  # Removed - preferences not guaranteed
    # assert 'スリム' in joined or 'オーバーサイズ' in joined  # Removed
    
    # Ensure only apparel-related terms (no banned items)
    banned = ['バッグ', 'アクセ', 'ジュエリー', 'ネックレス']
    assert all(not any(b in q for b in banned) for q in queries)
    
    # Every query should have at least one apparel keyword
    apparel_keywords = {kw for kw in APPAREL_KEYWORDS | FOOTWEAR_KEYWORDS}
    for q in queries:
        assert any(kw in q for kw in apparel_keywords), f"Query '{q}' has no apparel keyword"
    
    # Should return a list with reasonable length
    assert isinstance(queries, list)
    assert 1 <= len(queries) <= 6
    
    # New strategy: queries should be focused and simple
    # Example: "レディース ホワイト シャツ" not "レディース ホワイト シャツ 上班 正式"
    for q in queries:
        # Check queries don't contain untranslated Chinese
        for char in q:
            if '\u4e00' <= char <= '\u9fff':
                raise AssertionError(f"Query contains Chinese character: {q}")
