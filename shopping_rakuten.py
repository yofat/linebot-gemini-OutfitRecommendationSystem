import os
import time
import threading
from typing import List, Dict, Any, Optional, Tuple

import requests


def _parse_genre_list(value: str) -> List[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(',') if v.strip()]


_DEFAULT_GENRES = _parse_genre_list(os.getenv('RAKUTEN_DEFAULT_GENRES', '100371,551169'))
_FEMALE_GENRES = _parse_genre_list(os.getenv('RAKUTEN_FEMALE_GENRES', '100371'))
_MALE_GENRES = _parse_genre_list(os.getenv('RAKUTEN_MALE_GENRES', '551169'))
_UNISEX_GENRES = _parse_genre_list(os.getenv('RAKUTEN_UNISEX_GENRES', '100371,551169'))


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


def resolve_genre_ids(gender: str = '', preferences: Optional[List[str]] = None) -> List[str]:
    """Return genre IDs appropriate for the provided gender/preferences."""

    gender_norm = (gender or '').strip().lower()
    prefs = preferences or []

    def _fallback(values: List[str]) -> List[str]:
        if values:
            return values
        if _DEFAULT_GENRES:
            return _DEFAULT_GENRES
        return []

    if gender_norm in ('女性', '女', 'female', 'ladies', 'レディース', '女性向'):
        return _fallback(_FEMALE_GENRES)
    if gender_norm in ('男性', '男', 'male', 'mens', 'メンズ', '男性向'):
        return _fallback(_MALE_GENRES)

    prefs_join = ' '.join(prefs).lower()
    if any(token in prefs_join for token in ['女性', 'ladies', 'レディース', '女装']):
        return _fallback(_FEMALE_GENRES)
    if any(token in prefs_join for token in ['男性', 'メンズ', 'mens']):
        return _fallback(_MALE_GENRES)

    return _fallback(_UNISEX_GENRES)


def _search_single(keyword: str, max_results: int, qps: float, genre_id: Optional[str]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    app_id = os.getenv('RAKUTEN_APP_ID')
    if not app_id:
        raise RakutenAPIError('RAKUTEN_APP_ID missing')

    _throttle(qps)

    url = 'https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601'
    params = {
        'applicationId': app_id,
        'keyword': keyword,
        'imageFlag': 1,
        'availability': 1,
        'formatVersion': 2,
        'elements': 'itemName,itemPrice,itemUrl,shopName,reviewAverage,reviewCount,mediumImageUrls,affiliateUrl,genreId',
        'hits': min(max_results, 30),
        'sort': '-reviewAverage',
    }
    if genre_id:
        params['genreId'] = genre_id

    meta: Dict[str, Any] = {'genre_id': genre_id}

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

    raw_items: List[Dict[str, Any]] = []
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
    out: List[Dict[str, Any]] = []
    for entry in raw_items:
        if isinstance(entry, dict):
            item = entry.get('Item')
            if not item:
                item = entry
        else:
            item = entry
        if not item:
            continue
        image = None
        imgs = item.get('mediumImageUrls') or []
        if imgs:
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
            'genreId': item.get('genreId'),
        })

    return out, meta


def search_items(keyword: str, max_results: int = 8, qps: float = 1.0, *, return_meta: bool = False, genre_ids: Optional[List[str]] = None) -> List[Dict[str, Any]] | Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Search Rakuten Ichiba API and return normalized list of products."""

    genre_ids = [gid for gid in (genre_ids or []) if gid]

    all_items: List[Dict[str, Any]] = []
    metas: List[Dict[str, Any]] = []

    if not genre_ids:
        items, meta = _search_single(keyword, max_results, qps, None)
        all_items.extend(items)
        metas.append(meta)
    else:
        for gid in genre_ids:
            if len(all_items) >= max_results:
                break
            items, meta = _search_single(keyword, max_results, qps, gid)
            metas.append(meta)
            all_items.extend(items)
            if len(all_items) >= max_results:
                break

    seen_urls = set()
    deduped: List[Dict[str, Any]] = []
    for item in all_items:
        url = item.get('url')
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        deduped.append(item)
        if len(deduped) >= max_results:
            break

    first_meta = metas[0] if metas else {}

    meta_out: Dict[str, Any] = {
        'genre_meta': metas,
        'total_items': len(deduped),
        'items_returned': len(deduped),
        'raw_items_total': sum(m.get('raw_items_count', 0) for m in metas),
        'raw_items_count': first_meta.get('raw_items_count') if isinstance(first_meta, dict) else None,
    }
    if deduped:
        sample = deduped[0]
        meta_out['sample_title'] = sample.get('title')
        meta_out['sample_price'] = sample.get('price')
        meta_out['sample_url'] = sample.get('url')

    if return_meta:
        return deduped, meta_out

    return deduped
