import os
import re
import time
import urllib
import webbrowser
import dotenv
import pandas as pd
import pyautogui
import pyperclip
from pynput import keyboard, mouse
import sqlalchemy as sa

dotenv.load_dotenv()

mouse_controller = mouse.Controller()
mouse_button = mouse.Button

keyboard_controller = keyboard.Controller()
keyboard_key = keyboard.Key

def openWppDektop():
    keyboard_controller.press(keyboard_key.cmd)
    keyboard_controller.press('1')
    keyboard_controller.release('1')
    keyboard_controller.release(keyboard_key.cmd)
    time.sleep(1)

class contatoWpp():
    def __init__(self, dadosContato):
        self.nome = dadosContato.NOME
        self.telefone = dadosContato.TELEFONE
        self.tipo_envio = dadosContato.ID_TIPO_ENVIO
        self.descricao_tipo_envio = dadosContato.DESCRICAO_TIPO_ENVIO
        self.caminho_arquivo = dadosContato.CAMINHO_ARQUIVO
        self.mensagem = dadosContato.DESCRICAO_MENSAGEM
        self.flag_img = True if dadosContato.ID_TIPO_ENVIO == 3 and dadosContato.CAMINHO_ARQUIVO else False

    def eventClickSearch(self):
        # botao_pesquisa_desktop = pyautogui.locateCenterOnScreen('botao_pesquisa_desktop.png')
        # pyautogui.click(botao_pesquisa_desktop[0], botao_pesquisa_desktop[1], interval=3)

        keyboard_controller.press(keyboard_key.ctrl)
        keyboard_controller.press('f')
        keyboard_controller.release('f')
        keyboard_controller.release(keyboard_key.ctrl)

        self.cleanSearh()

    def cleanSearh(self):
        keyboard_controller.press(keyboard_key.ctrl)
        keyboard_controller.press('a')
        keyboard_controller.release('a')
        keyboard_controller.release(keyboard_key.ctrl)

        keyboard_controller.press(keyboard_key.delete)
        keyboard_controller.release(keyboard_key.delete)

    def eventSelectUser(self):
        telefone = re.sub(r'\D', '', str(self.telefone))

        if len(telefone) in (10, 11) and not telefone.startswith('55'):
            telefone = f'55{telefone}'

        if not telefone.startswith('55') or len(telefone) not in (12, 13):
            raise ValueError(
                'Telefone invalido. Cadastre no formato internacional, por exemplo: 5511999999999.'
            )

        # Se houver mensagem de texto simples, passa na URI para o WhatsApp preencher automaticamente
        uri = f'whatsapp://send?phone={telefone}'

        try:
            os.startfile(uri)
        except OSError:
            webbrowser.open(f'https://wa.me/{telefone}')

        # Aguarda o WhatsApp Desktop carregar a conversa aberta pelo link
        time.sleep(5.0)

        # Garante o foco na janela do WhatsApp Desktop
        try:
            import subprocess
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", "(New-Object -ComObject WScript.Shell).AppActivate('WhatsApp')"],
                capture_output=True,
                timeout=3
            )
        except Exception:
            pass

        time.sleep(0.5)

    def eventClickFile(self):
        # Desacoplado de reconhecimento visual de tela para evitar erros de
        # "screen grab failed", escala de DPI e mudancas de tema do WhatsApp Desktop.
        pass

    def eventSendMsg(self):
        time.sleep(0.5)

        # 1. Localiza a janela do WhatsApp Desktop e traz para primeiro plano
        whatsapp_win = None
        try:
            import pygetwindow as gw
            candidates = gw.getWindowsWithTitle('WhatsApp')
            if not candidates:
                candidates = [w for w in gw.getAllWindows() if 'whatsapp' in w.title.lower()]
            if candidates:
                whatsapp_win = candidates[0]
                if whatsapp_win.isMinimized:
                    whatsapp_win.restore()
                whatsapp_win.activate()
                time.sleep(0.5)
        except Exception:
            pass

        # 2. Se localizou a janela, clica dentro da caixa de texto para forçar o foco do cursor
        if whatsapp_win and whatsapp_win.width > 200 and whatsapp_win.height > 200:
            try:
                input_x = whatsapp_win.left + int(whatsapp_win.width * 0.6)
                input_y = whatsapp_win.top + whatsapp_win.height - 45
                pyautogui.click(input_x, input_y)
                time.sleep(0.4)
            except Exception:
                pass
        else:
            # Fallback para focar via WScript.Shell
            try:
                import subprocess
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", "(New-Object -ComObject WScript.Shell).AppActivate('WhatsApp')"],
                    capture_output=True,
                    timeout=3
                )
                time.sleep(0.5)
            except Exception:
                pass

        # 3. Copia a mensagem para a área de transferência e cola via Ctrl+V no campo focado
        if getattr(self, 'mensagem', None):
            pyperclip.copy(str(self.mensagem))
            time.sleep(0.3)
            keyboard_controller.press(keyboard_key.ctrl)
            keyboard_controller.press('v')
            keyboard_controller.release('v')
            keyboard_controller.release(keyboard_key.ctrl)
            time.sleep(0.5)

        # 4. Dispara o envio com Enter (pyautogui e pynput)
        try:
            pyautogui.press('enter')
        except Exception:
            pass

        time.sleep(0.3)
        keyboard_controller.press(keyboard_key.enter)
        keyboard_controller.release(keyboard_key.enter)
        time.sleep(1.5)

    def eventSendFile(self):
        # Utiliza a area de transferencia nativa do Windows (CF_HDROP) para
        # colar o arquivo diretamente na conversa aberta do WhatsApp Desktop.
        import subprocess

        abs_path = os.path.abspath(self.caminho_arquivo)
        if not os.path.isfile(abs_path):
            raise FileNotFoundError(f"Arquivo nao encontrado para envio: {abs_path}")

        cmd = f"Set-Clipboard -Path '{abs_path}'"
        res = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, timeout=10)
        if res.returncode != 0:
            raise RuntimeError(f"Falha ao copiar arquivo para clipboard: {res.stderr}")

        time.sleep(0.5)

        # Cola o arquivo no WhatsApp Desktop
        keyboard_controller.press(keyboard_key.ctrl)
        keyboard_controller.press('v')
        keyboard_controller.release('v')
        keyboard_controller.release(keyboard_key.ctrl)

        # Aguarda a tela de confirmacao e legenda do WhatsApp Desktop abrir
        time.sleep(2)

        # Se houver legenda, cola no campo que ja vem focado
        if self.mensagem:
            pyperclip.copy(self.mensagem)
            time.sleep(0.3)
            keyboard_controller.press(keyboard_key.ctrl)
            keyboard_controller.press('v')
            keyboard_controller.release('v')
            keyboard_controller.release(keyboard_key.ctrl)
            time.sleep(0.5)

        # Confirma e envia o anexo
        keyboard_controller.press(keyboard_key.enter)
        keyboard_controller.release(keyboard_key.enter)

        time.sleep(1.5)

class dataBase():
    def __init__(self):
        self.serverName = os.getenv('serverName')
        self.dataBase = os.getenv('dataBase')
        self.userName = os.getenv('userName')
        self.password = os.getenv('password')
        self.drive = os.getenv('driveConnection')
        self.schema = os.getenv('schema', 'automatizacao')
        self.encrypt = os.getenv('encrypt', 'no')
        self.trustServerCertificate = os.getenv('trustServerCertificate', 'yes')

    def connectDataBase(self):
        """
        Conecta ao SQL Server usando autenticacao configurada (SQL Auth ou Windows Auth).
        Detecta automaticamente contas Windows ou configuracao de autenticacao integrada.
        """
        driver_str = self.drive.strip("{}") if self.drive else "ODBC Driver 17 for SQL Server"
        driver = f"{{{driver_str}}}"
        win_user = os.getenv("USERNAME", "")

        trusted_env = os.getenv("trustedConnection", "").strip().lower()
        if trusted_env in ("yes", "true", "1"):
            use_trusted = True
        elif trusted_env in ("no", "false", "0"):
            use_trusted = False
        else:
            use_trusted = (
                not (self.userName and self.password)
                or (bool(self.userName) and self.userName.lower() == win_user.lower())
            )

        server = self.serverName

        if use_trusted:
            connection_string = (
                f"Driver={driver};"
                f"Server={server};"
                f"Database={self.dataBase};"
                f"Trusted_Connection=yes;"
                f"Encrypt={self.encrypt};"
                f"TrustServerCertificate={self.trustServerCertificate};"
            )
        else:
            connection_string = (
                f"Driver={driver};"
                f"Server={server};"
                f"Database={self.dataBase};"
                f"UID={self.userName};"
                f"PWD={self.password};"
                f"Trusted_Connection=no;"
                f"Encrypt={self.encrypt};"
                f"TrustServerCertificate={self.trustServerCertificate};"
            )

        connection_url = sa.engine.URL.create("mssql+pyodbc", query={"odbc_connect": connection_string})
        return sa.create_engine(connection_url, fast_executemany=True, poolclass=sa.pool.NullPool)

    def select(self, query=str):
        try:
            return pd.DataFrame(pd.read_sql(sql=query, con=self.connectDataBase()))
        except Exception as ex:
            raise ConnectionError(
                'Nao foi possivel conectar ao SQL Server. Verifique servidor, '
                'credenciais, servico SQL Server e configuracao de TLS.'
            ) from ex

    def iniciarEnvio(self, id_controle_envio):
        self._atualizarStatusEnvio(id_controle_envio, 'PROCESSANDO')

    def concluirEnvio(self, id_controle_envio):
        self._atualizarStatusEnvio(id_controle_envio, 'ENVIADO')

    def registrarErroEnvio(self, id_controle_envio, erro):
        self._atualizarStatusEnvio(id_controle_envio, 'ERRO', str(erro)[:2000])

    def _atualizarStatusEnvio(self, id_controle_envio, status, erro=None):
        sql = sa.text(f"""
            UPDATE {self.dataBase}.{self.schema}.CONTROLE_ENVIO_WPP
            SET STATUS = :status,
                TENTATIVAS = CASE WHEN :status = 'PROCESSANDO' THEN TENTATIVAS + 1 ELSE TENTATIVAS END,
                DATA_INICIO = CASE WHEN :status = 'PROCESSANDO' THEN SYSDATETIME() ELSE DATA_INICIO END,
                DATA_ENVIO = CASE WHEN :status = 'ENVIADO' THEN SYSDATETIME() ELSE DATA_ENVIO END,
                MENSAGEM_ERRO = CASE WHEN :status = 'ERRO' THEN :erro ELSE NULL END
            WHERE ID_CONTROLE_ENVIO = :id_controle_envio
        """)

        with self.connectDataBase().begin() as connection:
            connection.execute(sql, {
                'id_controle_envio': int(id_controle_envio),
                'status': status,
                'erro': erro,
            })