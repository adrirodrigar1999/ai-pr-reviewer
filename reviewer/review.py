"""Interpretación y validación de la respuesta del modelo.

Un LLM puede inventarse ficheros o números de línea. Antes de publicar nada se
comprueba que cada comentario apunta a una línea añadida que existe en el diff;
lo que no cumple se descarta y se cuenta.
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

    @field_validator("severity", "category", mode="before")
    @classmethod
    def _lower(cls, v):
        return v.strip().lower() if isinstance(v, str) else v

    @field_validator("suggestion", mode="before")
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


def parse_review(text: str, files: list[FileDiff], config: RepoConfig) -> Review:
    data = extract_json(text)
    valid_lines = {f.path: f.added_lines for f in files}
    findings: list[Finding] = []
    discarded = 0

    for raw in data.get("findings") or []:
        try:
            finding = Finding.model_validate(raw)
        except ValidationError:
            discarded += 1
            continue
        if finding.line not in valid_lines.get(finding.file, set()):
            discarded += 1
            continue
        if SEVERITY_ORDER[finding.severity] < SEVERITY_ORDER[config.min_severity]:
            continue
        findings.append(finding)

    # Sin duplicados en la misma línea, lo más grave primero y con tope de comentarios
    unique: dict[tuple[str, int], Finding] = {}
    for f in sorted(findings, key=lambda f: -SEVERITY_ORDER[f.severity]):
        unique.setdefault((f.file, f.line), f)
    ordered = list(unique.values())[: config.max_comments]

    return Review(summary=str(data.get("summary", "")).strip(), findings=ordered, discarded=discarded)
