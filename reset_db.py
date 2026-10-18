"""Script para reset completo e seguro dos dados de teste no SQL Server."""

import re
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

import sqlalchemy as sa
from functions import dataBase
from google_sheets import GoogleSheetsClient
from sync_messages import MessageCatalogSync


def reset_database() -> None:
    print("=== 1. EXECUTANDO RESET COMPLETO NO SQL SERVER ===")
    sql_path = project_root / "sql" / "reset_test_data.sql"
    with open(sql_path, "r", encoding="utf-8") as f:
        sql_content = f.read()

    batches = [b.strip() for b in re.split(r"(?im)^\s*GO\s*$", sql_content) if b.strip()]

    db = dataBase()
    engine = db.connectDataBase()
    if isinstance(engine, tuple) and not engine[0]:
        print(f"Erro ao conectar ao banco de dados: {engine[1]}")
        sys.exit(1)

    raw_conn = engine.raw_connection()
    try:
        cursor = raw_conn.cursor()
        for idx, batch in enumerate(batches, start=1):
            cleaned = re.sub(r"/\*.*?\*/", "", batch, flags=re.DOTALL)
            cleaned = re.sub(r"--.*$", "", cleaned, flags=re.MULTILINE).strip()
            if not cleaned:
                continue
            try:
                cursor.execute(batch)
                while cursor.nextset():
                    pass
                raw_conn.commit()
            except Exception as ex:
                raw_conn.rollback()
                print(f"Erro no batch {idx}: {ex}")
                raise
        print("SQL Server limpo e identities reiniciadas com sucesso.")
    finally:
        raw_conn.close()

    print("\n=== 2. RECARREGANDO CATALOGO DE MENSAGENS ===")
    sheets = GoogleSheetsClient.from_environment()
    cat_sync = MessageCatalogSync(sheets_client=sheets)
    cat_res = cat_sync.sync()
    print("Catalogo recarregado:", cat_res)

    print("\n=== 3. CONFERINDO TABELAS APOS O RESET ===")
    with engine.connect() as conn:
        for tab in [
            "SOLICITACOES_ENVIO_WPP",
            "ETAPAS_SOLICITACAO_WPP",
            "HISTORICO_TENTATIVAS_ENVIO_WPP",
            "CONTROLE_ENVIO_WPP",
            "CONTATOS_WPP",
            "MENSAGEM_WPP",
            "TIPO_ENVIO_WPP",
        ]:
            count = conn.execute(sa.text(f"SELECT COUNT(*) FROM automatizacao.{tab}")).scalar()
            print(f"- automatizacao.{tab}: {count} registros")

    print("\n=== BANCO DE DADOS RESETADO E PRONTO PARA NOVO USO! ===")


if __name__ == "__main__":
    reset_database()
