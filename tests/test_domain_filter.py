from shopping import search_products, SHOP_DOMAINS


def test_domain_filter_only_whitelist():
    # craft a fake query that will likely return many domains; rely on duckduckgo-search responses
    queries = ['白色 T-shirt site:uniqlo.com tw']
    res = search_products(queries, max_results=5)
    # ensure all returned domains contain at least one whitelist substring
    for r in res:
        assert any(d in r['source'] for d in SHOP_DOMAINS)
