#!/usr/bin/env python3
"""kembarki — read-only duplicate file finder.

Usage: python kembarki.py /path/to/backup [more paths] [-o report.html]
"""

from __future__ import annotations

import argparse, csv, fnmatch, json, os, re, sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from string import Template
from typing import Callable, Iterable, Iterator

__version__ = "0.1.0"


# ---- scanner ----




@dataclass(frozen=True)
class FileEntry:
    name: str
    path: str
    size: int
    mtime: float


@dataclass
class ScanStats:
    files: int = 0
    dirs: int = 0
    errors: int = 0


def _excluded(name: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def scan(
    roots: Iterable[str],
    *,
    exclude: Iterable[str] = (),
    follow_symlinks: bool = False,
    min_size: int = 0,
    stats: ScanStats | None = None,
    on_error: Callable[[str, OSError], None] | None = None,
    progress: Callable[[ScanStats], None] | None = None,
) -> Iterator[FileEntry]:
    """Yield FileEntry for every regular file under each root."""
    exclude = list(exclude)
    stats = stats if stats is not None else ScanStats()
    on_error = on_error or (lambda p, e: print(f"warning: {p}: {e.strerror or e}", file=sys.stderr))
    seen_dirs: set[tuple[int, int]] = set()

    stack = [os.path.abspath(r) for r in roots]
    while stack:
        current = stack.pop()
        try:
            st = os.stat(current, follow_symlinks=follow_symlinks)
            key = (st.st_dev, st.st_ino)
            if key in seen_dirs:  # avoid loops / double-scanning overlapping roots
                continue
            seen_dirs.add(key)
            it = os.scandir(current)
        except OSError as e:
            stats.errors += 1
            on_error(current, e)
            continue
        stats.dirs += 1
        with it:
            for entry in it:
                if _excluded(entry.name, exclude):
                    continue
                try:
                    if entry.is_dir(follow_symlinks=follow_symlinks):
                        stack.append(entry.path)
                    elif entry.is_file(follow_symlinks=follow_symlinks):
                        st = entry.stat(follow_symlinks=follow_symlinks)
                        if st.st_size < min_size:
                            continue
                        stats.files += 1
                        if progress and stats.files % 1000 == 0:
                            progress(stats)
                        yield FileEntry(entry.name, entry.path, st.st_size, st.st_mtime)
                except OSError as e:
                    stats.errors += 1
                    on_error(entry.path, e)


# ---- grouping ----





@dataclass
class DuplicateGroup:
    name: str
    entries: list[FileEntry] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.entries)

    @property
    def same_size(self) -> bool:
        return len({e.size for e in self.entries}) == 1

    @property
    def total_size(self) -> int:
        return sum(e.size for e in self.entries)

    @property
    def wasted(self) -> int:
        """Space reclaimable by keeping only the largest copy."""
        return self.total_size - max(e.size for e in self.entries)


def group_by_name(entries: Iterable[FileEntry], *, ignore_case: bool = False) -> list[DuplicateGroup]:
    buckets: dict[str, list[FileEntry]] = defaultdict(list)
    for e in entries:
        buckets[e.name.casefold() if ignore_case else e.name].append(e)
    groups = [
        DuplicateGroup(name=items[0].name, entries=sorted(items, key=lambda e: e.path))
        for items in buckets.values()
        if len(items) > 1
    ]
    groups.sort(key=lambda g: (-g.wasted, g.name))
    return groups


# ---- report/util ----


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


def fmt_time(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


# ---- report/csv_out ----



def write_csv(groups: list[DuplicateGroup], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8", errors="replace") as f:
        w = csv.writer(f)
        w.writerow(["group", "name", "size_bytes", "modified", "same_size", "path"])
        for i, g in enumerate(groups, 1):
            for e in g.entries:
                w.writerow([i, e.name, e.size, fmt_time(e.mtime), g.same_size, e.path])


# ---- report/json_out ----



def write_json(groups: list[DuplicateGroup], path: str, meta: dict) -> None:
    data = {
        "meta": meta,
        "groups": [
            {
                "name": g.name,
                "count": g.count,
                "same_size": g.same_size,
                "wasted_bytes": g.wasted,
                "instances": [{"path": e.path, "size": e.size, "mtime": e.mtime} for e in g.entries],
            }
            for g in groups
        ],
    }
    with open(path, "w", encoding="utf-8", errors="replace") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---- report/html ----




_PAGE = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>kembarki report</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
/* Bootstrap 5.3-style tokens (light + dark) */
:root {
  color-scheme: light;
  --bs-body-bg:#fff; --bs-body-color:#212529; --bs-secondary-color:rgba(33,37,41,.75);
  --bs-tertiary-bg:#f8f9fa; --bs-border-color:#dee2e6; --bs-primary:#0d6efd; --bs-primary-rgb:13,110,253;
  --bs-success:#198754; --bs-warning-text:#997404; --bs-striped:rgba(0,0,0,.05); --bs-hover:rgba(0,0,0,.075);
  --bs-code:#d63384;
}
* { box-sizing:border-box; }
body { margin:0; font-family:"Inter", system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  font-size:1rem; line-height:1.5; font-weight:400; background:var(--bs-tertiary-bg); color:var(--bs-body-color);
  -webkit-font-smoothing:antialiased; font-feature-settings:"cv11", "ss01"; }
main { max-width:1140px; margin:0 auto; padding:2rem 1rem; }
h1 { font-size:1.75rem; font-weight:600; letter-spacing:-.02em; margin:0 0 .25rem; }
.muted { color:var(--bs-secondary-color); }

/* stat cards */
.stats { display:grid; grid-template-columns:repeat(auto-fit, minmax(170px, 1fr)); gap:1rem; margin:1.5rem 0; }
.stat { background:var(--bs-body-bg); border:1px solid var(--bs-border-color); border-radius:.375rem; padding:1rem 1.25rem;
  box-shadow:0 .125rem .25rem rgba(0,0,0,.075); }
.stat b { display:block; font-size:1.5rem; font-weight:600; font-variant-numeric:tabular-nums; letter-spacing:-.01em; }
.stat span { font-size:.875rem; }

/* toolbar: form-control, btn, btn-group */
.toolbar { display:flex; gap:.75rem; align-items:center; margin:0 0 1rem; flex-wrap:wrap; }
input[type=search] { flex:1; min-width:240px; padding:.375rem .75rem; font:inherit; color:var(--bs-body-color);
  background:var(--bs-body-bg); border:1px solid var(--bs-border-color); border-radius:.375rem;
  transition:border-color .15s, box-shadow .15s; }
input[type=search]:focus { outline:0; border-color:rgba(var(--bs-primary-rgb),.6); box-shadow:0 0 0 .25rem rgba(var(--bs-primary-rgb),.25); }
input[type=checkbox] { width:1em; height:1em; accent-color:var(--bs-primary); vertical-align:-.125em; margin:0 .35rem 0 0; }
select { font:inherit; font-size:.9375rem; padding:.375rem 2.25rem .375rem .75rem; color:var(--bs-body-color); cursor:pointer;
  background:var(--bs-body-bg) url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3e%3cpath fill='none' stroke='%23343a40' stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='m2 5 6 6 6-6'/%3e%3c/svg%3e") no-repeat right .75rem center/16px 12px;
  border:1px solid var(--bs-border-color); border-radius:.375rem; appearance:none; transition:border-color .15s, box-shadow .15s; }
select:focus { outline:0; border-color:rgba(var(--bs-primary-rgb),.6); box-shadow:0 0 0 .25rem rgba(var(--bs-primary-rgb),.25); }
button { font:inherit; font-size:.875rem; font-weight:500; padding:.375rem .75rem; line-height:1.5; cursor:pointer;
  color:var(--bs-body-color); background:var(--bs-body-bg); border:1px solid var(--bs-border-color); border-radius:.375rem;
  transition:background-color .15s, color .15s, border-color .15s; }
button:hover { background:var(--bs-hover); }
button:focus-visible { outline:0; box-shadow:0 0 0 .25rem rgba(var(--bs-primary-rgb),.25); }
.seg { display:inline-flex; }
.seg button { border-radius:0; margin-left:-1px; border-color:var(--bs-primary); color:var(--bs-primary); }
.seg button:first-child { border-radius:.375rem 0 0 .375rem; margin-left:0; }
.seg button:last-child { border-radius:0 .375rem .375rem 0; }
.seg button.on { background:var(--bs-primary); color:#fff; }
.gonly { display:inline-flex; gap:.5rem; }
#shown { font-size:.875rem; margin-left:auto; min-width:10rem; text-align:right; font-variant-numeric:tabular-nums; }

/* status text */
.status { white-space:nowrap; font-size:.875rem; font-weight:500; }
.status.ok { color:var(--bs-success); } .status.warn { color:var(--bs-warning-text); }

/* tables (.table .table-hover) */
table { width:100%; border-collapse:collapse; font-size:.9375rem; }
th, td { text-align:left; padding:.5rem .75rem; border-bottom:1px solid var(--bs-border-color); vertical-align:top; }
thead th { font-weight:600; border-bottom:2px solid currentColor; cursor:pointer; user-select:none; white-space:nowrap; }
thead th:hover { color:var(--bs-primary); }
th[data-dir=asc]::after { content:" ▲"; font-size:.7em; } th[data-dir=desc]::after { content:" ▼"; font-size:.7em; }
tbody tr:hover > td:not([rowspan]) { background:var(--bs-hover); }
td.num { font-variant-numeric:tabular-nums; white-space:nowrap; }
td.path { font-family:SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; font-size:.8125rem; color:var(--bs-code); word-break:break-all; }

/* grouped view: cards (.card / .card-header) */
details { background:var(--bs-body-bg); border:1px solid var(--bs-border-color); border-radius:.375rem; margin-bottom:.75rem; overflow:hidden; }
summary { padding:.75rem 1.25rem; cursor:pointer; display:flex; gap:.75rem; align-items:baseline; flex-wrap:wrap; list-style:none; }
summary::-webkit-details-marker { display:none; }
summary::before { content:"›"; display:inline-block; width:.75rem; color:var(--bs-secondary-color); transition:transform .15s; }
details[open] > summary::before { transform:rotate(90deg); }
details[open] > summary { background:var(--bs-tertiary-bg); border-bottom:1px solid var(--bs-border-color); }
summary .name { font-weight:600; word-break:break-all; }
summary .muted { font-size:.875rem; margin-left:auto; }
details table tr:last-child td { border-bottom:0; }
details thead th { border-bottom-width:1px; color:var(--bs-secondary-color); font-size:.8125rem; text-transform:uppercase; letter-spacing:.03em; }
.empty { padding:3rem; text-align:center; background:var(--bs-body-bg); border:1px solid var(--bs-border-color); border-radius:.375rem; }

/* table view */
#flat { background:var(--bs-body-bg); border:1px solid var(--bs-border-color); border-radius:.375rem; border-collapse:separate; border-spacing:0; overflow:hidden; }
#flat thead th { position:sticky; top:0; background:var(--bs-body-bg); z-index:1; }
#flat tbody + tbody tr:first-child td { border-top:2px solid var(--bs-border-color); }
#flat tbody:last-child tr:last-child td { border-bottom:0; }
#flat td[rowspan] { background:var(--bs-tertiary-bg); border-right:1px solid var(--bs-border-color); }
#flat td.name { min-width:190px; max-width:280px; word-break:break-all; }
#flat td.name > div:first-child { font-weight:600; }
#flat .sub { font-size:.8125rem; }
#flat td.num { width:1%; }
th[style] { cursor:default !important; } th[style]:hover { color:inherit; }
body[data-view=grouped] #flat, body[data-view=table] #grouped { display:none; }
body[data-view=table] .gonly { visibility:hidden; }
</style>
</head>
<body data-view="$view">
<main>
<h1>kembarki duplicate report</h1>
<div class="muted">Scanned $roots · $when · read-only (no files were changed)</div>
<div class="stats">
  <div class="stat"><b>$files</b><span class="muted">files scanned</span></div>
  <div class="stat"><b>$ngroups</b><span class="muted">duplicate names</span></div>
  <div class="stat"><b>$ninstances</b><span class="muted">duplicate instances</span></div>
  <div class="stat"><b>$wasted</b><span class="muted">potentially reclaimable</span></div>
  <div class="stat"><b>$errors</b><span class="muted">unreadable entries</span></div>
</div>
<div class="toolbar">
  <span class="seg"><button data-view="grouped">Grouped</button><button data-view="table">Table</button></span>
  <input type="search" id="q" placeholder="Filter by name or path…">
  <select id="ftype" aria-label="File type"><option value="">All types</option>$type_options</select>
  <select id="fsize" aria-label="Size match"><option value="">Any size</option><option value="1">Same size</option><option value="0">Size differs</option></select>
  <span class="gonly"><button id="expand">Expand all</button> <button id="collapse">Collapse all</button></span>
  <span class="muted" id="shown"></span>
</div>
<div id="grouped">$body</div>
$flat
</main>
<script>
const groups = [...document.querySelectorAll('details.group')];
const flatGroups = [...document.querySelectorAll('#flat tbody')];
const KEY = 'kembarki-view';
function setView(v) {
  document.body.dataset.view = v;
  document.querySelectorAll('.seg button').forEach(b => b.classList.toggle('on', b.dataset.view === v));
  try { localStorage.setItem(KEY, v); } catch (e) {}
  filter();
}
document.querySelectorAll('.seg button').forEach(b => b.onclick = () => setView(b.dataset.view));
const q = document.getElementById('q'), ftype = document.getElementById('ftype'), fsize = document.getElementById('fsize'), shown = document.getElementById('shown');
const match = (el, t) => (!t || el.dataset.search.includes(t)) && (!ftype.value || el.dataset.type === ftype.value) && (!fsize.value || el.dataset.same === fsize.value);
function filter() {
  const t = q.value.toLowerCase(); let n = 0;
  for (const g of groups) {
    const ok = match(g, t);
    g.hidden = !ok; if (ok) n++;
  }
  let m = 0;
  for (const r of flatGroups) {
    const ok = match(r, t);
    r.hidden = !ok; if (ok) m++;
  }
  shown.textContent = document.body.dataset.view === 'table'
    ? m + ' / ' + flatGroups.length + ' names shown'
    : n + ' / ' + groups.length + ' names shown';
}
q.addEventListener('input', filter); ftype.addEventListener('change', filter); fsize.addEventListener('change', filter);
document.getElementById('expand').onclick = () => groups.forEach(g => { if (!g.hidden) g.open = true; });
document.getElementById('collapse').onclick = () => groups.forEach(g => g.open = false);
document.querySelectorAll('#flat th[data-k]').forEach(th => th.addEventListener('click', () => {
  const table = th.closest('table'), k = th.dataset.k;
  const dir = th.dataset.dir = th.dataset.dir === 'asc' ? 'desc' : 'asc';
  th.closest('tr').querySelectorAll('th').forEach(o => { if (o !== th) delete o.dataset.dir; });
  [...table.tBodies].sort((a, b) => {
    const x = a.dataset[k], y = b.dataset[k];
    const c = k === 'name' ? x.localeCompare(y) : x - y;
    return dir === 'asc' ? c : -c;
  }).forEach(b => table.appendChild(b));
}));
document.querySelectorAll('#grouped th[data-k]').forEach(th => th.addEventListener('click', () => {
  const tbody = th.closest('table').tBodies[0], k = th.dataset.k;
  const dir = th.dataset.dir = th.dataset.dir === 'asc' ? 'desc' : 'asc';
  const rows = [...tbody.rows].sort((a, b) => {
    const x = a.dataset[k], y = b.dataset[k];
    const c = (k === 'path' || k === 'name') ? x.localeCompare(y) : x - y;
    return dir === 'asc' ? c : -c;
  });
  th.closest('tr').querySelectorAll('th').forEach(o => { if (o !== th) delete o.dataset.dir; });
  rows.forEach(r => tbody.appendChild(r));
}));
let saved = null; try { saved = localStorage.getItem(KEY); } catch (e) {}
setView(saved || document.body.dataset.view);
</script>
</body>
</html>
""")


_TYPES = {
    "Video": "mp4 mkv avi mov wmv flv webm m4v mpg mpeg ts 3gp vob",
    "Image": "jpg jpeg png gif bmp webp tif tiff heic heif raw cr2 nef arw dng svg ico psd",
    "Audio": "mp3 flac wav aac ogg m4a wma opus aiff alac",
    "Document": "pdf doc docx xls xlsx ppt pptx odt ods odp txt md rtf csv epub",
    "Archive": "zip rar 7z tar gz bz2 xz tgz iso dmg",
    "Code": "py js ts html css json xml yml yaml sh c cpp h java go rs php rb sql",
}
_EXT_TYPE = {ext: t for t, exts in _TYPES.items() for ext in exts.split()}
TYPE_ORDER = [*_TYPES, "Other"]


def file_type(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name.strip(".") else ""
    return _EXT_TYPE.get(ext, "Other")


def _type_options(groups: list[DuplicateGroup]) -> str:
    counts: dict[str, int] = {}
    for g in groups:
        t = file_type(g.name)
        counts[t] = counts.get(t, 0) + 1
    return "".join(f'<option value="{t}">{t} ({counts[t]:,})</option>' for t in TYPE_ORDER if t in counts)


def _group_html(g: DuplicateGroup) -> str:
    rows = "\n".join(
        f'<tr data-size="{e.size}" data-mtime="{e.mtime}" data-path="{escape(e.path)}">'
        f'<td class="num" title="{e.size:,} bytes">{human_size(e.size)}</td>'
        f'<td class="num">{fmt_time(e.mtime)}</td>'
        f'<td class="path">{escape(e.path)}</td></tr>'
        for e in g.entries
    )
    badge = '<span class="status ok">same size</span>' if g.same_size else '<span class="status warn">size differs</span>'
    search = escape(" ".join([g.name, *(e.path for e in g.entries)]).lower())
    return (
        f'<details class="group" data-same="{int(g.same_size)}" data-type="{file_type(g.name)}" data-search="{search}">'
        f'<summary><span class="name">{escape(g.name)}</span>{badge}'
        f'<span class="muted">{g.count} copies · {human_size(g.wasted)} reclaimable</span></summary>'
        f'<table><thead><tr><th data-k="size">Size</th><th data-k="mtime">Modified</th><th data-k="path">Location</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></details>"
    )


def _flat_html(groups: list[DuplicateGroup]) -> str:
    """Table layout: one <tbody> per name; name/status cells span that group's rows."""
    if not groups:
        return ""
    bodies = []
    for g in groups:
        n = g.count
        status = '<span class="status ok">same size</span>' if g.same_size else '<span class="status warn">size differs</span>'
        search = escape(" ".join([g.name, *(e.path for e in g.entries)]).lower())
        rows = []
        for i, e in enumerate(g.entries):
            lead = (
                f'<td class="name" rowspan="{n}"><div>{escape(g.name)}</div>'
                f'<div class="muted sub">{n} copies</div>'
                f'<div class="muted sub">{human_size(g.wasted)} in extra copies</div></td>'
                f'<td rowspan="{n}">{status}</td>'
            ) if i == 0 else ""
            rows.append(
                f"<tr>{lead}"
                f'<td class="num" title="{e.size:,} bytes">{human_size(e.size)}</td>'
                f'<td class="num">{fmt_time(e.mtime)}</td>'
                f'<td class="path">{escape(e.path)}</td></tr>'
            )
        bodies.append(
            f'<tbody data-name="{escape(g.name.lower())}" data-same="{int(g.same_size)}" data-type="{file_type(g.name)}" '
            f'data-size="{max(e.size for e in g.entries)}" data-mtime="{max(e.mtime for e in g.entries)}" '
            f'data-wasted="{g.wasted}" data-search="{search}">{"".join(rows)}</tbody>'
        )
    return (
        '<table id="flat"><thead><tr>'
        '<th data-k="name">Name</th><th data-k="same">Status</th><th data-k="size">Size</th>'
        '<th data-k="mtime">Modified</th><th style="cursor:default">Location</th>'
        f'</tr></thead>{"".join(bodies)}</table>'
    )


def write_html(groups: list[DuplicateGroup], path: str, meta: dict, view: str = "grouped") -> None:
    body = "\n".join(_group_html(g) for g in groups) or '<div class="empty muted">No duplicate file names found.</div>'
    html = _PAGE.substitute(
        roots=escape(", ".join(meta["roots"])),
        when=escape(meta["generated"]),
        files=f'{meta["files_scanned"]:,}',
        ngroups=f"{len(groups):,}",
        ninstances=f"{sum(g.count for g in groups):,}",
        wasted=human_size(sum(g.wasted for g in groups)),
        errors=f'{meta["errors"]:,}',
        body=body,
        flat=_flat_html(groups),
        view=view,
        type_options=_type_options(groups),
    )
    with open(path, "w", encoding="utf-8", errors="replace") as f:
        f.write(html)


# ---- cli ----




_UNITS = {"": 1, "B": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}


def parse_size(text: str) -> int:
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([KMGT]?)B?\s*", text.upper())
    if not m:
        raise argparse.ArgumentTypeError(f"invalid size: {text!r} (e.g. 500K, 10M, 1G)")
    return int(float(m.group(1)) * _UNITS[m.group(2)])


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="kembarki",
        description="Find duplicate file names recursively and write a report. Read-only.",
    )
    p.add_argument("paths", nargs="+", help="directories to scan")
    p.add_argument("-o", "--output", default="kembarki-report.html", help="HTML report path (default: %(default)s)")
    p.add_argument("--layout", choices=["grouped", "table"], default="grouped",
                   help="initial report layout; can be switched in the page (default: %(default)s)")
    p.add_argument("--csv", metavar="FILE", help="also write a CSV report")
    p.add_argument("--json", metavar="FILE", help="also write a JSON report")
    p.add_argument("--ignore-case", action="store_true", help="treat Photo.JPG and photo.jpg as the same name")
    p.add_argument("--min-size", type=parse_size, default=0, metavar="SIZE", help="skip files smaller than SIZE (e.g. 1M)")
    p.add_argument("--exclude", action="append", default=[], metavar="PATTERN",
                   help="skip files/dirs matching glob PATTERN (repeatable)")
    p.add_argument("--follow-symlinks", action="store_true", help="follow symbolic links (off by default)")
    p.add_argument("-q", "--quiet", action="store_true", help="no progress output")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    for path in args.paths:
        if not os.path.isdir(path):
            print(f"error: not a directory: {path}", file=sys.stderr)
            return 2

    stats = ScanStats()
    progress = None if args.quiet else (lambda s: print(f"\rscanned {s.files:,} files…", end="", file=sys.stderr))
    entries = scan(args.paths, exclude=args.exclude, follow_symlinks=args.follow_symlinks,
                   min_size=args.min_size, stats=stats, progress=progress)
    groups = group_by_name(entries, ignore_case=args.ignore_case)
    if progress and stats.files >= 1000:
        print("\r" + " " * 40 + "\r", end="", file=sys.stderr)

    meta = {
        "roots": [os.path.abspath(p) for p in args.paths],
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "files_scanned": stats.files,
        "dirs_scanned": stats.dirs,
        "errors": stats.errors,
        "ignore_case": args.ignore_case,
    }
    write_html(groups, args.output, meta, view=args.layout)
    if args.csv:
        write_csv(groups, args.csv)
    if args.json:
        write_json(groups, args.json, meta)

    wasted = sum(g.wasted for g in groups)
    print(f"Scanned {stats.files:,} files in {stats.dirs:,} dirs · {len(groups):,} duplicate names · "
          f"{human_size(wasted)} potentially reclaimable")
    if stats.errors:
        print(f"{stats.errors:,} entries could not be read (see warnings above)")
    print(f"Report: {os.path.abspath(args.output)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
