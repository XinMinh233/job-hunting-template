---
description: Text mock interview for one application, run by the isolated interviewer agent; appends one score row to the interview log. `sync` mode appends a voice-session row instead.
argument-hint: "<app id | company>   — or:  sync <pasted voice-session row>"
---

# /interview — text mock interview (stage 1 of the routine)

The interview routine has up to three steps: **1. text** (here — lock
content and structure), **2. voice** (optional: a claude.ai mobile
Project running prompts/interviewer-voice.md — drill delivery),
**3.** any external pronunciation app the user chooses. This command
runs step 1 and keeps the shared log, data/interview_log.csv, in sync
for all of them.

## Mode A — run a text session (default)

**1 — Resolve the application.** Find the row in
data/applications.csv matching $ARGUMENTS (id or company). Collect:

- **The JD** — ask the user to paste it if it isn't in this
  conversation (jd_link alone is not enough unless the page loads
  cleanly). Never reconstruct a JD from memory.
- **The resume** — the tracker row's `resume_version` file in
  tailored/ if it exists, else the base resume that fits the role's
  center of gravity.
- **History digest** — from data/interview_log.csv: the last ~10
  rows' questions, weak spots, and recurring flags, condensed to a
  short list.

**2 — Spawn the interviewer agent** (subagent type `interviewer`)
with ONLY those three things: JD text, resume text, history digest.
Nothing else — no master.md, no *_notes.md, no rubric, no tracker
contents, no conversation history. The interviewer must be as blind
as a real one; prep notes in its context would soften the interview.

**3 — Relay.** Show the agent's reply to the user VERBATIM — no
summarizing, no commentary, no hints (anything you add pollutes the
interview). Send the user's answer back to the same agent with
SendMessage. Repeat until the agent delivers its debrief + score row.
Pass through the user's control requests (pause, stop, "re-answer in
my other language") verbatim too.

**4 — Log.** Parse the agent's pipe-delimited score row and append it
to data/interview_log.csv, aligned to the live header (read the
header on every run), with `app_id` filled from the tracker row.
interview_log.csv is append-only — never edit or remove existing
rows. Do NOT add an event to events.csv: mock practice is not a
pipeline event ("interview" there means a real one with the company).

## Mode B — `sync`: log a voice-session row

`/interview sync <row>` — the user pastes the pipe-delimited row a
voice session emitted on mobile.

1. Map the row's columns onto the data/interview_log.csv header (the
   voice prompt uses the same order, minus app_id).
2. Resolve `app_id` by matching the row's role_jd against
   data/applications.csv; if ambiguous, ask one question.
3. Append; never modify existing rows. Echo the appended row for
   confirmation.

If several rows are pasted at once, append them all in the given
order.

## Edge cases

- No tracker row for the target → say so in one line; /match logs
  JDs.
- No interview_log.csv rows yet → session 1: empty digest, still log
  the resulting row.
- Agent relay unavailable (agent dies mid-session) → apologize,
  debrief from what was covered yourself, log the partial session
  with a note in `next_action`.
- A sync row whose column count doesn't match the header → show the
  mismatch and ask; never guess score values.
