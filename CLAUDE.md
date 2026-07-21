# CLAUDE.md — job-search system

## First-run guard

If `master.md` still contains the marker `<!-- ONBOARD: not yet run -->`,
this system has not been set up for its user yet. Whatever was asked,
first suggest running `/onboard` (the guided setup interview) in one
friendly line — most commands cannot work without it. Do not run the
onboarding implicitly; it is a conversation the user drives.

## User preferences

<!-- ONBOARD: /onboard fills this section from the interview. -->

- Preferred chat language(s): (not set — ask, or default to the
  language the user writes in)
- Weekly time budget & protected time (WLB line): (not set)
- Target role family: see data/rubric.md "WHO THIS SCORES FOR"

## The user may be a beginner

Assume no programming or git knowledge unless the preferences above
say otherwise. Concretely: explain what a command did in plain words
after doing it; never show raw diffs or jargon without a one-line
translation; when something fails, say what happened and what you'll
do about it, not a stack trace. Questions about how this system works
are always in scope — answer them from the README and the command
files, patiently.

## Data flow (one-way, never reversed)

master.md → base/<track>.md → tailored/YYYY-MM-DD_<company>_<role>.md
JD (external) → /match → data/applications.csv → /tailor → /interview

- master.md is the ONLY entry point for new facts about the user
  (experience, projects, metrics, skills).
- base/: one full-length resume per track. Regenerated from master.md;
  never add new facts here directly.
- tailored/: one resume per JD, derived from a base, plus a
  `*_notes.md` companion (gap report, cut-first list — never sent).
  Resume files are IMMUTABLE after sending — each records exactly what
  a company received.
- data/applications.csv: tracker, current-state snapshot. One row per
  application. Columns: id, date_logged, company, role_title, jd_link,
  location_tz, target_tier, salary, match_score, must_have_gaps,
  strengths, status, next_action, resume_version, notes.
- data/events.csv: tracker, append-only timeline. One row per event
  (applied, reply, screen, interview, offer, rejection, ...).
  Columns: date, app_id, event, notes.

## File map

- .claude/commands/ — the system's workflows; one file per command.
  Read the command file before running one; each is self-contained.
- .claude/agents/ — jd-scout (bulk JD triage, read-only, structured
  verdicts) and interviewer (clean mock-interview persona; give it
  ONLY the JD + resume + history digest, never repo internals).
- .claude/skills/resume-style/ — truth, voice, and format rules for
  ALL resume output (auto-applied).
- data/rubric.md — JD scoring criteria, tiers, gates, weights. ONE
  canonical copy.
- data/scout-lanes.md — living scout knowledge (sources, methods,
  avoid-lists); read by jd-scout, appended by /scout.
- data/strategy.md — durable positioning layer; written only via
  /strategy with approval (does not exist until first run).
- data/competency-map.md — versioned competency map derived from the
  logged-JD corpus (does not exist until first derivation).
- data/self-check.md — the user's weekly self-review questions, read
  by /review.
- data/review_log.md — weekly digest log, append-only.
- prompts/interviewer-voice.md — paste target for the optional
  claude.ai voice-interview Project.
- build_resumes.py — Markdown → styled HTML/PDF (`--watch` live
  preview with page-count badge). render/resume.css owns layout.
- resume_lint.py — deterministic formatting gate; /tailor runs it.
- build_dashboard.py — read-only tracker dashboard (static or
  `--serve`); never writes back.

## Rules for Claude

- master.md is ground truth. On any conflict with base/, tailored/,
  or the tracker, master.md wins.
- NEVER invent facts about the user — no skills, numbers, titles,
  dates, or scope they didn't state. A blank beats a guess. (The
  resume-style skill owns the full truth rules.)
- When a new fact surfaces in conversation, propose adding it to
  master.md first; never write it only into a derived file.
- Prefer creating a new dated file in tailored/ over modifying an
  existing one — sent files are historical records.
- Update the tracker only through the commands, preserving the column
  schemas above. applications.csv: append or update rows, never
  delete. events.csv: strictly append-only.
- Every status change in applications.csv is paired with a matching
  events.csv row, so the timeline stays complete.
- Approval gates are real: /strategy, /rubric-drift, and tracker
  status changes proposed by /daily apply only on the user's go.
- End every session that changed files with a commit (one line, plain:
  `<area>: <what & why>`).
- Keep this file lean: step-by-step workflows belong in
  .claude/commands/, not here.
