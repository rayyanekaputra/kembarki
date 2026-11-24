# AGENTS.md

Guidance for AI agents and contributors working on **kembarki**, a read-only duplicate file finder. See `PLAN.md` for scope and roadmap.

## Hard rules
- **Never modify, move, rename, or delete scanned files.** The tool only reads metadata (`stat`) and writes its own report files. Do not add "fix"/"delete" features.
- **Do not read file contents** in the default path. Hashing is backlog and must stay opt-in.
- Default output is a **self-contained HTML** file (no CDN/external assets). Always `html.escape` paths and names.

## Environment
```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
- Python 3.10+. Prefer the standard library; add dependencies only with good reason and list them in `requirements.txt`.

## Commands
- Run: `python kembarki.py <path> [-o report.html]`
- Test: `pytest`

## Code conventions
- All code lives in a single script, `kembarki.py`, run directly with `python kembarki.py`. Don't split it into a package or require `python -m`. Tests in `tests/` using pytest and `tmp_path`.
- Use `os.scandir` for traversal; don't follow symlinks unless `--follow-symlinks`.
- Handle `PermissionError`/`OSError` per entry: warn on stderr and continue — never crash a long scan.
- Keep scanning, grouping, and reporting as separate sections/functions inside `kembarki.py`.
- Type hints and small dataclasses (e.g. `FileEntry`). Progress/warnings go to stderr; summary to stdout.

## Before finishing a change
- `pytest` passes; add tests for new behavior.
- Update `PLAN.md` (move items out of Backlog when done) and `README.md` if CLI changes.
