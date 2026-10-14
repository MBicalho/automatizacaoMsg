"""Utilitarios para normalizacao, validacao e mascaramento seguro de telefones brasileiros."""

from __future__ import annotations

import re


# DDDs geograficos validos no Brasil (Anatel)
VALID_DDDS = {
    # SP
    11, 12, 13, 14, 15, 16, 17, 18, 19,
    # RJ / ES
    21, 22, 24, 27, 28,
    # MG
    31, 32, 33, 34, 35, 37, 38,
    # PR / SC
    41, 42, 43, 44, 45, 46, 47, 48, 49,
    # RS
    51, 53, 54, 55,
    # CO / TO
    61, 62, 63, 64, 65, 66, 67, 68, 69,
    # Nordeste
    71, 73, 74, 75, 77, 79,
    81, 82, 83, 84, 85, 86, 87, 88, 89,
    # Norte
    91, 92, 93, 94, 95, 96, 97, 98, 99,
}


class InvalidPhoneNumberError(ValueError):
    """Excecao para numeros de telefone fora do padrao brasileiro aceito."""


def normalize_brazilian_phone(phone_input: str | int | float | None) -> str:
    """
    Normaliza um numero de telefone brasileiro para o formato internacional somente digitos:
    '55' + DDD (2 digitos) + numero (8 ou 9 digitos).
    Exemplos aceitos:
      '(11) 98765-4321' -> '5511987654321'
      '+55 11 98765-4321' -> '5511987654321'
      '11987654321' -> '5511987654321'
      '5511987654321' -> '5511987654321'
      '1133334444' -> '551133334444' (fixo)
    """
    if phone_input is None:
        raise InvalidPhoneNumberError("Telefone nao pode ser nulo.")

    # Converte numero de ponto flutuante do Excel/Sheets se vier como float
    raw_str = str(phone_input).split(".")[0].strip()
    digits = re.sub(r"\D", "", raw_str)

    if not digits:
        raise InvalidPhoneNumberError("Telefone vazio ou sem digitos.")

    # Se comeca com 0 no DDD (ex: 011987654321), remove o 0 inicial
    if digits.startswith("0") and len(digits) in (11, 12):
        digits = digits[1:]

    # Ajusta presenca ou ausencia do DDI 55
    if digits.startswith("55"):
        # Pode ter 12 (55 + 2 ddd + 8 fixo) ou 13 (55 + 2 ddd + 9 celular)
        if len(digits) in (12, 13):
            national_digits = digits[2:]
        elif len(digits) in (10, 11):
            # Caso raro onde o DDD e 55 (RS) e nao tem DDI
            national_digits = digits
            digits = "55" + national_digits
        else:
            raise InvalidPhoneNumberError(
                f"Tamanho invalido ({len(digits)} digitos) para numero internacional brasileiro."
            )
    else:
        # Sem DDI: deve ter 10 digitos (DDD + fixo) ou 11 digitos (DDD + celular)
        if len(digits) in (10, 11):
            national_digits = digits
            digits = "55" + national_digits
        else:
            raise InvalidPhoneNumberError(
                f"Tamanho invalido ({len(digits)} digitos). Esperado 10 ou 11 digitos nacionais."
            )

    ddd = int(national_digits[:2])
    if ddd not in VALID_DDDS:
        raise InvalidPhoneNumberError(f"DDD '{ddd}' nao e um DDD geografico valido no Brasil.")

    subscriber_number = national_digits[2:]
    if len(subscriber_number) == 9:
        if not subscriber_number.startswith("9"):
            raise InvalidPhoneNumberError("Celular de 9 digitos deve iniciar com o digito 9.")
    elif len(subscriber_number) == 8:
        # Fixos costumam comecar com digitos entre 2 e 5
        if subscriber_number.startswith("0") or subscriber_number.startswith("1"):
            raise InvalidPhoneNumberError(
                "Numero fixo de 8 digitos nao pode iniciar com 0 ou 1."
            )
    else:
        raise InvalidPhoneNumberError(
            f"Numero do assinante invalido ({len(subscriber_number)} digitos). Esperado 8 ou 9."
        )

    return digits


def mask_phone(phone_input: str | None) -> str:
    """
    Retorna uma representacao mascarada do telefone para logs seguros e auditoria (LGPD).
    Exemplo: '5511987654321' -> '+55 (11) *****-4321'
    """
    if not phone_input:
        return "[VAZIO]"

    raw_str = str(phone_input).split(".")[0].strip()
    digits = re.sub(r"\D", "", raw_str)

    if len(digits) >= 12:
        # Internacional: DDI 55 + DDD 2 + resto
        ddd = digits[2:4]
        last4 = digits[-4:]
        return f"+55 ({ddd}) *****-{last4}"
    elif len(digits) >= 10:
        ddd = digits[:2]
        last4 = digits[-4:]
        return f"({ddd}) *****-{last4}"
    elif len(digits) >= 4:
        return f"***{digits[-4:]}"
    return "***"
