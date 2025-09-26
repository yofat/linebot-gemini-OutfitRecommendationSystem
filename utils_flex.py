from typing import List, Dict, Any

def _format_price(price: int) -> str:
    if price is None:
        return '價格不明'
    return f"¥{price:,}"


def flex_rakuten_carousel(products: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a Flex carousel dict compatible with LINE's Flex Message for up to 10 products."""
    bubbles = []
    for p in products[:10]:
        title = p.get('title') or ''
        price_text = _format_price(p.get('price'))
        shop = p.get('shop') or ''
        rating = p.get('rating')
        reviews = p.get('reviews')
        image = p.get('image')
        url = p.get('url') or ''

        rating_text = ''
        if rating is not None:
            rating_text = f"{rating:.1f}★"
            if reviews is not None:
                rating_text += f" ({reviews})"

        bubble = {
            'type': 'bubble',
            'hero': {'type': 'image', 'url': image, 'size': 'full', 'aspectRatio': '20:13', 'aspectMode': 'cover'} if image else None,
            'body': {
                'type': 'box',
                'layout': 'vertical',
                'contents': [
                    {'type': 'text', 'text': title, 'wrap': True, 'weight': 'bold', 'size': 'sm'},
                    {'type': 'text', 'text': price_text, 'wrap': True, 'color': '#FF5722', 'size': 'sm', 'margin': 'md'},
                    {'type': 'text', 'text': shop, 'wrap': True, 'size': 'xs', 'color': '#999999', 'margin': 'md'},
                    {'type': 'text', 'text': rating_text, 'wrap': True, 'size': 'xs', 'color': '#999999', 'margin': 'sm'},
                ],
            },
            'footer': {
                'type': 'box',
                'layout': 'vertical',
                'contents': [
                    {'type': 'button', 'action': {'type': 'uri', 'label': '查看商品', 'uri': url}, 'style': 'primary'}
                ],
            },
        }

        # remove None hero if no image
        if bubble.get('hero') is None:
            del bubble['hero']

        bubbles.append(bubble)

    carousel = {'type': 'carousel', 'contents': bubbles}
    return {'type': 'flex', 'altText': '推薦商品', 'contents': carousel}


def format_for_flex(products: List[Dict[str, Any]], currency: str = 'JPY') -> Dict[str, Any]:
    """Compatibility wrapper used by existing tests expecting shopping.format_for_flex"""
    # return a structure similar to the legacy shopping.format_for_flex:
    # - if products exist -> {'type': 'carousel', 'contents': [bubbles...]}
    # - if no products -> {'type': 'text', 'text': '暫時找不到...'}
    bubbles = []
    for p in products[:10]:
        title = p.get('title') or p.get('url')
        if len(title) > 40:
            title_short = title[:37] + '...'
        else:
            title_short = title
        domain = p.get('source') or p.get('shop') or ''
        price_text = p.get('price_text') or p.get('price')
        footer_text = domain
        if price_text:
            footer_text = f"{footer_text} • {price_text}"
        bubble = {
            'type': 'bubble',
            'body': {
                'type': 'box',
                'layout': 'vertical',
                'contents': [
                    {'type': 'text', 'text': title_short, 'wrap': True, 'weight': 'bold', 'size': 'md'},
                    {'type': 'text', 'text': footer_text, 'wrap': True, 'size': 'xs', 'color': '#8c8c8c', 'margin': 'md'},
                ]
            },
            'footer': {'type': 'box', 'layout': 'vertical', 'contents': [
                {'type': 'button', 'style': 'link', 'action': {'type': 'uri', 'label': '查看商品', 'uri': p.get('url')}}
            ]}
        }
        bubbles.append(bubble)

    if not bubbles:
        return {'type': 'text', 'text': '暫時找不到符合建議的單品，請改用品牌或顏色關鍵字再試。'}
    return {'type': 'carousel', 'contents': bubbles}
