#!/usr/bin/env python3
# /// script
# dependencies = ["pyyaml"]
# ///
"""Render the career decision timeline tree: dist/career-tree.html.

The sensemaking twin of build_dashboard.py: the dashboard answers "what's
the state now"; this page answers "what shape does the journey have" —
past decisions and outcomes on the left, an amber NOW rule, and the map's
future branches with dated, falsifiable checkpoints fanning right. Solid
ink is RECORD (events.csv, git re-score commits, scored checkpoints);
dashed ink is CLAIM (due-dated predictions). Opened at the monthly
re-score and at /crossroads sessions; regenerated on demand, never live.

    uv run build_career_tree.py            # -> dist/career-tree.html
    uv run build_career_tree.py --open     # build and open it

Sources (all read-only; this is a derived, throwaway VIEW):
    - data/career-map.yaml   paths, stances, seeded markers, checkpoints
    - data/events.csv        past record: decision rows + rows for app ids
                             the map itself cites; the rest becomes a
                             weekly density ribbon (texture, not stations)
    - git log --grep career-map:   the scoring history rail; if git is
                             unavailable the rail says "history not read"
                             rather than rendering a falsely empty history
    - data/life-events.yaml  OPTIONAL life trunk, [{date, label, kind}] —
                             the user curates it by hand (judgment work);
                             absent file = a visible masthead note, not an
                             error

Honesty rules (from the map's own header; the drawing must not soften
them): null confidence renders as "p = ?" — ignorance, never 0; an
AI-seeded number carries * and the own-action footnote; a seeded stance
is an OUTLINED chip with the re-scores-since-seed fuse counted from git;
ambiguous is as loud as right/wrong; past-due unscored gets the amber
"DUE — UNSCORED" halo (the audit's warn state, kept visible); tombstones
keep their final tally; undated checkpoints get a lane note (drawn
nowhere on the axis — an undated prediction is not a prediction).

Time axis: the default view is SEGMENTED (zone widths follow mark
density; every break prints its px/day gauge — declared distortion). The
"true linear" toggle re-renders the same marks on a strictly linear
date scale in a horizontal scroller: the honest ruler is one click away.

Lane + hue assignment is stable across regenerations: paths sort by
(earliest checkpoint due, id) and take categorical slots in that order.
The slot list deliberately SKIPS green and red so a path's identity can
never be misread as a score (good/critical are reserved for outcomes).
"""

import argparse
import csv
import datetime as dt
import html
import math
import re
import subprocess
import sys
import webbrowser
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit(
        "PyYAML is required: run with `uv run build_career_tree.py` "
        "(PEP 723 header resolves it) or `pip install pyyaml`."
    )

ROOT = Path(__file__).resolve().parent
MAP = ROOT / "data" / "career-map.yaml"
EVENTS = ROOT / "data" / "events.csv"
LIFE = ROOT / "data" / "life-events.yaml"
OUT = ROOT / "dist" / "career-tree.html"

# Categorical slots minus green + red (reserved for scored outcomes);
# fixed order, validated light+dark (dataviz validator, 2026-07-12).
PATH_HUES = [
    ("blue", "#2a78d6", "#3987e5"),
    ("aqua", "#1baf7a", "#199e70"),
    ("violet", "#4a3aa7", "#9085e9"),
    ("magenta", "#e87ba4", "#d55181"),
    ("orange", "#eb6834", "#d95926"),
    ("yellow", "#eda100", "#c98500"),
]
STATUS = {"right": "#0ca30c", "wrong": "#d03b3b", "ambiguous": "#fab219"}
GLYPH = {"right": "✓", "wrong": "✗", "ambiguous": "≈"}
RIBBON_LIGHT = ["#b7d3f6", "#5598e7", "#1c5cab"]
RIBBON_DARK = ["#184f95", "#256abf", "#5598e7"]
STALE_RAIL_DAYS = 45
LANE_CAP = 6


def load_map():
    data = yaml.safe_load(MAP.read_text(encoding="utf-8")) or {}
    raw = MAP.read_text(encoding="utf-8")
    cited_ids = set(re.findall(r"app ids? (\d+)(?:\s*(?:and|\+)\s*(\d+))?", raw))
    ids = {i for pair in cited_ids for i in pair if i}
    paths = []
    for row in data.get("paths") or []:
        cps = []
        for cp in row.get("checkpoints") or []:
            if not isinstance(cp, dict):
                continue
            due = cp.get("due")
            if isinstance(due, dt.datetime):
                due = due.date()
            cps.append(
                {
                    "id": cp.get("id") or "?",
                    "claim": str(cp.get("claim") or "").strip(),
                    "due": due if isinstance(due, dt.date) else None,
                    "confidence": cp.get("confidence"),
                    "scored": (cp.get("scored") or "").strip() or None,
                    "kill_if": str(cp.get("kill_if") or ""),
                    "boost_if": str(cp.get("boost_if") or ""),
                }
            )
        seeded = str(row.get("seeded") or "").strip()
        m = re.search(r"(\d{4}-\d{2}-\d{2})", seeded)
        paths.append(
            {
                "id": row.get("id") or "?",
                "name": row.get("name") or row.get("id") or "?",
                "stance": row.get("stance") or "?",
                "seeded": seeded or None,
                "seed_date": dt.date.fromisoformat(m.group(1)) if m else None,
                "checkpoints": cps,
                "frame": str(row.get("frame") or "").strip(),
            }
        )
    order_key = lambda p: (  # noqa: E731 — stable lane/hue rule (docstring)
        min((c["due"] for c in p["checkpoints"] if c["due"]), default=dt.date.max),
        p["id"],
    )
    paths.sort(key=order_key)
    return paths, ids


def load_events(cited_ids):
    record, weekly = [], {}
    if not EVENTS.exists():
        return record, weekly
    with EVENTS.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                date = dt.date.fromisoformat(row["date"].strip())
            except (ValueError, KeyError):
                continue
            event = (row.get("event") or "").strip()
            if event == "decision" or (row.get("app_id", "").strip() in cited_ids):
                record.append(
                    {"date": date, "event": event, "notes": (row.get("notes") or "")[:220]}
                )
            else:
                week = date - dt.timedelta(days=date.weekday())
                weekly[week] = weekly.get(week, 0) + 1
    return record, weekly


def load_git():
    try:
        out = subprocess.run(
            ["git", "log", "--reverse", "--date=short", "--format=%ad|%s", "--grep", "career-map:"],
            cwd=ROOT, capture_output=True, text=True, timeout=10, check=True,
        ).stdout
    except Exception:
        return None
    commits = []
    for line in out.splitlines():
        date_s, _, subject = line.partition("|")
        try:
            commits.append({"date": dt.date.fromisoformat(date_s), "subject": subject})
        except ValueError:
            continue
    return commits


def load_life():
    if not LIFE.exists():
        return None
    rows = yaml.safe_load(LIFE.read_text(encoding="utf-8")) or []
    events = []
    for r in rows:
        if isinstance(r, dict) and r.get("date") and r.get("label"):
            d = r["date"]
            if isinstance(d, dt.datetime):
                d = d.date()
            if isinstance(d, dt.date):
                events.append({"date": d, "label": str(r["label"]), "kind": str(r.get("kind", ""))})
    return sorted(events, key=lambda e: e["date"]) or None


class Axis:
    """Segmented (default) + linear x-scales over the same marks."""

    def __init__(self, dates, today):
        lo = min(dates + [today]) - dt.timedelta(days=7)
        hi = max(dates + [today]) + dt.timedelta(days=30)
        cuts = [lo, today, min(today + dt.timedelta(days=120), hi)]
        cuts = sorted(set(c for c in cuts if lo <= c <= hi)) + [hi]
        self.zones = []
        x = 60.0
        for a, b in zip(cuts, cuts[1:]):
            n = sum(1 for d in dates if a <= d < b)
            width = max(150.0, min(520.0, 110.0 + 62.0 * math.sqrt(n + 1)))
            days = max((b - a).days, 1)
            self.zones.append({"a": a, "b": b, "x": x, "w": width, "ppd": width / days})
            x += width
        self.width = x + 40
        self.lo, self.hi, self.today = lo, hi, today
        self.lin_ppd = max(2.2, min(5.0, 1100.0 / max((hi - lo).days, 1)))
        self.lin_width = 60 + (hi - lo).days * self.lin_ppd + 40

    def seg(self, d):
        for z in self.zones:
            if z["a"] <= d <= z["b"]:
                return z["x"] + (d - z["a"]).days * z["ppd"]
        return 60.0 if d < self.lo else self.width - 40

    def lin(self, d):
        return 60 + (d - self.lo).days * self.lin_ppd


def esc(s):
    return html.escape(str(s), quote=True)


def month_ticks(axis, linear):
    ticks, d = [], dt.date(axis.lo.year, axis.lo.month, 1)
    while d <= axis.hi:
        x = axis.lin(d) if linear else axis.seg(d)
        if axis.lo <= d:
            ticks.append((x, d.strftime("%b %Y" if d.month == 1 or not ticks else "%b")))
        d = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    kept = []  # declutter; a year label evicts a crowding plain month
    for x, label in ticks:  # rather than being dropped itself
        year = label[-1].isdigit()
        gap = 52 if (kept and kept[-1][1][-1].isdigit()) else 30
        if kept and x - kept[-1][0] < gap:
            if year and not kept[-1][1][-1].isdigit():
                kept.pop()
            else:
                continue
        if not kept or x - kept[-1][0] >= gap:
            kept.append((x, label))
    return kept


def lane_label(name):
    if len(name) <= 46:
        return name
    return name[:46].rsplit(" ", 1)[0] + " …"


def default_word(kill_if):
    m = re.search(r"default (parked|killed)", kill_if)
    return m.group(1) if m else None


def rescores_since(commits, seed_date):
    if commits is None or seed_date is None:
        return None
    return sum(
        1 for c in commits if c["date"] > seed_date and "re-score" in c["subject"]
    )


def render_view(paths, record, weekly, commits, life, axis, today, linear):
    X = axis.lin if linear else axis.seg
    width = axis.lin_width if linear else axis.width
    lanes_y, lane_h, y = [], 92, 118
    for _ in paths:
        lanes_y.append(y)
        y += lane_h
    rail_y = y + 8
    ribbon_y = rail_y + 34
    axis_y = ribbon_y + 22
    height = axis_y + 46
    s = [
        f'<svg viewBox="0 0 {width:.0f} {height}" width="{width:.0f}" height="{height}" '
        f'role="img" aria-label="career decision timeline">'
    ]
    # month grid + axis
    for x, label in month_ticks(axis, linear):
        s.append(f'<line x1="{x:.1f}" y1="70" x2="{x:.1f}" y2="{axis_y}" class="grid"/>')
        s.append(f'<text x="{x + 3:.1f}" y="{axis_y + 16}" class="tick">{esc(label)}</text>')
    s.append(f'<line x1="40" y1="{axis_y}" x2="{width - 20:.0f}" y2="{axis_y}" class="baseline"/>')
    # zone break gauges (segmented only — declared distortion)
    if not linear:
        for z in axis.zones[1:]:
            s.append(
                f'<line x1="{z["x"]:.1f}" y1="70" x2="{z["x"]:.1f}" y2="{axis_y}" class="zonecut"/>'
            )
        for z in axis.zones:
            s.append(
                f'<text x="{z["x"] + 4:.1f}" y="80" class="gauge">1d ≈ {z["ppd"]:.1f}px</text>'
            )
    # life trunk marks (if curated)
    if life:
        for ev in life:
            x = X(ev["date"])
            s.append(f'<circle cx="{x:.1f}" cy="{rail_y - 14}" r="4" class="lifedot"/>')
            s.append(
                f'<text x="{x:.1f}" y="{rail_y - 22}" class="lifelabel">{esc(ev["label"][:26])}</text>'
            )
    # path lanes
    for i, p in enumerate(paths):
        hue = PATH_HUES[i % len(PATH_HUES)][0]
        ly = lanes_y[i]
        dues = [c["due"] for c in p["checkpoints"] if c["due"]]
        start = min([p["seed_date"]] + dues) if (p["seed_date"] or dues) else today
        end = max(dues, default=today)
        x0, x1, xn = X(start), X(end) + 26, X(today)
        parked = p["stance"] in ("parked", "killed")
        cls = f"spine-{hue}" + (" spine-mute" if parked else "")
        w = 3.5 if p["stance"] == "pursuing" else 2
        if start < today:
            s.append(
                f'<line x1="{x0:.1f}" y1="{ly}" x2="{min(xn, x1):.1f}" y2="{ly}" '
                f'class="{cls}" stroke-width="{w}"/>'
            )
        if end > today or x1 > xn:
            s.append(
                f'<line x1="{max(xn, x0):.1f}" y1="{ly}" x2="{x1:.1f}" y2="{ly}" '
                f'class="{cls} claim" stroke-width="{w}"/>'
            )
        if p["seed_date"]:  # riser: record lane -> spine at seed date
            xs = X(p["seed_date"])
            s.append(f'<line x1="{xs:.1f}" y1="{rail_y - 6}" x2="{xs:.1f}" y2="{ly}" class="riser"/>')
        # lane head (chip drawn in HTML layer; here the lane label)
        s.append(f'<text x="8" y="{ly - 26}" class="lanename">{esc(lane_label(p["name"]))}</text>')
        nearest = min(
            (c for c in p["checkpoints"] if c["due"] and not c["scored"] and c["due"] >= today),
            key=lambda c: c["due"], default=None,
        )
        for c in p["checkpoints"]:
            if not c["due"]:
                continue
            x = X(c["due"])
            past_due = c["due"] < today and not c["scored"]
            if c["scored"]:
                col = STATUS[c["scored"]]
                s.append(f'<circle cx="{x:.1f}" cy="{ly}" r="7" fill="{col}" class="node"/>')
                s.append(
                    f'<text x="{x:.1f}" y="{ly - 14}" class="scorechip" fill="{col}">'
                    f"{GLYPH[c['scored']]} {c['scored']}</text>"
                )
            else:
                if past_due:
                    s.append(f'<circle cx="{x:.1f}" cy="{ly}" r="12" class="halo"/>')
                    s.append(
                        f'<text x="{x:.1f}" y="{ly - 26}" class="duewarn">DUE — UNSCORED</text>'
                    )
                s.append(f'<circle cx="{x:.1f}" cy="{ly}" r="7" class="node hollow node-{hue}"/>')
            conf = c["confidence"]
            gate = str(c["id"]).endswith("-gate")
            p_txt = "p = ?" if conf is None else f"p={conf:g}" + ("*" if gate else "")
            s.append(f'<text x="{x:.1f}" y="{ly + 22}" class="cpid">{esc(c["id"])}</text>')
            s.append(
                f'<text x="{x:.1f}" y="{ly + 36}" class="cpdue">{c["due"]} · '
                f'<tspan class="{"pnull" if conf is None else "pnum"}">{esc(p_txt)}</tspan></text>'
            )
            if nearest is c:
                word = default_word(c["kill_if"])
                if word:
                    s.append(
                        f'<text x="{x:.1f}" y="{ly + 50}" class="stake">miss → {word}</text>'
                    )
            s.append(
                f'<rect x="{x - 12:.1f}" y="{ly - 12}" width="24" height="24" class="hit" '
                f'data-tip="{esc(c["id"])} · due {c["due"]} · {esc(p_txt)}&#10;{esc(c["claim"][:400])}"/>'
            )
        undated = [c["id"] for c in p["checkpoints"] if not c["due"] and not c["scored"]]
        if undated:
            s.append(
                f'<text x="{x1 + 10:.1f}" y="{ly + 4}" class="duewarn">'
                f"{len(undated)} undated claim(s) — not drawn (not a prediction; audit warns)</text>"
            )
    # record rail: events + git squares
    s.append(f'<text x="8" y="{rail_y - 12}" class="lanename">MAP RECORD</text>')
    s.append(f'<line x1="40" y1="{rail_y}" x2="{X(today):.1f}" y2="{rail_y}" class="rail"/>')
    for ev in record:
        x = X(ev["date"])
        s.append(
            f'<circle cx="{x:.1f}" cy="{rail_y}" r="5" class="recdot"/>'
            f'<rect x="{x - 9:.1f}" y="{rail_y - 9}" width="18" height="18" class="hit" '
            f'data-tip="{ev["date"]} · {esc(ev["event"])}&#10;{esc(ev["notes"])}"/>'
        )
    if commits is None:
        s.append(f'<text x="46" y="{rail_y + 20}" class="duewarn">git history not read</text>')
    else:
        for c in commits:
            x = X(c["date"])
            s.append(
                f'<rect x="{x - 4:.1f}" y="{rail_y + 8}" width="8" height="8" class="gitsq" '
                f'data-tip="{c["date"]} · {esc(c["subject"][:160])}"/>'
            )
        last = max((c["date"] for c in commits), default=None)
        if last and (today - last).days > STALE_RAIL_DAYS:
            s.append(
                f'<text x="{X(last) + 10:.1f}" y="{rail_y + 20}" class="duewarn">'
                f"⟨ no re-score for {(today - last).days}d ⟩</text>"
            )
    # weekly density ribbon
    if weekly:
        top = max(weekly.values())
        for week, n in weekly.items():
            if week < axis.lo or week > axis.hi:
                continue
            step = 0 if n <= top / 3 else (1 if n <= 2 * top / 3 else 2)
            x0, x1 = X(week), X(week + dt.timedelta(days=6))
            s.append(
                f'<rect x="{x0:.1f}" y="{ribbon_y}" width="{max(x1 - x0, 3):.1f}" height="8" '
                f'class="rib rib{step}" data-tip="week of {week}: {n} tracker events"/>'
            )
        s.append(
            f'<text x="8" y="{ribbon_y + 8}" class="tick">tracker churn</text>'
        )
    # NOW rule on top
    xn = X(today)
    s.append(f'<line x1="{xn:.1f}" y1="56" x2="{xn:.1f}" y2="{axis_y}" class="now"/>')
    s.append(
        f'<rect x="{xn - 52:.1f}" y="40" width="104" height="18" rx="3" class="nowtab"/>'
        f'<text x="{xn:.1f}" y="53" class="nowtxt">NOW · {today}</text>'
    )
    s.append("</svg>")
    return "".join(s)


def stance_chip(p, commits):
    seeded = p["seeded"] is not None
    n = rescores_since(commits, p["seed_date"])
    fuse = (
        f" · re-scores since seed: {n}/2 · the owner confirms or clears"
        if seeded and n is not None
        else (" · fuse uncounted (git history not read)" if seeded else "")
    )
    cls = "chip seeded" if seeded else "chip"
    label = p["stance"].upper() + (
        f" — seeded {p['seed_date']}" if seeded and p["seed_date"] else ""
    )
    return f'<span class="{cls}">{esc(label)}{esc(fuse)}</span>'


def build(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--open", action="store_true", help="open the page after building")
    args = ap.parse_args(argv)

    today = dt.date.today()
    paths, cited_ids = load_map()
    if len(paths) > len(PATH_HUES):
        print(f"note: {len(paths)} paths > {len(PATH_HUES)} hue slots; extras reuse slots")
    record, weekly = load_events(cited_ids)
    commits = load_git()
    life = load_life()

    dates = [c["due"] for p in paths for c in p["checkpoints"] if c["due"]]
    dates += [e["date"] for e in record]
    if commits:
        dates += [c["date"] for c in commits]
    if life:
        dates += [e["date"] for e in life]
    if not dates:
        sys.exit("nothing to draw: no dated marks found in the map or the tracker")
    axis = Axis(dates, today)

    world_scored = sum(
        1
        for p in paths
        for c in p["checkpoints"]
        if c["scored"] and not str(c["id"]).endswith("-gate")
    )
    calib = (
        f"calibration: n/a — {world_scored} scored world-facing claims"
        if world_scored == 0
        else f"calibration: {world_scored} scored world-facing claims — read it at /crossroads"
    )
    open_slots = max(0, LANE_CAP - len([p for p in paths if p["stance"] != "killed"]))
    life_note = (
        "" if life else
        '<span class="mut">life trunk: data/life-events.yaml not present — curate it (your '
        "judgment work) to extend the timeline left</span>"
    )

    seg = render_view(paths, record, weekly, commits, life, axis, today, linear=False)
    lin = render_view(paths, record, weekly, commits, life, axis, today, linear=True)

    ledger = ['<table class="ledger"><thead><tr><th>path</th><th>stance</th>'
              "<th>checkpoint</th><th>due</th><th>p</th><th>scored</th><th>miss default</th></tr></thead><tbody>"]
    for i, p in enumerate(paths):
        hue_l, hue_d = PATH_HUES[i % len(PATH_HUES)][1], PATH_HUES[i % len(PATH_HUES)][2]
        for j, c in enumerate(p["checkpoints"]):
            conf = c["confidence"]
            gate = str(c["id"]).endswith("-gate")
            p_txt = "?" if conf is None else f"{conf:g}" + ("*" if gate else "")
            ledger.append(
                "<tr>"
                + (
                    f'<td rowspan="{len(p["checkpoints"])}"><span class="dot" '
                    f'style="--dl:{hue_l};--dd:{hue_d}"></span>{esc(p["id"])}</td>'
                    f'<td rowspan="{len(p["checkpoints"])}">{stance_chip(p, commits)}</td>'
                    if j == 0
                    else ""
                )
                + f"<td>{esc(c['id'])}</td><td>{c['due'] or '<em>undated</em>'}</td>"
                f"<td>{esc(p_txt)}</td><td>{esc(c['scored'] or 'pending')}</td>"
                f"<td>{esc(default_word(c['kill_if']) or '—')}</td></tr>"
            )
    ledger.append("</tbody></table>")

    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Career tree — decision timeline</title>
<style>
:root {{ --surface:#fcfcfb; --page:#f9f9f7; --ink:#0b0b0b; --sec:#52514e;
  --mut:#898781; --grid:#e1e0d9; --base:#c3c2b7; --amber:#ffc233;
  --navy:#101f3c; --good:#0ca30c; --warn:#fab219; --crit:#d03b3b;
  --blue:#2a78d6; --aqua:#1baf7a; --violet:#4a3aa7; --magenta:#e87ba4;
  --orange:#eb6834; --yellow:#eda100;
  --rib0:{RIBBON_LIGHT[0]}; --rib1:{RIBBON_LIGHT[1]}; --rib2:{RIBBON_LIGHT[2]}; }}
@media (prefers-color-scheme: dark) {{ :root {{ --surface:#1a1a19; --page:#0d0d0d;
  --ink:#ffffff; --sec:#c3c2b7; --mut:#898781; --grid:#2c2c2a; --base:#383835;
  --blue:#3987e5; --aqua:#199e70; --violet:#9085e9; --magenta:#d55181;
  --orange:#d95926; --yellow:#c98500;
  --rib0:{RIBBON_DARK[0]}; --rib1:{RIBBON_DARK[1]}; --rib2:{RIBBON_DARK[2]}; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--page); color:var(--ink);
  font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; }}
.masthead {{ background:var(--navy); color:#fff; padding:14px 22px; }}
.masthead h1 {{ margin:0; font-size:17px; letter-spacing:.06em; }}
.masthead h1 b {{ color:var(--amber); }}
.masthead .sub {{ color:#c9d4ea; font-size:12px; margin-top:4px; }}
.wrap {{ max-width:1280px; margin:14px auto; padding:0 16px; }}
.card {{ background:var(--surface); border:1px solid var(--grid); border-radius:8px;
  padding:14px; margin-bottom:14px; }}
.scroller {{ overflow-x:auto; }}
.grid {{ stroke:var(--grid); stroke-width:1; }}
.baseline {{ stroke:var(--base); stroke-width:1.5; }}
.zonecut {{ stroke:var(--base); stroke-dasharray:2 4; }}
.gauge,.tick {{ fill:var(--mut); font-size:10px; }}
.lanename {{ fill:var(--sec); font-size:11px; font-weight:600; letter-spacing:.04em; }}
.lifelabel {{ fill:var(--sec); font-size:10px; text-anchor:middle; }}
.lifedot {{ fill:var(--ink); }}
.spine-blue{{stroke:var(--blue)}} .spine-aqua{{stroke:var(--aqua)}}
.spine-violet{{stroke:var(--violet)}} .spine-magenta{{stroke:var(--magenta)}}
.spine-orange{{stroke:var(--orange)}} .spine-yellow{{stroke:var(--yellow)}}
.spine-mute {{ stroke:var(--mut) !important; opacity:.6; }}
.claim {{ stroke-dasharray:7 5; }}
.riser {{ stroke:var(--base); stroke-dasharray:2 3; }}
.node {{ stroke:var(--surface); stroke-width:2; }}
.node.hollow {{ fill:var(--surface); stroke-width:2.5; }}
.node-blue{{stroke:var(--blue)}} .node-aqua{{stroke:var(--aqua)}}
.node-violet{{stroke:var(--violet)}} .node-magenta{{stroke:var(--magenta)}}
.node-orange{{stroke:var(--orange)}} .node-yellow{{stroke:var(--yellow)}}
.halo {{ fill:none; stroke:var(--warn); stroke-width:2; opacity:.85; }}
.scorechip {{ font-size:11px; font-weight:700; text-anchor:middle; }}
.cpid {{ fill:var(--ink); font-size:11px; font-weight:600; text-anchor:middle; }}
.cpdue {{ fill:var(--sec); font-size:10.5px; text-anchor:middle; }}
.pnull {{ fill:var(--mut); font-style:italic; }}
.pnum {{ font-family:ui-monospace,monospace; }}
.stake {{ fill:var(--crit); font-size:10px; text-anchor:middle; }}
.duewarn {{ fill:var(--warn); font-size:10px; font-weight:700; text-anchor:middle; }}
.rail {{ stroke:var(--base); stroke-width:2; }}
.recdot {{ fill:var(--ink); }}
.gitsq {{ fill:var(--mut); }}
.rib {{ opacity:.9 }} .rib0{{fill:var(--rib0)}} .rib1{{fill:var(--rib1)}} .rib2{{fill:var(--rib2)}}
.now {{ stroke:var(--amber); stroke-width:2.5; }}
.nowtab {{ fill:var(--navy); }}
.nowtxt {{ fill:var(--amber); font-size:11px; font-weight:700; text-anchor:middle; }}
.hit {{ fill:transparent; cursor:help; }}
.chip {{ display:inline-block; border-radius:4px; padding:2px 8px; font-size:11px;
  font-weight:700; background:var(--ink); color:var(--surface); }}
.chip.seeded {{ background:transparent; color:var(--ink);
  border:1.5px dashed var(--warn); font-weight:600; }}
.controls {{ display:flex; gap:10px; align-items:center; margin-bottom:8px;
  flex-wrap:wrap; font-size:12px; color:var(--sec); }}
button {{ font:inherit; background:var(--surface); color:var(--ink);
  border:1px solid var(--base); border-radius:5px; padding:4px 12px; cursor:pointer; }}
button[aria-pressed="true"] {{ background:var(--navy); color:#fff; border-color:var(--navy); }}
.ledger {{ border-collapse:collapse; width:100%; font-size:12.5px; }}
.ledger th,.ledger td {{ text-align:left; padding:6px 10px;
  border-bottom:1px solid var(--grid); vertical-align:top; }}
.ledger th {{ color:var(--mut); font-weight:600; }}
.dot {{ display:inline-block; width:10px; height:10px; border-radius:50%;
  background:var(--dl); margin-right:6px; }}
@media (prefers-color-scheme: dark) {{ .dot {{ background:var(--dd); }} }}
.legend {{ font-size:12px; color:var(--sec); display:flex; gap:18px; flex-wrap:wrap; }}
.mut {{ color:var(--mut); }}
#tip {{ position:fixed; display:none; max-width:380px; background:var(--ink);
  color:var(--surface); padding:8px 10px; border-radius:6px; font-size:12px;
  white-space:pre-wrap; z-index:9; pointer-events:none; }}
footer {{ color:var(--mut); font-size:11.5px; padding:6px 22px 20px; }}
</style></head><body>
<div class="masthead"><h1>CAREER TREE <b>· DECISION TIMELINE</b></h1>
<div class="sub">generated {today} · sources: data/career-map.yaml + data/events.csv +
git history · {esc(calib)} · {open_slots} of ~{LANE_CAP} lane slots open — /crossroads
diverges them · PRIVATE (stances &amp; forecasts) · read-only view {life_note}</div></div>
<div class="wrap">
<div class="card"><div class="controls">
<button id="segbtn" aria-pressed="true">focus view</button>
<button id="linbtn" aria-pressed="false">true linear</button>
<span>focus view widens dense zones (each break prints its px/day gauge);
true linear is the honest ruler — same marks, real distances.</span></div>
<div class="scroller" id="segview">{seg}</div>
<div class="scroller" id="linview" style="display:none">{lin}</div></div>
<div class="card"><div class="legend">
<span>— solid = record</span><span>––– dashed = claim (future)</span>
<span>◯ pending · <b style="color:var(--good)">✓ right</b> ·
<b style="color:var(--crit)">✗ wrong</b> ·
<b style="color:var(--warn)">≈ ambiguous</b> (glyph + word, never colour alone)</span>
<span>p = ? — no cited base rate yet (ignorance, not zero)</span>
<span>p=…* — own-action intention-as-odds, excluded from calibration</span>
<span>▤ ribbon = weekly tracker churn</span>
<span>■ squares = career-map commits (scoring history)</span></div></div>
<div class="card">{''.join(ledger)}</div>
</div>
<div id="tip"></div>
<footer>regenerate: uv run build_career_tree.py [--open] · opened at the monthly re-score
and /crossroads · never writes back · rules live in data/career-map.yaml's header;
rules live in data/career-map.yaml's header</footer>
<script>
const tip = document.getElementById('tip');
document.querySelectorAll('.hit,.gitsq,.rib').forEach(el => {{
  el.addEventListener('mousemove', e => {{
    const t = el.getAttribute('data-tip'); if (!t) return;
    tip.textContent = t; tip.style.display = 'block';
    tip.style.left = Math.min(e.clientX + 14, innerWidth - 400) + 'px';
    tip.style.top = (e.clientY + 14) + 'px';
  }});
  el.addEventListener('mouseleave', () => tip.style.display = 'none');
}});
const seg = document.getElementById('segview'), lin = document.getElementById('linview');
const sb = document.getElementById('segbtn'), lb = document.getElementById('linbtn');
function show(linear) {{
  seg.style.display = linear ? 'none' : '';
  lin.style.display = linear ? '' : 'none';
  sb.setAttribute('aria-pressed', String(!linear));
  lb.setAttribute('aria-pressed', String(linear));
}}
sb.onclick = () => show(false); lb.onclick = () => show(true);
</script>
</body></html>"""

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(page) // 1024} KB)")
    if args.open:
        webbrowser.open(OUT.as_uri())


if __name__ == "__main__":
    build()
