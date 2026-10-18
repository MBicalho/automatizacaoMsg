"""Sincronizacao de mensagens recebidas dos leads diretamente para a planilha Google Sheets."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
import re
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
import psycopg2

from google_sheets import GoogleSheetsClient
from phone_utils import normalize_brazilian_phone, InvalidPhoneNumberError

logger = logging.getLogger(__name__)


def _extract_message_text(msg_dict: dict[str, Any] | None, msg_type: str | None) -> str:
    """Extrai texto legivel ou indicador de midia de um objeto de mensagem da Evolution API."""
    if not msg_dict:
        if msg_type:
            tipo_map = {
                "audioMessage": "[Áudio]",
                "imageMessage": "[Imagem]",
                "documentMessage": "[Documento]",
                "videoMessage": "[Vídeo]",
                "stickerMessage": "[Figurinha]",
                "contactMessage": "[Contato]",
                "locationMessage": "[Localização]",
            }
            return tipo_map.get(msg_type, f"[{msg_type}]")
        return ""

    # Mensagem de texto simples
    if msg_dict.get("conversation"):
        return str(msg_dict["conversation"]).strip()

    # Mensagem de texto estendida
    ext = msg_dict.get("extendedTextMessage")
    if isinstance(ext, dict) and ext.get("text"):
        return str(ext["text"]).strip()

    # Imagem com legenda
    img = msg_dict.get("imageMessage")
    if isinstance(img, dict):
        caption = (img.get("caption") or "").strip()
        return f"[Imagem: {caption}]" if caption else "[Imagem]"

    # Documento com legenda
    doc = msg_dict.get("documentMessage")
    if isinstance(doc, dict):
        file_name = (doc.get("fileName") or "").strip()
        return f"[Documento: {file_name}]" if file_name else "[Documento]"

    # Audio
    if "audioMessage" in msg_dict:
        return "[Áudio]"

    # Video
    if "videoMessage" in msg_dict:
        return "[Vídeo]"

    return ""


class IncomingMessagesSync:
    """
    Sincroniza mensagens recebidas dos leads (respostas) para a coluna
    'Ultima Mensagem Recebida' da planilha Google Sheets.
    """

    def __init__(
        self,
        sheets_client: GoogleSheetsClient | None = None,
        db_url: str | None = None,
        tz_name: str = "America/Sao_Paulo",
    ) -> None:
        load_dotenv(override=True)
        self.sheets = sheets_client or GoogleSheetsClient.from_environment()
        self.db_url = db_url or os.getenv(
            "EVOLUTION_DB_URL",
            "postgresql://evolution:evolution_pass_123@localhost:5432/evolution",
        )
        self.tz = ZoneInfo(tz_name)

    def _get_db_connection(self):
        return psycopg2.connect(self.db_url)

    def fetch_latest_responses_for_phone(
        self, conn, phone: str
    ) -> tuple[list[str], datetime | None]:
        """
        Busca mensagens recebidas do lead apos a ultima mensagem que enviamos a ele.
        Retorna (lista_de_textos, data_hora_da_ultima_mensagem).
        """
        # Limpa telefone para pegar apenas digitos
        clean_phone = re.sub(r"\D", "", phone)
        if len(clean_phone) < 8:
            return [], None

        # Utiliza os ultimos 8 digitos para casar com ou sem nono digito
        suffix = clean_phone[-8:]
        pattern = f"%{suffix}%"

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 
                    id,
                    (key->>'fromMe')::boolean as from_me,
                    COALESCE(key->>'remoteJidAlt', key->>'remoteJid') as jid,
                    "messageTimestamp" as ts,
                    COALESCE(
                        message->>'conversation',
                        message->'extendedTextMessage'->>'text',
                        ''
                    ) as direct_text,
                    message,
                    "messageType"
                FROM "Message"
                WHERE (key->>'remoteJidAlt' LIKE %s OR key->>'remoteJid' LIKE %s)
                  AND (key->>'remoteJid') NOT LIKE '%%@g.us'
                ORDER BY "messageTimestamp" ASC;
                """,
                (pattern, pattern),
            )
            rows = cur.fetchall()

        if not rows:
            return [], None

        # 1. Encontra timestamp da ultima mensagem enviada por nos (fromMe = True)
        last_sent_ts = 0
        for r in rows:
            from_me = r[1]
            ts = r[3]
            if from_me and ts > last_sent_ts:
                last_sent_ts = ts

        # 2. Coleta mensagens recebidas do lead APOS nossa ultima mensagem
        # Se nunca enviamos mensagem, pega as ultimas mensagens do lead
        incoming_texts: list[str] = []
        last_incoming_dt: datetime | None = None

        for r in rows:
            from_me = r[1]
            ts = r[3]
            msg_dict = r[5]
            msg_type = r[6]

            if not from_me and ts > last_sent_ts:
                txt = _extract_message_text(msg_dict, msg_type)
                if txt:
                    incoming_texts.append(txt)
                    last_incoming_dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(self.tz)

        return incoming_texts, last_incoming_dt

    def sync_incoming_messages(self) -> dict[str, Any]:
        """
        Executa a verificacao de novas respostas para todos os leads da planilha
        e atualiza 'Ultima Mensagem Recebida' e 'Último contato' onde houver resposta nova.
        """
        try:
            conn = self._get_db_connection()
        except Exception as ex:
            logger.warning(f"Nao foi possivel conectar ao banco Evolution para ler respostas: {ex}")
            return {"checked": 0, "updated": 0, "error": str(ex)}

        try:
            headers, rows = self.sheets.read_table(self.sheets.controle_tab)
            if "Ultima Mensagem Recebida" not in headers:
                logger.warning("Coluna 'Ultima Mensagem Recebida' nao encontrada na planilha.")
                return {"checked": 0, "updated": 0, "error": "Coluna ausente"}

            checked_count = 0
            updated_count = 0

            for row in rows:
                raw_contato = row.values.get("Contato")
                if not raw_contato:
                    continue

                checked_count += 1
                try:
                    norm_phone = normalize_brazilian_phone(raw_contato)
                except InvalidPhoneNumberError:
                    norm_phone = re.sub(r"\D", "", str(raw_contato))

                responses, last_dt = self.fetch_latest_responses_for_phone(conn, norm_phone)

                if not responses or not last_dt:
                    continue

                # Formata no padrao selecionado:
                # 'Msg 1 | Msg 2 | Msg 3 (DD/MM/YYYY HH:MM)'
                dt_str = last_dt.strftime("%d/%m/%Y %H:%M")
                msgs_joined = " | ".join(responses)
                formatted_response = f"{msgs_joined} ({dt_str})"

                current_received = str(row.values.get("Ultima Mensagem Recebida") or "").strip()

                # Atualiza apenas se for diferente do que ja esta na planilha
                if formatted_response != current_received:
                    update_payload: dict[str, Any] = {
                        "Ultima Mensagem Recebida": formatted_response,
                    }
                    if "Último contato" in headers:
                        update_payload["Último contato"] = dt_str

                    self.sheets.update_control_fields(row.row_number, update_payload)
                    logger.info(
                        f"Linha {row.row_number} ({row.values.get('Nome')}): Nova resposta gravada -> {formatted_response}"
                    )
                    updated_count += 1

            return {"checked": checked_count, "updated": updated_count}
        finally:
            conn.close()
