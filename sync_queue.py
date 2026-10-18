"""Sincronizacao idempotente da fila de solicitacoes do Google Sheets com o SQL Server."""

from __future__ import annotations

import uuid
from typing import Any, Mapping
import sqlalchemy as sa

from consent import evaluate_consent_eligibility
from functions import dataBase
from google_sheets import CONTROLE_HEADERS, GoogleSheetsClient
from message_parser import parse_message_codes, render_message_text
from phone_utils import InvalidPhoneNumberError, mask_phone, normalize_brazilian_phone


class QueueSync:
    """Sincroniza as solicitacoes da aba Controle com as tabelas relacionais no SQL Server."""

    def __init__(self, sheets_client: GoogleSheetsClient, db: dataBase | None = None) -> None:
        self.sheets = sheets_client
        self.db = db or dataBase()

    def ensure_missing_control_ids(self) -> int:
        """
        Gera e salva ID_CONTROLE unico para linhas que ainda nao possuem esse identificador estavel.
        Retorna a quantidade de IDs gerados.
        """
        headers, rows = self.sheets.read_table(self.sheets.controle_tab)
        header_map = {h.strip().lower(): h for h in headers}
        id_header = header_map.get("id_controle")
        if not id_header:
            return 0

        generated_count = 0
        updates_batch: list[tuple[int, dict[str, Any]]] = []

        for row in rows:
            current_id = str(row.values.get(id_header, "")).strip()
            if not current_id:
                new_id = f"CTRL-{uuid.uuid4()}"
                updates_batch.append((row.row_number, {id_header: new_id}))
                generated_count += 1

        for row_num, val_dict in updates_batch:
            self.sheets.update_control_fields(row_num, val_dict)

        return generated_count

    def sync_requests(self) -> dict[str, int]:
        """
        Le a aba Controle, normaliza contatos, avalia consentimento/LGPD,
        e cria/atualiza solicitacoes e etapas de forma estritamente idempotente.
        """
        self.ensure_missing_control_ids()
        headers, rows = self.sheets.validate_headers(self.sheets.controle_tab, CONTROLE_HEADERS)

        header_map = {h.strip().lower(): h for h in headers}
        id_col = header_map.get("id_controle")
        if not id_col:
            raise ValueError("Coluna tecnica ID_CONTROLE nao encontrada na aba Controle.")

        engine = self.db.connectDataBase()
        if isinstance(engine, tuple) and not engine[0]:
            raise RuntimeError(f"Erro ao conectar ao SQL Server: {engine[1]}")

        created_requests = 0
        created_steps = 0
        cancelled_requests = 0

        with engine.begin() as conn:
            for row in rows:
                ctrl_id = str(row.values.get(id_col, "")).strip()
                if not ctrl_id:
                    continue

                raw_nome = str(row.values.get("Nome", "")).strip()
                raw_contato = row.values.get("Contato")
                raw_mensagens = row.values.get("Mensagem")
                raw_envio = str(row.values.get("Envio", "Pendente")).strip()
                raw_origem = str(row.values.get("Origem") or row.values.get("origem") or "").strip()

                # Mapeia Origem para instancia do WhatsApp (Evolution API)
                # 'Lead Pacifico' -> conta_1
                # 'Lead Daniela'  -> conta_2
                origem_lower = raw_origem.lower()
                if "daniela" in origem_lower or "conta 2" in origem_lower or "contato 2" in origem_lower:
                    instancia_envio = "conta_2"
                elif "pacifico" in origem_lower or "conta 1" in origem_lower or "contato 1" in origem_lower:
                    instancia_envio = "conta_1"
                else:
                    instancia_envio = "conta_1"

                # Normalizacao do telefone
                try:
                    norm_phone = normalize_brazilian_phone(raw_contato)
                except InvalidPhoneNumberError as ex:
                    # Registra erro na solicitacao sem quebrar o processamento das outras
                    self._upsert_invalid_request(
                        conn=conn,
                        ctrl_id=ctrl_id,
                        nome=raw_nome,
                        raw_contato=str(raw_contato or ""),
                        raw_envio=raw_envio,
                        erro=f"Telefone invalido: {ex}",
                    )
                    continue

                # Busca ou cadastra o contato no CONTATOS_WPP vinculado ao ID_CONTROLE
                id_contato, phone_changed = self._get_or_create_contact(
                    conn=conn,
                    ctrl_id=ctrl_id,
                    nome=raw_nome,
                    raw_contato=str(raw_contato or ""),
                    norm_phone=norm_phone,
                )

                # Busca dados atuais do contato para avaliacao de consentimento
                contact_row = conn.execute(
                    sa.text(f"""
                        SELECT ID_CONTATO, ATIVO, CONSENTIMENTO_STATUS, BLOQUEADO
                        FROM {self.db.dataBase}.{self.db.schema}.CONTATOS_WPP
                        WHERE ID_CONTATO = :id_contato
                    """),
                    {"id_contato": id_contato}
                ).mappings().fetchone()

                eligibility = evaluate_consent_eligibility(contact_row or {})

                # Verifica se a solicitacao ja existe
                existing_req = conn.execute(
                    sa.text(f"""
                        SELECT ID_SOLICITACAO, STATUS_OPERADOR, STATUS_TECNICO
                        FROM {self.db.dataBase}.{self.db.schema}.SOLICITACOES_ENVIO_WPP
                        WHERE ID_CONTROLE_SHEETS = :ctrl_id
                    """),
                    {"ctrl_id": ctrl_id}
                ).mappings().fetchone()

                # Se operador marcou 'Cancelado'
                if raw_envio.lower() == "cancelado":
                    if existing_req:
                        conn.execute(
                            sa.text(f"""
                                UPDATE {self.db.dataBase}.{self.db.schema}.SOLICITACOES_ENVIO_WPP
                                SET STATUS_OPERADOR = 'Cancelado',
                                    STATUS_TECNICO = CASE WHEN STATUS_TECNICO = 'PENDENTE' THEN 'CANCELADO' ELSE STATUS_TECNICO END
                                WHERE ID_SOLICITACAO = :req_id
                            """),
                            {"req_id": existing_req["ID_SOLICITACAO"]}
                        )
                        conn.execute(
                            sa.text(f"""
                                UPDATE {self.db.dataBase}.{self.db.schema}.ETAPAS_SOLICITACAO_WPP
                                SET STATUS = 'CANCELADO'
                                WHERE ID_SOLICITACAO = :req_id AND STATUS = 'PENDENTE'
                            """),
                            {"req_id": existing_req["ID_SOLICITACAO"]}
                        )
                        cancelled_requests += 1
                    continue

                # Se nao estiver elegivel por LGPD
                if not eligibility.is_eligible:
                    if not existing_req:
                        conn.execute(
                            sa.text(f"""
                                INSERT INTO {self.db.dataBase}.{self.db.schema}.SOLICITACOES_ENVIO_WPP
                                    (ID_CONTROLE_SHEETS, ID_CONTATO, STATUS_OPERADOR, STATUS_TECNICO,
                                     CODIGOS_MENSAGENS, MENSAGEM_ERRO, DATA_CRIACAO)
                                VALUES
                                    (:ctrl_id, :id_contato, :operador, 'NAO_ELEGIVEL', :msgs, :erro, SYSDATETIME())
                            """),
                            {
                                "ctrl_id": ctrl_id,
                                "id_contato": id_contato,
                                "operador": raw_envio,
                                "msgs": str(raw_mensagens or ""),
                                "erro": eligibility.reason,
                            }
                        )
                    continue

                # Cria a solicitacao se ainda nao existir
                if not existing_req:
                    req_insert = conn.execute(
                        sa.text(f"""
                            SET NOCOUNT ON;
                            INSERT INTO {self.db.dataBase}.{self.db.schema}.SOLICITACOES_ENVIO_WPP
                                (ID_CONTROLE_SHEETS, ID_CONTATO, STATUS_OPERADOR, STATUS_TECNICO,
                                 CODIGOS_MENSAGENS, ORIGEM, INSTANCIA_ENVIO, DATA_CRIACAO)
                            VALUES
                                (:ctrl_id, :id_contato, :operador, 'PENDENTE', :msgs, :origem, :instancia, SYSDATETIME());
                            SELECT SCOPE_IDENTITY() AS ID_SOLICITACAO;
                        """),
                        {
                            "ctrl_id": ctrl_id,
                            "id_contato": id_contato,
                            "operador": raw_envio,
                            "msgs": str(raw_mensagens or ""),
                            "origem": raw_origem,
                            "instancia": instancia_envio,
                        }
                    ).mappings().fetchone()
                    id_solicitacao = req_insert["ID_SOLICITACAO"]
                    created_requests += 1
                else:
                    id_solicitacao = existing_req["ID_SOLICITACAO"]
                    conn.execute(
                        sa.text(f"""
                            UPDATE {self.db.dataBase}.{self.db.schema}.SOLICITACOES_ENVIO_WPP
                            SET ID_CONTATO = :id_contato,
                                STATUS_OPERADOR = :operador,
                                CODIGOS_MENSAGENS = :msgs,
                                ORIGEM = :origem,
                                INSTANCIA_ENVIO = :instancia
                            WHERE ID_SOLICITACAO = :req_id
                        """),
                        {
                            "id_contato": id_contato,
                            "operador": raw_envio,
                            "msgs": str(raw_mensagens or ""),
                            "origem": raw_origem,
                            "instancia": instancia_envio,
                            "req_id": id_solicitacao,
                        }
                    )

                if phone_changed:
                    # Telefone corrigido/alterado na planilha: reseta etapas para reenviar ao novo numero
                    conn.execute(
                        sa.text(f"""
                            UPDATE {self.db.dataBase}.{self.db.schema}.ETAPAS_SOLICITACAO_WPP
                            SET STATUS = 'PENDENTE',
                                MENSAGEM_ERRO = NULL
                            WHERE ID_SOLICITACAO = :req_id
                        """),
                        {"req_id": id_solicitacao}
                    )
                    conn.execute(
                        sa.text(f"""
                            UPDATE {self.db.dataBase}.{self.db.schema}.SOLICITACOES_ENVIO_WPP
                            SET STATUS_TECNICO = 'PENDENTE'
                            WHERE ID_SOLICITACAO = :req_id
                        """),
                        {"req_id": id_solicitacao}
                    )
                elif raw_envio.lower() == "pendente":
                    # Operador reabriu como Pendente: retenta etapas com falha ou reativa canceladas
                    conn.execute(
                        sa.text(f"""
                            UPDATE {self.db.dataBase}.{self.db.schema}.ETAPAS_SOLICITACAO_WPP
                            SET STATUS = 'PENDENTE',
                                MENSAGEM_ERRO = NULL
                            WHERE ID_SOLICITACAO = :req_id AND STATUS IN ('ERRO', 'CANCELADO')
                        """),
                        {"req_id": id_solicitacao}
                    )
                    conn.execute(
                        sa.text(f"""
                            UPDATE {self.db.dataBase}.{self.db.schema}.SOLICITACOES_ENVIO_WPP
                            SET STATUS_TECNICO = 'PENDENTE'
                            WHERE ID_SOLICITACAO = :req_id AND STATUS_TECNICO <> 'PENDENTE'
                              AND EXISTS (
                                  SELECT 1 FROM {self.db.dataBase}.{self.db.schema}.ETAPAS_SOLICITACAO_WPP
                                  WHERE ID_SOLICITACAO = :req_id AND STATUS = 'PENDENTE'
                              )
                        """),
                        {"req_id": id_solicitacao}
                    )

                # Extrai os codigos de mensagem preservando a ordem
                message_codes = parse_message_codes(raw_mensagens)
                if not message_codes:
                    continue

                # Cancela etapas pendentes orfas (caso o operador tenha reduzido ou alterado a lista na planilha)
                valid_keys = [f"{ctrl_id}:{order_idx}:{code}" for order_idx, code in enumerate(message_codes, start=1)]
                existing_pending_steps = conn.execute(
                    sa.text(f"""
                        SELECT ID_ETAPA, CHAVE_IDEMPOTENCIA
                        FROM {self.db.dataBase}.{self.db.schema}.ETAPAS_SOLICITACAO_WPP
                        WHERE ID_SOLICITACAO = :req_id AND STATUS = 'PENDENTE'
                    """),
                    {"req_id": id_solicitacao}
                ).mappings().fetchall()

                for pending_step in existing_pending_steps:
                    if pending_step["CHAVE_IDEMPOTENCIA"] not in valid_keys:
                        conn.execute(
                            sa.text(f"""
                                UPDATE {self.db.dataBase}.{self.db.schema}.ETAPAS_SOLICITACAO_WPP
                                SET STATUS = 'CANCELADO',
                                    MENSAGEM_ERRO = 'Mensagem removida ou alterada na planilha.'
                                WHERE ID_ETAPA = :id_etapa
                            """),
                            {"id_etapa": pending_step["ID_ETAPA"]}
                        )

                # Cria as etapas individuais por codigo na ordem exata
                for order_idx, code in enumerate(message_codes, start=1):
                    idempotency_key = f"{ctrl_id}:{order_idx}:{code}"

                    # Verifica se a etapa ja existe pela chave de idempotencia
                    existing_step = conn.execute(
                        sa.text(f"""
                            SELECT ID_ETAPA, STATUS
                            FROM {self.db.dataBase}.{self.db.schema}.ETAPAS_SOLICITACAO_WPP
                            WHERE CHAVE_IDEMPOTENCIA = :key
                        """),
                        {"key": idempotency_key}
                    ).fetchone()

                    if existing_step:
                        # Etapa ja criada anteriormente; mantem estado
                        continue

                    # Busca detalhes do codigo no catalogo
                    msg_cat = conn.execute(
                        sa.text(f"""
                            SELECT ID_MENSAGEM, DESCRICAO_MENSAGEM, ARQUIVO, ATIVO
                            FROM {self.db.dataBase}.{self.db.schema}.MENSAGEM_WPP
                            WHERE CODIGO_MENSAGEM = :code
                        """),
                        {"code": code}
                    ).mappings().fetchone()

                    if not msg_cat or not msg_cat["ATIVO"]:
                        step_status = "ERRO"
                        erro_msg = f"Mensagem '{code}' nao encontrada no catalogo ou inativa."
                        id_msg = msg_cat["ID_MENSAGEM"] if msg_cat else None
                        caminho_arq = None
                        rendered_text = None
                        id_tipo = 1
                    else:
                        step_status = "PENDENTE"
                        erro_msg = None
                        id_msg = msg_cat["ID_MENSAGEM"]
                        caminho_arq = msg_cat["ARQUIVO"]
                        template = msg_cat["DESCRICAO_MENSAGEM"]
                        rendered_text = render_message_text(template, {"nome": raw_nome})
                        id_tipo = 3 if caminho_arq and any(caminho_arq.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp")) else (2 if caminho_arq else 1)

                    conn.execute(
                        sa.text(f"""
                            INSERT INTO {self.db.dataBase}.{self.db.schema}.ETAPAS_SOLICITACAO_WPP
                                (ID_SOLICITACAO, ORDEM, CODIGO_MENSAGEM, ID_MENSAGEM, ID_TIPO_ENVIO,
                                 CAMINHO_ARQUIVO, TEXTO_RENDERIZADO, STATUS, CHAVE_IDEMPOTENCIA, MENSAGEM_ERRO)
                            VALUES
                                (:req_id, :ordem, :code, :id_msg, :id_tipo,
                                 :caminho, :texto, :status, :key, :erro)
                        """),
                        {
                            "req_id": id_solicitacao,
                            "ordem": order_idx,
                            "code": code,
                            "id_msg": id_msg,
                            "id_tipo": id_tipo,
                            "caminho": caminho_arq,
                            "texto": rendered_text,
                            "status": step_status,
                            "key": idempotency_key,
                            "erro": erro_msg,
                        }
                    )
                    created_steps += 1

                # Garante que a solicitacao passe a PENDENTE caso existam etapas pendentes
                if raw_envio.lower() == "pendente":
                    conn.execute(
                        sa.text(f"""
                            UPDATE {self.db.dataBase}.{self.db.schema}.SOLICITACOES_ENVIO_WPP
                            SET STATUS_TECNICO = 'PENDENTE'
                            WHERE ID_SOLICITACAO = :req_id
                              AND STATUS_TECNICO <> 'PENDENTE'
                              AND EXISTS (
                                  SELECT 1 FROM {self.db.dataBase}.{self.db.schema}.ETAPAS_SOLICITACAO_WPP
                                  WHERE ID_SOLICITACAO = :req_id AND STATUS = 'PENDENTE'
                              )
                        """),
                        {"req_id": id_solicitacao}
                    )

        return {
            "created_requests": created_requests,
            "created_steps": created_steps,
            "cancelled_requests": cancelled_requests,
        }

    def _get_or_create_contact(
        self,
        conn: sa.Connection,
        ctrl_id: str,
        nome: str,
        raw_contato: str,
        norm_phone: str,
    ) -> tuple[int, bool]:
        # 1. Busca prioritariamente pelo ID_CONTROLE_SHEETS (chave estavel da linha na planilha)
        by_ctrl = conn.execute(
            sa.text(f"""
                SELECT ID_CONTATO, NOME, TELEFONE, TELEFONE_NORMALIZADO
                FROM {self.db.dataBase}.{self.db.schema}.CONTATOS_WPP
                WHERE ID_CONTROLE_SHEETS = :ctrl_id
            """),
            {"ctrl_id": ctrl_id}
        ).mappings().fetchone()

        if by_ctrl:
            phone_changed = (str(by_ctrl["TELEFONE_NORMALIZADO"] or "").strip() != norm_phone)
            conn.execute(
                sa.text(f"""
                    UPDATE {self.db.dataBase}.{self.db.schema}.CONTATOS_WPP
                    SET ATIVO = 1,
                        NOME = CASE WHEN :nome != '' THEN :nome ELSE NOME END,
                        TELEFONE = :raw,
                        TELEFONE_NORMALIZADO = :norm,
                        DATA_ATUALIZACAO = SYSDATETIME()
                    WHERE ID_CONTATO = :id
                """),
                {"nome": nome, "raw": raw_contato, "norm": norm_phone, "id": by_ctrl["ID_CONTATO"]}
            )
            return int(by_ctrl["ID_CONTATO"]), phone_changed

        # 2. Busca por TELEFONE_NORMALIZADO caso contato ja exista sem ID_CONTROLE_SHEETS
        by_phone = conn.execute(
            sa.text(f"""
                SELECT ID_CONTATO, NOME
                FROM {self.db.dataBase}.{self.db.schema}.CONTATOS_WPP
                WHERE TELEFONE_NORMALIZADO = :phone
            """),
            {"phone": norm_phone}
        ).mappings().fetchone()

        if by_phone:
            conn.execute(
                sa.text(f"""
                    UPDATE {self.db.dataBase}.{self.db.schema}.CONTATOS_WPP
                    SET ATIVO = 1,
                        ID_CONTROLE_SHEETS = :ctrl_id,
                        NOME = CASE WHEN :nome != '' THEN :nome ELSE NOME END,
                        DATA_ATUALIZACAO = SYSDATETIME()
                    WHERE ID_CONTATO = :id
                """),
                {"ctrl_id": ctrl_id, "nome": nome, "id": by_phone["ID_CONTATO"]}
            )
            return int(by_phone["ID_CONTATO"]), False

        # 3. Insere novo contato vinculado ao ID_CONTROLE_SHEETS
        ins = conn.execute(
            sa.text(f"""
                SET NOCOUNT ON;
                INSERT INTO {self.db.dataBase}.{self.db.schema}.CONTATOS_WPP
                    (ID_CONTROLE_SHEETS, NOME, TELEFONE, TELEFONE_NORMALIZADO, ATIVO, CONSENTIMENTO_STATUS, CONSENTIMENTO_DATA, CONSENTIMENTO_ORIGEM)
                VALUES
                    (:ctrl_id, :nome, :raw, :norm, 1, 'OPT_IN', SYSDATETIME(), 'GOOGLE_SHEETS_IMPORT');
                SELECT SCOPE_IDENTITY() AS ID_CONTATO;
            """),
            {"ctrl_id": ctrl_id, "nome": nome, "raw": raw_contato, "norm": norm_phone}
        ).mappings().fetchone()

        return int(ins["ID_CONTATO"]), False

    def _upsert_invalid_request(
        self,
        conn: sa.Connection,
        ctrl_id: str,
        nome: str,
        raw_contato: str,
        raw_envio: str,
        erro: str,
    ) -> None:
        """Cria ou atualiza solicitacao com erro tecnico sem travar a fila."""
        # Se contato nao existir, cria contato anonimo ou com erro
        dummy = conn.execute(
            sa.text(f"""
                SELECT ID_CONTATO FROM {self.db.dataBase}.{self.db.schema}.CONTATOS_WPP
                WHERE TELEFONE = :raw
            """),
            {"raw": raw_contato}
        ).mappings().fetchone()

        if not dummy:
            dummy = conn.execute(
                sa.text(f"""
                    SET NOCOUNT ON;
                    INSERT INTO {self.db.dataBase}.{self.db.schema}.CONTATOS_WPP
                        (NOME, TELEFONE, TELEFONE_NORMALIZADO, ATIVO, CONSENTIMENTO_STATUS)
                    VALUES
                        (:nome, :raw, NULL, 0, 'PENDENTE');
                    SELECT SCOPE_IDENTITY() AS ID_CONTATO;
                """),
                {"nome": nome or "Invalido", "raw": raw_contato}
            ).mappings().fetchone()

        id_contato = dummy["ID_CONTATO"]

        conn.execute(
            sa.text(f"""
                IF NOT EXISTS (SELECT 1 FROM {self.db.dataBase}.{self.db.schema}.SOLICITACOES_ENVIO_WPP WHERE ID_CONTROLE_SHEETS = :ctrl_id)
                    INSERT INTO {self.db.dataBase}.{self.db.schema}.SOLICITACOES_ENVIO_WPP
                        (ID_CONTROLE_SHEETS, ID_CONTATO, STATUS_OPERADOR, STATUS_TECNICO, MENSAGEM_ERRO, DATA_CRIACAO)
                    VALUES
                        (:ctrl_id, :id_contato, :operador, 'ERRO', :erro, SYSDATETIME());
                ELSE
                    UPDATE {self.db.dataBase}.{self.db.schema}.SOLICITACOES_ENVIO_WPP
                    SET STATUS_TECNICO = 'ERRO', MENSAGEM_ERRO = :erro
                    WHERE ID_CONTROLE_SHEETS = :ctrl_id AND STATUS_TECNICO = 'PENDENTE';
            """),
            {"ctrl_id": ctrl_id, "id_contato": id_contato, "operador": raw_envio, "erro": erro}
        )
