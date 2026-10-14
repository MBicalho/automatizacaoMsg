from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google_sheets import (
    CONTROLE_HEADERS,
    MENSAGENS_HEADERS,
    GoogleSheetsClient,
    GoogleSheetsError,
    _column_to_a1,
)


class FakeRequest:
    def __init__(self, response):
        self.response = response

    def execute(self):
        return self.response


class FakeValues:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, **kwargs):
        self.calls.append(("get", kwargs))
        return FakeRequest(self.response)

    def batchUpdate(self, **kwargs):
        self.calls.append(("batchUpdate", kwargs))
        return FakeRequest({"totalUpdatedCells": 1})


class FakeSpreadsheets:
    def __init__(self, response, metadata=None):
        self.values_api = FakeValues(response)
        self.metadata = metadata or {"sheets": []}

    def values(self):
        return self.values_api

    def get(self, **kwargs):
        return FakeRequest(self.metadata)


class FakeService:
    def __init__(self, response, metadata=None):
        self.api = FakeSpreadsheets(response, metadata)

    def spreadsheets(self):
        return self.api


class GoogleSheetsClientTests(unittest.TestCase):
    def test_column_a1(self):
        self.assertEqual(_column_to_a1(1), "A")
        self.assertEqual(_column_to_a1(26), "Z")
        self.assertEqual(_column_to_a1(27), "AA")

    def test_reads_and_validates_headers(self):
        response = {
            "values": [
                list(MENSAGENS_HEADERS),
                ["Ola {{nome}}", "", "boas-vindas", 1],
            ]
        }
        client = GoogleSheetsClient(FakeService(response), "spreadsheet-id")
        headers, rows = client.validate_headers("Mensagem", MENSAGENS_HEADERS)

        self.assertEqual(headers, list(MENSAGENS_HEADERS))
        self.assertEqual(rows[0].row_number, 2)
        self.assertEqual(rows[0].values["Codigo_Mensagem"], "boas-vindas")

    def test_reports_missing_header(self):
        client = GoogleSheetsClient(FakeService({"values": [["Mensagem"]]}), "spreadsheet-id")

        with self.assertRaises(GoogleSheetsError):
            client.validate_headers("Mensagem", MENSAGENS_HEADERS)

    def test_updates_existing_control_column(self):
        response = {"values": [list(CONTROLE_HEADERS), ["07/10/2026", "Ana"]]}
        service = FakeService(response)
        client = GoogleSheetsClient(service, "spreadsheet-id")

        client.update_control_fields(2, {"Envio": "Processando"})

        method, request = service.api.values_api.calls[-1]
        self.assertEqual(method, "batchUpdate")
        self.assertEqual(request["body"]["data"][0]["range"], "'Controle'!G2")

    def test_reports_configured_tab_that_does_not_exist(self):
        client = GoogleSheetsClient(
            FakeService(
                {"values": []},
                {"sheets": [{"properties": {"title": "Controle de envios"}}]},
            ),
            "spreadsheet-id",
        )

        with self.assertRaisesRegex(GoogleSheetsError, "Abas disponiveis: Controle de envios"):
            client.validate_operational_layout()


if __name__ == "__main__":
    unittest.main()
