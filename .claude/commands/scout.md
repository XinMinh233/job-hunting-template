---
description: JD sweep — one jd-scout agent per tier lane in parallel, verdicts logged to the tracker, funnel report
argument-hint: "[tiers, e.g. \"1 2\" — default: all lanes in data/scout-lanes.md]"
---

# /scout — JD sweep (manual trigger)

Run the bulk triage. The user triggers this manually (daily-ish); it
never runs unattended. Scouting is judgment work — no scheduler.

## WIP GATE (runs BEFORE any lane is swept)

Count the ACTIONABLE pre-apply rows in data/applications.csv — the ones
waiting on US, not on the user: `To tailor`, `Tailored`, `Queued`, and
any `Verify -` status.

Do NOT count `Hold -` or `Decision -` rows: those are parked on a
decision only the user can make, so they are not neglected inventory.

**If the actionable count is 5 or more, DO NOT SCOUT.** Report the
count, name the queue, and say plainly: *"The queue is full. Scouting
adds inventory that rots. Convert or close something first."* Then
stop. The user can override with an explicit instruction, but the
default is STOP.

WHY (measured in the hunt this template came from): it generated 11.5
leads for every application actually sent; postings decay ~50% in six
weeks, so seven genuinely eligible roles DIED waiting in the queue,
median 11 days held. Logging a JD is not progress — it only feels like
it. Throughput for one person is roughly 1-2 applications per week; a
queue longer than that is waste by definition.

## Workflow

**1 — Spawn the lanes.** Launch one `jd-scout` agent per tier lane
defined in data/scout-lanes.md, in parallel, each told only its lane.
$ARGUMENTS restricts which lanes run. Skip lanes whose sources are
app-gated-only (they're covered by the manual checklist instead). The
agents read the rubric, master.md, data/scout-lanes.md, and the
tracker for dedupe themselves, and return structured verdicts + a
funnel count + learnings. They never write; all writes happen here.

**2 — Collect and cross-dedupe.** Merge the verdict lists; drop
duplicates across lanes (same jd_link, or same company + role — keep
the higher-tier copy). Dedupe once more against data/applications.csv
before writing.

**3 — Log.** For every verdict (all are >= 60 by contract): append a
data/applications.csv row aligned to the live header — `id` = max + 1,
`date_logged` = today, `status` = New, `next_action` = Recruiter
review, `resume_version` blank, `notes` = tier, comms tag, sub-scores,
STRONG mark if >= 75, flags, source. Then append the matching first
event to data/events.csv: `date, app_id, logged, scout <lane>`.
Append-only, both files.

**4 — Update lane knowledge.** Fold the lanes' `learnings` into
data/scout-lanes.md as a dated section (append/refine; keep old
VERIFIED entries as history). Skip if all lanes returned nothing new.

**5 — Report** (in the user's preferred language(s); terse and
operational).
- One-line funnel tally: searched N, passed filter M, logged K (of
  which S strong >= 75), skipped — plus the per-tier breakdown. An
  empty funnel is reported honestly — never pad the tracker to look
  productive.
- MILESTONE CHECK — remind the user when a gated process is due:
  - **/rubric-drift** — DUE if >= 10 new JDs since the last approved
    re-weight (rubric change log / git log).
  - **competency map** (via /strategist expert) — re-derived at ~10-JD
    milestones; report the gap if not yet due.
  - **/strategy** — re-grounded every ~10-15 logged JDs; read the
    grounded-N from data/strategy.md's header if it exists.
  - **/review** — DUE if today is the user's review day, or >= 7 days
    since the last `review:` commit.
  State each as DUE / approaching / not-yet with the numbers;
  recommend but never auto-run.
- THE MANUAL CHECKLIST — the app/login-gated boards from
  data/scout-lanes.md the user hand-searches; list them with their
  lane's search terms, and ask for promising JDs to be pasted into
  /match.

**6 — Commit** the tracker + lane-knowledge changes: `data: scout
YYYY-MM-DD, logged K (S strong)`.

## Edge cases

- A lane agent dies or returns malformed verdicts → log the other
  lanes, report the failed lane explicitly, and offer to re-run just
  that lane.
- A verdict's jd_link is dead on re-check → still log it with "JD
  inaccessible, verify" in notes (the scout flagged it; the user
  decides).
- Zero new JDs across all lanes → report the empty funnel and stop; no
  commit.
- data/scout-lanes.md has no lanes yet → point to /onboard and stop.
