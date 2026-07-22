---
description: Derive a tailored resume for one JD from the right base, write to tailored/, update the tracker
argument-hint: <app id | company> — plus pasted JD and optional recruiter notes
---

# /tailor — per-application tailored resume

Derive a posting-specific resume from the right base resume, write it
(plus a companion notes file) to tailored/, and update the tracker.
All writing follows the resume-style skill. Tailoring selects,
reorders, re-angles, and re-words — it never invents; every statement
traces to master.md.

## Inputs

- **The application** — $ARGUMENTS names an id or company from
  data/applications.csv. The row must exist: /match logs and scores
  JDs. If there is no row, say so in one line and point to /match.
- **The JD** (required) — pasted text preferred. If only a URL is
  available, open it; if the page is unreadable, ask for pasted text.
  Never reconstruct a JD from memory or a web search.
- **Recruiter notes** (optional) — an emphasis signal from an insider:
  they outrank the JD text on what to stress and how to word it, but
  they are not a source of facts about the user.

## Workflow

**1 — Preflight.** Confirm master.md exists and is onboarded (else
point to /onboard in one line). Find the application row in
data/applications.csv. Re-read master.md and, once chosen, the base
resume from disk in this run — never from conversational memory of
them.

**1b — FRESHNESS + GEO GATE. Do not skip this to save a fetch — it is
cheaper than a wasted tailoring session.** Before drafting a single
line:

- OPEN THE EMPLOYER'S OWN POSTING (Greenhouse / Ashby / Lever /
  Workday / icims / careers page — never the aggregator the row was
  found on) and confirm the role is STILL LIVE. Dead posting → set
  status `Closed - posting removed`, pair an events.csv row, tell the
  user in one line, and STOP. Do not tailor for a ghost.
- CONFIRM GEOGRAPHY from that same source: does the country / timezone
  / work-authorization clause actually admit this candidate? An
  aggregator "Worldwide" header is not evidence. Geo-gated →
  `Skip (geo gate)` + event, and STOP.
- CAPTURE THE DEADLINE into the row's notes if the posting states one.
- If the row has not been touched in over four weeks, this check is
  MANDATORY.

Field note: the audit that forced this gate killed 23 of 32 "live"
rows — 13 postings no longer existed, 10 were geo-gated. A tailoring
session spent on either is a session stolen from a real application.

**2 — Parse.** From the JD: company, role title, posting language,
location and work mode, must-have vs nice-to-have requirements, stack
and domain keywords. From recruiter notes: emphasis points, insider
signals, and any factual claims about the user.

**3 — Fact-check recruiter claims.** If a recruiter note asserts
something about the user that master.md does not back, ask the user to
confirm it (one batched question) before drafting. Confirmed → usable,
and propose appending it to master.md so future runs inherit it.
Unconfirmed → omit from the resume and log it in the notes file.

**4 — Select the base.** Choose the base/ file whose track and
language fit the JD's center of gravity; a posting in another of the
user's working languages → the base for that language, and output in
it. A bilingual JD → ask one question: which output language? Announce:
`Base: {file} — {one-line reason}`. If the user objects, redo with the
base they name, without argument. If the needed base file is missing
but master.md exists, derive that base first per the resume-style
skill, then continue.

**5 — Map evidence.** For each key requirement: the strongest
master.md evidence (reference `Exp-` / `Proj-` IDs) or an honest gap.
Mark **verify-and-rerun** items: `[VERIFY]`-tagged master content that
would strengthen this application if the user confirmed it. Do not
re-score the JD — match_score in the tracker row is /match's verdict;
if it is empty, suggest running /match first.

**5b — Readiness gate.** After mapping, compare the JD's center of
gravity — the role TITLE plus its top must-haves — against the
evidence. If it rests on a competency whose strongest closer is an
in-progress or `[VERIFY]`-tagged artifact (master.md Verification
Log), do not let the application go out weak silently:

- State it plainly: `Title-level gap: {competency} — closer:
  {artifact}, status: {in progress/unverified}`.
- Check the posting window. If the deadline (minus ~1 week of margin)
  leaves room for the artifact to land: still tailor now, but
  recommend HOLD SUBMISSION — set `next_action` to "Hold submission
  for {artifact}; re-tailor + submit by {deadline − 1 week}" and pair
  a `decision` event.
- If the window is too tight for the artifact: present the submit-now
  risk honestly (where the screen will probe, the offsetting angle)
  and let the user choose; record the call in the notes file.
- The gate never blocks tailoring itself — the file pair is written
  either way, so the later re-tailor is a diff, not a restart.

**6 — Draft.** Start from the chosen base. Reorder skills groups and
bullets by relevance to this posting; swap in the ready-made bullets
whose angle fits; re-word to the JD's own terminology only where
master.md backs the skill; apply recruiter emphasis above JD emphasis;
rewrite the Summary to speak to this role (it may mirror the JD's role
title — the user's past job titles never change). Keep full length,
relevance-ordered. Exclude all `[VERIFY]`-tagged content — the resume
file must be submission-clean.

**7 — Write the file pair.**

- `tailored/YYYY-MM-DD_{company}_{role}.md` — the resume. Filename:
  today's date; lowercase; spaces and slashes → hyphens; the company's
  common English name when it has one, otherwise its native name; on
  collision append `-v2`, `-v3` — never overwrite an earlier tailored
  file, they are historical records.
- `tailored/YYYY-MM-DD_{company}_{role}_notes.md` — companion notes
  (JD lines may be quoted in their original language). May contain
  `[VERIFY]` tags. Sections:
  1. **Gap Report** — each key requirement → strongest evidence (with
     `Exp-`/`Proj-` IDs) → honest gap; include the verify-and-rerun
     list.
  2. **Cut-First List** — ordered list for the one-page hand-trim:
     first item is the first thing to cut, each with a one-phrase
     reason. List enough cuts to plausibly reach one rendered page.
  3. **Recruiter Notes Applied** — each recruiter point → how it was
     honored, or why it was declined. "None provided" if there were
     none.

**8 — Lint + LIVE-LINK CHECK.** Run `python3 resume_lint.py
<resume file>` (the notes file is exempt). Fix every finding and
re-run until clean — a tidy resume reads as a tidy candidate. If the
linter is missing, enforce the same rules by hand and flag its
absence.

Then CHECK EVERY URL the resume claims — repos and live demos alike:

```
grep -oE 'https?://[^ )]+' <resume file> | sort -u | \
  while read u; do printf '%s  %s\n' "$(curl -s -o /dev/null -w '%{http_code}' "$u")" "$u"; done
```

Anything not 200 → fix the link or cut the entry, and correct
master.md if the claim there is stale. A public link that 404s is
worse than no link. Record the result in master.md's Verification Log.

KNOWN FALSE POSITIVE: linkedin.com returns **HTTP 999** to any
non-browser request (their bot-block), never 200. That is NOT a broken
link — ignore 999 on linkedin.com. Treat 403 on other hosts with the
same suspicion: confirm in a browser before cutting anything over a
status code.

Field note: master.md holds dated facts about the outside world, and
dated facts decay in BOTH directions — the original hunt nearly cut a
perfectly good project because a "repo is private" note was days
stale.

**9 — Update the tracker.** In data/applications.csv, update the row:
`status` → `Tailored`, `resume_version` → the tailored filename,
`next_action` → apply/submit step. Append one row to data/events.csv:
`date, app_id, tailored, <base used + one-line angle>`. Read each
file's header on every run and align to it exactly — the live header
always wins. Fill cells only from the JD, recruiter notes, this run's
outputs, or today's date; leave truly unknown cells blank. Never
delete rows; events.csv is append-only.

**10 — Report.** In chat: base + reason, top gaps in at most two
lines, verify-and-rerun items if any, the files written, lint status,
and the tracker updates made. Close by naming the next step
explicitly: **run `/pdf` to turn this into the submission-ready PDF**
— a beginner will not know the .md is not the thing they upload.

## Edge cases

- JD given as a URL that won't load → ask for pasted text; do not
  proceed without the actual JD.
- Multiple JDs at once → confirm the order, then process sequentially,
  one file pair per JD.
- Recruiter notes contradict the JD on facts about the company or role
  → recruiter wins for emphasis as the insider signal, but record the
  discrepancy in the notes file. Factual conflicts about the **user**
  always go to the user.
- Same company and role tailored again → new dated file (or `-v2` on
  same-day collision); never modify the earlier pair.
