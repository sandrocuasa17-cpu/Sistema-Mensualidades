# -*- coding: utf-8 -*-
"""
Configuración Centralizada del Sistema
✅ COMPATIBLE CON RENDER (PostgreSQL + SQLite local)
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno desde .env (en local)
load_dotenv()

# Directorio base de la aplicación
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
    # ✅ FIX: Manejo correcto de DATABASE_URL de Render
    _db_url = os.environ.get("DATABASE_URL")
    
    if _db_url:
        # Render usa postgres://, pero SQLAlchemy necesita postgresql://
        if _db_url.startswith("postgres://"):
            _db_url = _db_url.replace("postgres://", "postgresql://", 1)
        SQLALCHEMY_DATABASE_URI = _db_url
    else:
        # Desarrollo local: SQLite
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(INSTANCE_DIR / 'database.db').as_posix()}"

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False

    # === DETECCIÓN DE ENTORNO ===
    @staticmethod
    def is_production():
        """Detecta si estamos en producción (Render)"""
        return os.environ.get("DATABASE_URL") is not None
    
    @staticmethod
    def is_sqlite():
        """Detecta si la base de datos es SQLite"""
        db_uri = Config.SQLALCHEMY_DATABASE_URI
        return db_uri.startswith("sqlite://")

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
    PERMANENT_SESSION_LIFETIME = 3600

    # === CONFIGURACIÓN DE UPLOADS ===
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

    # === BACKUP DE BASE DE DATOS ===
    MAX_BACKUPS = 10
    # ✅ NUEVO: Deshabilitar backups en producción (solo funciona con SQLite)
    ENABLE_DATABASE_BACKUPS = not is_production.__func__()

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
        """Inicializar configuraciones adicionales"""
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
    SQLALCHEMY_ECHO = False

    @property
    def SECRET_KEY(self):
        secret = os.environ.get("SECRET_KEY")
        if not secret:
            raise ValueError("❌ SECRET_KEY debe estar configurada en producción!")
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
        # Si existe DATABASE_URL, asumir producción
        if os.environ.get("DATABASE_URL"):
            env = "production"
        else:
            env = os.environ.get("FLASK_ENV", "development")
    
    return config.get(env, config["default"])
