# Job-Search System — template

A complete, single-repo job-hunting system that runs inside Claude
Code: a career fact base, a resume pipeline, a JD tracker, and the
prompts that drive them. Everything is a plain text file; git is the
shared state and the memory.

**New here? Read [START-HERE.md](START-HERE.md) first, then run
`/onboard`.** This README is the reference for daily use afterwards.

> Provenance: this template was distilled from a real, heavily-used
> hunt system (2026). The gates and habits baked into the commands —
> the WIP gate, the primary-source gate, the freshness gate, the
> falsification pass — each exist because their absence measurably
> cost that hunt applications. Field notes explaining the "why" are
> kept inline where they teach.

## The shape of the system

```
master.md  →  base/<track>.md  →  tailored/YYYY-MM-DD_<company>_<role>.md
(your facts)   (one per track)      (one per application, immutable once sent)

JD (found) → /match → data/applications.csv → /tailor → apply → /interview
                       data/events.csv (append-only timeline)
```

- `master.md` is the ONLY entry point for new facts about you.
- `base/` holds one full-length resume per track you pursue.
- `tailored/` holds one dated resume per application, plus a
  `*_notes.md` companion (gap report, cut-first list — never sent).
  Sent files are immutable history.
- `data/applications.csv` is the tracker (one row per application);
  `data/events.csv` is its append-only timeline. CSV on purpose:
  line-diffable, no database, no lock-in.

## Daily loop (start of your apply block)

1. `/daily` — light incremental pass over rows new/changed since the
   last pass; ends with exactly THREE priorities for today.
2. `/tailor <id|company>` — derive a tailored resume from the right
   base, lint it, write the file pair, update the tracker.
3. `/audit tailored/<file>.md` — truth/voice/structure pass; apply
   confirmed fixes to this (un-sent) version.
4. `python3 build_resumes.py tailored/<file>.md --watch` — live HTML
   preview with a page-count badge; trim per the notes file's
   cut-first list. Then `--density compact --pdf` renders the real
   PDF. Submit the `dist/*.pdf`.
5. After sending: commit. The tailored file is now immutable history.
6. `/scout` — after the apply block, not before it: sweeps your lanes
   for new postings, logs scoring JDs. Its results feed tomorrow's
   `/daily`. (Applying converts; scouting only stocks the shelf —
   which is why it goes last.)
7. (optional) `/interview <id>` — text mock interview; the score row
   is logged automatically.

## Weekly loop (pick a fixed morning — the template says Saturday)

- `/review` — the week's numbers, a falsification pass against
  reality, ONE course-correction, next week's top 3.
- `/rubric-drift` — only if ≥ 10 new JDs since the last approved
  re-weight; propose-only, you approve.
- `/strategy` — refresh your positioning doc if it shifted
  (milestones: roughly every 10 logged JDs).
- Manual sweep of any app-gated boards in `data/scout-lanes.md`;
  paste anything promising into `/match`.

## Command quick-reference

- `/onboard` .......... first-run interview; builds your personal files
- `/scout` ............ JD sweep (jd-scout agents, one per lane), log + funnel
- `/match <JD>` ....... score one JD, append tracker row + first event
- `/daily` ............ morning opener: incremental pass, 3 priorities
- `/strategist <role>`  ad-hoc recruiter / pm / expert reasoning
- `/strategy` ......... draft/refresh data/strategy.md (approval-gated)
- `/tailor <id>` ...... tailored resume pair into tailored/, lint, track
- `/audit <file>` ..... 3-pass content audit (truth / voice / structure)
- `/interview <id>` ... text mock via interviewer agent; `sync` logs voice rows
- `/review` ........... weekly digest + PM review
- `/rubric-drift` ..... weights check vs the market (propose-only)
- `build_resumes.py` .. md → HTML/PDF (`--watch` = live preview + page badge)
- `resume_lint.py` .... deterministic formatting gate (run by /tailor)
- `build_dashboard.py`  read-only tracker dashboard — tiles, funnel,
                        action queue, searchable table (`--serve` = live)

## Voice interview satellite (optional)

Text mock interviews run right here (`/interview`). To also drill
spoken delivery: create a claude.ai Project on mobile, paste
`prompts/interviewer-voice.md` into its instructions, and run voice
sessions there. Each session ends by emitting a score row — paste it
back with `/interview sync <row>` so the log stays complete.

## Maintenance rules (the short list)

- `master.md` is ground truth for facts; the tracker for application
  state; git history is the memory. Never trust chat memory over them.
- The rubric, the strategy doc, and the competency map each live in
  exactly ONE file under `data/` — there is nothing to keep in sync.
- Tracker changes go through commands: `applications.csv` rows are
  never deleted; `events.csv` is append-only; every status change is
  paired with an event row.
- Sent tailored files are immutable; audits of sent files feed the
  next version.
- End every session that changed files with a commit.
