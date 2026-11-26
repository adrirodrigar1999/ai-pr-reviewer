"""Cliente mínimo para cualquier API compatible con OpenAI chat/completions.

Funciona con Azure OpenAI (API v1), una pasarela como llm-gateway, OpenAI,
Google Gemini (endpoint compatible), Ollama...
"""

from __future__ import annotations

import time
from typing import Any

import requests


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        auth: str = "bearer",
        timeout: float = 120.0,
        session: requests.Session | None = None,
        sleep=time.sleep,
    ) -> None:
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.auth = auth.lower()
        self.timeout = timeout
        self.session = session or requests.Session()
        self._sleep = sleep

    def _post(self, body: dict[str, Any]) -> requests.Response:
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.auth == "api-key":
            headers["api-key"] = self.api_key  # Azure OpenAI con clave del recurso
        elif self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return self.session.post(self.url, json=body, headers=headers, timeout=self.timeout)

    def complete(self, messages: list[dict[str, str]], temperature: float = 0.1) -> str:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        for attempt in range(3):
            try:
                resp = self._post(body)
            except requests.RequestException as exc:
                if attempt == 2:
                    raise LLMError(f"No se pudo contactar con el modelo: {exc}") from exc
                self._sleep(2**attempt)
                continue
            if resp.status_code == 400 and "response_format" in body:
                # Algunos modelos no admiten el modo JSON: se reintenta sin él.
                body.pop("response_format")
                continue
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                self._sleep(2**attempt)
                continue
            if resp.status_code >= 400:
                raise LLMError(f"El modelo devolvió HTTP {resp.status_code}: {resp.text[:300]}")
            try:
                data = resp.json()
            except ValueError as exc:
                content_type = resp.headers.get("Content-Type", "?") if hasattr(resp, "headers") else "?"
                history = [f"{r.status_code} {r.url}" for r in getattr(resp, "history", [])]
                raise LLMError(
                    f"El modelo respondió HTTP {resp.status_code} ({content_type}) sin JSON: {resp.text[:300]!r}."
                    f" URL final: {getattr(resp, 'url', '?')}. Redirecciones: {history or 'ninguna'}"
                ) from exc
            try:
                return data["choices"][0]["message"]["content"] or ""
            except (KeyError, IndexError, TypeError) as exc:
                raise LLMError(f"Respuesta inesperada del modelo: {str(data)[:300]}") from exc
        raise LLMError("El modelo no respondió tras varios intentos.")
