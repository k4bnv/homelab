from pathlib import Path

from scraper.parse import parse_api_response, parse_search_html
from scraper.schema import SellerType

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_api_response_returns_all_items():
    raw = (FIXTURES / "sample_api_response.json").read_text(encoding="utf-8")
    listings = parse_api_response(raw)
    assert len(listings) == 4
    titles = {l.title for l in listings}
    assert "Lenovo ThinkPad T480 i5-8350U 16GB 256GB SSD" in titles


def test_parse_api_response_maps_fields():
    raw = (FIXTURES / "sample_api_response.json").read_text(encoding="utf-8")
    listings = parse_api_response(raw)
    t480 = next(l for l in listings if "T480" in l.title)
    assert t480.price == 150.0
    assert t480.location == "Amsterdam"
    assert t480.seller_type == SellerType.PARTICULIER
    assert t480.url.startswith("https://www.marktplaats.nl/")
    assert t480.images

    macbook = next(l for l in listings if "MacBook" in l.title)
    assert macbook.price == 320.0
    assert macbook.seller_type == SellerType.ZAKELIJK


def test_parse_api_response_handles_garbage():
    assert parse_api_response("not json") == []
    assert parse_api_response('{"listings": "oops"}') == []


def test_parse_search_html_next_data_fallback():
    html = (FIXTURES / "sample_next_data.html").read_text(encoding="utf-8")
    listings = parse_search_html(html)
    assert len(listings) == 4
    prices = sorted(l.price for l in listings)
    assert prices == [60.0, 90.0, 150.0, 320.0]


def test_parse_search_html_missing_next_data():
    assert parse_search_html("<html><body>no data here</body></html>") == []
