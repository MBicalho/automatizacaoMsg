# Manual Operacional - Automatização de Disparos WhatsApp (Multi-Conta)

Este guia contém todos os comandos, rotinas e procedimentos para operação, manutenção e solução de problemas da automação.

---

## 🚀 1. Comandos Principais do Dia a Dia

Todos os comandos devem ser executados no terminal na raiz do projeto (`c:\Repositorios\automatizacaoMsg`):

### A) Rodar o Agendador Contínuo (Modo Produção)
Executa um ciclo imediatamente e continua rodando automaticamente a cada 15 minutos:
```powershell
python scheduler.py
```
> **Nota:** Esse processo possui trava contra concorrência (*ProcessLock*). Se você tentar abrir dois sem querer, o segundo será ignorado com segurança.

### B) Rodar um Ciclo Único Imediato (Sob Demanda)
Executa a sincronização, dispara as mensagens pendentes, coleta respostas dos leads e encerra em seguida:
```powershell
python scheduler.py --once
```

### C) Resetar o Banco de Dados (Limpeza de Testes)
Limpa todas as filas e logs do SQL Server, reinicia os contadores de ID em 0 e recarrega as mensagens da planilha:
```powershell
python reset_db.py
```

### D) Executar os Testes Automatizados
Valida se todas as regras e canais do sistema estão funcionando perfeitamente (41 testes unitários):
```powershell
python -m unittest discover tests
```

---

## 📱 2. Gerenciamento das Contas de WhatsApp

A automação opera com duas contas independentes em simultâneo através da **Evolution API (Docker)**:

| Conta no Docker | Responsável / Mapeamento na Planilha | Função |
| :--- | :--- | :--- |
| **`conta_1`** | **`Lead Pacifico`** | Envia as mensagens de leads do Pacífico |
| **`conta_2`** | **`Lead Daniela`** | Envia as mensagens de leads da Daniela |

### Como conectar ou trocar de celular:
1. Dê dois cliques no arquivo **[`qrcodes.html`](file:///c:/Repositorios/automatizacaoMsg/qrcodes.html)** para abrir no navegador.
2. A página atualiza o status de conexão automaticamente a cada 3 segundos:
   - **Verde ("Conectado"):** O WhatsApp está ativo e pronto para envio.
   - **Amarelo ("Aguardando Leitura"):** Exibe o QR Code para você escanear.
3. Para trocar de aparelho:
   - Clique no botão vermelho **`🔌 Desconectar para Trocar`** no card da conta desejada.
   - Abra o novo WhatsApp no celular em **Aparelhos Conectados** > **Conectar um aparelho**.
   - Aponte a câmera e leia o novo QR Code.

> **Importante:** A página `qrcodes.html` e o app do *WhatsApp Desktop* **NÃO** precisam ficar abertos no dia a dia. Uma vez conectadas, as contas permanecem salvas no Docker.

---

## 📊 3. Regras da Planilha Google Sheets (Aba `Controle`)

### A) Coluna `Origem` (Roteamento Automático)
Define por qual WhatsApp a mensagem será disparada:
- Digite **`Lead Pacifico`** (ou `Pacifico`, `Conta 1`) para disparar pela **Conta 1**.
- Digite **`Lead Daniela`** (ou `Daniela`, `Conta 2`) para disparar pela **Conta 2**.

### B) Coluna `Envio` (Controle de Fila)
- **`Pendente`**: O robô lê a linha e enfileira para envio no próximo ciclo.
- **`Processando`**: Marcado automaticamente enquanto os envios estão ocorrendo.
- **`Enviado`**: Marcado automaticamente assim que todos os passos foram concluídos.
- **`Cancelado`**: Se você digitar *Cancelado*, o robô cancela os passos pendentes no banco.

### C) Colunas de Mensagens
- **`Ultima Mensagem Enviada`**: Preenchida automaticamente pelo robô após o envio com o código do template e data/hora (ex: `analise (18/10/2026 20:15)`).
- **`Ultima Mensagem Recebida`**: Se o lead responder pelo WhatsApp, o robô captura as respostas recebidas após o nosso último envio e grava na planilha:
  - Formato: `Msg 1 | Msg 2 | Msg 3 (18/10/2026 20:30)`
  - Mídias enviadas pelo lead são identificadas como `[Áudio]`, `[Imagem]`, `[Documento]`.
- **`Último contato`**: Preenchida automaticamente com a data/hora do contato mais recente.

---

## 🛠️ 4. Solução de Problemas Comuns (Troubleshooting)

### Problema 1: Erro de Timeout no SQL Server `[Provedor de Memória Compartilhada: Erro 258]`
**Causa:** O serviço do SQL Server no Windows congelou após suspensão ou reinicialização da máquina.  
**Solução rápida:**
1. Pressione `Win + R`, digite `services.msc` e pressione **Enter**.
2. Procure por **`SQL Server (SQLEXPRESS)`**.
3. Clique com o botão direito e escolha **Reiniciar**.
*(Ou abra o PowerShell como Administrador e rode: `net stop MSSQL$SQLEXPRESS` e depois `net start MSSQL$SQLEXPRESS`)*.

---

### Problema 2: Celular dá erro ao escanear QR Code (*"Não foi possível conectar. Verifique sua conexão..."*)
**Causa:** O QR Code acumulou muitas tentativas ou expirou, ou o celular atingiu o limite de 4 aparelhos conectados.  
**Solução:**
1. No WhatsApp do celular, vá em **Aparelhos Conectados** e desconecte qualquer sessão antiga que não esteja usando.
2. No terminal, execute o comando para recriar a instância do zero com contador de QR Code zerado:
   ```powershell
   python -c "import urllib.request, json; h={'apikey':'minha_chave_secreta_123','Content-Type':'application/json'}; urllib.request.urlopen(urllib.request.Request('http://localhost:8080/instance/delete/conta_1', headers=h, method='DELETE')); urllib.request.urlopen(urllib.request.Request('http://localhost:8080/instance/create', data=json.dumps({'instanceName':'conta_1','integration':'WHATSAPP-BAILEYS','qrcode':True}).encode(), headers=h)); print('Conta 1 recriada com sucesso!')"
   ```
3. Abra a página `qrcodes.html` e escaneie o novo QR Code.

---

### Problema 3: O Docker ou a Evolution API não estão respondendo
**Causa:** O Docker Desktop foi fechado ou reiniciado.  
**Solução:**
1. Abra o **Docker Desktop** e aguarde a luz verde no canto inferior esquerdo (*Engine running*).
2. Se os containers não subirem sozinhos, abra o terminal e rode:
   ```powershell
   cd evolution
   docker compose up -d
   cd ..
   ```
3. Verifique se os 3 containers estão ativos:
   ```powershell
   docker ps
   ```
   *(Devem aparecer `evolution_api`, `evolution_postgres` e `evolution_redis`).*

---

## 📋 5. Resumo Rápido de Arquivos e Pastas

- **[`scheduler.py`](file:///c:/Repositorios/automatizacaoMsg/scheduler.py)**: Orquestrador principal (executa a cada 15 min ou `--once`).
- **[`reset_db.py`](file:///c:/Repositorios/automatizacaoMsg/reset_db.py)**: Script para zerar o banco de dados e recarregar mensagens.
- **[`qrcodes.html`](file:///c:/Repositorios/automatizacaoMsg/qrcodes.html)**: Painel visual para conectar ou trocar números de WhatsApp.
- **[`evolution/docker-compose.yml`](file:///c:/Repositorios/automatizacaoMsg/evolution/docker-compose.yml)**: Configuração dos containers da Evolution API.
- **[`.env`](file:///c:/Repositorios/automatizacaoMsg/.env)**: Configurações de conexão (SQL Server, Google Sheets e Evolution API).
