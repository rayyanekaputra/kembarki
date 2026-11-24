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
<style>
:root { color-scheme: light dark; --bg:#fafafa; --fg:#1d1d1f; --muted:#6b6b70; --card:#fff; --line:#e3e3e6; --ok:#1a7f37; --warn:#b35900; }
@media (prefers-color-scheme: dark) { :root { --bg:#141416; --fg:#ececf0; --muted:#9a9aa2; --card:#1d1d21; --line:#2e2e34; --ok:#4ac26b; --warn:#f0a040; } }
* { box-sizing: border-box; }
body { margin:0; font:14px/1.5 system-ui, sans-serif; background:var(--bg); color:var(--fg); }
main { max-width:1100px; margin:0 auto; padding:24px; }
h1 { font-size:22px; margin:0 0 4px; }
.muted { color:var(--muted); }
.stats { display:flex; flex-wrap:wrap; gap:12px; margin:16px 0; }
.stat { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:10px 14px; min-width:150px; }
.stat b { display:block; font-size:20px; font-variant-numeric:tabular-nums; }
.toolbar { display:flex; gap:12px; align-items:center; margin:16px 0; flex-wrap:wrap; }
input[type=search] { flex:1; min-width:220px; padding:8px 10px; border:1px solid var(--line); border-radius:6px; background:var(--card); color:var(--fg); font:inherit; }
button { padding:7px 12px; border:1px solid var(--line); border-radius:6px; background:var(--card); color:var(--fg); font:inherit; cursor:pointer; }
details { background:var(--card); border:1px solid var(--line); border-radius:8px; margin-bottom:8px; }
summary { padding:10px 14px; cursor:pointer; display:flex; gap:12px; align-items:baseline; flex-wrap:wrap; }
summary .name { font-weight:600; word-break:break-all; }
.badge { font-size:12px; padding:1px 8px; border-radius:10px; border:1px solid currentColor; }
.badge.ok { color:var(--ok); } .badge.warn { color:var(--warn); }
table { width:100%; border-collapse:collapse; }
th, td { text-align:left; padding:6px 14px; border-top:1px solid var(--line); vertical-align:top; }
th { cursor:pointer; user-select:none; font-weight:600; color:var(--muted); }
td.num { font-variant-numeric:tabular-nums; white-space:nowrap; }
td.path { font-family:ui-monospace, monospace; font-size:13px; word-break:break-all; }
.empty { padding:40px; text-align:center; }
.seg { display:inline-flex; border:1px solid var(--line); border-radius:6px; overflow:hidden; }
.seg button { border:0; border-radius:0; }
.seg button.on { background:var(--fg); color:var(--bg); }
#flat { background:var(--card); border:1px solid var(--line); border-radius:8px; overflow:hidden; }
#flat thead th { position:sticky; top:0; background:var(--card); border-top:0; }
#flat tbody + tbody tr:first-child td { border-top:2px solid var(--muted); }
#flat td[rowspan] { background:color-mix(in srgb, var(--fg) 3%, transparent); }
#flat td.name { min-width:180px; max-width:280px; word-break:break-all; }
#flat td.name > div:first-child { font-weight:600; }
#flat .sub { font-size:12px; }
#flat td.num { width:1%; }
th[data-dir=asc]::after { content:" ▲"; } th[data-dir=desc]::after { content:" ▼"; }
body[data-view=grouped] #flat, body[data-view=table] #grouped, body[data-view=table] .gonly { display:none; }
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
  <input type="search" id="q" placeholder="Filter by name or path…">
  <label><input type="checkbox" id="sameOnly"> same size only</label>
  <span class="seg"><button data-view="grouped">Grouped</button><button data-view="table">Table</button></span>
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
const q = document.getElementById('q'), same = document.getElementById('sameOnly'), shown = document.getElementById('shown');
function filter() {
  const t = q.value.toLowerCase(); let n = 0;
  for (const g of groups) {
    const ok = (!t || g.dataset.search.includes(t)) && (!same.checked || g.dataset.same === '1');
    g.hidden = !ok; if (ok) n++;
  }
  let m = 0;
  for (const r of flatGroups) {
    const ok = (!t || r.dataset.search.includes(t)) && (!same.checked || r.dataset.same === '1');
    r.hidden = !ok; if (ok) m++;
  }
  shown.textContent = document.body.dataset.view === 'table'
    ? m + ' / ' + flatGroups.length + ' names shown'
    : n + ' / ' + groups.length + ' names shown';
}
q.addEventListener('input', filter); same.addEventListener('change', filter);
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


def _group_html(g: DuplicateGroup) -> str:
    rows = "\n".join(
        f'<tr data-size="{e.size}" data-mtime="{e.mtime}" data-path="{escape(e.path)}">'
        f'<td class="num" title="{e.size:,} bytes">{human_size(e.size)}</td>'
        f'<td class="num">{fmt_time(e.mtime)}</td>'
        f'<td class="path">{escape(e.path)}</td></tr>'
        for e in g.entries
    )
    badge = '<span class="badge ok">same size</span>' if g.same_size else '<span class="badge warn">size differs</span>'
    search = escape(" ".join([g.name, *(e.path for e in g.entries)]).lower())
    return (
        f'<details class="group" data-same="{int(g.same_size)}" data-search="{search}">'
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
        status = '<span class="badge ok">same size</span>' if g.same_size else '<span class="badge warn">size differs</span>'
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
            f'<tbody data-name="{escape(g.name.lower())}" data-same="{int(g.same_size)}" '
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
