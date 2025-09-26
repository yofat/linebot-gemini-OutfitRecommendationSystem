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
    # items
    "襯衫": "シャツ",
    "襯衫短袖": "半袖シャツ",
    "T恤": "Tシャツ",
    "素T": "Tシャツ",
    "外套": "ジャケット",
    "褲子": "パンツ",
    # scenes/purposes
    "面試": "面接",
    "上班": "ビジネス",
    "休閒": "カジュアル",
    # styles
    "合身": "スリム",
    "寬鬆": "ゆったり",
}


def translate_token(token: str) -> str:
    # crude normalisation
    t = token.strip()
    return CN_JP_MAP.get(t, t)


def build_queries(suggestions: List[str], scene: str, purpose: str) -> List[str]:
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

    # include scene/purpose
    if scene:
        tokens.append(scene)
    if purpose:
        tokens.append(purpose)

    # translate tokens where possible
    jp_tokens = [translate_token(t) for t in tokens if t]

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

    # add メンズ variants for item-like tokens
    men_added = []
    for q in list(queries):
        if any(x in q for x in ['シャツ', 'Tシャツ', 'パンツ', 'ジャケット']):
            mq = f"メンズ {q}"
            if mq not in queries and len(queries) < 6:
                men_added.append(mq)

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
