# Week 5 Write-up — Data Explorer MCP Server

**Agent / MCP client:** Claude Code (VS Code extension), connected to `server.py` over STDIO
through the project's `.mcp.json`.

## 1. Transcript: agent calling both tools

Real tool calls made by Claude Code through the connected `data-explorer` server
(long lists shortened with `...`):

```text
User: Find countries whose name contains "land", show 5.
Tool call: search_countries({"query": "land", "limit": 5})
Result: {"result": [{"name": "Åland Islands", "capital": "Mariehamn", "region": "Europe", "subregion": "Northern Europe"},
 {"name": "French Southern and Antarctic Lands", "capital": "Port-aux-Français", "region": "Antarctic", "subregion": ""},
 {"name": "Bermuda", ...}, {"name": "Caribbean Netherlands", ...}, {"name": "Bouvet Island", "capital": null, ...}]}

User: Give me the details for Japan.
Tool call: get_country_details({"name": "Japan"})
Result: {"name": "Japan", "official_name": "Japan", "cca3": "JPN",
 "currencies": [{"code": "JPY", "name": "Japanese yen", "symbol": "¥"}],
 "languages": ["Japanese"], "borders": [],
 "flag_url": "https://raw.githubusercontent.com/mledoze/countries/master/data/jpn.svg"}

User: Give me the details for Turkey.
Tool call: get_country_details({"name": "Turkey"})
Result: {"name": "Türkiye", "official_name": "Republic of Türkiye", "cca3": "TUR",
 "currencies": [{"code": "TRY", "name": "Turkish lira", "symbol": "₺"}],
 "languages": ["Turkish"],
 "borders": [{"code": "ARM", "name": "Armenia"}, {"code": "AZE", "name": "Azerbaijan"}, ..., {"code": "SYR", "name": "Syria"}],
 "flag_url": "https://raw.githubusercontent.com/mledoze/countries/master/data/tur.svg"}

User: Give me the details for Atlantis.
Tool call: get_country_details({"name": "Atlantis"})
Result: {"error": "no country found matching 'Atlantis'", "hint": "use search_countries to find the exact name"}

User: Search countries with an empty query.
Tool call: search_countries({"query": ""})
Result: {"result": [{"error": "query must not be empty"}]}
```

## 2. Transcript: MCP client test run

`scripts/demo_client.py` uses the official MCP Python client to start the server over STDIO,
list its tools, and call them with good and bad input. Output (long lists shortened with `...`):

```text
server: data-explorer
tools: ['search_countries', 'get_country_details']

>>> search_countries({"query": "guinea", "limit": 5})
[{"name": "Guinea", "capital": "Conakry", "region": "Africa", "subregion": "Western Africa"},
 {"name": "Guinea-Bissau", ...}, {"name": "Equatorial Guinea", ...}, {"name": "Papua New Guinea", ...}]

>>> get_country_details({"name": "Turkey"})
{"name": "Türkiye", "official_name": "Republic of Türkiye", "cca3": "TUR",
 "currencies": [{"code": "TRY", "name": "Turkish lira", "symbol": "₺"}],
 "languages": ["Turkish"],
 "borders": [{"code": "ARM", "name": "Armenia"}, ..., {"code": "SYR", "name": "Syria"}],
 "flag_url": "https://raw.githubusercontent.com/mledoze/countries/master/data/tur.svg"}

>>> get_country_details({"name": "guin"})
{"error": "'guin' matches 4 countries; be more specific",
 "matches": ["Equatorial Guinea", "Guinea", "Guinea-Bissau", "Papua New Guinea"]}

>>> get_country_details({"name": "Atlantis"})
{"error": "no country found matching 'Atlantis'", "hint": "use search_countries to find the exact name"}

>>> search_countries({"query": "   "})
{"error": "query must not be empty"}

>>> search_countries({"query": "ger", "limit": 500})
{"error": "limit must be an integer from 1 to 50"}
```

## 3. How I handled errors

All network handling lives in `load_countries()`. It turns every failure into one
`DataUnavailable` exception with a short, safe message. Timeouts, HTTP status errors,
connection errors, invalid JSON and an unexpected data format each get their own message.
Both tools catch that exception and return it as `{"error": ...}`, so a failure never
crashes the server or leaks a stack trace. Failed downloads are not cached, so the next
call retries.

Input is validated before any network call: the text must be a non-blank string of at most
100 characters, and `limit` must be an integer from 1 to 50. Not-found and ambiguous
names return a `hint` or the list of `matches`, so the agent knows what to do next instead
of guessing.

36 offline pytest tests check each case against mocked HTTP responses. The live runs
caught three things the starter didn't handle:
- The flag files are lowercase (`deu.svg`). Formatting the URL with the raw `cca3` code,
  as the starter hint suggests, gives a 404.
- The dataset calls Turkey "Türkiye", so `"Turkey"` was "not found" until I also matched
  the dataset's alternate spellings.
- When the MCP client launched the server without my network settings, every fetch failed,
  but the server kept running and returned clean errors.

## 4. What I learned

An MCP server decides exactly what context an agent can reach: the agent sees only the
tools I expose, the arguments I accept, and the fields I return. That makes the return
shape a design decision. I resolve border codes to names and keep the fields the agent
actually needs, so it doesn't pull a large raw record into its context. Errors are context
too: a structured message with a hint lets the agent recover on its own, for example by
calling `search_countries` after a failed lookup. A raw exception would just end the attempt.
Limits such as the 1–50 `limit` cap keep a single call from flooding the context window.
