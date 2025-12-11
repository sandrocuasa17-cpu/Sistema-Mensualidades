# -*- coding: utf-8 -*-
"""
Sistema de Recordatorios Automáticos - VERSIÓN MEJORADA
Envía recordatorios en momentos estratégicos sin ser molesto
"""

from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import logging

class ReminderScheduler:
    def __init__(self, app, db, Cliente, enviar_aviso_vencimiento):
        """
        Inicializa el scheduler de recordatorios
        
        Args:
            app: Instancia de Flask
            db: Instancia de SQLAlchemy
            Cliente: Modelo de Cliente
            enviar_aviso_vencimiento: Función para enviar avisos
        """
        self.app = app
        self.db = db
        self.Cliente = Cliente
        self.enviar_aviso_vencimiento = enviar_aviso_vencimiento
        self.scheduler = BackgroundScheduler()
        self.logger = app.logger
        
    def iniciar(self):
        """Inicia el scheduler con las tareas programadas"""
        try:
            # Programar envío de recordatorios diarios a las 9:00 AM
            self.scheduler.add_job(
                func=self.enviar_recordatorios_diarios,
                trigger='cron',
                hour=9,
                minute=0,
                id='recordatorios_diarios',
                name='Envío de recordatorios diarios',
                replace_existing=True
            )
            
            self.scheduler.start()
            self.logger.info("✅ Scheduler de recordatorios iniciado correctamente")
            return True
        except Exception as e:
            self.logger.error(f"❌ Error iniciando scheduler: {e}")
            return False
    
    def enviar_recordatorios_diarios(self):
        """
        Envía recordatorios estratégicos sin ser molesto:
        - 3 días antes: "Tu plan vence en 3 días"
        - 1 día después de vencer: "Tu plan venció ayer, renuévalo pronto"
        """
        with self.app.app_context():
            try:
                self.logger.info("📧 Iniciando envío de recordatorios diarios...")
                
                # Obtener clientes activos con plan
                clientes_activos = self.Cliente.query.filter_by(activo=True).all()
                
                enviados_previos = 0
                enviados_vencidos = 0
                errores = 0
                saltados = 0
                
                for cliente in clientes_activos:
                    # Validar que tenga plan y fecha_fin
                    if not cliente.plan or not cliente.fecha_fin:
                        saltados += 1
                        continue
                    
                    # Calcular días para vencer
                    dias_para_vencer = (cliente.fecha_fin - datetime.utcnow()).days
                    
                    # 🎯 ESTRATEGIA NO MOLESTA:
                    
                    # 1. Recordatorio PREVIO: Solo a los 3 días antes
                    if dias_para_vencer == 3:
                        if self._enviar_recordatorio_seguro(cliente, dias_para_vencer, tipo='previo'):
                            enviados_previos += 1
                        else:
                            errores += 1
                    
                    # 2. Recordatorio POST-VENCIMIENTO: Solo 1 día después de vencer
                    elif dias_para_vencer == -1:
                        if self._enviar_recordatorio_seguro(cliente, dias_para_vencer, tipo='vencido'):
                            enviados_vencidos += 1
                        else:
                            errores += 1
                    
                    # Los demás días NO se envía nada (no molestar)
                
                # Log de resumen
                self.logger.info(
                    f"📊 Recordatorios completados: "
                    f"{enviados_previos} previos (3 días antes), "
                    f"{enviados_vencidos} vencidos (1 día después), "
                    f"{errores} errores, "
                    f"{saltados} saltados"
                )
                
            except Exception as e:
                self.logger.error(f"❌ Error en envío de recordatorios: {e}")
    
    def _enviar_recordatorio_seguro(self, cliente, dias_para_vencer, tipo='previo'):
        """
        Envía recordatorio con manejo de errores y validaciones
        
        Args:
            cliente: Objeto Cliente
            dias_para_vencer: Días hasta el vencimiento (puede ser negativo)
            tipo: 'previo' o 'vencido'
        
        Returns:
            bool: True si se envió correctamente, False si hubo error
        """
        try:
            # Validar email
            if not cliente.email:
                self.logger.warning(f"⚠️ Cliente {cliente.nombre_completo} sin email")
                return False
            
            # Enviar según el tipo
            if tipo == 'previo':
                # Recordatorio 3 días antes: tono amigable
                mensaje_tipo = f"recordatorio previo (3 días antes)"
            else:
                # Recordatorio 1 día después de vencer: tono urgente pero amable
                mensaje_tipo = f"recordatorio de vencimiento (1 día después)"
            
            # Intentar enviar
            if self.enviar_aviso_vencimiento(cliente, abs(dias_para_vencer)):
                self.logger.info(
                    f"✅ {mensaje_tipo} enviado a {cliente.email} "
                    f"({cliente.nombre_completo})"
                )
                return True
            else:
                self.logger.error(
                    f"❌ Error enviando {mensaje_tipo} a {cliente.email}"
                )
                return False
                
        except Exception as e:
            self.logger.error(
                f"❌ Excepción enviando a {cliente.email}: {e}"
            )
            return False
    
    def enviar_ahora(self):
        """Envía recordatorios inmediatamente (para testing)"""
        self.logger.info("🚀 Envío manual de recordatorios...")
        self.enviar_recordatorios_diarios()
    
    def detener(self):
        """Detiene el scheduler"""
        try:
            if self.scheduler.running:
                self.scheduler.shutdown()
                self.logger.info("ℹ️ Scheduler detenido")
        except Exception as e:
            self.logger.error(f"❌ Error deteniendo scheduler: {e}")


def init_reminder_scheduler(app, db, Cliente, enviar_aviso_vencimiento):
    """
    Función de inicialización del scheduler
    
    Returns:
        ReminderScheduler: Instancia del scheduler
    """
    scheduler = ReminderScheduler(app, db, Cliente, enviar_aviso_vencimiento)
    scheduler.iniciar()
    return scheduler