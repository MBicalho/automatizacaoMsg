# Automatização e Rastreabilidade de Envio de Mensagens (WhatsApp)

Sistema corporativo para captação/sincronização de leads a partir do Google Sheets, catálogo de mensagens com suporte a anexos e múltiplos templates sequenciais, fila persistente no SQL Server, conformidade com a LGPD e canal de envio desacoplado (com modo de simulação `dry-run` por padrão e suporte a WhatsApp Desktop e API Oficial).

---

## 🚀 Arquitetura Geral

- **Fonte da Verdade Persistente**: SQL Server (banco `AUTOMATIZACAO`, schema `automatizacao`).
- **Interface Operacional e Catálogo**: Google Sheets via API oficial (contas de serviço do Google Cloud, sem automação de navegador).
- **Canal de Envio Desacoplado**:
  - `DryRunWhatsAppChannel`: simulação segura padrão (sem automação de interface e sem envio real acidental).
  - `DesktopWhatsAppChannel`: automação desktop legada via PyAutoGUI, pynput e URI scheme `whatsapp://send`.
  - `WhatsAppBusinessApiChannel`: estrutura extensível para a API Oficial do WhatsApp Business.
- **Rastreabilidade e LGPD**:
  - Auditoria completa por etapa de envio na tabela `HISTORICO_TENTATIVAS_ENVIO_WPP`.
  - Controle explícito de consentimento (`OPT_IN`), revogação e bloqueio (`OPT_OUT`).
  - Mascaramento rigoroso de telefones e dados sensíveis em logs e consoles.
  - Prevenção contra Directory Traversal em arquivos de anexo.
- **Idempotência e Concorrência**:
  - Cada etapa possui chave de idempotência única: `{ID_CONTROLE}:{ORDEM}:{CODIGO_MENSAGEM}`.
  - Orquestrador com Single-Instance Process Lock no Windows contra execuções simultâneas.
  - Recuperação segura de etapas abandonadas em `PROCESSANDO` após timeout, sem reenvio cego.

---

## 📋 Abas da Planilha (Google Sheets)

1. **`Mensagem`** (Catálogo de templates):
   - `Mensagem`: texto do template, suportando `{{nome}}` e `{{nome_completo}}`.
   - `Arquivo`: nome ou caminho do anexo (resolvido exclusivamente dentro de `ANEXOS_BASE_DIR`).
   - `Codigo_Mensagem`: identificador textual único, estável e sem vírgulas (ex: `boas-vindas`, `apresentacao`).
   - `Ativo`: `1` para disponível, `0` para bloqueado.

2. **`Controle`** (Fila operacional de solicitações):
   - `ID_CONTROLE`: identificador técnico gerado automaticamente pelo sistema (ex: `CTRL-uuid`).
   - `Data`: data da solicitação.
   - `Nome`: nome do contato/lead.
   - `Contato`: telefone brasileiro (formatado ou somente dígitos).
   - `Mensagem`: um ou mais códigos de mensagem separados por vírgula (a ordem é estritamente preservada).
   - `Envio`: preenchido pelo operador (`Pendente` ou `Cancelado`) e atualizado pelo sistema (`Processando`, `Enviado`, `Erro`).
   - `Ultima Mensagem Enviada`: preenchida pelo sistema após envio de cada etapa.
   - `Ultima Mensagem Recebida`: preservada e nunca preenchida sem fonte confiável.
   - `Último contato`: data/hora de controle operacional.

3. **`Listas`**:
   - Fonte para validação de dados (dropdowns e regras da planilha).

---

## 🛠️ Configuração do Ambiente (`.env`)

Copie o `.env.example` para `.env` e configure:

```dotenv
# SQL Server
serverName=localhost,1433
dataBase=AUTOMATIZACAO
userName=usuario_sql
password=senha_sql
driveConnection=ODBC Driver 17 for SQL Server
schema=automatizacao

# Google Sheets
GOOGLE_SHEETS_SPREADSHEET_ID=identificador-da-planilha
GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE=C:\caminho-protegido\service-account.json
GOOGLE_SHEETS_MENSAGENS_TAB=Mensagem
GOOGLE_SHEETS_CONTROLE_TAB=Controle

# Diretorio seguro para arquivos anexos
ANEXOS_BASE_DIR=C:\Repositorios\automatizacaoMsg\anexos

# Modo de simulacao e canal (por padrao true para seguranca)
WHATSAPP_DRY_RUN=true
WHATSAPP_CHANNEL=desktop
REQUIRE_EXPLICIT_OPT_IN=true
```

---

## 📦 Migrações do Banco de Dados

Para aplicar as migrações não-destrutivas e idempotentes:

```powershell
python .\migrate.py
```

O script aplica as evoluções sem `DROP` ou `TRUNCATE`, preservando histórico e identificadores.

---

## 🧪 Testes Automatizados

Para rodar a suíte completa de testes unitários com mocks:

```powershell
python -m unittest discover -s tests -v
```

---

## ⚙️ Execução

### 1. Verificação da Planilha Google Sheets
```powershell
python .\check_google_sheets.py
```

### 2. Execução Única do Ciclo Completo (Sincronização + Worker)
```powershell
python .\scheduler.py --once
```

### 3. Execução Recorrente (A cada 15 minutos com Lock de Processo)
```powershell
python .\scheduler.py
```

### 4. Worker Legado Compatível
```powershell
python .\sendinfos.py
```
*(Executa em modo `dry-run` por padrão caso `WHATSAPP_DRY_RUN=true`)*.
