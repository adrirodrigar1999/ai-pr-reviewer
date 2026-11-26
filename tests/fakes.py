"""Dobles de prueba para no hacer llamadas HTTP reales."""

from __future__ import annotations

import json
from typing import Any


class FakeResponse:
    def __init__(self, status_code: int = 200, data: Any = None, text: str | None = None) -> None:
        self.status_code = status_code
        self._data = data
        self.text = text if text is not None else json.dumps(data)

    def json(self) -> Any:
        return self._data


class FakeSession:
    """Devuelve las respuestas encoladas en orden y guarda cada petición recibida."""

    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def post(self, url, json=None, headers=None, timeout=None):
        return self.request("POST", url, json=json, headers=headers, timeout=timeout)

    def request(self, method, url, headers=None, timeout=None, **kwargs):
        self.calls.append({"method": method, "url": url, "headers": headers, **kwargs})
        return self.responses.pop(0)


def llm_answer(payload: dict) -> FakeResponse:
    return FakeResponse(200, {"choices": [{"message": {"role": "assistant", "content": json.dumps(payload)}}]})
