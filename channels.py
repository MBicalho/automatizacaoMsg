"""Abstracao e adaptadores de canais de envio (Simulacao Dry-Run, WhatsApp Desktop e API Oficial)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import os
from pathlib import Path
import re
import time
from typing import Any
from dotenv import load_dotenv

from phone_utils import mask_phone


@dataclass(frozen=True)
class ChannelResult:
    """Resultado padronizado da tentativa de envio atraves de um canal."""

    success: bool
    status: str  # 'SUCESSO', 'FALHA', 'INCERTO'
    detail: str
    channel_name: str
    duration_seconds: float = 0.0


class WhatsAppChannel(ABC):
    """Interface padrao para canais de mensageria WhatsApp."""

    @abstractmethod
    def send_text(self, phone: str, text: str, instance: str | None = None, **kwargs: Any) -> ChannelResult:
        """Envia uma mensagem de texto simples para o telefone normalizado."""

    @abstractmethod
    def send_file(
        self,
        phone: str,
        file_path: Path,
        caption: str | None = None,
        is_image: bool = False,
        instance: str | None = None,
        **kwargs: Any,
    ) -> ChannelResult:
        """Envia um arquivo (documento ou imagem) com legenda opcional."""


class DryRunWhatsAppChannel(WhatsAppChannel):
    """
    Canal de simulacao segura. Nao move o mouse, nao abre janelas,
    nao envia mensagens reais e mascara informacoes pessoais em logs.
    """

    def __init__(self, simulated_delay_seconds: float = 0.05) -> None:
        self.simulated_delay = simulated_delay_seconds

    def send_text(self, phone: str, text: str, instance: str | None = None, **kwargs: Any) -> ChannelResult:
        start_time = time.monotonic()
        time.sleep(self.simulated_delay)
        masked = mask_phone(phone)
        summary = (text[:40] + "...") if len(text) > 40 else text
        inst_label = f"[{instance}] " if instance else ""
        detail = (
            f"[DRY-RUN] {inst_label}Simulacao de envio de texto para {masked}. "
            f"Tamanho do texto: {len(text)} caracteres ('{summary}')."
        )
        return ChannelResult(
            success=True,
            status="SUCESSO",
            detail=detail,
            channel_name="SIMULACAO",
            duration_seconds=round(time.monotonic() - start_time, 3),
        )

    def send_file(
        self,
        phone: str,
        file_path: Path,
        caption: str | None = None,
        is_image: bool = False,
        instance: str | None = None,
        **kwargs: Any,
    ) -> ChannelResult:
        start_time = time.monotonic()
        time.sleep(self.simulated_delay)
        masked = mask_phone(phone)
        ext = file_path.suffix.lower()
        if is_image or ext in (".png", ".jpg", ".jpeg", ".webp"):
            file_type = "imagem"
        elif ext in (".mp4", ".mov", ".avi", ".mkv"):
            file_type = "video"
        elif ext in (".mp3", ".ogg", ".m4a", ".wav"):
            file_type = "audio"
        else:
            file_type = "documento"

        inst_label = f"[{instance}] " if instance else ""
        detail = (
            f"[DRY-RUN] {inst_label}Simulacao de envio de {file_type} para {masked}. "
            f"Arquivo: {file_path.name} ({file_path.stat().st_size if file_path.exists() else 0} bytes). "
            f"Legenda: '{caption or ''}'."
        )
        return ChannelResult(
            success=True,
            status="SUCESSO",
            detail=detail,
            channel_name="SIMULACAO",
            duration_seconds=round(time.monotonic() - start_time, 3),
        )


class DesktopWhatsAppChannel(WhatsAppChannel):
    """
    Adaptador para automacao do WhatsApp Desktop legado via PyAutoGUI e startfile.
    Possui tratamento para status INCERTO caso o processo sofra interrupcao.
    """

    def __init__(self) -> None:
        # Importacao tardia para nao exigir bibliotecas de GUI em ambientes headless
        import functions  # type: ignore

        self._functions = functions
        self._current_phone: str | None = None

    def _prepare_chat(self, contact_obj, phone: str) -> None:
        clean_phone = re.sub(r"\D", "", phone)
        if self._current_phone != clean_phone:
            contact_obj.eventSelectUser()
            self._current_phone = clean_phone
        else:
            # Mensagem subsequente para o mesmo contato cuja conversa ja esta aberta na tela:
            # Nao reabre o protocolo (evita recarregar conversa e perder o foco do campo de texto)
            time.sleep(2.5)

    def send_text(self, phone: str, text: str, instance: str | None = None, **kwargs: Any) -> ChannelResult:
        start_time = time.monotonic()
        masked = mask_phone(phone)
        try:
            # Cria estrutura compativel com o contatoWpp legado
            class FakeContact:
                def __init__(self, p: str, msg: str):
                    self.NOME = "Contato"
                    self.TELEFONE = p
                    self.ID_TIPO_ENVIO = 1
                    self.DESCRICAO_TIPO_ENVIO = "MENSAGEM"
                    self.CAMINHO_ARQUIVO = None
                    self.DESCRICAO_MENSAGEM = msg

            contact_obj = self._functions.contatoWpp(FakeContact(phone, text))
            self._prepare_chat(contact_obj, phone)
            contact_obj.eventSendMsg()

            return ChannelResult(
                success=True,
                status="SUCESSO",
                detail=f"Mensagem enviada via WhatsApp Desktop para {masked}.",
                channel_name="WHATSAPP_DESKTOP",
                duration_seconds=round(time.monotonic() - start_time, 3),
            )
        except Exception as ex:
            # Em caso de falha, invalida a sessao atual para forcar reabertura no proximo envio
            self._current_phone = None
            return ChannelResult(
                success=False,
                status="INCERTO",
                detail=f"Falha na automacao WhatsApp Desktop para {masked}: {ex}",
                channel_name="WHATSAPP_DESKTOP",
                duration_seconds=round(time.monotonic() - start_time, 3),
            )

    def send_file(
        self,
        phone: str,
        file_path: Path,
        caption: str | None = None,
        is_image: bool = False,
        instance: str | None = None,
        **kwargs: Any,
    ) -> ChannelResult:
        start_time = time.monotonic()
        masked = mask_phone(phone)
        try:
            class FakeContactFile:
                def __init__(self, p: str, path: str, cap: str | None, img: bool):
                    self.NOME = "Contato"
                    self.TELEFONE = p
                    self.ID_TIPO_ENVIO = 3 if img else 2
                    self.DESCRICAO_TIPO_ENVIO = "IMAGEM" if img else "DOCUMENTO"
                    self.CAMINHO_ARQUIVO = path
                    self.DESCRICAO_MENSAGEM = cap or ""

            contact_obj = self._functions.contatoWpp(
                FakeContactFile(phone, str(file_path), caption, is_image)
            )
            self._prepare_chat(contact_obj, phone)
            contact_obj.eventSendFile()

            return ChannelResult(
                success=True,
                status="SUCESSO",
                detail=f"Arquivo {file_path.name} enviado via WhatsApp Desktop para {masked}.",
                channel_name="WHATSAPP_DESKTOP",
                duration_seconds=round(time.monotonic() - start_time, 3),
            )
        except Exception as ex:
            self._current_phone = None
            return ChannelResult(
                success=False,
                status="INCERTO",
                detail=f"Falha no envio de arquivo via WhatsApp Desktop para {masked}: {ex}",
                channel_name="WHATSAPP_DESKTOP",
                duration_seconds=round(time.monotonic() - start_time, 3),
            )


class WhatsAppBusinessApiChannel(WhatsAppChannel):
    """Adaptador stub para futura migracao para a API Oficial do WhatsApp Business."""

    def __init__(self, api_token: str = "", phone_number_id: str = "") -> None:
        self.api_token = api_token
        self.phone_number_id = phone_number_id

    def send_text(self, phone: str, text: str) -> ChannelResult:
        return ChannelResult(
            success=False,
            status="FALHA",
            detail="API Oficial do WhatsApp Business nao configurada.",
            channel_name="WHATSAPP_BUSINESS_API",
        )

    def send_file(
        self,
        phone: str,
        file_path: Path,
        caption: str | None = None,
        is_image: bool = False,
    ) -> ChannelResult:
        return ChannelResult(
            success=False,
            status="FALHA",
            detail="API Oficial do WhatsApp Business nao configurada.",
            channel_name="WHATSAPP_BUSINESS_API",
        )


class EvolutionApiWhatsAppChannel(WhatsAppChannel):
    """
    Adaptador para envio atraves da Evolution API local (suporta multiplas contas simultaneas).
    Faz o balanceamento round-robin entre as instancias configuradas ou usa a instancia informada.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        api_key: str = "minha_chave_secreta_123",
        instances: list[str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.instances = instances or ["conta_1", "conta_2"]
        self._current_index = 0

    def _get_next_instance(self) -> str:
        if not self.instances:
            return "conta_1"
        inst = self.instances[self._current_index % len(self.instances)]
        self._current_index += 1
        return inst

    def send_text(self, phone: str, text: str, instance: str | None = None) -> ChannelResult:
        import urllib.request
        import urllib.error
        import json

        start_time = time.monotonic()
        clean_phone = re.sub(r"\D", "", phone)
        masked = mask_phone(clean_phone)
        inst = instance or self._get_next_instance()

        url = f"{self.base_url}/message/sendText/{inst}"
        headers = {
            "apikey": self.api_key,
            "Content-Type": "application/json",
        }
        payload = json.dumps({
            "number": clean_phone,
            "text": text,
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
                return ChannelResult(
                    success=True,
                    status="SUCESSO",
                    detail=f"Mensagem enviada via Evolution API ({inst}) para {masked}.",
                    channel_name=f"EVOLUTION_API_{inst.upper()}",
                    duration_seconds=round(time.monotonic() - start_time, 3),
                )
        except urllib.error.HTTPError as ex:
            err_body = ex.read().decode()
            if "reading 'id'" in err_body or "not found" in err_body.lower() or ex.code == 404:
                friendly_msg = f"A conta '{inst}' não está conectada ao WhatsApp. Abra o qrcodes.html e escaneie o QR Code."
            else:
                friendly_msg = f"Erro HTTP {ex.code} na Evolution API ({inst}) para {masked}: {err_body}"
            return ChannelResult(
                success=False,
                status="FALHA",
                detail=friendly_msg,
                channel_name=f"EVOLUTION_API_{inst.upper()}",
                duration_seconds=round(time.monotonic() - start_time, 3),
            )
        except Exception as ex:
            return ChannelResult(
                success=False,
                status="FALHA",
                detail=f"Falha de conexao com a Evolution API ({inst}) para {masked}: {ex}",
                channel_name=f"EVOLUTION_API_{inst.upper()}",
                duration_seconds=round(time.monotonic() - start_time, 3),
            )

    def send_file(
        self,
        phone: str,
        file_path: Path,
        caption: str | None = None,
        is_image: bool = False,
        instance: str | None = None,
    ) -> ChannelResult:
        import urllib.request
        import urllib.error
        import json
        import base64
        import mimetypes

        start_time = time.monotonic()
        clean_phone = re.sub(r"\D", "", phone)
        masked = mask_phone(clean_phone)
        inst = instance or self._get_next_instance()

        if not file_path.exists():
            return ChannelResult(
                success=False,
                status="FALHA",
                detail=f"Arquivo nao encontrado para envio: {file_path}",
                channel_name=f"EVOLUTION_API_{inst.upper()}",
                duration_seconds=round(time.monotonic() - start_time, 3),
            )

        suffix = file_path.suffix.lower()
        if is_image or suffix in (".png", ".jpg", ".jpeg", ".webp"):
            media_type = "image"
            default_mime = "image/jpeg"
        elif suffix in (".mp4", ".mov", ".avi", ".mkv"):
            media_type = "video"
            default_mime = "video/mp4"
        elif suffix in (".mp3", ".ogg", ".m4a", ".wav", ".aac"):
            media_type = "audio"
            default_mime = "audio/mp4"
        else:
            media_type = "document"
            default_mime = "application/octet-stream"

        mime_type, _ = mimetypes.guess_type(str(file_path))
        mime_type = mime_type or default_mime

        with open(file_path, "rb") as f:
            encoded_media = base64.b64encode(f.read()).decode("utf-8")

        url = f"{self.base_url}/message/sendMedia/{inst}"
        headers = {
            "apikey": self.api_key,
            "Content-Type": "application/json",
        }
        payload = json.dumps({
            "number": clean_phone,
            "mediatype": media_type,
            "mimetype": mime_type,
            "caption": caption or "",
            "media": encoded_media,
            "fileName": file_path.name,
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode())
                return ChannelResult(
                    success=True,
                    status="SUCESSO",
                    detail=f"Arquivo {file_path.name} enviado via Evolution API ({inst}) para {masked}.",
                    channel_name=f"EVOLUTION_API_{inst.upper()}",
                    duration_seconds=round(time.monotonic() - start_time, 3),
                )
        except urllib.error.HTTPError as ex:
            err_body = ex.read().decode()
            if "reading 'id'" in err_body or "not found" in err_body.lower() or ex.code == 404:
                friendly_msg = f"A conta '{inst}' não está conectada ao WhatsApp. Abra o qrcodes.html e escaneie o QR Code."
            else:
                friendly_msg = f"Erro HTTP {ex.code} ao enviar arquivo via Evolution API ({inst}): {err_body}"
            return ChannelResult(
                success=False,
                status="FALHA",
                detail=friendly_msg,
                channel_name=f"EVOLUTION_API_{inst.upper()}",
                duration_seconds=round(time.monotonic() - start_time, 3),
            )
        except Exception as ex:
            return ChannelResult(
                success=False,
                status="FALHA",
                detail=f"Falha de conexao ao enviar arquivo via Evolution API ({inst}): {ex}",
                channel_name=f"EVOLUTION_API_{inst.upper()}",
                duration_seconds=round(time.monotonic() - start_time, 3),
            )


def get_channel() -> WhatsAppChannel:
    """
    Fabrica de canais: respeita WHATSAPP_DRY_RUN (padrao True).
    Nunca executa envio real a menos que WHATSAPP_DRY_RUN seja false.
    """
    load_dotenv(override=True)
    dry_run = os.getenv("WHATSAPP_DRY_RUN", "true").strip().lower()

    if dry_run in ("true", "1", "yes", ""):
        return DryRunWhatsAppChannel()

    channel_type = os.getenv("WHATSAPP_CHANNEL", "desktop").strip().lower()
    if channel_type == "business_api":
        return WhatsAppBusinessApiChannel(
            api_token=os.getenv("WHATSAPP_API_TOKEN", ""),
            phone_number_id=os.getenv("WHATSAPP_PHONE_NUMBER_ID", ""),
        )
    elif channel_type in ("evolution_api", "evolution"):
        raw_instances = os.getenv("EVOLUTION_INSTANCES", "conta_1,conta_2")
        inst_list = [i.strip() for i in raw_instances.split(",") if i.strip()]
        return EvolutionApiWhatsAppChannel(
            base_url=os.getenv("EVOLUTION_API_URL", "http://localhost:8080"),
            api_key=os.getenv("EVOLUTION_API_KEY", "minha_chave_secreta_123"),
            instances=inst_list,
        )

    return DesktopWhatsAppChannel()
