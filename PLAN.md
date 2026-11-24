# kembarki — Duplicate File Finder (report-only)

## Goal
Scan a directory tree recursively (root + all nested dirs), find files sharing the same name, and produce a report. **Read-only: never moves, renames, or deletes anything.**

## Status
v0.1 is done: scanner, name grouping, HTML report (grouped + table layouts, filters), CSV/JSON export, tests, sample data, bilingual README. Next up is the Backlog.

## Core output (per duplicate group)
1. File name
2. Size of each instance
3. Full path of each instance

Plus: modified time per instance, reclaimable space per group (total size − largest copy), and a summary total.

## Detection
- Group by **file name** (optionally case-insensitive).
- Within a name group, flag whether sizes match (`same size` vs `size differs`). It's a cheap hint that copies are identical, with no hashing needed.
- No content hashing for now (too slow for 10 GB+ videos). See Backlog.

## Output
- **Default: HTML report** (`kembarki-report.html`), single file with inline CSS/JS.
  - Look: Bootstrap 5 style, hand-written (no framework). Inter is loaded from Google Fonts and falls back to the system font offline. **Light mode only.**
  - Summary cards: root path(s), scan time, files scanned, duplicate names, duplicate instances, reclaimable space, unreadable entries.
  - Toolbar, left to right: Grouped | Table toggle (always first so it never shifts), search box, file type filter, size match filter, Expand/Collapse (hidden but space kept in Table view), shown counter (fixed width).
  - Filters:
    - **File type** by extension: Video, Image, Audio, Document, Archive, Code, Other. Only types present in the scan are listed, with counts.
    - **Size match**: Any size, Same size, Size differs.
    - Filters combine with the search box and work in both layouts.
  - Two layouts, toggled in the page (last choice remembered in localStorage); `--layout` sets the initial one:
    - **Grouped:** one collapsible card per name (name, status, copies, reclaimable), with an inner table of size, modified, location.
    - **Table:** one table, one `<tbody>` per name. The name cell (name, "N copies", "X in extra copies") and the status cell span that group's rows. Sorting by Name, Status, Size or Modified moves whole groups; Location isn't sortable.
  - Status is **plain colored text** (green "same size", orange "size differs"), not a pill/badge, so it doesn't wrap in table cells.
  - Groups are ordered by reclaimable space, largest first.
- Optional: `--csv` / `--json` for machine use.
- Short summary also printed to terminal.

## CLI
```
python kembarki.py <path> [<path> ...]
    [-o report.html]           # output file (default: kembarki-report.html)
    [--layout grouped|table]   # initial report layout (default: grouped)
    [--csv out.csv] [--json out.json]
    [--ignore-case]            # Photo.JPG == photo.jpg
    [--min-size 1M]            # skip small files (B/K/M/G/T)
    [--exclude PATTERN]        # glob on file/dir names, repeatable
    [--follow-symlinks]        # off by default; loops are safe
    [-q]                       # no progress output
```
Multiple roots are allowed to compare folders or drives (e.g. `/backup /archive`). Overlapping roots aren't double-counted.

## Project layout
```
kembarki/
├── kembarki.py              # the whole tool: python kembarki.py <path>
├── tests/test_kembarki.py   # pytest
├── sample_folder_to_test/   # demo data: 3 levels, 72 animal .txt dups
├── README.md                # english
├── README.id.md             # bahasa indonesia
├── PLAN.md
├── AGENTS.md
├── requirements.txt         # pytest only; the tool itself is stdlib
├── pyproject.toml           # pytest config
├── uv.lock
└── .gitignore               # .venv, caches, *.html / *.csv / *.json reports
```

## Done
1. **Setup:** venv (or uv), pytest.
2. **Scanner:** recursive `os.scandir`, reading size + mtime from `stat` only. Excludes, symlinks skipped by default, loop and overlap safe, warns and continues on `OSError`, progress on stderr.
3. **Grouping:** by name, groups of 2 or more, size-match flag, reclaimable space.
4. **HTML report:** grouped + table layouts, filters, sorting, Bootstrap 5 look, all paths escaped.
5. **CSV/JSON export.**
6. **CLI** with terminal summary.
7. **Tests:** nested dupes, case-insensitivity, excludes, min size, symlinks and loops, overlapping roots, unreadable dirs, HTML escaping, read-only guarantee, layouts, file types, filters.
8. **Sample data:** `sample_folder_to_test/`, used in both READMEs.
9. **README** in english and bahasa, in the author's casual tone.

## Backlog
- **Content hashing** (`--mode content|both`): size prefilter → partial hash (first/last few MB) → full SHA-256 only on candidates. Opt-in due to cost on large files.
- Detect the same content under different names (needs hashing).
- Exact extension filter (`.mkv`, `.mp4`, …) alongside the type categories.
- Optional light/dark switch in the report (must default to light).
- Cache scan results between runs (e.g. SQLite keyed on path+size+mtime).
- Parallel scanning for network drives.
- Fuzzy name matching (`video (1).mp4` vs `video.mp4`, `Copy of …`).
