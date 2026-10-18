"""Agendador periodico com protecao contra execucao simultanea (Single Instance Lock no Windows)."""

from __future__ import annotations

import logging
import msvcrt
import os
from pathlib import Path
import sys
import time
from typing import Any

from google_sheets import GoogleSheetsClient
from sync_incoming import IncomingMessagesSync
from sync_messages import MessageCatalogSync
from sync_queue import QueueSync
from worker import QueueWorker

LOCK_FILE_PATH = Path(__file__).parent / ".scheduler.lock"


class AlreadyRunningError(RuntimeError):
    """Outra instancia do orquestrador ja esta em execucao."""


class ProcessLock:
    """Garante execucao unica do processo usando msvcrt no Windows."""

    def __init__(self, lock_path: Path = LOCK_FILE_PATH) -> None:
        self.lock_path = lock_path
        self._file = None

    def acquire(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.lock_path, "w")
        try:
            # Tenta bloquear 1 byte sem esperar (non-blocking)
            msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            self._file.write(str(os.getpid()))
            self._file.flush()
        except OSError as ex:
            self._file.close()
            self._file = None
            raise AlreadyRunningError("Outra instancia do orquestrador ja esta em execucao.") from ex

    def release(self) -> None:
        if self._file:
            try:
                self._file.seek(0)
                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            finally:
                self._file.close()
                self._file = None
                try:
                    if self.lock_path.exists():
                        self.lock_path.unlink()
                except OSError:
                    pass

    def __enter__(self) -> "ProcessLock":
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()


def run_single_cycle() -> dict[str, Any]:
    """
    Executa um ciclo completo e atomico de operacao:
    1. Sincroniza catalogo de mensagens.
    2. Sincroniza fila de solicitacoes do Google Sheets.
    3. Processa etapas pendentes no worker.
    """
    client = GoogleSheetsClient.from_environment()

    # 1. Catalogo de mensagens
    msg_sync = MessageCatalogSync(client)
    msg_stats = msg_sync.sync()

    # 2. Fila de solicitacoes
    queue_sync = QueueSync(client)
    queue_stats = queue_sync.sync_requests()

    # 3. Worker de envio
    worker = QueueWorker(sheets_client=client)
    worker_stats = worker.process_pending_requests()

    # 4. Sincroniza respostas recebidas dos leads
    incoming_sync = IncomingMessagesSync(sheets_client=client)
    incoming_stats = incoming_sync.sync_incoming_messages()

    return {
        "catalog": msg_stats,
        "queue": queue_stats,
        "worker": worker_stats,
        "incoming": incoming_stats,
    }


def run_scheduler(interval_minutes: int = 15) -> None:
    """Executa o orquestrador periodicamente a cada 15 minutos com lock exclusivo."""
    print(f"Iniciando orquestrador com intervalo de {interval_minutes} minutos.")
    interval_seconds = interval_minutes * 60

    try:
        with ProcessLock():
            while True:
                start = time.time()
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Iniciando ciclo de sincronizacao e envio...")
                try:
                    summary = run_single_cycle()
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Ciclo concluido com sucesso: {summary}")
                except Exception as ex:
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Erro durante o ciclo: {ex}")

                elapsed = time.time() - start
                sleep_time = max(0.0, interval_seconds - elapsed)
                print(f"Proximo ciclo em {sleep_time / 60:.1f} minutos. Pressione Ctrl+C para encerrar.")
                time.sleep(sleep_time)
    except AlreadyRunningError as err:
        print(f"Abortando: {err}")
        sys.exit(0)
    except KeyboardInterrupt:
        print("\nOrquestrador interrompido pelo operador.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h"):
        print("Uso: python scheduler.py [--once | --help]")
        print("  --once   Executa um unico ciclo (sincronizacao + envio) e encerra.")
        print("  (padrao) Executa continuamente a cada 15 minutos com lock exclusivo.")
        sys.exit(0)
    elif len(sys.argv) > 1 and sys.argv[1] == "--once":
        try:
            with ProcessLock():
                res = run_single_cycle()
                print("Execucao unica finalizada:", res)
        except AlreadyRunningError as err:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Execucao ignorada: {err}")
            sys.exit(0)
    else:
        run_scheduler()
