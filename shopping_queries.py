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


COLOR_KEYWORDS = {
    'ホワイト', 'ブラック', 'ブルー', 'レッド', 'グリーン', 'グレー', 'ネイビー', 'ベージュ', 'ブラウン',
    'ピンク', 'パープル', 'イエロー', 'オレンジ', 'カーキ', 'アイボリー', 'モノトーン', 'ボルドー',
    'ライトグレー', 'ダークグレー', 'ミント', 'スカイブルー', 'ライトブルー', 'ダークブルー', 'ワインレッド',
    'シャンパン', 'グレージュ', 'テラコッタ', 'クリーム', 'アッシュ', 'マルチカラー'
}

APPAREL_KEYWORDS = {
    'シャツ', 'ブラウス', 'tシャツ', 'ティーシャツ', 'トップス', 'パンツ', 'ジーンズ', 'デニム', 'チノ', 'スラックス',
    'スカート', 'ミニスカート', 'ロングスカート', 'プリーツスカート', 'ワンピース', 'ドレス', 'ニット', 'セーター',
    'カーディガン', 'スウェット', 'フーディー', 'パーカー', 'コート', 'ジャケット', 'トレンチ', 'アウター', 'ベスト',
    'タートルネック', 'ポロシャツ', 'セットアップ', 'スーツ', 'オーバーオール', 'ジャンプスーツ', 'レギンス', 'タイツ',
    'ボトムス', 'ショートパンツ', 'ハーフパンツ', 'ロンt', 'ロングtシャツ', 'カットソー', 'スウェットパンツ', 'ブルゾン',
    'マウンテンパーカー', 'トレーナー', 'ニットワンピース', 'シャツワンピース', 'ジレ', 'キャミソール', 'タンクトップ',
    'チュニック', 'ボレロ', 'ドルマン', 'ニットベスト', 'カバーオール', 'カーゴパンツ', 'フリース', 'ダウン',
    'ダウンジャケット', 'ライダース', 'レザージャケット', 'パフスリーブ', 'ガウチョ', 'キュロット', 'サロペット',
    '袴', '訪問着', '着物', '羽織', '甚平', '浴衣', '帯', 'アンサンブル', 'ポンチョ'
}

FOOTWEAR_KEYWORDS = {
    'シューズ', 'スニーカー', 'ローファー', 'パンプス', 'ヒール', 'サンダル', 'ブーツ', 'ミュール', 'フラット', 'スリッポン', 'モカシン'
}

EXCLUDED_KEYWORDS = {
    'バッグ', 'カバン', 'バック', 'アクセサリー', 'アクセ', 'ジュエリー', 'ネックレス', 'イヤリング', 'ピアス', 'ブレスレット',
    'リング', '帽子', 'キャップ', 'ハット', 'ビーニー', 'ニット帽', 'サングラス', 'メガネ', '眼鏡', 'ウォッチ', '時計',
    '財布', 'カードケース', 'キーケース', 'スカーフ', 'マフラー', 'ストール', '手袋', 'グローブ', 'ベルト', 'ポーチ',
    'バックパック', 'リュック', 'トート', 'ショルダー', 'クラッチ', 'ボストン', 'スーツケース', 'イヤカフ', 'アンクレット',
    '髪飾り', 'ヘアアクセ', 'ヘアアクセサリー', 'ヘアピン', 'ヘアゴム', 'ヘアバンド'
}

STYLE_KEYWORDS = {
    'スリム', 'オーバーサイズ', 'リラックス', 'テーパード', 'ストレート', 'ワイド', 'タイト', 'フレア', 'ボックス', 'クロップド',
    'ロング', 'ショート', 'ミディ', 'ハイウエスト', 'ローウエスト', 'フィット', 'クラシック', 'モード', 'エレガント',
    'フェミニン', 'ストリート', 'スポーティー'
}

SCENE_KEYWORDS = {
    'ビジネス', 'カジュアル', 'フォーマル', 'パーティー', 'オフィス', 'デート', 'アウトドア', 'リラックス', 'ワーク',
    '通勤', '旅行', 'バケーション', 'ビーチ', '週末', 'キャンプ', '面接', 'オケージョン'
}

SEASON_KEYWORDS = {
    '春', '夏', '秋', '冬', '梅雨', '真冬', '真夏', 'オールシーズン', '秋冬', '春夏', '昼間', '夕方', '朝', '夜'
}

MATERIAL_KEYWORDS = {
    'コットン', 'リネン', 'シルク', 'ウール', 'カシミヤ', 'レザー', 'フェイクレザー', 'デニム', 'フリース', 'ナイロン',
    'ポリエステル', 'ツイード', 'ベロア', 'スエード', 'シフォン', 'レース', 'ジャージ', 'サテン'
}

GENERAL_KEYWORDS = {
    'コーデ', 'コーディネート', 'ファッション', 'スタイル', 'トレンド', 'おすすめ', '着回し', '着心地'
}

GENDER_KEYWORDS = {'メンズ', 'レディース', 'ユニセックス', '男女兼用', 'ジェンダーレス'}

APPAREL_KEYWORDS_LOWER = {kw.lower() for kw in APPAREL_KEYWORDS | FOOTWEAR_KEYWORDS}


def _contains_keyword(token: str, keywords: set[str]) -> bool:
    if not token:
        return False
    lower = token.lower()
    for kw in keywords:
        if not kw:
            continue
        if kw.lower() in lower:
            return True
    return False


def _classify_token(token: str) -> str:
    token = token.strip()
    if not token:
        return 'other'
    if _contains_keyword(token, EXCLUDED_KEYWORDS):
        return 'exclude'
    if _contains_keyword(token, APPAREL_KEYWORDS) or _contains_keyword(token, FOOTWEAR_KEYWORDS):
        return 'apparel'
    if token in GENDER_KEYWORDS:
        return 'gender'
    if _contains_keyword(token, COLOR_KEYWORDS):
        return 'color'
    if _contains_keyword(token, STYLE_KEYWORDS):
        return 'style'
    if _contains_keyword(token, MATERIAL_KEYWORDS):
        return 'material'
    if _contains_keyword(token, SCENE_KEYWORDS):
        return 'scene'
    if _contains_keyword(token, SEASON_KEYWORDS):
        return 'season'
    if _contains_keyword(token, GENERAL_KEYWORDS):
        return 'general'
    return 'other'


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

    groups = {
        'gender': [],
        'scene': [],
        'season': [],
        'color': [],
        'style': [],
        'material': [],
        'apparel': [],
        'general': [],
        'other': []
    }

    apparel_count = 0
    for tok in jp_tokens:
        tok = tok.strip()
        if not tok:
            continue
        category = _classify_token(tok)
        if category == 'exclude':
            continue
        if category == 'apparel':
            apparel_count += 1
        target = category if category in groups else 'other'
        groups[target].append(tok)

    # dedupe within each group while preserving order
    for key, values in groups.items():
        seen = set()
        deduped = []
        for v in values:
            if v not in seen:
                deduped.append(v)
                seen.add(v)
        groups[key] = deduped

    if apparel_count == 0:
        groups['apparel'].append('トップス')

    ordered_keys = ['gender', 'scene', 'season', 'color', 'style', 'material', 'apparel', 'general', 'other']
    filtered_tokens = []
    seen_all = set()
    for key in ordered_keys:
        for tok in groups.get(key, []):
            if tok not in seen_all:
                filtered_tokens.append(tok)
                seen_all.add(tok)

    jp_tokens = filtered_tokens
    build_queries.last_tokens = jp_tokens  # type: ignore[attr-defined]

    def _query_has_apparel(q: str) -> bool:
        ql = q.lower()
        return any(app_kw in ql for app_kw in APPAREL_KEYWORDS_LOWER)

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

    # keep only apparel-focused queries; if none remain, synthesize fallback combos
    apparel_queries = [q for q in queries if _query_has_apparel(q)]
    if apparel_queries:
        queries = apparel_queries
    else:
        fallback_queries = []
        primary_color = groups['color'][0] if groups['color'] else ''
        primary_style = groups['style'][0] if groups['style'] else ''
        primary_gender = groups['gender'][0] if groups['gender'] else ''
        base_parts = [tok for tok in (primary_gender, primary_color, primary_style) if tok]
        apparel_tokens = groups['apparel'] or ['トップス']
        for apparel_tok in apparel_tokens[:3]:
            parts = base_parts + [apparel_tok]
            q = ' '.join(parts).strip()
            if q and q not in fallback_queries:
                fallback_queries.append(q)
        queries = fallback_queries or ['トップス']

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

