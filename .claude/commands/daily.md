---
description: Morning strategist pass — expert(light) → recruiter → pm over rows new/changed since the last pass; three priorities for today's apply block
---

# /daily — the everyday refresh (light, incremental)

Runs the three strategist banners in sequence in ONE response — the
sanctioned exception to one-role-per-response; keep their reasoning
cleanly separated. Follow the role definitions in
.claude/commands/strategist.md (read it first, plus the shared state
it names).

WHEN: /daily is the OPENING step of the apply block. The pass looks
BACK at yesterday's events and FORWARD at today's next_actions; its
three priorities are the work order for the apply block that starts
the moment the pass ends. /scout is not a prerequisite — yesterday's
scout results are simply part of "since the last pass".

Precondition 0 — SYNC PREFLIGHT (before reading any tracker file):
`git fetch origin` + `git status -sb`; if BEHIND origin, pull (merge)
first — if work also lands from other machines or cloud sessions, the
local tree may be days stale. If the pull conflicts, stop and resolve
with the user before the pass. (Skip silently if there is no remote.)

Precondition: data/applications.csv has logged JDs. If empty, reply
"Run /scout first — or /match a posting you've already found." and
stop.

Announce at the top: `[DAILY] expert(light) → recruiter → pm`.

**Find "since the last pass" honestly:** the tracker is in git — use
the last /daily or /scout commit (`git log`) plus events.csv dates to
identify rows that are NEW or changed since then. Do not re-process
rows already reviewed unless they changed.

STEP 1 — [TARGET-ROLE EXPERT] incremental

- MASTER FRESHNESS SCAN (cheap — three checks; question the user only
  on a trigger). master.md holds dated facts about the outside world,
  and dated facts decay in BOTH directions — claims go stale AND new
  work goes unlogged:
  1. **Unlogged-work check:** if the user's portfolio repos are on
     GitHub (linked from master.md), check for pushes AFTER
     master.md's "Last updated" stamp ⇒ ask in one line what shipped;
     new facts route through master.md first.
  2. **Stale-claim check:** any master.md fact tagged "verified
     YYYY-MM-DD" about the outside world (repo visibility, live URLs,
     third-party states) older than 14 days ⇒ flag for a cheap
     re-verify. If the live-link check is older than 7 days AND
     anything is about to be submitted, re-run the curl loop now.
  3. **[VERIFY] aging:** any open Verification Log item older than 30
     days ⇒ surface it (resolve or consciously drop — don't let it
     rot).
- Look only at new/changed rows. Surface any NEW gaps they reveal —
  don't repeat the full gap analysis.
- Re-derive the competency map ONLY if the logged-JD count just
  crossed a ~10-JD milestone since the last version, or the map is
  unset/stale (bootstrap: if data/competency-map.md doesn't exist yet
  and N >= 10, derive v1 now per the strategist expert rules).
  Otherwise say "map unchanged (vN)".

STEP 2 — [RECRUITER] review new/changed rows

- For new rows: pursue priority (tier first, then match score + salary
  within tier), recommended Status and Next action. Flag below-floor
  or high-comms-risk rows. Leave already-handled rows alone unless
  something changed.
- Apply approved Status/Next-action updates to data/applications.csv
  with paired data/events.csv rows; otherwise just recommend.
- DUE FOLLOW-UPS: scan ALL rows in an active post-apply status
  (Applied, Screen, Interview) — not just new/changed ones — and flag
  any whose next_action is a "Follow-up YYYY-MM-DD" date on or before
  today. This is the one place /daily deliberately looks past the
  "since last pass" delta. For each, surface it as a due-now action
  (nudge shape per data/strategy.md if it defines one; else a polite
  D+7/D+14 rhythm); on the user's go, draft the nudge and advance
  next_action to the next step.
- DUE DEADLINES (pre-apply, symmetric): scan ALL rows in a live
  pre-apply status (To tailor, Tailored, Queued, Verify –, Decision –,
  Hold) for a hard date in next_action OR notes near a deadline word
  (closes / deadline / submit by / apply before). Flag every one whose
  date is on or before today+2. This is a HARD gate: a STRONG (>=75)
  row with a deadline inside the window is the top priority of the
  pass and must be surfaced as act-today, ahead of any new-lead triage
  — an application deadline missed is a lead lost outright. Report "no
  deadlines due" honestly when the scan is clean.
- DECAY SCAN (freshness gate). Scan ALL rows in a live pre-apply
  status for a `date_logged` or last event older than FOUR WEEKS.
  Those rows are PRESUMED STALE — the posting is more likely dead than
  alive. Name them plainly; do not let them sit in the queue reading
  as live inventory. On the user's go, re-verify each at its PRIMARY
  SOURCE and either refresh the row or close it
  `Closed - posting removed`.
- CHEAP-VERIFY REFLEX. Any `next_action` that is merely "ask X" /
  "confirm Y" / "open the page" — an email or a page load, not a work
  session — is a SAME-DAY action, never a queue item. Surface every
  one and BATCH them into a single message or a single call. Field
  note: in the original hunt, ONE unsent message of this kind held
  seven rows hostage for ten days and three of them died waiting.

STEP 3 — [PM] daily review

- Summarize what was scouted/logged/applied since the last pass and
  any surfaced gaps; output exactly THREE priorities for TODAY. These
  are the apply block's work order — actionable within the time budget
  in the user preferences, not an end-of-day wish list.

CLOSE: one line naming the first action of today's apply block. If
files changed, commit: `daily: YYYY-MM-DD pass`.

## Do NOT

- Do NOT re-derive the competency map every run.
- Do NOT re-plan the whole week — that's /review's weekly job. /daily
  is incremental only.
- Do NOT invent tracker contents; empty deltas are reported honestly
  ("nothing new since yesterday's pass").
