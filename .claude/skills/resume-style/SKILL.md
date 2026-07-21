---
name: resume-style
description: Truth, voice, and format rules for all resume and career-document output. Apply whenever writing or editing master.md, base resumes in base/, tailored resumes in tailored/, or LinkedIn drafts — any content a company or recruiter might read.
---

# Resume style — truth, voice, and format rules

## Truth rules (non-negotiable)

- master.md is ground truth. Every factual statement in any derived
  file traces to approved master.md content. master.md itself takes
  facts only from direct user statements, the user's LinkedIn, or
  user-confirmed old-resume content — never from JDs, recruiter
  notes, or inference.
- Numbers appear only if the user supplied or confirmed them (they
  live in master.md's Metrics Bank with sources). Never estimate,
  extrapolate, or round up. A bullet without a number beats a bullet
  with an invented one.
- Never upgrade skill claims ("used X once" must not become "expert
  in X"). Depth wording follows the user's own words.
- In Chinese, skill-level words follow the ladder 了解 < 熟悉 < 熟练 <
  精通 and must match the depth the user confirmed; when unsure, use
  the lower word. 精通 only if the user explicitly claims mastery.
- Anything plausible but unconfirmed: tag it inline as
  `[VERIFY: what exactly needs checking]`. Tags may appear in
  master.md, base resumes, and notes files; **tailored resume files
  must be tag-free** (submission-clean). Every open tag also appears
  in master.md's Verification Log.
- Do not import phrases, claims, or requirements from JDs into the
  user's content as facts.

Additional rules when tailoring:

- Tailoring may **select, reorder, re-angle, and re-word — never
  invent**.
- Recruiter notes steer emphasis, ordering, and wording; they can
  never introduce facts about the user. A recruiter-claimed fact
  absent from master.md is confirmed with the user or omitted.
- Adopt the JD's own terminology only for skills master.md actually
  backs (if the JD requires a tool the master has no evidence for,
  that tool appears nowhere).
- Never alter past job titles, dates, or organizations to match a JD.
  The Summary and Skills sections do the aligning.

## Voice rules (English output)

- Plain, natural English. Test every line: could the user comfortably
  say this aloud in an interview and defend it? Prefer common words;
  keep sentences short; one idea per bullet; name real technologies.
- Banned words and phrases: spearheaded, leveraged, utilized,
  passionate, results-driven, synergy, seasoned, dynamic,
  cutting-edge, state-of-the-art, world-class, proven track record,
  honed, delved, meticulous, visionary, and "responsible for" as a
  bullet opener. If a sentence sounds like every AI-written resume,
  rewrite it.
- Bullet grammar: start with an action verb; no pronouns (I/my) in
  bullets; past tense for completed work, present tense only for
  ongoing duties in a current role. Vary the opening verbs — never
  repeat one formula bullet after bullet.
- Non-native speakers: fix grammar and unnatural phrasing, but keep
  it plain — add no flourish, raise no register, never inflate. The
  goal is authentic and defensible, not "polished."
- First person is allowed **only** in the narrative parts of
  master.md (Positioning Summary) and in LinkedIn About drafts.
  Resume files contain no pronouns.

Register example:

- ✗ "Spearheaded the development of a cutting-edge AI-powered
  solution, leveraging modern frameworks to drive significant
  improvements."
- ✓ "Built a support-ticket agent that routes requests across four
  internal tools; cut average handling time by 32%." _(the 32% may
  appear only because the user stated it)_
- ✓ (no number available) "Built a support-ticket agent that routes
  requests across four internal tools."

## Chinese output rules (for users who write Chinese resumes)

- Simplified Chinese throughout; keep technology names and standard
  industry terms in English, as is normal in Chinese tech resumes.
- Write natively from master.md's Experience and Project records —
  never translate English resume bullets sentence-by-sentence.
  Translationese (翻译腔) is a defect; if a line reads like translated
  English, rewrite it.
- Bullets start with a verb (负责 / 主导 / 搭建 / 实现 / 优化 / 设计…),
  vary the verbs, one idea per bullet; numbers only from the Metrics
  Bank.
- Do not include age, photo, marital status, political status, or
  expected salary unless the user explicitly asks.

## Format rules (all output files)

- Standard Markdown only — H1 for the name/title, H2 for sections,
  plain bullet lists. No tables, no HTML, no images (the downstream
  Markdown→HTML converter requires this).
- Links must be clickable Markdown, `[visible text](url)` — the
  renderer only turns that form into `<a>`; bare URLs render as dead
  text. Use `mailto:` for the email and `https://` for web links.
- Contact-line links use short word labels, not spelled-out URLs
  (`[GitHub](url) · [Blog](url) · [LinkedIn](url)`). The email stays
  in full so it can be copied off a printed page. Label links
  honestly (a blog of essays is "Blog", not "Portfolio").
- In a project's title line prefer short labels too
  (`[live demo](url)`, `[repo](url)`) over the full URL.
- Dates as YYYY-MM-DD wherever a full date is needed.
- No page limit on any file — completeness and truth beat brevity.
  The one-page hand-trim happens downstream, guided by the notes
  file's cut-first list.

## File structures

### English resumes (base and tailored)

- H1: name. One line beneath: location | email | links (email and
  links as clickable Markdown, per the format rules).
- Lead summary paragraph, **no heading** — 3–5 lines, no pronouns,
  angled to the role family (base) or the specific posting
  (tailored). It sits directly under the contact line; the renderer
  styles the first paragraph after the name as the contact line and
  any following paragraph as body text, so the summary needs no
  `## Summary` label.
- **Skills** — grouped and ordered by relevance.
- **Experience** — reverse-chronological. Per role: a bold header
  line (`**Role — Organization** | Dates`) and 3–6 bullets chosen and
  re-angled from the master's ready-made bullets.
- **Projects** — those relevant to the target.
- **Education & Certifications**.

Each base file opens with an HTML comment naming its track and the
emphasis order (what leads, what supports) so tailoring runs know its
center of gravity. /onboard writes the first one.

Full-length means: include everything genuinely relevant, ordered by
relevance; cut only what is irrelevant, never for page count.

### Chinese resume (CN base and CN tailored files)

- H1 姓名 (English name in parentheses if the user wants it). One
  line beneath: 电话 | 邮箱 | 链接 (邮箱与链接用可点击的 Markdown 链接，
  标签保留中文前缀如 `邮箱：[…](mailto:…)`；电话为纯文本). Unlike the
  English resume, 个人简介 keeps its `## 个人简介` heading — it is the
  second section (after 求职意向), not the opening paragraph.
- Sections: **求职意向** (target role titles in Chinese, plus
  city/remote preference); **个人简介** (3–5 lines, no 我);
  **专业技能** (grouped, relevance-ordered; skill-level words obey
  the ladder rule); **工作经历** (reverse-chronological; per role
  `**岗位 — 公司** | 日期` plus 3–6 bullets); **项目经历** (a full,
  prominent section — Chinese tech resumes weight projects heavily;
  per project: 背景 → 职责与动作 → 成果); **教育背景**; **证书**.

### LinkedIn drafts (only on request)

- Headline options: 2–3 variants, each ≤ 220 characters, each a
  genuinely different positioning angle. About draft: first person,
  ≤ 2,600 characters (aim 1,200–2,000), recruiter-searchable terms
  woven into real sentences, never stuffed. Skills to pin: up to 5.
  Everything derives from master.md only; the user applies changes to
  LinkedIn manually.
