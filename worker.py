"""Worker de envio rastreavel, idempotente e seguro com suporte a canais desacoplados."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import os
from pathlib import Path
import random
import time
from typing import Any
import sqlalchemy as sa

from channels import WhatsAppChannel, get_channel
from consent import evaluate_consent_eligibility
from functions import dataBase
from google_sheets import GoogleSheetsClient
from phone_utils import mask_phone


class QueueWorker:
    """Worker que consome etapas pendentes da fila SQL e atualiza o Google Sheets."""

    def __init__(
        self,
        channel: WhatsAppChannel | None = None,
        sheets_client: GoogleSheetsClient | None = None,
        db: dataBase | None = None,
        inter_contact_delay_range: tuple[float, float] = (15.0, 35.0),
        inter_step_delay_range: tuple[float, float] = (3.0, 7.0),
        enable_antiban_delays: bool | None = None,
    ) -> None:
        self.channel = channel or get_channel()
        self.sheets = sheets_client or GoogleSheetsClient.from_environment()
        self.db = db or dataBase()

        self.inter_contact_delay_min = inter_contact_delay_range[0]
        self.inter_contact_delay_max = inter_contact_delay_range[1]
        self.inter_step_delay_min = inter_step_delay_range[0]
        self.inter_step_delay_max = inter_step_delay_range[1]

        from channels import DryRunWhatsAppChannel
        if enable_antiban_delays is not None:
            self.enable_antiban_delays = enable_antiban_delays
        else:
            is_dry = isinstance(self.channel, DryRunWhatsAppChannel) or os.getenv("WHATSAPP_DRY_RUN", "").lower() in ("true", "1")
            env_enabled = os.getenv("ENABLE_ANTIBAN_DELAYS", "true").lower() in ("true", "1", "yes")
            self.enable_antiban_delays = env_enabled and not is_dry

    def recover_stale_processing(self, timeout_minutes: int = 15) -> int:
        """
        Recupera etapas que ficaram em PROCESSANDO por tempo excessivo (ex: queda do processo).
        Politica de resultado incerto: NAO reenvia automaticamente para evitar spam/duplicacao.
        Marca como ERRO com orientacao de conferencia manual.
        """
        engine = self.db.connectDataBase()
        if isinstance(engine, tuple) and not engine[0]:
            return 0

        with engine.begin() as conn:
            stale_steps = conn.execute(
                sa.text(f"""
                    SELECT E.ID_ETAPA, E.ID_SOLICITACAO, E.CODIGO_MENSAGEM
                    FROM {self.db.dataBase}.{self.db.schema}.ETAPAS_SOLICITACAO_WPP E
                    WHERE E.STATUS = 'PROCESSANDO'
                      AND E.DATA_INICIO < DATEADD(minute, -:timeout, SYSDATETIME())
                """),
                {"timeout": timeout_minutes}
            ).mappings().fetchall()

            for step in stale_steps:
                conn.execute(
                    sa.text(f"""
                        UPDATE {self.db.dataBase}.{self.db.schema}.ETAPAS_SOLICITACAO_WPP
                        SET STATUS = 'ERRO',
                            MENSAGEM_ERRO = 'Timeout: processo interrompido durante envio. Reenvio automatico bloqueado por seguranca.'
                        WHERE ID_ETAPA = :id_etapa
                    """),
                    {"id_etapa": step["ID_ETAPA"]}
                )
                conn.execute(
                    sa.text(f"""
                        UPDATE {self.db.dataBase}.{self.db.schema}.SOLICITACOES_ENVIO_WPP
                        SET STATUS_TECNICO = 'ERRO',
                            MENSAGEM_ERRO = 'Etapa com timeout em processamento.'
                        WHERE ID_SOLICITACAO = :id_sol
                    """),
                    {"id_sol": step["ID_SOLICITACAO"]}
                )

            return len(stale_steps)

    def process_pending_requests(
        self,
        max_requests: int = 50,
        max_per_account: int | None = None,
    ) -> dict[str, int]:
        """
        Processa as solicitacoes ativas e suas etapas na ordem sequencial.
        Limita o envio para no maximo 'max_per_account' contatos por conta por ciclo (padrao: 5).
        Retorna estatisticas de processamento.
        """
        self.recover_stale_processing()

        if max_per_account is None:
            max_per_account = int(os.getenv("MAX_CONTACTS_PER_ACCOUNT_PER_CYCLE", "5"))

        engine = self.db.connectDataBase()
        if isinstance(engine, tuple) and not engine[0]:
            raise RuntimeError(f"Erro ao conectar ao SQL Server: {engine[1]}")

        steps_sent = 0
        steps_failed = 0
        requests_completed = 0

        with engine.begin() as conn:
            # Busca solicitacoes ativas particionadas por instancia (ate max_per_account por conta)
            requests = conn.execute(
                sa.text(f"""
                    WITH RankedRequests AS (
                        SELECT 
                            S.ID_SOLICITACAO, S.ID_CONTROLE_SHEETS, S.ID_CONTATO, S.INSTANCIA_ENVIO,
                            C.NOME, C.TELEFONE_NORMALIZADO, C.ATIVO, C.CONSENTIMENTO_STATUS, C.BLOQUEADO,
                            ROW_NUMBER() OVER (
                                PARTITION BY COALESCE(S.INSTANCIA_ENVIO, 'conta_1') 
                                ORDER BY S.ID_SOLICITACAO ASC
                            ) as rn
                        FROM {self.db.dataBase}.{self.db.schema}.SOLICITACOES_ENVIO_WPP S
                        JOIN {self.db.dataBase}.{self.db.schema}.CONTATOS_WPP C ON S.ID_CONTATO = C.ID_CONTATO
                        WHERE S.STATUS_OPERADOR = 'Pendente'
                          AND S.STATUS_TECNICO IN ('PENDENTE', 'PROCESSANDO')
                    )
                    SELECT TOP (:total_max)
                        ID_SOLICITACAO, ID_CONTROLE_SHEETS, ID_CONTATO, INSTANCIA_ENVIO,
                        NOME, TELEFONE_NORMALIZADO, ATIVO, CONSENTIMENTO_STATUS, BLOQUEADO
                    FROM RankedRequests
                    WHERE rn <= :max_per_acc
                    ORDER BY rn ASC, INSTANCIA_ENVIO ASC
                """),
                {
                    "max_per_acc": max_per_account,
                    "total_max": max_requests,
                }
            ).mappings().fetchall()

            processed_contacts_count = 0
            sent_per_account: dict[str, int] = defaultdict(int)

            for req in requests:
                req_id = req["ID_SOLICITACAO"]
                ctrl_id = req["ID_CONTROLE_SHEETS"]
                phone = req["TELEFONE_NORMALIZADO"]
                nome = req["NOME"]
                target_instance = req.get("INSTANCIA_ENVIO") or "conta_1"

                # Garante limite estrito de contatos por conta no ciclo
                if sent_per_account[target_instance] >= max_per_account:
                    continue

                # Valida elegibilidade do contato
                eligibility = evaluate_consent_eligibility(req)
                if not eligibility.is_eligible:
                    conn.execute(
                        sa.text(f"""
                            UPDATE {self.db.dataBase}.{self.db.schema}.SOLICITACOES_ENVIO_WPP
                            SET STATUS_TECNICO = 'NAO_ELEGIVEL', MENSAGEM_ERRO = :erro
                            WHERE ID_SOLICITACAO = :id_sol
                        """),
                        {"id_sol": req_id, "erro": eligibility.reason}
                    )
                    conn.execute(
                        sa.text(f"""
                            UPDATE {self.db.dataBase}.{self.db.schema}.ETAPAS_SOLICITACAO_WPP
                            SET STATUS = 'CANCELADO', MENSAGEM_ERRO = :erro
                            WHERE ID_SOLICITACAO = :id_sol AND STATUS = 'PENDENTE'
                        """),
                        {"id_sol": req_id, "erro": eligibility.reason}
                    )
                    self._update_sheet_status(ctrl_id, envio="Cancelado", ultima_msg=f"Bloqueado: {eligibility.reason}")
                    continue

                # Busca todas as etapas da solicitacao ordenadas por ORDEM ASC
                steps = conn.execute(
                    sa.text(f"""
                        SELECT ID_ETAPA, ORDEM, CODIGO_MENSAGEM, ID_TIPO_ENVIO,
                               CAMINHO_ARQUIVO, TEXTO_RENDERIZADO, STATUS, TENTATIVAS
                        FROM {self.db.dataBase}.{self.db.schema}.ETAPAS_SOLICITACAO_WPP
                        WHERE ID_SOLICITACAO = :id_sol
                        ORDER BY ORDEM ASC
                    """),
                    {"id_sol": req_id}
                ).mappings().fetchall()

                if not steps:
                    continue

                has_pending = any(s["STATUS"] == "PENDENTE" for s in steps)
                if not has_pending:
                    continue

                # Pausa humanizada entre contatos diferentes (15 a 35 segundos)
                if processed_contacts_count > 0 and self.enable_antiban_delays:
                    contact_delay = round(random.uniform(self.inter_contact_delay_min, self.inter_contact_delay_max), 1)
                    if contact_delay > 0:
                        print(f"[ANTI-BAN] Aguardando {contact_delay}s antes de enviar para o proximo contato ({mask_phone(phone)})...")
                        time.sleep(contact_delay)

                processed_contacts_count += 1
                has_failure = False
                last_sent_code = None
                sent_in_this_req = 0

                for step in steps:
                    step_id = step["ID_ETAPA"]
                    step_status = step["STATUS"]
                    step_code = step["CODIGO_MENSAGEM"]

                    if step_status == "ENVIADO":
                        last_sent_code = step_code
                        continue

                    if step_status == "CANCELADO":
                        # Etapa cancelada (ex: operador alterou a lista de mensagens na planilha); pula sem falhar a fila
                        continue

                    if step_status == "ERRO":
                        has_failure = True
                        break

                    if step_status == "PENDENTE":
                        if has_failure:
                            # Se uma etapa anterior falhou, nao executa a proxima
                            break

                        # Pausa humanizada entre mensagens do MESMO contato (3 a 7 segundos)
                        if sent_in_this_req > 0 and self.enable_antiban_delays:
                            step_delay = round(random.uniform(self.inter_step_delay_min, self.inter_step_delay_max), 1)
                            if step_delay > 0:
                                print(f"[ANTI-BAN] Aguardando {step_delay}s antes do proximo envio para {mask_phone(phone)}...")
                                time.sleep(step_delay)

                        # Marca etapa como PROCESSANDO
                        conn.execute(
                            sa.text(f"""
                                UPDATE {self.db.dataBase}.{self.db.schema}.ETAPAS_SOLICITACAO_WPP
                                SET STATUS = 'PROCESSANDO',
                                    TENTATIVAS = TENTATIVAS + 1,
                                    DATA_INICIO = SYSDATETIME()
                                WHERE ID_ETAPA = :id_etapa
                            """),
                            {"id_etapa": step_id}
                        )
                        conn.execute(
                            sa.text(f"""
                                UPDATE {self.db.dataBase}.{self.db.schema}.SOLICITACOES_ENVIO_WPP
                                SET STATUS_TECNICO = 'PROCESSANDO',
                                    DATA_INICIO = CASE WHEN DATA_INICIO IS NULL THEN SYSDATETIME() ELSE DATA_INICIO END
                                WHERE ID_SOLICITACAO = :id_sol
                            """),
                            {"id_sol": req_id}
                        )

                        # Atualiza planilha indicando Processando
                        self._update_sheet_status(ctrl_id, envio="Processando")

                        # Executa o envio atraves do canal
                        tipo_envio = step["ID_TIPO_ENVIO"]
                        texto = step["TEXTO_RENDERIZADO"] or ""
                        caminho_arq = step["CAMINHO_ARQUIVO"]

                        target_instance = req.get("INSTANCIA_ENVIO") or "conta_1"

                        if tipo_envio == 1:
                            send_res = self.channel.send_text(phone, texto, instance=target_instance)
                        else:
                            file_path = Path(caminho_arq) if caminho_arq else Path("")
                            send_res = self.channel.send_file(
                                phone=phone,
                                file_path=file_path,
                                caption=texto,
                                is_image=(tipo_envio == 3),
                                instance=target_instance,
                            )

                        print(f"[{send_res.channel_name}] {send_res.status}: {send_res.detail}")

                        # Registra tentativa no historico
                        conn.execute(
                            sa.text(f"""
                                INSERT INTO {self.db.dataBase}.{self.db.schema}.HISTORICO_TENTATIVAS_ENVIO_WPP
                                    (ID_ETAPA, NUMERO_TENTATIVA, CANAL, RESULTADO, DETALHE, DATA_TENTATIVA)
                                VALUES
                                    (:id_etapa, :tentativas, :canal, :resultado, :detalhe, SYSDATETIME())
                            """),
                            {
                                "id_etapa": step_id,
                                "tentativas": step["TENTATIVAS"] + 1,
                                "canal": send_res.channel_name,
                                "resultado": send_res.status,
                                "detalhe": send_res.detail,
                            }
                        )

                        if send_res.success and send_res.status == "SUCESSO":
                            conn.execute(
                                sa.text(f"""
                                    UPDATE {self.db.dataBase}.{self.db.schema}.ETAPAS_SOLICITACAO_WPP
                                    SET STATUS = 'ENVIADO', DATA_ENVIO = SYSDATETIME(), MENSAGEM_ERRO = NULL
                                    WHERE ID_ETAPA = :id_etapa
                                """),
                                {"id_etapa": step_id}
                            )
                            steps_sent += 1
                            sent_in_this_req += 1
                            last_sent_code = step_code
                        else:
                            conn.execute(
                                sa.text(f"""
                                    UPDATE {self.db.dataBase}.{self.db.schema}.ETAPAS_SOLICITACAO_WPP
                                    SET STATUS = 'ERRO', MENSAGEM_ERRO = :erro
                                    WHERE ID_ETAPA = :id_etapa
                                """),
                                {"id_etapa": step_id, "erro": send_res.detail[:2000]}
                            )
                            steps_failed += 1
                            has_failure = True
                            break

                if sent_in_this_req > 0:
                    sent_per_account[target_instance] += 1

                # Avalia o resultado final da solicitacao
                updated_steps = conn.execute(
                    sa.text(f"""
                        SELECT STATUS, CODIGO_MENSAGEM FROM {self.db.dataBase}.{self.db.schema}.ETAPAS_SOLICITACAO_WPP
                        WHERE ID_SOLICITACAO = :id_sol
                        ORDER BY ORDEM ASC
                    """),
                    {"id_sol": req_id}
                ).mappings().fetchall()

                # Considera apenas etapas ativas (ignora etapas canceladas por reducao/ajuste de mensagens na planilha)
                active_steps = [s for s in updated_steps if s["STATUS"] != "CANCELADO"]
                active_statuses = [s["STATUS"] for s in active_steps]

                all_sent = bool(active_statuses) and all(st == "ENVIADO" for st in active_statuses)
                any_sent = any(st == "ENVIADO" for st in active_statuses)
                has_error = any(st == "ERRO" for st in active_statuses)

                if all_sent:
                    conn.execute(
                        sa.text(f"""
                            UPDATE {self.db.dataBase}.{self.db.schema}.SOLICITACOES_ENVIO_WPP
                            SET STATUS_TECNICO = 'CONCLUIDO', DATA_CONCLUSAO = SYSDATETIME(), MENSAGEM_ERRO = NULL
                            WHERE ID_SOLICITACAO = :id_sol
                        """),
                        {"id_sol": req_id}
                    )
                    requests_completed += 1
                    timestamp_str = datetime.now().strftime("%d/%m/%Y %H:%M")
                    self._update_sheet_status(
                        ctrl_id,
                        envio="Enviado",
                        ultima_msg=f"{last_sent_code} ({timestamp_str})",
                    )
                elif has_error:
                    final_tech = "FALHA_PARCIAL" if any_sent else "ERRO"
                    conn.execute(
                        sa.text(f"""
                            UPDATE {self.db.dataBase}.{self.db.schema}.SOLICITACOES_ENVIO_WPP
                            SET STATUS_TECNICO = :st, MENSAGEM_ERRO = 'Falha em uma ou mais etapas.'
                            WHERE ID_SOLICITACAO = :id_sol
                        """),
                        {"id_sol": req_id, "st": final_tech}
                    )
                    timestamp_str = datetime.now().strftime("%d/%m/%Y %H:%M")
                    ultima_info = f"{last_sent_code} ({timestamp_str})" if last_sent_code else ""
                    self._update_sheet_status(ctrl_id, envio="Erro", ultima_msg=ultima_info)

        return {
            "steps_sent": steps_sent,
            "steps_failed": steps_failed,
            "requests_completed": requests_completed,
        }

    def _update_sheet_status(
        self,
        ctrl_id: str,
        envio: str,
        ultima_msg: str | None = None,
    ) -> None:
        """Localiza a linha na aba Controle pelo ID_CONTROLE e atualiza campos operacionais."""
        try:
            headers, rows = self.sheets.read_table(self.sheets.controle_tab)
            header_map = {h.strip().lower(): h for h in headers}
            id_header = header_map.get("id_controle")
            if not id_header:
                return

            target_row = None
            for row in rows:
                if str(row.values.get(id_header, "")).strip() == ctrl_id.strip():
                    target_row = row
                    break

            if not target_row:
                return

            fields_to_update: dict[str, Any] = {"Envio": envio}
            if ultima_msg is not None:
                fields_to_update["Ultima Mensagem Enviada"] = ultima_msg

            self.sheets.update_control_fields(target_row.row_number, fields_to_update)
        except Exception as ex:
            # Erro ao atualizar o Google Sheets nao deve derrubar a transacao SQL
            print(f"Aviso: falha ao atualizar status na planilha para {ctrl_id}: {ex}")
