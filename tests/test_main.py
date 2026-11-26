from __future__ import annotations

import json
from pathlib import Path

from reviewer import main as main_mod
from reviewer.config import RepoConfig
from reviewer.llm import LLMClient
from reviewer.review import Finding, Review
from tests.fakes import FakeResponse, FakeSession, llm_answer

SAMPLE = (Path(__file__).parent / "fixtures" / "sample.diff").read_text(encoding="utf-8")
ANSWER = {
    "summary": "Añade consultas de usuarios.",
    "findings": [
        {"file": "app/users.py", "line": 8, "severity": "high", "category": "security", "message": "Inyección SQL"},
        {"file": "app/users.py", "line": 50, "severity": "low", "category": "bug", "message": "Inventado"},
    ],
}


def llm(responses):
    return LLMClient("https://x/v1", "k", "modelo-test", session=FakeSession(responses), sleep=lambda s: None)


def test_run_review_end_to_end():
    review, report = main_mod.run_review(SAMPLE, llm([llm_answer(ANSWER)]), RepoConfig(), 60_000)
    assert [x.line for x in review.findings] == [8]
    assert review.discarded == 1
    assert "modelo-test" in report and "`package-lock.json`" in report


def test_run_review_without_code_does_not_call_llm():
    session = FakeSession([])
    client = LLMClient("https://x/v1", "k", "m", session=session)
    review, _ = main_mod.run_review("", client, RepoConfig(), 60_000)
    assert "No hay cambios" in review.summary and session.calls == []


def test_should_fail():
    review = Review("s", [Finding(file="a", line=1, severity="medium", message="m")])
    assert main_mod.should_fail(review, "medium")
    assert not main_mod.should_fail(review, "high")
    assert not main_mod.should_fail(review, "none")


def test_main_in_github_actions(tmp_path, monkeypatch, capsys):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"number": 5}}))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_REPOSITORY", "yo/repo")
    monkeypatch.setenv("GITHUB_TOKEN", "gh-token")
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "no-existe.yml"))
    monkeypatch.setenv("FAIL_ON", "high")

    gh_session = FakeSession(
        [
            FakeResponse(200, {"title": "PR", "body": None, "head": {"sha": "sha123"}}),
            FakeResponse(200, None, text=SAMPLE),
            FakeResponse(200, {}),
        ]
    )
    llm_session = FakeSession([llm_answer(ANSWER)])
    real_gh, real_llm = main_mod.GitHubClient, main_mod.LLMClient
    monkeypatch.setattr(main_mod, "GitHubClient", lambda *a, **k: real_gh(*a, session=gh_session, **k))
    monkeypatch.setattr(main_mod, "LLMClient", lambda **k: real_llm(session=llm_session, **k))

    assert main_mod.main([]) == 1  # hay un hallazgo "high" y FAIL_ON=high
    review_call = gh_session.calls[2]
    assert review_call["json"]["commit_id"] == "sha123"
    assert review_call["json"]["comments"][0]["line"] == 8
    assert llm_session.calls[0]["headers"]["Authorization"] == "Bearer gh-token"
    assert llm_session.calls[0]["url"] == "https://models.github.ai/inference/chat/completions"
    assert "1 comentarios, 1 descartados" in capsys.readouterr().out


def test_main_local_diff_file(tmp_path, monkeypatch, capsys):
    diff = tmp_path / "c.diff"
    diff.write_text(SAMPLE)
    monkeypatch.setenv("CONFIG_PATH", str(tmp_path / "no.yml"))
    monkeypatch.delenv("FAIL_ON", raising=False)
    session = FakeSession([llm_answer(ANSWER)])
    real_llm = main_mod.LLMClient
    monkeypatch.setattr(main_mod, "LLMClient", lambda **k: real_llm(session=session, **k))
    assert main_mod.main(["--diff-file", str(diff)]) == 0
    assert "`app/users.py:8`" in capsys.readouterr().out
