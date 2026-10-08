"""Code health of the package (CLAUDE.md §7: replace, never build beside; dead code removed).

    PYTHONUTF8=1 $PY scripts/codehealth.py

1. **Import cycles** between the package's modules, counting the imports inside functions too (a function-level import
   hides a cycle from Python, not from the design): ARCHITECTURE §11.1's dependency direction is downward only.
2. **Unreferenced definitions**: top-level functions and classes of the package that no module, script or the CLI
   names, as a name or as a string (a lens is dispatched by its name; a typer command and an MCP tool count as used).
Exits 1 when a cycle exists; unreferenced definitions are listed for review.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "pegasus_core"


def modules() -> dict[str, Path]:
    out = {}
    for path in sorted(PKG.rglob("*.py")):
        parts = path.relative_to(PKG.parent).with_suffix("").parts
        out[".".join(parts[:-1] if parts[-1] == "__init__" else parts)] = path
    return out


def imports(name: str, path: Path, mods: set[str]) -> set[str]:
    """The package modules ``name`` imports anywhere in its body."""
    package = name if path.name == "__init__.py" else name.rsplit(".", 1)[0]
    out = set()
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(n, ast.ImportFrom):
            base = package if n.level else ""
            for _ in range(max(n.level - 1, 0)):
                base = base.rsplit(".", 1)[0]
            base = ".".join(x for x in (base, n.module or "") if x) if n.level else (n.module or "")
            for a in n.names:
                full = f"{base}.{a.name}"
                out.add(full if full in mods else base)
        elif isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
    return {m for m in out if m in mods and m != name}


def cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Strongly connected components of more than one module (Tarjan)."""
    index, low, stack, on, out, counter = {}, {}, [], set(), [], [0]

    def visit(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in graph[v]:
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                out.append(sorted(comp))

    sys.setrecursionlimit(10000)
    for v in graph:
        if v not in index:
            visit(v)
    return out


def unreferenced(mods: dict[str, Path]) -> list[str]:
    texts = {p: p.read_text(encoding="utf-8") for p in list(mods.values()) + sorted((ROOT / "scripts").glob("*.py"))}
    words: dict[str, int] = {}
    for text in texts.values():
        for w in set(ast.walk(ast.parse(text))):
            name = w.id if isinstance(w, ast.Name) else w.attr if isinstance(w, ast.Attribute) else                 w.value if isinstance(w, ast.Constant) and isinstance(w.value, str) and w.value.isidentifier() else None
            if name:
                words[name] = words.get(name, 0) + 1
    out = []
    for name, path in mods.items():
        tree = ast.parse(texts[path])
        for n in tree.body:
            if not isinstance(n, (ast.FunctionDef, ast.ClassDef)) or n.name.startswith("__"):
                continue
            exposed = any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr in ("command", "tool", "resource", "prompt")
                          for d in n.decorator_list)
            if not exposed and not words.get(n.name):
                out.append(f"{name}.{n.name}")
    return out


def main() -> int:
    mods = modules()
    graph = {m: imports(m, p, set(mods)) for m, p in mods.items()}
    found = cycles(graph)
    for c in found:
        print("CYCLE " + " <-> ".join(c))
    dead = unreferenced(mods)
    for d in dead:
        print(f"UNREFERENCED {d}")
    print(f"{len(mods)} modules, {len(found)} import cycles, {len(dead)} unreferenced definitions")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
