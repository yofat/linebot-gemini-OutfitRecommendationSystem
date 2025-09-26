from typing import List

# basic Chinese->Japanese map for colors/items/scenes/styles (expandable)
CN_JP_MAP = {
    # colors
    "白": "ホワイト",
    "白色": "ホワイト",
    "黑": "ブラック",
    "黑色": "ブラック",
    "藍": "ブルー",
    "藍色": "ブルー",
    "紅": "レッド",
    "紅色": "レッド",
    "綠": "グリーン",
    "綠色": "グリーン",
    "灰": "グレー",
    "灰色": "グレー",
    # items
    "襯衫": "シャツ",
    "襯衫短袖": "半袖シャツ",
    "短袖": "半袖",
    "長袖": "長袖",
    "T恤": "Tシャツ",
    "素T": "Tシャツ",
    "外套": "ジャケット",
    "外套(大衣)": "コート",
    "褲子": "パンツ",
    "牛仔褲": "ジーンズ",
    "裙子": "スカート",
    "洋裝": "ワンピース",
    "鞋": "シューズ",
    "運動鞋": "スニーカー",
    # scenes/purposes
    "面試": "面接",
    "上班": "ビジネス",
    "休閒": "カジュアル",
    "正式": "フォーマル",
    "聚會": "パーティー",
    "海邊": "ビーチ",
    # time/weather
    "夏": "夏",
    "冬": "冬",
    "傍晚": "夕方",
    "白天": "昼間",
    # styles
    "合身": "スリム",
    "寬鬆": "オーバーサイズ",
    "修身": "スリム",
    # gender
    "男性": "メンズ",
    "男": "メンズ",
    "女性": "レディース",
    "女": "レディース",
    "不公開": "ユニセックス",
    # more detailed items / preferences
    "短裙": "ミニスカート",
    "長裙": "ロングスカート",
    "蕾絲": "レース",
    "一件式洋裝": "ワンピース",
    "連身裙": "ワンピース",
    "吊帶裙": "キャミソールドレス",
    "蕾絲長裙": "レースロングスカート",
    "針織": "ニット",
    "針織外套": "ニットカーディガン",
    "開衫": "カーディガン",
    "樂福鞋": "ローファー",
    "拖鞋": "サンダル",
    "高跟鞋": "ハイヒール",
    "短褲": "ショートパンツ",
    "無鋼圈內衣": "ワイヤレスブラ",
    "運動褲": "トレーニングパンツ",
    "直筒": "ストレート",
    "合身": "スリム",
    "修身": "スリム",
    "oversize": "オーバーサイズ",
}


def translate_token(token: str) -> str:
    # crude normalisation
    t = token.strip()
    # remove trailing punctuation
    t = t.strip(' .，,、')
    # try exact map, then lowercase key
    if t in CN_JP_MAP:
        return CN_JP_MAP[t]
    tl = t.lower()
    return CN_JP_MAP.get(tl, t)


def build_queries(suggestions: List[str], scene: str, purpose: str, time_weather: str = '', gender: str = '', preferences: List[str] = None) -> List[str]:
    """Build up to 6 distinct Rakuten-friendly Japanese queries from suggestions + scene/purpose.

    - use first 2-3 suggestions
    - add a メンズ variant for garment items
    - de-duplicate and cap length <= 80
    """
    tokens = []
    # take up to first 3 suggestions
    for s in (suggestions or [])[:3]:
        for part in s.replace('/', ' ').split():
            tokens.append(part)

    # include scene/purpose/time and ensure they're added as tokens
    for ctx in (scene, purpose, time_weather):
        if ctx:
            tokens.append(ctx)

    # include gender and preferences tokens
    if gender:
        tokens.append(gender)
    if preferences:
        for p in preferences:
            tokens.append(p)

    # translate tokens where possible
    jp_tokens = [translate_token(t) for t in tokens if t]

    # new signature supports gender and preferences via kwargs in a backward-compatible way
    queries = []
    # primary query: join all
    main = ' '.join(jp_tokens).strip()
    if main:
        queries.append(main)

    # try smaller combinations
    for i in range(len(jp_tokens)):
        for j in range(i, min(len(jp_tokens), i + 3)):
            q = ' '.join(jp_tokens[i : j + 1])
            if q and q not in queries:
                queries.append(q)
            if len(queries) >= 6:
                break
        if len(queries) >= 6:
            break

    # add メンズ / レディース variants for item-like tokens depending on gender preference
    men_added = []
    for q in list(queries):
        if any(x in q for x in ['シャツ', 'Tシャツ', 'パンツ', 'ジャケット', 'ワンピース', 'スカート', 'ジーンズ']):
            # add generic メンズ
            mq = f"メンズ {q}"
            if mq not in queries and len(queries) < 6:
                men_added.append(mq)
            # add レディース
            lq = f"レディース {q}"
            if lq not in queries and len(queries) + len(men_added) < 6:
                men_added.append(lq)

    queries.extend(men_added)

    # sanitize: length cap and dedupe
    out = []
    seen = set()
    for q in queries:
        qq = q.strip()
        if len(qq) > 80:
            qq = qq[:80]
        if qq not in seen:
            seen.add(qq)
            out.append(qq)
        if len(out) >= 6:
            break

    return out

