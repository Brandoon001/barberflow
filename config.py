import os
from datetime import timedelta
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"


def _bool_env(nome, padrao=False):
    valor = os.environ.get(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in {"1", "true", "sim", "yes", "on"}


class Config:
    ENV = os.environ.get("FLASK_ENV", "development")
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-apenas-nao-use-em-producao"
    DATABASE_PATH = os.environ.get("DATABASE_PATH") or str(
        INSTANCE_DIR / "barbearia.db"
    )

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool_env("SESSION_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    ADMIN_SESSAO_MINUTOS = int(os.environ.get("ADMIN_SESSAO_MINUTOS", "60"))
    MAX_CONTENT_LENGTH = int(
        os.environ.get("MAX_CONTENT_LENGTH", str(2 * 1024 * 1024))
    )
    TRUST_PROXY_HEADERS = _bool_env("TRUST_PROXY_HEADERS", False)

    WTF_CSRF_TIME_LIMIT = None
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_ENABLED = True
    RATELIMIT_HEADERS_ENABLED = True

    CONSENTIMENTO_VERSAO = os.environ.get("CONSENTIMENTO_VERSAO", "2026-10")

    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI = os.environ.get(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:5000/auth/google/callback",
    )
    GOOGLE_DISCOVERY_URL = (
        "https://accounts.google.com/.well-known/openid-configuration"
    )

    MARCA = {
        "nome": os.environ.get("MARCA_NOME", "BarberFlow"),
        "slogan": os.environ.get(
            "MARCA_SLOGAN", "Seu próximo corte começa aqui."
        ),
        "telefone": os.environ.get("MARCA_TELEFONE", ""),
        "whatsapp": os.environ.get("MARCA_WHATSAPP", ""),
        "endereco": os.environ.get("MARCA_ENDERECO", ""),
        "instagram": os.environ.get("MARCA_INSTAGRAM", ""),
    }
    TEMA = os.environ.get("TEMA", "urbano")

    AGENDAMENTO_INTERVALO_MINUTOS = int(
        os.environ.get("AGENDAMENTO_INTERVALO_MINUTOS", "30")
    )
    AGENDAMENTO_DIAS_FUTUROS = int(
        os.environ.get("AGENDAMENTO_DIAS_FUTUROS", "60")
    )
    CANCELAMENTO_MINUTOS_ANTECEDENCIA = int(
        os.environ.get("CANCELAMENTO_MINUTOS_ANTECEDENCIA", "30")
    )
    AGENDAMENTO_CONFIRMACAO_AUTOMATICA = _bool_env(
        "AGENDAMENTO_CONFIRMACAO_AUTOMATICA", False
    )
    TIMEZONE = os.environ.get("TIMEZONE", "America/Sao_Paulo")


class DevelopmentConfig(Config):
    ENV = "development"


class TestingConfig(Config):
    ENV = "testing"
    TESTING = True
    SECRET_KEY = "teste-segredo"
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    DATABASE_PATH = str(INSTANCE_DIR / "teste.db")
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    ENV = "production"
    SESSION_COOKIE_SECURE = _bool_env("SESSION_COOKIE_SECURE", True)
    TRUST_PROXY_HEADERS = _bool_env("TRUST_PROXY_HEADERS", True)
    PREFERRED_URL_SCHEME = "https"


def obter_config(nome=None):
    nome = (nome or os.environ.get("FLASK_ENV", "development")).lower()
    configuracoes = {
        "development": DevelopmentConfig,
        "testing": TestingConfig,
        "production": ProductionConfig,
    }
    if nome not in configuracoes:
        raise ValueError(
            f"FLASK_ENV inválido: {nome!r}. "
            "Use development, testing ou production."
        )
    return configuracoes[nome]
