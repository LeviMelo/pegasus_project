"""Exercise the PegaSUS MCP server over stdio with a real client, against the real pegasus_home.

    python scripts/mcp_demo.py            # read-only server, real ledger: every reading tool, dry-run claims
    python scripts/mcp_demo.py --spend    # a second server with --allow-confirm on a COPY of the ledger: one spend

The write demo never touches the production reserve: the ledger is copied to a scratch directory first.
Full outputs go to data/logs/mcp_demo*.json; the console shows them cut to fit.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

from mcp import Client, StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]


def show(name: str, args: dict, result, log: list, seconds: float, width: int = 900) -> dict:
    payload = result.structured_content if result.structured_content is not None else \
        json.loads(result.content[0].text)
    log.append({"tool": name, "args": args, "seconds": round(seconds, 1), "result": payload})
    text = json.dumps(payload, ensure_ascii=False)
    print(f"\n### {name} {json.dumps(args)}  [{seconds:.1f}s{' ERROR' if result.is_error else ''}]\n"
          f"{text[:width]}{' ...' if len(text) > width else ''}", flush=True)
    return payload


async def call(client: Client, log: list, name: str, args: dict | None = None, width: int = 900) -> dict:
    t = time.time()
    r = await client.call_tool(name, args or {}, read_timeout_seconds=900)
    return show(name, args or {}, r, log, time.time() - t, width)


def params(extra: list[str]) -> StdioServerParameters:
    return StdioServerParameters(command=sys.executable, args=["-m", "pegasus_core.mcp_server", *extra],
                                 env={"PYTHONUTF8": "1", **__import__("os").environ})


async def reading(log: list) -> dict:
    async with Client(params([])) as client:
        tools = await client.list_tools()
        print("tools:", [t.name for t in tools.tools])
        res = await client.list_resources()
        tpl = await client.list_resource_templates()
        print("resources:", [str(r.uri) for r in res.resources], [t.uri_template for t in tpl.resource_templates])
        await call(client, log, "list_blocks", {"dataset": "SIM.DO"})
        await call(client, log, "gate_status", {})
        await call(client, log, "ledger_status", {})
        found = await call(client, log, "search_leads", {"triage_class": "signal", "min_replication": "R1", "limit": 5})
        if not found["leads"]:
            found = await call(client, log, "search_leads", {"triage_class": "signal", "limit": 5})
        top = found["leads"][0]
        await call(client, log, "search_leads", {"code": "I60-I69", "direction": "up", "year": 2020, "limit": 3})
        await call(client, log, "explain_lead", {"lead_id": top["id"]}, width=1800)
        if top["places"]:
            await call(client, log, "place_story", {"place": top["places"][0], "limit": 2}, width=1500)
        await call(client, log, "place_story", {"limit": 3, "triage_class": "signal"}, width=1200)
        await call(client, log, "list_fields", {"block": "IX"}, width=700)
        await call(client, log, "get_expectation", {"node": "I60-I69", "tier": "B1", "top": 5}, width=1800)
        await call(client, log, "get_expectation", {"node": "I60-I69", "tier": "B1", "places": [355030],
                                                    "years": [2019, 2020, 2021]}, width=1500)
        for uri in ("pegasus://architecture", "pegasus://architecture/9.3", "pegasus://evaluation"):
            r = await client.read_resource(uri)
            body = r.contents[0].text
            print(f"\n### resource {uri} [{len(body)} chars]\n{body[:350]}")
        # a claim built from a lead, dry run, and a refused spend on the read-only server
        claim = next((x for x in found["leads"] if x["estimand"] in
                      ("outbreak", "change_point", "space_time", "spatial_cluster") and x["years"]
                      and x["direction"] in ("up", "down")), None)
        if claim is None:
            more = await call(client, log, "search_leads", {"triage_class": "signal", "estimand": "outbreak", "limit": 1})
            claim = more["leads"][0]
        args = {"node": claim["node"], "lens": claim["estimand"], "places": claim["places"], "years": claim["years"],
                "direction": claim["direction"], "caller": "mcp_demo.py"}
        await call(client, log, "confirm_claim", args, width=1200)
        await call(client, log, "confirm_claim", {**args, "spend": True}, width=1200)
        r = await client.call_tool("confirm_claim", {**args, "caller": " "}, read_timeout_seconds=60)
        print(f"\n### confirm_claim (blank caller) -> is_error={r.is_error}: {r.content[0].text[:200]}")
        return args


async def pick_claim(client: Client, log: list) -> dict:
    more = await call(client, log, "search_leads", {"triage_class": "signal", "estimand": "outbreak", "limit": 1})
    c = more["leads"][0]
    return {"node": c["node"], "lens": c["estimand"], "places": c["places"], "years": c["years"],
            "direction": c["direction"], "caller": "mcp_demo.py"}


async def spending(log: list, args: dict | None) -> None:
    scratch = Path(tempfile.mkdtemp(prefix="pegasus_ledger_"))
    shutil.copytree(ROOT / "pegasus_home" / "ledger", scratch / "ledger")
    print(f"\n=== write server on a copy of the ledger: {scratch / 'ledger'}")
    async with Client(params(["--allow-confirm", "--ledger", str(scratch / "ledger")])) as client:
        args = args or await pick_claim(client, log)
        await call(client, log, "ledger_status", {}, width=600)
        await call(client, log, "confirm_claim", {**args, "spend": True, "actor": "agent"}, width=2200)
        await call(client, log, "confirm_claim", {**args, "spend": True}, width=900)
        await call(client, log, "ledger_status", {}, width=1500)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spend", action="store_true")
    ap.add_argument("--spend-only", action="store_true", help="skip the reading tools")
    a = ap.parse_args()
    log: list = []
    args = None if a.spend_only else asyncio.run(reading(log))
    if a.spend or a.spend_only:
        asyncio.run(spending(log, args))
    out = ROOT / "data" / "logs" / ("mcp_demo_spend.json" if a.spend_only else "mcp_demo.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nlog: {out}")


if __name__ == "__main__":
    main()
