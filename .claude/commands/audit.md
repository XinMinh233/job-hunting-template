---
description: Three-pass audit for a resume. Pass A flags unverifiable / inflated / vague claims; Pass B rewrites AI-sounding lines into plain, defensible language; Pass C checks structure (quantification, verb-first, ordering). Never invents facts. Does not touch layout.
argument-hint: "[resume-file] [mode: all|truth|voice|structure]"
allowed-tools: Read, Write, Grep, Glob
disable-model-invocation: true
---

# Resume Truth-and-Voice Audit

You are auditing the resume at `$1` line by line — Read it from disk first.
Mode = `$2` (if empty, default to `all`). `truth` = Pass A only. `voice` = Pass B only. `structure` = Pass C only. `all` = A, then B, then C.

**Scope note — you audit CONTENT, not LAYOUT.** Do not touch or comment on rendered page length, date alignment, column widths, spacing, or ATS table tricks — those are owned by the build script (`build_resumes.py`) and the design CSS (`render/resume.css`). If you notice a layout issue, mention it in one line under "out of scope" and move on; never rewrite it.

If `$1` is empty or does not resolve to a readable file, do NOT guess: ask the user to paste the resume text or give a valid path, then stop.

Respect this project's CLAUDE.md and the resume-style skill for output language and voice. When auditing master.md-derived facts, master.md is the reference for what is confirmed.

## PRIME DIRECTIVES (always, non-negotiable)

1. **Never invent or infer facts.** Do not add or assume metrics, percentages, job titles, dates, employers, team sizes, tech stacks, or scope that are not already in the source or explicitly confirmed by the user.
2. **Missing detail → ask, never fill.** If a number or specific is absent, mark it and pose a question. A blank is honest; a fabricated number is a liability the user has to defend in an interview.
3. **You flag and rewrite; the human owns the truth.** Truth calls are never yours to assume. You surface the risk and the question.
4. **Plainer and smaller beats impressive and hollow.** Preserve meaning; never inflate. If the only way to make a line sound stronger is to add a claim, don't — ask for the real underlying detail instead.
5. **Never edit the source file during the passes.** Findings go to chat or a NEW `resume-audit-report.md`. What happens after depends on whether `$1` was already sent (check its status/events in the tracker, or ask):
   - **Not yet sent** → once the user has confirmed the truth calls, apply the confirmed rewrites directly to `$1` on the user's request — only lines the user explicitly confirmed or chose, nothing speculative. This is the normal flow: tailor → audit → fix this version → build → send.
   - **Already sent** → the file is a historical record; never touch it. Findings apply to the NEXT tailored version.

---

## PASS A — Truth audit  (run when mode is `all` or `truth`)

Go through every bullet / claim line. For each, output one table row:

| # | Original line | Verdict | Why | Interview-story question | Action |

**Verdicts:**
- `VERIFIABLE` — concrete, specific, plausibly backed by a real artifact or story.
- `INFLATED` — likely real underneath but the wording overstates scope/impact.
- `FABRICATION-RISK` — asserts a specific fact (number, title, scale) that cannot be checked from the resume alone and would collapse under interview questioning if untrue.
- `VAGUE` — no verifiable content ("passionate about delivering value"); says nothing checkable.

**The test to apply to every line:** *Could the candidate tell a specific 2-minute interview story about this — with a real number, the names of the system/tools, what actually broke, and what they personally did?* If not, it is not `VERIFIABLE`.

**Actions:** `KEEP` / `DOWNGRADE` (soften to the defensible core) / `CUT` / `NEEDS-EVIDENCE` (keep only if the user can supply the real detail).

For the `Interview-story question` column, write the single sharpest question the user must be able to answer out loud (e.g. "What was the baseline and how was the 30% measured?" / "Did you lead the team or contribute to it?").

**End of Pass A:** collect every `FABRICATION-RISK`, `NEEDS-EVIDENCE`, and `INFLATED` line into a short numbered checklist of open questions. Then STOP and ask the user to answer them and confirm any `CUT`/`DOWNGRADE` decisions **before** running Pass B. Do not rewrite a line whose truth is still unconfirmed. Facts the user confirms here are new master.md material — propose appending them (Metrics Bank / Verification Log) so future runs inherit them.

---

## PASS B — Voice rewrite  (run when mode is `all` or `voice`)

Only rewrite lines the user has kept or confirmed. If run in `voice` mode standalone, still refuse to rewrite any line asserting a specific fact until the user confirms it is true.

**AI-voice tells to hunt and kill:**
- **Filler verbs:** spearheaded, leveraged, orchestrated, utilized, championed, drove, empowered, facilitated, architected (when not literal), streamlined (as decoration).
- **Buzz adjectives:** robust, seamless, cutting-edge, comprehensive, innovative, dynamic, scalable (as decoration), state-of-the-art, best-in-class, passionate, results-driven, detail-oriented.
- **Structures:** triple parallels ("designed, developed, and deployed"), impact-with-no-mechanism ("improved efficiency by 40%" with no "by doing X"), noun-heavy abstraction that hides who did what.

**Rewrite rules:**
- Use plain verbs the person would actually say aloud: built, wrote, shipped, fixed, cut, set up, ran, migrated, measured, debugged, replaced.
- **Verb-first:** every bullet must open with a strong action verb. Flag any bullet that opens with a noun, "Responsible for…", "Worked on…", or a gerund used as a title, and rewrite it to lead with the verb.
- **No-fluff adjectives (general rule, beyond the banned list):** delete any adjective or adverb that is not carrying a fact. If removing the word loses no information a screener could act on, remove it. Keep only descriptors tied to a concrete number, name, or outcome.
- Keep the real object + real number; state exactly one mechanism: *did X by doing Y, which led to Z.*
- **Non-native-speaker rule:** fix grammar and unnatural phrasing, but keep it plain — add no flourish, raise no register, never inflate. The goal is authentic and defensible, not "polished."
- One line per bullet where possible; concrete over abstract.
- Offer at most **2 variants** per line, labeled (e.g. `tighter` / `fuller`).

**Output per line:**

> **Original:** …
> **`tighter`:** …
> **`fuller`:** …
> _changed: <one line on what you removed/plainer-ed>_
> ✅ defensible because … **or** ⚠️ still needs a real number/story from you

---

## PASS C — Structure & consistency  (run when mode is `all` or `structure`)

Judgment-level structural checks only — the things an LLM reads well. Leave deterministic formatting to the build script. For each finding, name the line and the fix; do not silently rewrite unless the user is in `all` mode and the line already passed Pass A/B.

- **Quantification coverage:** every bullet should carry a measurable result (number, %, scale, time saved, before→after). List any bullet with NO quantifiable outcome and either (a) rewrite it to surface a real metric the user confirmed, or (b) flag it `NEEDS-METRIC` and ask what the number was. Never invent the number.
- **Verb-first coverage:** scan all bullets; list every one that does not open with an action verb (see Pass B) and give the verb-first fix.
- **Reverse-chronological order:** within each section (experience, projects, education), check that entries run most-recent-first. Flag any out-of-order entry by its dates; do not reorder layout, just report it.
- **Tense & person consistency:** past roles in past tense, current role in present; no first-person pronouns. Flag deviations.
- **Soft length signal (advisory only):** if any single bullet runs long (roughly >2 lines of prose) or a role carries an unusually high bullet count, flag it as verbosity to trim — but state clearly you cannot measure rendered page length; one-page enforcement belongs to the build script and the tailored notes file's cut-first list.

Output Pass C as a short findings list grouped by check, each item as `line/section → issue → fix`.

---

## STOP CONDITIONS

- If asked to make a line "sound more impressive" beyond the facts → refuse, explain why, and ask for the real underlying detail.
- Never add a skill, tool, metric, or achievement not in the source or confirmed by the user.
- If most of the resume can't be verified, that is an acceptable outcome: output the question checklist and stop. Do not paper over gaps with guesses.

## OPTIONAL ARTIFACT

If the user asks to save the results, write them to `resume-audit-report.md` (create new; never touch `$1`). Otherwise present everything inline in the conversation.
