import importlib

import shopping_rakuten


def reload_with_env(monkeypatch, **env):
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    importlib.reload(shopping_rakuten)


def reload_defaults(monkeypatch):
    reload_with_env(
        monkeypatch,
        RAKUTEN_FEMALE_GENRES=None,
        RAKUTEN_MALE_GENRES=None,
        RAKUTEN_UNISEX_GENRES=None,
        RAKUTEN_DEFAULT_GENRES=None,
    )


def test_resolve_genre_ids_by_gender(monkeypatch):
    reload_with_env(monkeypatch, RAKUTEN_FEMALE_GENRES='200001', RAKUTEN_MALE_GENRES='300001', RAKUTEN_UNISEX_GENRES='900001,900002')
    assert shopping_rakuten.resolve_genre_ids('女性') == ['200001']
    assert shopping_rakuten.resolve_genre_ids('男性') == ['300001']
    assert shopping_rakuten.resolve_genre_ids('') == ['900001', '900002']
    reload_defaults(monkeypatch)


def test_resolve_genre_ids_by_preferences(monkeypatch):
    reload_with_env(monkeypatch, RAKUTEN_FEMALE_GENRES='111,222', RAKUTEN_MALE_GENRES='333,444', RAKUTEN_UNISEX_GENRES='555')
    # preference mentions メンズ should choose male genres
    prefs = ['喜歡 メンズ 風格']
    assert shopping_rakuten.resolve_genre_ids('', prefs) == ['333', '444']
    # preference mentions レディース should choose female genres
    prefs2 = ['偏好 レディース 剪裁']
    assert shopping_rakuten.resolve_genre_ids('', prefs2) == ['111', '222']
    # mixed/neutral fallback to unisex
    prefs3 = ['質感 簡約']
    assert shopping_rakuten.resolve_genre_ids('', prefs3) == ['555']
    reload_defaults(monkeypatch)


def test_resolve_genre_ids_env_defaults(monkeypatch):
    reload_with_env(monkeypatch, RAKUTEN_FEMALE_GENRES='', RAKUTEN_MALE_GENRES='', RAKUTEN_UNISEX_GENRES='', RAKUTEN_DEFAULT_GENRES='777,888')
    # when specific lists empty, should fallback to default
    assert shopping_rakuten.resolve_genre_ids('女') == ['777', '888']
    assert shopping_rakuten.resolve_genre_ids('男性') == ['777', '888']
    assert shopping_rakuten.resolve_genre_ids('') == ['777', '888']
    reload_defaults(monkeypatch)
