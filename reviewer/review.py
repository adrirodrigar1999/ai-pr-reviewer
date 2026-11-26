"""Interpretación y validación de la respuesta del modelo.

Un LLM puede inventarse ficheros o números de línea. Antes de publicar nada:
1. Si el modelo cita el fragmento de código (`code`), el comentario se ancla a la línea
   añadida que de verdad contiene ese fragmento (los modelos pequeños suelen fallar el número).
2. Se comprueba que cada comentario apunta a una línea añadida que existe en el diff;
   lo que no cumple se descarta y se cuenta.
3. Se eliminan duplicados (misma línea, o mismo mensaje repetido en un fichero).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ValidationError, field_validator

from reviewer.config import SEVERITY_ORDER, RepoConfig
from reviewer.diff import FileDiff

Category = Literal["bug", "security", "tests", "performance", "maintainability"]


class Finding(BaseModel):
    file: str
    line: int
    severity: Literal["high", "medium", "low"]
    category: Category = "maintainability"
    message: str
    suggestion: str = ""
    code: str = ""

    @field_validator("severity", "category", mode="before")
    @classmethod
    def _lower(cls, v):
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("suggestion", "code", mode="before")
    @classmethod
    def _none_to_empty(cls, v):
        return v or ""


@dataclass
class Review:
    summary: str
    findings: list[Finding] = field(default_factory=list)
    discarded: int = 0  # comentarios descartados por apuntar fuera del diff o estar mal formados


def extract_json(text: str) -> dict:
    """Acepta JSON puro, JSON dentro de ```json ...``` o con texto alrededor."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("La respuesta del modelo no contiene JSON.")
    return json.loads(candidate[start : end + 1])


def _normalize(code: str) -> str:
    return " ".join(code.split())


def anchor(finding: Finding, file: FileDiff) -> int | None:
    """Devuelve la línea correcta para el hallazgo, o None si no se puede ubicar en el diff."""
    added = {ln.new_lineno: _normalize(ln.content) for ln in file.lines if ln.kind == "+" and ln.new_lineno}
    snippet = _normalize(finding.code)
    if not snippet:
        return finding.line if finding.line in added else None
    if snippet in added.get(finding.line, ""):
        return finding.line
    matches = [n for n, content in added.items() if snippet and snippet in content]
    if not matches:
        return None  # cita código que no está en las líneas añadidas
    return min(matches, key=lambda n: abs(n - finding.line))


def parse_review(text: str, files: list[FileDiff], config: RepoConfig) -> Review:
    data = extract_json(text)
    by_path = {f.path: f for f in files}
    findings: list[Finding] = []
    discarded = 0

    for raw in data.get("findings") or []:
        try:
            finding = Finding.model_validate(raw)
        except ValidationError:
            discarded += 1
            continue
        file = by_path.get(finding.file)
        line = anchor(finding, file) if file else None
        if line is None:
            discarded += 1
            continue
        finding.line = line
        if SEVERITY_ORDER[finding.severity] < SEVERITY_ORDER[config.min_severity]:
            continue
        findings.append(finding)

    # Sin duplicados (misma línea o mismo mensaje en el fichero), lo más grave primero y con tope
    seen_lines: set[tuple[str, int]] = set()
    seen_messages: set[tuple[str, str]] = set()
    ordered: list[Finding] = []
    for f in sorted(findings, key=lambda f: -SEVERITY_ORDER[f.severity]):
        msg_key = (f.file, _normalize(f.message).lower())
        if (f.file, f.line) in seen_lines or msg_key in seen_messages:
            continue
        seen_lines.add((f.file, f.line))
        seen_messages.add(msg_key)
        ordered.append(f)
    ordered = ordered[: config.max_comments]

    return Review(summary=str(data.get("summary", "")).strip(), findings=ordered, discarded=discarded)
