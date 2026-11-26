"""Construcción del prompt para el modelo."""

from __future__ import annotations

from reviewer.config import RepoConfig
from reviewer.diff import FileDiff

SYSTEM_PROMPT = """Eres un revisor de código sénior. Revisas pull requests de forma rigurosa pero útil.

Céntrate SOLO en problemas reales de las líneas añadidas (marcadas con +):
- bug: errores de lógica, casos límite, excepciones no controladas, condiciones de carrera
- security: inyección, secretos en el código, validación de entradas, permisos
- tests: lógica nueva o modificada sin tests
- performance: trabajo innecesario evidente (bucles anidados, consultas repetidas)
- maintainability: solo si dificulta claramente entender o cambiar el código

No comentes estilo, formato ni gustos personales. Si no hay problemas, devuelve una lista vacía:
es mejor no comentar que comentar algo dudoso.

Responde ÚNICAMENTE con un objeto JSON con este formato:
{
  "summary": "2-3 frases sobre qué hace el PR y su calidad general",
  "findings": [
    {
      "file": "ruta/del/fichero.py",
      "line": 42,
      "severity": "high | medium | low",
      "category": "bug | security | tests | performance | maintainability",
      "message": "qué problema hay y por qué importa",
      "suggestion": "cómo arreglarlo (opcional)"
    }
  ]
}

`line` debe ser el número que aparece a la izquierda de una línea marcada con `+`."""


def build_messages(files: list[FileDiff], config: RepoConfig, title: str = "", body: str = "") -> list[dict[str, str]]:
    parts = [f"Escribe `summary`, `message` y `suggestion` en {config.language}."]
    if config.rules:
        parts.append("Reglas específicas de este repositorio:\n" + "\n".join(f"- {r}" for r in config.rules))
    if title:
        parts.append(f"Título del PR: {title}")
    if body:
        parts.append(f"Descripción del PR:\n{body[:2000]}")
    parts.append("Diff (número de línea en el fichero nuevo, tipo de línea y contenido):\n\n")
    user = "\n\n".join(parts) + "\n\n".join(f.render() for f in files)
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]
