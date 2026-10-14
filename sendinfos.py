from pathlib import Path
import functions
import scripts
from channels import DesktopWhatsAppChannel, get_channel
from phone_utils import mask_phone

if __name__ == '__main__':
    # Worker legado compativel, protegido por canal com dry-run por padrao
    channel = get_channel()
    print(f"Iniciando worker legado no canal: {type(channel).__name__}")

    if isinstance(channel, DesktopWhatsAppChannel):
        functions.openWppDektop()

    dba = functions.dataBase()
    query = scripts.querys()

    for contato in dba.select(query=query.consultaDadosCliente()).itertuples():
        masked_tel = mask_phone(getattr(contato, 'TELEFONE', None))
        try:
            dba.iniciarEnvio(contato.ID_CONTROLE_ENVIO)
            texto_msg = contato.DESCRICAO_MENSAGEM if not functions.pd.isna(contato.DESCRICAO_MENSAGEM) else ""

            if contato.ID_TIPO_ENVIO == 1:
                if not texto_msg:
                    raise ValueError('Envio de mensagem sem texto cadastrado.')
                res = channel.send_text(phone=str(contato.TELEFONE), text=texto_msg)
            elif contato.ID_TIPO_ENVIO in (2, 3):
                if not contato.CAMINHO_ARQUIVO or functions.pd.isna(contato.CAMINHO_ARQUIVO):
                    raise ValueError('Envio de arquivo sem caminho cadastrado.')
                res = channel.send_file(
                    phone=str(contato.TELEFONE),
                    file_path=Path(contato.CAMINHO_ARQUIVO),
                    caption=texto_msg,
                    is_image=(contato.ID_TIPO_ENVIO == 3),
                )
            else:
                raise ValueError(f'Tipo de envio invalido: {contato.ID_TIPO_ENVIO}.')

            if res.success:
                dba.concluirEnvio(contato.ID_CONTROLE_ENVIO)
                print(f"Envio {contato.ID_CONTROLE_ENVIO} concluido para {masked_tel}: {res.detail}")
            else:
                dba.registrarErroEnvio(contato.ID_CONTROLE_ENVIO, res.detail)
                print(f"Envio {contato.ID_CONTROLE_ENVIO} falhou para {masked_tel}: {res.detail}")
        except Exception as ex:
            dba.registrarErroEnvio(contato.ID_CONTROLE_ENVIO, ex)
            print(f'Envio {contato.ID_CONTROLE_ENVIO} falhou para {masked_tel}: {ex}')
