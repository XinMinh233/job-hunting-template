#!/usr/bin/env python3
"""Deterministic formatting lint for resume Markdown — the machine-checkable
half of resume quality (judgment-level checks live in /audit; layout lives
in build_resumes.py). Run on tailored files before rendering; fix and
re-run until clean. Base files may legitimately exceed the char cap
(full-length, no page limit) — lint them with --max-chars 0 to skip.
`*_notes.md` companions are auto-skipped: they are gap reports, never
sent, so the resume rules don't apply to them.

Checks:
  bullet-glyph   every bullet uses "- " (no *, •, +, or en-dash bullets)
  bullets/role   at most N bullets under one entry header (default 6)
  bullet-length  per-bullet char cap (default 300; 0 disables). Skills
                 lines ("- **Label:** ...") and header-shaped bullets
                 ("- **Title** | date") are exempt — not prose bullets
  date-format    all entry-header date slots share ONE style
  spacing        no double blank lines, no trailing spaces, one final newline

Exit 0 = clean, 1 = findings (printed as file:line: rule: message).
"""

import argparse
import re
import sys
from pathlib import Path

BAD_BULLET_RE = re.compile(r"^\s*([*+•‣▪–—·])\s+\S")
HEADER_RE = re.compile(r"^\*\*.+")  # entry header: bold-opening line w/ | or pure bold
SKILLS_BULLET_RE = re.compile(r"^-\s+\*\*[^*]+:\*\*")  # skills line: "- **AI / LLM:** ..."

DATE_STYLES = {
    "en-month": re.compile(r"\b[A-Z][a-z]{2,8} \d{4}\b"),          # Mar 2022
    "cn-dotted": re.compile(r"\b\d{4}\.\d{2}\b"),                  # 2022.03
    "iso": re.compile(r"\b\d{4}-\d{2}\b"),                         # 2022-03
    "year-span": re.compile(r"\b\d{4}\s*[–—\-]\s*(\d{4}|Present|至今)\b"),  # 2015 – 2019
}


def is_entry_header(line):
    s = line.strip()
    return s.startswith("**") and ("|" in s or s.endswith("**"))


def lint(path, max_bullets, max_chars):
    findings = []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    bullets_in_entry = 0
    entry_line = None
    date_styles_seen = {}  # style -> first line no
    blank_run = 0

    def flush_entry():
        nonlocal bullets_in_entry
        if entry_line and bullets_in_entry > max_bullets:
            findings.append(
                (entry_line, "bullets/role",
                 f"{bullets_in_entry} bullets under this entry (max {max_bullets})")
            )
        bullets_in_entry = 0

    for i, raw in enumerate(lines, start=1):
        stripped = raw.strip()

        if raw != raw.rstrip():
            findings.append((i, "spacing", "trailing whitespace"))
        if not stripped:
            blank_run += 1
            if blank_run == 2:
                findings.append((i, "spacing", "more than one consecutive blank line"))
            continue
        blank_run = 0

        m = BAD_BULLET_RE.match(raw)
        if m:
            findings.append((i, "bullet-glyph", f"bullet uses '{m.group(1)}' — use '- '"))

        if stripped.startswith(("# ", "## ")):
            flush_entry()
            entry_line = None
            continue

        if is_entry_header(stripped):
            flush_entry()
            entry_line = i
            # date style: look only at the segment after the last pipe
            slot = stripped.rsplit("|", 1)[1] if "|" in stripped else stripped
            for style, rx in DATE_STYLES.items():
                if rx.search(slot):
                    date_styles_seen.setdefault(style, i)
            continue

        if stripped.startswith("- ") or BAD_BULLET_RE.match(raw):
            bullets_in_entry += 1
            # Skills enumerations and header-shaped bullets aren't prose
            # bullets — they legitimately run long; exempt from the char cap.
            content = stripped[2:] if stripped.startswith("- ") else stripped
            exempt = is_entry_header(content) or SKILLS_BULLET_RE.match(stripped)
            if max_chars and not exempt and len(stripped) - 2 > max_chars:
                findings.append(
                    (i, "bullet-length",
                     f"{len(stripped) - 2} chars (max {max_chars}) — split or tighten")
                )

    flush_entry()

    if len(date_styles_seen) > 1:
        detail = ", ".join(f"{s} (first at line {n})" for s, n in sorted(date_styles_seen.items()))
        findings.append((0, "date-format", f"mixed date styles in entry headers: {detail}"))

    if text and not text.endswith("\n"):
        findings.append((len(lines), "spacing", "missing final newline"))
    elif text.endswith("\n\n"):
        findings.append((len(lines), "spacing", "extra blank line(s) at end of file"))

    return findings


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--max-bullets", type=int, default=6)
    ap.add_argument("--max-chars", type=int, default=300,
                    help="per-bullet char cap; 0 disables (for base files)")
    args = ap.parse_args()

    dirty = False
    for f in args.files:
        if not f.is_file():
            sys.exit(f"not a file: {f}")
        if f.name.endswith("_notes.md"):
            print(f"{f}: skipped (notes companion — not a sent resume)")
            continue
        findings = lint(f, args.max_bullets, args.max_chars)
        for line, rule, msg in sorted(findings):
            dirty = True
            loc = f"{f}:{line}" if line else f"{f}"
            print(f"{loc}: {rule}: {msg}")
        if not findings:
            print(f"{f}: clean")
    sys.exit(1 if dirty else 0)


if __name__ == "__main__":
    main()
