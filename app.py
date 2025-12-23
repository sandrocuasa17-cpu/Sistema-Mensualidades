
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
from sqlalchemy import func, and_, or_
from validadores import (
    validar_email, 
    validar_cedula_generica, 
    validar_cedula_ecuador,
    validar_formulario_cliente
)

from helpers_pagos import (
        calcular_distribucion_pago,
        validar_pago,
        obtener_sugerencias_pago,
        generar_resumen_estado
    )
# Importar configuración centralizada
from config import get_config

# Imports necesarios para autenticación y servicios
from auth import AuthManager, requiere_autenticacion, cambiar_password
from excel_reports import excel_generator

# Inicializar Flask
app = Flask(__name__)

# Cargar configuración según entorno
env = os.environ.get('FLASK_ENV', 'development')
app.config.from_object(get_config(env))

# Inicializar SQLAlchemy
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
from email_service import (
    mail, 
    enviar_confirmacion_pago, 
    enviar_aviso_vencimiento,
    enviar_recordatorio_pago,
    init_email_service,
    cargar_config_correo_desde_bd  # ✅ AGREGAR ESTA LÍNEA
)


# ✅ Context processor para templates
@app.context_processor
def inject_now():
    """Inyecta la función 'now' en todos los templates"""
    return {
        'now': datetime.now
    }

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
# MODELOS DE BASE DE DATOS (CORREGIDOS)
# ============================================

class Configuracion(db.Model):
    """Configuración dinámica del sistema"""
    __tablename__ = 'configuracion'
    
    id = db.Column(db.Integer, primary_key=True)
    clave = db.Column(db.String(100), unique=True, nullable=False, index=True)
    valor = db.Column(db.Text)
    descripcion = db.Column(db.Text)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

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


class Curso(db.Model):
    """
    Cursos con duración INDEFINIDA
    ✅ CAMBIO: Se eliminó duracion_meses (ahora es indefinido)
    """
    __tablename__ = 'curso'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    precio_mensual = db.Column(db.Float, nullable=False)
    precio_inscripcion = db.Column(db.Float, default=0)
    # ❌ ELIMINADO: duracion_meses (ahora indefinido)
    activo = db.Column(db.Boolean, default=True, index=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.now)
    
    # Relación con estudiantes
    estudiantes = db.relationship('Cliente', backref='curso', lazy=True, foreign_keys='Cliente.curso_id')
    
    def __repr__(self):
        return f'<Curso {self.nombre}>'


class Cliente(db.Model):
    """
    Estudiantes del sistema
    ✅ CAMBIO: Nuevo tracking separado para inscripción y mensualidades
    """
    __tablename__ = 'cliente'
    
    # ===================================
    # DATOS PERSONALES
    # ===================================
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, index=True)
    apellido = db.Column(db.String(100), nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    cedula = db.Column(db.String(20), unique=True, nullable=True, index=True)
    telefono = db.Column(db.String(20))
    direccion = db.Column(db.String(200))
    
    # ===================================
    # RELACIONES ACADÉMICAS
    # ===================================
    curso_id = db.Column(db.Integer, db.ForeignKey('curso.id'), index=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('plan.id'), index=True)  # Legacy
    
    # ===================================
    # ✅ NUEVO SISTEMA DE TRACKING DE PAGOS
    # ===================================
    # INSCRIPCIÓN (pago único)
    abono_inscripcion = db.Column(db.Float, default=0)  # Cuánto ha pagado de inscripción
    
    # MENSUALIDADES (pagos recurrentes)
    mensualidades_canceladas = db.Column(db.Integer, default=0)  # Meses COMPLETOS pagados
    carry_mensualidad = db.Column(db.Float, default=0)  # Dinero acumulado para próxima mensualidad
    
    # ===================================
    # FECHAS
    # ===================================
    fecha_registro = db.Column(db.DateTime, default=datetime.now)
    fecha_inicio_clases = db.Column(db.DateTime)
    fecha_fin = db.Column(db.DateTime)  # Fecha de vencimiento (basado en mensualidades)
    fecha_inicio = db.Column(db.DateTime, default=datetime.now)  # Legacy
    fecha_creacion = db.Column(db.DateTime, default=datetime.now)
    fecha_actualizacion = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    # ===================================
    # OTROS
    # ===================================
    activo = db.Column(db.Boolean, default=True, index=True)
    notas = db.Column(db.Text)
    observaciones_inscripcion = db.Column(db.Text)
    
    # ❌ ELIMINADO: valor_inscripcion (se toma del curso automáticamente)
    
    # Relaciones
    pagos = db.relationship('Pago', backref='cliente', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Cliente {self.nombre_completo}>'

    # ===================================
    # PROPIEDADES CALCULADAS
    # ===================================
    
    @property
    def nombre_completo(self):
        """Nombre completo del estudiante"""
        return f"{self.nombre} {self.apellido}"
    
    @property
    def inscripcion_pendiente(self):
        """
        Saldo pendiente de inscripción
        ✅ Se calcula automáticamente desde el curso
        """
        if not self.curso:
            return 0
        
        total_inscripcion = float(self.curso.precio_inscripcion or 0)
        abonado = float(self.abono_inscripcion or 0)
        
        return max(0, total_inscripcion - abonado)
    
    @property
    def inscripcion_pagada(self):
        """
        True si la inscripción está completamente pagada
        ✅ Tolerancia de $0.01 para errores de redondeo
        """
        return self.inscripcion_pendiente <= 0.01
    
    @property
    def porcentaje_inscripcion(self):
        """
        Porcentaje de inscripción pagado (0-100)
        """
        if not self.curso or self.curso.precio_inscripcion <= 0:
            return 100
        
        abonado = float(self.abono_inscripcion or 0)
        total = float(self.curso.precio_inscripcion)
        
        return min(100, (abonado / total) * 100)
    
    @property
    def ha_iniciado_clases(self):
        """True si ya llegó (o pasó) la fecha de inicio de clases"""
        if not self.fecha_inicio_clases:
            return True  # Sin fecha = asumimos que ya inició
        return datetime.now() >= self.fecha_inicio_clases

    @property
    def dias_para_inicio(self):
        """Días que faltan para iniciar clases (0 si ya inició)"""
        if not self.fecha_inicio_clases:
            return 0
        dias = (self.fecha_inicio_clases - datetime.now()).days
        return dias if dias > 0 else 0

    @property
    def dias_restantes(self):
        """
        Días restantes de cobertura
        
        LÓGICA:
        - Si aún no inicia clases: días de cobertura TOTAL
        - Si ya inició: días hasta fecha_fin
        """
        if not self.fecha_fin:
            return None

        # Si aún no inicia clases, no descuentas días
        if self.fecha_inicio_clases and datetime.now() < self.fecha_inicio_clases:
            return max(0, (self.fecha_fin - self.fecha_inicio_clases).days)

        # Si ya inició, sí descuentas desde hoy
        return (self.fecha_fin - datetime.now()).days

    @property
    def plan_vencido(self):
        """Vencido = fecha_fin pasada (pero solo si ya inició clases)"""
        if not self.fecha_fin:
            return False

        # Antes de iniciar clases nunca debe marcarse como vencido
        if self.fecha_inicio_clases and datetime.now() < self.fecha_inicio_clases:
            return False

        return datetime.now() > self.fecha_fin

    @property
    def proximo_a_vencer(self):
        """
        Próximo a vencer (0-7 días)
        Solo si ya inició clases y tiene al menos 1 mensualidad pagada
        """
        if not self.fecha_fin:
            return False
        if self.mensualidades_canceladas == 0:
            return False
        if self.plan_vencido:
            return False
        if not self.ha_iniciado_clases:
            return False

        dias = self.dias_restantes
        return dias is not None and 0 <= dias <= 7

    @property
    def estado_pago(self):
        """
        Estado de pago del estudiante
        
        Estados posibles:
        - sin-cobertura: No tiene fecha_fin o 0 mensualidades
        - pendiente-inicio: Pagó pero aún no inicia clases
        - vencido: fecha_fin pasada
        - por-vencer: 0-7 días restantes
        - al-dia: >7 días restantes
        """
        if not self.fecha_fin or self.mensualidades_canceladas == 0:
            return 'sin-cobertura'

        if not self.ha_iniciado_clases:
            return 'pendiente-inicio'

        dias = self.dias_restantes
        if dias is None:
            return 'sin-cobertura'

        if dias < 0:
            return 'vencido'
        elif 0 <= dias <= 7:
            return 'por-vencer'
        else:
            return 'al-dia'

    @property
    def total_programa(self):
        """
        Total a pagar por TODO el programa
        ✅ NOTA: Como la duración es indefinida, esto es solo referencial
        """
        total = 0.0

        # Inscripción
        if self.curso:
            total += float(self.curso.precio_inscripcion or 0)

        return round(total, 2)

    @property
    def total_pagado(self):
        """Total pagado por el estudiante (suma de todos los pagos)"""
        return round(sum(float(p.monto or 0) for p in self.pagos), 2)

    @property
    def saldo_pendiente(self):
        """
        Saldo pendiente SOLO de inscripción
        (Las mensualidades son indefinidas, no tienen "saldo pendiente" fijo)
        """
        return round(self.inscripcion_pendiente, 2)


class Pago(db.Model):
    """
    Pagos realizados por estudiantes
    ✅ NUEVO: Campo 'concepto' para identificar tipo de pago
    """
    __tablename__ = 'pago'
    
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False, index=True)
    monto = db.Column(db.Float, nullable=False)
    fecha_pago = db.Column(db.DateTime, default=datetime.now, index=True)
    
    # ✅ NUEVO: Concepto del pago
    concepto = db.Column(db.String(20), default='auto')  # 'auto', 'inscripcion', 'mensualidad'
    
    metodo_pago = db.Column(db.String(50))
    referencia = db.Column(db.String(100))
    notas = db.Column(db.Text)
    periodo = db.Column(db.String(20))
    
    def __repr__(self):
        return f'<Pago ${self.monto} - {self.cliente.nombre_completo}>'


class Plan(db.Model):
    """
    Planes de servicio (LEGACY - mantener para compatibilidad)
    """
    __tablename__ = 'plan'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    precio = db.Column(db.Float, nullable=False)
    duracion_dias = db.Column(db.Integer, nullable=False, default=30)
    descripcion = db.Column(db.Text)
    activo = db.Column(db.Boolean, default=True, index=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.now)
    
    clientes = db.relationship('Cliente', backref='plan', lazy=True)
    
    def __repr__(self):
        return f'<Plan {self.nombre}>'

def _recalcular_cobertura_cliente(cliente):
    """
    Recalcula la cobertura del estudiante con sistema de abonos inteligente
    
    CARACTERÍSTICAS:
    ✅ Permite abonos parciales a inscripción
    ✅ Permite abonos parciales a mensualidades
    ✅ Distribución automática: primero inscripción, luego mensualidades
    ✅ Acumula crédito (carry) para completar mensualidades
    ✅ Calcula cobertura exacta (30 días por mensualidad completa)
    
    FLUJO:
    1. Validar que tenga curso y fecha de inicio
    2. Obtener todos los pagos ordenados cronológicamente
    3. Procesar cada pago:
       - Primero cubrir inscripción (si está pendiente)
       - Luego acumular para mensualidades
    4. Calcular mensualidades completas
    5. Actualizar fecha de vencimiento
    
    Args:
        cliente: Objeto Cliente a recalcular
    
    Returns:
        dict con:
        - inscripcion_completa (bool)
        - abono_inscripcion (float)
        - inscripcion_pendiente (float)
        - total_meses (int)
        - carry (float)
        - fecha_fin (datetime)
    """
    
    # ===================================
    # 1. VALIDACIONES BÁSICAS
    # ===================================
    if not getattr(cliente, "curso", None):
        cliente.mensualidades_canceladas = 0
        cliente.fecha_fin = None
        cliente.abono_inscripcion = 0
        cliente.carry_mensualidad = 0
        return {
            "inscripcion_completa": False,
            "abono_inscripcion": 0,
            "inscripcion_pendiente": 0,
            "total_meses": 0,
            "carry": 0,
            "fecha_fin": None
        }
    
    try:
        precio_mensual = float(cliente.curso.precio_mensual)
        precio_inscripcion = float(cliente.curso.precio_inscripcion or 0)
    except (TypeError, ValueError, AttributeError):
        precio_mensual = 0.0
        precio_inscripcion = 0.0
    
    if precio_mensual <= 0:
        cliente.mensualidades_canceladas = 0
        cliente.fecha_fin = None
        cliente.abono_inscripcion = 0
        cliente.carry_mensualidad = 0
        return {
            "inscripcion_completa": False,
            "abono_inscripcion": 0,
            "inscripcion_pendiente": 0,
            "total_meses": 0,
            "carry": 0,
            "fecha_fin": None
        }
    
    if not getattr(cliente, "fecha_inicio_clases", None):
        cliente.mensualidades_canceladas = 0
        cliente.fecha_fin = None
        cliente.abono_inscripcion = 0
        cliente.carry_mensualidad = 0
        return {
            "inscripcion_completa": False,
            "abono_inscripcion": 0,
            "inscripcion_pendiente": 0,
            "total_meses": 0,
            "carry": 0,
            "fecha_fin": None
        }
    
    # ===================================
    # 2. OBTENER Y ORDENAR PAGOS
    # ===================================
    try:
        db.session.refresh(cliente, ['pagos'])
    except Exception:
        pass

    # Ordenar pagos cronológicamente
    pagos = sorted(
        list(cliente.pagos),
        key=lambda p: p.fecha_pago or datetime.now()
    )
    
    # ===================================
    # 3. PROCESAR PAGOS CON SISTEMA DE ABONOS
    # ===================================
    
    # Variables de tracking
    abono_inscripcion_acumulado = 0.0
    carry_mensualidades = 0.0
    total_meses = 0
    
    for pago in pagos:
        try:
            monto = float(pago.monto or 0)
            concepto = getattr(pago, 'concepto', 'auto') or 'auto'
        except (TypeError, ValueError):
            continue
        
        if monto <= 0:
            continue
        
        saldo_disponible = monto
        
        # ====================================
        # CONCEPTO: AUTOMÁTICO (distribución inteligente)
        # ====================================
        if concepto == 'auto':
            # PASO 1: Cubrir inscripción primero
            if precio_inscripcion > 0 and abono_inscripcion_acumulado < precio_inscripcion:
                falta_inscripcion = precio_inscripcion - abono_inscripcion_acumulado
                
                if saldo_disponible >= falta_inscripcion:
                    # Completa la inscripción
                    abono_inscripcion_acumulado = precio_inscripcion
                    saldo_disponible -= falta_inscripcion
                    app.logger.info(f"✅ Inscripción COMPLETADA con pago #{pago.id}")
                else:
                    # Abono parcial a inscripción
                    abono_inscripcion_acumulado += saldo_disponible
                    app.logger.info(
                        f"💰 Abono inscripción: ${saldo_disponible:.2f} "
                        f"(total: ${abono_inscripcion_acumulado:.2f}/${precio_inscripcion:.2f})"
                    )
                    saldo_disponible = 0
            
            # PASO 2: Lo que sobra va a mensualidades
            if saldo_disponible > 0:
                carry_mensualidades += saldo_disponible
                
                # Calcular mensualidades completas
                meses_completos = int(carry_mensualidades // precio_mensual)
                
                if meses_completos > 0:
                    total_meses += meses_completos
                    carry_mensualidades = round(carry_mensualidades - (meses_completos * precio_mensual), 2)
                    app.logger.info(
                        f"✅ {meses_completos} mensualidad(es) completada(s). "
                        f"Carry: ${carry_mensualidades:.2f}"
                    )
        
        # ====================================
        # CONCEPTO: SOLO INSCRIPCIÓN
        # ====================================
        elif concepto == 'inscripcion':
            if precio_inscripcion > 0:
                falta_inscripcion = max(0, precio_inscripcion - abono_inscripcion_acumulado)
                
                if falta_inscripcion > 0:
                    abono = min(saldo_disponible, falta_inscripcion)
                    abono_inscripcion_acumulado += abono
                    app.logger.info(
                        f"💰 Abono inscripción (concepto específico): ${abono:.2f}"
                    )
        
        # ====================================
        # CONCEPTO: SOLO MENSUALIDAD
        # ====================================
        elif concepto == 'mensualidad':
            carry_mensualidades += saldo_disponible
            
            meses_completos = int(carry_mensualidades // precio_mensual)
            
            if meses_completos > 0:
                total_meses += meses_completos
                carry_mensualidades = round(carry_mensualidades - (meses_completos * precio_mensual), 2)
                app.logger.info(
                    f"✅ {meses_completos} mensualidad(es) - concepto específico. "
                    f"Carry: ${carry_mensualidades:.2f}"
                )
    
    # ===================================
    # 4. ACTUALIZAR CLIENTE
    # ===================================
    cliente.abono_inscripcion = round(abono_inscripcion_acumulado, 2)
    cliente.mensualidades_canceladas = int(total_meses)
    cliente.carry_mensualidad = round(carry_mensualidades, 2)
    
    # Calcular fecha fin
    if total_meses <= 0:
        cliente.fecha_fin = cliente.fecha_inicio_clases
    else:
        cliente.fecha_fin = cliente.fecha_inicio_clases + timedelta(days=total_meses * 30)
    
    inscripcion_completa = (abono_inscripcion_acumulado >= precio_inscripcion) if precio_inscripcion > 0 else True
    inscripcion_pendiente = max(0, precio_inscripcion - abono_inscripcion_acumulado)
    
    # ===================================
    # 5. LOG DETALLADO
    # ===================================
    app.logger.info(f"""
    📊 RECÁLCULO DE COBERTURA: {cliente.nombre_completo}
    {'='*60}
    💵 Total pagado: ${sum(p.monto for p in pagos):.2f}
    📝 Inscripción: ${abono_inscripcion_acumulado:.2f} / ${precio_inscripcion:.2f} {'✅' if inscripcion_completa else '❌'}
    📅 Mensualidades: {total_meses} completas
    💰 Carry mensualidades: ${carry_mensualidades:.2f}
    🗓️ Fecha fin: {cliente.fecha_fin.strftime('%d/%m/%Y') if cliente.fecha_fin else 'N/A'}
    {'='*60}
    """)
    
    return {
        "inscripcion_completa": inscripcion_completa,
        "abono_inscripcion": abono_inscripcion_acumulado,
        "inscripcion_pendiente": inscripcion_pendiente,
        "total_meses": total_meses,
        "carry": carry_mensualidades,
        "fecha_fin": cliente.fecha_fin
    }
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
    if AuthManager.esta_autenticado():
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        password_hash = Configuracion.obtener('PASSWORD_HASH', AuthManager.DEFAULT_PASSWORD_HASH)
        
        if AuthManager.verificar_password(password, password_hash):
            AuthManager.iniciar_sesion(password)
            app.logger.info('Inicio de sesión exitoso')
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


@app.route('/cambiar-password', methods=['GET', 'POST'])
@requiere_licencia_y_auth
def cambiar_password_route():
    """Cambiar contraseña del sistema"""
    if request.method == 'POST':
        password_actual = request.form.get('password_actual', '').strip()
        password_nueva = request.form.get('password_nueva', '').strip()
        password_confirmar = request.form.get('password_confirmar', '').strip()
        
        # Validar que las contraseñas coincidan
        if password_nueva != password_confirmar:
            flash('❌ Las contraseñas nuevas no coinciden', 'danger')
            return redirect(url_for('cambiar_password_route'))
        
        # Validar longitud mínima
        if len(password_nueva) < 6:
            flash('❌ La nueva contraseña debe tener al menos 6 caracteres', 'danger')
            return redirect(url_for('cambiar_password_route'))
        
        # Intentar cambiar contraseña
        success, mensaje = cambiar_password(password_actual, password_nueva, db, Configuracion)
        
        if success:
            app.logger.info('✅ Contraseña cambiada exitosamente')
            flash(mensaje, 'success')
            return redirect(url_for('configuracion'))
        else:
            app.logger.warning(f'⚠️ Error cambiando contraseña: {mensaje}')
            flash(mensaje, 'danger')
    
    return render_template('cambiar_password.html')

# ============================================
# RUTA: BLOCKSCREEN (PANTALLA DE BLOQUEO)
# ============================================

@app.route('/blockscreen')
def blockscreen():
    """Pantalla de bloqueo cuando la licencia expira"""
    es_demo, mensaje, info = license_manager.verificar_licencia_activa()
    
    return render_template('blockscreen.html', 
                         mensaje=mensaje,
                         info=info)
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


# ============================================
# RUTAS DE CURSOS - ACTUALIZADAS
# ============================================

@app.route('/cursos/nuevo', methods=['GET', 'POST'])
@requiere_licencia_y_auth
def curso_nuevo():
    """Crear nuevo curso (sin duración)"""
    if request.method == 'POST':
        try:
            precio_mensual = float(request.form.get('precio_mensual', 0))
            precio_inscripcion = float(request.form.get('precio_inscripcion', 0))

            if precio_mensual <= 0:
                flash('El precio mensual debe ser mayor a 0', 'danger')
                return redirect(url_for('curso_nuevo'))

            curso = Curso(
                nombre=request.form['nombre'].strip(),
                descripcion=request.form.get('descripcion', '').strip() or None,
                precio_mensual=precio_mensual,
                precio_inscripcion=precio_inscripcion
            )

            db.session.add(curso)
            db.session.commit()

            app.logger.info(f'✅ Curso creado: {curso.nombre}')
            flash(f'✅ Curso {curso.nombre} creado exitosamente', 'success')
            return redirect(url_for('cursos'))

        except Exception as e:
            db.session.rollback()
            app.logger.error(f'❌ Error creando curso: {e}')
            flash('Error al crear el curso', 'danger')

    return render_template('cursos/formulario.html', curso=None)


@app.route('/cursos/<int:id>/editar', methods=['GET', 'POST'])
@requiere_licencia_y_auth
def curso_editar(id):
    curso = Curso.query.get_or_404(id)

    if request.method == 'POST':
        try:
            precio_mensual = float(request.form.get('precio_mensual', 0))
            precio_inscripcion = float(request.form.get('precio_inscripcion', 0))

            if precio_mensual <= 0:
                flash('El precio mensual debe ser mayor a 0', 'danger')
                return redirect(url_for('curso_editar', id=id))

            curso.nombre = request.form['nombre'].strip()
            curso.descripcion = request.form.get('descripcion', '').strip() or None
            curso.precio_mensual = precio_mensual
            curso.precio_inscripcion = precio_inscripcion
            curso.activo = 'activo' in request.form

            db.session.commit()

            app.logger.info(f'✅ Curso actualizado: {curso.nombre}')
            flash(f'✅ Curso {curso.nombre} actualizado exitosamente', 'success')
            return redirect(url_for('cursos'))

        except Exception as e:
            db.session.rollback()
            app.logger.error(f'❌ Error actualizando curso {id}: {e}')
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
# RUTAS DE REPORTES EXCEL
# ============================================

@app.route('/reportes')
@requiere_licencia_y_auth
def reportes():
    """Página de reportes"""
    total_estudiantes = Cliente.query.filter_by(activo=True).count()
    total_pagos = Pago.query.count()
    
    estudiantes_activos = Cliente.query.filter_by(activo=True).all()
    proximos_vencer = [e for e in estudiantes_activos if e.proximo_a_vencer]
    
    return render_template('reportes/index.html',
                         total_estudiantes=total_estudiantes,
                         total_pagos=total_pagos,
                         total_proximos_vencer=len(proximos_vencer))


@app.route('/reportes/estudiantes/excel')
@requiere_licencia_y_auth
def reporte_estudiantes_excel():
    """Genera reporte de estudiantes en Excel"""
    try:
        estudiantes = Cliente.query.order_by(Cliente.nombre).all()
        
        if not estudiantes:
            flash('⚠️ No hay estudiantes para generar el reporte', 'warning')
            return redirect(url_for('reportes'))
        
        excel_file = excel_generator.generar_reporte_estudiantes(estudiantes)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'reporte_estudiantes_{timestamp}.xlsx'
        
        app.logger.info(f'Reporte de estudiantes generado: {len(estudiantes)} registros')
        
        return send_file(
            excel_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        app.logger.error(f'Error generando reporte de estudiantes: {e}')
        flash('❌ Error al generar el reporte', 'danger')
        return redirect(url_for('reportes'))


@app.route('/reportes/pagos/excel')
@requiere_licencia_y_auth
def reporte_pagos_excel():
    """Genera reporte de pagos en Excel"""
    try:
        fecha_inicio_str = request.args.get('fecha_inicio')
        fecha_fin_str = request.args.get('fecha_fin')
        
        query = Pago.query
        fecha_inicio = None
        fecha_fin = None
        
        if fecha_inicio_str:
            try:
                fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d')
                query = query.filter(Pago.fecha_pago >= fecha_inicio)
            except:
                pass
        
        if fecha_fin_str:
            try:
                fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d')
                fecha_fin = fecha_fin.replace(hour=23, minute=59, second=59)
                query = query.filter(Pago.fecha_pago <= fecha_fin)
            except:
                pass
        
        pagos = query.order_by(Pago.fecha_pago.desc()).all()
        
        if not pagos:
            flash('⚠️ No hay pagos en el rango seleccionado', 'warning')
            return redirect(url_for('reportes'))
        
        excel_file = excel_generator.generar_reporte_pagos(pagos, fecha_inicio, fecha_fin)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'reporte_pagos_{timestamp}.xlsx'
        
        app.logger.info(f'Reporte de pagos generado: {len(pagos)} registros')
        
        return send_file(
            excel_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        app.logger.error(f'Error generando reporte de pagos: {e}')
        flash('❌ Error al generar el reporte', 'danger')
        return redirect(url_for('reportes'))


@app.route('/reportes/proximos-vencer/excel')
@requiere_licencia_y_auth
def reporte_proximos_vencer_excel():
    """Genera reporte de estudiantes próximos a vencer en Excel"""
    try:
        estudiantes_activos = Cliente.query.filter_by(activo=True).all()
        proximos_vencer = [e for e in estudiantes_activos if e.proximo_a_vencer]
        
        if not proximos_vencer:
            flash('⚠️ No hay estudiantes próximos a vencer', 'info')
            return redirect(url_for('reportes'))
        
        proximos_vencer.sort(key=lambda e: e.dias_restantes or 0)
        excel_file = excel_generator.generar_reporte_proximos_vencer(proximos_vencer)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'reporte_proximos_vencer_{timestamp}.xlsx'
        
        app.logger.info(f'Reporte próximos a vencer generado: {len(proximos_vencer)} estudiantes')
        
        return send_file(
            excel_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        app.logger.error(f'Error generando reporte próximos a vencer: {e}')
        flash('❌ Error al generar el reporte', 'danger')
        return redirect(url_for('reportes'))

        
@app.route('/reportes/completo/excel')
@requiere_licencia_y_auth
def reporte_completo_excel():
    """Genera reporte completo con múltiples hojas en Excel"""
    try:
        # Obtener todos los datos
        estudiantes = Cliente.query.order_by(Cliente.nombre).all()
        pagos = Pago.query.order_by(Pago.fecha_pago.desc()).all()
        cursos = Curso.query.filter_by(activo=True).all()
        
        if not estudiantes:
            flash('⚠️ No hay estudiantes para generar el reporte', 'warning')
            return redirect(url_for('reportes'))
        
        # Generar Excel con múltiples hojas
        excel_file = excel_generator.generar_reporte_completo(estudiantes, pagos, cursos)
        
        # Nombre del archivo con fecha
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'reporte_completo_{timestamp}.xlsx'
        
        app.logger.info(f'✅ Reporte completo generado: {len(estudiantes)} estudiantes, {len(pagos)} pagos')
        
        return send_file(
            excel_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        app.logger.error(f'❌ Error generando reporte completo: {e}')
        import traceback
        app.logger.error(traceback.format_exc())
        flash('❌ Error al generar el reporte', 'danger')
        return redirect(url_for('reportes'))
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
# FUNCIÓN CORREGIDA: Calcular Vencimiento
# ============================================

def calcular_fecha_vencimiento(fecha_inicio_clases, mensualidades_ya_pagadas=0):
    """
    Calcula la fecha de vencimiento EXACTA sin regalar días
    
    LÓGICA CORREGIDA:
    - 0 mensualidades pagadas = SIN COBERTURA = vence HOY MISMO
    - 1 mensualidad pagada = 30 días de cobertura desde inicio de clases
    - 2 mensualidades pagadas = 60 días de cobertura desde inicio de clases
    - N mensualidades pagadas = N * 30 días desde inicio de clases
    
    EJEMPLOS REALES:
    
    Caso 1: Inscripción nueva (0 pagadas)
    ----------------------------------------
    Inicio: 19/12/2025
    Pagadas: 0
    Días cubiertos: 0 * 30 = 0 días
    Vence: 19/12/2025 (MISMO DÍA - sin cobertura)
    Estado: ❌ "Sin cobertura - Debe pagar primera mensualidad"
    
    Caso 2: Pagó 1 mes
    -------------------
    Inicio: 19/12/2025
    Pagadas: 1
    Días cubiertos: 1 * 30 = 30 días
    Vence: 18/01/2026 (día 30 contando desde el 19/12)
    Estado: ✅ "Activo hasta 18/01/2026"
    
    Caso 3: Pagó 3 meses
    ---------------------
    Inicio: 19/12/2025
    Pagadas: 3
    Días cubiertos: 3 * 30 = 90 días
    Vence: 19/03/2026
    Estado: ✅ "Activo hasta 19/03/2026"
    
    Args:
        fecha_inicio_clases: datetime - Fecha en que empezaron las clases
        mensualidades_ya_pagadas: int - Cantidad de mensualidades YA canceladas
    
    Returns:
        datetime: Fecha EXACTA de vencimiento
    """
    if not isinstance(fecha_inicio_clases, datetime):
        raise ValueError("fecha_inicio_clases debe ser un objeto datetime")
    
    # ✅ CORRECCIÓN: Si no ha pagado nada, vence el MISMO día de inicio
    if mensualidades_ya_pagadas == 0:
        return fecha_inicio_clases  # SIN COBERTURA
    
    # Cálculo simple y directo
    dias_cubiertos = mensualidades_ya_pagadas * 30
    
    # La fecha de vencimiento es: inicio + días cubiertos
    fecha_vencimiento = fecha_inicio_clases + timedelta(days=dias_cubiertos)
    
    return fecha_vencimiento

def extender_fecha_vencimiento_con_pago(fecha_vencimiento_actual, monto_pagado, precio_mensual):
    """
    Extiende la fecha de vencimiento cuando se registra un pago
    
    LÓGICA CORREGIDA:
    - Calcula cuántas mensualidades COMPLETAS cubre el pago
    - Extiende 30 días por cada mensualidad completa
    - Retorna mensualidades agregadas para actualizar contador
    
    EJEMPLOS:
    
    Caso 1: Pago exacto de 1 mes
    -----------------------------
    Vence actualmente: 19/12/2025 (sin cobertura)
    Pago: $50.00 (precio mensual: $50.00)
    Mensualidades que cubre: $50/$50 = 1 mes
    Nueva fecha: 19/12/2025 + 30 días = 18/01/2026
    Mensualidades agregadas: +1
    
    Caso 2: Pago de 3 meses
    ------------------------
    Vence actualmente: 18/01/2026
    Pago: $150.00 (precio mensual: $50.00)
    Mensualidades que cubre: $150/$50 = 3 meses
    Nueva fecha: 18/01/2026 + 90 días = 18/04/2026
    Mensualidades agregadas: +3
    
    Caso 3: Pago parcial (NO cubre 1 mes completo)
    -----------------------------------------------
    Vence actualmente: 18/01/2026
    Pago: $25.00 (precio mensual: $50.00)
    Mensualidades que cubre: $25/$50 = 0.5 → 0 meses completos
    Nueva fecha: 18/01/2026 (NO cambia)
    Mensualidades agregadas: 0
    NOTA: El estudiante debe completar los $50 para obtener cobertura
    
    Args:
        fecha_vencimiento_actual: datetime - Fecha de vencimiento actual
        monto_pagado: float - Monto del pago realizado
        precio_mensual: float - Precio de la mensualidad del curso
    
    Returns:
        tuple: (nueva_fecha_vencimiento, mensualidades_agregadas, es_pago_completo)
    """
    if not isinstance(fecha_vencimiento_actual, datetime):
        raise ValueError("fecha_vencimiento_actual debe ser un objeto datetime")
    
    if monto_pagado <= 0 or precio_mensual <= 0:
        return fecha_vencimiento_actual, 0, False
    
    # ✅ Calcular cuántos meses COMPLETOS cubre el pago
    mensualidades_completas = int(monto_pagado / precio_mensual)
    
    if mensualidades_completas == 0:
        # ❌ Pago parcial - NO extiende la fecha
        return fecha_vencimiento_actual, 0, False
    
    # ✅ Extender la fecha: 30 días por cada mensualidad pagada
    dias_a_extender = 30 * mensualidades_completas
    nueva_fecha = fecha_vencimiento_actual + timedelta(days=dias_a_extender)
    
    return nueva_fecha, mensualidades_completas, True


def obtener_estado_estudiante(cliente):
    """Resumen de estado para UI / correos.

    Usa las propiedades del modelo para mantener una sola fuente de verdad:
    - cliente.estado_pago
    - cliente.dias_restantes
    - cliente.dias_para_inicio
    """
    if not cliente.fecha_fin:
        return {
            'estado': 'sin_cobertura',
            'dias_restantes': None,
            'mensaje': 'Sin fecha de vencimiento configurada',
            'color': 'secondary'
        }

    # Si no ha pagado ninguna mensualidad
    if cliente.mensualidades_canceladas == 0:
        return {
            'estado': 'sin_cobertura',
            'dias_restantes': 0,
            'mensaje': '❌ Sin cobertura - Debe pagar primera mensualidad',
            'color': 'danger'
        }

    # Si pagó pero aún no inicia clases
    if cliente.estado_pago == 'pendiente-inicio':
        return {
            'estado': 'pendiente_inicio',
            'dias_restantes': cliente.dias_restantes,
            'mensaje': f'⏳ Inicia clases en {cliente.dias_para_inicio} día{"s" if cliente.dias_para_inicio != 1 else ""}',
            'color': 'info'
        }

    dias_restantes = cliente.dias_restantes if cliente.dias_restantes is not None else 0

    if dias_restantes < 0:
        dias_vencido = abs(dias_restantes)
        return {
            'estado': 'vencido',
            'dias_restantes': dias_restantes,
            'mensaje': f'❌ Vencido hace {dias_vencido} día{"s" if dias_vencido != 1 else ""}',
            'color': 'danger'
        }
    elif dias_restantes <= 7:
        return {
            'estado': 'proximo_vencer',
            'dias_restantes': dias_restantes,
            'mensaje': f'⚠️ Vence en {dias_restantes} día{"s" if dias_restantes != 1 else ""}',
            'color': 'warning'
        }
    else:
        return {
            'estado': 'al_dia',
            'dias_restantes': dias_restantes,
            'mensaje': f'✅ {dias_restantes} días restantes',
            'color': 'success'
        }

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
# En app.py, reemplaza la ruta @app.route('/') con esta versión corregida:

@app.route('/')
@requiere_licencia_y_auth
def index():
    """Dashboard principal MEJORADO con analytics avanzados"""
    try:
        ahora = datetime.now()
        
        # ===================================
        # 1. ESTADÍSTICAS BÁSICAS
        # ===================================
        estudiantes_activos = Cliente.query.filter_by(activo=True).all()
        total_estudiantes = len(estudiantes_activos)
        
        # ===================================
        # 2. ANÁLISIS DE VENCIMIENTOS (MEJORADO)
        # ===================================
        sin_cobertura = []
        vencidos = []
        criticos = []  # 0-3 días
        proximamente = []  # 4-7 días
        al_dia = []  # >7 días
        
        for e in estudiantes_activos:
            dias = e.dias_restantes
            
            if e.mensualidades_canceladas == 0:
                sin_cobertura.append(e)
            elif dias is None or dias < 0:
                vencidos.append(e)
            elif dias <= 3:
                criticos.append(e)
            elif dias <= 7:
                proximamente.append(e)
            else:
                al_dia.append(e)
        
        # ===================================
        # 3. ANÁLISIS POR CURSO
        # ===================================
        cursos_stats = {}
        for curso in Curso.query.filter_by(activo=True).all():
            estudiantes_curso = [e for e in estudiantes_activos if e.curso_id == curso.id]
            
            if estudiantes_curso:
                cursos_stats[curso.id] = {
                    'nombre': curso.nombre,
                    'total': len(estudiantes_curso),
                    'vencidos': len([e for e in estudiantes_curso if e in vencidos]),
                    'criticos': len([e for e in estudiantes_curso if e in criticos]),
                    'proximamente': len([e for e in estudiantes_curso if e in proximamente]),
                    'al_dia': len([e for e in estudiantes_curso if e in al_dia]),
                    'sin_cobertura': len([e for e in estudiantes_curso if e in sin_cobertura])
                }
        
        # ===================================
        # 4. PROYECCIÓN DE INGRESOS
        # ===================================
        estudiantes_venceran_30dias = [
            e for e in estudiantes_activos 
            if e.dias_restantes is not None and 0 <= e.dias_restantes <= 30
        ]
        
        ingresos_proyectados = sum(
            e.curso.precio_mensual for e in estudiantes_venceran_30dias 
            if e.curso
        )
        
        # ===================================
        # 5. ESTADÍSTICAS FINANCIERAS
        # ===================================
        inicio_mes = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        pagos_este_mes = Pago.query.filter(
            Pago.fecha_pago >= inicio_mes
        ).all()
        
        total_mes_actual = sum(p.monto for p in pagos_este_mes)
        
        # Mes anterior
        if inicio_mes.month == 1:
            inicio_mes_anterior = inicio_mes.replace(year=inicio_mes.year - 1, month=12)
        else:
            inicio_mes_anterior = inicio_mes.replace(month=inicio_mes.month - 1)
        
        pagos_mes_anterior = Pago.query.filter(
            and_(
                Pago.fecha_pago >= inicio_mes_anterior,
                Pago.fecha_pago < inicio_mes
            )
        ).all()
        
        total_mes_anterior = sum(p.monto for p in pagos_mes_anterior)
        
        # Crecimiento
        if total_mes_anterior > 0:
            crecimiento_porcentual = ((total_mes_actual - total_mes_anterior) / total_mes_anterior) * 100
        else:
            crecimiento_porcentual = 100 if total_mes_actual > 0 else 0
        
        # ===================================
        # 6. CALENDARIO DE VENCIMIENTOS (PRÓXIMOS 7 DÍAS)
        # ===================================
        calendario_vencimientos = {}
        for i in range(8):  # 0-7 días
            fecha = ahora + timedelta(days=i)
            fecha_str = fecha.strftime('%Y-%m-%d')
            
            vencen_ese_dia = [
                e for e in estudiantes_activos 
                if e.fecha_fin and e.fecha_fin.date() == fecha.date()
            ]
            
            if vencen_ese_dia:
                calendario_vencimientos[fecha_str] = {
                    'fecha_display': fecha.strftime('%d/%m'),
                    'dia_semana': ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'][fecha.weekday()],
                    'estudiantes': vencen_ese_dia,
                    'cantidad': len(vencen_ese_dia),
                    'monto_esperado': sum(e.curso.precio_mensual for e in vencen_ese_dia if e.curso)
                }
        
        # ===================================
        # 7. ALERTAS INTELIGENTES
        # ===================================
        alertas = []
        
        if sin_cobertura:
            alertas.append({
                'tipo': 'danger',
                'icono': 'exclamation-triangle-fill',
                'titulo': f'{len(sin_cobertura)} estudiante(s) sin cobertura activa',
                'mensaje': 'Estos estudiantes no tienen ninguna mensualidad pagada.',
                'accion': 'clientes',
                'cantidad': len(sin_cobertura)
            })
        
        if vencidos:
            alertas.append({
                'tipo': 'danger',
                'icono': 'x-circle-fill',
                'titulo': f'{len(vencidos)} estudiante(s) con pago vencido',
                'mensaje': 'Requieren renovación urgente.',
                'accion': 'enviar_recordatorios',
                'cantidad': len(vencidos)
            })
        
        if criticos:
            alertas.append({
                'tipo': 'warning',
                'icono': 'clock-fill',
                'titulo': f'{len(criticos)} estudiante(s) críticos',
                'mensaje': 'Vencen en 3 días o menos.',
                'accion': 'enviar_recordatorios',
                'cantidad': len(criticos)
            })
        
        if proximamente:
            alertas.append({
                'tipo': 'info',
                'icono': 'info-circle-fill',
                'titulo': f'{len(proximamente)} estudiante(s) próximos a vencer',
                'mensaje': 'Vencen entre 4-7 días.',
                'accion': None,
                'cantidad': len(proximamente)
            })
        
        # ===================================
        # 8. ÚLTIMOS PAGOS
        # ===================================
        ultimos_pagos = Pago.query.order_by(Pago.fecha_pago.desc()).limit(5).all()
        
        # ===================================
        # RENDERIZAR TEMPLATE
        # ===================================
        return render_template('dashboard_mejorado.html',
            total_estudiantes=total_estudiantes,
            sin_cobertura=sin_cobertura,
            vencidos=vencidos,
            criticos=criticos,
            proximamente=proximamente,
            al_dia=al_dia,
            cursos_stats=cursos_stats,
            total_mes_actual=total_mes_actual,
            total_mes_anterior=total_mes_anterior,
            crecimiento_porcentual=crecimiento_porcentual,
            ingresos_proyectados=ingresos_proyectados,
            cantidad_pagos_mes=len(pagos_este_mes),
            calendario_vencimientos=calendario_vencimientos,
            alertas=alertas,
            ultimos_pagos=ultimos_pagos,
            mes_actual=ahora.strftime('%B %Y'),
            ahora=ahora
        )
        
    except Exception as e:
        app.logger.error(f'Error en dashboard: {e}')
        import traceback
        app.logger.error(traceback.format_exc())
        flash('Error cargando el dashboard', 'danger')
        
        # Fallback a valores vacíos
        return render_template('dashboard_mejorado.html',
            total_estudiantes=0,
            sin_cobertura=[],
            vencidos=[],
            criticos=[],
            proximamente=[],
            al_dia=[],
            cursos_stats={},
            total_mes_actual=0,
            total_mes_anterior=0,
            crecimiento_porcentual=0,
            ingresos_proyectados=0,
            cantidad_pagos_mes=0,
            calendario_vencimientos={},
            alertas=[],
            ultimos_pagos=[],
            mes_actual=datetime.now().strftime('%B %Y'),
            ahora=datetime.now()
        )
# ============================================
# RUTAS DE CLIENTES
# ============================================
@app.route('/clientes')
@requiere_licencia_y_auth
def clientes():
    """Lista de todos los clientes"""
    try:
        busqueda = request.args.get('busqueda', '').strip()
        
        if busqueda:
            # Búsqueda por nombre, apellido, email o cédula
            clientes = Cliente.query.filter(
                or_(
                    Cliente.nombre.ilike(f'%{busqueda}%'),
                    Cliente.apellido.ilike(f'%{busqueda}%'),
                    Cliente.email.ilike(f'%{busqueda}%'),
                    Cliente.cedula.ilike(f'%{busqueda}%') if busqueda else False
                )
            ).order_by(Cliente.fecha_creacion.desc()).all()
        else:
            # Todos los clientes
            clientes = Cliente.query.order_by(Cliente.fecha_creacion.desc()).all()
        
        # ✅ IMPORTANTE: Pasar 'clientes' (plural), NO 'cliente'
        return render_template('clientes/lista.html', clientes=clientes)
        
    except Exception as e:
        app.logger.error(f'Error en lista clientes: {e}')
        flash('❌ Error cargando la lista de estudiantes', 'danger')
        return render_template('clientes/lista.html', clientes=[])

# ============================================
# RUTAS DE CLIENTES - INSCRIPCIÓN MEJORADA
# ============================================

@app.route('/clientes/nuevo', methods=['GET', 'POST'])
@requiere_licencia_y_auth
def cliente_nuevo():
    """Inscribir nuevo estudiante (inscripción automática desde curso)"""
    if request.method == 'POST':
        try:
            # ===================================
            # 1. VALIDAR FORMULARIO COMPLETO
            # ===================================
            es_valido, errores = validar_formulario_cliente(request.form)
            
            if not es_valido:
                for error in errores:
                    flash(f'❌ {error}', 'danger')
                return redirect(url_for('cliente_nuevo'))
            
            # ===================================
            # 2. VALIDAR EMAIL ÚNICO
            # ===================================
            email = request.form.get('email', '').strip()
            if Cliente.query.filter_by(email=email).first():
                flash(f'❌ Ya existe un estudiante con el email {email}', 'danger')
                return redirect(url_for('cliente_nuevo'))
            
            # ===================================
            # 3. VALIDAR CÉDULA ÚNICA (SI SE PROPORCIONA)
            # ===================================
            cedula = request.form.get('cedula', '').strip()
            if cedula:
                cedula_existe = Cliente.query.filter_by(cedula=cedula).first()
                if cedula_existe:
                    flash(f'❌ Ya existe un estudiante con la cédula {cedula}', 'danger')
                    return redirect(url_for('cliente_nuevo'))
            
            # ===================================
            # 4. VALIDAR CURSO (OBLIGATORIO)
            # ===================================
            curso_id = request.form.get('curso_id')
            if not curso_id:
                flash('❌ Debes seleccionar un curso para la inscripción', 'danger')
                return redirect(url_for('cliente_nuevo'))
            
            curso = Curso.query.get(curso_id)
            if not curso or not curso.activo:
                flash('❌ El curso seleccionado no está disponible', 'danger')
                return redirect(url_for('cliente_nuevo'))
            
            # ===================================
            # 5. PROCESAR FECHAS
            # ===================================
            fecha_registro_str = request.form.get('fecha_registro')
            fecha_registro = datetime.strptime(fecha_registro_str, '%Y-%m-%d') if fecha_registro_str else datetime.now()
            
            fecha_inicio_clases_str = request.form.get('fecha_inicio_clases')
            if not fecha_inicio_clases_str:
                flash('❌ La fecha de inicio de clases es obligatoria', 'danger')
                return redirect(url_for('cliente_nuevo'))
            
            try:
                fecha_inicio_clases = datetime.strptime(fecha_inicio_clases_str, '%Y-%m-%d')
            except:
                flash('❌ Formato de fecha inválido', 'danger')
                return redirect(url_for('cliente_nuevo'))
            
            # ===================================
            # 6. CALCULAR FECHA DE VENCIMIENTO
            # ===================================
            mensualidades_canceladas = int(request.form.get('mensualidades_canceladas', 0))
            
            if mensualidades_canceladas == 0:
                fecha_fin = fecha_inicio_clases
            else:
                dias_cubiertos = mensualidades_canceladas * 30
                fecha_fin = fecha_inicio_clases + timedelta(days=dias_cubiertos)
            
            # ===================================
            # 7. ✅ VALOR DE INSCRIPCIÓN AUTOMÁTICO DESDE CURSO
            # ===================================
            valor_inscripcion = curso.precio_inscripcion  # ✅ Se toma del curso automáticamente
            
            # ===================================
            # 8. CREAR ESTUDIANTE
            # ===================================
            cliente = Cliente(
                nombre=request.form['nombre'].strip(),
                apellido=request.form['apellido'].strip(),
                email=email,
                cedula=cedula or None,
                telefono=request.form.get('telefono', '').strip() or None,
                direccion=request.form.get('direccion', '').strip() or None,
                curso_id=curso_id,
                plan_id=request.form.get('plan_id') or None,
                fecha_registro=fecha_registro,
                fecha_inicio_clases=fecha_inicio_clases,
                fecha_inicio=fecha_registro,
                fecha_fin=fecha_fin,
                mensualidades_canceladas=mensualidades_canceladas,
                observaciones_inscripcion=request.form.get('observaciones_inscripcion', '').strip() or None,
                notas=request.form.get('notas', '').strip() or None,
                activo=True
            )
            
            db.session.add(cliente)
            db.session.commit()
            
            # ===================================
            # 9. LOG Y MENSAJE DE ÉXITO
            # ===================================
            app.logger.info(
                f'✅ Inscripción: {cliente.nombre_completo} - '
                f'Cédula: {cliente.cedula or "N/A"} - '
                f'Curso: {curso.nombre} - '
                f'Inscripción: ${valor_inscripcion:.2f} - '
                f'Cobertura: {mensualidades_canceladas} meses'
            )
            
            flash(f'✅ ¡{cliente.nombre_completo} inscrito exitosamente!', 'success')
            return redirect(url_for('cliente_detalle', id=cliente.id))
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'❌ Error en inscripción: {e}')
            import traceback
            app.logger.error(traceback.format_exc())
            flash(f'❌ Error al inscribir: {str(e)}', 'danger')
            return redirect(url_for('cliente_nuevo'))
    
    # ===================================
    # GET: Mostrar formulario
    # ===================================
    cursos = Curso.query.filter_by(activo=True).all()
    planes = Plan.query.filter_by(activo=True).all()
    
    return render_template('clientes/formulario_extended.html', 
                         cliente=None, 
                         cursos=cursos, 
                         planes=planes)

@app.route('/clientes/<int:id>')
@requiere_licencia_y_auth
def cliente_detalle(id):
    """Detalle de un cliente - VERSION CORREGIDA"""
    try:
        # 1. Buscar cliente
        cliente = Cliente.query.get(id)
        
        # 2. Si no existe, mostrar error claro
        if not cliente:
            app.logger.warning(f'❌ Cliente {id} no encontrado')
            flash(f'❌ No se encontró el estudiante con ID {id}', 'danger')
            return redirect(url_for('clientes'))
        
        # 3. Obtener pagos ordenados
        pagos = Pago.query.filter_by(
            cliente_id=id
        ).order_by(
            Pago.fecha_pago.desc()
        ).all()
        
        # 4. Log de éxito
        app.logger.info(f'✅ Cliente {id} cargado: {cliente.nombre_completo}')
        
        # 5. Renderizar template
        return render_template(
            'clientes/detalle.html', 
            cliente=cliente, 
            pagos=pagos
        )
        
    except Exception as e:
        # 6. Manejo de errores detallado
        app.logger.error(f'❌ Error cargando cliente {id}: {str(e)}')
        import traceback
        app.logger.error(traceback.format_exc())
        
        flash(f'❌ Error al cargar el estudiante: {str(e)}', 'danger')
        return redirect(url_for('clientes'))

@app.route('/clientes/<int:id>/editar', methods=['GET', 'POST'])
@requiere_licencia_y_auth
def cliente_editar(id):
    cliente = Cliente.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            # Validar email único
            email = request.form.get('email', '').strip()
            email_existe = Cliente.query.filter(
                Cliente.email == email,
                Cliente.id != id
            ).first()
            
            if email_existe:
                flash(f'Ya existe otro estudiante con el email {email}', 'danger')
                return redirect(url_for('cliente_editar', id=id))
            
            # Validar cédula única (si se proporciona)
            cedula = request.form.get('cedula', '').strip()
            if cedula:
                cedula_existe = Cliente.query.filter(
                    Cliente.cedula == cedula,
                    Cliente.id != id
                ).first()
                
                if cedula_existe:
                    flash(f'Ya existe otro estudiante con la cédula {cedula}', 'danger')
                    return redirect(url_for('cliente_editar', id=id))
            
            # Actualizar datos personales
            cliente.nombre = request.form['nombre'].strip()
            cliente.apellido = request.form['apellido'].strip()
            cliente.email = email
            cliente.cedula = cedula or None
            cliente.telefono = request.form.get('telefono', '').strip() or None
            cliente.direccion = request.form.get('direccion', '').strip() or None
            cliente.activo = 'activo' in request.form
            
            # Actualizar notas
            cliente.notas = request.form.get('notas', '').strip() or None
            cliente.observaciones_inscripcion = request.form.get('observaciones_inscripcion', '').strip() or None
            
            # ✅ NO permitir cambio de curso
            # El curso_id se mantiene igual
            
            # Actualizar fecha de inicio si cambió
            fecha_inicio_str = request.form.get('fecha_inicio_clases')
            if fecha_inicio_str:
                nueva_fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d')
                if cliente.fecha_inicio_clases != nueva_fecha_inicio:
                    cliente.fecha_inicio_clases = nueva_fecha_inicio
                    # Recalcular fecha_fin basado en mensualidades_canceladas
                    mensualidades = int(request.form.get('mensualidades_canceladas', cliente.mensualidades_canceladas))
                    if mensualidades > 0:
                        cliente.fecha_fin = nueva_fecha_inicio + timedelta(days=mensualidades * 30)
                    else:
                        cliente.fecha_fin = nueva_fecha_inicio
            
            # Recalcular cobertura
            _recalcular_cobertura_cliente(cliente)
            db.session.commit()
            
            flash(f'✅ Estudiante {cliente.nombre_completo} actualizado exitosamente', 'success')
            return redirect(url_for('cliente_detalle', id=id))
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Error actualizando cliente {id}: {e}')
            flash(f'❌ Error al actualizar: {str(e)}', 'danger')
    
    cursos = Curso.query.filter_by(activo=True).all()
    return render_template('clientes/formulario_extended.html', 
                         cliente=cliente, 
                         cursos=cursos, 
                         planes=[])

@app.route('/clientes/<int:id>/eliminar', methods=['POST'])
@requiere_licencia_y_auth  # ✅ CAMBIO AQUÍ
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
# RUTAS DE PAGOS - SECCIÓN CORREGIDA
# ============================================
@app.route('/pagos')
@requiere_licencia_y_auth
def pagos():
    """Lista de pagos con filtros mejorados"""
    try:
        # Query base
        query = Pago.query
        
        # 🔍 FILTRO: Búsqueda por estudiante (nombre, cédula, email)
        busqueda = request.args.get('busqueda', '').strip()
        if busqueda:
            query = query.join(Cliente).filter(
                or_(
                    Cliente.nombre.ilike(f'%{busqueda}%'),
                    Cliente.apellido.ilike(f'%{busqueda}%'),
                    Cliente.email.ilike(f'%{busqueda}%'),
                    Cliente.cedula.ilike(f'%{busqueda}%'),
                    Pago.referencia.ilike(f'%{busqueda}%')
                )
            )
        
        # 📅 FILTRO: Fecha inicio
        fecha_inicio_str = request.args.get('fecha_inicio', '').strip()
        if fecha_inicio_str:
            try:
                fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d')
                query = query.filter(Pago.fecha_pago >= fecha_inicio)
            except ValueError:
                flash('⚠️ Formato de fecha inicio inválido', 'warning')
        
        # 📅 FILTRO: Fecha fin
        fecha_fin_str = request.args.get('fecha_fin', '').strip()
        if fecha_fin_str:
            try:
                fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d')
                fecha_fin = fecha_fin.replace(hour=23, minute=59, second=59)
                query = query.filter(Pago.fecha_pago <= fecha_fin)
            except ValueError:
                flash('⚠️ Formato de fecha fin inválido', 'warning')
        
        # 💳 FILTRO: Método de pago
        metodo = request.args.get('metodo', '').strip()
        if metodo:
            query = query.filter(Pago.metodo_pago == metodo)
        
        # Ejecutar query con orden descendente
        pagos = query.order_by(Pago.fecha_pago.desc()).all()
        
        # Log para debugging
        app.logger.info(f"🔍 Filtros aplicados - Búsqueda: '{busqueda}', Método: '{metodo}', Resultados: {len(pagos)}")
        
        return render_template('pagos/lista.html', pagos=pagos)
        
    except Exception as e:
        app.logger.error(f'❌ Error en lista de pagos: {e}')
        import traceback
        app.logger.error(traceback.format_exc())
        flash('Error cargando pagos', 'danger')
        return render_template('pagos/lista.html', pagos=[])

@app.route('/pagos/pdf')
@requiere_licencia_y_auth
def pagos_pdf():
    """Genera PDF de pagos filtrados"""
    try:
        from pdf_reports import pdf_generator
        
        # Aplicar los MISMOS filtros que en /pagos
        query = Pago.query
        
        busqueda = request.args.get('busqueda', '').strip()
        if busqueda:
            query = query.join(Cliente).filter(
                or_(
                    Cliente.nombre.ilike(f'%{busqueda}%'),
                    Cliente.apellido.ilike(f'%{busqueda}%'),
                    Cliente.email.ilike(f'%{busqueda}%'),
                    Cliente.cedula.ilike(f'%{busqueda}%'),
                    Pago.referencia.ilike(f'%{busqueda}%')
                )
            )
        
        fecha_inicio_str = request.args.get('fecha_inicio', '').strip()
        fecha_fin_str = request.args.get('fecha_fin', '').strip()
        
        if fecha_inicio_str:
            try:
                fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d')
                query = query.filter(Pago.fecha_pago >= fecha_inicio)
            except ValueError:
                pass
        
        if fecha_fin_str:
            try:
                fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d')
                fecha_fin = fecha_fin.replace(hour=23, minute=59, second=59)
                query = query.filter(Pago.fecha_pago <= fecha_fin)
            except ValueError:
                pass
        
        metodo = request.args.get('metodo', '').strip()
        if metodo:
            query = query.filter(Pago.metodo_pago == metodo)
        
        pagos = query.order_by(Pago.fecha_pago.desc()).all()
        
        if not pagos:
            flash('⚠️ No hay pagos para generar el PDF', 'warning')
            return redirect(url_for('pagos'))
        
        # Configurar info de empresa
        nombre_empresa = Configuracion.obtener('NOMBRE_EMPRESA', 'Sistema de Gestión')
        eslogan_empresa = Configuracion.obtener('ESLOGAN_EMPRESA', 'Control de Mensualidades')
        
        pdf_generator.nombre_empresa = nombre_empresa
        pdf_generator.eslogan_empresa = eslogan_empresa
        
        # Preparar info de filtros
        filtros = {}
        if fecha_inicio_str:
            filtros['fecha_inicio'] = fecha_inicio_str
        if fecha_fin_str:
            filtros['fecha_fin'] = fecha_fin_str
        if busqueda:
            filtros['estudiante'] = busqueda
        if metodo:
            filtros['metodo'] = metodo
        
        # Generar PDF
        pdf_file = pdf_generator.generar_reporte_pagos_lista(pagos, filtros)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'reporte_pagos_{timestamp}.pdf'
        
        app.logger.info(f'📄 PDF generado: {len(pagos)} pagos')
        
        return send_file(
            pdf_file,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        app.logger.error(f'❌ Error generando PDF: {e}')
        import traceback
        app.logger.error(traceback.format_exc())
        flash(f'❌ Error al generar PDF: {str(e)}', 'danger')
        return redirect(url_for('pagos'))


@app.route('/pagos/estudiante/<int:cliente_id>/pdf')
@requiere_licencia_y_auth
def pagos_estudiante_pdf(cliente_id):
    """Genera PDF de pagos de un estudiante específico"""
    try:
        from pdf_reports import pdf_generator
        
        cliente = Cliente.query.get_or_404(cliente_id)
        
        # Configurar info de empresa
        nombre_empresa = Configuracion.obtener('NOMBRE_EMPRESA', 'Sistema de Gestión')
        eslogan_empresa = Configuracion.obtener('ESLOGAN_EMPRESA', 'Control de Mensualidades')
        
        pdf_generator.nombre_empresa = nombre_empresa
        pdf_generator.eslogan_empresa = eslogan_empresa
        
        # Generar PDF
        pdf_file = pdf_generator.generar_reporte_estudiante(cliente)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'estudiante_{cliente.id}_{timestamp}.pdf'
        
        app.logger.info(f'📄 PDF generado para: {cliente.nombre_completo}')
        
        return send_file(
            pdf_file,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        app.logger.error(f'❌ Error generando PDF: {e}')
        import traceback
        app.logger.error(traceback.format_exc())
        flash(f'❌ Error al generar PDF: {str(e)}', 'danger')
        return redirect(url_for('cliente_detalle', id=cliente_id))
        
@app.route('/pagos/nuevo/<int:cliente_id>', methods=['GET', 'POST'])
@requiere_licencia_y_auth
def pago_nuevo(cliente_id):
    """
    Registrar un pago con sistema de abonos inteligente
    
    CARACTERÍSTICAS:
    ✅ Permite abonos parciales a inscripción
    ✅ Permite abonos parciales a mensualidades
    ✅ Acumula pagos hasta completar conceptos
    ✅ Recalcula cobertura automáticamente
    ✅ Muestra desglose detallado en tiempo real
    
    CONCEPTOS DE PAGO:
    - 'auto': Distribución automática (primero inscripción, luego mensualidades)
    - 'inscripcion': Solo para inscripción
    - 'mensualidad': Solo para mensualidades
    """
    
    
    cliente = Cliente.query.get_or_404(cliente_id)

    if request.method == 'POST':
        try:
            # ===================================
            # 1. VALIDAR MONTO
            # ===================================
            monto = float(request.form.get('monto', 0))
            if monto <= 0:
                flash('❌ El monto debe ser mayor a 0', 'danger')
                return redirect(url_for('pago_nuevo', cliente_id=cliente_id))

            # ===================================
            # 2. VALIDAR QUE TENGA CURSO
            # ===================================
            if not cliente.curso:
                flash('❌ El estudiante no tiene curso asignado', 'danger')
                return redirect(url_for('cliente_detalle', id=cliente_id))

            precio_mensual = float(cliente.curso.precio_mensual or 0)
            precio_inscripcion = float(cliente.curso.precio_inscripcion or 0)
            
            if precio_mensual <= 0:
                flash('❌ El curso no tiene un precio mensual válido', 'danger')
                return redirect(url_for('cliente_detalle', id=cliente_id))

            # ===================================
            # 3. OBTENER CONCEPTO DEL PAGO
            # ===================================
            concepto = request.form.get('concepto_pago', 'auto').strip()
            
            # Validar concepto
            if concepto not in ['auto', 'inscripcion', 'mensualidad']:
                concepto = 'auto'

            # ===================================
            # 4. CALCULAR QUÉ CUBRE EL PAGO (PREVIEW)
            # ===================================
            
            # Estado ANTES del pago
            inscripcion_pendiente_antes = cliente.inscripcion_pendiente
            meses_antes = int(cliente.mensualidades_canceladas or 0)
            carry_antes = float(cliente.carry_mensualidad or 0)
            fecha_fin_antes = cliente.fecha_fin
            
            # Simular distribución
            desglose = []
            saldo = monto
            
            # CONCEPTO: AUTOMÁTICO
            if concepto == 'auto':
                # ¿Cubre inscripción?
                if inscripcion_pendiente_antes > 0:
                    if saldo >= inscripcion_pendiente_antes:
                        desglose.append({
                            'tipo': 'inscripcion',
                            'monto': inscripcion_pendiente_antes,
                            'completo': True,
                            'descripcion': f"✅ Inscripción completa: ${inscripcion_pendiente_antes:.2f}"
                        })
                        saldo -= inscripcion_pendiente_antes
                    else:
                        desglose.append({
                            'tipo': 'inscripcion',
                            'monto': saldo,
                            'completo': False,
                            'descripcion': f"💰 Abono inscripción: ${saldo:.2f} (falta ${inscripcion_pendiente_antes - saldo:.2f})"
                        })
                        saldo = 0
                
                # ¿Cubre mensualidades?
                if saldo > 0:
                    carry_total = carry_antes + saldo
                    meses_completos = int(carry_total // precio_mensual)
                    carry_restante = carry_total % precio_mensual
                    
                    if meses_completos > 0:
                        desglose.append({
                            'tipo': 'mensualidad',
                            'monto': meses_completos * precio_mensual,
                            'completo': True,
                            'descripcion': f"✅ {meses_completos} mensualidad(es): ${meses_completos * precio_mensual:.2f}"
                        })
                    
                    if carry_restante > 0:
                        desglose.append({
                            'tipo': 'carry',
                            'monto': carry_restante,
                            'completo': False,
                            'descripcion': f"💰 Crédito acumulado: ${carry_restante:.2f} (falta ${precio_mensual - carry_restante:.2f})"
                        })
            
            # CONCEPTO: SOLO INSCRIPCIÓN
            elif concepto == 'inscripcion':
                if inscripcion_pendiente_antes > 0:
                    abono = min(saldo, inscripcion_pendiente_antes)
                    completo = (abono >= inscripcion_pendiente_antes)
                    
                    if completo:
                        desglose.append({
                            'tipo': 'inscripcion',
                            'monto': abono,
                            'completo': True,
                            'descripcion': f"✅ Inscripción completa: ${abono:.2f}"
                        })
                    else:
                        desglose.append({
                            'tipo': 'inscripcion',
                            'monto': abono,
                            'completo': False,
                            'descripcion': f"💰 Abono inscripción: ${abono:.2f} (falta ${inscripcion_pendiente_antes - abono:.2f})"
                        })
                else:
                    desglose.append({
                        'tipo': 'info',
                        'monto': 0,
                        'completo': False,
                        'descripcion': "⚠️ La inscripción ya está pagada"
                    })
            
            # CONCEPTO: SOLO MENSUALIDAD
            elif concepto == 'mensualidad':
                carry_total = carry_antes + saldo
                meses_completos = int(carry_total // precio_mensual)
                carry_restante = carry_total % precio_mensual
                
                if meses_completos > 0:
                    desglose.append({
                        'tipo': 'mensualidad',
                        'monto': meses_completos * precio_mensual,
                        'completo': True,
                        'descripcion': f"✅ {meses_completos} mensualidad(es): ${meses_completos * precio_mensual:.2f}"
                    })
                
                if carry_restante > 0:
                    desglose.append({
                        'tipo': 'carry',
                        'monto': carry_restante,
                        'completo': False,
                        'descripcion': f"💰 Crédito acumulado: ${carry_restante:.2f} (falta ${precio_mensual - carry_restante:.2f})"
                    })

            # ===================================
            # 5. REGISTRAR PAGO
            # ===================================
            pago = Pago(
                cliente_id=cliente_id,
                monto=monto,
                concepto=concepto,  # ✅ NUEVO CAMPO
                metodo_pago=(request.form.get('metodo_pago', '') or '').strip() or None,
                referencia=(request.form.get('referencia', '') or '').strip() or None,
                notas=(request.form.get('notas', '') or '').strip() or None,
                periodo=(request.form.get('periodo', '') or '').strip() or datetime.now().strftime('%m/%Y')
            )
            db.session.add(pago)
            db.session.flush()

            # ===================================
            # 6. RECALCULAR COBERTURA
            # ===================================
            resultado = _recalcular_cobertura_cliente(cliente)
            db.session.commit()

            # ===================================
            # 7. PREPARAR MENSAJE DE CONFIRMACIÓN
            # ===================================
            
            # Estado DESPUÉS del pago
            inscripcion_completa = resultado.get("inscripcion_completa", False)
            meses_despues = int(cliente.mensualidades_canceladas or 0)
            meses_ganados = max(0, meses_despues - meses_antes)
            carry_despues = resultado.get("carry", 0)
            
            # Construir mensaje
            mensaje_parts = [f'✅ Pago de ${monto:.2f} registrado exitosamente']
            
            # Concepto usado
            concepto_display = {
                'auto': 'Automático',
                'inscripcion': 'Inscripción',
                'mensualidad': 'Mensualidad'
            }.get(concepto, concepto)
            
            mensaje_parts.append(f"\n📋 Concepto: {concepto_display}")
            
            # Agregar desglose
            if desglose:
                mensaje_parts.append("\n\n🧾 Distribución:")
                for item in desglose:
                    mensaje_parts.append(f"\n   • {item['descripcion']}")
            
            # Estado de inscripción
            if precio_inscripcion > 0:
                if inscripcion_completa:
                    mensaje_parts.append("\n\n✅ Inscripción: COMPLETADA")
                else:
                    pendiente = resultado.get("inscripcion_pendiente", 0)
                    porcentaje = cliente.porcentaje_inscripcion
                    mensaje_parts.append(
                        f"\n\n⏳ Inscripción: {porcentaje:.0f}% completado "
                        f"(Pendiente: ${pendiente:.2f})"
                    )
            
            # Cobertura de mensualidades
            if meses_ganados > 0:
                mensaje_parts.append(f"\n📅 Cobertura: +{meses_ganados} mes(es)")
                if cliente.fecha_fin:
                    mensaje_parts.append(f"\n🗓️ Nuevo vencimiento: {cliente.fecha_fin.strftime('%d/%m/%Y')}")
            
            # Carry acumulado
            if carry_despues > 0:
                faltante = precio_mensual - carry_despues
                mensaje_parts.append(f"\n\n💰 Crédito acumulado: ${carry_despues:.2f}")
                mensaje_parts.append(f"   Faltan ${faltante:.2f} para completar 1 mensualidad")

            mensaje_flash = ''.join(mensaje_parts)

            # ===================================
            # 8. ENVIAR CORREO (OPCIONAL)
            # ===================================
            correo_enviado = False
            try:
                if app.config.get('ENABLE_EMAIL_NOTIFICATIONS', False):
                    from email_service import enviar_confirmacion_pago
                    correo_enviado = enviar_confirmacion_pago(cliente, pago)
            except Exception as e:
                app.logger.error(f'❌ Error enviando correo: {e}')

            if correo_enviado:
                mensaje_flash += f'\n\n✉️ Correo enviado a {cliente.email}'
            
            flash(mensaje_flash, 'success')
            
            # Log detallado
            app.logger.info(f"""
            💳 PAGO REGISTRADO
            {'='*60}
            👤 Estudiante: {cliente.nombre_completo}
            💵 Monto: ${monto:.2f}
            📋 Concepto: {concepto_display}
            🧾 Desglose: {', '.join(d['descripcion'] for d in desglose)}
            📊 Resultado:
               - Inscripción: {'✅ Completa' if inscripcion_completa else f'⏳ ${resultado.get("inscripcion_pendiente", 0):.2f} pendiente'}
               - Mensualidades: {meses_despues} ({'+' + str(meses_ganados) if meses_ganados > 0 else 'sin cambio'})
               - Carry: ${carry_despues:.2f}
            🗓️ Vencimiento: {cliente.fecha_fin.strftime('%d/%m/%Y') if cliente.fecha_fin else 'N/A'}
            {'='*60}
            """)
            
            return redirect(url_for('cliente_detalle', id=cliente_id))

        except ValueError:
            flash('❌ Monto inválido', 'danger')
            return redirect(url_for('pago_nuevo', cliente_id=cliente_id))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'❌ Error registrando pago: {e}')
            import traceback
            app.logger.error(traceback.format_exc())
            flash('❌ Error al registrar el pago', 'danger')
            return redirect(url_for('pago_nuevo', cliente_id=cliente_id))

    # ===================================
    # GET: MOSTRAR FORMULARIO CON INFO
    # ===================================
    return render_template('pagos/formulario.html', cliente=cliente, pago=None)
@app.route('/pagos/<int:id>/eliminar', methods=['POST'])
@requiere_licencia_y_auth
def pago_eliminar(id):
    """Eliminar un pago Y recalcular cobertura con sistema de abonos"""
    try:
        pago = Pago.query.get_or_404(id)
        cliente_id = pago.cliente_id
        cliente = pago.cliente
        monto = pago.monto
        
        # Estado antes de eliminar
        inscripcion_antes = cliente.abono_inscripcion
        meses_antes = cliente.mensualidades_canceladas
        
        # Eliminar pago
        db.session.delete(pago)
        db.session.flush()
        
        # ✅ CRÍTICO: Recalcular cobertura después de eliminar
        resultado = _recalcular_cobertura_cliente(cliente)
        
        db.session.commit()
        
        # Estado después
        inscripcion_despues = resultado.get("abono_inscripcion", 0)
        meses_despues = resultado.get("total_meses", 0)
        
        app.logger.info(f"""
        🗑️ PAGO ELIMINADO
        {'='*60}
        💵 Monto eliminado: ${monto:.2f}
        📊 Cambios:
           - Inscripción: ${inscripcion_antes:.2f} → ${inscripcion_despues:.2f}
           - Mensualidades: {meses_antes} → {meses_despues}
           - Nuevo vencimiento: {cliente.fecha_fin.strftime('%d/%m/%Y') if cliente.fecha_fin else 'Sin cobertura'}
        {'='*60}
        """)
        
        flash(
            f'✅ Pago de ${monto:.2f} eliminado exitosamente\n'
            f'📊 Cobertura actualizada:\n'
            f'   • Inscripción: ${inscripcion_despues:.2f}\n'
            f'   • Mensualidades: {meses_despues}\n'
            f'   • Vencimiento: {cliente.fecha_fin.strftime("%d/%m/%Y") if cliente.fecha_fin else "Sin cobertura"}',
            'success'
        )
        
        return redirect(url_for('cliente_detalle', id=cliente_id))
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'❌ Error eliminando pago {id}: {e}')
        import traceback
        app.logger.error(traceback.format_exc())
        flash('❌ Error al eliminar el pago', 'danger')
        return redirect(url_for('pagos'))
# ============================================
# CONFIGURACIÓN DEL SISTEMA
# ============================================
@app.route('/configuracion', methods=['GET', 'POST'])
@requiere_licencia_y_auth
def configuracion():
    """Configuración del sistema - VERSIÓN 100% FUNCIONAL"""
    
    if request.method == 'POST':
        accion = request.form.get('accion')

        # =========================
        # GUARDAR CONFIG DE CORREO
        # =========================
        if accion == 'guardar_correo':
            try:
                from email_service import cargar_config_correo_desde_bd
                import traceback

                # ✅ OBTENER DATOS DEL FORMULARIO (SIN MODIFICAR)
                mail_server = request.form.get('mail_server', '').strip()
                mail_port = request.form.get('mail_port', '').strip()
                mail_username = request.form.get('mail_username', '').strip()
                
                # ⚠️ CRÍTICO: NO hacer .strip() en la contraseña
                mail_password = request.form.get('mail_password', '')
                
                mail_sender = request.form.get('mail_sender', '').strip()

                # ✅ PERSONALIZACIÓN
                nombre_empresa = request.form.get('nombre_empresa', '').strip()
                eslogan_empresa = request.form.get('eslogan_empresa', '').strip()

                app.logger.info("=" * 70)
                app.logger.info("🔍 GUARDANDO CONFIGURACIÓN DE CORREO")
                app.logger.info("=" * 70)
                app.logger.info(f"Nombre Empresa: '{nombre_empresa}'")
                app.logger.info(f"Eslogan Empresa: '{eslogan_empresa}'")
                app.logger.info(f"SMTP Server: '{mail_server}'")
                app.logger.info(f"SMTP Port: '{mail_port}'")
                app.logger.info(f"SMTP Username: '{mail_username}'")
                app.logger.info(f"SMTP Password: {'*' * len(mail_password)} ({len(mail_password)} chars)")
                app.logger.info(f"Mail Sender: '{mail_sender}'")
                app.logger.info("=" * 70)

                # Validación 1: NOMBRE DE EMPRESA
                if not nombre_empresa:
                    flash('⚠️ Debes ingresar el NOMBRE DE LA EMPRESA', 'warning')
                    return redirect(url_for('configuracion'))

                # Validación 2: DATOS SMTP
                if not all([mail_server, mail_port, mail_username, mail_password, mail_sender]):
                    flash('⚠️ Completa todos los campos SMTP', 'warning')
                    return redirect(url_for('configuracion'))

                # Validación 3: PUERTO
                try:
                    mail_port_int = int(mail_port)
                except ValueError:
                    flash('⚠️ El puerto debe ser un número (ej: 587)', 'warning')
                    return redirect(url_for('configuracion'))

                # ✅ GUARDAR EN BD
                app.logger.info("💾 Guardando en base de datos...")
                
                Configuracion.establecer('MAIL_SERVER', mail_server, 'Servidor SMTP')
                Configuracion.establecer('MAIL_PORT', str(mail_port_int), 'Puerto SMTP')
                Configuracion.establecer('MAIL_USERNAME', mail_username, 'Usuario SMTP')
                
                # ⚠️ CRÍTICO: Guardar contraseña EXACTA sin strip()
                Configuracion.establecer('MAIL_PASSWORD', mail_password, 'Contraseña SMTP')
                
                Configuracion.establecer('MAIL_DEFAULT_SENDER', mail_sender, 'Remitente')
                Configuracion.establecer('NOMBRE_EMPRESA', nombre_empresa, 'Nombre de empresa')
                Configuracion.establecer('ESLOGAN_EMPRESA', eslogan_empresa, 'Eslogan de empresa')

                app.logger.info("✅ Datos guardados en BD")

                # ✅ RECARGAR Y VALIDAR SMTP
                app.logger.info("🔄 Recargando configuración...")
                ok = cargar_config_correo_desde_bd()

                if ok:
                    app.logger.info("✅ SMTP VALIDADO CORRECTAMENTE")
                    flash('✅ Configuración guardada y correos ACTIVADOS (SMTP OK)', 'success')
                else:
                    error_msg = app.config.get('SMTP_LAST_ERROR', 'Error desconocido')
                    app.logger.error(f"❌ Validación SMTP falló: {error_msg}")
                    flash(f'⚠️ Configuración guardada, pero SMTP tiene errores: {error_msg}', 'warning')

                return redirect(url_for('configuracion'))

            except Exception as e:
                app.logger.error(f"❌ ERROR: {e}")
                app.logger.error(traceback.format_exc())
                flash(f'❌ Error: {str(e)}', 'danger')
                return redirect(url_for('configuracion'))

        # =========================
        # LICENCIA
        # =========================
        elif accion == 'activar_licencia':
            try:
                license_key = request.form.get('license_key', '').strip()
                license_data = request.form.get('license_data', '').strip()

                if not license_key or not license_data:
                    flash('❌ Debes proporcionar clave y datos', 'danger')
                    return redirect(url_for('configuracion'))

                success, mensaje = license_manager.guardar_licencia_local(license_key, license_data)
                flash(mensaje, 'success' if success else 'danger')
                return redirect(url_for('configuracion'))

            except Exception as e:
                app.logger.error(f'Error activando licencia: {e}')
                flash(f'Error: {str(e)}', 'danger')
                return redirect(url_for('configuracion'))

    # =========================
    # GET: MOSTRAR FORMULARIO
    # =========================
    config_correo = {
        'mail_server': Configuracion.obtener('MAIL_SERVER') or 'smtp.gmail.com',
        'mail_port': Configuracion.obtener('MAIL_PORT') or '587',
        'mail_username': Configuracion.obtener('MAIL_USERNAME') or '',
        
        # ⚠️ MOSTRAR ASTERISCOS en el campo contraseña (por seguridad)
        'mail_password': Configuracion.obtener('MAIL_PASSWORD') or '',
        
        'mail_sender': Configuracion.obtener('MAIL_DEFAULT_SENDER') or '',
        'nombre_empresa': Configuracion.obtener('NOMBRE_EMPRESA') or '',
        'eslogan_empresa': Configuracion.obtener('ESLOGAN_EMPRESA') or ''
    }

    info_licencia = license_manager.obtener_info_licencia()
    
    return render_template('configuracion.html', 
                         config_correo=config_correo, 
                         info_licencia=info_licencia)

@app.route('/test-correo')
@requiere_licencia_y_auth  
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
@requiere_licencia_y_auth
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
@requiere_licencia_y_auth
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
@requiere_licencia_y_auth
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
@requiere_licencia_y_auth
def enviar_recordatorios():
    """Envía recordatorios a clientes con pagos próximos a vencer y vencidos"""
    if not app.config.get('ENABLE_EMAIL_NOTIFICATIONS'):
        flash('⚠️ Las notificaciones por correo están deshabilitadas. Actívalas en Configuración.', 'warning')
        return redirect(url_for('index'))
    
    try:
        clientes_activos = Cliente.query.filter_by(activo=True).all()
        
        # Filtrar estudiantes que necesitan recordatorio
        necesitan_recordatorio = []
        
        for cliente in clientes_activos:
            # Validaciones básicas
            if not cliente.email:
                app.logger.debug(f'⚠️ {cliente.nombre_completo} - Sin email')
                continue
                
            if not cliente.curso:
                app.logger.debug(f'⚠️ {cliente.nombre_completo} - Sin curso')
                continue
            
            # ✅ CAMBIO CRÍTICO: Si no tiene mensualidades pagadas, no enviar
            if cliente.mensualidades_canceladas == 0:
                app.logger.debug(f'⚠️ {cliente.nombre_completo} - Sin cobertura (0 mensualidades)')
                continue
            
            # Si no ha iniciado clases, no enviar recordatorio
            if not cliente.ha_iniciado_clases:
                app.logger.debug(f'⚠️ {cliente.nombre_completo} - No ha iniciado clases')
                continue
            
            dias = cliente.dias_restantes
            
            # ✅ Próximo a vencer (0-7 días) O vencido (negativo)
            if dias is not None and dias <= 7:
                necesitan_recordatorio.append((cliente, dias))
                app.logger.info(f'📌 {cliente.nombre_completo} - Necesita recordatorio ({dias} días)')
        
        if not necesitan_recordatorio:
            flash('ℹ️ No hay estudiantes que requieran recordatorios en este momento', 'info')
            return redirect(url_for('index'))
        
        enviados = 0
        errores = 0
        
        for cliente, dias in necesitan_recordatorio:
            try:
                if dias < 0:
                    # Vencido - enviar recordatorio de pago
                    app.logger.info(f'📧 Enviando recordatorio VENCIDO a {cliente.email} ({abs(dias)} días vencido)')
                    if enviar_recordatorio_pago(cliente, dias_vencido=abs(dias)):
                        enviados += 1
                        app.logger.info(f'✅ Recordatorio enviado (vencido): {cliente.email}')
                    else:
                        errores += 1
                        app.logger.error(f'❌ Error enviando (vencido): {cliente.email}')
                else:
                    # Próximo a vencer (0-7 días) - enviar aviso
                    app.logger.info(f'📧 Enviando aviso PRÓXIMO A VENCER a {cliente.email} ({dias} días)')
                    if enviar_aviso_vencimiento(cliente, dias_para_vencer=dias):
                        enviados += 1
                        app.logger.info(f'✅ Aviso enviado (vence en {dias} días): {cliente.email}')
                    else:
                        errores += 1
                        app.logger.error(f'❌ Error enviando aviso: {cliente.email}')
                        
            except Exception as e:
                errores += 1
                app.logger.error(f'❌ Excepción enviando a {cliente.email}: {e}')
                import traceback
                app.logger.error(traceback.format_exc())
        
        total = len(necesitan_recordatorio)
        
        # Mensaje de resultado
        if errores == 0:
            flash(
                f'✅ {enviados} recordatorio(s) enviado(s) exitosamente\n'
                f'📧 Revisa los correos electrónicos de los estudiantes',
                'success'
            )
        else:
            flash(
                f'📊 Resultados del envío:\n'
                f'✅ Enviados: {enviados}\n'
                f'❌ Errores: {errores}\n'
                f'📧 Total procesados: {total}',
                'warning'
            )
        
        app.logger.info(f'📊 Recordatorios enviados: {enviados}/{total} (errores: {errores})')
        
    except Exception as e:
        app.logger.error(f'❌ Error en envío de recordatorios: {e}')
        import traceback
        app.logger.error(traceback.format_exc())
        flash('❌ Error al enviar recordatorios. Revisa la configuración de correo.', 'danger')
    
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
@requiere_licencia_y_auth
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
@requiere_licencia_y_auth
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
@requiere_licencia_y_auth
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
@requiere_licencia_y_auth
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
import atexit

def limpiar_backups_al_cerrar():
    """Limpia backups temporales al cerrar la aplicación"""
    try:
        backup_manager.limpiar_backups_temporales()
        app.logger.info("🗑️ Backups temporales limpiados al cerrar")
    except Exception as e:
        app.logger.error(f"Error limpiando backups al cerrar: {e}")

atexit.register(limpiar_backups_al_cerrar)

# ============================================
# ✅ INICIALIZACIÓN COMPLETA Y CORREGIDA
# ============================================
with app.app_context():
    try:
        # 1. Crear tablas primero
        db.create_all()
        app.logger.info("✅ Tablas de base de datos creadas/verificadas")
        
        # 2. Inicializar contraseña por defecto si no existe
        if not Configuracion.obtener('PASSWORD_HASH'):
            Configuracion.establecer(
                'PASSWORD_HASH', 
                AuthManager.DEFAULT_PASSWORD_HASH,
                'Hash de contraseña del sistema (default: admin123)'
            )
            app.logger.info("🔒 Contraseña por defecto configurada: admin123")
        
        # 3. Inicializar el servicio de email con las dependencias
        init_email_service(db, Configuracion)
        app.logger.info("📧 Servicio de email inicializado con BD")
        
        # 4. Cargar configuración de correo desde BD
        app.logger.info("=" * 70)
        if cargar_config_correo_desde_bd():
            app.logger.info("✅ CORREOS ELECTRÓNICOS ACTIVADOS")
        else:
            error = app.config.get('SMTP_LAST_ERROR', 'Configuración incompleta')
            app.logger.warning("⚠️ CORREOS DESHABILITADOS")
            app.logger.warning(f"   Motivo: {error}")
            app.logger.warning("   Configura SMTP en: Configuración > Correo Electrónico")
        app.logger.info("=" * 70)
        
    except Exception as e:
        app.logger.error(f"❌ Error en inicialización: {e}")
        import traceback
        app.logger.error(traceback.format_exc())
        app.logger.warning("⚠️ El sistema funcionará sin notificaciones por email")

#================================================================================================================================================================================
#================================================================================================================================================================================

# ============================================
# API: ESTUDIANTES ACTIVOS (para testing)
# ============================================

@app.route('/api/estudiantes-activos')
@requiere_licencia_y_auth
def api_estudiantes_activos():
    """Lista de estudiantes activos para testing"""
    try:
        estudiantes = Cliente.query.filter_by(activo=True).all()
        return jsonify({
            'success': True,
            'estudiantes': [
                {
                    'id': e.id,
                    'nombre_completo': e.nombre_completo,
                    'email': e.email,
                    'fecha_fin': e.fecha_fin.strftime('%Y-%m-%d') if e.fecha_fin else None
                }
                for e in estudiantes
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# TEST: REGISTRAR PAGO
# ============================================

@app.route('/test-pago-estudiante/<int:cliente_id>')
@requiere_licencia_y_auth
def test_pago_estudiante(cliente_id):
    """Simula el registro de 1 mensualidad para testing"""
    try:
        cliente = Cliente.query.get_or_404(cliente_id)
        
        if not cliente.curso:
            return jsonify({
                'success': False,
                'error': 'El estudiante no tiene curso asignado'
            }), 400
        
        # Guardar estado original (para restaurar después)
        session[f'test_original_{cliente_id}'] = {
            'fecha_fin': cliente.fecha_fin.isoformat() if cliente.fecha_fin else None,
            'mensualidades_canceladas': cliente.mensualidades_canceladas
        }
        
        # Simular pago de 1 mensualidad
        monto = cliente.curso.precio_mensual
        
        # Crear pago
        pago = Pago(
            cliente_id=cliente_id,
            monto=monto,
            metodo_pago='Test',
            referencia=f'TEST-{datetime.now().strftime("%Y%m%d%H%M%S")}',
            notas='🧪 Pago de prueba (testing)',
            periodo=datetime.now().strftime('%m/%Y')
        )
        
        # Extender fecha de vencimiento
        if cliente.fecha_fin:
            nueva_fecha = cliente.fecha_fin + timedelta(days=30)
        else:
            nueva_fecha = datetime.utcnow() + timedelta(days=30)
        
        cliente.fecha_fin = nueva_fecha
        cliente.mensualidades_canceladas += 1
        
        db.session.add(pago)
        db.session.commit()
        
        # Enviar correo
        correo_enviado = False
        try:
            if app.config.get('ENABLE_EMAIL_NOTIFICATIONS'):
                correo_enviado = enviar_confirmacion_pago(cliente, pago)
        except Exception as e:
            app.logger.error(f'Error enviando correo de prueba: {e}')
        
        return jsonify({
            'success': True,
            'mensaje': f'✅ Pago simulado: ${monto:.2f} registrado',
            'email': cliente.email,
            'correo_enviado': correo_enviado,
            'nueva_fecha': nueva_fecha.strftime('%d/%m/%Y')
        })
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error en test de pago: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# TEST: PRÓXIMO A VENCER
# ============================================

@app.route('/test-proximo-vencer/<int:cliente_id>')
@requiere_licencia_y_auth
def test_proximo_vencer(cliente_id):
    """Configura estudiante próximo a vencer (3 días)"""
    try:
        cliente = Cliente.query.get_or_404(cliente_id)
        
        # Guardar estado original
        session[f'test_original_{cliente_id}'] = {
            'fecha_fin': cliente.fecha_fin.isoformat() if cliente.fecha_fin else None,
            'mensualidades_canceladas': cliente.mensualidades_canceladas
        }
        
        # Configurar fecha de vencimiento a 3 días desde hoy
        cliente.fecha_fin = datetime.utcnow() + timedelta(days=3)
        
        # Asegurar que tenga al menos 1 mensualidad cancelada
        if cliente.mensualidades_canceladas == 0:
            cliente.mensualidades_canceladas = 1
        
        db.session.commit()
        
        # Enviar recordatorio
        correo_enviado = False
        try:
            if app.config.get('ENABLE_EMAIL_NOTIFICATIONS'):
                correo_enviado = enviar_aviso_vencimiento(cliente, dias_para_vencer=3)
        except Exception as e:
            app.logger.error(f'Error enviando recordatorio de prueba: {e}')
        
        return jsonify({
            'success': True,
            'mensaje': '✅ Estudiante configurado como "Próximo a Vencer"',
            'fecha_fin': cliente.fecha_fin.strftime('%d/%m/%Y'),
            'email': cliente.email,
            'correo_enviado': correo_enviado
        })
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error en test próximo a vencer: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# TEST: VENCIDO
# ============================================

@app.route('/test-vencido/<int:cliente_id>')
@requiere_licencia_y_auth
def test_vencido(cliente_id):
    """Configura estudiante vencido (-10 días)"""
    try:
        cliente = Cliente.query.get_or_404(cliente_id)
        
        # Guardar estado original
        session[f'test_original_{cliente_id}'] = {
            'fecha_fin': cliente.fecha_fin.isoformat() if cliente.fecha_fin else None,
            'mensualidades_canceladas': cliente.mensualidades_canceladas
        }
        
        # Configurar fecha de vencimiento a 10 días en el pasado
        cliente.fecha_fin = datetime.utcnow() - timedelta(days=10)
        
        # Asegurar que tenga al menos 1 mensualidad cancelada
        if cliente.mensualidades_canceladas == 0:
            cliente.mensualidades_canceladas = 1
        
        db.session.commit()
        
        # Enviar recordatorio
        correo_enviado = False
        try:
            if app.config.get('ENABLE_EMAIL_NOTIFICATIONS'):
                correo_enviado = enviar_recordatorio_pago(cliente, dias_vencido=10)
        except Exception as e:
            app.logger.error(f'Error enviando recordatorio de prueba: {e}')
        
        return jsonify({
            'success': True,
            'mensaje': '✅ Estudiante configurado como "Vencido"',
            'fecha_fin': cliente.fecha_fin.strftime('%d/%m/%Y'),
            'email': cliente.email,
            'correo_enviado': correo_enviado
        })
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error en test vencido: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# TEST: RESTAURAR ESTADO ORIGINAL
# ============================================

@app.route('/test-restaurar/<int:cliente_id>')
@requiere_licencia_y_auth
def test_restaurar(cliente_id):
    """Restaura el estado original del estudiante"""
    try:
        cliente = Cliente.query.get_or_404(cliente_id)
        
        # Recuperar estado original
        estado_key = f'test_original_{cliente_id}'
        estado_original = session.get(estado_key)
        
        if not estado_original:
            return jsonify({
                'success': False,
                'error': 'No hay estado original guardado para este estudiante'
            }), 400
        
        # Restaurar valores
        if estado_original['fecha_fin']:
            cliente.fecha_fin = datetime.fromisoformat(estado_original['fecha_fin'])
        else:
            cliente.fecha_fin = None
        
        cliente.mensualidades_canceladas = estado_original['mensualidades_canceladas']
        
        # Eliminar pagos de prueba
        Pago.query.filter(
            Pago.cliente_id == cliente_id,
            Pago.notas.like('%testing%')
        ).delete()
        
        db.session.commit()
        
        # Limpiar sesión
        session.pop(estado_key, None)
        
        return jsonify({
            'success': True,
            'mensaje': '✅ Estado original restaurado exitosamente'
        })
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error restaurando estado: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500
#================================================================================================================================================================================
 #================================================================================================================================================================================       
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
    env = os.environ.get('FLASK_ENV', 'development')
    is_production = (env == 'production')
    
    host = '0.0.0.0' if is_production else '127.0.0.1'
    port = int(os.environ.get('PORT', 5000))
    url = f"http://{host}:{port}"
    
    # Solo abrir navegador en desarrollo
    if not is_production and not ejecutable:
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
    debug = False if ejecutable or is_production else app.config.get('DEBUG', False)
    app.run(
        debug=debug,
        host=host,
        port=port,
        use_reloader=False
    )