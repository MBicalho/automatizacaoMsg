import re
import sys
from pathlib import Path

# Add project root to path
project_root = Path(r"c:\Repositorios\automatizacaoMsg")
sys.path.insert(0, str(project_root))

from functions import dataBase
from google_sheets import GoogleSheetsClient
from sync_messages import MessageCatalogSync
import sqlalchemy as sa

print("=== 1. EXECUTANDO RESET COMPLETO NO SQL SERVER ===")
sql_path = project_root / "sql" / "reset_test_data.sql"
with open(sql_path, "r", encoding="utf-8") as f:
    sql_content = f.read()

# Divide os batches por GO
batches = [b.strip() for b in re.split(r"(?im)^\s*GO\s*$", sql_content) if b.strip()]

db = dataBase()
engine = db.connectDataBase()
if isinstance(engine, tuple) and not engine[0]:
    print(f"Erro ao conectar ao banco: {engine[1]}")
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
            print(f"Batch {idx} executado com sucesso.")
        except Exception as ex:
            raw_conn.rollback()
            print(f"Erro no batch {idx}: {ex}")
            raise
finally:
    raw_conn.close()

print("\n=== 2. SINCRONIZANDO CATALOGO DE MENSAGENS ===")
sheets = GoogleSheetsClient.from_environment()
cat_sync = MessageCatalogSync(sheets_client=sheets)
cat_res = cat_sync.sync()
print("Catalogo sincronizado:", cat_res)

print("\n=== 3. VERIFICANDO TABELAS DO BANCO APOS RESET ===")
with engine.connect() as conn:
    for tab in ["CONTROLE_ENVIO_WPP", "CONTATOS_WPP", "SOLICITACOES_ENVIO_WPP", "ETAPAS_SOLICITACAO_WPP", "HISTORICO_TENTATIVAS_ENVIO_WPP", "MENSAGEM_WPP", "TIPO_ENVIO_WPP"]:
        count = conn.execute(sa.text(f"SELECT COUNT(*) FROM automatizacao.{tab}")).scalar()
        print(f"Tabela automatizacao.{tab}: {count} registros")

print("\n=== RESET DO BANCO CONCLUIDO COM SUCESSO! ===")
