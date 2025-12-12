
# -*- coding: utf-8 -*-
"""
Sistema de Gestión de Mensualidades
Versión 2.0 - Corregida y Mejorada
"""

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime, timedelta
from functools import wraps
import logging
from logging.handlers import RotatingFileHandler
import os
from datetime import datetime, timedelta
import sys
from flask import send_file
from werkzeug.utils import secure_filename
from backup_manager import BackupManager
from pathlib import Path

# Importar configuración centralizada
from config import get_config

# Inicializar Flask
app = Flask(__name__)


# Cargar configuración según entorno
env = os.environ.get('FLASK_ENV', 'development')
app.config.from_object(get_config(env))

# Inicializar extensiones
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Inicializar BackupManager con manejo inteligente de PostgreSQL/SQLite
db_uri = app.config['SQLALCHEMY_DATABASE_URI']

if 'sqlite:///' in db_uri:
    # ✅ SQLite: Backups habilitados
    db_path_relative = db_uri.replace('sqlite:///', '')
    
    if not db_path_relative.startswith('instance/'):
        db_path = os.path.join('instance', os.path.basename(db_path_relative))
    else:
        db_path = db_path_relative
    
    backup_manager = BackupManager(app, db_path)
    app.logger.info(f"📦 BackupManager inicializado (SQLite): {db_path}")
    
else:
    # ✅ PostgreSQL: Backups deshabilitados pero manager disponible
    backup_manager = BackupManager(app, db_path=None)
    app.logger.info(f"📦 BackupManager inicializado (PostgreSQL - sin backups)")

# Importar servicio de correos
from email_service import mail, enviar_confirmacion_pago, enviar_recordatorio_pago, enviar_aviso_vencimiento


# Importar license manager
from license_manager import license_manager

# Configurar logging
if not app.debug:
    if not os.path.exists('logs'):
        os.mkdir('logs')
    
    file_handler = RotatingFileHandler(
        'logs/sistema.log', 
        maxBytes=10240000,  # 10MB
        backupCount=10
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    
    app.logger.setLevel(logging.INFO)
    app.logger.info('Sistema de Mensualidades iniciado')


# ============================================
# MODELOS DE BASE DE DATOS
# ============================================

class Configuracion(db.Model):
    """Configuración dinámica del sistema"""
    __tablename__ = 'configuracion'
    
    id = db.Column(db.Integer, primary_key=True)
    clave = db.Column(db.String(100), unique=True, nullable=False, index=True)
    valor = db.Column(db.Text)
    descripcion = db.Column(db.Text)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def obtener(clave, valor_defecto=None):
        """Obtiene un valor de configuración"""
        config = Configuracion.query.filter_by(clave=clave).first()
        return config.valor if config else valor_defecto
    
    @staticmethod
    def establecer(clave, valor, descripcion=None):
        """Establece un valor de configuración"""
        config = Configuracion.query.filter_by(clave=clave).first()
        if config:
            config.valor = valor
            if descripcion:
                config.descripcion = descripcion
        else:
            config = Configuracion(clave=clave, valor=valor, descripcion=descripcion)
            db.session.add(config)
        db.session.commit()
        return config


class Plan(db.Model):
    """Planes de servicio/mensualidad"""
    __tablename__ = 'plan'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    precio = db.Column(db.Float, nullable=False)
    duracion_dias = db.Column(db.Integer, nullable=False, default=30)
    descripcion = db.Column(db.Text)
    activo = db.Column(db.Boolean, default=True, index=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relaciones
    clientes = db.relationship('Cliente', backref='plan', lazy=True)
    
    def __repr__(self):
        return f'<Plan {self.nombre}>'


class Cliente(db.Model):
    """Clientes del sistema"""
    __tablename__ = 'cliente'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, index=True)
    apellido = db.Column(db.String(100), nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    telefono = db.Column(db.String(20))
    direccion = db.Column(db.String(200))
    plan_id = db.Column(db.Integer, db.ForeignKey('plan.id'), index=True)
    fecha_inicio = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_fin = db.Column(db.DateTime)
    activo = db.Column(db.Boolean, default=True, index=True)
    notas = db.Column(db.Text)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relaciones
    pagos = db.relationship('Pago', backref='cliente', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Cliente {self.nombre_completo}>'

    @property
    def nombre_completo(self):
        """Nombre completo del cliente"""
        return f"{self.nombre} {self.apellido}"
    
    @property
    def dias_restantes(self):
        """Calcula los días restantes hasta la fecha_fin"""
        if not self.fecha_fin:
            return None
        dias = (self.fecha_fin - datetime.utcnow()).days
        return max(0, dias)
    
    @property
    def plan_vencido(self):
        """Verifica si el plan ha vencido"""
        if not self.fecha_fin:
            return False
        return datetime.utcnow() > self.fecha_fin
    
    @property
    def estado_pago(self):
        """Calcula el estado de pago del cliente"""
        if self.plan_vencido:
            return 'vencido'
        
        ultimo_pago = Pago.query.filter_by(cliente_id=self.id).order_by(Pago.fecha_pago.desc()).first()
        if not ultimo_pago:
            return 'sin-pagos'
        
        dias_desde_pago = (datetime.utcnow() - ultimo_pago.fecha_pago).days
        if self.plan:
            if dias_desde_pago > self.plan.duracion_dias + 5:
                return 'moroso'
            elif dias_desde_pago > self.plan.duracion_dias:
                return 'por-vencer'
        return 'al-dia'
    
    @property
    def saldo_pendiente(self):
        """Calcula el saldo pendiente (simplificado)"""
        if not self.plan:
            return 0
        total_pagos = sum(p.monto for p in self.pagos)
        meses_desde_inicio = max(1, (datetime.utcnow() - self.fecha_inicio).days // 30)
        total_esperado = self.plan.precio * meses_desde_inicio
        return max(0, total_esperado - total_pagos)


class Pago(db.Model):
    """Pagos realizados por clientes"""
    __tablename__ = 'pago'
    
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False, index=True)
    monto = db.Column(db.Float, nullable=False)
    fecha_pago = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    metodo_pago = db.Column(db.String(50))
    referencia = db.Column(db.String(100))
    notas = db.Column(db.Text)
    periodo = db.Column(db.String(20))
    
    def __repr__(self):
        return f'<Pago ${self.monto} - {self.cliente.nombre_completo}>'

with app.app_context():
        db.create_all()
        app.logger.info("Tablas verificadas/creadas")
# ============================================
# DECORADORES Y UTILIDADES
# ============================================

def requiere_licencia(f):
    """Decorador para verificar licencia antes de acceder a rutas"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Verificar estado de licencia
        es_demo, mensaje, info = license_manager.verificar_licencia_activa()
        
        if info.get('bloqueado'):
            # Sistema bloqueado - redirigir a pantalla de bloqueo
            return redirect(url_for('blockscreen'))
        
        # Guardar info en sesión para mostrar en templates
        session['es_demo'] = es_demo
        session['licencia_info'] = info
        session['licencia_mensaje'] = mensaje
        
        return f(*args, **kwargs)
    return decorated_function


def validar_email(email):
    """Valida formato de email"""
    import re
    patron = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(patron, email) is not None


# ============================================
# MANEJADORES DE ERRORES
# ============================================

@app.errorhandler(404)
def not_found_error(error):
    """Página no encontrada"""
    return render_template('errors/404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    """Error interno del servidor"""
    db.session.rollback()
    app.logger.error(f'Error 500: {error}')
    return render_template('errors/500.html'), 500


@app.errorhandler(403)
def forbidden_error(error):
    """Acceso prohibido"""
    return render_template('errors/403.html'), 403

# -*- coding: utf-8 -*-
# Continuación de app.py - Parte 2/3

# ============================================
# RUTAS PRINCIPALES
# ============================================

@app.route('/')
@requiere_licencia
def index():
    """Dashboard principal"""
    try:
        # Estadísticas generales
        total_clientes = Cliente.query.filter_by(activo=True).count()
        
        clientes_activos = Cliente.query.filter_by(activo=True).all()
        clientes_morosos = sum(1 for c in clientes_activos if c.estado_pago == 'moroso')
        clientes_vencidos = sum(1 for c in clientes_activos if c.plan_vencido)
        
        total_cobrado = db.session.query(db.func.sum(Pago.monto)).scalar() or 0
        total_pendiente = sum(c.saldo_pendiente for c in clientes_activos)
        
        ultimos_pagos = Pago.query.order_by(Pago.fecha_pago.desc()).limit(5).all()
        
        return render_template('index.html',
                             total_clientes=total_clientes,
                             clientes_morosos=clientes_morosos,
                             clientes_vencidos=clientes_vencidos,
                             total_cobrado=total_cobrado,
                             total_pendiente=total_pendiente,
                             ultimos_pagos=ultimos_pagos)
    except Exception as e:
        app.logger.error(f'Error en index: {e}')
        flash('Error cargando el dashboard', 'danger')
        return render_template('index.html',
                             total_clientes=0,
                             clientes_morosos=0,
                             clientes_vencidos=0,
                             total_cobrado=0,
                             total_pendiente=0,
                             ultimos_pagos=[])


@app.route('/blockscreen')
def blockscreen():
    """Pantalla de sistema bloqueado"""
    es_demo, mensaje, info = license_manager.verificar_licencia_activa()
    return render_template('blockscreen.html', mensaje=mensaje, info=info)


# ============================================
# RUTAS DE CLIENTES
# ============================================

@app.route('/clientes')
@requiere_licencia
def clientes():
    """Lista de clientes"""
    try:
        busqueda = request.args.get('busqueda', '').strip()
        
        if busqueda:
            clientes = Cliente.query.filter(
                (Cliente.nombre.contains(busqueda)) | 
                (Cliente.apellido.contains(busqueda)) |
                (Cliente.email.contains(busqueda))
            ).all()
        else:
            clientes = Cliente.query.order_by(Cliente.fecha_creacion.desc()).all()
        
        planes = Plan.query.filter_by(activo=True).all()
        
        return render_template('clientes/lista.html', clientes=clientes, planes=planes)
    except Exception as e:
        app.logger.error(f'Error en lista clientes: {e}')
        flash('Error cargando clientes', 'danger')
        return render_template('clientes/lista.html', clientes=[], planes=[])


@app.route('/clientes/nuevo', methods=['GET', 'POST'])
@requiere_licencia
def cliente_nuevo():
    """Crear nuevo cliente con fechas"""
    if request.method == 'POST':
        try:
            # Validaciones
            email = request.form.get('email', '').strip()
            if not validar_email(email):
                flash('Email inválido', 'danger')
                return redirect(url_for('cliente_nuevo'))
            
            # Verificar email duplicado
            if Cliente.query.filter_by(email=email).first():
                flash(f'Ya existe un cliente con el email {email}', 'danger')
                return redirect(url_for('cliente_nuevo'))
            
            plan_id = request.form.get('plan_id')
            
            # Obtener fechas del formulario
            fecha_inicio_str = request.form.get('fecha_inicio')
            fecha_fin_str = request.form.get('fecha_fin')
            
            # Convertir strings a datetime
            fecha_inicio = None
            fecha_fin = None
            
            if fecha_inicio_str:
                try:
                    fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d')
                except:
                    flash('Formato de fecha de inicio inválido', 'danger')
                    return redirect(url_for('cliente_nuevo'))
            else:
                # Si no se proporciona, usar fecha actual
                fecha_inicio = datetime.utcnow()
            
            if fecha_fin_str:
                try:
                    fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d')
                except:
                    flash('Formato de fecha de fin inválido', 'danger')
                    return redirect(url_for('cliente_nuevo'))
            elif plan_id:
                # Calcular fecha_fin automáticamente si hay plan
                plan = Plan.query.get(plan_id)
                if plan:
                    fecha_fin = fecha_inicio + timedelta(days=plan.duracion_dias)
            
            cliente = Cliente(
                nombre=request.form['nombre'].strip(),
                apellido=request.form['apellido'].strip(),
                email=email,
                telefono=request.form.get('telefono', '').strip() or None,
                direccion=request.form.get('direccion', '').strip() or None,
                plan_id=plan_id if plan_id else None,
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                notas=request.form.get('notas', '').strip() or None
            )
            
            db.session.add(cliente)
            db.session.commit()
            
            app.logger.info(f'Cliente creado: {cliente.nombre_completo} - Inicio: {fecha_inicio}, Fin: {fecha_fin}')
            flash(f'Cliente {cliente.nombre_completo} creado exitosamente', 'success')
            return redirect(url_for('cliente_detalle', id=cliente.id))
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Error creando cliente: {e}')
            flash('Error al crear el cliente', 'danger')
            return redirect(url_for('cliente_nuevo'))
    
    planes = Plan.query.filter_by(activo=True).all()
    return render_template('clientes/formulario.html', cliente=None, planes=planes)



@app.route('/clientes/<int:id>')
@requiere_licencia
def cliente_detalle(id):
    """Detalle de un cliente"""
    try:
        cliente = Cliente.query.get_or_404(id)
        pagos = Pago.query.filter_by(cliente_id=id).order_by(Pago.fecha_pago.desc()).all()
        return render_template('clientes/detalle.html', cliente=cliente, pagos=pagos)
    except Exception as e:
        app.logger.error(f'Error en detalle cliente {id}: {e}')
        flash('Cliente no encontrado', 'danger')
        return redirect(url_for('clientes'))



@app.route('/clientes/<int:id>/editar', methods=['GET', 'POST'])
@requiere_licencia
def cliente_editar(id):
    """Editar un cliente con fechas"""
    cliente = Cliente.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            # Validar email
            email = request.form.get('email', '').strip()
            if not validar_email(email):
                flash('Email inválido', 'danger')
                return redirect(url_for('cliente_editar', id=id))
            
            # Verificar email duplicado (excepto el mismo cliente)
            email_existe = Cliente.query.filter(
                Cliente.email == email,
                Cliente.id != id
            ).first()
            
            if email_existe:
                flash(f'Ya existe otro cliente con el email {email}', 'danger')
                return redirect(url_for('cliente_editar', id=id))
            
            # Actualizar datos básicos
            cliente.nombre = request.form['nombre'].strip()
            cliente.apellido = request.form['apellido'].strip()
            cliente.email = email
            cliente.telefono = request.form.get('telefono', '').strip() or None
            cliente.direccion = request.form.get('direccion', '').strip() or None
            
            # Actualizar fechas
            fecha_inicio_str = request.form.get('fecha_inicio')
            fecha_fin_str = request.form.get('fecha_fin')
            
            if fecha_inicio_str:
                try:
                    cliente.fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d')
                except:
                    flash('Formato de fecha de inicio inválido', 'danger')
                    return redirect(url_for('cliente_editar', id=id))
            
            if fecha_fin_str:
                try:
                    cliente.fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d')
                except:
                    flash('Formato de fecha de fin inválido', 'danger')
                    return redirect(url_for('cliente_editar', id=id))
            
            # Actualizar plan
            plan_id = request.form.get('plan_id')
            if plan_id != str(cliente.plan_id):
                cliente.plan_id = plan_id if plan_id else None
                # Si se cambia el plan, recalcular fecha_fin
                if plan_id and cliente.fecha_inicio:
                    plan = Plan.query.get(plan_id)
                    if plan:
                        cliente.fecha_fin = cliente.fecha_inicio + timedelta(days=plan.duracion_dias)
            
            cliente.notas = request.form.get('notas', '').strip() or None
            cliente.activo = 'activo' in request.form
            
            db.session.commit()
            
            app.logger.info(f'Cliente actualizado: {cliente.nombre_completo}')
            flash(f'Cliente {cliente.nombre_completo} actualizado exitosamente', 'success')
            return redirect(url_for('cliente_detalle', id=id))
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Error actualizando cliente {id}: {e}')
            flash('Error al actualizar el cliente', 'danger')
            return redirect(url_for('cliente_editar', id=id))
    
    planes = Plan.query.filter_by(activo=True).all()
    return render_template('clientes/formulario.html', cliente=cliente, planes=planes)


@app.route('/clientes/<int:id>/eliminar', methods=['POST'])
@requiere_licencia
def cliente_eliminar(id):
    """Eliminar un cliente"""
    try:
        cliente = Cliente.query.get_or_404(id)
        nombre = cliente.nombre_completo
        
        db.session.delete(cliente)
        db.session.commit()
        
        app.logger.info(f'Cliente eliminado: {nombre}')
        flash(f'Cliente {nombre} eliminado exitosamente', 'success')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error eliminando cliente {id}: {e}')
        flash('Error al eliminar el cliente', 'danger')
    
    return redirect(url_for('clientes'))


# ============================================
# RUTAS DE PAGOS
# ============================================

@app.route('/pagos')
@requiere_licencia
def pagos():
    """Lista de pagos"""
    try:
        pagos = Pago.query.order_by(Pago.fecha_pago.desc()).all()
        return render_template('pagos/lista.html', pagos=pagos)
    except Exception as e:
        app.logger.error(f'Error en lista pagos: {e}')
        flash('Error cargando pagos', 'danger')
        return render_template('pagos/lista.html', pagos=[])


@app.route('/pagos/nuevo/<int:cliente_id>', methods=['GET', 'POST'])
@requiere_licencia
def pago_nuevo(cliente_id):
    """Registrar nuevo pago"""
    cliente = Cliente.query.get_or_404(cliente_id)
    
    if request.method == 'POST':
        try:
            # Validar monto
            monto = float(request.form.get('monto', 0))
            if monto <= 0:
                flash('El monto debe ser mayor a 0', 'danger')
                return redirect(url_for('pago_nuevo', cliente_id=cliente_id))
            
            # Crear pago
            pago = Pago(
                cliente_id=cliente_id,
                monto=monto,
                metodo_pago=request.form.get('metodo_pago', '').strip() or None,
                referencia=request.form.get('referencia', '').strip() or None,
                notas=request.form.get('notas', '').strip() or None,
                periodo=request.form.get('periodo', '').strip() or None
            )
            db.session.add(pago)
            
            # Extender fecha_fin
            if cliente.plan:
                if cliente.fecha_fin:
                    # Si ya tiene fecha_fin, extenderla
                    cliente.fecha_fin = cliente.fecha_fin + timedelta(days=cliente.plan.duracion_dias)
                else:
                    # Si no tiene fecha_fin, crearla desde ahora
                    cliente.fecha_fin = datetime.utcnow() + timedelta(days=cliente.plan.duracion_dias)
            
            db.session.commit()
            
            app.logger.info(f'Pago registrado: ${monto} - {cliente.nombre_completo}')
            
            # Enviar correo de confirmación
            try:
                if app.config['ENABLE_EMAIL_NOTIFICATIONS']:
                    if enviar_confirmacion_pago(cliente, pago):
                        flash(f'Pago de ${monto:.2f} registrado y correo enviado a {cliente.email}', 'success')
                    else:
                        flash(f'Pago registrado pero no se pudo enviar el correo', 'warning')
                else:
                    flash(f'Pago de ${monto:.2f} registrado exitosamente', 'success')
            except Exception as e:
                app.logger.error(f'Error enviando correo: {e}')
                flash(f'Pago registrado pero error al enviar correo', 'warning')
            
            return redirect(url_for('cliente_detalle', id=cliente_id))
            
        except ValueError:
            flash('Monto inválido', 'danger')
            return redirect(url_for('pago_nuevo', cliente_id=cliente_id))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Error registrando pago: {e}')
            flash('Error al registrar el pago', 'danger')
            return redirect(url_for('pago_nuevo', cliente_id=cliente_id))
    
    return render_template('pagos/formulario.html', cliente=cliente, pago=None)


@app.route('/pagos/<int:id>/eliminar', methods=['POST'])
@requiere_licencia
def pago_eliminar(id):
    """Eliminar un pago"""
    try:
        pago = Pago.query.get_or_404(id)
        cliente_id = pago.cliente_id
        monto = pago.monto
        
        db.session.delete(pago)
        db.session.commit()
        
        app.logger.info(f'Pago eliminado: ${monto}')
        flash(f'Pago de ${monto:.2f} eliminado exitosamente', 'success')
        
        return redirect(url_for('cliente_detalle', id=cliente_id))
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error eliminando pago {id}: {e}')
        flash('Error al eliminar el pago', 'danger')
        return redirect(url_for('pagos'))


# -*- coding: utf-8 -*-
# Continuación de app.py - Parte 3/3

# ============================================
# RUTAS DE PLANES
# ============================================

@app.route('/planes')
@requiere_licencia
def planes():
    """Lista de planes"""
    try:
        planes = Plan.query.order_by(Plan.activo.desc(), Plan.fecha_creacion.desc()).all()
        return render_template('planes/lista.html', planes=planes)
    except Exception as e:
        app.logger.error(f'Error en lista planes: {e}')
        flash('Error cargando planes', 'danger')
        return render_template('planes/lista.html', planes=[])


@app.route('/planes/nuevo', methods=['GET', 'POST'])
@requiere_licencia
def plan_nuevo():
    """Crear nuevo plan"""
    if request.method == 'POST':
        try:
            # Validar precio
            precio = float(request.form.get('precio', 0))
            if precio <= 0:
                flash('El precio debe ser mayor a 0', 'danger')
                return redirect(url_for('plan_nuevo'))
            
            # Validar duración
            duracion_dias = int(request.form.get('duracion_dias', 30))
            if duracion_dias <= 0:
                flash('La duración debe ser mayor a 0 días', 'danger')
                return redirect(url_for('plan_nuevo'))
            
            plan = Plan(
                nombre=request.form['nombre'].strip(),
                precio=precio,
                duracion_dias=duracion_dias,
                descripcion=request.form.get('descripcion', '').strip() or None
            )
            
            db.session.add(plan)
            db.session.commit()
            
            app.logger.info(f'Plan creado: {plan.nombre}')
            flash(f'Plan {plan.nombre} creado exitosamente', 'success')
            return redirect(url_for('planes'))
            
        except ValueError as e:
            flash('Datos numéricos inválidos', 'danger')
            return redirect(url_for('plan_nuevo'))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Error creando plan: {e}')
            flash('Error al crear el plan', 'danger')
            return redirect(url_for('plan_nuevo'))
    
    return render_template('planes/formulario.html', plan=None)


@app.route('/planes/<int:id>/editar', methods=['GET', 'POST'])
@requiere_licencia
def plan_editar(id):
    """Editar un plan"""
    plan = Plan.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            # Validar precio
            precio = float(request.form.get('precio', 0))
            if precio <= 0:
                flash('El precio debe ser mayor a 0', 'danger')
                return redirect(url_for('plan_editar', id=id))
            
            # Validar duración
            duracion_dias = int(request.form.get('duracion_dias', 30))
            if duracion_dias <= 0:
                flash('La duración debe ser mayor a 0 días', 'danger')
                return redirect(url_for('plan_editar', id=id))
            
            plan.nombre = request.form['nombre'].strip()
            plan.precio = precio
            plan.duracion_dias = duracion_dias
            plan.descripcion = request.form.get('descripcion', '').strip() or None
            plan.activo = 'activo' in request.form
            
            db.session.commit()
            
            app.logger.info(f'Plan actualizado: {plan.nombre}')
            flash(f'Plan {plan.nombre} actualizado exitosamente', 'success')
            return redirect(url_for('planes'))
            
        except ValueError:
            flash('Datos numéricos inválidos', 'danger')
            return redirect(url_for('plan_editar', id=id))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Error actualizando plan {id}: {e}')
            flash('Error al actualizar el plan', 'danger')
            return redirect(url_for('plan_editar', id=id))
    
    return render_template('planes/formulario.html', plan=plan)


@app.route('/planes/<int:id>/eliminar', methods=['POST'])
@requiere_licencia
def plan_eliminar(id):
    """Eliminar un plan"""
    try:
        plan = Plan.query.get_or_404(id)
        
        # Verificar que no tenga clientes
        if plan.clientes:
            flash('No se puede eliminar un plan con clientes asociados', 'danger')
            return redirect(url_for('planes'))
        
        nombre = plan.nombre
        db.session.delete(plan)
        db.session.commit()
        
        app.logger.info(f'Plan eliminado: {nombre}')
        flash(f'Plan {nombre} eliminado exitosamente', 'success')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error eliminando plan {id}: {e}')
        flash('Error al eliminar el plan', 'danger')
    
    return redirect(url_for('planes'))


# ============================================
# CONFIGURACIÓN DEL SISTEMA
# ============================================

# -*- coding: utf-8 -*-
"""
PARCHE PARA app.py
Reemplaza la ruta /configuracion completa
"""

@app.route('/configuracion', methods=['GET', 'POST'])
@requiere_licencia
def configuracion():
    """Configuración del sistema"""
    if request.method == 'POST':
        accion = request.form.get('accion')
        
        # Guardar configuración de correo
        if accion == 'guardar_correo':
            try:
                mail_server = request.form.get('mail_server', '').strip()
                mail_port = request.form.get('mail_port', '').strip()
                mail_username = request.form.get('mail_username', '').strip()
                mail_password = request.form.get('mail_password', '').strip()
                mail_sender = request.form.get('mail_sender', '').strip()
                
                # Validar que no estén vacíos
                if not all([mail_server, mail_port, mail_username, mail_password, mail_sender]):
                    flash('⚠️ Todos los campos son obligatorios', 'warning')
                    return redirect(url_for('configuracion'))
                
                # Guardar en base de datos
                Configuracion.establecer('MAIL_SERVER', mail_server, 'Servidor SMTP')
                Configuracion.establecer('MAIL_PORT', mail_port, 'Puerto SMTP')
                Configuracion.establecer('MAIL_USERNAME', mail_username, 'Usuario de correo')
                Configuracion.establecer('MAIL_PASSWORD', mail_password, 'Contraseña de correo')
                Configuracion.establecer('MAIL_DEFAULT_SENDER', mail_sender, 'Correo remitente')
                
                # ✅ CRÍTICO: Actualizar configuración de Flask EN MEMORIA
                app.config['MAIL_SERVER'] = mail_server
                app.config['MAIL_PORT'] = int(mail_port)
                app.config['MAIL_USERNAME'] = mail_username
                app.config['MAIL_PASSWORD'] = mail_password
                app.config['MAIL_DEFAULT_SENDER'] = mail_sender
                app.config['MAIL_USE_TLS'] = True  # Importante
                app.config['MAIL_USE_SSL'] = False
                
                # ✅ CRÍTICO: Reinicializar Flask-Mail con la nueva configuración
                mail.init_app(app)
                
                app.logger.info(f'✅ Configuración de correo actualizada: {mail_username}')
                flash('✅ Configuración de correo guardada exitosamente. Prueba enviando un correo de prueba.', 'success')
                return redirect(url_for('configuracion'))
            except Exception as e:
                app.logger.error(f'❌ Error guardando config correo: {e}')
                flash(f'❌ Error al guardar configuración: {str(e)}', 'danger')
                return redirect(url_for('configuracion'))
        
        # Activar licencia
        elif accion == 'activar_licencia':
            license_key = request.form.get('license_key', '').strip()
            license_data = request.form.get('license_data', '').strip()
            
            if not license_key or not license_data:
                flash('Debes proporcionar ambos campos', 'danger')
                return redirect(url_for('configuracion'))
            
            success, mensaje = license_manager.guardar_licencia_local(license_key, license_data)
            
            if success:
                app.logger.info('Licencia activada exitosamente')
                flash(mensaje, 'success')
                session.clear()
                return redirect(url_for('index'))
            else:
                app.logger.warning(f'Error activando licencia: {mensaje}')
                flash(mensaje, 'danger')
                return redirect(url_for('configuracion'))
    
    # GET: Mostrar configuración
    # ✅ Cargar desde BD primero, luego desde .env si no existe
    config_correo = {
        'mail_server': Configuracion.obtener('MAIL_SERVER') or app.config.get('MAIL_SERVER', 'smtp.gmail.com'),
        'mail_port': Configuracion.obtener('MAIL_PORT') or app.config.get('MAIL_PORT', '587'),
        'mail_username': Configuracion.obtener('MAIL_USERNAME') or app.config.get('MAIL_USERNAME', ''),
        'mail_password': Configuracion.obtener('MAIL_PASSWORD') or app.config.get('MAIL_PASSWORD', ''),
        'mail_sender': Configuracion.obtener('MAIL_DEFAULT_SENDER') or app.config.get('MAIL_DEFAULT_SENDER', '')
    }
    
    # Obtener información de licencia
    info_licencia = license_manager.obtener_info_licencia()
    
    return render_template('configuracion.html', 
                         config_correo=config_correo,
                         info_licencia=info_licencia)


@app.route('/test-correo')
@requiere_licencia
def test_correo():
    """Envía un correo de prueba para verificar la configuración"""
    try:
        from email_service import test_email_config
        
        # ✅ IMPORTANTE: Cargar configuración desde BD antes de probar
        mail_server = Configuracion.obtener('MAIL_SERVER')
        mail_port = Configuracion.obtener('MAIL_PORT')
        mail_username = Configuracion.obtener('MAIL_USERNAME')
        mail_password = Configuracion.obtener('MAIL_PASSWORD')
        mail_sender = Configuracion.obtener('MAIL_DEFAULT_SENDER')
        
        # Si hay configuración en BD, usarla
        if all([mail_server, mail_username, mail_password]):
            app.config['MAIL_SERVER'] = mail_server
            app.config['MAIL_PORT'] = int(mail_port)
            app.config['MAIL_USERNAME'] = mail_username
            app.config['MAIL_PASSWORD'] = mail_password
            app.config['MAIL_DEFAULT_SENDER'] = mail_sender
            app.config['MAIL_USE_TLS'] = True
            mail.init_app(app)
        
        success, mensaje = test_email_config()
        
        if success:
            flash(f'✅ {mensaje}. Revisa tu bandeja de entrada en {app.config["MAIL_USERNAME"]}', 'success')
        else:
            flash(f'❌ Error al enviar correo de prueba: {mensaje}', 'danger')
            
    except Exception as e:
        app.logger.error(f'Error en test de correo: {e}')
        flash(f'❌ Error: {str(e)}', 'danger')
    
    return redirect(url_for('configuracion'))
# ============================================
# RUTAS DE BACKUP CORREGIDAS
# ============================================

@app.route('/backup/info')
@requiere_licencia
def backup_info():
    """Obtiene información de la base de datos actual"""
    try:
        info = backup_manager.obtener_info_bd()
        
        if info:
            return jsonify({
                'success': True,
                'info': {
                    'nombre': info['nombre'],
                    'tamano_mb': info['tamano_mb'],
                    'fecha_modificacion': info['fecha_modificacion_str'],
                    'tipo': info.get('tipo', 'SQLite'),
                    'backups_disponibles': info.get('backups_disponibles', False)
                }
            })
        else:
            return jsonify({
                'success': False, 
                'error': 'Información no disponible'
            }), 404
            
    except Exception as e:
        app.logger.error(f"Error obteniendo info de BD: {e}")
        return jsonify({
            'success': False, 
            'error': str(e)
        }), 500


@app.route('/backup/descargar')
@requiere_licencia
def descargar_bd():
    """Descarga un backup de la base de datos (solo SQLite)"""
    try:
        # Verificar si los backups están disponibles
        if not backup_manager.is_sqlite:
            flash('⚠️ Los backups solo están disponibles en desarrollo local (SQLite)', 'warning')
            return redirect(url_for('configuracion'))
        
        # Crear backup temporal
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        nombre_backup = f"backup_{timestamp}.db"
        
        success, mensaje, ruta_backup = backup_manager.crear_backup_temporal(nombre_backup)
        
        if not success:
            flash(mensaje, 'danger')
            return redirect(url_for('configuracion'))
        
        # Enviar archivo
        return send_file(
            ruta_backup,
            as_attachment=True,
            download_name=nombre_backup
        )
        
    except Exception as e:
        app.logger.error(f"Error descargando backup: {e}")
        flash(f'Error al descargar backup: {str(e)}', 'danger')
        return redirect(url_for('configuracion'))


@app.route('/backup/subir', methods=['POST'])
@requiere_licencia
def subir_bd():
    """Restaura la base de datos desde un archivo (solo SQLite)"""
    try:
        # Verificar si los backups están disponibles
        if not backup_manager.is_sqlite:
            flash('⚠️ La restauración solo está disponible en desarrollo local (SQLite)', 'warning')
            return redirect(url_for('configuracion'))
        
        archivo = request.files.get('archivo_bd')
        
        if not archivo:
            flash('No se seleccionó ningún archivo', 'danger')
            return redirect(url_for('configuracion'))
        
        if not archivo.filename.endswith('.db'):
            flash('El archivo debe tener extensión .db', 'danger')
            return redirect(url_for('configuracion'))
        
        # Cerrar todas las conexiones de la base de datos
        db.session.remove()
        db.engine.dispose()
        
        # Restaurar desde archivo
        success, mensaje = backup_manager.restaurar_desde_archivo(archivo)
        
        if not success:
            flash(mensaje, 'danger')
            return redirect(url_for('configuracion'))
        
        # Reiniciar conexión a la base de datos
        db.engine.dispose()
        
        # Página de éxito con recarga automática
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta http-equiv="refresh" content="3;url={url_for('index')}">
            <title>Restauración Exitosa</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    text-align: center;
                    padding: 50px;
                    background: #f5f5f5;
                }}
                .container {{
                    background: white;
                    padding: 40px;
                    border-radius: 10px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    max-width: 500px;
                    margin: 0 auto;
                }}
                .success-icon {{
                    font-size: 60px;
                    color: #28a745;
                    margin-bottom: 20px;
                }}
                h2 {{
                    color: #333;
                    margin-bottom: 15px;
                }}
                p {{
                    color: #666;
                    margin-bottom: 10px;
                }}
                a {{
                    color: #007bff;
                    text-decoration: none;
                }}
                a:hover {{
                    text-decoration: underline;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="success-icon">✅</div>
                <h2>Base de datos restaurada exitosamente</h2>
                <p>La página se recargará automáticamente en 3 segundos...</p>
                <p style="margin-top: 20px;">
                    <a href="{url_for('index')}">Haz clic aquí si no se recarga automáticamente</a>
                </p>
            </div>
        </body>
        </html>
        """
        
    except Exception as e:
        app.logger.error(f"Error restaurando backup: {e}")
        flash(f'Error al restaurar backup: {str(e)}', 'danger')
        return redirect(url_for('configuracion'))
# ============================================
# TAREA PROGRAMADA: LIMPIAR BACKUPS ANTIGUOS
# ============================================

@app.cli.command()
def limpiar_backups():
    """Limpia backups temporales antiguos (más de 1 hora)"""
    try:
        backup_manager.limpiar_backups_temporales()
        print("✅ Backups temporales limpiados")
    except Exception as e:
        print(f"❌ Error limpiando backups: {e}")


# ============================================
# UTILIDADES - RECORDATORIOS
# ============================================

@app.route('/enviar-recordatorios')
@requiere_licencia
def enviar_recordatorios():
    """Envía recordatorios a clientes morosos y con planes vencidos"""
    if not app.config.get('ENABLE_EMAIL_NOTIFICATIONS'):
        flash('Las notificaciones por correo están deshabilitadas', 'warning')
        return redirect(url_for('index'))
    
    try:
        clientes_activos = Cliente.query.filter_by(activo=True).all()
        clientes_morosos = [c for c in clientes_activos if c.estado_pago == 'moroso']
        clientes_vencidos = [c for c in clientes_activos if c.plan_vencido]
        
        enviados = 0
        errores = 0
        
        # Enviar a morosos
        for cliente in clientes_morosos:
            try:
                if enviar_recordatorio_pago(cliente, dias_vencido=10):
                    enviados += 1
                else:
                    errores += 1
            except Exception as e:
                app.logger.error(f'Error enviando a {cliente.email}: {e}')
                errores += 1
        
        # Enviar a vencidos (que no sean morosos)
        for cliente in clientes_vencidos:
            if cliente not in clientes_morosos:
                try:
                    if enviar_aviso_vencimiento(cliente, dias_para_vencer=0):
                        enviados += 1
                    else:
                        errores += 1
                except Exception as e:
                    app.logger.error(f'Error enviando a {cliente.email}: {e}')
                    errores += 1
        
        total = len(set(clientes_morosos + clientes_vencidos))
        
        app.logger.info(f'Recordatorios enviados: {enviados}/{total}')
        
        if errores > 0:
            flash(f'Se enviaron {enviados} de {total} recordatorios ({errores} errores)', 'warning')
        else:
            flash(f'Se enviaron {enviados} recordatorios de {total} clientes', 'success')
            
    except Exception as e:
        app.logger.error(f'Error enviando recordatorios: {e}')
        flash('Error al enviar recordatorios', 'danger')
    
    return redirect(url_for('index'))


# ============================================
# API REST
# ============================================

@app.route('/api/estadisticas')
def api_estadisticas():
    """API: Estadísticas generales"""
    if not app.config.get('ENABLE_API'):
        return jsonify({'error': 'API deshabilitada'}), 403
    
    try:
        clientes_activos = Cliente.query.filter_by(activo=True).all()
        
        return jsonify({
            'total_clientes': len(clientes_activos),
            'clientes_morosos': sum(1 for c in clientes_activos if c.estado_pago == 'moroso'),
            'total_cobrado': db.session.query(db.func.sum(Pago.monto)).scalar() or 0,
            'total_pendiente': sum(c.saldo_pendiente for c in clientes_activos),
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        app.logger.error(f'Error en API estadísticas: {e}')
        return jsonify({'error': 'Error interno'}), 500


# ============================================
# COMANDOS CLI
# ============================================

@app.cli.command()
def init_db():
    """Inicializa la base de datos"""
    db.create_all()
    print('✅ Base de datos inicializada')


@app.cli.command()
def create_demo_data():
    """Crea datos de demostración"""
    # Crear planes
    plan1 = Plan(nombre='Plan Básico', precio=50.00, duracion_dias=30, descripcion='Plan mensual básico')
    plan2 = Plan(nombre='Plan Premium', precio=100.00, duracion_dias=30, descripcion='Plan mensual premium')
    
    db.session.add(plan1)
    db.session.add(plan2)
    db.session.commit()
    
    # Crear clientes
    cliente1 = Cliente(
        nombre='Juan',
        apellido='Pérez',
        email='juan@ejemplo.com',
        telefono='0987654321',
        plan_id=plan1.id,
        fecha_fin=datetime.utcnow() + timedelta(days=30)
    )
    
    db.session.add(cliente1)
    db.session.commit()
    
    print('✅ Datos de demostración creados')


# Inicializar sistema de recordatorios automáticos
try:
    from reminder_scheduler import init_reminder_scheduler
    
    reminder_scheduler = init_reminder_scheduler(
        app=app,
        db=db,
        Cliente=Cliente,
        enviar_aviso_vencimiento=enviar_aviso_vencimiento
    )
    
    app.logger.info("✅ Sistema de recordatorios automáticos inicializado")
    
    # Detener scheduler al cerrar la aplicación
    import atexit
    atexit.register(lambda: reminder_scheduler.detener())
    
except Exception as e:
    app.logger.warning(f"⚠️ No se pudo inicializar recordatorios automáticos: {e}")
    app.logger.info("ℹ️ Los recordatorios manuales seguirán funcionando")


# ============================================
# RUTA: Activar Licencia desde Blockscreen
# ============================================

@app.route('/activar-licencia-block', methods=['POST'])
def activar_licencia_desde_block():
    """Activa la licencia directamente desde el blockscreen"""
    try:
        license_key = request.form.get('license_key', '').strip()
        license_data = request.form.get('license_data', '').strip()
        
        if not license_key or not license_data:
            flash('Debes proporcionar ambos campos: Clave y Datos', 'danger')
            return redirect(url_for('blockscreen'))
        
        # Intentar activar la licencia
        success, mensaje = license_manager.guardar_licencia_local(license_key, license_data)
        
        if success:
            app.logger.info('✅ Licencia activada exitosamente desde blockscreen')
            flash(mensaje, 'success')
            
            # Limpiar sesión y redirigir al dashboard
            session.clear()
            return redirect(url_for('index'))
        else:
            app.logger.warning(f'⚠️ Error activando licencia: {mensaje}')
            flash(mensaje, 'danger')
            return redirect(url_for('blockscreen'))
            
    except Exception as e:
        app.logger.error(f'❌ Error en activación de licencia: {e}')
        flash(f'Error al activar la licencia: {str(e)}', 'danger')
        return redirect(url_for('blockscreen'))


# ============================================
# RUTA ADICIONAL: Test de Recordatorios
# ============================================

@app.route('/test-recordatorios')
@requiere_licencia
def test_recordatorios():
    """Envía recordatorios inmediatamente (para testing)"""
    try:
        if 'reminder_scheduler' in globals():
            reminder_scheduler.enviar_ahora()
            flash('Recordatorios enviados exitosamente', 'success')
        else:
            flash('Sistema de recordatorios no está inicializado', 'warning')
    except Exception as e:
        app.logger.error(f'Error en test de recordatorios: {e}')
        flash(f'Error: {str(e)}', 'danger')
    
    return redirect(url_for('configuracion'))

@app.route('/test-recordatorio/<int:cliente_id>')
@requiere_licencia
def test_recordatorio_cliente(cliente_id):
    """Envía un recordatorio de prueba a un cliente específico (TESTING)"""
    try:
        cliente = Cliente.query.get_or_404(cliente_id)
        
        if not cliente.email:
            flash(f'❌ El cliente {cliente.nombre_completo} no tiene email registrado', 'danger')
            return redirect(url_for('cliente_detalle', id=cliente_id))
        
        if not cliente.plan:
            flash(f'❌ El cliente {cliente.nombre_completo} no tiene plan asignado', 'danger')
            return redirect(url_for('cliente_detalle', id=cliente_id))
        
        # Enviar recordatorio de prueba
        success = enviar_recordatorio_pago(cliente, dias_vencido=0)
        
        if success:
            flash(f'✅ Recordatorio de prueba enviado a {cliente.email}', 'success')
            app.logger.info(f'Recordatorio de prueba enviado a {cliente.email}')
        else:
            flash(f'❌ Error al enviar recordatorio a {cliente.email}. Revisa la configuración de correo.', 'danger')
            
    except Exception as e:
        app.logger.error(f'Error en test de recordatorio: {e}')
        flash(f'❌ Error: {str(e)}', 'danger')
    
    return redirect(url_for('cliente_detalle', id=cliente_id))


@app.route('/forzar-recordatorios')
@requiere_licencia
def forzar_recordatorios():
    """Envía recordatorios a TODOS los clientes activos (SOLO PARA PRUEBAS)"""
    try:
        clientes_activos = Cliente.query.filter_by(activo=True).all()
        
        if not clientes_activos:
            flash('⚠️ No hay clientes activos para enviar recordatorios', 'warning')
            return redirect(url_for('configuracion'))
        
        enviados = 0
        errores = 0
        sin_email = 0
        sin_plan = 0
        
        for cliente in clientes_activos:
            if not cliente.email:
                sin_email += 1
                continue
            
            if not cliente.plan:
                sin_plan += 1
                continue
            
            try:
                if enviar_recordatorio_pago(cliente, dias_vencido=0):
                    enviados += 1
                    app.logger.info(f'✅ Recordatorio enviado a {cliente.email}')
                else:
                    errores += 1
                    app.logger.error(f'❌ Error enviando a {cliente.email}')
            except Exception as e:
                errores += 1
                app.logger.error(f'❌ Excepción enviando a {cliente.email}: {e}')
        
        # Mostrar resumen
        mensaje = f'📊 Resumen del envío:\n'
        mensaje += f'✅ Enviados: {enviados}\n'
        if errores > 0:
            mensaje += f'❌ Errores: {errores}\n'
        if sin_email > 0:
            mensaje += f'⚠️ Sin email: {sin_email}\n'
        if sin_plan > 0:
            mensaje += f'⚠️ Sin plan: {sin_plan}\n'
        
        if errores > 0:
            flash(mensaje, 'warning')
        else:
            flash(mensaje, 'success')
        
        app.logger.info(f'Envío masivo de prueba completado: {enviados} enviados, {errores} errores')
        
    except Exception as e:
        app.logger.error(f'Error en envío masivo: {e}')
        flash(f'❌ Error: {str(e)}', 'danger')
    
    return redirect(url_for('configuracion'))


@app.route('/simular-vencimiento/<int:cliente_id>')
@requiere_licencia
def simular_vencimiento(cliente_id):
    """Simula que un cliente está vencido (cambia fecha_fin al pasado)"""
    try:
        cliente = Cliente.query.get_or_404(cliente_id)
        
        # Cambiar fecha_fin a hace 10 días
        cliente.fecha_fin = datetime.utcnow() - timedelta(days=10)
        db.session.commit()
        
        flash(f'⚠️ Cliente {cliente.nombre_completo} configurado como VENCIDO (fecha_fin: {cliente.fecha_fin.strftime("%d/%m/%Y")})', 'warning')
        app.logger.info(f'Cliente {cliente_id} configurado para simulación de vencimiento')
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error simulando vencimiento: {e}')
        flash(f'❌ Error: {str(e)}', 'danger')
    
    return redirect(url_for('cliente_detalle', id=cliente_id))
# ============================================
# PUNTO DE ENTRADA
# ============================================

def es_ejecutable():
    """Detecta si estamos corriendo como .exe o script"""
    return getattr(sys, 'frozen', False)

def abrir_navegador(url, delay=2):
    """Abre el navegador después de un delay"""
    import time
    import webbrowser
    time.sleep(delay)
    try:
        webbrowser.open(url)
    except:
        pass
# Programar limpieza periódica de backups (opcional)
import atexit

def limpiar_backups_al_cerrar():
    """Limpia backups temporales al cerrar la aplicación"""
    try:
        backup_manager.limpiar_backups_temporales()
        app.logger.info("🗑️ Backups temporales limpiados al cerrar")
    except Exception as e:
        app.logger.error(f"Error limpiando backups al cerrar: {e}")

atexit.register(limpiar_backups_al_cerrar)

if __name__ == '__main__':
    import threading
    
    ejecutable = es_ejecutable()
    
    # ✅ INICIALIZACIÓN INTELIGENTE DE BASE DE DATOS
    with app.app_context():
        try:
            db_uri = app.config['SQLALCHEMY_DATABASE_URI']
            
            if 'sqlite:///' in db_uri:
                # SQLite: Verificar archivo
                db_path = db_uri.replace('sqlite:///', '')
                db_existe = os.path.exists(db_path)
                
                if db_existe:
                    app.logger.info(f"✅ Base de datos SQLite existente: {db_path}")
                else:
                    app.logger.info(f"🆕 Creando nueva base de datos SQLite: {db_path}")
            else:
                # PostgreSQL: No verificar archivo
                app.logger.info(f"✅ Usando PostgreSQL en producción")
            
            # Crear todas las tablas (es seguro, no borra datos)
            db.create_all()
            app.logger.info("✅ Estructura de base de datos verificada")
            
        except Exception as e:
            app.logger.error(f"❌ Error inicializando la base de datos: {e}")
            import traceback
            app.logger.error(traceback.format_exc())
    
    # Configurar host y puerto
    host = '0.0.0.0' if Config.is_production() else '127.0.0.1'
    port = int(os.environ.get('PORT', 5000))
    url = f"http://{host}:{port}"
    
    # Solo abrir navegador en desarrollo
    if not Config.is_production() and not ejecutable:
        threading.Thread(
            target=abrir_navegador,
            args=(url, 2),
            daemon=True
        ).start()
        
        print(f"\n🌐 Servidor: {url}")
        print(f"⏳ El navegador se abrirá en 2 segundos...")
        print(f"💡 Presiona Ctrl+C para detener\n")
        print("=" * 60 + "\n")
    
    # Iniciar servidor
    debug = False if ejecutable or Config.is_production() else app.config.get('DEBUG', False)
    app.run(
        debug=debug,
        host=host,
        port=port,
        use_reloader=False
    )
