"""Drive the Data Explorer server over STDIO with the official MCP Python client.

Usage (from the repo root):  python scripts/demo_client.py server.py
Starts the server as a subprocess, lists its tools, and calls each one with good
and bad input, printing every result. Useful for checking the server without an IDE.
"""
import asyncio
import json
import os
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

CALLS = [
    ("search_countries", {"query": "guinea", "limit": 5}),
    ("get_country_details", {"name": "Turkey"}),
    ("get_country_details", {"name": "Germany"}),
    ("get_country_details", {"name": "guin"}),
    ("get_country_details", {"name": "Atlantis"}),
    ("search_countries", {"query": "   "}),
    ("search_countries", {"query": "ger", "limit": 500}),
]

async def main():
    params = StdioServerParameters(command=sys.executable, args=[sys.argv[1]], env=dict(os.environ))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            print("server:", init.serverInfo.name)
            tools = await s.list_tools()
            print("tools:", [t.name for t in tools.tools])
            for name, args in CALLS:
                res = await s.call_tool(name, args)
                text = [c.text for c in res.content]
                body = json.loads(text[0]) if len(text) == 1 else [json.loads(t) for t in text]
                print(f"\n>>> {name}({json.dumps(args)})  isError={res.isError}")
                print(json.dumps(body, ensure_ascii=False, indent=2))

asyncio.run(main())
