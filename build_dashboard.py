#!/usr/bin/env python3
"""Render the JD tracker (data/applications.csv + data/events.csv) into a
single self-contained dashboard: dist/dashboard.html.

The CSVs stay the line-diffable source of truth (see CLAUDE.md); this is a
derived, throwaway VIEW.

    python3 build_dashboard.py                 # -> dist/dashboard.html (static snapshot)
    python3 build_dashboard.py --open          # build the file and open it
    python3 build_dashboard.py --serve         # LIVE: re-reads the CSVs on every load,
                                               #       auto-reloads the tab when a CSV changes
    python3 build_dashboard.py --serve --port 7789

Two modes for two needs. The default writes a self-contained
dist/dashboard.html — shareable, works offline, but a snapshot (stale until
you rebuild). --serve runs a tiny localhost server that re-renders straight
from the data files on every request and pushes a reload whenever
applications.csv, events.csv or career-map.yaml changes on disk: start it
once, leave the tab open, never rerun. Mirrors build_resumes.py --watch.

What it shows
    - The DEPARTURES BOARD (hero): actionable rows sorted by nearest deadline,
      with the deadline date lifted out of next_action / notes
    - The CAREER STRIP (under the board): the next PENDING dated checkpoint of
      every non-killed path in data/career-map.yaml — overdue critical, due
      within 14 days warning, parked muted. Scored checkpoints are history and
      never shown. Exists because dated commitments living outside the tracker
      CSVs were invisible on the daily surfaces (a re-dated due was missed
      2026-07-15 and found only by hand-scan). Fails soft: a missing or
      drifted file omits the strip, never breaks the tracker view.
    - KPI strip: total logged, applied, ready-to-act, awaiting-info, closed
    - A pipeline funnel (logged -> pursue -> tailored -> applied -> reply+)
    - Per-tier counts
    - The full application table: search, filter by status-bucket + tier,
      sort any column, click a row to expand strengths / gaps / next action
    - A recent-events timeline from events.csv

Data colours follow the validated data-viz palette (status hues for
application state, an ordinal blue ramp for tiers/funnel); identity chrome is
a transit-signage pair (navy #101f3c + amber #ffc233) on the board only. The
page is theme-aware (light/dark; the board stays dark in both, like a real
board) and needs no network — inline CSS/JS only, no third-party dependencies.
"""

import argparse
import csv
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
APPS_CSV = DATA / "applications.csv"
EVENTS_CSV = DATA / "events.csv"
CAREER_YAML = DATA / "career-map.yaml"

DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
# A date in notes is only a DEADLINE when a deadline word precedes it — this
# keeps genuine "apply by / closes / deadline" dates while ignoring the many
# non-deadline dates in notes (the "(recruiter 2026-07-01)" strategist tag,
# "posted …", "Applied …"), which must never masquerade as a due date.
NOTES_DEADLINE_RE = re.compile(
    r"(?:deadline|apply by|apply before|clos\w*|window clos\w*|submit by|due|by)"
    r"\s*~?\s*(20\d{2}-\d{2}-\d{2})",
    re.I,
)
# resume_version is a real tailored artifact only when it names a file/date;
# bare track labels like "AI Engineer EN" are just the planned base, not a file.
REAL_RESUME_RE = re.compile(r"\.md|20\d\d")

# --- status -> bucket -------------------------------------------------------
# Every free-text status collapses into one of these buckets; the bucket
# drives colour, grouping, and which rows land in the action queue.
BUCKETS = {
    "applied": {"label": "Applied", "hue": "blue"},
    "act": {"label": "Ready to act", "hue": "good"},
    "info": {"label": "Awaiting info", "hue": "warning"},
    "blocked": {"label": "Blocked", "hue": "serious"},
    "hold": {"label": "On hold", "hue": "violet"},
    "skip": {"label": "Skipped", "hue": "muted"},
    "closed": {"label": "Closed", "hue": "critical"},
}
# Buckets whose rows are things the user can move forward right now.
ACTIONABLE = {"act", "info"}


def bucket_of(status):
    s = (status or "").strip().lower()
    if s.startswith("applied"):
        return "applied"
    if s in ("rejected", "offer", "withdrawn", "closed") or s.startswith("reject"):
        return "closed"
    if s.startswith("skip"):
        return "skip"
    if s.startswith("hold"):
        return "hold"
    if s.startswith(("verify", "decision", "queued")):
        return "info"
    if s.startswith("blocked"):
        return "blocked"
    if s.startswith(("to tailor", "tailored", "new")):
        return "act"
    return "info"  # unknown -> treat as needing a look


def read_apps():
    with APPS_CSV.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_events():
    with EVENTS_CSV.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def data_stamp():
    """A version token for the data — the newest mtime of any rendered file.
    The live page polls this so it reloads the instant a data file changes."""
    stamps = []
    for f in (APPS_CSV, EVENTS_CSV, CAREER_YAML):
        try:
            stamps.append(f.stat().st_mtime_ns)
        except FileNotFoundError:
            pass
    return str(max(stamps, default=0))


# Injected only in --serve mode: poll the lightweight /_stamp route and reload
# the tab when the tracker CSVs change on disk. (Static builds never include it.)
LIVE_JS = """
<script>
(function(){
  var id=document.body.getAttribute('data-build');
  var badge=document.createElement('div');
  badge.textContent='live';
  badge.style.cssText='position:fixed;bottom:12px;right:12px;z-index:9;padding:4px 10px;'+
    'font:600 10px ui-monospace,Menlo,monospace;letter-spacing:.12em;text-transform:uppercase;'+
    'color:#ffc233;border-radius:6px;background:#101f3c;border:1px solid #233863;opacity:.92;';
  window.addEventListener('load',function(){document.body.appendChild(badge);});
  setInterval(function(){
    fetch('/_stamp',{cache:'no-store'}).then(function(r){return r.text();}).then(function(t){
      if(t&&t.trim()!==id) location.reload();
    }).catch(function(){});
  },1200);
})();
</script>
"""


def find_deadline(row):
    """The real due date, or ''. next_action is where /daily records the next
    concrete step, so any date there is genuine. notes is scanned only for a
    date introduced by a deadline word, so strategist tags like
    "(recruiter 2026-07-01)" never get mistaken for a deadline."""
    m = DATE_RE.search(row.get("next_action", "") or "")
    if m:
        return m.group(1)
    m = NOTES_DEADLINE_RE.search(row.get("notes", "") or "")
    if m:
        return m.group(1)
    return ""


def esc(s):
    return html.escape(str(s or ""), quote=True)


def build_rows(apps, events):
    """One normalised dict per application, ready to embed as JSON."""
    # last event per app -> a compact activity string for the row
    last_event = {}
    for e in events:
        last_event[e["app_id"]] = (e["date"], e["event"])
    rows = []
    for a in apps:
        b = bucket_of(a["status"])
        try:
            score = int(a["match_score"])
        except (ValueError, KeyError):
            score = 0
        try:
            tier = int(a["target_tier"])
        except (ValueError, KeyError):
            tier = 0
        le = last_event.get(a["id"])
        rows.append(
            {
                "id": a["id"],
                "company": a["company"],
                "role": a["role_title"],
                "tier": tier,
                "score": score,
                "status": a["status"],
                "bucket": b,
                "bucketLabel": BUCKETS[b]["label"],
                "location": a["location_tz"],
                "salary": a.get("salary", ""),
                "deadline": find_deadline(a),
                "nextAction": a["next_action"],
                "strengths": a["strengths"],
                "gaps": a["must_have_gaps"],
                "resume": a.get("resume_version", ""),
                "jd": a["jd_link"],
                "notes": a["notes"],
                "lastEvent": f"{le[1]} · {le[0]}" if le else "",
            }
        )
    return rows


def funnel(rows, events):
    total = len(rows)
    # A row counts as "pursuing" if it isn't skipped/held/closed.
    pursue = sum(1 for r in rows if r["bucket"] in ("act", "info", "applied"))
    tailored_ids = {e["app_id"] for e in events if e["event"] in ("tailored", "applied")}
    tailored_ids |= {r["id"] for r in rows if REAL_RESUME_RE.search(r["resume"])}
    tailored = len(tailored_ids)
    applied_ids = {e["app_id"] for e in events if e["event"] == "applied"}
    applied = len(applied_ids)
    reply_ids = {
        e["app_id"] for e in events if e["event"] in ("reply", "screen", "interview")
    }
    reply = len(reply_ids)
    return [
        ("Logged", total),
        ("Pursuing", pursue),
        ("Tailored", tailored),
        ("Applied", applied),
        ("Reply+", reply),
    ]


def kpis(rows):
    def n(*buckets):
        return sum(1 for r in rows if r["bucket"] in buckets)

    return [
        ("Total logged", len(rows), "muted"),
        ("Applied", n("applied"), "blue"),
        ("Ready to act", n("act"), "good"),
        ("Awaiting info", n("info"), "warning"),
        ("On hold / skip", n("hold", "skip"), "violet"),
        ("Closed", n("closed"), "critical"),
    ]


def tier_counts(rows):
    counts = {}
    for r in rows:
        counts[r["tier"]] = counts.get(r["tier"], 0) + 1
    return [(t, counts.get(t, 0)) for t in sorted(counts)]


# --- career strip (data/career-map.yaml) ------------------------------------

CAREER_KEY_RE = re.compile(r"(name|stance|due|scored):\s*(.*)$")


def read_career_paths():
    """Extract the strip's fields from data/career-map.yaml without PyYAML:
    paths[].id / name / stance and each checkpoint's id / due / scored.
    Deliberately NOT a YAML parser — it reads only the line shapes those
    fields actually use (scalar `key: value`, plus the folded `name: >-`)
    and ignores every line it doesn't recognise, so a drifted file degrades
    to missing fields instead of a crash (render fails soft on the rest)."""
    paths = []
    path = None
    cp = None
    folding_name = False
    for raw in CAREER_YAML.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if folding_name:
            if indent >= 6 and not stripped.startswith("- "):
                path["name"] = f"{path['name']} {stripped}".strip()
                continue
            folding_name = False
        if indent == 2 and stripped.startswith("- id:"):
            path = {"id": stripped[5:].strip(), "name": "", "stance": "", "checkpoints": []}
            paths.append(path)
            cp = None
            continue
        if path is None:
            continue
        if indent > 2 and stripped.startswith("- id:"):
            cp = {"id": stripped[5:].strip(), "due": "", "scored": ""}
            path["checkpoints"].append(cp)
            continue
        m = CAREER_KEY_RE.match(stripped)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if key == "name" and cp is None:
            folding_name = val in (">", ">-", ">+", "|", "|-")
            path["name"] = "" if folding_name else val
        elif key == "stance" and cp is None:
            path["stance"] = val
        elif key in ("due", "scored") and cp is not None:
            cp[key] = val
    return paths


def career_strip_html(paths, today):
    """One cell per non-killed path: its stance and NEXT pending dated
    checkpoint (earliest empty-`scored` due). Scored checkpoints are
    history — showing them as due would be exactly the false positive the
    map's header warns about. Overdue = critical, due within 14 days =
    warning, otherwise neutral; parked paths sit muted at the end with
    their single reopen checkpoint."""
    items = []
    for p in paths:
        stance = p["stance"].split()[0] if p["stance"] else ""
        if stance == "killed":
            continue
        pending = sorted(
            (c for c in p["checkpoints"] if not c["scored"] and c["due"]),
            key=lambda c: c["due"],
        )
        nxt = pending[0] if pending else None
        items.append((stance == "parked", nxt["due"] if nxt else "9999-99-99", p, stance, nxt))
    if not items:
        return ""
    items.sort(key=lambda it: (it[0], it[1], it[2]["id"]))
    cells = []
    for parked, _, p, stance, nxt in items:
        days = None
        if nxt:
            try:
                days = (dt.date.fromisoformat(nxt["due"]) - today).days
            except ValueError:  # malformed due -> undated, never a crash
                pass
        if parked:
            cls, accent = " parked", "var(--muted)"
        elif days is not None and days < 0:
            cls, accent = " overdue", "var(--critical)"
        elif days is not None and days <= 14:
            cls, accent = " soon", "var(--warning)"
        else:
            cls, accent = "", "var(--ink2)"
        if nxt:
            due_main = nxt["due"]
            due_sub = (
                "no date" if days is None
                else f"{-days}d overdue" if days < 0
                else "today" if days == 0
                else f"in {days}d"
            )
            cp_id = nxt["id"]
        else:
            due_main, due_sub, cp_id = "—", "nothing pending", "—"
        cells.append(
            f'<div class="pc{cls}" style="--accent:{accent}" title="{esc(p["name"] or p["id"])}">'
            f'<div class="ph"><span class="pid">{esc(p["id"])}</span>'
            f'<span class="pst">{esc(stance or "?")}</span></div>'
            f'<div class="pdue tabnum">{esc(due_main)} <small>{esc(due_sub)}</small></div>'
            f'<div class="pcp">{esc(cp_id)}</div>'
            f"</div>"
        )
    return (
        '<section aria-label="Career map checkpoints">'
        '<p class="ccap">Career map · next pending checkpoint per path · data/career-map.yaml</p>'
        f'<div class="career">{"".join(cells)}</div></section>'
    )


# --- HTML assembly ----------------------------------------------------------

CSS = """
:root {
  --plane:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e;
  --muted:#898781; --grid:#e1e0d9; --line:#c3c2b7; --ring:rgba(11,11,11,.10);
  --blue:#2a78d6; --good:#0ca30c; --warning:#c98500; --serious:#c85a2a;
  --violet:#4a3aa7; --critical:#d03b3b; --aqua:#1baf7a;
  --t1:#184f95; --t2:#256abf; --t3:#3987e5; --t4:#86b6ef;
  --t1ink:#fff; --t2ink:#fff; --t3ink:#fff; --t4ink:#0d366b;
  --f1:#86b6ef; --f2:#5598e7; --f3:#2a78d6; --f4:#1c5cab; --f5:#104281;
  --disp:"Avenir Next Condensed",Futura,"Arial Narrow","Segoe UI",system-ui,sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    --plane:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7;
    --muted:#898781; --grid:#2c2c2a; --line:#383835; --ring:rgba(255,255,255,.10);
    --blue:#3987e5; --good:#0ca30c; --warning:#fab219; --serious:#ec835a;
    --violet:#9085e9; --critical:#e66767; --aqua:#199e70;
    --t1:#256abf; --t2:#3987e5; --t3:#5598e7; --t4:#86b6ef;
    --t1ink:#fff; --t2ink:#fff; --t3ink:#0d366b; --t4ink:#0d366b;
    --f1:#9ec5f4; --f2:#6da7ec; --f3:#3987e5; --f4:#256abf; --f5:#184f95;
  }
}
* { box-sizing:border-box; }
body {
  margin:0; background:var(--plane); color:var(--ink);
  font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;
  -webkit-font-smoothing:antialiased;
}
main { max-width:1180px; margin:0 auto; padding:30px 20px 64px; }
.eyebrow { font-family:var(--mono); font-size:11px; font-weight:600;
  letter-spacing:.14em; text-transform:uppercase; color:var(--muted);
  margin:0 0 8px; }
h1 { font-family:var(--disp); font-size:34px; font-weight:600; line-height:1;
  letter-spacing:.05em; text-transform:uppercase; margin:0 0 8px; }
h2 { font-family:var(--disp); font-size:15px; text-transform:uppercase;
  letter-spacing:.16em; color:var(--muted); margin:38px 0 12px; font-weight:600; }
.sub { color:var(--ink2); font-size:13.5px; margin:0 0 4px; }
a { color:var(--blue); text-decoration:none; }
a:hover { text-decoration:underline; }
.tabnum { font-variant-numeric:tabular-nums; }
:focus-visible { outline:2px solid var(--blue); outline-offset:2px; }
@media (prefers-reduced-motion: reduce) { * { transition:none !important; } }

/* departures board — the action queue. Signage-dark in BOTH themes, like a
   real board; every colour here is board-scoped and mode-invariant. */
.board { --bd:#101f3c; --bd-edge:#233863; --bd-ink:#f2f5fc; --bd-dim:#8fa0c4;
  --bd-soft:#b6c3e0; --bd-amber:#ffc233; --bd-good:#35c53f; --bd-warning:#fab219;
  --bd-soon:#ec835a; --bd-over:#ff7b6e;
  background:var(--bd); border-radius:12px; color:var(--bd-ink);
  box-shadow:inset 0 0 0 1px var(--bd-edge); overflow:hidden; margin-top:24px; }
.board-top { display:flex; flex-wrap:wrap; gap:4px 16px;
  justify-content:space-between; align-items:baseline;
  padding:13px 18px 11px; border-bottom:1px solid var(--bd-edge); }
.board-top .bt { font-family:var(--disp); font-size:16px; font-weight:600;
  letter-spacing:.22em; text-transform:uppercase; color:var(--bd-amber); }
.board-top .bs { font-family:var(--mono); font-size:10.5px; letter-spacing:.1em;
  text-transform:uppercase; color:var(--bd-dim); }
.bhead, .brow { display:grid; grid-template-columns:112px 1fr 168px 44px;
  gap:4px 16px; padding:10px 18px; align-items:baseline; }
.bhead { font-family:var(--mono); font-size:10px; font-weight:600;
  letter-spacing:.12em; text-transform:uppercase; color:var(--bd-dim);
  padding:9px 18px 7px; border-bottom:1px solid var(--bd-edge); }
.brow { border-top:1px solid rgba(143,160,196,.14); }
.brow:first-of-type { border-top:0; }
.brow .due { font-family:var(--mono); font-size:13px; font-weight:600;
  color:var(--bd-amber); }
.brow .due small { display:block; font-size:10.5px; font-weight:400;
  color:var(--bd-dim); margin-top:3px; }
.brow.soon .due small { color:var(--bd-soon); }
.brow.overdue .due, .brow.overdue .due small { color:var(--bd-over); }
.brow .co { font-weight:650; font-size:14.5px; }
.brow .ro { color:var(--bd-soft); font-size:12.5px; }
.brow .act { color:var(--bd-dim); font-size:12.5px; margin-top:3px; }
.brow .st { font-family:var(--mono); font-size:10.5px; font-weight:600;
  letter-spacing:.08em; text-transform:uppercase; line-height:1.5; }
.brow .tc { font-family:var(--mono); font-size:11px; font-weight:700;
  color:var(--bd-soft); border:1px solid var(--bd-edge); border-radius:4px;
  padding:2px 6px; }
.board .empty { color:var(--bd-dim); }
@media (max-width:680px) {
  .bhead { display:none; }
  .brow { grid-template-columns:96px 1fr; }
  .brow .st { grid-column:2; }
  .brow .tc { display:none; }
}

/* career strip — the next pending dated checkpoint of every non-killed
   life path (data/career-map.yaml). State rides --accent: overdue
   critical, due <=14d warning, neutral ink2, parked muted. */
.ccap { font-family:var(--mono); font-size:10.5px; font-weight:600;
  letter-spacing:.12em; text-transform:uppercase; color:var(--muted);
  margin:22px 0 8px; }
.career { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:1px; background:var(--grid); border:1px solid var(--ring);
  border-radius:10px; overflow:hidden; }
.career .pc { background:var(--surface); padding:9px 12px 10px;
  border-top:3px solid var(--accent); }
.career .ph { display:flex; justify-content:space-between; gap:8px;
  align-items:baseline; }
.career .pid { font-family:var(--mono); font-size:11.5px; font-weight:700;
  overflow-wrap:anywhere; }
.career .pst { font-family:var(--mono); font-size:9.5px; font-weight:600;
  letter-spacing:.08em; text-transform:uppercase; color:var(--muted); }
.career .pdue { font-family:var(--mono); font-size:12px; font-weight:600;
  color:var(--accent); margin-top:6px; }
.career .pdue small { font-weight:400; color:var(--muted); }
.career .pc.overdue .pdue small, .career .pc.soon .pdue small {
  color:var(--accent); }
.career .pcp { font-size:11.5px; color:var(--ink2); margin-top:2px;
  overflow-wrap:anywhere; }
.career .pc.parked .pid, .career .pc.parked .pcp { color:var(--muted); }

/* KPI strip — one quiet ledger row, hairline-separated */
.strip { display:grid; grid-template-columns:repeat(6,1fr); gap:1px;
  background:var(--grid); border:1px solid var(--ring); border-radius:10px;
  overflow:hidden; margin-top:22px; }
.cell { background:var(--surface); padding:14px 16px; }
.cell .v { font-family:var(--disp); font-size:30px; font-weight:600;
  line-height:1; letter-spacing:.02em; font-variant-numeric:tabular-nums; }
.cell .k { font-size:12px; color:var(--ink2); margin-top:7px;
  display:flex; align-items:center; gap:6px; }
.cell .k::before { content:""; width:7px; height:7px; border-radius:2px;
  background:var(--accent); flex:none; }
@media (max-width:820px){ .strip{grid-template-columns:repeat(3,1fr);} }
@media (max-width:520px){ .strip{grid-template-columns:repeat(2,1fr);} }

/* funnel + tiers, side by side */
.cols { display:grid; gap:20px; grid-template-columns:1.4fr 1fr; align-items:start; }
@media (max-width:820px){ .cols{grid-template-columns:1fr;} }
.card { background:var(--surface); border:1px solid var(--ring);
        border-radius:10px; padding:16px 18px; }
.funnel-row { display:grid; grid-template-columns:96px 1fr 40px; align-items:center;
  gap:10px; margin:9px 0; }
.funnel-row .lab { font-size:13px; color:var(--ink2); }
.funnel-row .bar { height:18px; border-radius:0 4px 4px 0; background:var(--barcol);
  min-width:3px; transition:width .3s; }
.funnel-row .cnt { text-align:right; font-family:var(--mono); font-size:12.5px;
  font-weight:600; font-variant-numeric:tabular-nums; }
.tier-row { display:grid; grid-template-columns:70px 1fr 32px; align-items:center;
  gap:10px; margin:8px 0; }
.tier-row .chip { font-family:var(--mono); font-size:11.5px; font-weight:600;
  color:#fff; border-radius:4px; padding:2px 0; text-align:center; }
.tier-row .bar { height:14px; border-radius:0 4px 4px 0; }
.tier-row .cnt { text-align:right; font-family:var(--mono); font-size:12.5px;
  font-variant-numeric:tabular-nums; }

/* badges */
.badge { display:inline-block; font-size:11.5px; font-weight:600; padding:2px 8px;
  border-radius:5px; white-space:nowrap;
  background:color-mix(in srgb,var(--accent) 16%,transparent); color:var(--accent);
  border:1px solid color-mix(in srgb,var(--accent) 30%,transparent); }

/* filters */
.filters { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-bottom:12px; }
.filters input[type=search] {
  flex:1 1 200px; min-width:160px; background:var(--surface); color:var(--ink);
  border:1px solid var(--ring); border-radius:8px; padding:8px 11px; font-size:14px; }
.fbtn { font:inherit; font-size:12.5px; padding:5px 11px; border-radius:6px;
  cursor:pointer; border:1px solid var(--ring); background:var(--surface);
  color:var(--ink2); user-select:none; }
.fbtn.on { background:var(--ink); color:var(--plane); border-color:var(--ink); }

/* table */
table { width:100%; border-collapse:collapse; font-size:13.5px; }
thead th { text-align:left; color:var(--muted); font-weight:600;
  font-family:var(--mono); font-size:10.5px; text-transform:uppercase;
  letter-spacing:.1em; padding:8px 10px;
  border-bottom:1px solid var(--line); cursor:pointer; white-space:nowrap; }
thead th.num, td.num { text-align:right; font-variant-numeric:tabular-nums; }
thead th .ar { color:var(--blue); }
tbody td { padding:9px 10px; border-bottom:1px solid var(--grid); vertical-align:top; }
tbody tr.main { cursor:pointer; }
tbody tr.main:hover { background:color-mix(in srgb,var(--blue) 6%,transparent); }
.co-cell { font-weight:600; }
.ro-cell { color:var(--ink2); font-size:12.5px; }
.tchip { display:inline-block; width:24px; text-align:center; color:#fff;
  border-radius:4px; font-family:var(--mono); font-size:11px; font-weight:700;
  padding:1px 0; }
.scorebar { display:inline-flex; align-items:center; gap:7px; }
.scorebar .track { width:52px; height:6px; border-radius:3px; background:var(--grid); }
.scorebar .fill { height:6px; border-radius:3px; background:var(--blue); }
.detail td { background:color-mix(in srgb,var(--blue) 3.5%,transparent);
  border-bottom:1px solid var(--line); }
.detail dl { margin:0; display:grid; grid-template-columns:auto 1fr; gap:4px 14px; }
.detail dt { color:var(--muted); font-size:11.5px; text-transform:uppercase;
  letter-spacing:.04em; white-space:nowrap; padding-top:2px; }
.detail dd { margin:0; color:var(--ink2); font-size:13px; }
.hidden { display:none; }
.empty { color:var(--muted); padding:22px; text-align:center; }

/* timeline */
.tl { list-style:none; margin:0; padding:0; }
.tl li { display:grid; grid-template-columns:92px 92px 1fr; gap:12px;
  padding:7px 0; border-bottom:1px solid var(--grid); font-size:13px; }
.tl .d { color:var(--muted); font-family:var(--mono); font-size:12px;
  font-variant-numeric:tabular-nums; }
.tl .ev { font-weight:600; }
.tl .nt { color:var(--ink2); }
.foot { margin-top:40px; color:var(--muted); font-size:12px; text-align:center; }
"""

JS = """
const ROWS = %ROWS%;
const HUES = {applied:'blue',act:'good',info:'warning',blocked:'serious',
  hold:'violet',skip:'muted',closed:'critical'};
const TIERCOL = {1:'var(--t1)',2:'var(--t2)',3:'var(--t3)',4:'var(--t4)',0:'var(--muted)'};
const TIERINK = {1:'var(--t1ink)',2:'var(--t2ink)',3:'var(--t3ink)',4:'var(--t4ink)',0:'#fff'};
const state = { q:'', bucket:'all', tier:'all', sort:'deadline', dir:1, open:new Set() };

function esc(s){ const d=document.createElement('div'); d.textContent=s==null?'':s; return d.innerHTML; }

function daysTo(iso){
  if(!iso) return null;
  const today = new Date(document.body.dataset.today+'T00:00:00');
  return Math.round((new Date(iso+'T00:00:00')-today)/86400000);
}

function matches(r){
  if(state.bucket!=='all' && r.bucket!==state.bucket) return false;
  if(state.tier!=='all' && String(r.tier)!==state.tier) return false;
  if(state.q){
    const hay=(r.company+' '+r.role+' '+r.status+' '+r.location+' '+r.strengths+' '+r.gaps).toLowerCase();
    if(!hay.includes(state.q)) return false;
  }
  return true;
}

function sortRows(rows){
  const k=state.sort, d=state.dir;
  return rows.slice().sort((a,b)=>{
    let x=a[k], y=b[k];
    if(k==='deadline'){ x=x||'9999'; y=y||'9999'; }
    if(k==='company'||k==='role'||k==='status'){ x=(''+x).toLowerCase(); y=(''+y).toLowerCase(); }
    return x<y?-d:x>y?d:0;
  });
}

function badge(r){
  return `<span class="badge" style="--accent:var(--${HUES[r.bucket]})">${esc(r.status)}</span>`;
}

function renderTable(){
  const rows=sortRows(ROWS.filter(matches));
  const body=document.getElementById('tbody');
  document.getElementById('shown').textContent=rows.length;
  if(!rows.length){ body.innerHTML='<tr><td colspan="6" class="empty">No applications match these filters.</td></tr>'; return; }
  let h='';
  for(const r of rows){
    const dd=daysTo(r.deadline);
    const due = r.deadline ? `<span class="tabnum" style="color:${dd!=null&&dd<0?'var(--critical)':dd!=null&&dd<=7?'var(--serious)':'var(--ink2)'}">${r.deadline}</span>` : '<span style="color:var(--muted)">—</span>';
    h+=`<tr class="main" data-id="${r.id}">
      <td class="num tabnum">${r.id}</td>
      <td><div class="co-cell">${esc(r.company)}</div><div class="ro-cell">${esc(r.role)}</div></td>
      <td class="num"><span class="tchip" style="background:${TIERCOL[r.tier]};color:${TIERINK[r.tier]}">${r.tier||'–'}</span></td>
      <td class="num"><span class="scorebar"><span class="track"><span class="fill" style="width:${r.score}%"></span></span><span class="tabnum">${r.score}</span></span></td>
      <td>${badge(r)}</td>
      <td>${due}</td></tr>`;
    if(state.open.has(r.id)){
      h+=`<tr class="detail"><td colspan="6"><dl>
        <dt>Next action</dt><dd>${esc(r.nextAction)||'—'}</dd>
        <dt>Strengths</dt><dd>${esc(r.strengths)}</dd>
        <dt>Gaps</dt><dd>${esc(r.gaps)}</dd>
        <dt>Location</dt><dd>${esc(r.location)}</dd>
        <dt>Salary</dt><dd>${esc(r.salary)||'not stated'}</dd>
        <dt>Last event</dt><dd>${esc(r.lastEvent)||'—'}</dd>
        ${r.resume?`<dt>Resume</dt><dd>${esc(r.resume)}</dd>`:''}
        <dt>JD</dt><dd><a href="${esc(r.jd)}" target="_blank" rel="noopener">${esc(r.jd)}</a></dd>
        <dt>Notes</dt><dd>${esc(r.notes)}</dd>
      </dl></td></tr>`;
    }
  }
  body.innerHTML=h;
  body.querySelectorAll('tr.main').forEach(tr=>tr.onclick=()=>{
    const id=tr.dataset.id;
    state.open.has(id)?state.open.delete(id):state.open.add(id);
    renderTable();
  });
}

function initFilters(){
  document.getElementById('search').oninput=e=>{ state.q=e.target.value.trim().toLowerCase(); renderTable(); };
  document.querySelectorAll('.fbtn').forEach(b=>b.onclick=()=>{
    const g=b.dataset.group;
    document.querySelectorAll(`.fbtn[data-group="${g}"]`).forEach(x=>x.classList.remove('on'));
    b.classList.add('on');
    state[g]=b.dataset.val;
    renderTable();
  });
  document.querySelectorAll('thead th[data-k]').forEach(th=>th.onclick=()=>{
    const k=th.dataset.k;
    if(state.sort===k) state.dir*=-1; else { state.sort=k; state.dir=(k==='score')?-1:1; }
    document.querySelectorAll('thead th .ar').forEach(a=>a.textContent='');
    th.querySelector('.ar').textContent = state.dir>0?' ▲':' ▼';
    renderTable();
  });
}
initFilters();
renderTable();
"""


def render(rows, apps, events, today, live=False):
    total = len(rows)
    applied = sum(1 for r in rows if r["bucket"] == "applied")

    # KPI strip
    tiles = "".join(
        f'<div class="cell" style="--accent:var(--{hue})">'
        f'<div class="v">{v}</div><div class="k">{esc(k)}</div></div>'
        for k, v, hue in kpis(rows)
    )

    # Funnel — one ordinal blue ramp, light->dark with pipeline depth; the
    # --f* vars carry mode-specific steps (100-step gaps, validator-passing)
    fdata = funnel(rows, events)
    fmax = max((v for _, v in fdata), default=1) or 1
    fcolors = ["var(--f1)", "var(--f2)", "var(--f3)", "var(--f4)", "var(--f5)"]
    frows = "".join(
        f'<div class="funnel-row"><span class="lab">{esc(lab)}</span>'
        f'<span class="bar" style="width:{max(3, round(v / fmax * 100))}%;--barcol:{fcolors[i % len(fcolors)]}"></span>'
        f'<span class="cnt tabnum">{v}</span></div>'
        for i, (lab, v) in enumerate(fdata)
    )

    # Tier breakdown
    tdata = tier_counts(rows)
    tmax = max((v for _, v in tdata), default=1) or 1
    trows = "".join(
        f'<div class="tier-row"><span class="chip" style="background:var(--t{t});color:var(--t{t}ink)">T{t}</span>'
        f'<span class="bar" style="width:{max(3, round(v / tmax * 100))}%;background:var(--t{t})"></span>'
        f'<span class="cnt tabnum">{v}</span></div>'
        for t, v in tdata
        if t
    )

    # Departures board — actionable rows, nearest deadline first, then score.
    # Tier on the board is the "T3" text itself, one quiet colour — an ordinal
    # colour ramp can't keep visible step gaps on the fixed navy, and the
    # number already carries the information.
    q = [r for r in rows if r["bucket"] in ACTIONABLE]

    def qkey(r):
        return (r["deadline"] or "9999-99-99", -r["score"])

    q.sort(key=qkey)
    qitems = []
    for r in q[:12]:
        cls = ""
        if r["deadline"]:
            d = (dt.date.fromisoformat(r["deadline"]) - today).days
            cls = "overdue" if d < 0 else "soon" if d <= 7 else ""
            due_main = r["deadline"]
            due_sub = (
                f"{-d}d overdue" if d < 0 else "today" if d == 0 else f"in {d}d"
            )
        else:
            due_main = "—"
            due_sub = "no date"
        hue = BUCKETS[r["bucket"]]["hue"]  # act->good, info->warning only
        tc = f'<span class="tc">T{r["tier"]}</span>' if r["tier"] else ""
        qitems.append(
            f'<div class="brow {cls}">'
            f'<div class="due">{esc(due_main)}<small>{esc(due_sub)}</small></div>'
            f'<div><span class="co">{esc(r["company"])}</span> '
            f'<span class="ro">— {esc(r["role"])}</span>'
            f'<div class="act">{esc(r["nextAction"])}</div></div>'
            f'<div class="st" style="color:var(--bd-{hue})">{esc(r["status"])}</div>'
            f"<div>{tc}</div>"
            f"</div>"
        )
    queue = (
        "".join(qitems)
        or '<div class="empty">Nothing scheduled — all caught up.</div>'
    )

    # Career strip — dated commitments living OUTSIDE the tracker CSVs
    # (data/career-map.yaml), re-read on every render like the CSVs.
    # Fails soft: a missing or drifted file omits the strip with a
    # comment instead of breaking the tracker view.
    try:
        career = career_strip_html(read_career_paths(), today)
    except Exception as e:
        career = f"<!-- career strip omitted: {esc(e)} -->"

    # Timeline — most recent events first
    ev_sorted = sorted(events, key=lambda e: (e["date"], e["app_id"]), reverse=True)[:16]
    co_by_id = {a["id"]: a["company"] for a in apps}
    tl = "".join(
        f'<li><span class="d">{esc(e["date"])}</span>'
        f'<span class="ev">{esc(e["event"])}</span>'
        f'<span class="nt">#{esc(e["app_id"])} {esc(co_by_id.get(e["app_id"], ""))} — {esc(e["notes"])}</span></li>'
        for e in ev_sorted
    )

    # Filter buttons
    bucket_btns = '<button class="fbtn on" data-group="bucket" data-val="all">All</button>' + "".join(
        f'<button class="fbtn" data-group="bucket" data-val="{b}">{esc(meta["label"])}</button>'
        for b, meta in BUCKETS.items()
    )
    tier_btns = '<button class="fbtn on" data-group="tier" data-val="all">All tiers</button>' + "".join(
        f'<button class="fbtn" data-group="tier" data-val="{t}">T{t}</button>'
        for t, _ in tdata
        if t
    )

    js = JS.replace("%ROWS%", json.dumps(rows, ensure_ascii=False))

    body_attrs = f'data-today="{today.isoformat()}"'
    live_js = ""
    if live:
        body_attrs += f' data-build="{data_stamp()}"'
        live_js = LIVE_JS
    mode_note = "live · re-reads the CSVs" if live else "static snapshot"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Job Search Dashboard</title>
<style>{CSS}</style>
</head>
<body {body_attrs}>
<main>
  <p class="eyebrow">Frontend &rarr; AI Application Engineer / FDE</p>
  <h1>Job Search Dashboard</h1>
  <p class="sub">{total} applications tracked · {applied} applied · as of {today.isoformat()} · {mode_note} from data/applications.csv + data/events.csv</p>

  <section class="board" aria-label="Action queue">
    <div class="board-top">
      <span class="bt">Departures</span>
      <span class="bs">next actions · nearest deadline first</span>
    </div>
    <div class="bhead"><span>Scheduled</span><span>Application · next action</span><span>Status</span><span>T</span></div>
    {queue}
  </section>

  {career}

  <div class="strip">{tiles}</div>

  <div class="cols">
    <section>
      <h2>Pipeline funnel</h2>
      <div class="card">{frows}</div>
    </section>
    <section>
      <h2>By tier</h2>
      <div class="card">{trows}</div>
    </section>
  </div>

  <h2>All applications</h2>
  <div class="filters">
    <input id="search" type="search" placeholder="Search company, role, skills, location…">
  </div>
  <div class="filters">{bucket_btns}</div>
  <div class="filters">{tier_btns}</div>
  <p class="sub"><span id="shown">{total}</span> of {total} shown · click any row for details</p>
  <table>
    <thead><tr>
      <th class="num" data-k="id">#<span class="ar"></span></th>
      <th data-k="company">Company / Role<span class="ar"></span></th>
      <th class="num" data-k="tier">Tier<span class="ar"></span></th>
      <th class="num" data-k="score">Match<span class="ar"></span></th>
      <th data-k="status">Status<span class="ar"></span></th>
      <th data-k="deadline">Deadline<span class="ar">&#9650;</span></th>
    </tr></thead>
    <tbody id="tbody"></tbody>
  </table>

  <h2>Recent activity</h2>
  <ul class="tl">{tl}</ul>

  <p class="foot">Regenerate with <code>python3 build_dashboard.py</code> · applications.csv stays the source of truth</p>
</main>
<script>{js}</script>
{live_js}</body>
</html>
"""


def render_current(live=False):
    """Read the CSVs right now and render the page — the single source both
    the static build and the live server render through, so they can't drift."""
    apps = read_apps()
    events = read_events()
    rows = build_rows(apps, events)
    return render(rows, apps, events, dt.date.today(), live=live), len(rows)


def serve(port):
    """Live mode: a localhost server that re-renders from the CSVs on every
    request. GET /_stamp returns the data version the tab polls for reload."""
    import http.server
    import webbrowser

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, body, ctype="text/html; charset=utf-8"):
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/_stamp":
                self._send(data_stamp(), "text/plain; charset=utf-8")
                return
            if path in ("/", "/dashboard.html", "/index.html"):
                try:
                    html_doc, _ = render_current(live=True)
                except Exception as e:  # keep the server up; surface the error
                    self._send(f"<pre>build error: {html.escape(str(e))}</pre>")
                    return
                self._send(html_doc)
                return
            self.send_error(404)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"live dashboard: {url}")
    print("re-reads the data on every load; the tab reloads on any data-file change.")
    print("Ctrl-C to stop")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", type=Path, default=ROOT / "dist")
    ap.add_argument("--open", action="store_true", help="open the built file in a browser")
    ap.add_argument("--serve", action="store_true", help="live mode: always-fresh local server")
    ap.add_argument("--port", type=int, default=7789, help="port for --serve (default 7789)")
    args = ap.parse_args()

    if not APPS_CSV.is_file():
        sys.exit(f"not found: {APPS_CSV}")

    if args.serve:
        serve(args.port)
        return

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / "dashboard.html"
    html_doc, n = render_current(live=False)
    out.write_text(html_doc, encoding="utf-8")
    print(f"{APPS_CSV.name} + {EVENTS_CSV.name} -> {out}  ({n} applications)")

    if args.open:
        import webbrowser

        webbrowser.open(out.resolve().as_uri())


if __name__ == "__main__":
    main()
