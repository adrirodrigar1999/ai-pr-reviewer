from __future__ import annotations

import json
from pathlib import Path

import pytest

from reviewer.config import DEFAULT_IGNORE, RepoConfig
from reviewer.diff import filter_files, parse_diff
from reviewer.prompt import build_messages
from reviewer.report import MARKER, inline_comment, summary_body
from reviewer.review import extract_json, parse_review

SAMPLE = (Path(__file__).parent / "fixtures" / "sample.diff").read_text(encoding="utf-8")
FILES, _ = filter_files(parse_diff(SAMPLE), DEFAULT_IGNORE)


def answer(findings, summary="Resumen"):
    return json.dumps({"summary": summary, "findings": findings})


def f(file="app/users.py", line=8, severity="high", category="security", message="Inyección SQL"):
    return {"file": file, "line": line, "severity": severity, "category": category, "message": message}


def test_extract_json_variants():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('Aquí tienes:\n```json\n{"a": 2}\n```') == {"a": 2}
    assert extract_json('texto {"a": 3} más texto') == {"a": 3}
    with pytest.raises(ValueError):
        extract_json("sin json")


def test_valid_findings_are_kept():
    review = parse_review(answer([f(), f(line=3, message="Secreto en el código")]), FILES, RepoConfig())
    assert [x.line for x in review.findings] == [8, 3]
    assert review.discarded == 0 and review.summary == "Resumen"


def test_hallucinated_lines_and_files_are_discarded():
    findings = [f(line=2), f(line=999), f(file="no/existe.py"), {"file": "app/users.py"}]
    review = parse_review(answer(findings), FILES, RepoConfig())
    assert review.findings == [] and review.discarded == 4


def test_min_severity_and_max_comments():
    findings = [f(line=3, severity="low"), f(line=8, severity="HIGH"), f(line=13, severity="medium", category="bug")]
    review = parse_review(answer(findings), FILES, RepoConfig(min_severity="medium", max_comments=1))
    assert [(x.line, x.severity) for x in review.findings] == [(8, "high")]


def test_duplicates_on_same_line_keep_most_severe():
    review = parse_review(answer([f(severity="low"), f(severity="high")]), FILES, RepoConfig())
    assert len(review.findings) == 1 and review.findings[0].severity == "high"


def test_prompt_contains_rules_language_and_numbered_diff():
    msgs = build_messages(FILES, RepoConfig(language="inglés", rules=["Usa siempre logging"]), title="Mi PR")
    user = msgs[1]["content"]
    assert "inglés" in user and "Usa siempre logging" in user and "Mi PR" in user
    assert '    7 +     query = f"SELECT' in user


def test_report_texts():
    review = parse_review(answer([f()]), FILES, RepoConfig())
    body = summary_body(review, "openai/gpt-4o-mini", ["app/users.py"], ["old.py"], [])
    assert body.startswith(MARKER) and "🔴 Alta: **1**" in body and "`old.py`" in body
    assert "Seguridad" in inline_comment(review.findings[0])
    empty = summary_body(parse_review(answer([]), FILES, RepoConfig()), "m", [], [], [])
    assert "No se han encontrado problemas" in empty


def test_code_snippet_relocates_wrong_line_number():
    wrong = {**f(line=12), "code": 'query = f"SELECT * FROM users WHERE id = {user_id}"'}
    review = parse_review(answer([wrong]), FILES, RepoConfig())
    assert [x.line for x in review.findings] == [7]


def test_code_snippet_approximate_match_relocates():
    approx = {**f(line=12), "code": "query = f'SELECT * FROM users WHERE id={user_id}'"}
    review = parse_review(answer([approx]), FILES, RepoConfig())
    assert [x.line for x in review.findings] == [7]


def test_unmatched_snippet_falls_back_to_valid_line_or_discards():
    keep = {**f(line=7), "code": "eval(user_input)"}
    assert [x.line for x in parse_review(answer([keep]), FILES, RepoConfig()).findings] == [7]
    drop = {**f(line=2), "code": "eval(user_input)"}
    review = parse_review(answer([drop]), FILES, RepoConfig())
    assert review.findings == [] and review.discarded == 1


def test_same_message_repeated_in_file_is_collapsed():
    repeated = [f(line=3, message="Secreto en el código"), f(line=8, message="secreto  en el código")]
    review = parse_review(answer(repeated), FILES, RepoConfig())
    assert len(review.findings) == 1
