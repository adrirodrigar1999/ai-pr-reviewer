"""Análisis de diffs unificados (formato `git diff`).

Convierte el diff de un PR en estructuras con los números de línea del fichero nuevo,
para poder (1) enseñar al modelo exactamente qué ha cambiado y (2) comprobar después
que cada comentario apunta a una línea que existe en el diff.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass
class Line:
    kind: str  # "+", "-" o " "
    content: str
    new_lineno: int | None  # None para líneas eliminadas


@dataclass
class FileDiff:
    path: str
    is_new: bool = False
    is_deleted: bool = False
    is_binary: bool = False
    lines: list[Line] = field(default_factory=list)

    @property
    def added_lines(self) -> set[int]:
        return {ln.new_lineno for ln in self.lines if ln.kind == "+" and ln.new_lineno is not None}

    @property
    def additions(self) -> int:
        return sum(1 for ln in self.lines if ln.kind == "+")

    def render(self) -> str:
        """Texto para el modelo: cada línea nueva lleva su número para que pueda citarla."""
        out = [f"### {self.path}" + (" (nuevo)" if self.is_new else "")]
        for ln in self.lines:
            if ln.kind == "@":
                out.append(ln.content)
            elif ln.kind == "-":
                out.append(f"      - {ln.content}")
            else:
                out.append(f"{ln.new_lineno:>5} {ln.kind} {ln.content}")
        return "\n".join(out)


def parse_diff(text: str) -> list[FileDiff]:
    files: list[FileDiff] = []
    current: FileDiff | None = None
    new_lineno = 0

    for raw in text.splitlines():
        if raw.startswith("diff --git "):
            match = re.match(r"diff --git a/(.+?) b/(.+)$", raw)
            current = FileDiff(path=match.group(2) if match else raw.split()[-1])
            files.append(current)
            continue
        if current is None:
            continue
        if raw.startswith("new file mode"):
            current.is_new = True
        elif raw.startswith("deleted file mode"):
            current.is_deleted = True
        elif raw.startswith("Binary files") or raw.startswith("GIT binary patch"):
            current.is_binary = True
        elif raw.startswith("+++ "):
            target = raw[4:].strip()
            if target != "/dev/null":
                current.path = target[2:] if target.startswith("b/") else target
        elif raw.startswith("--- ") or raw.startswith("index ") or raw.startswith("similarity index"):
            continue
        elif raw.startswith("rename from ") or raw.startswith("rename to "):
            if raw.startswith("rename to "):
                current.path = raw[len("rename to ") :]
        elif raw.startswith("@@"):
            match = _HUNK_HEADER.match(raw)
            if match:
                new_lineno = int(match.group(3))
                current.lines.append(Line("@", raw, None))
        elif raw.startswith("+"):
            current.lines.append(Line("+", raw[1:], new_lineno))
            new_lineno += 1
        elif raw.startswith("-"):
            current.lines.append(Line("-", raw[1:], None))
        elif raw.startswith(" ") or raw == "":
            current.lines.append(Line(" ", raw[1:] if raw else "", new_lineno))
            new_lineno += 1
        # "\ No newline at end of file" y similares se ignoran
    return files


def filter_files(files: list[FileDiff], ignore_patterns: list[str]) -> tuple[list[FileDiff], list[str]]:
    """Quita ficheros borrados, binarios o que coinciden con los patrones a ignorar."""
    kept, skipped = [], []
    for f in files:
        if f.is_deleted or f.is_binary or not f.added_lines or any(fnmatch.fnmatch(f.path, p) for p in ignore_patterns):
            skipped.append(f.path)
        else:
            kept.append(f)
    return kept, skipped


def fit_to_budget(files: list[FileDiff], max_chars: int) -> tuple[list[FileDiff], list[str]]:
    """Mete ficheros completos hasta agotar el presupuesto de caracteres (los más pequeños primero)."""
    selected, dropped, used = [], [], 0
    for f in sorted(files, key=lambda f: len(f.render())):
        size = len(f.render())
        if used + size <= max_chars:
            selected.append(f)
            used += size
        else:
            dropped.append(f.path)
    order = {f.path: i for i, f in enumerate(files)}
    selected.sort(key=lambda f: order[f.path])
    return selected, dropped
