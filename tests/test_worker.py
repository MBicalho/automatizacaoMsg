from unittest.mock import MagicMock
import unittest

from channels import ChannelResult, WhatsAppChannel
from google_sheets import GoogleSheetsClient
from worker import QueueWorker


class WorkerTests(unittest.TestCase):
    def test_worker_recover_stale_processing(self):
        db_mock = MagicMock()
        engine_mock = MagicMock()
        conn_mock = MagicMock()
        db_mock.connectDataBase.return_value = engine_mock
        engine_mock.begin.return_value.__enter__.return_value = conn_mock
        conn_mock.execute.return_value.mappings.return_value.fetchall.return_value = [
            {"ID_ETAPA": 10, "ID_SOLICITACAO": 1, "CODIGO_MENSAGEM": "boas-vindas"}
        ]

        worker = QueueWorker(
            channel=MagicMock(spec=WhatsAppChannel),
            sheets_client=MagicMock(spec=GoogleSheetsClient),
            db=db_mock,
        )

        recovered = worker.recover_stale_processing(timeout_minutes=15)
        self.assertEqual(recovered, 1)

        # Verifica se chamou UPDATE com 'ERRO'
        found_error_update = False
        for call_args in conn_mock.execute.call_args_list:
            if call_args.args:
                sql_clause = call_args.args[0]
                sql_text = getattr(sql_clause, "text", str(sql_clause))
                if "ERRO" in sql_text:
                    found_error_update = True
                    break
        self.assertTrue(found_error_update)

    def test_worker_halts_on_failure_and_does_not_send_next_steps(self):
        db_mock = MagicMock()
        engine_mock = MagicMock()
        conn_mock = MagicMock()
        db_mock.connectDataBase.return_value = engine_mock
        engine_mock.begin.return_value.__enter__.return_value = conn_mock

        # Solicitacao com 2 etapas
        req_row = {
            "ID_SOLICITACAO": 1,
            "ID_CONTROLE_SHEETS": "CTRL-1",
            "ID_CONTATO": 100,
            "NOME": "Ana",
            "TELEFONE_NORMALIZADO": "5511999999999",
            "ATIVO": 1,
            "CONSENTIMENTO_STATUS": "OPT_IN",
            "BLOQUEADO": 0,
        }
        step1 = {
            "ID_ETAPA": 1,
            "ORDEM": 1,
            "CODIGO_MENSAGEM": "msg1",
            "ID_TIPO_ENVIO": 1,
            "CAMINHO_ARQUIVO": None,
            "TEXTO_RENDERIZADO": "Texto 1",
            "STATUS": "PENDENTE",
            "TENTATIVAS": 0,
        }
        step2 = {
            "ID_ETAPA": 2,
            "ORDEM": 2,
            "CODIGO_MENSAGEM": "msg2",
            "ID_TIPO_ENVIO": 1,
            "CAMINHO_ARQUIVO": None,
            "TEXTO_RENDERIZADO": "Texto 2",
            "STATUS": "PENDENTE",
            "TENTATIVAS": 0,
        }

        # Mock das consultas sequenciais
        conn_mock.execute.return_value.mappings.return_value.fetchall.side_effect = [
            [],  # stale steps
            [req_row],  # pending requests
            [step1, step2],  # steps of request
            [{"STATUS": "ERRO", "CODIGO_MENSAGEM": "msg1"}, {"STATUS": "PENDENTE", "CODIGO_MENSAGEM": "msg2"}],  # updated steps
        ]

        # Canal que simula falha na etapa 1
        channel_mock = MagicMock(spec=WhatsAppChannel)
        channel_mock.send_text.return_value = ChannelResult(
            success=False,
            status="FALHA",
            detail="Erro simulado de envio",
            channel_name="SIMULACAO",
        )

        sheets_mock = MagicMock(spec=GoogleSheetsClient)
        sheets_mock.controle_tab = "Controle"
        sheets_mock.read_table.return_value = (["ID_CONTROLE", "Envio"], [])

        worker = QueueWorker(
            channel=channel_mock,
            sheets_client=sheets_mock,
            db=db_mock,
        )

        res = worker.process_pending_requests(max_requests=1)
        self.assertEqual(res["steps_sent"], 0)
        self.assertEqual(res["steps_failed"], 1)
        self.assertEqual(res["requests_completed"], 0)
        channel_mock.send_text.assert_called_once()


if __name__ == "__main__":
    unittest.main()
