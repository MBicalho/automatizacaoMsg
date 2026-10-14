from unittest.mock import MagicMock
import unittest

from google_sheets import GoogleSheetsClient, SheetRow
from sync_messages import MessageCatalogSync, MessageCatalogValidationError
from sync_queue import QueueSync


class SyncAndQueueTests(unittest.TestCase):
    def test_catalog_rejects_comma_in_message_code(self):
        client = MagicMock(spec=GoogleSheetsClient)
        client.mensagens_tab = "Mensagem"
        client.validate_headers.return_value = (
            ["Mensagem", "Arquivo", "Codigo_Mensagem", "Ativo"],
            [SheetRow(2, {"Mensagem": "Ola", "Arquivo": "", "Codigo_Mensagem": "cod1,cod2", "Ativo": 1})],
        )
        sync = MessageCatalogSync(client, db=MagicMock())
        with self.assertRaises(MessageCatalogValidationError):
            sync.sync()

    def test_catalog_rejects_duplicate_message_code(self):
        client = MagicMock(spec=GoogleSheetsClient)
        client.mensagens_tab = "Mensagem"
        client.validate_headers.return_value = (
            ["Mensagem", "Arquivo", "Codigo_Mensagem", "Ativo"],
            [
                SheetRow(2, {"Mensagem": "Ola 1", "Arquivo": "", "Codigo_Mensagem": "boas-vindas", "Ativo": 1}),
                SheetRow(3, {"Mensagem": "Ola 2", "Arquivo": "", "Codigo_Mensagem": "boas-vindas", "Ativo": 1}),
            ],
        )
        sync = MessageCatalogSync(client, db=MagicMock())
        with self.assertRaises(MessageCatalogValidationError):
            sync.sync()

    def test_ensure_missing_control_ids_generates_and_updates(self):
        client = MagicMock(spec=GoogleSheetsClient)
        client.controle_tab = "Controle"
        client.read_table.return_value = (
            ["ID_CONTROLE", "Data", "Nome", "Contato", "Mensagem", "Envio"],
            [
                SheetRow(2, {"ID_CONTROLE": "CTRL-123", "Nome": "Ana", "Contato": "11988887777"}),
                SheetRow(3, {"ID_CONTROLE": "", "Nome": "Bruno", "Contato": "11999998888"}),
            ],
        )
        queue_sync = QueueSync(client, db=MagicMock())
        count = queue_sync.ensure_missing_control_ids()
        self.assertEqual(count, 1)
        client.update_control_fields.assert_called_once()
        args = client.update_control_fields.call_args[0]
        self.assertEqual(args[0], 3)
        self.assertTrue(args[1]["ID_CONTROLE"].startswith("CTRL-"))

    def test_get_or_create_contact_updates_on_phone_change(self):
        client = MagicMock(spec=GoogleSheetsClient)
        db = MagicMock()
        db.dataBase = "DB"
        db.schema = "SCHEMA"
        sync = QueueSync(client, db=db)

        conn = MagicMock()
        # Simula contato existente com telefone antigo
        conn.execute.return_value.mappings.return_value.fetchone.return_value = {
            "ID_CONTATO": 10,
            "NOME": "Matheus",
            "TELEFONE": "11988887777",
            "TELEFONE_NORMALIZADO": "5511988887777",
        }

        contact_id, phone_changed = sync._get_or_create_contact(
            conn=conn,
            ctrl_id="CTRL-ABC",
            nome="Matheus Novo",
            raw_contato="11999998888",
            norm_phone="5511999998888",
        )

        self.assertEqual(contact_id, 10)
        self.assertTrue(phone_changed)
        # Verifica se o UPDATE no contato foi chamado
        self.assertTrue(conn.execute.called)


if __name__ == "__main__":
    unittest.main()
