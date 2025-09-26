from utils_flex import flex_rakuten_carousel


def test_flex_generation():
    products = [
        {'title': 'A', 'url': 'https://a', 'price': 1000, 'image': None, 'shop': 'S', 'rating': 4.2, 'reviews': 10},
        {'title': 'B', 'url': 'https://b', 'price': 2000, 'image': 'https://b.jpg', 'shop': 'S2', 'rating': 4.8, 'reviews': 5},
    ]
    flex = flex_rakuten_carousel(products)
    assert flex['type'] == 'flex'
    assert 'contents' in flex
    assert flex['contents']['type'] == 'carousel'
    assert len(flex['contents']['contents']) == 2
