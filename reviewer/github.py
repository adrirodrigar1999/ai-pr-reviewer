"""Cliente mínimo de la API REST de GitHub para leer un PR y publicar la revisión."""

from __future__ import annotations

from typing import Any

import requests


class GitHubError(Exception):
    pass


class GitHubClient:
    def __init__(
        self,
        token: str,
        repo: str,
        api_url: str = "https://api.github.com",
        session: requests.Session | None = None,
    ) -> None:
        self.repo = repo
        self.api = api_url.rstrip("/")
        self.session = session or requests.Session()
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request(self, method: str, path: str, accept: str | None = None, **kwargs) -> requests.Response:
        headers = dict(self.headers)
        if accept:
            headers["Accept"] = accept
        resp = self.session.request(method, f"{self.api}{path}", headers=headers, timeout=60, **kwargs)
        if resp.status_code >= 400:
            raise GitHubError(f"{method} {path} → HTTP {resp.status_code}: {resp.text[:300]}")
        return resp

    def get_pull_request(self, number: int) -> dict[str, Any]:
        return self._request("GET", f"/repos/{self.repo}/pulls/{number}").json()

    def get_diff(self, number: int) -> str:
        return self._request("GET", f"/repos/{self.repo}/pulls/{number}", accept="application/vnd.github.diff").text

    def create_review(self, number: int, commit_id: str, body: str, comments: list[dict[str, Any]]) -> None:
        payload = {"commit_id": commit_id, "event": "COMMENT", "body": body, "comments": comments}
        try:
            self._request("POST", f"/repos/{self.repo}/pulls/{number}/reviews", json=payload)
        except GitHubError as exc:
            if not comments or "HTTP 422" not in str(exc):
                raise
            # Si GitHub rechaza algún comentario en línea, se publica al menos el resumen.
            self._request("POST", f"/repos/{self.repo}/issues/{number}/comments", json={"body": body})
