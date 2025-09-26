from shopping_queries import build_queries


def test_build_queries_basic():
    suggestions = ["白色 襯衫 合身", "休閒"]
    queries = build_queries(suggestions, scene='面試', purpose='正式')
    # should produce several queries and contain some Japanese tokens
    joined = ' '.join(queries)
    assert any(x in joined for x in ['ホワイト', 'シャツ', 'スリム', '面接', 'メンズ'])
    # dedupe
    assert len(set(queries)) == len(queries)
