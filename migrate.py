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
            if not cleaned:
                continue

            # Se for apenas declaracao USE, pode ignorar pois pyodbc ja esta no banco
            if re.match(r"^USE\s+\[?\w+\]?;?$", cleaned, flags=re.IGNORECASE):
                continue

            conn.execute(sa.text(cleaned))

    print(f"Migracao executada com sucesso: {sql_file_path.name}")


def run_all_migrations() -> None:
    migrations_dir = Path(__file__).parent / "sql" / "migrations"
    migration_files = sorted(migrations_dir.glob("*.sql"))

    if not migration_files:
        print(f"Nenhum arquivo de migracao encontrado em {migrations_dir}")
        return

    print(f"Encontradas {len(migration_files)} migracoes. Iniciando execucao...")
    for migration_file in migration_files:
        execute_sql_file(migration_file)

    print("Todas as migracoes foram concluidas com sucesso!")


if __name__ == "__main__":
    run_all_migrations()
