# ADR-0038: Runs are a register of detached processes admitted by memory; one `pegasus` command and one window over the workspace

**Date:** 2026-10-15. **Status:** active. **Amends:** ARCHITECTURE §10.5 (the machine), §10.6 (interfaces); retires
ADR-0008's MCP server.

**Context.** The author set the interface on 2026-10-15:
- PegaSUS is a local scientific instrument run by a person exercising scientific judgment;
- there is no AI inside it, no MCP server and no scripting interface;
- a desktop window (pegasus_app) shows a run's progress, a study's outputs and the data, and a command line has full
  parity with it;
- several studies may run at once, within the machine's memory.

Before this, a study ran in the foreground of whichever shell started it, through scratchpad launchers. Its progress
existed only as free text in a log. `jobs.slot` admitted one heavy job at a time machine-wide. The commands were 39 flat
`pegasus-core` verbs, beside an MCP server parked since ADR-0008.

**Decision.**
1. **A run is a record in the workspace's register** (`jobs`): `runs/<id>/meta.json`, `log.txt` and
   `events/<pid>.jsonl`.
   - `jobs.submit` starts it as a detached process (`python -m pegasus_core.jobs execute ID`, its own process group,
     out of the starter's job object), so it outlives the window or shell that started it.
   - `jobs.stop` ends its process tree.
   - A run whose process is gone without recording its end is `lost`.
2. **Progress is typed events.**
   - `jobs.emit` writes one JSON line per event to the run's file for that process; lanes inherit `PEGASUS_RUN_DIR`, so
     no two processes interleave a line.
   - A study emits:
     - its phases (scope with the planned items and their estimates, store, lanes, products);
     - its store steps;
     - its lanes (start, end, paused, resumed, failed);
     - its items, with their lane;
     - its products;
     - its analytic body at the end.
   - The executor samples its process tree's memory: the peak goes into the record, and a `resources` event every 30 s.
3. **Memory admits among slots.**
   - Heavy slots number one per 16 GB (2 on this machine).
   - A job states the memory it needs to make progress: for a study, `study.need_gb`, its own process plus the largest
     lane its last provenance measured.
   - It starts when the machine's available memory, less what every other holder still expects to take beyond what it
     holds (`jobs.room_gb`), covers that need.
   - A study raises its expectation as it admits lanes (`jobs.expect`), and its lanes are admitted against the same
     machine-wide room. Two studies therefore share the machine lane by lane; a second study runs fewer lanes at once,
     not none.
4. **One command, `pegasus`, nouns and verbs:**
   - `study` (list, show, search, new, scope, run, audit, export);
   - `run` (start, list, show, log, events, stop, wait);
   - `data`;
   - `store` (update, links, keys, gc);
   - `explore` (the hypothesis-generating machinery, the MCP server's tools among it: blocks, lead, methods, confirm);
   - `machine`, `context`, `ui`.
   `--json` before the noun prints JSON. `pegasus study run` is a registered run followed in the shell; Ctrl+C leaves
   it running.
5. **The read models both interfaces share are `workspace`:** the studies with their bodies (cached in the folder's
   `body.json`), a study's detail, its scope, starting a study, and the context bundle.
6. **`pegasus context [STUDY]`** writes what an assistant the person consults outside PegaSUS needs:
   - PegaSUS's rules;
   - every command, from the live command tree;
   - the declaration's keys and presets;
   - the studies;
   - one study's declaration, scope, body and tables.
   Nothing in PegaSUS calls an assistant.
7. **`workspace.yml`** keeps the engine's environment for the workspace (store, data root, adoption window). A run
   started from the window, which inherits no shell, then runs as one started from a configured shell. A variable the
   process already has wins.
8. The MCP server, its script and its extra are deleted; `pegasus-core` is renamed `pegasus`.

**Evidence.** These checks ran on 2026-10-15 at the working tree over `755cf5c`:
- A two-command run (40 s, then exit 3) ran detached and was followed live in the window (pegasus_app, real service):
  state, items, exit, memory samples and log. It was recorded `failed` with "a command exited with 3".
- A stopped run's child process was gone after `jobs.stop`.
- A run whose executor was killed from outside was recorded `lost`.
- `pegasus study list` read the twenty declarations and their bodies in 0.5 s once the bodies were cached.

**Consequences.**
- The window (pegasus_app) is a view over these functions and files and computes nothing.
- The scratchpad launchers are superseded.
- Exploration commands print tables, and JSON only where they already did, until the window's exploration view needs
  them.
