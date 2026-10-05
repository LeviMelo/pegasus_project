# ADR-0008: The tools are served over MCP, read-mostly; the reserve is spent only by an explicit, attributed call

**Date.** 2026-10-05. **Status.** Built; **paused** (author, 2026-10-05): its use and integration are to be planned with the author before anything relies on it. Realises the "MCP server" of ARCHITECTURE §9.3 and §11.1 (`tools`), moved from phase 3 to now for the exploration half.

**Evidence.** `docs/evaluation/2026-10-05-mcp-tools.md` (every tool exercised by a real client over stdio against the real `pegasus_home`; the write path on a copy of the ledger).

## Decision

1. **A thin server, the official SDK.** `pegasus_core/mcp_server.py` (`mcp` 2.x, `MCPServer`, stdio) wraps the Python API; the reusable parts it needed (`tools.fitted`, `find_leads`, `explain_lead`, `ledger_status`, `gate_status`, `Reserve.level`/`previous`) live in `tools`/`control`, where the CLI and any other front can call them. The SDK is an optional extra (`pip install -e .[mcp]`); the core never imports it. Started by `pegasus-core mcp` (or `pegasus-mcp`).
2. **Nine tools, one resource family.** Reading: `list_blocks`, `list_fields`, `get_expectation`, `search_leads`, `explain_lead`, `place_story`, `gate_status`, `ledger_status`. Writing: `confirm_claim`. Resources: the ARCHITECTURE section map and sections, the evaluation index and entries. Every answer is JSON with its provenance: data version, pegasus_data commit, code version, the fitted model's address and manifest, the tier.
3. **The exploration half cannot spend anything.** Reading tools never touch side R or write the ledger beyond what the Session already does.
4. **`confirm_claim` is the only write, and it is guarded three ways.** It spends the shared, finite confirmation reserve (side R, one LOND stream, ADR-0007), so a spend happens only if (a) the server was started with `--allow-confirm`, (b) the call has `spend=true`, and (c) it names a `caller`, recorded with the claim in the ledger spec beside the `actor` (`agent` | `person`). Anything less is a dry run that returns the level the claim would be tested at and writes nothing. The default server cannot spend.
5. **A claim is read once.** A claim already in the ledger on side R (same field, lens, locus) returns its earlier verdict and is never tested again: asking twice must not buy a second draw from the reserve.
6. **Compact answers.** Lists are capped (`limit` ≤ 200, `top` ≤ 500 cells), leads are summarised (`tools.lead_row`), and nothing the API does not compute is computed in the server.

## What it does not do

- It does not make loading quick: the first `list_fields` or `get_expectation` for a block loads the model and assembles its cells (minutes); a client needs a long tool timeout (`MCP_TOOL_TIMEOUT`, see RUNBOOK). Later calls in the same server process are quick.
- Two servers sharing one ledger could each read the LOND state before the other writes; the ledger has an in-process lock only. Run one write-enabled server per `PEGASUS_HOME`.
- `--allow-confirm` is a server-level switch the person who registers the server sets; the caller name is an attribution, not authentication.
- `gate_status` pools stored harness records (repeat runs count again) and does not store the recovery of declared positives; it says where to read it.
- Only a fitted block can be read: the server never fits (no tool starts the minutes-to-hours of `fit`).
