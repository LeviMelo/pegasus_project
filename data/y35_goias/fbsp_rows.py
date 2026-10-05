"""Rows of a PDF page by word position: prints every line whose first words contain 'Goiás' or 'Brasil' (y-clustered)."""
import sys, pymupdf
def rows(pdf, pages, keys=("Goiás", "Brasil")):
    d = pymupdf.open(pdf)
    for p in pages:
        w = d[p].get_text("words")
        lines = {}
        for x0, y0, x1, y1, t, *_ in w:
            lines.setdefault(round((y0 + y1) / 2 / 2), []).append((x0, t))
        for y in sorted(lines):
            ws = [t for x, t in sorted(lines[y])]
            if any(k in ws[:3] for k in keys) or any(k == ws[0] for k in keys):
                print(p + 1, " ".join(ws))
def find(pdf, needle):
    d = pymupdf.open(pdf)
    return [i for i in range(len(d)) if needle in d[i].get_text()]
if __name__ == "__main__":
    pdf, needle = sys.argv[1], sys.argv[2]
    pg = find(pdf, needle); print(pg)
