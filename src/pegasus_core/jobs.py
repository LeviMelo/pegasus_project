"""The machine a computation runs on, and the runs on it (ARCHITECTURE §10.5, §10.6; ADR-0038).

A heavy computation (a study, a fit, a plan's update, a measurement script) takes a **machine-wide slot** before it
starts (`slot`: OS file locks shared by every process on the machine, through pegasus_data's admission), and the GPU
job also the single **GPU slot**, so two jobs never share the 6 GB card. Among the slots, **memory admits**: a job
states the memory it needs to make progress and starts when the machine's available memory, less what the jobs already
running still expect to take (`room_gb`), holds it. It then states its **threads** (`threads`: BLAS, OpenMP, numba,
torch), because six jobs of implicit threads each made every one of them 5–20× slower (2026-10-06).

A **run** is a job in the workspace's register (`<workspace>/runs/<id>/`): ``meta.json`` (what it runs, its state, its
process, its memory), ``log.txt`` (its output) and ``events/<pid>.jsonl`` (what each of its processes did, as typed
events: `emit`). A run is a detached process (`submit` → `execute`): it outlives the window or the command that started
it, which reads its files and stops it (`stop`). It replaces `scripts/heavy.py`, `data/chain.py`, the ad hoc queues
(survey 2026-10-07, work plan S0.3) and the scratchpad launchers.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager, suppress
from pathlib import Path

from . import config

_GIB = 2**30


def _default_slots() -> int:
    """One heavy slot per 16 GB of the machine's memory (2 on a 32 GB machine), at least 1: memory admits among them."""
    import psutil

    return max(1, min(4, round(psutil.virtual_memory().total / _GIB / 16)))


#: machine-wide heavy slots (``PEGASUS_HEAVY_SLOTS``): how many heavy jobs may run at once, memory admitting each
HEAVY_SLOTS = int(os.environ.get("PEGASUS_HEAVY_SLOTS") or _default_slots())
#: what a heavy job is admitted with when it states no need (``PEGASUS_HEAVY_NEED_GB``)
DEFAULT_NEED_GB = float(os.environ.get("PEGASUS_HEAVY_NEED_GB", "4"))
STATES = ("queued", "running", "done", "failed", "stopped", "lost")


def default_threads() -> int:
    """Half the logical cores (at least 2), or ``PEGASUS_THREADS``."""
    return int(os.environ.get("PEGASUS_THREADS") or max(2, (os.cpu_count() or 4) // 2))


# ----------------------------------------------------------------------------------------------------- admission


def _holders_dir() -> Path:
    path = Path(tempfile.gettempdir()) / "pegasus_heavy_slots" / "holders"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _tree_rss_gb(pid: int) -> float:
    import psutil

    try:
        p = psutil.Process(pid)
        procs = [p, *p.children(recursive=True)]
    except psutil.Error:
        return 0.0
    total = 0
    for q in procs:
        with suppress(psutil.Error):
            total += q.memory_info().rss
    return total / _GIB


def holders() -> list[dict]:
    """The heavy jobs holding a slot now: each one's label, the memory it was admitted with (``need_gb``), what it now
    expects to hold at most (``expect_gb``, raised as it grows: a study's lanes) and what its process tree holds."""
    import psutil

    out = []
    for f in _holders_dir().glob("*.json"):
        try:
            h = json.loads(f.read_text(encoding="utf-8"))
            alive = psutil.pid_exists(h["pid"]) and abs(psutil.Process(h["pid"]).create_time() - h["created"]) < 1
        except (OSError, ValueError, KeyError, psutil.Error):
            alive = False
            h = None
        if not alive:
            with suppress(OSError):
                f.unlink()                          # a holder killed before its exit: its file is not a job
            continue
        out.append({**h, "rss_gb": round(_tree_rss_gb(h["pid"]), 2)})
    return out


def room_gb(exclude: int | None = None) -> float:
    """The memory a new job (or a new lane of a running one) may take: what the machine has available, less what every
    other holder still expects to take beyond what it holds. A job admitted at its start grows (a study's lanes), and
    admitting by available memory alone had let two studies' lanes together outgrow the machine."""
    import psutil

    me = exclude if exclude is not None else os.getpid()
    owed = sum(max(h["expect_gb"] - h["rss_gb"], 0.0) for h in holders() if h["pid"] != me)
    return psutil.virtual_memory().available / _GIB - owed


def expect(gb: float) -> None:
    """State what this job now expects to hold at most (a study as it admits a lane), so other jobs leave it room."""
    f = _holders_dir() / f"{os.getpid()}.json"
    with suppress(OSError, ValueError):
        h = json.loads(f.read_text(encoding="utf-8"))
        h["expect_gb"] = round(max(gb, h["need_gb"]), 2)
        _write_json(f, h)


def _admissible(need: float) -> tuple[bool, dict]:
    """Whether a heavy job needing ``need`` GB may start now, and why not: every heavy slot held, the machine's
    available memory under the floor pegasus_data's admission keeps (``PEGASUS_HEAVY_MIN_FREE_GB``, default 4), or too
    little room beside what the running jobs still expect (`room_gb`)."""
    import psutil

    floor = float(str(os.environ.get("PEGASUS_HEAVY_MIN_FREE_GB", "4")).replace(",", "."))
    available = psutil.virtual_memory().available / _GIB
    others = [h for h in holders() if h["pid"] != os.getpid()]
    room = room_gb()
    state = {"need_gb": round(need, 2), "room_gb": round(room, 2), "available_gb": round(available, 2),
             "floor_gb": floor, "slots": HEAVY_SLOTS, "held": len(others)}
    if len(others) >= HEAVY_SLOTS:
        return False, {**state, "reason": f"every heavy slot is held ({len(others)} of {HEAVY_SLOTS})"}
    if available < floor:
        return False, {**state, "reason": f"{available:.1f} GB available, under the {floor:.0f} GB the machine keeps free"}
    if room < need:
        return False, {**state, "reason": f"{room:.1f} GB of room beside the running jobs, {need:.1f} GB needed"}
    return True, state


@contextmanager
def slot(label: str, gpu: bool = False, need_gb: float | None = None) -> Iterator[None]:
    """Hold the machine's heavy slot (and the GPU slot with ``gpu``) while the block runs. It waits, saying why in
    ``admission`` events (`_admissible`), until a slot is free, the machine's available memory is over its floor and
    there is ``need_gb`` of room among the jobs running (default `DEFAULT_NEED_GB`), at most ``PEGASUS_HEAVY_WAIT``
    seconds; then it takes the slot (pegasus_data's admission, the OS lock) and holds it while the block runs."""
    import psutil

    from . import gateway

    if os.environ.get("PEGASUS_SLOT_HELD") == "1":         # a child of a job that holds them
        yield
        return
    need = float(need_gb or DEFAULT_NEED_GB)
    queued = time.time()
    wait = float(os.environ.get("PEGASUS_HEAVY_WAIT", "86400"))
    said, told = 0.0, 0.0
    # the wait is said before the slot is taken: inside pegasus_data's admission a run waited on its memory floor and
    # the window showed it queued with no reason (2026-10-15)
    while time.time() - queued < wait:
        ok, why = _admissible(need)
        if ok:
            break
        if time.time() - told > 30:
            emit("admission", waited_s=round(time.time() - queued, 1), **why)
            told = time.time()
        if time.time() - said > 300:
            print(f"[jobs] {label}: waiting: {why['reason']}", flush=True)
            said = time.time()
        time.sleep(5)
    with ExitStack() as stack:
        if gpu:
            stack.enter_context(gateway.machine_slot("pegasus_gpu_slots", 1, label))
        stack.enter_context(gateway.machine_slot("pegasus_heavy_slots", HEAVY_SLOTS, label))
        f = _holders_dir() / f"{os.getpid()}.json"
        _write_json(f, {"pid": os.getpid(), "created": psutil.Process().create_time(), "label": label,
                        "need_gb": round(need, 2), "expect_gb": round(need, 2), "run": os.environ.get("PEGASUS_RUN_ID"),
                        "since": time.time()})
        stack.callback(lambda: f.unlink(missing_ok=True))
        print(f"[jobs] admitted after {time.time() - queued:.0f}s with {room_gb():.1f} GB of room: {label}", flush=True)
        emit("run", state="running", waited_s=round(time.time() - queued, 1), need_gb=round(need, 2))
        if os.environ.get("PEGASUS_RUN_PID") == str(os.getpid()):       # the run's own process: its record says so
            with suppress(OSError, ValueError, LookupError):
                _update(os.environ["PEGASUS_RUN_ID"], state="running", started=_now(), need_gb=round(need, 2))
        os.environ["PEGASUS_SLOT_HELD"] = "1"
        try:
            yield
        finally:
            os.environ.pop("PEGASUS_SLOT_HELD", None)


def threads(n: int | None = None) -> int:
    """Limit this process's BLAS, OpenMP, numba and torch threads to ``n`` (default `default_threads`)."""
    n = n or default_threads()
    os.environ["PEGASUS_THREADS"] = str(n)          # what `default_threads` reads: our own thread pools follow it
    from threadpoolctl import threadpool_limits

    threadpool_limits(limits=n)
    try:
        import numba

        numba.set_num_threads(min(n, numba.config.NUMBA_NUM_THREADS))
    except ImportError:
        pass
    import torch

    torch.set_num_threads(n)
    return n


def run(commands: list[list[str]], logs: list[str | None] | None = None, gpu: bool = False,
        n_threads: int | None = None, label: str = "") -> int:
    """Run ``commands`` one after another under one slot, each to its log (or this process's output), with explicit
    thread counts in their environment; returns the last non-zero exit, or 0. A shell is never used (`bash` started
    from Windows Python is WSL's, which cannot see C: paths)."""
    n = str(n_threads or default_threads())
    env = dict(os.environ, PYTHONUTF8="1", PEGASUS_SLOT_HELD="1", PEGASUS_THREADS=n)
    for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMBA_NUM_THREADS"):
        env.setdefault(var, n)
    logs = logs or [None] * len(commands)
    worst = 0
    with slot(label or " ; ".join(" ".join(c) for c in commands)[:80], gpu=gpu):
        for k, (cmd, log) in enumerate(zip(commands, logs, strict=True)):
            cmd = [sys.executable, "-u", *cmd[1:]] if cmd[0] in ("python", "py") else cmd
            print(f"{time.strftime('%H:%M')} START {' '.join(cmd)[:120]}", flush=True)
            emit("item", item=f"command {k + 1}", dataset="", event=" ".join(cmd)[:200], status="start")
            t = time.time()
            if log:
                Path(log).parent.mkdir(parents=True, exist_ok=True)
                with open(log, "w", encoding="utf-8") as fh:
                    code = subprocess.call(cmd, stdout=fh, stderr=subprocess.STDOUT, env=env)
            else:
                code = subprocess.call(cmd, env=env)
            print(f"{time.strftime('%H:%M')} EXIT {code} {log or ''}", flush=True)
            emit("item", item=f"command {k + 1}", dataset="", event=" ".join(cmd)[:200],
                 status="failed" if code else "end", seconds=round(time.time() - t, 1),
                 **({"error": f"exit {code}"} if code else {}))
            worst = code or worst
    return worst


# ---------------------------------------------------------------------------------------------------------- runs


workspace = config.workspace


def runs_dir() -> Path:
    path = workspace() / "runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, obj: dict) -> None:
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, path)


def _now() -> str:
    """Local time with its offset (``2026-10-15T21:00:00-03:00``): a reader elsewhere parses it unambiguously."""
    from datetime import datetime

    return datetime.now().astimezone().isoformat(timespec="seconds")


def _meta_path(run_id: str) -> Path:
    path = runs_dir() / run_id / "meta.json"
    if not path.exists():
        raise LookupError(f"no run {run_id} in {runs_dir()}")
    return path


def _update(run_id: str, **fields) -> dict:
    path = _meta_path(run_id)
    meta = json.loads(path.read_text(encoding="utf-8"))
    meta.update(fields)
    _write_json(path, meta)
    return meta


def _alive(meta: dict) -> bool:
    import psutil

    try:
        return meta.get("pid") is not None and abs(psutil.Process(meta["pid"]).create_time() - meta["pid_created"]) < 1
    except (psutil.Error, KeyError, TypeError):
        return False


def get(run_id: str) -> dict:
    """A run's record; a run whose process is gone without saying how it ended is ``lost`` (killed from outside, the
    machine restarted), recorded so."""
    meta = json.loads(_meta_path(run_id).read_text(encoding="utf-8"))
    if meta["state"] in ("queued", "running") and meta.get("pid") and not _alive(meta):
        meta = _update(run_id, state="lost", ended=meta.get("ended") or _now(),
                       error=meta.get("error") or "its process ended without recording how")
    return meta


def runs(limit: int | None = None, study: str | None = None) -> list[dict]:
    """The register, newest first; ``study`` keeps that study's runs."""
    out = []
    for d in sorted(runs_dir().iterdir(), key=lambda p: p.name, reverse=True):
        if not (d / "meta.json").exists():
            continue
        try:
            meta = get(d.name)
        except (OSError, ValueError, LookupError):
            continue
        if study is None or meta.get("study") == study:
            out.append(meta)
        if limit and len(out) >= limit:
            break
    return out


def active() -> list[dict]:
    return [r for r in runs() if r["state"] in ("queued", "running")]


def submit(kind: str, label: str, *, declaration: str | None = None, commands: list[list[str]] | None = None,
           options: dict | None = None, need_gb: float | None = None, study: str | None = None,
           folder: str | None = None) -> dict:
    """Register a run and start it as a detached process (`execute`), which waits for its slot and memory, runs, and
    records how it ended. ``kind`` "study" runs a declaration (``options``: ``products_only``); "commands" runs
    ``commands`` one after another (`run`). Returns the run's record, state ``queued``."""
    if kind not in _TARGETS:
        raise ValueError(f"unknown run kind {kind!r}: one of {sorted(_TARGETS)}")
    if kind in ("study", "scope"):
        if not declaration or not Path(declaration).exists():
            raise FileNotFoundError(f"no declaration {declaration}")
        declaration = str(Path(declaration).resolve())
        same = [r for r in active() if r.get("declaration") == declaration]
        if same:
            # two runs of one declaration write one folder: the second would delete the first's products as it starts
            raise RuntimeError(f"{declaration} is already being run ({same[0]['id']}, {same[0]['state']})")
    slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in (study or label))[:48]
    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{slug}"
    d = runs_dir() / run_id
    k = 1
    while d.exists():
        k += 1
        d = runs_dir() / f"{run_id}-{k}"
    run_id = d.name
    (d / "events").mkdir(parents=True)
    meta = {"id": run_id, "kind": kind, "label": label, "study": study, "declaration": declaration, "folder": folder,
            "commands": commands, "options": options or {}, "state": "queued", "created": _now(), "started": None,
            "ended": None, "exit": None, "error": None, "pid": None, "pid_created": None, "need_gb": need_gb,
            "peak_gb": None, "code_version": config.code_version(), "result": None}
    _write_json(d / "meta.json", meta)
    flags = 0
    if sys.platform == "win32":
        # its own process group, so a console's Ctrl+C does not reach it; a hidden console its lanes inherit (a
        # detached process's spawned children each opened a window); out of the starter's job object where it may
        # leave it, so closing the window or the shell that started it does not end it
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    env = dict(os.environ, PYTHONUTF8="1", PYTHONUNBUFFERED="1", PEGASUS_WORKSPACE=str(workspace()))
    env.pop("PEGASUS_SLOT_HELD", None)
    cmd = [sys.executable, "-u", "-m", "pegasus_core.jobs", "execute", run_id]
    with open(d / "log.txt", "ab") as log:
        try:
            proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    cwd=workspace(), env=env, close_fds=True,
                                    creationflags=flags | getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0))
        except OSError:
            proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    cwd=workspace(), env=env, close_fds=True, creationflags=flags)
    import psutil

    try:
        created = psutil.Process(proc.pid).create_time()
    except psutil.Error:
        created = None
    return _update(run_id, pid=proc.pid, pid_created=created)


def stop(run_id: str) -> dict:
    """End a run and every process it started (its lanes), and record it ``stopped``."""
    import psutil

    meta = get(run_id)
    if meta["state"] not in ("queued", "running"):
        return meta
    if _alive(meta):
        root = psutil.Process(meta["pid"])
        procs = [*root.children(recursive=True), root]
        for p in procs:
            with suppress(psutil.Error):
                p.terminate()
        _gone, left = psutil.wait_procs(procs, timeout=10)
        for p in left:
            with suppress(psutil.Error):
                p.kill()
    _event_line(runs_dir() / run_id, {"kind": "run", "state": "stopped"})
    return _update(run_id, state="stopped", ended=_now(), error="stopped")


def wait(run_id: str, follow=None, poll: float = 2.0) -> dict:
    """Wait for a run to end, passing each new line of its log to ``follow``."""
    path = runs_dir() / run_id / "log.txt"
    pos = 0
    while True:
        meta = get(run_id)
        if follow and path.exists():
            with open(path, encoding="utf-8", errors="replace") as fh:
                fh.seek(pos)
                for line in fh:
                    follow(line.rstrip("\n"))
                pos = fh.tell()
        if meta["state"] not in ("queued", "running"):
            return meta
        time.sleep(poll)


def log_tail(run_id: str, lines: int = 400) -> str:
    path = runs_dir() / run_id / "log.txt"
    if not path.exists():
        return ""
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        block = min(size, max(lines * 200, 65536))
        fh.seek(size - block)
        text = fh.read().decode("utf-8", errors="replace")
    return "\n".join(text.splitlines()[-lines:])


def machine() -> dict:
    """The machine as the runs see it: memory, CPU, the disks of the workspace, the store and the data root, the heavy
    slots and their holders."""
    import psutil

    vm = psutil.virtual_memory()
    disks, seen = [], set()
    for p in (workspace(), config.home(), Path(config.data_root())):
        anchor = Path(p).anchor
        if anchor in seen or not Path(p).exists():
            continue
        seen.add(anchor)
        du = psutil.disk_usage(str(p))
        disks.append({"path": anchor, "free_gb": round(du.free / _GIB, 1), "total_gb": round(du.total / _GIB, 1)})
    return {"ram_total_gb": round(vm.total / _GIB, 1), "ram_available_gb": round(vm.available / _GIB, 1),
            "cpu_percent": psutil.cpu_percent(interval=0.2), "slots": HEAVY_SLOTS, "disks": disks,
            "holders": holders()}


# -------------------------------------------------------------------------------------------------------- events


def _event_line(run_dir: Path, event: dict) -> None:
    path = run_dir / "events" / f"{os.getpid()}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"t": round(time.time(), 3), "pid": os.getpid(), **event}, default=str) + "\n")


@config.keyless
def emit(kind: str, **fields) -> None:
    """Record what this process did as a typed event of the run it belongs to (``PEGASUS_RUN_DIR``, inherited by its
    lanes); nothing outside a run. Each process writes its own file, so lanes never interleave a line."""
    d = os.environ.get("PEGASUS_RUN_DIR")
    if not d:
        return
    with suppress(OSError):
        _event_line(Path(d), {"kind": kind, **fields})


def events(run_id: str, since: float = 0.0) -> list[dict]:
    """A run's events from ``since`` on (unix seconds, inclusive), from all its processes, in time order."""
    out = []
    for f in (runs_dir() / run_id / "events").glob("*.jsonl"):
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue                            # a line being written
                if e.get("t", 0) >= since:              # inclusive: a reader drops what it has seen
                    out.append(e)
    return sorted(out, key=lambda e: e["t"])


# ------------------------------------------------------------------------------------------------------ executor


def _sample(run_id: str, stop_flag: threading.Event) -> None:
    """The run's process tree's memory every 5 s: its peak into the record (what its next run is admitted with), a
    ``resources`` event every 30 s."""
    import psutil

    peak, said, wrote = 0.0, 0.0, 0.0
    psutil.cpu_percent(interval=None)
    while not stop_flag.wait(5):
        rss = _tree_rss_gb(os.getpid())
        peak = max(peak, rss)
        now = time.time()
        if now - said >= 30:
            emit("resources", rss_gb=round(rss, 2), available_gb=round(psutil.virtual_memory().available / _GIB, 2),
                 cpu_percent=psutil.cpu_percent(interval=None))
            said = now
        if now - wrote >= 30:
            with suppress(OSError, ValueError, LookupError):
                _update(run_id, peak_gb=round(peak, 2))
            wrote = now
    with suppress(OSError, ValueError, LookupError):
        _update(run_id, peak_gb=round(max(peak, _tree_rss_gb(os.getpid())), 2))


def _study_target(meta: dict) -> dict:
    from . import study

    decl = study.load(meta["declaration"])
    need = meta.get("need_gb") or study.need_gb(decl)
    _update(meta["id"], need_gb=round(need, 2), folder=str(study.folder_of(decl)))
    with slot(f"study {decl.study}", need_gb=need):
        out = study.run(decl, log=lambda line: print(f"[{time.strftime('%H:%M:%S')}] {line}", flush=True),
                        products_only=bool(meta["options"].get("products_only")))
    result = {"folder": str(out)}
    try:
        parts = study.body(out)
        missing = [{"part": r["part"], "evidence": r["evidence"]} for r in parts if r["status"] != "met"]
        result.update(met=len(parts) - len(missing), total=len(parts))
        emit("body", met=len(parts) - len(missing), total=len(parts), missing=missing)
        print(f"{len(parts) - len(missing)} of {len(parts)} parts of the analytic body met", flush=True)
    except Exception as exc:  # noqa: BLE001 - the folder stands; its check is said, never a failed run
        result["body_error"] = f"{type(exc).__name__}: {exc}"
    return result


class RunFailed(RuntimeError):
    """A run whose work ended in a stated failure (a command's exit code): recorded without a traceback."""

    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


def _commands_target(meta: dict) -> dict:
    opts = meta["options"]
    code = run(meta["commands"], logs=opts.get("logs"), gpu=bool(opts.get("gpu")), n_threads=opts.get("threads"),
               label=meta["label"])
    if code:
        raise RunFailed(f"a command exited with {code}", code)
    return {"exit": 0}


def _scope_target(meta: dict) -> dict:
    """A declaration priced (`workspace.scope`): light, so no heavy slot; its scope written to the folder."""
    from . import workspace

    _update(meta["id"], state="running", started=_now())
    emit("run", state="running")
    emit("phase", phase="scope", status="start")
    t = time.time()
    scope = workspace.scope(meta["declaration"])
    emit("phase", phase="scope", status="end", seconds=round(time.time() - t, 1),
         estimate_s=round((scope.get("estimated_minutes") or 0) * 60, 1))
    print(f"{len(scope['read'])} read, {len(scope['deferred'])} deferred, {len(scope['not_read'])} not read; "
          f"estimated {scope['estimated_minutes']} min; written to {scope['written']}", flush=True)
    return {"estimated_minutes": scope["estimated_minutes"], "read": len(scope["read"]),
            "deferred": len(scope["deferred"]), "not_read": len(scope["not_read"]), "written": scope["written"],
            "nothing_read": scope["nothing_read"]}


_TARGETS = {"study": _study_target, "commands": _commands_target, "scope": _scope_target}


def execute(run_id: str) -> int:
    """The detached process of a run (`submit`): runs its target under its slot and records how it ended."""
    d = runs_dir() / run_id
    os.environ["PEGASUS_RUN_DIR"] = str(d)
    os.environ["PEGASUS_RUN_ID"] = run_id
    os.environ["PEGASUS_RUN_PID"] = str(os.getpid())
    import psutil

    meta = _update(run_id, pid=os.getpid(), pid_created=psutil.Process().create_time())
    print(f"[{_now()}] run {run_id}: {meta['label']} (code {meta['code_version']})", flush=True)
    emit("run", state="queued")
    flag = threading.Event()
    sampler = threading.Thread(target=_sample, args=(run_id, flag), daemon=True)
    sampler.start()
    try:
        result = _TARGETS[meta["kind"]](meta)
    except BaseException as exc:  # noqa: BLE001 - every ending is recorded, then returned as the exit code
        code = exc.code if isinstance(exc, (SystemExit, RunFailed)) and isinstance(exc.code, int) else 1
        flag.set()
        sampler.join(timeout=10)
        error = str(exc) if isinstance(exc, RunFailed) else f"{type(exc).__name__}: {exc}"
        if not isinstance(exc, RunFailed):
            print(traceback.format_exc(), flush=True)
        emit("run", state="failed", error=error)
        _update(run_id, state="failed", ended=_now(), exit=code, error=error)
        return code
    flag.set()
    sampler.join(timeout=10)
    emit("run", state="done")
    _update(run_id, state="done", ended=_now(), exit=0, result=result)
    return 0


_MAP_POOL = None


def parallel_map(fn, items) -> list:
    """``[fn(x) for x in items]`` over this process's threads, in order: for independent evaluations whose work is in
    numpy and scipy (which release the GIL), such as the per-group fits of a dispersion or the grid of a search. The
    results equal the sequential ones."""
    from concurrent.futures import ThreadPoolExecutor

    global _MAP_POOL
    items = list(items)
    if len(items) < 2 or default_threads() < 2:
        return [fn(x) for x in items]
    if _MAP_POOL is None:
        _MAP_POOL = ThreadPoolExecutor(default_threads())
    return list(_MAP_POOL.map(fn, items))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "execute":
        raise SystemExit(execute(sys.argv[2]))
    raise SystemExit("usage: python -m pegasus_core.jobs execute RUN_ID")
