# kembarki

Finds duplicate file names across a directory tree (the root and every folder inside it) and writes an HTML report. It is **read-only**: it only reads file details (name, size, modified time). It never opens, changes, moves or deletes the files it scans, so even 10 GB+ videos are scanned instantly.

## Setup
```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt   # only needed for running the tests
```

## Usage
```
python kembarki.py /mnt/backup                       # → kembarki-report.html
python kembarki.py /mnt/backup /mnt/archive -o dupes.html
python kembarki.py /mnt/backup --ignore-case --min-size 10M --exclude .git --exclude '*.tmp'
python kembarki.py /mnt/backup --csv dupes.csv --json dupes.json
```

| Option | Meaning |
|---|---|
| `-o FILE` | HTML report path (default `kembarki-report.html`) |
| `--csv FILE`, `--json FILE` | extra machine-readable reports |
| `--ignore-case` | `Photo.JPG` == `photo.jpg` |
| `--min-size SIZE` | skip small files (`500K`, `10M`, `1G`) |
| `--exclude PATTERN` | glob on file/dir names, repeatable |
| `--follow-symlinks` | follow links (off by default; loops are safe) |
| `--layout grouped` or `table` | which view the report opens in (switchable in the page) |
| `-q` | no progress output |

The report lists every name that appears more than once, with each copy's size, modified time and location. Each group is labelled **same size** (probably the same file) or **size differs**. Groups are sorted by reclaimable space, and the page has search and sortable columns.

Matching is by name only. Content hashing is in the backlog (see `PLAN.md`).

## Tests
```
pytest
```
