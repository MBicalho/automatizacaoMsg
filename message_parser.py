"""Tratamento e parsing de codigos de mensagens, preservacao de ordem e renderizacao de variaveis."""

from __future__ import annotations

import re
from typing import Any, Mapping


def parse_message_codes(raw_input: Any) -> list[str]:
    """
    Extrai a lista de codigos de mensagem mantendo rigorosamente a ordem original.
    NUNCA ordena alfabeticamente.
    Suporta separadores por virgula, ponto e virgula ou quebra de linha.
    Exemplo: 'boas-vindas, apresentacao, interesse' -> ['boas-vindas', 'apresentacao', 'interesse']
    """
    if raw_input is None:
        return []

    if isinstance(raw_input, (list, tuple)):
        items = raw_input
    else:
        text = str(raw_input).strip()
        if not text:
            return []
        # Divide por virgula, ponto-e-virgula ou quebra de linha
        items = re.split(r"[,;\n\r]+", text)

    result: list[str] = []
    for item in items:
        clean = str(item).strip()
        if clean and clean not in ("", "-"):
            result.append(clean)

    return result


def extract_first_name(full_name: str | None) -> str:
    """Extrai o primeiro nome de forma amigavel e capitalizada."""
    if not full_name:
        return ""
    parts = str(full_name).strip().split()
    if not parts:
        return ""
    return parts[0].capitalize()


def render_message_text(template: str | None, context: Mapping[str, Any]) -> str:
    """
    Renderiza o template de mensagem substituindo variaveis como {{nome}}.
    Se {{nome}} estiver no texto e o contexto tiver 'nome', substitui pelo primeiro nome.
    Tambem suporta {{nome_completo}}.
    """
    if not template:
        return ""

    rendered = str(template)

    raw_nome = context.get("nome") or context.get("Nome") or ""
    first_name = extract_first_name(raw_nome)
    full_name = str(raw_nome).strip()

    # Substitui {{nome}} de forma case-insensitive
    rendered = re.sub(r"\{\{\s*nome\s*\}\}", first_name, rendered, flags=re.IGNORECASE)
    # Substitui {{nome_completo}}
    rendered = re.sub(r"\{\{\s*nome_completo\s*\}\}", full_name, rendered, flags=re.IGNORECASE)

    return rendered
