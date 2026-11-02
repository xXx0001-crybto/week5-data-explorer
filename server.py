"""Data Explorer — MCP server for Week 5.

Wraps the open `mledoze/countries` dataset and exposes it to an agent as two MCP
tools over STDIO:

    search_countries(query, limit=5)  -> list of {name, capital, region, subregion}
    get_country_details(name)         -> {name, currencies, languages, borders, flag_url, ...}

Data source: one JSON file from GitHub (no API key). It is fetched over HTTPS on the
first successful call and cached in memory. Failures (timeouts, HTTP errors, bad
JSON) are never cached, so the next call retries.

Every failure is returned as a structured `{"error": ...}` message instead of an
exception, so a bad input or a network problem never crashes the server.

Setup:
    pip install -r requirements.txt
Run (STDIO) — register this command in your MCP client:
    python server.py
"""
import httpx
from mcp.server.fastmcp import FastMCP

DATA_URL = "https://raw.githubusercontent.com/mledoze/countries/master/countries.json"
# Each country has a 3-letter `cca3` code; its flag lives at this URL.
FLAG_URL = "https://raw.githubusercontent.com/mledoze/countries/master/data/{cca3}.svg"
TIMEOUT_SECONDS = 15
MAX_LIMIT = 50
MAX_QUERY_LENGTH = 100

mcp = FastMCP("data-explorer")

_countries: list[dict] | None = None  # in-memory cache of the dataset


class DataUnavailable(Exception):
    """The dataset could not be fetched or parsed. The message is safe to show."""


def load_countries() -> list[dict]:
    """Download the dataset once and cache it. Raises DataUnavailable on any failure."""
    global _countries
    if _countries is not None:
        return _countries
    try:
        resp = httpx.get(DATA_URL, timeout=TIMEOUT_SECONDS, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
    except httpx.TimeoutException:
        raise DataUnavailable(
            f"the country data source timed out after {TIMEOUT_SECONDS}s; try again shortly"
        )
    except httpx.HTTPStatusError as exc:
        raise DataUnavailable(
            f"the country data source returned HTTP {exc.response.status_code}; try again later"
        )
    except httpx.HTTPError as exc:
        raise DataUnavailable(f"could not reach the country data source ({type(exc).__name__})")
    except ValueError:  # includes json.JSONDecodeError
        raise DataUnavailable("the country data source returned invalid JSON")
    if not isinstance(data, list) or not data:
        raise DataUnavailable("the country data source returned an unexpected format")
    _countries = data
    return _countries


def _clean_text(value: object, field: str) -> tuple[str | None, str | None]:
    """Validate a free-text argument. Returns (cleaned_text, error_message)."""
    if not isinstance(value, str):
        return None, f"{field} must be a string"
    text = value.strip()
    if not text:
        return None, f"{field} must not be empty"
    if len(text) > MAX_QUERY_LENGTH:
        return None, f"{field} must be at most {MAX_QUERY_LENGTH} characters"
    return text, None


def _names(country: dict) -> tuple[str, str]:
    name = country.get("name") or {}
    return name.get("common", ""), name.get("official", "")


def _all_names(country: dict) -> list[str]:
    """Common and official names plus alternate spellings (e.g. "Republic of Turkey")."""
    return [n for n in (*_names(country), *(country.get("altSpellings") or [])) if n]


@mcp.tool()
def search_countries(query: str, limit: int = 5) -> list[dict]:
    """Search countries by part of their common, official, or alternate name.

    Returns a list of {name, capital, region, subregion}, at most `limit` items
    (1-50, default 5). No match returns an empty list. On bad input or a data
    source failure, returns a single-item list: [{"error": "..."}].
    """
    q, error = _clean_text(query, "query")
    if error:
        return [{"error": error}]
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        return [{"error": f"limit must be an integer from 1 to {MAX_LIMIT}"}]
    try:
        countries = load_countries()
    except DataUnavailable as exc:
        return [{"error": str(exc)}]

    q = q.lower()
    results = []
    for c in countries:
        if any(q in n.lower() for n in _all_names(c)):
            results.append(
                {
                    "name": _names(c)[0],
                    "capital": (c.get("capital") or [None])[0],
                    "region": c.get("region"),
                    "subregion": c.get("subregion"),
                }
            )
            if len(results) == limit:
                break
    # No matches is not an error: return an empty list.
    return results


def _find_country(countries: list[dict], name: str) -> tuple[dict | None, dict | None]:
    """Resolve a name or code to exactly one country. Returns (country, error)."""
    key = name.lower()
    # 1. Exact match on any name, alternate spelling, or the 2/3-letter code. This
    #    makes "Guinea" mean Guinea, not Guinea-Bissau or Papua New Guinea.
    for c in countries:
        codes = [str(c.get("cca2", "")), str(c.get("cca3", ""))]
        if key in (n.lower() for n in _all_names(c) + codes):
            return c, None
    # 2. Otherwise accept a partial match only if it is unambiguous, e.g. "Turkey"
    #    matches only Türkiye's alternate spelling "Republic of Turkey".
    partial = [c for c in countries if any(key in n.lower() for n in _all_names(c))]
    if len(partial) == 1:
        return partial[0], None
    if not partial:
        return None, {
            "error": f"no country found matching '{name}'",
            "hint": "use search_countries to find the exact name",
        }
    return None, {
        "error": f"'{name}' matches {len(partial)} countries; be more specific",
        "matches": sorted(_names(c)[0] for c in partial)[:10],
    }


@mcp.tool()
def get_country_details(name: str) -> dict:
    """Get details for one country by name, alternate spelling, or 2/3-letter code
    (e.g. "Germany", "DE", "DEU", "Holland", "Turkey").

    Returns {name, official_name, cca3, currencies, languages, borders, flag_url}.
    `currencies` is a list of {code, name, symbol}; `languages` is a list of names;
    `borders` is a list of {code, name} for neighbouring countries (empty for islands).
    Ambiguous or unknown names, bad input, and data source failures return
    {"error": "..."} with a hint or the list of possible matches.
    """
    text, error = _clean_text(name, "name")
    if error:
        return {"error": error}
    try:
        countries = load_countries()
    except DataUnavailable as exc:
        return {"error": str(exc)}

    country, not_found = _find_country(countries, text)
    if not_found:
        return not_found

    by_code = {c.get("cca3"): _names(c)[0] for c in countries}
    cca3 = country.get("cca3", "")
    common, official = _names(country)
    return {
        "name": common,
        "official_name": official,
        "cca3": cca3,
        "currencies": [
            {"code": code, "name": info.get("name"), "symbol": info.get("symbol")}
            for code, info in (country.get("currencies") or {}).items()
        ],
        "languages": sorted((country.get("languages") or {}).values()),
        "borders": [
            {"code": code, "name": by_code.get(code, code)}
            for code in (country.get("borders") or [])
        ],
        "flag_url": FLAG_URL.format(cca3=cca3.lower()) if cca3 else None,
    }


if __name__ == "__main__":
    mcp.run()
