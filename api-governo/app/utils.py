import secrets
import string
from datetime import datetime


def gerar_protocolo(prefixo):
    """Gera um protocolo de identificação governamental."""

    agora = datetime.now().strftime("%Y%m%d%H%M%S")

    caracteres = string.ascii_uppercase + string.digits

    sufixo = "".join(
        secrets.choice(caracteres)
        for _ in range(12)
    )

    return f"{prefixo}-{agora}-{sufixo}"