---
description: Weekly digest — week's git log + tracker summary + PM weekly review with per-tier funnel and one course-correction
---

# /review — weekly review

Runs under the `[PM]` banner, following the strategist role
definitions (.claude/commands/strategist.md) and its shared-state
reading list. Pick a fixed morning for it (the README suggests
Saturday) and keep it.

**0 — SYNC PREFLIGHT (before reading ANY tracker file).** `git fetch
origin` then `git status -sb`. If the local branch is BEHIND origin,
pull (merge) FIRST; if the pull conflicts, stop and resolve with the
user before reviewing anything. (Skip silently if there is no
remote.) Field note: the original hunt's first stale-tree review
reported a screen "idle 5 days" about a video submitted the day
before, missed two rejections, prescribed a moot course-correction,
and had to be reverted. A review that doesn't pull first audits a
snapshot, not the system.

**1 — What happened.** `git log --since="1 week ago" --oneline` plus
the week's rows in data/applications.csv, data/events.csv, and
data/interview_log.csv: what was scouted, logged, tailored, applied,
answered, interviewed (real and mock).

**2 — Funnel metrics, per tier.** scouted → logged → strong (>=75) →
applied → responded, broken down per tier (funnel counts from /scout
reports where available; logged-and-after straight from the tracker).
Compare against last week's entry in data/review_log.md if one exists
— call out week-over-week deltas (applied, sent, responses).

**2b — FALSIFICATION PASS (mandatory — this is the step that makes a
review worth running).** Every other step in this command computes
FROM the tracker. The tracker is therefore both the data and the
yardstick, and a review that only reads its own records can never
discover that the records are FALSE — only that we failed to act on
them. So ask the second question explicitly:

**"What did we believe last week that is no longer true?"**

Concretely, every week:
- SAMPLE at least 5 live rows (prefer the highest-scoring and the
  oldest) and re-verify each at its PRIMARY SOURCE — the employer's
  own ATS, never the aggregator. Is it still open? Does its geography
  clause still admit this candidate? Is there a deadline nobody
  logged?
- Report what DIED, and update those rows (`Closed - posting removed`
  / `Skip (geo gate)`) with paired events rows.
- Name any belief the week disproved — a "strong" row that was never
  eligible, a deadline that never existed, an artifact assumed shipped
  that isn't.

A week with zero falsifications is reported honestly as zero — but a
run of zeroes means the sample is too small or too comfortable, not
that the tracker is clean.

Field note: the review that forced this step was rigorous,
well-evidenced, internally consistent — and aimed its confident
course-correction at a conversion queue that was mostly DEAD (23 of
32 rows). No component's job had been to check whether reality still
agreed with the records.

**2c — THE THREE NUMBERS THAT MEASURE THE REAL BOTTLENECK.** Report
all three, every week, plainly. Volume of logged JDs is NOT progress
and must never be reported as if it were.

- **TIME-TO-APPLY (median days, logged → applied).** The single number
  that measures the actual constraint. Compute it over every row ever
  applied. If it is RISING week over week, say so and stop scouting
  until it falls.
- **DECAY COST — rows that DIED while we held them.** For every row
  closed `Closed - posting removed` this week: its score, and how many
  days we held it. Separate the ones that were never eligible (a
  scouting failure) from the ones we COULD have applied to (a
  conversion failure). Name the second group and its scores out loud.
  It is the honest price of delay, and it is invisible unless someone
  prints it.
- **LEADS-PER-APPLICATION (logged / sent).** Healthy is single
  digits. (The original hunt hit 11.5x — 46 logged, 4 sent. That is
  not a pipeline, it is a warehouse, and postings decay ~50% in six
  weeks.)

**2d — OWNER'S SELF-CHECK (the user answers — not Claude).** Read
data/self-check.md and put its three questions to the user, with this
week's numbers from step 2c attached so they are answering against
evidence, not memory. Do NOT answer for them and do NOT soften them.
If they name a habit, offer to bake it into a command — structural
fixes beat recall.

**3 — Verdict.** What's working, what isn't — grounded in the
numbers, no padding. If data/strategy.md defines a phase plan, check
the pace against it.

Weigh the funnel numbers ONLY after step 2b — a "16 strong" computed
over unverified rows is not a metric, it is a rumour.

**4 — ONE course-correction.** Exactly one concrete change for next
week, with the evidence for it. (More than one = none get done.)

A moratorium or focus rule proposed here may BAN BUILDING TOOLS — it
must never ban VERIFYING REALITY. Re-checking existing rows against
their primary sources is conversion work, not meta-work.

**5 — Next week's top 3.** Three priorities, realistic for the
user's weekly time budget — flag if the backlog exceeds what one week
holds.

Also surface, when due:
- /rubric-drift if >= 10 new JDs since the last approved re-weight.
- Competency-map re-derive if N crossed a ~10-JD milestone this week.
- Stale rows: applications with no event for 7+ days and a pending
  next_action — name them.
- DECAY: rows untouched for 4+ weeks — presumed stale, prime
  candidates for the step-2b sample.
- LIVE-LINK CHECK: re-run master.md's link check if any resume went
  out this week or any repo/demo changed.

**6 — Record the digest.** APPEND this week's review to
data/review_log.md (append-only, most recent at the bottom, terse).
One dated entry per the established format: a one-line week header
(`## Week N · <range> · reviewed <date> (<dow>)`), the per-tier funnel
table, the Verdict, the ONE course-correction, next week's top 3, the
due-checks, and a final one-line Snapshot (`N · strong · applied ·
sent · responses · mocks`) so the next /review can diff week-over-week.
Never edit past entries.

The review_log.md entry is the digest's durable record; the chat
delivery (in the user's preferred language(s)) is the same content
rendered for reading. Keep the two consistent.

**Commit.** `review: week N digest (<one-line headline>)`.

EXCEPTION: the falsification pass (step 2b) may also write
applications.csv + events.csv, but ONLY to record what the primary
sources proved — a posting that is gone, a geography clause that
excludes the user. Closing a dead row is bookkeeping, not strategy: it
needs no approval, and leaving a ghost in the tracker is the more
dangerous act. Every other tracker change still belongs to /daily and
/tailor.
