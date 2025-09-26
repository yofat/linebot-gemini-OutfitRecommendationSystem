from shopping import format_for_flex


def test_flex_structure():
    products = [
        {'title': '白色素T', 'url': 'https://uniqlo.com/item/1', 'source': 'uniqlo.com', 'price_text': 'NT$299', 'price_value': 299},
        {'title': '牛仔褲', 'url': 'https://momo.com.tw/item/2', 'source': 'momo.com.tw', 'price_text': None, 'price_value': None},
        {'title': '樂福鞋', 'url': 'https://shopee.tw/item/3', 'source': 'shopee.tw', 'price_text': 'NT$1290', 'price_value': 1290},
    ]
    f = format_for_flex(products, currency='TWD')
    assert isinstance(f, dict)
    # if a carousel, must have type carousel
    assert f.get('type') in ('carousel', 'text')
    if f.get('type') == 'carousel':
        assert 'contents' in f and isinstance(f['contents'], list)
        assert len(f['contents']) == 3
