import json
import os

import pytest

from kembarki import main, parse_size

from kembarki import group_by_name, scan


def make(root, rel, data=b"x"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def names(groups):
    return {g.name: g for g in groups}


def test_nested_duplicates(tmp_path):
    make(tmp_path, "a.txt")
    make(tmp_path, "sub/a.txt")
    make(tmp_path, "sub/deep/er/a.txt")
    make(tmp_path, "unique.txt")
    g = names(group_by_name(scan([str(tmp_path)])))
    assert set(g) == {"a.txt"}
    assert g["a.txt"].count == 3


def test_size_flag_and_wasted(tmp_path):
    make(tmp_path, "x/same.bin", b"1234")
    make(tmp_path, "y/same.bin", b"1234")
    make(tmp_path, "x/diff.bin", b"1")
    make(tmp_path, "y/diff.bin", b"123")
    g = names(group_by_name(scan([str(tmp_path)])))
    assert g["same.bin"].same_size and g["same.bin"].wasted == 4
    assert not g["diff.bin"].same_size and g["diff.bin"].wasted == 1


def test_ignore_case(tmp_path):
    make(tmp_path, "a/Photo.JPG")
    make(tmp_path, "b/photo.jpg")
    assert group_by_name(scan([str(tmp_path)])) == []
    assert len(group_by_name(scan([str(tmp_path)]), ignore_case=True)) == 1


def test_exclude_and_min_size(tmp_path):
    make(tmp_path, "a/f.txt")
    make(tmp_path, "node_modules/f.txt")
    assert group_by_name(scan([str(tmp_path)], exclude=["node_modules"])) == []
    make(tmp_path, "big1/g", b"x" * 100)
    make(tmp_path, "big2/g", b"x" * 100)
    g = names(group_by_name(scan([str(tmp_path)], min_size=50)))
    assert set(g) == {"g"}


def test_symlinks_not_followed(tmp_path):
    make(tmp_path, "real/f.txt")
    os.symlink(tmp_path / "real", tmp_path / "link")
    assert group_by_name(scan([str(tmp_path)])) == []


def test_symlink_loop_safe(tmp_path):
    make(tmp_path, "d/f.txt")
    os.symlink(tmp_path, tmp_path / "d" / "loop")
    list(scan([str(tmp_path)], follow_symlinks=True))  # must terminate


def test_overlapping_roots_not_double_counted(tmp_path):
    make(tmp_path, "sub/f.txt")
    assert group_by_name(scan([str(tmp_path), str(tmp_path / "sub")])) == []


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permissions")
def test_unreadable_dir_continues(tmp_path):
    make(tmp_path, "ok/a.txt")
    make(tmp_path, "ok2/a.txt")
    locked = tmp_path / "locked"
    make(tmp_path, "locked/a.txt")
    locked.chmod(0)
    try:
        errors = []
        g = group_by_name(scan([str(tmp_path)], on_error=lambda p, e: errors.append(p)))
        assert g[0].count == 2 and errors
    finally:
        locked.chmod(0o755)


def test_cli_reports_and_escaping(tmp_path, capsys):
    src = tmp_path / "src"
    make(src, "a/<script>x.txt")
    make(src, "b/<script>x.txt")
    out = tmp_path / "r.html"
    rc = main([str(src), "-o", str(out), "--json", str(tmp_path / "r.json"), "--csv", str(tmp_path / "r.csv"), "-q"])
    assert rc == 0
    html = out.read_text()
    assert "&lt;script&gt;x.txt" in html and "<script>x.txt" not in html
    data = json.loads((tmp_path / "r.json").read_text())
    assert data["groups"][0]["count"] == 2
    assert (tmp_path / "r.csv").read_text().count("\n") == 3


def test_cli_does_not_modify_files(tmp_path):
    src = tmp_path / "src"
    f1 = make(src, "a/x", b"data")
    make(src, "b/x", b"data")
    before = (f1.read_bytes(), f1.stat().st_mtime)
    main([str(src), "-o", str(tmp_path / "r.html"), "-q"])
    assert (f1.read_bytes(), f1.stat().st_mtime) == before


def test_parse_size():
    assert parse_size("10") == 10
    assert parse_size("1K") == 1024
    assert parse_size("1.5mb") == int(1.5 * 1024**2)
