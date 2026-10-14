"""Sincronizacao transacional do catalogo de mensagens entre Google Sheets e SQL Server."""

from __future__ import annotations

import re
from typing import Any
import sqlalchemy as sa

from file_validator import resolve_and_validate_attachment
from functions import dataBase
from google_sheets import MENSAGENS_HEADERS, GoogleSheetsClient, GoogleSheetsError


class MessageCatalogValidationError(ValueError):
    """Erro de validacao nas regras do catalogo de mensagens."""


def parse_boolean_ativo(val: Any) -> int:
    """Converte valores variados de planilha para bit 1 ou 0."""
    if val is None or val == "":
        return 0
    str_val = str(val).strip().lower()
    if str_val in ("1", "true", "sim", "ativo", "s"):
        return 1
    return 0


class MessageCatalogSync:
    """Sincroniza a aba Mensagem da planilha com a tabela MENSAGEM_WPP do banco."""

    def __init__(self, sheets_client: GoogleSheetsClient, db: dataBase | None = None) -> None:
        self.sheets = sheets_client
        self.db = db or dataBase()

    def sync(self) -> dict[str, int]:
        """
        Executa a sincronizacao transacional:
        1. Le e valida cabecalhos da aba Mensagem.
        2. Valida unicidade e regras de cada Codigo_Mensagem.
        3. Valida caminhos de arquivos anexos.
        4. Executa upsert no SQL Server mantendo integridade historica.
        """
        headers, rows = self.sheets.validate_headers(self.sheets.mensagens_tab, MENSAGENS_HEADERS)

        seen_codes: dict[str, int] = {}
        validated_messages: list[dict[str, Any]] = []

        for row in rows:
            codigo = str(row.values.get("Codigo_Mensagem", "")).strip()
            if not codigo:
                continue

            if "," in codigo or ";" in codigo:
                raise MessageCatalogValidationError(
                    f"Linha {row.row_number}: Codigo_Mensagem '{codigo}' nao pode conter virgula ou ponto-e-virgula."
                )

            if not re.match(r"^[a-zA-Z0-9_\-]+$", codigo):
                raise MessageCatalogValidationError(
                    f"Linha {row.row_number}: Codigo_Mensagem '{codigo}' contem caracteres invalidos. "
                    "Use apenas letras, numeros, hifens e underscores."
                )

            codigo_lower = codigo.lower()
            if codigo_lower in seen_codes:
                raise MessageCatalogValidationError(
                    f"Codigo_Mensagem duplicado '{codigo}' na linha {row.row_number} (ja definido na linha {seen_codes[codigo_lower]})."
                )
            seen_codes[codigo_lower] = row.row_number

            raw_file = str(row.values.get("Arquivo", "")).strip()
            resolved_file_path = None
            if raw_file:
                # Valida arquivo contra seguranca de diretoria
                file_obj = resolve_and_validate_attachment(raw_file, must_exist=False)
                resolved_file_path = str(file_obj) if file_obj else None

            texto_mensagem = str(row.values.get("Mensagem", "")).strip()
            ativo = parse_boolean_ativo(row.values.get("Ativo"))

            validated_messages.append({
                "codigo": codigo,
                "texto": texto_mensagem if texto_mensagem else None,
                "arquivo": resolved_file_path,
                "ativo": ativo,
            })

        if not validated_messages:
            return {"inserted": 0, "updated": 0, "total": 0}

        engine = self.db.connectDataBase()
        if isinstance(engine, tuple) and not engine[0]:
            raise RuntimeError(f"Erro de conexao ao SQL Server: {engine[1]}")

        inserted_count = 0
        updated_count = 0

        with engine.begin() as conn:
            for item in validated_messages:
                existing = conn.execute(
                    sa.text(f"""
                        SELECT ID_MENSAGEM, DESCRICAO_MENSAGEM, ARQUIVO, ATIVO
                        FROM {self.db.dataBase}.{self.db.schema}.MENSAGEM_WPP
                        WHERE CODIGO_MENSAGEM = :cod
                    """),
                    {"cod": item["codigo"]}
                ).fetchone()

                if existing:
                    # Atualiza registro existente
                    conn.execute(
                        sa.text(f"""
                            UPDATE {self.db.dataBase}.{self.db.schema}.MENSAGEM_WPP
                            SET DESCRICAO_MENSAGEM = :texto,
                                ARQUIVO = :arquivo,
                                ATIVO = :ativo,
                                DATA_ATUALIZACAO = SYSDATETIME()
                            WHERE CODIGO_MENSAGEM = :cod
                        """),
                        {
                            "texto": item["texto"],
                            "arquivo": item["arquivo"],
                            "ativo": item["ativo"],
                            "cod": item["codigo"],
                        }
                    )
                    updated_count += 1
                else:
                    # Insere novo registro
                    conn.execute(
                        sa.text(f"""
                            INSERT INTO {self.db.dataBase}.{self.db.schema}.MENSAGEM_WPP
                                (DESCRICAO_MENSAGEM, CODIGO_MENSAGEM, ARQUIVO, ATIVO, DATA_CRIACAO, DATA_ATUALIZACAO)
                            VALUES
                                (:texto, :cod, :arquivo, :ativo, SYSDATETIME(), SYSDATETIME())
                        """),
                        {
                            "texto": item["texto"],
                            "cod": item["codigo"],
                            "arquivo": item["arquivo"],
                            "ativo": item["ativo"],
                        }
                    )
                    inserted_count += 1

        return {
            "inserted": inserted_count,
            "updated": updated_count,
            "total": len(validated_messages),
        }
