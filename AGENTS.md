# AGENTS.md

Guidance for AI agents and contributors working on **kembarki**, a read-only duplicate file finder. See `PLAN.md` for scope, current state and roadmap.

## Hard rules
- **Never modify, move, rename, or delete scanned files.** The tool only reads metadata (`stat`) and writes its own report files. Do not add "fix"/"delete" features.
- **Do not read file contents** in the default path. Hashing is backlog and must stay opt-in.
- **Never commit generated reports** (`*.html`, `*.csv`, `*.json` are gitignored). They contain real file paths from the author's drives, which is private. Before committing, check `git status` for stray report files.
- Default output is a **self-contained HTML** file. The only external asset allowed is the Inter font from Google Fonts, which falls back to the system font offline. No other CDNs or external CSS/JS. Always `html.escape` paths and names.

## Report UI rules
- Bootstrap 5 look, hand-written without the framework. Inter typeface. **Light mode only**: don't follow the system dark mode.
- Status ("same size" / "size differs") is plain colored text. **No pill/badge/capsule styles**, which break in table cells.
- The Grouped | Table toggle stays first in the toolbar and must not shift when switching views. Hide view-specific controls with `visibility:hidden`, not `display:none`.
- In Table view, a name's rows stay together (one `<tbody>` per group); sorting moves whole groups.

## Environment
```
python -m venv .venv            # or: uv venv
source .venv/bin/activate
pip install -r requirements.txt # or: uv pip install -r requirements.txt
```
- Python 3.10+. The tool is standard library only; `requirements.txt` holds dev deps (pytest). Add dependencies only with good reason.

## Commands
- Run: `python kembarki.py <path> [-o report.html]`
- Try it: `python kembarki.py ./sample_folder_to_test` (expect 18 duplicate names)
- Test: `pytest`

## Code conventions
- All code lives in a single script, `kembarki.py`, run directly with `python kembarki.py`. Don't split it into a package or require `python -m`. Tests go in `tests/`, using pytest and `tmp_path`.
- Use `os.scandir` for traversal; don't follow symlinks unless `--follow-symlinks`.
- Handle `PermissionError`/`OSError` per entry: warn on stderr and continue. Never crash a long scan.
- Keep scanning, grouping, and reporting as separate sections/functions inside `kembarki.py`.
- Type hints and small dataclasses (e.g. `FileEntry`). Progress/warnings go to stderr; the summary goes to stdout.

## Docs and writing style
- Two READMEs: `README.md` (english) and `README.id.md` (bahasa indonesia). Keep them in sync, with the same sections in both.
- README tone is the author's own: casual, **all lowercase, no apostrophes** (write "doesnt", "its", "theyre"). Code, flags and file names keep their real spelling.
- README examples use `./sample_folder_to_test` so they can be copy-pasted. If the sample data changes, update the expected numbers in both READMEs.
- `PLAN.md` and `AGENTS.md` are written in plain standard english.

## Commits
- Messages are in the author's casual tone: lowercase, short, no apostrophes, e.g. `add file type and same size / differs filters. toggle doesnt move anymore`.
- Commit only when asked. Don't push, the author pushes themselves.

## Before finishing a change
- `pytest` passes; add tests for new behavior.
- Update `PLAN.md` (move items from Backlog to Done) and both READMEs if the CLI or report changes.
