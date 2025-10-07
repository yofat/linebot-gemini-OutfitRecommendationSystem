import json
from unittest.mock import patch

from shopping_rakuten import search_items, RakutenAPIError


def fake_resp_flat():
    return {
        'count': 1,
        'hits': 1,
        'Items': [
            {
                'itemName': 'テスト商品',
                'itemPrice': 1234,
                'itemUrl': 'https://example.com/item',
                'shopName': 'ショップ',
                'reviewAverage': '4.5',
                'reviewCount': '10',
                'mediumImageUrls': [{'imageUrl': 'https://example.com/img.jpg'}],
                'affiliateUrl': 'https://aff.example.com/item',
            }
        ]
    }


def fake_resp_nested():
    return {
        'Items': [
            {'Item': {
                'itemName': 'テスト商品',
                'itemPrice': 1234,
                'itemUrl': 'https://example.com/item',
                'shopName': 'ショップ',
                'reviewAverage': '4.5',
                'reviewCount': '10',
                'mediumImageUrls': [{'imageUrl': 'https://example.com/img.jpg'}],
                'affiliateUrl': 'https://aff.example.com/item',
            }}
        ]
    }


@patch('shopping_rakuten.requests.get')
def test_search_normalize_flat(mock_get, monkeypatch):
    class R:
        status_code = 200

        def json(self):
            return fake_resp_flat()

        # avoid shadowing the imported module name inside class body
        text = __import__('json').dumps(fake_resp_flat())

    mock_get.return_value = R()
    monkeypatch.setenv('RAKUTEN_APP_ID', 'dummy')

    items, meta = search_items('テスト', max_results=1, qps=1000, return_meta=True)
    assert isinstance(items, list)
    assert len(items) == 1
    it = items[0]
    assert it['title'] == 'テスト商品'
    assert it['price'] == 1234
    assert it['url'].startswith('https://')
    assert it['image'].endswith('.jpg')
    assert meta['items_returned'] == 1
    assert meta['raw_items_count'] == 1


@patch('shopping_rakuten.requests.get')
def test_search_normalize_nested(mock_get, monkeypatch):
    class R:
        status_code = 200

        def json(self):
            return fake_resp_nested()

        text = __import__('json').dumps(fake_resp_nested())

    mock_get.return_value = R()
    monkeypatch.setenv('RAKUTEN_APP_ID', 'dummy')

    items = search_items('テスト', max_results=1, qps=1000)
    assert isinstance(items, list)
    assert len(items) == 1
    assert items[0]['title'] == 'テスト商品'
