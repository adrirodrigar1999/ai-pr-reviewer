from __future__ import annotations

import pytest

from reviewer.github import GitHubClient, GitHubError
from reviewer.llm import LLMClient, LLMError
from tests.fakes import FakeResponse, FakeSession, llm_answer


def make_llm(responses):
    session = FakeSession(responses)
    return LLMClient("https://models.example/inference/", "token", "m", session=session, sleep=lambda s: None), session


def test_llm_sends_openai_compatible_request():
    llm, session = make_llm([llm_answer({"summary": "ok", "findings": []})])
    assert '"summary": "ok"' in llm.complete([{"role": "user", "content": "hola"}])
    call = session.calls[0]
    assert call["url"] == "https://models.example/inference/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer token"
    assert call["json"]["response_format"] == {"type": "json_object"}


def test_llm_retries_without_json_mode_on_400():
    llm, session = make_llm([FakeResponse(400, {"error": "unsupported"}), llm_answer({})])
    llm.complete([])
    assert "response_format" not in session.calls[1]["json"]


def test_llm_retries_on_429_then_fails():
    llm, session = make_llm([FakeResponse(429, {}), FakeResponse(503, {}), FakeResponse(500, {"e": 1})])
    with pytest.raises(LLMError, match="HTTP 500"):
        llm.complete([])
    assert len(session.calls) == 3


def test_github_review_payload():
    session = FakeSession([FakeResponse(200, {})])
    gh = GitHubClient("t", "yo/repo", session=session)
    gh.create_review(7, "abc", "cuerpo", [{"path": "a.py", "line": 3, "side": "RIGHT", "body": "x"}])
    call = session.calls[0]
    assert call["url"] == "https://api.github.com/repos/yo/repo/pulls/7/reviews"
    assert call["json"]["event"] == "COMMENT" and call["json"]["commit_id"] == "abc"


def test_github_falls_back_to_summary_comment_on_422():
    session = FakeSession([FakeResponse(422, {}, text="Line could not be resolved"), FakeResponse(201, {})])
    gh = GitHubClient("t", "yo/repo", session=session)
    gh.create_review(7, "abc", "cuerpo", [{"path": "a.py", "line": 3, "side": "RIGHT", "body": "x"}])
    assert session.calls[1]["url"].endswith("/issues/7/comments")


def test_github_raises_other_errors():
    gh = GitHubClient("t", "yo/repo", session=FakeSession([FakeResponse(403, {}, text="forbidden")]))
    with pytest.raises(GitHubError, match="403"):
        gh.get_pull_request(1)


def test_diff_request_uses_diff_media_type():
    session = FakeSession([FakeResponse(200, None, text="diff --git a/x b/x")])
    GitHubClient("t", "yo/repo", session=session).get_diff(3)
    assert session.calls[0]["headers"]["Accept"] == "application/vnd.github.diff"
