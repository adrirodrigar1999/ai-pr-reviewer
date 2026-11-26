from __future__ import annotations

from pathlib import Path

from reviewer.config import DEFAULT_IGNORE
from reviewer.diff import filter_files, fit_to_budget, parse_diff

SAMPLE = (Path(__file__).parent / "fixtures" / "sample.diff").read_text(encoding="utf-8")


def test_parse_files_and_flags():
    files = {f.path: f for f in parse_diff(SAMPLE)}
    assert set(files) == {"app/users.py", "app/new_module.py", "old.py", "package-lock.json", "logo.png"}
    assert files["app/new_module.py"].is_new
    assert files["old.py"].is_deleted
    assert files["logo.png"].is_binary


def test_added_line_numbers_match_new_file():
    users = next(f for f in parse_diff(SAMPLE) if f.path == "app/users.py")
    added = {ln.new_lineno: ln.content for ln in users.lines if ln.kind == "+"}
    assert added[3] == 'API_KEY = "sk-live-1234567890"'
    assert added[7] == '    query = f"SELECT * FROM users WHERE id = {user_id}"'
    assert added[12] == '    return sum(u["age"] for u in users) / len(users)'
    assert 2 not in users.added_lines  # línea de contexto, no añadida


def test_render_includes_line_numbers_and_removed_lines():
    users = next(f for f in parse_diff(SAMPLE) if f.path == "app/users.py")
    text = users.render()
    assert "    3 + API_KEY" in text
    assert '      -     return conn.execute("SELECT' in text


def test_filter_skips_deleted_binary_and_ignored():
    kept, skipped = filter_files(parse_diff(SAMPLE), DEFAULT_IGNORE)
    assert [f.path for f in kept] == ["app/users.py", "app/new_module.py"]
    assert set(skipped) == {"old.py", "package-lock.json", "logo.png"}


def test_filter_respects_repo_patterns():
    kept, _ = filter_files(parse_diff(SAMPLE), ["app/new_*"])
    assert "app/new_module.py" not in [f.path for f in kept]


def test_fit_to_budget_keeps_order_and_drops_large_files():
    kept, _ = filter_files(parse_diff(SAMPLE), DEFAULT_IGNORE)
    small = len(kept[1].render())
    selected, dropped = fit_to_budget(kept, small + 10)
    assert [f.path for f in selected] == ["app/new_module.py"]
    assert dropped == ["app/users.py"]
    selected, dropped = fit_to_budget(kept, 10_000)
    assert [f.path for f in selected] == ["app/users.py", "app/new_module.py"] and not dropped


def test_rename_uses_new_path():
    diff = (
        "diff --git a/a.py b/b.py\nsimilarity index 90%\nrename from a.py\nrename to b.py\n"
        "--- a/a.py\n+++ b/b.py\n@@ -1,1 +1,2 @@\n x = 1\n+y = 2\n"
    )
    (f,) = parse_diff(diff)
    assert f.path == "b.py" and f.added_lines == {2}
