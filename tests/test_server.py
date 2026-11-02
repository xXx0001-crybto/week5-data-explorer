"""Tests for both tools. The network is mocked, so these run offline and fast."""
import httpx
import pytest

import server

FAKE = [
    {"name": {"common": "Germany", "official": "Federal Republic of Germany"},
     "cca2": "DE", "cca3": "DEU", "capital": ["Berlin"], "region": "Europe",
     "subregion": "Western Europe", "currencies": {"EUR": {"name": "Euro", "symbol": "€"}},
     "languages": {"deu": "German"}, "borders": ["AUT", "FRA"]},
    {"name": {"common": "Austria", "official": "Republic of Austria"},
     "cca2": "AT", "cca3": "AUT", "capital": ["Vienna"], "region": "Europe",
     "subregion": "Central Europe", "currencies": {"EUR": {"name": "Euro", "symbol": "€"}},
     "languages": {"bar": "Austro-Bavarian German", "deu": "German"}, "borders": ["DEU"]},
    {"name": {"common": "France", "official": "French Republic"},
     "cca2": "FR", "cca3": "FRA", "capital": ["Paris"], "region": "Europe",
     "subregion": "Western Europe", "currencies": {"EUR": {"name": "Euro", "symbol": "€"}},
     "languages": {"fra": "French"}, "borders": ["DEU"]},
    {"name": {"common": "Guinea", "official": "Guinea"}, "cca2": "GN", "cca3": "GIN",
     "capital": ["Conakry"], "region": "Africa", "subregion": "Western Africa",
     "currencies": {"GNF": {"name": "Guinean franc", "symbol": "Fr"}},
     "languages": {"fra": "French"}, "borders": []},
    {"name": {"common": "Guinea-Bissau", "official": "Republic of Guinea-Bissau"},
     "cca2": "GW", "cca3": "GNB", "region": "Africa", "borders": ["GIN"]},
    {"name": {"common": "Papua New Guinea", "official": "Independent State of Papua New Guinea"},
     "cca2": "PG", "cca3": "PNG", "region": "Oceania", "borders": ["IDN"]},
    {"name": {"common": "Türkiye", "official": "Republic of Türkiye"}, "cca2": "TR",
     "cca3": "TUR", "capital": ["Ankara"], "region": "Asia", "subregion": "Western Asia",
     "altSpellings": ["TR", "Turkiye", "Republic of Turkey"], "borders": []},
    {"name": {"common": "Antarctica", "official": "Antarctica"}, "cca2": "AQ",
     "cca3": "ATA", "region": "Antarctic", "currencies": {}, "languages": {}},
]


@pytest.fixture(autouse=True)
def fake_data(monkeypatch):
    """Serve FAKE from a mocked HTTP call and reset the cache for every test."""
    monkeypatch.setattr(server, "_countries", None)
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _response(200, json=FAKE))


def _response(status, **kwargs):
    return httpx.Response(status, request=httpx.Request("GET", server.DATA_URL), **kwargs)


def _fail_with(monkeypatch, exc=None, response=None):
    def fake_get(*a, **k):
        if exc:
            raise exc
        return response
    monkeypatch.setattr(httpx, "get", fake_get)


# --- get_country_details: success -------------------------------------------------

def test_details_returns_full_shape():
    d = server.get_country_details("Germany")
    assert d == {
        "name": "Germany",
        "official_name": "Federal Republic of Germany",
        "cca3": "DEU",
        "currencies": [{"code": "EUR", "name": "Euro", "symbol": "€"}],
        "languages": ["German"],
        "borders": [{"code": "AUT", "name": "Austria"}, {"code": "FRA", "name": "France"}],
        "flag_url": "https://raw.githubusercontent.com/mledoze/countries/master/data/deu.svg",
    }


@pytest.mark.parametrize("query", ["germany", "  GERMANY ", "Federal Republic of Germany", "DE", "deu"])
def test_details_accepts_name_official_name_and_codes(query):
    assert server.get_country_details(query)["cca3"] == "DEU"


def test_details_exact_name_wins_over_partial_matches():
    assert server.get_country_details("Guinea")["cca3"] == "GIN"


def test_details_unique_partial_match_is_accepted():
    assert server.get_country_details("Papua")["name"] == "Papua New Guinea"


@pytest.mark.parametrize("query", ["Turkey", "turkiye", "Republic of Turkey", "TUR"])
def test_details_finds_country_by_former_name_or_alt_spelling(query):
    assert server.get_country_details(query)["name"] == "Türkiye"


def test_search_matches_alternate_spellings():
    assert [c["name"] for c in server.search_countries("turkey")] == ["Türkiye"]


def test_details_country_without_currency_or_borders():
    d = server.get_country_details("Antarctica")
    assert d["currencies"] == [] and d["languages"] == [] and d["borders"] == []


# --- get_country_details: failures -------------------------------------------------

def test_details_unknown_country():
    d = server.get_country_details("Atlantis")
    assert d["error"] == "no country found matching 'Atlantis'"
    assert "search_countries" in d["hint"]


def test_details_ambiguous_partial_lists_matches():
    d = server.get_country_details("guin")
    assert "matches 3 countries" in d["error"]
    assert d["matches"] == ["Guinea", "Guinea-Bissau", "Papua New Guinea"]


@pytest.mark.parametrize("bad, message", [
    ("", "name must not be empty"),
    ("   ", "name must not be empty"),
    (None, "name must be a string"),
    (42, "name must be a string"),
    ("x" * 101, "name must be at most 100 characters"),
])
def test_details_rejects_bad_input(bad, message):
    assert server.get_country_details(bad) == {"error": message}


# --- search_countries ---------------------------------------------------------------

def test_search_finds_partial_matches():
    r = server.search_countries("guinea")
    assert [c["name"] for c in r] == ["Guinea", "Guinea-Bissau", "Papua New Guinea"]
    assert r[0] == {"name": "Guinea", "capital": "Conakry", "region": "Africa",
                    "subregion": "Western Africa"}


def test_search_respects_limit():
    assert len(server.search_countries("a", limit=2)) == 2


def test_search_no_match_returns_empty_list():
    assert server.search_countries("Atlantis") == []


@pytest.mark.parametrize("query, limit, message", [
    ("", 5, "query must not be empty"),
    (None, 5, "query must be a string"),
    ("ger", 0, "limit must be an integer from 1 to 50"),
    ("ger", 51, "limit must be an integer from 1 to 50"),
    ("ger", "5", "limit must be an integer from 1 to 50"),
    ("ger", True, "limit must be an integer from 1 to 50"),
])
def test_search_rejects_bad_input(query, limit, message):
    assert server.search_countries(query, limit) == [{"error": message}]


# --- data source failures (both tools) ---------------------------------------------

FAILURES = [
    (dict(exc=httpx.ReadTimeout("slow")), "timed out after 15s"),
    (dict(exc=httpx.ConnectError("dns")), "could not reach the country data source (ConnectError)"),
    (dict(response=_response(503)), "returned HTTP 503"),
    (dict(response=_response(200, content=b"<html>not json")), "returned invalid JSON"),
    (dict(response=_response(200, json={"oops": True})), "unexpected format"),
]


@pytest.mark.parametrize("failure, message", FAILURES)
def test_both_tools_report_data_source_failures(monkeypatch, failure, message):
    _fail_with(monkeypatch, **failure)
    assert message in server.get_country_details("Germany")["error"]
    assert message in server.search_countries("ger")[0]["error"]


def test_failures_are_not_cached_so_next_call_retries(monkeypatch):
    _fail_with(monkeypatch, exc=httpx.ReadTimeout("slow"))
    assert "error" in server.get_country_details("Germany")
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _response(200, json=FAKE))
    assert server.get_country_details("Germany")["name"] == "Germany"
