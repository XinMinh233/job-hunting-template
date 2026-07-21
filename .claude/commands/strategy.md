---
description: Draft or refresh data/strategy.md — the durable positioning layer every strategist mode reads. Draft → the user approves → write + commit; never rewritten silently.
---

# /strategy — the positioning layer (RECRUITER role)

Runs under the `[RECRUITER]` banner, following the strategist role
definitions (.claude/commands/strategist.md).

data/strategy.md is BOTH an output (drafted here) and an input (read
by every recruiter/PM pass afterward) — so it is (re)written ONLY on
this explicit command, never silently mid-conversation.

## What it must contain (~1 page, tight)

- One-line market narrative: who the user is to their target
  employers.
- Lead strengths: the 2-3 they lead with everywhere, drawn from
  master.md.
- Gaps they preempt: the recurring objections and how they frame
  around them.
- Language/comms strategy (if applicable): which working-language
  loads they favor and how they position any gap.
- Geo/WLB strategy: which tiers they prioritize and the WLB line they
  won't cross.
- Salary floor: per tier/currency — the number the recruiter flags
  against.
- Phase shape: the hunt's phase plan at a glance (e.g. build → apply
  → interview), with the current phase marked.
- Deliberate tradeoffs: what they are choosing NOT to pursue, and
  why.

## Evidence rule

- Mandate preflight: read data/career-map.yaml first — its `pursuing`
  path(s) are the mandate this whole document positions within (the
  career-strategy layer above this hunt). A stance still carrying a
  `seeded:` marker counts as the mandate, but the draft must flag it
  as unconfirmed. Skip silently if the map has no paths yet; never
  edit it from here.
- Ground every section in master.md + the logged-JD signals in the
  tracker (and the competency map if it exists). No section on vibes.
- Empty tracker → label the draft "PROVISIONAL (no JDs yet)" and say
  to run /scout or /match first, then re-run /strategy.
- On refresh: read the current data/strategy.md first and note in 2-3
  lines what changed since the last version and why. Record the
  grounded-N (logged-JD count) in the header so /scout can tell when
  a refresh is due.

## Flow

1. Draft the full doc; show it in chat.
2. The user edits/approves — apply their corrections verbatim; they
   override your judgment.
3. On approval: write data/strategy.md and commit
   `strategy: <draft|refresh> — <one-line what changed>`.
   Do not write before approval.
