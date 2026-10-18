"""Script utilitario para validacao de conexao e estrutura da planilha Google Sheets."""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

from google_sheets import CONTROLE_HEADERS, MENSAGENS_HEADERS, GoogleSheetsClient, GoogleSheetsError


def main() -> None:
    load_dotenv(override=True)
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "").strip()
    credentials_file = os.getenv("GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE", "").strip()

    print("=" * 60)
    print(" Verificacao de Integracao com Google Sheets")
    print("=" * 60)
    print(f"Planilha ID: {spreadsheet_id if spreadsheet_id else '[NAO DEFINIDO]'}")
    print(f"Arquivo de Credenciais: {credentials_file if credentials_file else '[NAO DEFINIDO]'}")

    if not spreadsheet_id:
        print("\n[ERRO] A variavel GOOGLE_SHEETS_SPREADSHEET_ID nao foi configurada no .env.")
        return

    if not credentials_file or not Path(credentials_file).is_file():
        print(f"\n[AVISO] O arquivo de credenciais da service account nao foi encontrado: {credentials_file}")
        print("Coloque o arquivo .json da conta de servico do Google Cloud no caminho especificado para habilitar a integracao.")
        return

    try:
        client = GoogleSheetsClient.from_environment()
        sheets = client.list_sheet_names()
        print(f"\nAbas encontradas na planilha: {', '.join(sheets)}")

        # Valida aba Mensagem
        msg_tab = client.mensagens_tab
        print(f"\nValidando aba '{msg_tab}'...")
        headers_msg, rows_msg = client.validate_headers(msg_tab, MENSAGENS_HEADERS)
        print(f" -> Cabecalhos validos: {headers_msg}")
        print(f" -> Total de templates cadastrados: {len(rows_msg)}")

        # Valida aba Controle
        ctrl_tab = client.controle_tab
        print(f"\nValidando aba '{ctrl_tab}'...")
        headers_ctrl, rows_ctrl = client.validate_headers(ctrl_tab, CONTROLE_HEADERS)
        print(f" -> Cabecalhos validos: {headers_ctrl}")
        print(f" -> Total de solicitacoes na fila: {len(rows_ctrl)}")

        print("\n[SUCESSO] Conexao e estrutura do Google Sheets estao 100% compativeis!")

    except GoogleSheetsError as err:
        print(f"\n[ERRO NA PLANILHA] {err}")
    except Exception as ex:
        print(f"\n[FALHA INESPERADA] {ex}")


if __name__ == "__main__":
    main()
