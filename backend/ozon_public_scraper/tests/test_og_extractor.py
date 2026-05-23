"""Tests for Ozon public scraper parsers."""

from pathlib import Path

from ozon_public_scraper.parsers.og_extractor import extract_og
from ozon_public_scraper.parsers.price import parse_price
from ozon_public_scraper.pipelines.sitemap import classify_slug, parse_product_url

FIXTURE = Path(__file__).parent / "fixtures" / "product_og.html"


def test_parse_price():
    assert parse_price("8 990 ₽") == 8990
    assert parse_price("12990") == 12990
    assert parse_price("") is None


def test_parse_product_url():
    p = parse_product_url("https://www.ozon.ru/product/krossovki-nike-air-123456789/")
    assert p is not None
    assert p.numeric_id == "123456789"
    assert p.slug == "krossovki-nike-air"


def test_classify_slug():
    assert classify_slug("krossovki-nike-air") == "clothing"
    assert classify_slug("shina-zimnyaya-cordiant") == "tires"
    assert classify_slug("printer-hp-laserjet") == "office"


def test_extract_og_from_fixture():
    html = FIXTURE.read_text(encoding="utf-8")
    raw = extract_og(html, url="https://www.ozon.ru/product/krossovki-nike-123456/")
    assert raw.title == "Кроссовки Nike Air Max 90"
    assert raw.price_rub == 8990
    assert raw.image_url == "https://ir.ozone.ru/s3/nike-air.jpg"
    assert "price_rub" in raw.fields_extracted
