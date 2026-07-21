# JD-MATCH RUBRIC — canonical source of truth

# Version: v1.0 (template)

# WHO THIS SCORES FOR

<!-- ONBOARD: /onboard fills this from the interview. State: target
     role family + close title variants, target seniority, working
     language(s) with honest strength notes (e.g. "solid written
     English, weaker spoken"), and location/work-mode reality. The
     whole rubric scores FOR this person — keep it honest, not
     aspirational. -->

(not set — run /onboard)

# THE SCORE

Score each JD 0-100 across five weighted dimensions. Show per-dimension
sub-scores in your working, not just the total.

# TARGET TIERS (priority order)

Every JD is classified into one tier, recorded in the tracker's
`target_tier` column. Pursue-order keys off tier FIRST, then match
score within a tier. Tiers are location/work-mode priority groups —
define the ones that fit YOUR situation.

<!-- ONBOARD: define 2-4 tiers. The pattern that worked for the
     original hunt (a China-based candidate targeting foreign
     employers) was:
       Tier 1 — global remote from home country (highest priority)
       Tier 2 — foreign employer with a local office
       Tier 3 — abroad with relocation/sponsorship
       Tier 4 — domestic employers (lowest, still in scope)
     Yours may be as simple as "1 remote / 2 my city / 3 relocate". -->

(not set — run /onboard)

# DIMENSIONS & WEIGHTS

| #   | Dimension                      | Weight |
| --- | ------------------------------ | ------ |
| 1   | Must-have skill coverage       | 35%    |
| 2   | Seniority fit                  | 15%    |
| 3   | Target-tier / WLB / comms-load | 25%    |
| 4   | Domain & stack fit             | 15%    |
| 5   | Nice-to-have coverage          | 10%    |
|     | TOTAL                          | 100%   |

<!-- These starting weights survived two evidence-based re-weights in
     the original hunt. Don't hand-tune them on gut feel — /rubric-drift
     re-weights them against YOUR logged-JD corpus once you have data
     (≥10 JDs), and logs each change below. -->

# DIMENSION NOTES

1. MUST-HAVE SKILL COVERAGE (35%)
   How many of the JD's hard requirements the base resume already
   evidences. Weight by how central each is to the role.

2. SENIORITY FIT (15%)
   Against the target seniority in WHO THIS SCORES FOR. Clearly
   over-senior or under-level roles score low (the scout drops the
   extreme cases at the hard gate).

3. TARGET-TIER / WLB / COMMS-LOAD FIT (25%)
   - Tier: score by the tier ladder above. All defined tiers are
     loggable; tier sets priority, it does not gate.
   - WLB: better fit the more the role protects the working pattern
     set in the user preferences (CLAUDE.md).
   - Comms-load: if the user is stronger written than live in a
     working language, an async/written/docs-driven role is a BETTER
     fit and a heavy-live-meetings role a worse one. A role running in
     a language the user is native in removes the barrier entirely and
     scores HIGH here — a strength, not a risk.

4. DOMAIN & STACK FIT (15%)
   Overlap with the target stack and domain named in WHO THIS SCORES
   FOR.

5. NICE-TO-HAVE COVERAGE (10%)
   The JD's preferred/bonus items the resume can speak to.

# THRESHOLDS

- LOG if score >= 60 (append a row to applications.csv)
- STRONG if score >= 75 (mark as a priority)
- SKIP if score < 60 (do not log, but still COUNT it so funnel volume
  stays visible)

# SALARY (captured, NOT a scored dimension)

The scout records salary in the tracker (currency + range, or "not
stated") but does NOT score it — salary is a pursue-factor, not a
skill-match factor. Never drop a role for omitting salary. The
recruiter role ranks pay WITHIN a tier (currencies aren't
cross-comparable) against the salary floor in data/strategy.md.

# PRIMARY-SOURCE GATE (runs BEFORE any tier is assigned)

An aggregator is a DISCOVERY FEED, NEVER EVIDENCE. Geography,
work-mode, and freshness are read from the EMPLOYER'S OWN posting —
Greenhouse / Ashby / Lever / Workday / icims / SmartRecruiters / the
company careers page — and from nowhere else.

A row whose primary source has NOT been opened and read:
- gets status `Verify - geo (primary unread)`,
- is NOT assigned a target_tier,
- is NOT scored.
No tier, no score, no pursue rank. It is a lead, not an application.

Read from the primary source, and quote it into `notes`:
- the COUNTRY / TIMEZONE / WORK-AUTHORIZATION clause (a body-text
  country allowlist BEATS a "Remote — Worldwide" header every time),
- the posting's real last-updated date,
- any application deadline.

WHY THIS EXISTS (field note from the original hunt, 2026, N=32):
every single aggregator "Worldwide / open to all countries" label
checked against the employer's ATS was FALSE — one carried the
corpus's second-highest score purely on a fabricated label, and one
aggregator also fabricated posted-dates and deadlines on re-scrape.
Because geography sets the tier and the tier drives pursue order, an
unverified label does not merely mislead — it manufactures a score.

# FRESHNESS GATE

Postings decay fast: the same audit found ~50% of a six-week-old batch
already DEAD (req deleted, "no longer accepting applications").

- A posting whose primary source shows it removed/closed → status
  `Closed - posting removed`. Never carried as live inventory.
- A row untouched for MORE THAN 4 WEEKS is PRESUMED STALE. It must be
  re-verified at its primary source before it consumes a tailoring
  session (/tailor enforces this at preflight).

# FILTER GATES (applied by the scout BEFORE scoring)

A posting is dropped only if it fails a HARD gate:

- Tier: fits none of the defined tiers.
- Language: not workable in any of the user's working languages. A
  role requiring an additional language the user doesn't speak is
  FLAGGED in notes, not dropped, if the employer may be flexible.
- Seniority: clearly far above or below the target level.
- Geography (HARD, from the PRIMARY SOURCE only): the posting's own
  country / timezone / work-authorization clause excludes the user AND
  offers no relocation/sponsorship path. A relocation + sponsorship
  path is NOT a drop — it is a row for the user to decide on.

# COMMS-LOAD TAG (recorded by the scout in the tracker's notes)

"Comms: Low / Med / High" — describes live-communication demand in the
user's non-native working language(s).

- Low = async, written, PR/docs/issue-driven, few live meetings.
- Med = some standups/reviews live, mostly written otherwise.
- High = customer-facing, frequent live calls, heavy pairing.
- If the role runs in a language the user is native in, tag the
  language instead (e.g. "Comms: CN") — the barrier does not apply and
  this is a positive signal.
  High-comms roles are flagged, never dropped — the recruiter role
  weighs the barrier.

# CHANGE LOG

- v1.0 — template baseline: dimensions and weights inherited from the
  original hunt's v1.5 (twice re-weighted on evidence, N=14 and N=46);
  primary-source, freshness, and geography gates inherited from its
  v1.6. Personal targeting removed; /onboard personalizes.

# (Add a line each time /rubric-drift leads to an approved re-weight.
#  Bump the Version line at the top in the same edit.)
