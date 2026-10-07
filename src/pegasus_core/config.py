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
from functools import cache, lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def home() -> Path:
    path = Path(os.environ.get("PEGASUS_HOME", REPO / "pegasus_home"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_root() -> str:
    return os.environ.get("PEGASUS_DATA_ROOT", "C:/Users/Galaxy/pegasus_core_data")


def population_root() -> str:
    return os.environ.get("PEGASUS_POPULATION_ROOT",
                          "C:/Users/Galaxy/LEVI/projects/pegasus_data/pegasus_data_home")


def population_source() -> str:
    """The exposure the gateway reads unless a call names one: ``popsvs`` (IBGE's projection as the MoH
    distributes it) ``account-2`` (pegasus_data's modelled population account, with intervals; ADR-0010) or ``account-3`` / ``account-4``
    (its complete tensor, single ages; ADR-0010 amended)."""
    return os.environ.get("PEGASUS_POPULATION", "popsvs")


def population_pinned() -> str | None:
    """The source ``PEGASUS_POPULATION`` names, None when it is unset (then ``monolith.default_population`` chooses
    per field: ``hybrid`` where the events are the newborn's, ``popsvs`` otherwise; ADR-0010 amended)."""
    return os.environ.get("PEGASUS_POPULATION") or None


@lru_cache(maxsize=1)
def code_version() -> str:
    """This repository's commit, plus ``+dirty`` when the tree has changes: recorded in manifests and the ledger,
    never an artefact's key (`code_key`)."""
    return _git_version(REPO)


def code_key(*entries: object) -> str:
    """The version of the code an artefact is a function of (ARCHITECTURE §11.3): a hash of the source of ``entries``
    (functions, classes, methods, or ``"module:qualname"``) and of everything in this package they reach, read from
    the syntax tree without comments or docstrings. A name reaches its definition (function, class, module constant,
    through imports, local ones included); ``module.name`` reaches that module's definition; ``x.name`` on any other
    object reaches every method or class attribute of that name in the package (sound without types: it may include
    more than is called, never less). A class reached by name brings its body without its ordinary methods. So an edit
    re-keys exactly the artefacts whose code it can change, where the repository's commit re-keyed every artefact on
    every commit."""
    return _code_key(tuple(e if isinstance(e, str) else f"{e.__module__}:{e.__qualname__}" for e in entries))


@cache
def _code_key(entries: tuple[str, ...]) -> str:
    idx = _code_index()
    h = hashlib.sha256()
    for item in sorted(code_closure(entries)):
        h.update(f"{item[0]}:{item[1]}\n".encode())
        h.update(idx.dumps[item].encode())
    return h.hexdigest()[:16]


@cache
def code_closure(entries: tuple[str, ...]) -> frozenset[tuple[str, str]]:
    """The definitions `code_key` hashes for ``entries`` ("module:qualname" each)."""
    import ast

    idx = _code_index()
    seen: set[tuple[str, str]] = set()
    todo = [tuple(e.split(":", 1)) for e in entries]
    while todo:
        item = todo.pop()
        if item in seen:
            continue
        node = idx.nodes.get(item)
        if node is None:
            raise LookupError(f"code_key: no definition of {item[0]}:{item[1]} in the package")
        seen.add(item)
        module = item[0]
        local = dict(idx.aliases[module])
        for n in ast.walk(node):
            if isinstance(n, ast.ImportFrom):
                local.update(_import_aliases(n, module, idx.modules))
        for n in ast.walk(node):
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
                    todo.extend(idx.members.get(part, ()))
    return frozenset(seen)


_EXTERNAL = object()


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
        stmts = list(tree.body)
        while stmts:
            s = stmts.pop(0)
            if isinstance(s, (ast.If, ast.Try)):
                stmts[:0] = s.body + getattr(s, "orelse", []) + [x for h in getattr(s, "handlers", []) for x in h.body]
            elif isinstance(s, (ast.Import, ast.ImportFrom)):
                aliases[module].update(_import_aliases(s, module, modules))
            elif isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)):
                nodes[(module, s.name)] = s
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

    return SimpleNamespace(nodes=nodes, dumps=dumps, aliases=aliases, members=members, modules=modules,
                           resolve=resolve, family=family)


@lru_cache(maxsize=1)
def data_version() -> str:
    """The data version in every artefact key: pegasus_data's package version, until it
    exposes publication-level data versions (ARCHITECTURE §13). Not its commit: the
    repository is developed concurrently, and a commit key would invalidate every
    cached aggregate on each of its edits. The commit is recorded in each manifest."""
    from . import gateway

    return gateway.package_version()


@cache
def resource_version(file: str) -> str:
    """The sha256 (12 characters) of one of pegasus_data's shipped resources, from its manifest:
    the key of anything derived from that resource (code structures, graphs), so a rebuilt
    resource is a new key even when the package version is unchanged."""
    import json

    from . import gateway

    manifest = gateway.package_dir() / "resources" / "manifest.json"
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    entries = entries.get("resources", entries)
    entry = next(v for v in entries.values() if isinstance(v, dict) and v.get("file") == file)
    return str(entry["sha256"])[:12]


@lru_cache(maxsize=1)
def data_code_version() -> str:
    """pegasus_data's version and commit, recorded in manifests and the ledger."""
    from . import gateway

    return f"{gateway.package_version()}@{_git_version(gateway.package_dir().parents[1])}"


def _git_version(path: Path) -> str:
    try:
        head = subprocess.run(["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(path), "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True, timeout=10).stdout.strip()
        return f"{head}{'+dirty' if dirty else ''}" or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def seed(*parts: object) -> int:
    """A deterministic 64-bit seed from (object, cell, purpose) (ARCHITECTURE §11.4)."""
    digest = hashlib.blake2b("|".join(map(str, parts)).encode(), digest_size=8).digest()
    return int.from_bytes(digest, "little") & 0x7FFF_FFFF_FFFF_FFFF


def supply_exponents() -> dict[str, float] | None:
    """``PEGASUS_SUPPLY=volume:1,utilisation:0.5``: the facility-supply exponents given instead of chosen by likelihood
    (`facility.fit_supply`); unset: chosen."""
    raw = os.environ.get("PEGASUS_SUPPLY")
    return None if not raw else {k: float(v) for k, v in (kv.split(":") for kv in raw.split(","))}
