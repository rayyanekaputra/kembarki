# kembarki — Duplicate File Finder (report-only)

## Goal
Scan a directory tree recursively (root + all nested dirs), find files sharing the same name, and produce a report. **Read-only: never moves, renames, or deletes anything.**

## Core output (per duplicate group)
1. File name
2. Size of each instance
3. Full path of each instance

Plus: modified time per instance, wasted space per group ((count − 1) × size), and a summary total.

## Detection
- Group by **file name** (optionally case-insensitive).
- Within a name group, flag whether sizes match (`same size` vs `size differs`) — a cheap hint whether copies are identical, no hashing needed.
- No content hashing for now (too slow for 10 GB+ videos) — see Backlog.

## Output
- **Default: HTML report** (`kembarki-report.html`), single file with inline CSS/JS. It has a Bootstrap 5 look with Inter loaded from Google Fonts, falling back to the system font offline.
  - Summary header: root path(s), scan time, files scanned, duplicate groups, reclaimable space.
  - One collapsible section per group, sorted by wasted space (largest first).
  - Table per group: size, modified time, full path.
  - Badge: `same size` / `size differs`.
  - Client-side search box, filters for file type (Video, Image, Audio, Document, Archive, Code, Other) and size match (Any, Same size, Size differs), and sortable columns.
  - Two layouts, toggled in the page (choice remembered): **Grouped** (collapsible per name) and **Table** (one flat sortable table, one row per file). `--layout` sets the default.
- Optional: `--csv` / `--json` for machine use.
- Short summary also printed to terminal.

## CLI
```
python kembarki.py <path> [<path> ...]
    [-o report.html]        # output file (default: kembarki-report.html)
    [--csv out.csv] [--json out.json]
    [--ignore-case]         # Photo.JPG == photo.jpg
    [--min-size 1M]         # skip small files
    [--exclude PATTERN]     # repeatable, e.g. .git, node_modules
    [--follow-symlinks]     # off by default
```
Multiple roots allowed to compare across drives (e.g. `/backup /archive`).

## Project layout
```
kembarki/
├── .venv/
├── requirements.txt       # stdlib only for now; pytest for dev
├── kembarki.py          # the whole tool: python kembarki.py <path>
├── tests/
├── PLAN.md
├── AGENTS.md
└── README.md
```

## Steps
1. **Setup** — `python -m venv .venv`, `pip install pytest`.
2. **Scanner** — recursive `os.scandir` (size + mtime from `stat`, no file reads → fast even on huge files). Apply excludes, skip symlinks by default, warn and continue on `PermissionError`/`OSError`. Progress counter on stderr.
3. **Grouping** — `dict[name_key, list[FileEntry]]`, keep groups with ≥ 2 entries, compute size-match flag + wasted space.
4. **HTML report** — self-contained template, escape all paths, human-readable sizes (KB/MB/GB).
5. **CSV/JSON** — flat rows: group, name, size, mtime, path.
6. **CLI** — wire it together, print terminal summary + report path.
7. **Tests** — pytest with `tmp_path`: nested dupes, case-insensitivity, excludes, symlinks, unreadable dirs, HTML escaping of weird filenames.
8. **README** — usage + read-only guarantee.

## Backlog
- **Content hashing** (`--mode content|both`): size-prefilter → partial hash (first/last few MB) → full SHA-256 only on candidates. Opt-in due to cost on large files.
- Detect same content under different names (needs hashing).
- Cache scan results between runs (e.g. SQLite keyed on path+size+mtime).
- Parallel scanning for network drives.
- Fuzzy name matching (`video (1).mp4` vs `video.mp4`, `Copy of …`).
