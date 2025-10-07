import os
import time
import threading
from typing import List, Dict, Any, Optional, Tuple

import requests


class RakutenAPIError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, payload: Optional[Any] = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


# global rate limiter (simple token with lock)
_last_call = 0.0
_lock = threading.Lock()


def _throttle(qps: float):
    global _last_call

    if qps <= 0:
        return
    delay = 1.0 / qps
    with _lock:
        now = time.time()
        to_wait = _last_call + delay - now
        if to_wait > 0:
            time.sleep(to_wait)
        _last_call = time.time()


def search_items(keyword: str, max_results: int = 8, qps: float = 1.0, *, return_meta: bool = False) -> List[Dict[str, Any]] | Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Search Rakuten Ichiba API and return normalized list of products.

    Raises RakutenAPIError on HTTP/JSON errors.
    """
    app_id = os.getenv('RAKUTEN_APP_ID')
    if not app_id:
        raise RakutenAPIError('RAKUTEN_APP_ID missing')

    # throttle
    _throttle(qps)

    url = 'https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601'
    params = {
        'applicationId': app_id,
        'keyword': keyword,
        'imageFlag': 1,
        'availability': 1,
        'formatVersion': 2,
        'elements': 'itemName,itemPrice,itemUrl,shopName,reviewAverage,reviewCount,mediumImageUrls,affiliateUrl',
        'hits': min(max_results, 30),
        'sort': '-reviewAverage',
    }

    meta: Dict[str, Any] = {}

    try:
        resp = requests.get(url, params=params, timeout=8)
    except requests.RequestException as e:
        raise RakutenAPIError('network error', payload=str(e)) from e

    meta['status_code'] = resp.status_code

    if resp.status_code != 200:
        raise RakutenAPIError('bad status', status_code=resp.status_code, payload=resp.text)

    try:
        data = resp.json()
    except ValueError as e:
        raise RakutenAPIError('invalid json', payload=resp.text) from e

    raw_items = []
    if isinstance(data, dict):
        for k in ('error', 'error_description', 'error_description_en', 'errorCode', 'errorDescription'):
            if data.get(k) is not None:
                meta[k] = data.get(k)
        if any(key in data for key in ('error', 'errorCode')):
            raise RakutenAPIError('api error', payload=data)
        meta['count'] = data.get('count')
        meta['hits'] = data.get('hits')

        raw_items = data.get('Items') or []
    elif isinstance(data, list):
        raw_items = data

    meta['raw_items_count'] = len(raw_items)
    out = []
    for entry in raw_items:
        if isinstance(entry, dict):
            item = entry.get('Item')
            if not item:
                # formatVersion=2 returns flat dicts without nested `Item`
                item = entry
        else:
            item = entry
        if not item:
            continue
        image = None
        imgs = item.get('mediumImageUrls') or []
        if imgs:
            # mediumImageUrls is list of dicts with imageUrl
            first = imgs[0]
            image = first.get('imageUrl') if isinstance(first, dict) else None

        url_use = item.get('affiliateUrl') or item.get('itemUrl')

        try:
            price = int(item.get('itemPrice')) if item.get('itemPrice') is not None else None
        except Exception:
            price = None

        try:
            rating = float(item.get('reviewAverage')) if item.get('reviewAverage') not in (None, '') else None
        except Exception:
            rating = None

        try:
            reviews = int(item.get('reviewCount')) if item.get('reviewCount') is not None else None
        except Exception:
            reviews = None

        out.append({
            'title': item.get('itemName'),
            'url': url_use,
            'price': price,
            'image': image,
            'shop': item.get('shopName'),
            'rating': rating,
            'reviews': reviews,
        })

    meta['items_returned'] = len(out)
    if out:
        sample = out[0]
        meta.setdefault('sample_title', sample.get('title'))
        meta.setdefault('sample_price', sample.get('price'))
        meta.setdefault('sample_url', sample.get('url'))

    if return_meta:
        return out, meta

    return out
