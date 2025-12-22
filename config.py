# -*- coding: utf-8 -*-
"""
Configuración Centralizada del Sistema
Todas las configuraciones deben estar aquí
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno desde .env (en local)
load_dotenv()

# Directorio base de la aplicación (carpeta donde está config.py)
BASE_DIR = Path(__file__).parent.resolve()


def _ensure_dir(path: Path) -> Path:
    """Crea un directorio si no existe y retorna el mismo Path."""
    path.mkdir(parents=True, exist_ok=True)
    return path


class Config:
    """Configuración base del sistema"""

    # === SEGURIDAD ===
    SECRET_KEY = os.environ.get("SECRET_KEY") or os.urandom(24).hex()

    # === RUTAS IMPORTANTES ===
    INSTANCE_DIR = _ensure_dir(BASE_DIR / "instance")
    UPLOAD_FOLDER = _ensure_dir(BASE_DIR / "uploads")
    BACKUP_DIR = _ensure_dir(BASE_DIR / "backups")
    LOG_DIR = _ensure_dir(BASE_DIR / "logs")
    LOG_FILE = LOG_DIR / "app.log"

    # === BASE DE DATOS ===
    # Producción (Render): si existe DATABASE_URL úsalo (normalmente Postgres).
    # Si no existe: usa SQLite dentro de instance/database.db
    _default_sqlite = f"sqlite:///{(INSTANCE_DIR / 'database.db').as_posix()}"
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", _default_sqlite)

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False  # True para ver SQL en logs (debug)

    # === CORREO ELECTRÓNICO ===
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() in ["true", "on", "1"]
    MAIL_USE_SSL = os.environ.get("MAIL_USE_SSL", "false").lower() in ["true", "on", "1"]
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "noreply@sistema.com")

    # === CONFIGURACIÓN DE SESIÓN ===
    SESSION_TYPE = "filesystem"
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hora

    # === CONFIGURACIÓN DE UPLOADS ===
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max

    # === BACKUP DE BASE DE DATOS ===
    MAX_BACKUPS = 10

    # === PAGINACIÓN ===
    ITEMS_PER_PAGE = 20

    # === TIMEZONE ===
    TIMEZONE = "America/Guayaquil"

    # === DEMO ===
    DEMO_DURATION_MINUTES = 30

    # === FEATURES FLAGS ===
    ENABLE_EMAIL_NOTIFICATIONS = True
    ENABLE_AUTOMATIC_REMINDERS = True
    ENABLE_API = True

    # === LOGGING ===
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

    @staticmethod
    def init_app(app):
        """Inicializar configuraciones adicionales (carpetas, etc.)"""
        _ensure_dir(Config.INSTANCE_DIR)
        _ensure_dir(Config.UPLOAD_FOLDER)
        _ensure_dir(Config.BACKUP_DIR)
        _ensure_dir(Config.LOG_DIR)


class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False
    SQLALCHEMY_ECHO = True


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False

    @property
    def SECRET_KEY(self):
        secret = os.environ.get("SECRET_KEY")
        if not secret:
            raise ValueError("SECRET_KEY must be set in production!")
        return secret


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}


def get_config(env=None):
    """Obtiene la configuración según el entorno"""
    if env is None:
        env = os.environ.get("FLASK_ENV", "development")
    return config.get(env, config["default"])
