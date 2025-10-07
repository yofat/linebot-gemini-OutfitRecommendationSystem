from shopping_queries import build_queries


def test_build_queries_basic():
    suggestions = ["白色 襯衫 合身", "休閒"]
    queries = build_queries(suggestions, scene='面試', purpose='正式')
    # should produce several queries and contain some Japanese tokens
    joined = ' '.join(queries)
    assert any(x in joined for x in ['ホワイト', 'シャツ', 'スリム', '面接'])
    # 所有建議都應該是服飾/鞋類 (不含包包配件)
    banned = ['バッグ', 'アクセ', 'ネックレス', 'ハット', 'コスメ']
    assert all(not any(b in q for b in banned) for q in queries)
    # dedupe
    assert len(set(queries)) == len(queries)


def test_build_queries_fallbacks_and_tokens():
    suggestions = ["奶茶色 氣質"]  # 無明確服飾品項
    queries = build_queries(suggestions, scene='上班', purpose='正式')
    tokens = getattr(build_queries, 'last_tokens', [])
    # 若使用者沒有指出服飾，應自動補上通用服飾詞
    assert any(tok in ('トップス', 'ワンピース', 'パンツ') for tok in tokens)
    # 依然只應輸出服飾相關建議
    assert all('バッグ' not in q for q in queries)
