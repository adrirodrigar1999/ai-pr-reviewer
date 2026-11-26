"""Configuración: entradas de la Action + fichero `.ai-review.yml` opcional del repositorio."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

Severity = Literal["high", "medium", "low"]
SEVERITY_ORDER: dict[str, int] = {"low": 1, "medium": 2, "high": 3}

DEFAULT_IGNORE = [
    "*.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "*.min.js",
    "*.min.css",
    "*.svg",
    "*.png",
    "*.jpg",
    "dist/*",
    "build/*",
    "vendor/*",
]


class RepoConfig(BaseModel):
    """Lo que cada repositorio puede personalizar en `.ai-review.yml`."""

    language: str = "español"
    rules: list[str] = Field(default_factory=list)
    ignore: list[str] = Field(default_factory=list)
    min_severity: Severity = "low"
    max_comments: int = Field(10, ge=1, le=50)


def load_repo_config(path: str | Path) -> RepoConfig:
    p = Path(path)
    if not p.exists():
        return RepoConfig()
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return RepoConfig.model_validate(data)
