"""Build paper/manuscript.tex and manuscript.pdf from paper/manuscript.md.

manuscript.md is the source of truth -- tests/test_canonical_numbers.py asserts
it against results/canonical_numbers.json. The .tex is generated, never edited:
a hand-maintained second copy would drift from the first, which is exactly the
defect found in tier_a_results.csv (written by a different run than
canonical_numbers.json, disagreeing in the third decimal on all 16 values).

    python paper/build.py           # regenerate .tex and compile to .pdf
    python paper/build.py --check   # non-zero exit if the .tex is stale

Requires pandoc and tectonic on PATH.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREAMBLE = HERE / "preamble.tex"
FIGURES = HERE.parent / "results" / "figures"

# Two documents share one preamble and one source of numbers:
#   manuscript.md  the tested source; tests/test_canonical_numbers.py asserts it
#   paper.md       the same results restructured for a general venue
# Both are markdown; both compile through pandoc. Neither .tex is edited.
# name -> (preamble, body-page cap or None). A two-column document declares a
# cap; build.py reads the page on which references begin and fails the build if
# the body exceeds it.
WIDE_TABLE_COLUMNS = 4   # tables with more columns span both columns

# `paper.md` was retired in round 11 and moved to paper/archive/. It duplicated
# manuscript.md in a different section order, and maintaining four documents is
# what allowed a corrected claim to land in two of them and not the other two.
DOCUMENTS = {
    "manuscript": ("preamble.tex", None),      # full-detail version / preprint
    "paper_a": ("preamble_conf.tex", 8),       # conference: calibration
    "paper_b": ("preamble_conf.tex", 8),       # conference: evaluation
}

# Optionally preceded by the "**Table N.** ..." paragraph pandoc renders just
# above the table; without capturing it the caption stays in the body text
# while the table floats to another page.
LONGTABLE = re.compile(
    r"(?:\\textbf\{Table\s*\d+\.?\}([^\n]*)\n\n)?"
    r"\{\\def\\LTcaptype\{none\}[^\n]*\n"
    r"\\begin\{longtable\}\[\]\{(.*?)\}\n"
    r"(.*?)"
    r"\\end\{longtable\}\n\}", re.S)

# The markdown lists the figures as prose at the end; the typeset version
# embeds them. Caption text is taken from the markdown so the two agree.
# manuscript.md lists its figures as prose at the end; the floats are appended.
FIGURE_BLOCK = re.compile(
    r"\*\*Figure (\d+)\*\*\s*[—\-]+\s*`(figure\d+_[a-z_0-9]+\.png)`\.\s*"
    r"(.+?)(?=\n\n|\Z)", re.S)

# paper.md cites each figure where it is discussed; the float is placed there.
# Deliberately NOT re.S, and the title may not span lines. With `.` matching
# newlines, a "Figure N." citation that carries no image file (an unrendered
# [TODO] placeholder) backtracks forward to the next figure's filename and
# swallows every section in between into one caption.
FIGURE_INLINE = re.compile(
    r"^\*\*Figure (\d+)\.\*\*[ \t]*\*([^*\n]+)\*[ \t]*"
    r"\(`(figure\d+_[a-z_0-9]+\.png)`\)\.[ \t]*"
    r"((?:[^\n]|\n(?!\n))*)", re.M)


def to_float_tables(body: str) -> str:
    """Rewrite pandoc longtables as float tables that work in two columns.

    longtable cannot be used inside a twocolumn document -- it typesets across
    the full page and silently swallows the surrounding text. pandoc emits it
    for every pipe table. This converts each to a `table*` float spanning both
    columns, which is the correct construct for a wide table in a two-column
    layout.
    """
    def swap(match):
        caption, spec, inner = match.groups()
        # longtable's head/foot machinery has no meaning in a tabular.
        for token in ("\\endhead", "\\endfirsthead", "\\endlastfoot",
                      "\\endfoot", "\\noalign{}"):
            inner = inner.replace(token, "")
        # pandoc repeats \bottomrule before \endlastfoot and again at the end;
        # keep a single rule.
        inner = inner.replace("\\bottomrule\n\n", "", 1)
        inner = re.sub(r"\n{3,}", "\n", inner).strip("\n")
        # In a full-width float \linewidth is still the column width, so wide
        # tables need \textwidth; single-column tables must keep \linewidth.
        if (spec.count(">{") or spec.count("p{") or 1) > WIDE_TABLE_COLUMNS:
            spec = spec.replace("\\linewidth", "\\textwidth")
        # \caption goes above the tabular, and LaTeX supplies the number, so
        # the manual "Table N." prefix is dropped rather than duplicated.
        head = (f"\\caption{{{' '.join(caption.split())}}}\n"
                if caption and caption.strip() else "")
        # A narrow table belongs in one column. Making every table a full-width
        # float wastes roughly a page across a paper of this size, because each
        # `table*` reserves the full text width whatever its content.
        columns = spec.count(">{") or spec.count("p{") or 1
        if columns <= WIDE_TABLE_COLUMNS:
            return ("\\begin{table}[t]\n\\centering\n\\small\n"
                    f"{head}\\begin{{tabular}}{{{spec}}}\n{inner}\n"
                    "\\end{tabular}\n\\end{table}")
        return ("\\begin{table*}[t]\n\\centering\n\\small\n"
                f"{head}\\begin{{tabular}}{{{spec}}}\n{inner}\n"
                "\\end{tabular}\n\\end{table*}")
    return LONGTABLE.sub(swap, body)


def _require(tool: str) -> None:
    if shutil.which(tool) is None:
        sys.exit(f"error: {tool} not found on PATH")


def _tex_caption(text: str) -> str:
    """Markdown emphasis and LaTeX specials in a caption, made safe.

    Inline math is protected first: the escaping below strips backslashes, which
    would silently turn $\\log_2(RR_A \\times RR_B)$ into "log_2(RR_AtimesRR_B)".
    """
    text = " ".join(text.split())
    math = []

    def stash(match):
        math.append(match.group(0))
        return f"\x00{len(math) - 1}\x00"

    text = re.sub(r"\$[^$]+\$", stash, text)
    text = text.replace("\\", "").replace("%", "\\%").replace("&", "\\&")
    text = text.replace("_", "\\_").replace("`", "")
    text = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", text)
    text = re.sub(r"\*(.+?)\*", r"\\emph{\1}", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: math[int(m.group(1))], text)


def _float(filename: str, caption: str, number: str, width: str = "0.85") -> str:
    return (f"\n\\begin{{figure}}[htbp]\n\\centering\n"
            f"\\includegraphics[width={width}\\linewidth]{{{filename}}}\n"
            f"\\caption{{{caption}}}\n\\label{{fig:{number}}}\n"
            f"\\end{{figure}}\n")


def place_inline_figures(text: str) -> str:
    """Replace each inline figure citation with a LaTeX float in place.

    pandoc passes a raw LaTeX block through untouched when it is separated by
    blank lines, so the float lands exactly where the figure is discussed
    rather than being collected at the end.
    """
    def swap(match):
        number, title, filename, rest = match.groups()
        if not (FIGURES / filename).exists():
            print(f"warning: {filename} missing, leaving figure {number} as text")
            return match.group(0)
        caption = _tex_caption(f"**{title}.** {rest}")
        return _float(filename, caption, number)
    return FIGURE_INLINE.sub(swap, text)


AUTHOR_LINE = re.compile(r"^\*\*Authors?\.\*\*[ \t]*(.+)$", re.M)


def title_block(markdown: Path) -> tuple[str, str]:
    """Author text for \\author{}, and the body with that line removed.

    Without this the author line sits before the first heading and is swept
    into the abstract environment, which then prints "Abstract" twice: once as
    the environment's own heading and once as the markdown section.
    """
    text = markdown.read_text()
    match = AUTHOR_LINE.search(text)
    if not match:
        return "", text
    return _tex_caption(match.group(1)), text[:match.start()] + text[match.end():]


def split_abstract(text: str) -> tuple[str, str]:
    """Return (abstract markdown, remaining body).

    The two-column layout needs the abstract inside a full-width box above the
    columns, so it must be extracted rather than left in document order.
    """
    match = re.search(r"^##[ \t]+Abstract[ \t]*$", text, flags=re.M)
    if not match:
        return "", text
    rest = text[match.end():]
    nxt = re.search(r"^##[ \t]+", rest, flags=re.M)
    end = nxt.start() if nxt else len(rest)
    return rest[:end].strip(), text[:match.start()] + rest[end:]


def markdown_body(markdown: Path, drop_abstract: bool = False) -> str:
    """The document minus the trailing figure-caption list, if it has one."""
    _, text = title_block(markdown)
    if drop_abstract:
        _, text = split_abstract(text)
    else:
        # The abstract environment supplies its own heading.
        text = re.sub(r"^##[ \t]+Abstract[ \t]*$", "", text, count=1, flags=re.M)
    head, _, tail = text.partition("## Figures\n")
    if not tail:
        return place_inline_figures(text)
    # Keep everything after the caption list (references onward).
    rest = tail.split("## 8. References", 1)
    remainder = "## 8. References" + rest[1] if len(rest) > 1 else ""
    return head + remainder


def figure_floats(markdown: Path) -> str:
    """Trailing float section, for documents that list figures at the end."""
    text = markdown.read_text()
    if "## Figures\n" not in text:
        return ""
    out = ["\\clearpage", "\\section*{Figures}",
           "\\addcontentsline{toc}{section}{Figures}", ""]
    for number, filename, caption in FIGURE_BLOCK.findall(text):
        if not (FIGURES / filename).exists():
            print(f"warning: {filename} missing, skipping figure {number}")
            continue
        out.append(_float(filename, _tex_caption(caption), number))
    return "\n".join(out)


def _pandoc(text: str) -> str:
    return subprocess.run(
        ["pandoc", "-f", "markdown", "-t", "latex", "--wrap=preserve"],
        input=text, text=True, capture_output=True, check=True).stdout


def render(markdown: Path, preamble_name: str = "preamble.tex",
           two_column: bool = False) -> str:
    _require("pandoc")
    body = _pandoc(markdown_body(markdown, drop_abstract=two_column))

    # pandoc makes the H1 title a \section; the preamble supplies \title.
    title = re.search(r"^\\section\{(.*?)\}\\label\{[^}]*\}\n", body, flags=re.S)
    heading = " ".join(title.group(1).split()) if title else markdown.stem
    if title:
        body = body[:title.start()] + body[title.end():]
    # Demote one level: markdown "## 1. Introduction" -> \section.
    for src, dst in (("subsubsection", "subsection"), ("subsection", "section")):
        body = body.replace(f"\\{src}{{", f"\\{dst}{{")
    # Single-column: the abstract is whatever precedes the first \section, and
    # is wrapped here. Two-column documents have already had it lifted into the
    # title block, so wrapping again yields an empty abstract environment.
    if not two_column:
        marker = body.find("\\section{")
        if marker > 0:
            body = ("\\begin{abstract}\n" + body[:marker].replace("\\hrulefill", "")
                    + "\\end{abstract}\n\n" + body[marker:])

    authors, cleaned = title_block(markdown)
    preamble = (HERE / preamble_name).read_text()
    preamble = preamble.replace("%%TITLE%%", heading).replace("%%AUTHORS%%", authors)
    if two_column:
        abstract, _ = split_abstract(cleaned)
        preamble = preamble.replace("%%ABSTRACT%%", _pandoc(abstract).strip())
        body = to_float_tables(body)
        # References begin on a fresh page so the body page count is exact.
        body = re.sub(r"(\\section\{References\})",
                      r"\\clearpage\n\\label{sec:endofbody}\n\1", body, count=1)
    return "\n".join([preamble, body, figure_floats(markdown),
                       "\\end{document}", ""])


def body_pages(tex: Path) -> int | None:
    """Page on which the body ends, read from the references label in the .aux."""
    aux = tex.with_suffix(".aux")
    if not aux.exists():
        return None
    match = re.search(r"\\newlabel\{sec:endofbody\}\{\{[^}]*\}\{(\d+)\}", aux.read_text())
    return int(match.group(1)) if match else None


def build(name: str, make_pdf: bool = True, check: bool = False) -> int:
    markdown = HERE / f"{name}.md"
    tex = HERE / f"{name}.tex"
    if not markdown.exists():
        print(f"skip: {markdown.name} not present")
        return 0

    preamble_name, cap = DOCUMENTS[name]
    two_column = cap is not None
    rendered = render(markdown, preamble_name, two_column)
    if check:
        current = tex.read_text() if tex.exists() else ""
        if current != rendered:
            print(f"{tex.name} is stale; run `python paper/build.py`")
            return 1
        print(f"{tex.name} is up to date")
        return 0

    tex.write_text(rendered)
    print(f"wrote {tex}")
    if not make_pdf:
        return 0

    _require("tectonic")
    result = subprocess.run(["tectonic", "--keep-intermediates", tex.name],
                            cwd=HERE, capture_output=True, text=True)
    overfull = [line for line in result.stderr.splitlines() if "Overfull" in line]
    if overfull:
        print(f"  {len(overfull)} overfull boxes")
    if result.returncode:
        print(result.stderr[-3000:])
        return result.returncode

    status = 0
    if cap is not None:
        pages = body_pages(tex)
        if pages is None:
            print("  WARNING: could not locate the references label")
        else:
            body = pages - 1  # references start on their own page
            verdict = "OK" if body <= cap else "OVER"
            print(f"  body pages: {body} (cap {cap}) [{verdict}]")
            if body > cap:
                status = 1
    for stem in (".aux", ".log", ".out"):
        tex.with_suffix(stem).unlink(missing_ok=True)
    print(f"wrote {tex.with_suffix('.pdf')}")
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="exit non-zero if a .tex is out of date")
    parser.add_argument("--no-pdf", action="store_true")
    parser.add_argument("--only", choices=tuple(DOCUMENTS),
                        help="build one document instead of all")
    args = parser.parse_args(argv)

    targets = (args.only,) if args.only else tuple(DOCUMENTS)
    return max(build(name, make_pdf=not args.no_pdf, check=args.check)
               for name in targets)


if __name__ == "__main__":
    raise SystemExit(main())
