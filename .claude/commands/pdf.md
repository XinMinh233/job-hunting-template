---
description: Turn a resume .md into the submission-ready PDF — build, check the real page count, walk the one-page trim if needed, hand back the file to upload
argument-hint: "[tailored file | company | app id — default: the most recent tailored resume]"
---

# /pdf — from Markdown to the file you actually submit

The bridge between /tailor's output and the application form. Runs the
render pipeline, verifies the real page count, and tells the user in
plain words which file to upload. Built for a user who has never run a
python command — they should never have to.

## Workflow

**1 — Resolve the file.**
- $ARGUMENTS is a path → use it (base/ files are allowed too, e.g. for
  a generic PDF to hand to a recruiter).
- $ARGUMENTS names a company or app id → the tracker row's
  `resume_version` file in tailored/.
- Empty → the most recently modified resume in tailored/ (never a
  `*_notes.md` file). Announce the choice in one line so a wrong guess
  is caught immediately.
- Nothing found → say so and point to /tailor. Never build a resume
  that doesn't exist.

**2 — Build.** Run:

```
python3 build_resumes.py <file> --density compact --pdf
```

The script renders HTML (render/resume.css), then prints to PDF via
headless Chrome with the page's own @page CSS — no print-dialog
variables — and reports the TRUE page count per file
(`[1 page: OK]` / `[N pages: ...]`).

**3 — Read the page count and act.**
- **1 page** → done. Report, in plain words: the PDF path in dist/,
  "this is the file you upload", and (if a tracker row matched) a
  reminder of the row's next_action.
- **2+ pages** → do not hand over an overlong resume silently. Open
  the companion `*_notes.md` Cut-First List (it exists precisely for
  this moment) and propose the first cut(s) — each with its one-phrase
  reason. Apply cuts ONLY with the user's OK, only to a not-yet-sent
  file, then rebuild and re-check. Repeat until one page. No notes
  file (a base resume, say) → propose trims yourself, least-relevant
  first, same approval rule.
- A resume already sent must never be edited (immutable history) — if
  the user asks to re-trim a sent file, derive a new dated tailored
  file instead and say why.

**4 — No Chrome?** The script says so and keeps the HTML. Relay the
fallback in beginner words: open `dist/<file>.html` in any browser →
Print → save as PDF, with margins Default, scale 100%,
headers/footers OFF. Also mention `CHROME_BIN` for users who have a
Chromium at a nonstandard path — one line, no more.

**5 — Nothing to commit.** dist/ is git-ignored on purpose: PDFs are
generated artifacts; the .md stays the source of truth. If the trim
loop edited a tailored file, commit THAT: `tailored: <company>
one-page trim`.

## Edge cases

- Multiple files passed → build all, report each page count on its
  own line.
- The resolved file fails resume_lint's rules on sight (stray HTML,
  tables) → warn that the render may be off and suggest /tailor's
  lint step, but still build; /pdf is not a gate.
- `--watch` requests ("let me preview while I trim") → hand them the
  exact command to run in a separate terminal:
  `python3 build_resumes.py <file> --watch` — live preview with a
  page-count badge that rebuilds on every save.
