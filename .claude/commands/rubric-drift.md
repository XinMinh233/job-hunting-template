---
description: Rubric-drift check — do the match weights still discriminate on the real market? Propose-only; the user approves before anything changes.
---

# /rubric-drift — keep the match weights honest

Purpose: keep data/rubric.md's weights honest against the REAL market
instead of the initial guess. Never change weights silently —
propose, the user approves. Weekly cadence at most, manually
triggered.

**Gate:** run only if >= 10 JDs are logged in data/applications.csv
SINCE the last approved re-weight (see the rubric's change log). If
fewer, report "insufficient new data (N<10), skipping" and stop —
never re-weight on noise.

## Procedure

1. Read all logged JDs from data/applications.csv, including the
   per-dimension sub-scores recorded in `notes` (e.g. "sub MH72 Sen90
   Tier62 Dom85 Nice80").
2. Examine which dimensions actually DISCRIMINATE: are strong (>= 75)
   roles separated from the rest mainly by must-haves, by
   tier/WLB/comms fit, or by something the current weights
   under-count? Look for requirements that recur across JDs but
   aren't well captured by any dimension.
3. PROPOSE a re-weighting only if the evidence warrants it.
   Conservative: move weight in 5-point steps; the five dimensions
   must still sum to 100. If the current weights still fit, say so
   explicitly — that is a valid outcome.
4. OUTPUT a short diff, nothing more:
   - Current weights vs. proposed weights (one line each).
   - 2-3 lines of justification grounded in specific logged JDs (name
     them by id/company).
5. WAIT for the user's approval. Apply nothing until they say go.
6. On approval: edit data/rubric.md — update the weights table and
   the dimension notes if affected, bump the Version line at the top,
   and add a change-log line in the established format (version,
   date, N, evidence, new weights). Commit as `rubric: vX.Y —
   <one-line reason>`. The rubric has ONE canonical copy in this
   repo; there is nothing else to sync.

## Do NOT

- Do NOT re-weight on < 10 new JDs or on a single outlier posting.
- Do NOT change the 60/75 thresholds here — that is a separate
  decision the user raises explicitly.
- Do NOT touch scores already logged in the tracker — re-weighting
  applies from now on; history stays as scored.
