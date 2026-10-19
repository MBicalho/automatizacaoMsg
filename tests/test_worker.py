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

    def test_worker_antiban_delays_applied_between_contacts_and_steps(self):
        from unittest.mock import patch
        db_mock = MagicMock()
        engine_mock = MagicMock()
        conn_mock = MagicMock()
        db_mock.connectDataBase.return_value = engine_mock
        engine_mock.begin.return_value.__enter__.return_value = conn_mock

        req1 = {
            "ID_SOLICITACAO": 1,
            "ID_CONTROLE_SHEETS": "CTRL-1",
            "ID_CONTATO": 101,
            "NOME": "Contato 1",
            "TELEFONE_NORMALIZADO": "5511999990001",
            "ATIVO": 1,
            "CONSENTIMENTO_STATUS": "OPT_IN",
            "BLOQUEADO": 0,
        }
        req2 = {
            "ID_SOLICITACAO": 2,
            "ID_CONTROLE_SHEETS": "CTRL-2",
            "ID_CONTATO": 102,
            "NOME": "Contato 2",
            "TELEFONE_NORMALIZADO": "5511999990002",
            "ATIVO": 1,
            "CONSENTIMENTO_STATUS": "OPT_IN",
            "BLOQUEADO": 0,
        }

        step1_1 = {"ID_ETAPA": 1, "ORDEM": 1, "CODIGO_MENSAGEM": "msg1", "ID_TIPO_ENVIO": 1, "CAMINHO_ARQUIVO": None, "TEXTO_RENDERIZADO": "T1", "STATUS": "PENDENTE", "TENTATIVAS": 0}
        step1_2 = {"ID_ETAPA": 2, "ORDEM": 2, "CODIGO_MENSAGEM": "msg2", "ID_TIPO_ENVIO": 1, "CAMINHO_ARQUIVO": None, "TEXTO_RENDERIZADO": "T2", "STATUS": "PENDENTE", "TENTATIVAS": 0}

        step2_1 = {"ID_ETAPA": 3, "ORDEM": 1, "CODIGO_MENSAGEM": "msg1", "ID_TIPO_ENVIO": 1, "CAMINHO_ARQUIVO": None, "TEXTO_RENDERIZADO": "T1", "STATUS": "PENDENTE", "TENTATIVAS": 0}

        conn_mock.execute.return_value.mappings.return_value.fetchall.side_effect = [
            [],  # stale steps
            [req1, req2],  # requests
            [step1_1, step1_2],  # steps req 1
            [{"STATUS": "ENVIADO", "CODIGO_MENSAGEM": "msg1"}, {"STATUS": "ENVIADO", "CODIGO_MENSAGEM": "msg2"}],  # updated req 1
            [step2_1],  # steps req 2
            [{"STATUS": "ENVIADO", "CODIGO_MENSAGEM": "msg1"}],  # updated req 2
        ]

        channel_mock = MagicMock(spec=WhatsAppChannel)
        channel_mock.send_text.return_value = ChannelResult(
            success=True, status="SUCESSO", detail="ok", channel_name="SIMULACAO"
        )
        sheets_mock = MagicMock(spec=GoogleSheetsClient)
        sheets_mock.controle_tab = "Controle"
        sheets_mock.read_table.return_value = (["ID_CONTROLE", "Envio"], [])

        worker = QueueWorker(
            channel=channel_mock,
            sheets_client=sheets_mock,
            db=db_mock,
            inter_contact_delay_range=(25.0, 25.0),
            inter_step_delay_range=(5.0, 5.0),
            enable_antiban_delays=True,
        )

        with patch("time.sleep") as mock_sleep:
            res = worker.process_pending_requests(max_requests=2)
            self.assertEqual(res["steps_sent"], 3)
            self.assertEqual(res["requests_completed"], 2)

            sleep_calls = [c[0][0] for c in mock_sleep.call_args_list]
            # Deve conter a pausa entre etapas (5.0) e a pausa entre contatos (25.0)
            self.assertIn(5.0, sleep_calls)
            self.assertIn(25.0, sleep_calls)

    def test_worker_limits_contacts_per_account_per_cycle(self):
        db_mock = MagicMock()
        engine_mock = MagicMock()
        conn_mock = MagicMock()
        db_mock.connectDataBase.return_value = engine_mock
        engine_mock.begin.return_value.__enter__.return_value = conn_mock

        # 7 contatos para conta_1 (Pacifico) e 7 contatos para conta_2 (Daniela)
        requests_list = []
        for i in range(1, 8):
            requests_list.append({
                "ID_SOLICITACAO": i,
                "ID_CONTROLE_SHEETS": f"CTRL-PAC-{i}",
                "ID_CONTATO": 100 + i,
                "NOME": f"Lead Pac {i}",
                "TELEFONE_NORMALIZADO": f"55119999900{i:02d}",
                "INSTANCIA_ENVIO": "conta_1",
                "ATIVO": 1,
                "CONSENTIMENTO_STATUS": "OPT_IN",
                "BLOQUEADO": 0,
            })
        for i in range(1, 8):
            requests_list.append({
                "ID_SOLICITACAO": 10 + i,
                "ID_CONTROLE_SHEETS": f"CTRL-DAN-{i}",
                "ID_CONTATO": 200 + i,
                "NOME": f"Lead Dan {i}",
                "TELEFONE_NORMALIZADO": f"55119888800{i:02d}",
                "INSTANCIA_ENVIO": "conta_2",
                "ATIVO": 1,
                "CONSENTIMENTO_STATUS": "OPT_IN",
                "BLOQUEADO": 0,
            })

        fetchall_side_effects = [
            [],  # stale
            requests_list,  # requests
        ]
        # Para cada contato processado:
        # fetchall steps: [step1]
        # fetchall updated_steps: [{"STATUS": "ENVIADO"}]
        for _ in range(14):
            fetchall_side_effects.append([{"ID_ETAPA": 1, "ORDEM": 1, "CODIGO_MENSAGEM": "msg", "ID_TIPO_ENVIO": 1, "CAMINHO_ARQUIVO": None, "TEXTO_RENDERIZADO": "T", "STATUS": "PENDENTE", "TENTATIVAS": 0}])
            fetchall_side_effects.append([{"STATUS": "ENVIADO", "CODIGO_MENSAGEM": "msg"}])

        conn_mock.execute.return_value.mappings.return_value.fetchall.side_effect = fetchall_side_effects

        channel_mock = MagicMock(spec=WhatsAppChannel)
        channel_mock.send_text.return_value = ChannelResult(
            success=True, status="SUCESSO", detail="ok", channel_name="SIMULACAO"
        )
        sheets_mock = MagicMock(spec=GoogleSheetsClient)
        sheets_mock.controle_tab = "Controle"
        sheets_mock.read_table.return_value = (["ID_CONTROLE", "Envio"], [])

        worker = QueueWorker(
            channel=channel_mock,
            sheets_client=sheets_mock,
            db=db_mock,
            enable_antiban_delays=False,
        )

        res = worker.process_pending_requests(max_requests=50, max_per_account=5)
        # Deve enviar exatamente 10 (5 para conta_1 e 5 para conta_2)
        self.assertEqual(res["steps_sent"], 10)
        self.assertEqual(res["requests_completed"], 10)


if __name__ == "__main__":
    unittest.main()
