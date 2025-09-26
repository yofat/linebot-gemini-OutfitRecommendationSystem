from shopping_queries import build_queries


def test_build_queries_with_gender_and_preferences():
    suggestions = ["白色 襯衫 合身", "牛仔褲"]
    queries = build_queries(suggestions, scene='上班', purpose='正式', time_weather='白天', gender='女性', preferences=['蕾絲', '合身'])
    joined = ' '.join(queries)
    # should include translated Japanese tokens for gender and preferences
    assert 'レディース' in joined or 'メンズ' in joined
    assert 'レース' in joined
    assert 'スリム' in joined or 'オーバーサイズ' in joined
    # should return a list with at most 6 items
    assert isinstance(queries, list)
    assert 1 <= len(queries) <= 6
