"""Testes unitarios para a sincronizacao de respostas dos leads."""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sync_incoming import IncomingMessagesSync, _extract_message_text
from google_sheets import SheetRow


class TestIncomingMessagesSync(unittest.TestCase):
    def test_extract_message_text(self):
        # Texto simples
        self.assertEqual(_extract_message_text({"conversation": "Ola"}, "conversation"), "Ola")
        # Extended text
        self.assertEqual(_extract_message_text({"extendedTextMessage": {"text": "Tudo bem?"}}, "extendedTextMessage"), "Tudo bem?")
        # Audio
        self.assertEqual(_extract_message_text({"audioMessage": {}}, "audioMessage"), "[Áudio]")
        # Imagem com legenda
        self.assertEqual(_extract_message_text({"imageMessage": {"caption": "Comprovante"}}, "imageMessage"), "[Imagem: Comprovante]")
        # Imagem sem legenda
        self.assertEqual(_extract_message_text({"imageMessage": {}}, "imageMessage"), "[Imagem]")
        # Midia fallback por tipo
        self.assertEqual(_extract_message_text(None, "audioMessage"), "[Áudio]")

    def test_fetch_latest_responses_for_phone(self):
        syncer = IncomingMessagesSync(sheets_client=MagicMock(), db_url="sqlite://")
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        # Simulando mensagens no chat:
        # t=100: Enviada por nos ("Oi")
        # t=150: Recebida do lead ("Ola")
        # t=160: Recebida do lead ("Tenho interesse")
        mock_cur.fetchall.return_value = [
            ("1", True, "553199999999@s.whatsapp.net", 100, "Oi", {"conversation": "Oi"}, "conversation"),
            ("2", False, "553199999999@s.whatsapp.net", 150, "Ola", {"conversation": "Ola"}, "conversation"),
            ("3", False, "553199999999@s.whatsapp.net", 160, "Tenho interesse", {"conversation": "Tenho interesse"}, "conversation"),
        ]

        texts, last_dt = syncer.fetch_latest_responses_for_phone(mock_conn, "553199999999")
        self.assertEqual(texts, ["Ola", "Tenho interesse"])
        self.assertIsNotNone(last_dt)

    def test_no_responses_after_our_latest_sent(self):
        syncer = IncomingMessagesSync(sheets_client=MagicMock(), db_url="sqlite://")
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        # Simulando:
        # t=100: Recebida ("Antiga")
        # t=200: Enviada por nos ("Mais recente")
        mock_cur.fetchall.return_value = [
            ("1", False, "553199999999@s.whatsapp.net", 100, "Antiga", {"conversation": "Antiga"}, "conversation"),
            ("2", True, "553199999999@s.whatsapp.net", 200, "Mais recente", {"conversation": "Mais recente"}, "conversation"),
        ]

        texts, last_dt = syncer.fetch_latest_responses_for_phone(mock_conn, "553199999999")
        self.assertEqual(texts, [])
        self.assertIsNone(last_dt)

    def test_sync_incoming_messages_updates_sheets(self):
        mock_sheets = MagicMock()
        mock_sheets.controle_tab = "Controle"
        mock_sheets.read_table.return_value = (
            ["Contato", "Nome", "Ultima Mensagem Recebida", "Último contato"],
            [
                SheetRow(
                    row_number=2,
                    values={"Contato": "(31) 9999-9999", "Nome": "Joao", "Ultima Mensagem Recebida": "", "Último contato": ""}
                )
            ]
        )

        syncer = IncomingMessagesSync(sheets_client=mock_sheets, db_url="sqlite://")
        syncer._get_db_connection = MagicMock()

        dt = datetime(2026, 10, 17, 20, 30, tzinfo=ZoneInfo("America/Sao_Paulo"))
        with patch.object(syncer, "fetch_latest_responses_for_phone", return_value=(["Oi", "Tudo bem?"], dt)):
            res = syncer.sync_incoming_messages()

        self.assertEqual(res["checked"], 1)
        self.assertEqual(res["updated"], 1)
        mock_sheets.update_control_fields.assert_called_once_with(
            2,
            {
                "Ultima Mensagem Recebida": "Oi | Tudo bem? (17/10/2026 20:30)",
                "Último contato": "17/10/2026 20:30",
            }
        )


if __name__ == "__main__":
    unittest.main()
