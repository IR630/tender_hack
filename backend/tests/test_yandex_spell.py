
from app.query.yandex_spell import parse_yandex_spell_correction


def test_parse_yandex_spell_correction_from_text():
    html = '<div>Исправлена опечатка в запросе «принтер лазерный»</div>'
    assert parse_yandex_spell_correction(html) == "принтер лазерный"


def test_parse_yandex_spell_correction_imeli_vvidu():
    html = '<span>Возможно, вы имели в виду</span> <a href="/search/?text=ноутбук">ноутбук</a>'
    assert parse_yandex_spell_correction(html) == "ноутбук"


def test_parse_yandex_spell_correction_none():
    assert parse_yandex_spell_correction("<html><body>обычная выдача</body></html>") is None
