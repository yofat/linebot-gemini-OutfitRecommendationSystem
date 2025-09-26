from shopping import extract_price


def test_price_variants():
    cases = {
        'NT$1,290': 1290,
        '$990': 990,
        'NT 450': 450,
        '＄2,500': 2500,
    }
    for t, v in cases.items():
        r = extract_price(t)
        assert r is not None
        assert r[1] == v
