from shopping import build_queries_from_suggestions


def test_build_queries_basic():
    suggestions = [
        '白色 素T',
        '牛仔褲 直筒',
        '皮革 樂福鞋',
    ]
    q = build_queries_from_suggestions(suggestions, scene='上班', purpose='正式', time_weather='白天')
    assert isinstance(q, list)
    assert len(q) > 0
    # should include color/品項 and site: tags
    assert any('白色' in s for s in q)
    assert any('素T' in s or 'T' in s for s in q)
    assert any('site:' in s for s in q)
