"""Validacao rigorosa de anexos para seguranca de arquivos e prevencao de Directory Traversal."""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

ALLOWED_EXTENSIONS = {
    # Documentos
    ".pdf",
    ".docx",
    ".doc",
    ".txt",
    ".xlsx",
    ".xls",
    ".csv",
    # Imagens
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    # Videos
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    # Audios
    ".mp3",
    ".ogg",
    ".m4a",
    ".wav",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}
AUDIO_EXTENSIONS = {".mp3", ".ogg", ".m4a", ".wav"}


class AttachmentSecurityError(ValueError):
    """Tentativa de violacao de seguranca de arquivos (ex: path traversal ou extensao proibida)."""


def get_attachments_base_dir() -> Path:
    """Retorna o diretorio base canonico configurado no .env ou a pasta anexos padrao."""
    load_dotenv(override=True)
    env_dir = os.getenv("ANEXOS_BASE_DIR", "").strip()
    if env_dir:
        base = Path(env_dir).resolve()
    else:
        base = (Path(__file__).parent / "anexos").resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base


def resolve_and_validate_attachment(
    file_reference: str | None,
    base_dir: Path | str | None = None,
    must_exist: bool = False,
) -> Path | None:
    """
    Resolve e valida o caminho de um anexo:
    1. Impede Directory Traversal (escapar da pasta base).
    2. Valida se a extensao e permitida.
    3. Suporta referencias com ou sem extensao (se sem extensao, busca arquivo correspondente no diretorio).
    4. Opcionalmente verifica a existencia fisica do arquivo.
    """
    if not file_reference or not str(file_reference).strip():
        return None

    ref_str = str(file_reference).strip()

    # Previne caminhos absolutos ou relativos maliciosos
    if ref_str.startswith("/") or ref_str.startswith("\\") or (len(ref_str) > 1 and ref_str[1] == ":"):
        # Se for absoluto, so e permitido se estiver dentro do base_dir
        pass

    if base_dir is None:
        base_path = get_attachments_base_dir()
    else:
        base_path = Path(base_dir).resolve()

    target_candidate = (base_path / ref_str).resolve()

    # Checagem estrita de Directory Traversal
    try:
        target_candidate.relative_to(base_path)
    except ValueError as ex:
        raise AttachmentSecurityError(
            f"Tentativa de evasao de diretorio detectada para o arquivo: '{ref_str}'."
        ) from ex

    # Se a referencia ja tiver uma extensao
    if target_candidate.suffix:
        ext = target_candidate.suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise AttachmentSecurityError(
                f"Extensao de arquivo nao autorizada: '{ext}'. Extensoes permitidas: {sorted(ALLOWED_EXTENSIONS)}."
            )
        resolved_file = target_candidate
    else:
        # Se o usuario especificou apenas o nome sem extensao (ex: 'overview')
        matched = []
        if base_path.exists():
            for entry in base_path.iterdir():
                if entry.is_file() and entry.stem.lower() == ref_str.lower():
                    if entry.suffix.lower() in ALLOWED_EXTENSIONS:
                        matched.append(entry)

        if len(matched) == 1:
            resolved_file = matched[0]
        elif len(matched) > 1:
            raise AttachmentSecurityError(
                f"Multiplos arquivos encontrados para a referencia sem extensao '{ref_str}': "
                f"{[p.name for p in matched]}. Especifique a extensao desejada."
            )
        else:
            # Assume extensao padrao .pdf ou mantem o candidato para checagem de existencia
            resolved_file = target_candidate

    if must_exist and not resolved_file.is_file():
        raise FileNotFoundError(
            f"Anexo obrigatorio nao encontrado no diretorio de anexos: '{resolved_file.name}'."
        )

    return resolved_file


def classify_attachment_type(file_path: Path | None) -> int:
    """
    Classifica o ID_TIPO_ENVIO:
    1: MENSAGEM (sem arquivo)
    2: DOCUMENTO
    3: IMAGEM
    """
    if file_path is None:
        return 1
    if file_path.suffix.lower() in IMAGE_EXTENSIONS:
        return 3
    return 2
