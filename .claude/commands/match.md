---
description: Score one JD against data/rubric.md + master.md, append a tracker row and its first event
argument-hint: <pasted JD or JD link> [recruiter/source notes]
---

# /match — score one JD, log it

Score a single JD and log it. This is the only entry point (besides
/scout) that adds applications to the tracker.

## Workflow

**1 — Get the JD.** Pasted text preferred; a link is fine if the page
loads cleanly. Never reconstruct a JD from memory or a search snippet.

**1b — PRIMARY-SOURCE GATE (before anything is scored).** Per
data/rubric.md: an aggregator is a discovery feed, never evidence. If
the JD came from LinkedIn / Himalayas / We Work Remotely / any repost
site, OPEN THE EMPLOYER'S OWN POSTING (Greenhouse / Ashby / Lever /
Workday / icims / careers page) and read the geography, work-mode,
freshness, and deadline from there.

- Quote the country / timezone / work-authorization clause into
  `notes`. A body-text country allowlist BEATS a "Remote - Worldwide"
  header, always.
- Capture the posting's real last-updated date and any APPLICATION
  DEADLINE into `notes`. (A missed deadline is a lead lost outright,
  and /daily can only surface a deadline that was written down.)
- Primary source unreachable (403, login-walled)? Then the row is
  logged with status `Verify - geo (primary unread)`, NO target_tier,
  and NO score. It is a lead, not an application. Say so plainly; do
  not guess a tier to fill the cell.

**2 — Dedupe.** Check data/applications.csv for the same jd_link or
the same company + role. If it exists, say so, show the existing row,
and stop (update it only if the user asks).

**3 — Score.** Apply data/rubric.md exactly as written — its hard
gates, tiers, current dimension weights, thresholds, and comms-load
tag — judging evidence against master.md (ground truth for what the
user can claim). Show per-dimension sub-scores, not just the total.

Scoring is only permitted once step 1b passed. Geography sets the tier
and the tier drives pursue order, so a tier assigned from an
unverified label does not merely mislead — it manufactures a score.

**4 — Verdict.**
- Score < 60 → report SKIP with the sub-scores and the reason in two
  lines. Log it only if the user explicitly wants it tracked anyway.
- Score >= 60 → append a row to data/applications.csv, aligned to the
  live header (read it every run): `id` = max existing id + 1;
  `date_logged` = today; `status` = New; `next_action` =
  strat-recruiter review; `resume_version` blank; `salary` exactly as
  posted or "not stated" (never guessed); `notes` carries tier, comms
  tag, sub-scores (e.g. "sub MH72 Sen90 Tier62 Dom85 Nice80"), STRONG
  mark if >= 75, and any flags (extra-language requirement, seniority
  stretch, JD inaccessible, verify items).

**5 — First event.** Append to data/events.csv: `date, app_id,
logged, <one-line source/context>`. Every application enters the
timeline the moment it enters the tracker.

**6 — Echo.** Show the appended row(s) and the verdict line: tier,
score, STRONG or not, top gap.

## Rules

- Rows are append-only downward: never delete; update named fields of
  an existing row only when explicitly asked (and then pair the change
  with an events.csv row if it is a status change).
- Do not import JD claims into any resume content from here — /tailor
  owns that, under the resume-style skill.
- Multiple JDs pasted at once → confirm order, then process
  sequentially, one row + one event each.
- Rubric not yet personalized (WHO THIS SCORES FOR unset) → point to
  /onboard and stop.
