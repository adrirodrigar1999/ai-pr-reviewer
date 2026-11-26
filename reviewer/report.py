"""Texto en Markdown de la revisión (comentario resumen y comentarios en línea)."""

from __future__ import annotations

from reviewer.review import Finding, Review

MARKER = "<!-- ai-pr-reviewer -->"
ICONS = {"high": "🔴", "medium": "🟠", "low": "🟡"}
LABELS = {"high": "Alta", "medium": "Media", "low": "Baja"}
CATEGORIES = {
    "bug": "Error",
    "security": "Seguridad",
    "tests": "Tests",
    "performance": "Rendimiento",
    "maintainability": "Mantenibilidad",
}


def inline_comment(f: Finding) -> str:
    text = f"{ICONS[f.severity]} **{CATEGORIES[f.category]} · prioridad {LABELS[f.severity].lower()}**\n\n{f.message}"
    if f.suggestion:
        text += f"\n\n**Sugerencia:** {f.suggestion}"
    return text


def summary_body(review: Review, model: str, reviewed: list[str], skipped: list[str], dropped: list[str]) -> str:
    counts = {s: sum(1 for f in review.findings if f.severity == s) for s in ("high", "medium", "low")}
    lines = [MARKER, "## 🤖 Revisión automática con IA", "", review.summary or "_Sin resumen._", ""]
    if review.findings:
        lines.append(
            " · ".join(f"{ICONS[s]} {LABELS[s]}: **{n}**" for s, n in counts.items() if n)
            + "  — detalles en los comentarios del código."
        )
    else:
        lines.append("✅ No se han encontrado problemas relevantes en las líneas añadidas.")
    lines += ["", "<details><summary>Detalles de la revisión</summary>", ""]
    lines.append(f"- Modelo: `{model}`")
    lines.append(f"- Ficheros revisados: {len(reviewed)}")
    if skipped:
        lines.append(f"- Omitidos (ignorados, binarios o sin líneas nuevas): {', '.join(f'`{p}`' for p in skipped)}")
    if dropped:
        lines.append(f"- No revisados por tamaño del diff: {', '.join(f'`{p}`' for p in dropped)}")
    if review.discarded:
        lines.append(f"- Comentarios descartados por apuntar fuera del diff: {review.discarded}")
    lines += ["", "</details>", "", "_Revisión orientativa generada por IA: no sustituye a la revisión humana._"]
    return "\n".join(lines)


def markdown_report(review: Review, body: str) -> str:
    """Versión completa para la ejecución local (--diff-file): resumen + comentarios."""
    parts = [body]
    for f in review.findings:
        parts.append(f"---\n**`{f.file}:{f.line}`**\n\n{inline_comment(f)}")
    return "\n\n".join(parts)
