"""Are the documents internally consistent, and do they describe the code?

The `.md` files are this project's interface to people and agents who cannot
check a claim against the code, so a dangling reference is a false statement.
Checks, all mechanical:

    1  every ADR-NNNN referenced in a current document exists under docs/decisions/
    2  ADR numbers are unique and contiguous from 0001, and each is in DECISIONS.md
    3  every evaluation entry is in EVALUATION.md, and every docs/ link resolves
    4  every OQ-N referenced is a row of OPEN_QUESTIONS.md
    5  every script named in a current document exists
    6  every module under src/pegasus_core is named in ARCHITECTURE.md
    7  CLAUDE.md and AGENTS.md are byte-for-byte copies

`docs/history/` and `docs/discussion/` are frozen: not scanned.

    python scripts/check_docs.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = ROOT / "docs" / "decisions"
EVALUATION = ROOT / "docs" / "evaluation"
HANDOFFS = ROOT / "docs" / "handoffs"
PACKAGE = ROOT / "src" / "pegasus_core"

ADR_REF = re.compile(r"ADR-(\d{4})")
OQ_REF = re.compile(r"\bOQ-(\d{1,3})\b")
SCRIPT_REF = re.compile(r"scripts/([A-Za-z0-9_/]+\.py)")
LINK = re.compile(r"\]\((docs/[^)#\s]+\.md)\)")
ROW = re.compile(r"^\|\s*(\d{1,3})\s*\|", re.MULTILINE)


def current_documents() -> dict[str, str]:
    out = {p.name: p.read_text(encoding="utf-8") for p in sorted(ROOT.glob("*.md"))}
    for folder in (DECISIONS, EVALUATION, HANDOFFS):
        for p in sorted(folder.glob("*.md")):
            out[f"{folder.name}/{p.name}"] = p.read_text(encoding="utf-8")
    return out


def main() -> int:
    docs = current_documents()
    problems: list[str] = []
    adr_files = {int(m.group(1)): p.name for p in DECISIONS.glob("ADR-*.md")
                 if (m := re.match(r"ADR-(\d{4})-", p.name))}

    # 1
    for name, text in docs.items():
        for n in sorted({int(x) for x in ADR_REF.findall(text)}):
            if n not in adr_files and not name.startswith("handoffs/"):
                problems.append(f"{name} references ADR-{n:04d}, which does not exist")
    # 2
    numbers = sorted(adr_files)
    if numbers != list(range(1, len(numbers) + 1)):
        problems.append(f"ADR numbers are not contiguous from 0001: {numbers}")
    index = docs.get("DECISIONS.md", "")
    for fname in adr_files.values():
        if f"docs/decisions/{fname}" not in index:
            problems.append(f"{fname} is not in DECISIONS.md")
    # 3
    ev_index = docs.get("EVALUATION.md", "")
    for p in EVALUATION.glob("*.md"):
        if f"docs/evaluation/{p.name}" not in ev_index:
            problems.append(f"evaluation/{p.name} is not in EVALUATION.md")
    for name, text in docs.items():
        for link in LINK.findall(text):
            if not (ROOT / link).exists():
                problems.append(f"{name} links {link}, which does not exist")
    # 4
    open_rows = {int(x) for x in ROW.findall(docs.get("OPEN_QUESTIONS.md", ""))}
    for name, text in docs.items():
        for n in sorted({int(x) for x in OQ_REF.findall(text)}):
            if n not in open_rows:
                problems.append(f"{name} references OQ-{n}, which is not an open row")
    # 5
    for name, text in docs.items():
        for script in sorted(set(SCRIPT_REF.findall(text))):
            if not (ROOT / "scripts" / script).exists():
                problems.append(f"{name} names scripts/{script}, which does not exist")
    # 6
    arch = docs.get("ARCHITECTURE.md", "")
    for p in sorted(PACKAGE.rglob("*.py")):
        rel = p.relative_to(PACKAGE)
        if rel.name == "__init__.py" and rel.parent == Path("."):
            continue
        module = rel.parts[0].removesuffix(".py")
        if f"`{module}`" not in arch:
            problems.append(f"module {module} (src/pegasus_core/{rel.as_posix()}) is not named in ARCHITECTURE.md")
    # 7
    if (ROOT / "CLAUDE.md").read_bytes() != (ROOT / "AGENTS.md").read_bytes():
        problems.append("CLAUDE.md and AGENTS.md differ")

    if problems:
        print(f"{len(problems)} problems:")
        for p in problems:
            print("  -", p)
        return 1
    print("consistent: ADRs, evaluation index, open questions, scripts, modules, CLAUDE.md = AGENTS.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
