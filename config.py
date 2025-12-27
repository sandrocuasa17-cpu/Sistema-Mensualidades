# -*- coding: utf-8 -*-
"""
Configuración Centralizada del Sistema
✅ Optimizada para Render con Disco Persistente (/var/data)
✅ Compatible con local sin disco persistente
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno desde .env (en local)
load_dotenv()

# Directorio base de la aplicación (carpeta donde está este config.py)
BASE_DIR = Path(__file__).parent.resolve()


def _ensure_dir(path: Path) -> Path:
    """Crea un directorio si no existe y retorna el mismo Path."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def _get_persist_root() -> Path:
    """
    Retorna la raíz persistente.
    - En Render con Disk: RENDER_DISK_PATH=/var/data
    - En local (sin env): usa BASE_DIR
    """
    disk_path = os.environ.get("RENDER_DISK_PATH", "").strip()
    if disk_path:
        return Path(disk_path)
    return BASE_DIR


class Config:
    """Configuración base del sistema"""

    # =========================
    # SEGURIDAD
    # =========================
    SECRET_KEY = os.environ.get("SECRET_KEY") or os.urandom(24).hex()

    # =========================
    # RUTAS PERSISTENTES
    # =========================
    PERSIST_ROOT = _get_persist_root()

    # Mantener todo lo importante dentro del root persistente
    INSTANCE_DIR = _ensure_dir(PERSIST_ROOT / "instance")
    UPLOAD_FOLDER = _ensure_dir(PERSIST_ROOT / "uploads")
    BACKUP_DIR = _ensure_dir(PERSIST_ROOT / "backups")
    LOG_DIR = _ensure_dir(PERSIST_ROOT / "logs")
    LOG_FILE = LOG_DIR / "app.log"

    # =========================
    # BASE DE DATOS
    # =========================
    # ✅ Si existe DATABASE_URL: usa Postgres (o lo que sea)
    # ✅ Si no existe: usa SQLite dentro del disco persistente
    _default_sqlite = f"sqlite:///{(INSTANCE_DIR / 'database.db').as_posix()}"
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", _default_sqlite)

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False  # True para ver SQL en logs (debug)

    # =========================
    # CORREO ELECTRÓNICO
    # =========================
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() in ["true", "on", "1", "yes"]
    MAIL_USE_SSL = os.environ.get("MAIL_USE_SSL", "false").lower() in ["true", "on", "1", "yes"]
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "noreply@sistema.com")

    # =========================
    # SESIÓN / TIMEOUT
    # =========================
    SESSION_TYPE = "filesystem"
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hora

    # =========================
    # UPLOADS
    # =========================
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf", "xlsx"}

    # =========================
    # BACKUPS
    # =========================
    MAX_BACKUPS = 10

    # =========================
    # PAGINACIÓN
    # =========================
    ITEMS_PER_PAGE = 20

    # =========================
    # TIMEZONE
    # =========================
    TIMEZONE = "America/Guayaquil"

    # =========================
    # DEMO / FEATURES
    # =========================
    DEMO_DURATION_MINUTES = 30
    ENABLE_EMAIL_NOTIFICATIONS = True
    ENABLE_AUTOMATIC_REMINDERS = True
    ENABLE_API = True

    # =========================
    # LOGGING
    # =========================
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

    @staticmethod
    def init_app(app):
        """
        Inicializa carpetas y deja trazas útiles.
        (No rompe si se ejecuta en local o en Render)
        """
        _ensure_dir(Config.PERSIST_ROOT)
        _ensure_dir(Config.INSTANCE_DIR)
        _ensure_dir(Config.UPLOAD_FOLDER)
        _ensure_dir(Config.BACKUP_DIR)
        _ensure_dir(Config.LOG_DIR)

        # Logs útiles para verificar en Render
        try:
            app.logger.info(f"🗂️ PERSIST_ROOT: {Config.PERSIST_ROOT}")
            app.logger.info(f"🗃️ INSTANCE_DIR: {Config.INSTANCE_DIR}")
            app.logger.info(f"🧩 DB_URI: {Config.SQLALCHEMY_DATABASE_URI}")
        except Exception:
            pass


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
