"""Cliente minimo e testavel para a API oficial do Google Sheets."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from dotenv import load_dotenv


SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"

MENSAGENS_HEADERS = ("Mensagem", "Arquivo", "Codigo_Mensagem", "Ativo")
CONTROLE_HEADERS = (
    "Data",
    "Nome",
    "Contato",
    "Mensagem",
    "Ultima Mensagem Enviada",
    "Ultima Mensagem Recebida",
    "Envio",
    "Último contato",
)
CONTROL_ID_HEADER = "ID_Controle"


class GoogleSheetsError(RuntimeError):
    """Erro de configuracao, leitura ou escrita na planilha."""


@dataclass(frozen=True)
class SheetRow:
    """Linha da planilha com numero estavel apenas para a atualizacao atual."""

    row_number: int
    values: Mapping[str, Any]


def _quote_sheet_name(sheet_name: str) -> str:
    return "'" + sheet_name.replace("'", "''") + "'"


def _column_to_a1(column_index: int) -> str:
    """Converte indice iniciado em 1 na notacao A1 (1 -> A, 27 -> AA)."""
    if column_index < 1:
        raise ValueError("O indice da coluna deve iniciar em 1.")

    result = ""
    while column_index:
        column_index, remainder = divmod(column_index - 1, 26)
        result = chr(65 + remainder) + result
    return result


class GoogleSheetsClient:
    """Encapsula leitura e escrita em uma unica planilha configurada."""

    def __init__(
        self,
        service: Any,
        spreadsheet_id: str,
        mensagens_tab: str = "Mensagens",
        controle_tab: str = "Controle",
    ) -> None:
        if not spreadsheet_id:
            raise GoogleSheetsError("GOOGLE_SHEETS_SPREADSHEET_ID nao foi configurado.")
        self._service = service
        self.spreadsheet_id = spreadsheet_id
        self.mensagens_tab = mensagens_tab
        self.controle_tab = controle_tab

    @classmethod
    def from_environment(cls) -> "GoogleSheetsClient":
        """Cria o cliente com uma conta de servico, sem imprimir credenciais."""
        load_dotenv(override=True)
        spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "").strip()
        credential_file = os.getenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE", "").strip()

        if not credential_file:
            raise GoogleSheetsError("GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE nao foi configurado.")
        if not Path(credential_file).is_file():
            raise GoogleSheetsError("O arquivo de credenciais da conta de servico nao foi encontrado.")

        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build
        except ImportError as ex:
            raise GoogleSheetsError(
                "Dependencias do Google Sheets ausentes. Execute pip install -r requirements.txt."
            ) from ex

        credentials = Credentials.from_service_account_file(
            credential_file,
            scopes=[SHEETS_SCOPE],
        )
        service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        return cls(
            service=service,
            spreadsheet_id=spreadsheet_id,
            mensagens_tab=os.getenv("GOOGLE_SHEETS_MENSAGENS_TAB", "Mensagens"),
            controle_tab=os.getenv("GOOGLE_SHEETS_CONTROLE_TAB", "Controle"),
        )

    def read_table(self, sheet_name: str) -> tuple[list[str], list[SheetRow]]:
        """Le uma aba por linhas usando valores brutos da API, sem automacao visual."""
        try:
            response = (
                self._service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{_quote_sheet_name(sheet_name)}!A:ZZ",
                    majorDimension="ROWS",
                    valueRenderOption="UNFORMATTED_VALUE",
                )
                .execute()
            )
        except Exception as ex:
            raise GoogleSheetsError(f"Falha ao ler a aba '{sheet_name}'.") from ex
        values: list[list[Any]] = response.get("values", [])
        if not values:
            raise GoogleSheetsError(f"A aba '{sheet_name}' esta vazia.")

        headers = [str(value).strip() for value in values[0]]
        if not any(headers):
            raise GoogleSheetsError(f"A aba '{sheet_name}' nao possui cabecalhos.")
        if len(headers) != len(set(headers)):
            raise GoogleSheetsError(f"A aba '{sheet_name}' possui cabecalhos duplicados.")

        rows: list[SheetRow] = []
        for row_number, source_row in enumerate(values[1:], start=2):
            padded = list(source_row) + [""] * (len(headers) - len(source_row))
            record = dict(zip(headers, padded[: len(headers)]))
            if any(value not in (None, "") for value in record.values()):
                rows.append(SheetRow(row_number=row_number, values=record))
        return headers, rows

    def list_sheet_names(self) -> list[str]:
        """Retorna os nomes reais das abas configuradas na planilha."""
        try:
            response = (
                self._service.spreadsheets()
                .get(
                    spreadsheetId=self.spreadsheet_id,
                    fields="sheets.properties.title",
                )
                .execute()
            )
        except Exception as ex:
            raise GoogleSheetsError("Falha ao consultar as abas da planilha.") from ex

        return [
            sheet["properties"]["title"]
            for sheet in response.get("sheets", [])
            if "properties" in sheet and "title" in sheet["properties"]
        ]

    def validate_headers(
        self,
        sheet_name: str,
        required_headers: Sequence[str],
    ) -> tuple[list[str], list[SheetRow]]:
        headers, rows = self.read_table(sheet_name)
        missing = [header for header in required_headers if header not in headers]
        if missing:
            raise GoogleSheetsError(
                f"A aba '{sheet_name}' nao possui os cabecalhos obrigatorios: {', '.join(missing)}."
            )
        return headers, rows

    def validate_operational_layout(self) -> dict[str, bool]:
        """Valida as duas abas e informa se o identificador tecnico ja existe."""
        available_tabs = self.list_sheet_names()
        required_tabs = (self.mensagens_tab, self.controle_tab)
        missing_tabs = [tab for tab in required_tabs if tab not in available_tabs]
        if missing_tabs:
            available = ", ".join(available_tabs) or "nenhuma"
            raise GoogleSheetsError(
                "Abas configuradas inexistentes: "
                + ", ".join(missing_tabs)
                + f". Abas disponiveis: {available}."
            )
        self.validate_headers(self.mensagens_tab, MENSAGENS_HEADERS)
        control_headers, _ = self.validate_headers(self.controle_tab, CONTROLE_HEADERS)
        return {"control_id_present": CONTROL_ID_HEADER in control_headers}

    def batch_update(self, updates: Iterable[tuple[str, Sequence[Sequence[Any]]]]) -> dict[str, Any]:
        """Atualiza valores em lote. Cada item e um par (intervalo A1, valores)."""
        data = [
            {"range": range_name, "values": [list(row) for row in values]}
            for range_name, values in updates
        ]
        if not data:
            return {"totalUpdatedCells": 0}

        return (
            self._service.spreadsheets()
            .values()
            .batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={"valueInputOption": "RAW", "data": data},
            )
            .execute()
        )

    def update_control_fields(
        self,
        row_number: int,
        values_by_header: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Atualiza campos existentes de uma linha sem depender do numero como ID logico."""
        headers, _ = self.read_table(self.controle_tab)
        unknown_headers = set(values_by_header) - set(headers)
        if unknown_headers:
            raise GoogleSheetsError(
                "Cabecalhos inexistentes na aba Controle: " + ", ".join(sorted(unknown_headers))
            )

        updates = []
        for header, value in values_by_header.items():
            column = _column_to_a1(headers.index(header) + 1)
            cell = f"{_quote_sheet_name(self.controle_tab)}!{column}{row_number}"
            updates.append((cell, [[value]]))
        return self.batch_update(updates)
