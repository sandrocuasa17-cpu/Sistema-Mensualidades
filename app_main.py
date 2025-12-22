# -*- coding: utf-8 -*-
"""
Sistema de Gestión de Mensualidades
Versión 3.0 - Con Autenticación y Cursos
"""

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime, timedelta
from functools import wraps
import logging
from logging.handlers import RotatingFileHandler
import os

# Importar módulos del sistema
from config import get_config
from auth import AuthManager, requiere_autenticacion, cambiar_password
from models_extended import db, Cliente, Curso, Plan, Pago, Configuracion
from excel_reports import excel_generator
from email_service import mail, enviar_confirmacion_pago, enviar_aviso_vencimiento
from license_manager import license_manager
from backup_manager import BackupManager

# Inicializar Flask
app = Flask(__name__)

# Cargar configuración
env = os.environ.get('FLASK_ENV', 'development')
app.config.from_object(get_config(env))

# Inicializar extensiones
db.init_app(app)
migrate = Migrate(app, db)
mail.init_app(app)

# Inicializar BackupManager
db_uri = app.config['SQLALCHEMY_DATABASE_URI']
if 'sqlite:///' in db_uri:
    db_path_relative = db_uri.replace('sqlite:///', '')
    if not db_path_relative.startswith('instance/'):
        db_path = os.path.join('instance', os.path.basename(db_path_relative))
    else:
        db_path = db_path_relative
    backup_manager = BackupManager(app, db_path)
else:
    backup_manager = BackupManager(app, db_path=None)

# Configurar logging
if not app.debug:
    if not os.path.exists('logs'):
        os.mkdir('logs')
    
    file_handler = RotatingFileHandler(
        'logs/sistema.log', 
        maxBytes=10240000,
        backupCount=10
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Sistema iniciado')


# ============================================
# DECORADOR COMBINADO: LICENCIA + AUTENTICACIÓN
# ============================================

def requiere_licencia_y_auth(f):
    """Decorador que requiere licencia válida Y autenticación"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Verificar autenticación
        if not AuthManager.esta_autenticado():
            session['next_url'] = request.url
            return redirect(url_for('login'))
        
        # 2. Verificar licencia
        es_demo, mensaje, info = license_manager.verificar_licencia_activa()
        
        if info.get('bloqueado'):
            return redirect(url_for('blockscreen'))
        
        session['es_demo'] = es_demo
        session['licencia_info'] = info
        session['licencia_mensaje'] = mensaje
        
        return f(*args, **kwargs)
    return decorated_function


# ============================================
# RUTAS DE AUTENTICACIÓN
# ============================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Página de inicio de sesión"""
    # Si ya está autenticado, redirigir
    if AuthManager.esta_autenticado():
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        
        # Obtener hash almacenado en BD
        password_hash = Configuracion.obtener('PASSWORD_HASH', AuthManager.DEFAULT_PASSWORD_HASH)
        
        if AuthManager.verificar_password(password, password_hash):
            AuthManager.iniciar_sesion(password)
            app.logger.info('Inicio de sesión exitoso')
            
            # Redirigir a la URL guardada o al dashboard
            next_url = session.pop('next_url', None)
            return redirect(next_url or url_for('index'))
        else:
            app.logger.warning('Intento de inicio de sesión fallido')
            flash('❌ Contraseña incorrecta', 'danger')
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    """Cerrar sesión"""
    AuthManager.cerrar_sesion()
    flash('✅ Sesión cerrada exitosamente', 'success')
    return redirect(url_for('login'))


# ============================================
# RUTAS PRINCIPALES
# ============================================

@app.route('/')
@requiere_licencia_y_auth
def index():
    """Dashboard principal"""
    try:
        # Estadísticas generales
        total_estudiantes = Cliente.query.filter_by(activo=True).count()
        
        estudiantes_activos = Cliente.query.filter_by(activo=True).all()
        estudiantes_morosos = sum(1 for e in estudiantes_activos if e.estado_pago == 'moroso')
        estudiantes_vencidos = sum(1 for e in estudiantes_activos if e.plan_vencido)
        
        # Estudiantes próximos a vencer (0-7 días)
        proximos_vencer = [e for e in estudiantes_activos if e.proximo_a_vencer]
        
        total_cobrado = db.session.query(db.func.sum(Pago.monto)).scalar() or 0
        total_pendiente = sum(e.saldo_pendiente for e in estudiantes_activos)
        
        ultimos_pagos = Pago.query.order_by(Pago.fecha_pago.desc()).limit(5).all()
        
        return render_template('index_extended.html',
                             total_estudiantes=total_estudiantes,
                             estudiantes_morosos=estudiantes_morosos,
                             estudiantes_vencidos=estudiantes_vencidos,
                             proximos_vencer=proximos_vencer,
                             total_cobrado=total_cobrado,
                             total_pendiente=total_pendiente,
                             ultimos_pagos=ultimos_pagos)
    except Exception as e:
        app.logger.error(f'Error en dashboard: {e}')
        flash('Error cargando el dashboard', 'danger')
        return render_template('index_extended.html',
                             total_estudiantes=0,
                             estudiantes_morosos=0,
                             estudiantes_vencidos=0,
                             proximos_vencer=[],
                             total_cobrado=0,
                             total_pendiente=0,
                             ultimos_pagos=[])


@app.route('/blockscreen')
def blockscreen():
    """Pantalla de sistema bloqueado"""
    es_demo, mensaje, info = license_manager.verificar_licencia_activa()
    return render_template('blockscreen.html', mensaje=mensaje, info=info)


# ============================================
# RUTAS DE CURSOS
# ============================================

@app.route('/cursos')
@requiere_licencia_y_auth
def cursos():
    """Lista de cursos"""
    try:
        cursos = Curso.query.order_by(Curso.activo.desc(), Curso.fecha_creacion.desc()).all()
        return render_template('cursos/lista.html', cursos=cursos)
    except Exception as e:
        app.logger.error(f'Error en lista cursos: {e}')
        flash('Error cargando cursos', 'danger')
        return render_template('cursos/lista.html', cursos=[])


@app.route('/cursos/nuevo', methods=['GET', 'POST'])
@requiere_licencia_y_auth
def curso_nuevo():
    """Crear nuevo curso"""
    if request.method == 'POST':
        try:
            precio_mensual = float(request.form.get('precio_mensual', 0))
            precio_inscripcion = float(request.form.get('precio_inscripcion', 0))
            duracion_meses = int(request.form.get('duracion_meses', 12))
            
            if precio_mensual <= 0:
                flash('El precio mensual debe ser mayor a 0', 'danger')
                return redirect(url_for('curso_nuevo'))
            
            curso = Curso(
                nombre=request.form['nombre'].strip(),
                descripcion=request.form.get('descripcion', '').strip() or None,
                precio_mensual=precio_mensual,
                precio_inscripcion=precio_inscripcion,
                duracion_meses=duracion_meses
            )
            
            db.session.add(curso)
            db.session.commit()
            
            app.logger.info(f'Curso creado: {curso.nombre}')
            flash(f'✅ Curso {curso.nombre} creado exitosamente', 'success')
            return redirect(url_for('cursos'))
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Error creando curso: {e}')
            flash('Error al crear el curso', 'danger')
    
    return render_template('cursos/formulario.html', curso=None)


@app.route('/cursos/<int:id>/editar', methods=['GET', 'POST'])
@requiere_licencia_y_auth
def curso_editar(id):
    """Editar un curso"""
    curso = Curso.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            precio_mensual = float(request.form.get('precio_mensual', 0))
            precio_inscripcion = float(request.form.get('precio_inscripcion', 0))
            duracion_meses = int(request.form.get('duracion_meses', 12))
            
            if precio_mensual <= 0:
                flash('El precio mensual debe ser mayor a 0', 'danger')
                return redirect(url_for('curso_editar', id=id))
            
            curso.nombre = request.form['nombre'].strip()
            curso.descripcion = request.form.get('descripcion', '').strip() or None
            curso.precio_mensual = precio_mensual
            curso.precio_inscripcion = precio_inscripcion
            curso.duracion_meses = duracion_meses
            curso.activo = 'activo' in request.form
            
            db.session.commit()
            
            app.logger.info(f'Curso actualizado: {curso.nombre}')
            flash(f'✅ Curso {curso.nombre} actualizado exitosamente', 'success')
            return redirect(url_for('cursos'))
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Error actualizando curso {id}: {e}')
            flash('Error al actualizar el curso', 'danger')
    
    return render_template('cursos/formulario.html', curso=curso)


@app.route('/cursos/<int:id>/eliminar', methods=['POST'])
@requiere_licencia_y_auth
def curso_eliminar(id):
    """Eliminar un curso"""
    try:
        curso = Curso.query.get_or_404(id)
        
        if curso.estudiantes:
            flash('No se puede eliminar un curso con estudiantes asociados', 'danger')
            return redirect(url_for('cursos'))
        
        nombre = curso.nombre
        db.session.delete(curso)
        db.session.commit()
        
        app.logger.info(f'Curso eliminado: {nombre}')
        flash(f'✅ Curso {nombre} eliminado exitosamente', 'success')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error eliminando curso {id}: {e}')
        flash('Error al eliminar el curso', 'danger')
    
    return redirect(url_for('cursos'))


# ============================================
# INICIALIZACIÓN
# ============================================

with app.app_context():
    try:
        db.create_all()
        app.logger.info("✅ Tablas verificadas/creadas")
        
        # Crear contraseña por defecto si no existe
        if not Configuracion.obtener('PASSWORD_HASH'):
            Configuracion.establecer(
                'PASSWORD_HASH', 
                AuthManager.DEFAULT_PASSWORD_HASH,
                'Hash de contraseña del sistema (default: admin123)'
            )
            app.logger.info("🔑 Contraseña por defecto configurada")
            
    except Exception as e:
        app.logger.error(f"❌ Error inicializando BD: {e}")


if __name__ == '__main__':
    import threading
    
    # Configurar host y puerto
    is_production = env == 'production'
    host = '0.0.0.0' if is_production else '127.0.0.1'
    port = int(os.environ.get('PORT', 5000))
    
    app.run(
        debug=not is_production,
        host=host,
        port=port,
        use_reloader=False
    )