#!/usr/bin/env python3
"""Render resume Markdown (base/ or tailored/) into the Apple-restrained
HTML design (render/resume.css). Step 4 of the pipeline: the output is
opened in a browser and printed to PDF; one-page trimming stays a human
decision, guided by the tailored *_notes.md cut-first list.

Usage:
    python3 build_resumes.py <resume.md> [more.md ...]
                             [--density balanced|airy|compact]
                             [--out-dir dist]
    python3 build_resumes.py <resume.md> --watch [--port 7788]

--watch takes exactly one file: it serves the rendered HTML on
localhost, rebuilds whenever the Markdown or CSS changes, reloads the
browser tab automatically, and overlays a live page-count badge and
page-break guide (screen only — never printed, never in normal builds).

Input contract (the resume-style skill's format rules):
    # Name                              -> h1
    first paragraph after the name      -> contact line (| becomes ·)
    ## Section                          -> h2
    **Title[ — Org]** [extra] | right   -> h3 with right-aligned date/meta
    - **Label:** items                  -> inline skills row (Skills/专业技能)
    - bullet                            -> li
    anything else                       -> p

No third-party dependencies; standard Markdown subset only (no tables,
no HTML, no images — same constraints the skill imposes on authors).
"""

import argparse
import html
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
CSS_FILE = ROOT / "render" / "resume.css"
DENSITIES = ("balanced", "airy", "compact")
INLINE_SECTIONS = {"skills", "专业技能"}

LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
ITALIC_RE = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")

# Printable content height: A4 (297mm) minus the @page 16mm top+bottom
# margins in render/resume.css. CSS mm are exact on screen too, and the
# print content width matches the screen sheet, so line breaks agree.
PAGE_MM = 265

WATCH_JS = """
<script>
(function () {
  var MM = 96 / 25.4, PAGE_MM = %d;
  var style = document.createElement('style');
  style.textContent = '@media print { .watch-guide { display: none !important; } }';
  document.head.appendChild(style);
  function paint() {
    var main = document.querySelector('main');
    var cs = getComputedStyle(main);
    var padTop = parseFloat(cs.paddingTop);
    var mm = (main.scrollHeight - padTop - parseFloat(cs.paddingBottom)) / MM;
    var pages = Math.max(1, Math.ceil(mm / PAGE_MM));
    document.querySelectorAll('.watch-guide').forEach(function (e) { e.remove(); });
    var badge = document.createElement('div');
    badge.className = 'watch-guide';
    badge.textContent = pages === 1
      ? '1 page \\u00b7 ' + Math.floor(PAGE_MM - mm) + 'mm spare'
      : pages + ' pages \\u00b7 over by ' + Math.ceil(mm - PAGE_MM) + 'mm';
    badge.style.cssText = 'position:fixed;top:10px;right:10px;z-index:9;' +
      'padding:6px 10px;font:12px -apple-system,sans-serif;color:#fff;' +
      'border-radius:6px;background:' + (pages === 1 ? '#1a7f37' : '#c62828');
    document.body.appendChild(badge);
    main.style.position = 'relative';
    for (var i = 1; i * PAGE_MM < mm; i++) {
      var line = document.createElement('div');
      line.className = 'watch-guide';
      line.style.cssText = 'position:absolute;left:0;right:0;top:' +
        (padTop + i * PAGE_MM * MM) + 'px;border-top:1px dashed #c62828;';
      var tag = document.createElement('span');
      tag.textContent = 'page ' + i + ' ends';
      tag.style.cssText = 'position:absolute;right:0;top:-16px;' +
        'font:10px -apple-system,sans-serif;color:#c62828;';
      line.appendChild(tag);
      main.appendChild(line);
    }
  }
  window.addEventListener('load', paint);
  var id = document.body.getAttribute('data-build');
  setInterval(function () {
    fetch(location.href, { cache: 'no-store' })
      .then(function (r) { return r.text(); })
      .then(function (t) {
        var m = t.match(/data-build="([^"]+)"/);
        if (m && m[1] !== id) location.reload();
      })
      .catch(function () {});
  }, 700);
})();
</script>
""" % PAGE_MM


class BuildError(Exception):
    pass


def inline(text):
    """Escape, then render the inline Markdown subset (links, bold, italic)."""
    out = html.escape(text, quote=False)
    out = LINK_RE.sub(r'<a href="\2">\1</a>', out)
    out = BOLD_RE.sub(r"<strong>\1</strong>", out)
    out = ITALIC_RE.sub(r"<em>\1</em>", out)
    return out


def is_h3(line):
    """Entry-title lines carry a `|` date slot or are bold end to end;
    a paragraph that merely opens with bold is neither."""
    return line.startswith("**") and ("|" in line or line.rstrip().endswith("**"))


def h3_line(line):
    """A title line becomes the design's flex h3: title on the left (org
    after the em dash rendered as .meta), everything after the first `|`
    joined into the right-aligned .date span."""
    m = re.match(r"\*\*(.+?)\*\*\s*(.*)", line)
    bold, rest = m.group(1), m.group(2)
    right = ""
    parts = re.split(r"\s*\|\s*", rest)
    if len(parts) > 1:
        rest = parts[0]
        right = " · ".join(p for p in parts[1:] if p)

    dash = re.split(r"\s*—\s*", bold, maxsplit=1)
    if len(dash) == 2:
        title = f'{inline(dash[0])} — <span class="meta">{inline(dash[1])}</span>'
    else:
        title = inline(bold)
    if rest.strip():
        title += f' <span class="meta">{inline(rest.strip())}</span>'

    right_html = f'<span class="date">{inline(right)}</span>' if right else ""
    return f"    <h3>\n      <span>{title}</span>\n      {right_html}\n    </h3>"


def skill_li(line):
    """`- **Label:** items` / `- **Label：**items` / `- **Label** — items`
    -> inline skills row; the CN fullwidth colon is kept as the joiner."""
    m = re.match(r"\*\*(.+?)\*\*\s*(?:—\s*)?(.*)", line)
    label, items = m.group(1), m.group(2)
    joiner = "：" if label.endswith("：") else " — "
    label = label.rstrip(":：")
    return (
        f'      <li><span class="label">{inline(label)}</span>'
        f"{joiner}{inline(items)}</li>"
    )


def render(md_text):
    lines = md_text.splitlines()
    body = []
    name = ""
    section = ""
    ul_open = None  # None | "plain" | "inline"

    def close_ul():
        nonlocal ul_open
        if ul_open:
            body.append("    </ul>")
            ul_open = None

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("# ") and not name:
            name = line[2:].strip()
            body.append(f"    <h1>{inline(name)}</h1>")
            continue
        if line.startswith("## "):
            close_ul()
            section = line[3:].strip()
            body.append(f"    <h2>{inline(section)}</h2>")
            continue
        if is_h3(line):
            close_ul()
            body.append(h3_line(line))
            continue
        if line.startswith("- "):
            item = line[2:].strip()
            inline_skill = section.lower() in INLINE_SECTIONS and item.startswith("**")
            want = "inline" if inline_skill else "plain"
            if ul_open != want:
                close_ul()
                body.append('    <ul class="inline">' if want == "inline" else "    <ul>")
                ul_open = want
            body.append(skill_li(item) if want == "inline" else f"      <li>{inline(item)}</li>")
            continue
        # paragraph — the first one after the h1 is the contact line
        close_ul()
        if body and body[-1].startswith("    <h1>"):
            contact = " · ".join(s.strip() for s in line.split(" | "))
            body.append(f"    <p>{inline(contact)}</p>")
        else:
            body.append(f"    <p>{inline(line)}</p>")

    close_ul()
    return name, "\n".join(body)


def build(md_path, css, density, out_dir, build_id=None):
    md_text = md_path.read_text(encoding="utf-8")
    if "[VERIFY" in md_text and "tailored/" in str(md_path):
        raise BuildError(
            f"{md_path}: contains [VERIFY] tags — tailored files must be submission-clean."
        )
    name, body = render(md_text)
    title = f"{name} — Resume" if name else md_path.stem
    body_attrs = f'class="density-{density}"'
    if build_id:
        body_attrs += f' data-build="{build_id}"'
    watch_js = WATCH_JS if build_id else ""
    lang = "zh-CN" if re.search(r"[一-鿿]", md_text) else "en"
    doc = f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
{css}
  </style>
</head>
<body {body_attrs}>
  <main>
{body}
  </main>
{watch_js}</body>
</html>
"""
    out = out_dir / (md_path.stem + ".html")
    out.write_text(doc, encoding="utf-8")
    return out


def print_pdf(html_path):
    """Render the built HTML to PDF with headless Chrome — the @page CSS
    (A4, 16mm/22mm margins) is honored exactly, with no print-dialog
    variables (margin preset, scale, header/footer stamps). Returns
    (pdf_path, page_count); page count is read from the PDF itself, so it
    is the truth the watch badge only estimates."""
    import shutil
    import subprocess

    candidates = [
        os.environ.get("CHROME_BIN"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
    ]
    chrome = next((c for c in candidates if c and Path(c).exists()), None)
    if not chrome:
        raise BuildError(
            "no Chrome/Chromium found (set CHROME_BIN). Fallback: print from the "
            "browser dialog with Margins: Default, Scale: 100, Headers and footers: OFF."
        )
    pdf = html_path.with_suffix(".pdf")
    subprocess.run(
        [chrome, "--headless", "--disable-gpu",
         f"--print-to-pdf={pdf}", "--no-pdf-header-footer", html_path.as_uri()],
        check=True, capture_output=True, timeout=120,
    )
    pages = len(re.findall(rb"/Type\s*/Page\b(?!s)", pdf.read_bytes()))
    return pdf, pages


def watch(md_path, density, out_dir, port):
    import functools
    import http.server
    import threading
    import time
    import webbrowser

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    def stamp():
        try:
            return str(max(md_path.stat().st_mtime_ns, CSS_FILE.stat().st_mtime_ns))
        except FileNotFoundError:  # editor mid-save (atomic replace)
            return None

    def rebuild(build_id):
        try:
            build(md_path, CSS_FILE.read_text(encoding="utf-8"), density, out_dir, build_id)
            return True
        except (BuildError, FileNotFoundError) as e:
            print(f"build error (fix and save again): {e}")
            return False

    last = stamp()
    rebuild(last)
    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", port), functools.partial(Quiet, directory=str(out_dir))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/{md_path.stem}.html"
    print(f"watching {md_path} + {CSS_FILE}")
    print(f"preview:  {url}   (Ctrl-C to stop)")
    webbrowser.open(url)
    try:
        while True:
            time.sleep(0.4)
            cur = stamp()
            if cur and cur != last:
                last = cur
                if rebuild(cur):
                    print(f"rebuilt {time.strftime('%H:%M:%S')}")
    except KeyboardInterrupt:
        print("\nstopped")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="+", type=Path, help="resume .md files to render")
    ap.add_argument("--density", choices=DENSITIES, default="balanced")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "dist")
    ap.add_argument("--watch", action="store_true", help="live preview one file")
    ap.add_argument("--port", type=int, default=7788)
    ap.add_argument(
        "--pdf", action="store_true",
        help="also print each build to PDF via headless Chrome (@page CSS honored "
             "exactly — no print-dialog variables) and report the true page count",
    )
    args = ap.parse_args()

    for f in args.files:
        if not f.is_file():
            sys.exit(f"not a file: {f}")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    if args.watch:
        if len(args.files) != 1:
            sys.exit("--watch takes exactly one file")
        watch(args.files[0], args.density, args.out_dir, args.port)
        return

    css = CSS_FILE.read_text(encoding="utf-8")
    for f in args.files:
        try:
            out = build(f, css, args.density, args.out_dir)
            print(f"{f} -> {out}")
            if args.pdf:
                pdf, pages = print_pdf(out)
                tag = "OK" if pages == 1 else f"OVER — trim per the notes cut-first list"
                print(f"  -> {pdf}  [{pages} page{'s' if pages != 1 else ''}: {tag}]")
        except BuildError as e:
            sys.exit(str(e))


if __name__ == "__main__":
    main()
