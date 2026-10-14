"""Homes, versions and seeds (ARCHITECTURE §11.1, §11.3).

PegaSUS writes only under ``PEGASUS_HOME``. pegasus_data is reached through its
API with two roots: ``PEGASUS_DATA_ROOT``, where PegaSUS's own queries fetch
and build (never pegasus_data's maintainer home), and ``PEGASUS_POPULATION_ROOT``,
read for population series already built there.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import time
from functools import cache, lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def keyless(fn):
    """A definition no stored result depends on (storage, paths, versions, devices, the keys' own machinery): `code_key`
    neither hashes nor follows it, so mending the plumbing re-keys nothing. Declared, never inferred; a module whose
    every definition is so says ``__keyless__ = True`` (store)."""
    return fn


#: the years of the production fits and readings (the dependency map reads their calibration; a declared column whose
#: years end before them is read by none)
FIT_YEARS = list(range(2010, 2024))

@keyless
def home() -> Path:
    path = Path(os.environ.get("PEGASUS_HOME", REPO / "pegasus_home"))
    path.mkdir(parents=True, exist_ok=True)
    return path


@keyless
def data_root() -> str:
    return os.environ.get("PEGASUS_DATA_ROOT", "C:/Users/Galaxy/pegasus_core_data")


# a pegasus_data call that names no root addresses PegaSUS's data root: unset, pegasus_data creates a home beside the
# working directory, and two did (pegasus_project/pegasus_data_home fetched 167 files again, 2026-10-05..09)
os.environ.setdefault("PEGASUS_DATA_HOME", data_root())


@keyless
def population_root() -> str:
    return os.environ.get("PEGASUS_POPULATION_ROOT",
                          "C:/Users/Galaxy/LEVI/projects/pegasus_data/pegasus_data_home")


def study_area() -> frozenset[int] | None:
    """The study's area (a declaration's ``where``, set for its process and lanes as ``PEGASUS_AREA``): two-digit state
    codes and six-digit municipality codes; None for Brazil. A block's places are the population's places inside it,
    so every fit, null world and map is the area's, at a fraction of Brazil's cost (Rio Grande do Sul: 497 of 5,570)."""
    raw = os.environ.get("PEGASUS_AREA", "").strip()
    if not raw or raw.upper() == "BR":
        return None
    return frozenset(int(x) for x in raw.replace(";", ",").split(",") if x.strip())


def in_area(u, area: frozenset[int] | None = None):
    """Which municipality codes (six digits) lie in the study's area (all of them for Brazil)."""
    import numpy as np

    area = study_area() if area is None else area
    u = np.asarray(u, dtype=np.int64)
    if area is None:
        return np.ones(u.shape, dtype=bool)
    states = np.array([a for a in area if a < 100], dtype=np.int64)
    places = np.array([a for a in area if a >= 100], dtype=np.int64)
    return np.isin(u // 10000, states) | np.isin(u, places)


def area_suffix() -> str:
    """The suffix of the register's and the ledger's homes for the study's area ("" for Brazil): an area's leads and
    tests are its own, never read by Brazil's studies as theirs, nor theirs by it."""
    area = study_area()
    return "" if area is None else "_area_" + "-".join(str(a) for a in sorted(area))


def replicates(n: int, floor: int = 19) -> int:
    """A method's own number of replicate null worlds, scaled by the study's ``nulls`` (`PEGASUS_NULLS`: 0.25 quick, 1
    standard, 4 precise): the precision of every Monte Carlo p-value, the user's to trade against time; never below
    ``floor`` (a p-value needs some worlds to exist)."""
    try:
        scale = float(os.environ.get("PEGASUS_NULLS", "1") or 1)
    except ValueError:
        scale = 1.0
    return max(floor, int(round(n * scale)))


def population_source() -> str:
    """The exposure the gateway reads unless a call names one: ``popsvs`` (IBGE's projection as the MoH
    distributes it) ``account-2`` (pegasus_data's modelled population account, with intervals; ADR-0010) or ``account-3`` / ``account-4``
    (its complete tensor, single ages; ADR-0010 amended)."""
    return os.environ.get("PEGASUS_POPULATION", "popsvs")


def population_pinned() -> str | None:
    """The source ``PEGASUS_POPULATION`` names, None when it is unset (then ``monolith.default_population`` chooses
    per field: ``hybrid`` where the events are the newborn's, ``popsvs`` otherwise; ADR-0010 amended)."""
    return os.environ.get("PEGASUS_POPULATION") or None


@keyless
@lru_cache(maxsize=1)
def code_version() -> str:
    """This repository's commit, plus ``+dirty`` when the tree has changes: recorded in manifests and the ledger,
    never an artefact's key (`code_key`)."""
    return _git_version(REPO)


@keyless
def code_key(*entries: object) -> str:
    """The version of the code an artefact is a function of (ARCHITECTURE §11.3): a hash of the source of ``entries``
    (functions, classes, methods, or ``"module:qualname"``) and of everything in this package they reach, read from
    the syntax tree without comments or docstrings. A name reaches its definition (function, class, module constant,
    through imports, local ones included); ``module.name`` reaches that module's definition; ``x.name`` on any other
    object reaches every method of that name in the package, unless the name is ambiguous, one the builtin types or the
    array libraries also carry (``add``, ``get``, ``lower``, ``rank``): then only the method of the classes the closure
    reaches (by name, a base or a subclass). ``set.add`` had reached the lead register's ``add``, and a counting
    function's key held the solver, the register and the ledger, 574 definitions (the review of the gateway,
    2026-10-14); restricting every name, a cold study's audit found `questions.ask` running 231 functions its key lacked.
    A class reached by name brings its body without its ordinary methods; a `keyless` definition is neither hashed nor
    followed. Checked by running: `key_audit_start` records any function a keyed computation runs that its key lacks."""
    return _code_key(tuple(e if isinstance(e, str) else f"{e.__module__}:{e.__qualname__}" for e in entries))


@keyless
@cache
def _code_key(entries: tuple[str, ...]) -> str:
    known = _known_keys()
    name = "|".join(entries)
    if name in known["keys"]:
        return known["keys"][name]
    if _sources_state() != _STATE_AT_IMPORT:
        # the sources changed after this process imported them: a key computed now would be the new code's, stored for
        # artefacts this process makes with the old (a lane started before an edit), and served later as current
        raise StaleCode(f"the package's sources changed after this process started ({_STATE_AT_IMPORT} -> "
                        f"{_sources_state()}): it runs code that no longer exists; restart it on the current code")
    key = _computed_key(entries)
    known["keys"][name] = key
    _save_keys(known)
    return key


class StaleCode(RuntimeError):
    """A process asked for the key of code it no longer runs (the sources were edited after it started)."""


@keyless
def _sources_state() -> str:
    """The package's sources as they stand (each file's path, size and modification time): what a code key is a
    function of, read in milliseconds where parsing and dumping every syntax tree took 42 s of a one-state scope's
    329 (infarto_alagoas, 2026-10-13)."""
    root = Path(__file__).resolve().parent
    h = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        st = path.stat()
        h.update(f"{path.relative_to(root).as_posix()}:{st.st_size}:{st.st_mtime_ns}\n".encode())
    return h.hexdigest()[:16]


#: the sources' state when this process imported the package: its keys are of this code, whatever is edited later
_STATE_AT_IMPORT = _sources_state()


@keyless
@cache
def _known_keys() -> dict:
    import json

    path = home() / "code_keys" / f"{_STATE_AT_IMPORT}.json"
    try:
        keys = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        keys = {}
    return {"path": path, "keys": keys}


@keyless
def _save_keys(known: dict) -> None:
    """The keys of this state of the sources, written whole and atomically (lanes compute them concurrently: a lost
    write is a key computed again, never a wrong one). Another state's file is removed only when a week old: a lane of
    an older state had deleted the live state's file, and every process after it recomputed its keys (2026-10-14)."""
    import contextlib
    import json

    path = known["path"]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError, ValueError):
            known["keys"] = {**json.loads(path.read_text(encoding="utf-8")), **known["keys"]}
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(known["keys"], sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)
        week = time.time() - 7 * 86400
        for other in path.parent.glob("*.json"):
            if other != path and other.stat().st_mtime < week:
                other.unlink(missing_ok=True)
    except OSError:
        pass


@keyless
def _computed_key(entries: tuple[str, ...]) -> str:
    idx = _code_index()
    h = hashlib.sha256()
    for item in sorted(code_closure(entries)):
        h.update(f"{item[0]}:{item[1]}\n".encode())
        h.update(idx.dumps[item].encode())
    return h.hexdigest()[:16]


@keyless
@cache
def code_closure(entries: tuple[str, ...]) -> frozenset[tuple[str, str]]:
    """The definitions `code_key` hashes for ``entries`` ("module:qualname" each)."""
    import ast

    idx = _code_index()
    seen: set[tuple[str, str]] = set()
    todo = [tuple(e.split(":", 1)) for e in entries]
    pending: set[str] = set()                     # attribute names met on objects of no known class
    classes: set[tuple[str, str]] = set()         # the classes reached, with their bases and subclasses

    def reach(c: tuple[str, str]) -> None:
        for k in idx.family(c):
            if k not in classes:
                classes.add(k)
                todo.extend((k[0], f"{k[1]}.{a}") for a in pending if (k[0], f"{k[1]}.{a}") in idx.nodes)

    while todo:
        item = todo.pop()
        if item in seen or item in idx.keyless:
            continue
        node = idx.nodes.get(item)
        if node is None:
            raise LookupError(f"code_key: no definition of {item[0]}:{item[1]} in the package")
        seen.add(item)
        if isinstance(node, ast.ClassDef):
            reach(item)
        elif "." in item[1] and (item[0], item[1].split(".")[0]) in idx.nodes:
            reach((item[0], item[1].split(".")[0]))      # a method reached by name: its class is
        module = item[0]
        local = dict(idx.aliases[module])
        for n in ast.walk(node):
            if isinstance(n, ast.ImportFrom):
                local.update(_import_aliases(n, module, idx.modules))
        for n in ast.walk(node):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("getattr", "hasattr")                     and len(n.args) >= 2 and isinstance(n.args[1], ast.Constant) and isinstance(n.args[1].value, str):
                part = n.args[1].value              # an attribute named by a literal: x.part in another spelling
                if part not in idx.ambiguous:
                    todo.extend(idx.members.get(part, ()))
                elif part not in pending:
                    pending.add(part)
                    todo.extend(k for k in idx.members.get(part, ()) if (k[0], k[1].split(".")[0]) in classes)
            if isinstance(n, ast.Name):
                todo.extend(idx.resolve(module, n.id, local))
            elif isinstance(n, ast.Attribute):
                chain, root = [], n
                while isinstance(root, ast.Attribute):
                    chain.append(root.attr)
                    root = root.value
                chain.reverse()
                target = local.get(root.id) if isinstance(root, ast.Name) else None
                if isinstance(target, str):                        # a package module: module.name[.name]
                    for i, part in enumerate(chain):
                        if f"{target}.{part}" in idx.modules:
                            target = f"{target}.{part}"
                            continue
                        todo.extend(idx.resolve(target, part, idx.aliases[target]))
                        chain = chain[i + 1:]
                        break
                    else:
                        chain = []
                elif target is _EXTERNAL:                          # numpy, pyarrow, ...: not this package's code
                    chain = []
                elif isinstance(root, ast.Name) and root.id in ("self", "cls")                         and isinstance(idx.nodes.get((module, item[1].split(".")[0])), ast.ClassDef):
                    for c in idx.family((module, item[1].split(".")[0])):    # the class, its bases, its subclasses
                        if (c[0], f"{c[1]}.{chain[0]}") in idx.nodes:
                            todo.append((c[0], f"{c[1]}.{chain[0]}"))
                    chain = chain[1:]
                for part in chain:
                    if part not in idx.ambiguous:
                        todo.extend(idx.members.get(part, ()))
                    elif part not in pending:
                        pending.add(part)
                        todo.extend(k for k in idx.members.get(part, ()) if (k[0], k[1].split(".")[0]) in classes)
    return frozenset(seen)


_EXTERNAL = object()


@keyless
def _import_aliases(n, module: str, modules: set[str]) -> dict[str, object]:
    """The names an ``import`` statement binds: a package module (its dotted name), a package definition
    ((module, name)), or `_EXTERNAL`."""
    import ast

    out: dict[str, object] = {}
    if isinstance(n, ast.Import):
        for a in n.names:
            out[(a.asname or a.name).split(".")[0]] = a.name if a.name in modules and a.asname else _EXTERNAL
        return out
    if n.level:
        package = module if module in _PACKAGES else module.rsplit(".", 1)[0]
        base = package.rsplit(".", n.level - 1)[0] if n.level > 1 else package
        base = f"{base}.{n.module}" if n.module else base
    else:
        base = n.module or ""
    for a in n.names:
        name = a.asname or a.name
        if f"{base}.{a.name}" in modules:
            out[name] = f"{base}.{a.name}"
        elif base in modules:
            out[name] = (base, a.name)
        else:
            out[name] = _EXTERNAL
    return out


_PACKAGES: set[str] = set()


@keyless
@cache
def _code_index():
    """Every definition of the package, by (module, qualname), with its syntax tree and its dump."""
    import ast
    from types import SimpleNamespace

    root = Path(__file__).resolve().parent
    files = {}
    for path in sorted(root.rglob("*.py")):
        parts = path.relative_to(root.parent).with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
            _PACKAGES.add(".".join(parts))
        files[".".join(parts)] = path
    modules = set(files)
    nodes, dumps, aliases, members = {}, {}, {}, {}
    keyless_: set[tuple[str, str]] = set()
    keyless_modules: set[str] = set()

    def declared_keyless(node) -> bool:
        return any((isinstance(d, ast.Name) and d.id == "keyless") or (isinstance(d, ast.Attribute) and d.attr == "keyless")
                   for d in getattr(node, "decorator_list", []))

    def strip(node):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                and isinstance(getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
            node.body = body[1:] or [ast.Pass()]
        return node

    for module, path in files.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                strip(n)
        aliases[module] = {}
        whole = any(isinstance(s, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__keyless__" for t in s.targets)
                    and isinstance(s.value, ast.Constant) and s.value.value is True for s in tree.body)
        if whole:
            keyless_modules.add(module)
        stmts = list(tree.body)
        while stmts:
            s = stmts.pop(0)
            if isinstance(s, (ast.If, ast.Try)):
                stmts[:0] = s.body + getattr(s, "orelse", []) + [x for h in getattr(s, "handlers", []) for x in h.body]
            elif isinstance(s, (ast.Import, ast.ImportFrom)):
                aliases[module].update(_import_aliases(s, module, modules))
            elif isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)):
                nodes[(module, s.name)] = s
                if whole or declared_keyless(s):
                    keyless_.add((module, s.name))
            elif isinstance(s, ast.ClassDef):
                head = ast.ClassDef(name=s.name, bases=s.bases, keywords=s.keywords, decorator_list=s.decorator_list,
                                    type_params=getattr(s, "type_params", []),
                                    body=[b for b in s.body if not isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef))
                                          or (b.name.startswith("__") and b.name.endswith("__"))] or [ast.Pass()])
                nodes[(module, s.name)] = head
                for b in s.body:                  # methods; a data attribute runs no code, and is in the class's body
                    if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)) and not b.name.startswith("__"):
                        key = (module, f"{s.name}.{b.name}")
                        nodes[key] = b
                        members.setdefault(b.name, []).append(key)
            elif isinstance(s, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = s.targets if isinstance(s, ast.Assign) else [s.target]
                for t in targets:
                    for x in ast.walk(t):
                        if isinstance(x, ast.Name):
                            prev = nodes.get((module, x.id))
                            nodes[(module, x.id)] = ast.Module(body=[prev, s] if prev is not None else [s],
                                                               type_ignores=[]) if prev is not None else s
    for key, node in nodes.items():
        dumps[key] = ast.dump(node)
    def resolve(module: str, name: str, local: dict) -> list[tuple[str, str]]:
        if name in local and isinstance(local[name], tuple):
            m, n = local[name]
            return resolve(m, n, aliases[m]) if (m, n) not in nodes and n in aliases.get(m, {}) else \
                ([(m, n)] if (m, n) in nodes else [])
        return [(module, name)] if (module, name) in nodes else []

    up = {}                                                    # a class's package bases
    for (module, name), node in nodes.items():
        if isinstance(node, ast.ClassDef):
            up[(module, name)] = [r for b in node.bases if isinstance(b, ast.Name)
                                  for r in resolve(module, b.id, aliases[module])]

    @cache
    def family(c: tuple[str, str]) -> tuple[tuple[str, str], ...]:
        out, todo = {c}, [c]
        while todo:
            x = todo.pop()
            for y in up.get(x, []) + [k for k, v in up.items() if x in v]:
                if y not in out:
                    out.add(y)
                    todo.append(y)
        return tuple(out)

    keyless_ |= {k for k in nodes if k[0] in keyless_modules}
    # the attribute names an object outside the package also answers to: a call of one may be on a dict, a set, a
    # string, an array or a table as well as on a package object
    ambiguous: set[str] = set()
    for t in (dict, list, set, frozenset, str, bytes, tuple, int, float):
        ambiguous |= set(dir(t))
    for module_, names_ in (("numpy", ("ndarray", "generic")), ("pyarrow", ("Table", "Array", "ChunkedArray", "Schema")),
                            ("pandas", ("DataFrame", "Series", "Index")), ("torch", ("Tensor",))):
        try:
            lib = __import__(module_)
        except ImportError:
            continue
        for n in names_:
            ambiguous |= set(dir(getattr(lib, n, None)))
    return SimpleNamespace(nodes=nodes, dumps=dumps, aliases=aliases, members=members, modules=modules,
                           resolve=resolve, family=family, keyless=frozenset(keyless_), ambiguous=frozenset(ambiguous))


@keyless
@lru_cache(maxsize=1)
def data_version() -> str:
    """The data version in every artefact key: pegasus_data's package version, until it
    exposes publication-level data versions (ARCHITECTURE §13). Not its commit: the
    repository is developed concurrently, and a commit key would invalidate every
    cached aggregate on each of its edits. The commit is recorded in each manifest."""
    import importlib.metadata

    return importlib.metadata.version("pegasus_data")


@keyless
@cache
def resource_version(file: str) -> str:
    """The sha256 (12 characters) of one of pegasus_data's shipped resources, from its manifest:
    the key of anything derived from that resource (code structures, graphs), so a rebuilt
    resource is a new key even when the package version is unchanged."""
    import json

    manifest = data_package_dir() / "resources" / "manifest.json"
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    entries = entries.get("resources", entries)
    entry = next(v for v in entries.values() if isinstance(v, dict) and v.get("file") == file)
    return str(entry["sha256"])[:12]


@keyless
@lru_cache(maxsize=1)
def data_code_version() -> str:
    """pegasus_data's version and commit, recorded in manifests and the ledger."""
    return f"{data_version()}@{_git_version(data_package_dir().parents[1])}"


@keyless
def data_package_dir() -> Path:
    """pegasus_data's package directory, found without importing it (only the gateway imports pegasus_data)."""
    import importlib.util

    return Path(importlib.util.find_spec("pegasus_data").origin).resolve().parent


@keyless
def _git_version(path: Path) -> str:
    try:
        head = subprocess.run(["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(path), "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True, timeout=10).stdout.strip()
        return f"{head}{'+dirty' if dirty else ''}" or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


#: a model's device memory per non-empty cell and its fixed part (measured: SIH A00-A09 2014-2023, 565,938 cells, 139 MB
#: peak on CUDA; TOXG, 19,094 cells, 68 MB), with a margin; the share of the card's free memory a model may take
DEVICE_BYTES_PER_CELL, DEVICE_FIXED_BYTES, DEVICE_SHARE = 400, 200 * 2**20, 0.6


@keyless
def device(cells: int | None = None) -> str:
    """Where a model computes: ``PEGASUS_DEVICE`` when set; else CUDA when the card is there and the block's estimated
    memory fits within `DEVICE_SHARE` of its free memory now, else the CPU. The same fit on CUDA is 1.4-1.75 times
    faster (SIH A00-A09 3.3 s against 4.6 s, TOXG 3.2 s against 5.6 s) with identical estimates (φ, P to 13 digits,
    2026-10-11); a block too large for the card's free memory stays on the CPU, never fails there."""
    forced = os.environ.get("PEGASUS_DEVICE")
    if forced:
        return forced
    import torch

    if not torch.cuda.is_available():
        return "cpu"
    free, _ = torch.cuda.mem_get_info()
    need = DEVICE_FIXED_BYTES + DEVICE_BYTES_PER_CELL * int(cells or 0)
    return "cuda" if need <= DEVICE_SHARE * free else "cpu"


@keyless
def array_device() -> str:
    """Where the array work outside a model's fit runs (graph kernels, scans, the relation map's factors):
    ``PEGASUS_DEVICE`` when set, else CUDA when there is a card. Fixed for the process, so tensors made apart stay on
    one device. Each module had chosen CUDA by itself: a study lane pinned to the CPU still computed its multiscale
    kernels on the card beside the lane that held it (2026-10-11)."""
    forced = os.environ.get("PEGASUS_DEVICE")
    if forced:
        return forced
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


@keyless
def cuda_failed(exc: BaseException) -> bool:
    """Whether ``exc`` is the card failing (out of its memory, or a kernel error). If so this process computes on the
    CPU from now on: ``PEGASUS_DEVICE`` is set, so `device` and `array_device` answer the CPU, and the graph spectra
    held on the card are dropped. A CUDA error leaves the process's context unusable: in the survey one out-of-memory
    error in SIM-DO chapter I's lane failed that lane's next item, and one in the products phase failed 30 of its
    later steps (2026-10-11)."""
    import torch

    oom = getattr(torch.cuda, "OutOfMemoryError", ())
    if not (isinstance(exc, oom) or (isinstance(exc, RuntimeError) and "CUDA" in str(exc))):
        return False
    os.environ["PEGASUS_DEVICE"] = "cpu"
    from . import multiscale

    multiscale._SPECTRA.clear()
    return True


@keyless
def on_cpu_if_cuda_fails(fn, *args, **kwargs):
    """``fn(*args, **kwargs)``; if the card fails under it (`cuda_failed`), said, and once more on the CPU."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        if not cuda_failed(exc):
            raise
        print(f"CUDA failed in {getattr(fn, '__qualname__', fn)} ({str(exc).splitlines()[0]}): on the CPU from now on",
              flush=True)
        return fn(*args, **kwargs)


def seed(*parts: object) -> int:
    """A deterministic 64-bit seed from (object, cell, purpose) (ARCHITECTURE §11.4). A part that is a key is read
    without its code keys (`identity`): the draws of a model's randomised PIT followed its key's code, so an edit of
    unrelated code drew new random numbers (2026-10-14)."""
    digest = hashlib.blake2b("|".join(str(identity(p)) if isinstance(p, dict) else str(p) for p in parts).encode(),
                             digest_size=8).digest()
    return int.from_bytes(digest, "little") & 0x7FFF_FFFF_FFFF_FFFF


def identity(key: dict) -> dict:
    """A stored artefact's key without its code keys (``code`` and every ``*_code``, at any depth): what the artefact is
    of (its data, field, tier, reader), not the version of the code that made it."""
    return {k: identity(v) if isinstance(v, dict) else v for k, v in key.items()
            if not (k == "code" or str(k).endswith("_code"))}


def supply_exponents() -> dict[str, float] | None:
    """``PEGASUS_SUPPLY=volume:1,utilisation:0.5``: the facility-supply exponents given instead of chosen by likelihood
    (`facility.fit_supply`); unset: chosen."""
    raw = os.environ.get("PEGASUS_SUPPLY")
    return None if not raw else {k: float(v) for k, v in (kv.split(":") for kv in raw.split(","))}


@keyless
def key_audit_start(directory: str | Path) -> None:
    """Record, for this process, every call of a package function made while a keyed function runs that its key's code
    closure lacks (`code_closure`): an edit to such a definition would change a stored result without changing its key.
    The keyed functions are the entries of every key recorded under ``code_keys`` (any source state); a nested function,
    a comprehension or a dunder method counts as its enclosing definition. Written to ``directory/<pid>.json`` at exit.
    Started at import when ``PEGASUS_KEY_AUDIT`` names a directory, so a study's lanes are audited too: run the tests or
    a study on a scratch home with it, and keys are checked sound by what actually ran (ARCHITECTURE §11.3)."""
    import atexit
    import contextlib
    import json
    import sys
    import threading
    from collections import Counter

    idx = _code_index()
    names: set[str] = set()
    for f in (home() / "code_keys").glob("*.json"):
        with contextlib.suppress(OSError, ValueError):
            names |= set(json.loads(f.read_text(encoding="utf-8")))
    closure_of: dict[tuple[str, str], set] = {}
    for name in names:
        entries = tuple(name.split("|"))
        try:
            cl = code_closure(entries)
        except LookupError:
            continue
        for e in entries:
            closure_of.setdefault(tuple(e.split(":", 1)), set()).update(cl)
    found: dict[str, Counter] = {}
    paths: dict[str, dict[str, list]] = {}
    calls: Counter = Counter()
    local = threading.local()
    package = __name__.rsplit(".", 1)[0]

    def item_of(frame) -> tuple[str, str] | None:
        module = frame.f_globals.get("__name__") or ""
        if not module.startswith(package):
            return None
        qn = frame.f_code.co_qualname
        if "<" in qn:
            qn = qn.split(".<", 1)[0]
            if not qn or qn.startswith("<"):
                return None
        if qn.rsplit(".", 1)[-1].startswith("__") and "." in qn:
            qn = qn.rsplit(".", 1)[0]                    # a dunder method is in its class's dump
        item = (module, qn)
        return item if item in idx.nodes else None

    def profile(frame, event, arg):
        stack = getattr(local, "stack", None)
        if stack is None:
            stack = local.stack = []
        if event == "call":
            item = item_of(frame)
            if item is None:
                return
            for entry, cl, top in stack:
                if item not in cl and item not in idx.keyless:
                    name = f"{item[0]}:{item[1]}"
                    seen_ = found.setdefault(f"{entry[0]}:{entry[1]}", Counter())
                    if name not in seen_:               # how it was reached: the package frames from the entry down
                        path, f_ = [], frame
                        while f_ is not None and f_ is not top:
                            it = item_of(f_)
                            if it is not None and (not path or path[-1] != f"{it[0]}:{it[1]}"):
                                path.append(f"{it[0]}:{it[1]}")
                            f_ = f_.f_back
                        paths.setdefault(f"{entry[0]}:{entry[1]}", {})[name] = path[::-1]
                    seen_[name] += 1
            if item in closure_of:
                calls[f"{item[0]}:{item[1]}"] += 1
                stack.append((item, closure_of[item], frame))
        elif event == "return" and stack and stack[-1][2] is frame:
            stack.pop()

    def write() -> None:
        out = Path(directory)
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{os.getpid()}.json").write_text(json.dumps(
            {"entries_run": dict(calls), "missing": {k: dict(v) for k, v in found.items()}, "paths": paths}, indent=1,
            sort_keys=True),
            encoding="utf-8")

    sys.setprofile(profile)
    threading.setprofile(profile)
    atexit.register(write)


if os.environ.get("PEGASUS_KEY_AUDIT"):
    key_audit_start(os.environ["PEGASUS_KEY_AUDIT"])
