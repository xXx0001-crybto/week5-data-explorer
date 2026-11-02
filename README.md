# Data Explorer — MCP Server

An MCP server (Python, `FastMCP`, STDIO transport) that gives a coding agent two tools
for looking up countries in the open **[mledoze/countries](https://github.com/mledoze/countries)**
dataset. There's no API key. The dataset is downloaded over HTTPS on the first call and cached in memory.

## Install

Requires Python 3.10+.

```bash
pip install -r requirements.txt
```

## Run

```bash
python server.py
```

The server speaks MCP over STDIO. It prints nothing and waits for a client, which is normal.
Stop it with Ctrl+C. Normally you don't start it yourself: the MCP client launches it.

To check it without an IDE, run the bundled client, which starts the server and calls both tools:

```bash
python scripts/demo_client.py server.py
```

## Register the server

### Claude Code (VS Code or terminal)

This repo includes a project-scoped `.mcp.json`, so Claude Code finds the server when you
open the folder. Approve `data-explorer` when prompted, then check it with `/mcp`.
Alternatively, register it by hand with an absolute path:

```bash
claude mcp add data-explorer -- python /absolute/path/to/server.py
```

### Claude Desktop

Add this to `claude_desktop_config.json`. On Windows, use double backslashes in the path:

```json
{
  "mcpServers": {
    "data-explorer": {
      "command": "python",
      "args": ["C:\\path\\to\\week5-data-explorer\\server.py"]
    }
  }
}
```

Restart Claude Desktop. The two tools then appear in the tools menu.

## Tool reference

### `search_countries(query, limit=5)`

Finds countries whose common name, official name, or alternate spelling contains `query`
(case-insensitive).

| Parameter | Type | Rules |
| --- | --- | --- |
| `query` | string | Required, not blank, at most 100 characters |
| `limit` | integer | 1–50, default 5 |

Returns a list of `{name, capital, region, subregion}`. No match returns `[]`.

```text
search_countries(query="guinea", limit=2)
→ [
    {"name": "Guinea", "capital": "Conakry", "region": "Africa", "subregion": "Western Africa"},
    {"name": "Guinea-Bissau", "capital": "Bissau", "region": "Africa", "subregion": "Western Africa"}
  ]
```

### `get_country_details(name)`

Returns details for exactly one country. `name` can be a common name, official name,
alternate spelling, or 2/3-letter code, e.g. `"Germany"`, `"DE"`, `"DEU"`, `"Holland"` or `"Turkey"`.
An exact match wins: `"Guinea"` means Guinea, not Guinea-Bissau. A partial name is
accepted only when it matches a single country.

| Parameter | Type | Rules |
| --- | --- | --- |
| `name` | string | Required, not blank, at most 100 characters |

```text
get_country_details(name="Turkey")
→ {
    "name": "Türkiye",
    "official_name": "Republic of Türkiye",
    "cca3": "TUR",
    "currencies": [{"code": "TRY", "name": "Turkish lira", "symbol": "₺"}],
    "languages": ["Turkish"],
    "borders": [{"code": "ARM", "name": "Armenia"}, {"code": "AZE", "name": "Azerbaijan"}, ...],
    "flag_url": "https://raw.githubusercontent.com/mledoze/countries/master/data/tur.svg"
  }
```

`currencies`, `languages` and `borders` are empty lists when a country has none
(for example, Antarctica, or islands with no land borders).

### Errors

Neither tool raises an exception. Problems come back as data the agent can read and act on.
`search_countries` wraps the error in a one-item list: `[{"error": "..."}]`.

| Situation | Result |
| --- | --- |
| Empty, blank, non-string or too-long input | `{"error": "name must not be empty"}` (etc.) |
| `limit` outside 1–50 | `{"error": "limit must be an integer from 1 to 50"}` |
| Unknown country | `{"error": "no country found matching 'Atlantis'", "hint": "use search_countries to find the exact name"}` |
| Ambiguous partial name | `{"error": "'guin' matches 4 countries; be more specific", "matches": [...]}` |
| Timeout (15 s) | `{"error": "the country data source timed out after 15s; try again shortly"}` |
| HTTP error | `{"error": "the country data source returned HTTP 503; try again later"}` |
| Network failure | `{"error": "could not reach the country data source (ConnectError)"}` |
| Invalid or unexpected JSON | `{"error": "the country data source returned invalid JSON"}` |

Failed downloads are never cached, so the next call retries.

## Tests

```bash
pytest
```

36 tests cover both tools: success cases, every bad-input case, and every data-source
failure. The network is mocked, so the tests run offline.
