
import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    # Configuracoes do banco de dados
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", 3306))
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "clinica_veterinaria")

    # Chave obrigatoria para assinatura dos tokens JWT
    SECRET_KEY = os.getenv("SECRET_KEY", "").strip()

    if (
        len(SECRET_KEY) < 32
        or SECRET_KEY == "dev-secret-nao-use-em-producao"
    ):
        raise RuntimeError(
            "SECRET_KEY ausente ou insegura. "
            "Configure uma chave secreta forte no arquivo .env."
        )

    # Configuracoes da integracao governamental
    GOVERNO_URL = os.getenv(
        "GOVERNO_URL",
        "http://localhost:5001"
    )

    GOVERNO_API_KEY = os.getenv("GOVERNO_API_KEY", "")
