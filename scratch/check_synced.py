import sys
from pathlib import Path
project_root = Path(r"c:\Repositorios\automatizacaoMsg")
sys.path.insert(0, str(project_root))

from functions import dataBase
import sqlalchemy as sa

db = dataBase()
engine = db.connectDataBase()

with engine.connect() as conn:
    rows = conn.execute(sa.text("""
        SELECT S.ID_SOLICITACAO, C.NOME, C.TELEFONE_NORMALIZADO, S.ORIGEM, S.INSTANCIA_ENVIO, S.STATUS_OPERADOR, S.STATUS_TECNICO, S.CODIGOS_MENSAGENS
        FROM automatizacao.SOLICITACOES_ENVIO_WPP S
        JOIN automatizacao.CONTATOS_WPP C ON S.ID_CONTATO = C.ID_CONTATO
        ORDER BY S.ID_SOLICITACAO
    """)).fetchall()
    print("=== SOLICITACOES SINCRONIZADAS ===")
    for r in rows:
        print(f"ID {r[0]}: {r[1]} ({r[2]}) | Origem: '{r[3]}' -> Instancia: '{r[4]}' | Status: {r[5]}/{r[6]} | Msgs: {r[7]}")
