# Configuracao do Google Sheets

Esta integracao usa a API oficial do Google Sheets; ela nao usa automacao de navegador.

## Conta de servico

1. Crie ou escolha um projeto no Google Cloud.
2. Habilite a Google Sheets API.
3. Crie uma conta de servico e gere uma chave JSON.
4. Guarde esse arquivo fora do repositorio, em diretorio protegido.
5. Compartilhe a planilha com o e-mail da conta de servico, com permissao de editor.
6. Preencha `GOOGLE_SHEETS_SPREADSHEET_ID` e `GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE` no `.env` local.
7. Instale as dependencias com `pip install -r requirements.txt` e execute `python check_google_sheets.py`.

O ID da planilha e a parte da URL entre `/d/` e a proxima barra. Nao registre a chave JSON no Git ou em logs.

## Abas e cabecalhos

A aba `Mensagem` precisa conter exatamente estes cabecalhos:

`Mensagem`, `Arquivo`, `Codigo_Mensagem`, `Ativo`.

A aba `Controle` precisa conter:

`Data`, `Nome`, `Contato`, `Mensagem`, `Ultima Mensagem Enviada`,
`Ultima Mensagem Recebida`, `Envio`, `Último contato`.

Acrescente `ID_Controle` como coluna tecnica adicional (idealmente oculta). Ela sera obrigatoria antes da etapa de sincronizacao de solicitacoes, pois o numero da linha nao e um identificador estavel quando o operador reordena a planilha.

## Leitura e atualizacao

O cliente le valores pela API com `UNFORMATTED_VALUE`, portanto a proxima etapa devera validar a representacao real retornada para selecoes multiplas de `Mensagem`. A API devolve uma matriz de linhas e pode omitir celulas vazias no fim da linha; o cliente preenche essas celulas internamente para manter o mapeamento pelos cabecalhos.

Atualizacoes usam `spreadsheets.values.batchUpdate`, reduzindo chamadas individuais. Esta etapa ainda nao cria solicitacoes, nao altera estados operacionais e nao envia mensagens.
