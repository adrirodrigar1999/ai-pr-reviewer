"""Punto de entrada.

En GitHub Actions lee el PR del evento y publica la revisión.
En local: `python -m reviewer --diff-file cambios.diff` imprime la revisión en Markdown.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from reviewer.config import DEFAULT_IGNORE, SEVERITY_ORDER, RepoConfig, load_repo_config
from reviewer.diff import filter_files, fit_to_budget, parse_diff
from reviewer.github import GitHubClient
from reviewer.llm import LLMClient
from reviewer.prompt import build_messages
from reviewer.report import inline_comment, markdown_report, summary_body
from reviewer.review import Review, parse_review


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def run_review(diff_text: str, llm: LLMClient, config: RepoConfig, max_chars: int, title: str = "", body: str = ""):
    files, skipped = filter_files(parse_diff(diff_text), DEFAULT_IGNORE + config.ignore)
    files, dropped = fit_to_budget(files, max_chars)
    if not files:
        review = Review(summary="No hay cambios de código que revisar en este PR.")
    else:
        raw = llm.complete(build_messages(files, config, title, body))
        print("::group::Respuesta del modelo")
        print(raw)
        print("::endgroup::")
        review = parse_review(raw, files, config)
    report = summary_body(review, llm.model, [f.path for f in files], skipped, dropped)
    return review, report


def should_fail(review: Review, fail_on: str) -> bool:
    if fail_on not in SEVERITY_ORDER:
        return False
    return any(SEVERITY_ORDER[f.severity] >= SEVERITY_ORDER[fail_on] for f in review.findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Revisor de pull requests con IA")
    parser.add_argument("--diff-file", help="Revisar un diff local e imprimir el resultado (no publica nada)")
    args = parser.parse_args(argv)

    base_url, api_key = env("LLM_BASE_URL"), env("LLM_API_KEY")
    if not base_url or not api_key:
        # Sin proveedor configurado no se rompe el PR: se avisa y se sale sin error.
        print("::warning::AI PR Reviewer: faltan llm-base-url o llm-api-key; se omite la revisión.")
        return 0
    llm = LLMClient(
        base_url=base_url,
        api_key=api_key,
        model=env("LLM_MODEL", "gpt-4o-mini"),
        auth=env("LLM_AUTH", "bearer"),
        timeout=float(env("LLM_TIMEOUT", "120")),
    )
    config = load_repo_config(env("CONFIG_PATH", ".ai-review.yml"))
    max_chars = int(env("MAX_DIFF_CHARS", "60000"))
    fail_on = env("FAIL_ON", "none").lower()

    if args.diff_file:
        review, report = run_review(Path(args.diff_file).read_text(encoding="utf-8"), llm, config, max_chars)
        print(markdown_report(review, report))
        return 1 if should_fail(review, fail_on) else 0

    event = json.loads(Path(env("GITHUB_EVENT_PATH")).read_text(encoding="utf-8"))
    number = event.get("pull_request", {}).get("number") or event.get("number")
    if not number:
        print("Este evento no es un pull request; no hay nada que revisar.")
        return 0

    gh = GitHubClient(env("GITHUB_TOKEN"), env("GITHUB_REPOSITORY"), env("GITHUB_API_URL", "https://api.github.com"))
    pr = gh.get_pull_request(number)
    review, report = run_review(gh.get_diff(number), llm, config, max_chars, pr.get("title", ""), pr.get("body") or "")
    comments = [{"path": f.file, "line": f.line, "side": "RIGHT", "body": inline_comment(f)} for f in review.findings]
    gh.create_review(number, pr["head"]["sha"], report, comments)
    print(f"Revisión publicada en el PR #{number}: {len(comments)} comentarios, {review.discarded} descartados.")
    return 1 if should_fail(review, fail_on) else 0


if __name__ == "__main__":
    sys.exit(main())
