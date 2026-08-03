from pathlib import Path

from filters import filter_listings
from scraper.parse import parse_api_response

FIXTURES = Path(__file__).parent / "fixtures"


def _listings():
    raw = (FIXTURES / "sample_api_response.json").read_text(encoding="utf-8")
    return parse_api_response(raw)


def test_filter_by_keyword_and_price():
    listings = _listings()
    keywords = ["laptop", "thinkpad t480", "thinkpad x1 carbon", "macbook air m1"]
    result = filter_listings(listings, keywords, min_price=0, max_price=300)
    titles = {l.title for l in result}
    assert "Lenovo ThinkPad T480 i5-8350U 16GB 256GB SSD" in titles
    assert "ThinkPad X1 Carbon defect scherm - voor onderdelen" in titles
    # MacBook Air is 320 EUR, above max_price=300 -> excluded
    assert "Apple MacBook Air M1 2020 8GB 256GB" not in titles
    # HP Pavilion doesn't match any keyword -> excluded
    assert "HP Pavilion 15 i5 8GB 128GB SSD" not in titles


def test_filter_no_keywords_matches_everything_within_price():
    listings = _listings()
    result = filter_listings(listings, [], min_price=0, max_price=100)
    assert {l.price for l in result} == {60.0, 90.0}


def test_filter_price_none_excluded():
    listings = _listings()
    for l in listings:
        l.price = None
    assert filter_listings(listings, [], min_price=0, max_price=1000) == []
