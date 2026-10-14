"""Regras de elegibilidade de contatos: todo contato cadastrado e considerado apto para envio."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class EligibilityResult:
    is_eligible: bool
    reason: str
    consent_status: str
    is_blocked: bool


def evaluate_consent_eligibility(
    contact_record: Mapping[str, Any] | None = None,
    require_opt_in: bool | None = False,
) -> EligibilityResult:
    """
    Retorna sempre apto para envio: todo contato cadastrado na tabela esta apto
    a receber mensagem se o operador da planilha colocar 'Pendente' e escolher a mensagem.
    """
    return EligibilityResult(
        is_eligible=True,
        reason="Contato apto para envio.",
        consent_status="ATIVO",
        is_blocked=False,
    )
