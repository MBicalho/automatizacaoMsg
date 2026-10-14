"""Script para execucao controlada e idempotente de migracoes SQL."""

from pathlib import Path
import re
import sqlalchemy as sa
from functions import dataBase


def execute_sql_file(sql_file_path: Path) -> None:
    dba = dataBase()
    engine = dba.connectDataBase()
    if isinstance(engine, tuple) and not engine[0]:
        raise RuntimeError(f"Falha ao conectar no banco de dados: {engine[1]}")

    content = sql_file_path.read_text(encoding="utf-8")
    # Divide os lotes por comandos GO isolados em linhas
    batches = re.split(r"^\s*GO\s*$", content, flags=re.MULTILINE | re.IGNORECASE)

    with engine.begin() as conn:
        for batch in batches:
            cleaned = batch.strip()
            if cleaned:
                # Remove USE statements se pyodbc ja conectar no banco configurado
                # mas mantem os comandos DDL/DML
                conn.execute(sa.text(cleaned))

    print(f"Migracao executada com sucesso: {sql_file_path.name}")


if __name__ == "__main__":
    migration_file = Path(__file__).parent / "sql" / "migrations" / "001_evolucao_schema_mensagens_filas.sql"
    execute_sql_file(migration_file)
