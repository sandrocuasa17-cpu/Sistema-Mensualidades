# -*- coding: utf-8 -*-
"""
Sistema de Recordatorios Automáticos - VERSIÓN FINAL OPTIMIZADA
✅ Trabaja con CURSOS (no planes)
✅ Usa ambas funciones: enviar_aviso_vencimiento Y enviar_recordatorio_pago
✅ Estrategia inteligente en 3 momentos clave
✅ Logs detallados de cada acción
✅ Manejo robusto de errores
"""

from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import logging

class ReminderScheduler:
    def __init__(self, app, db, Cliente, enviar_aviso_vencimiento, enviar_recordatorio_pago):
        """
        Inicializa el scheduler de recordatorios
        
        Args:
            app: Instancia de Flask
            db: Instancia de SQLAlchemy
            Cliente: Modelo de Cliente
            enviar_aviso_vencimiento: Función para avisos preventivos (3 días antes)
            enviar_recordatorio_pago: Función para recordatorios urgentes (vencidos)
        """
        self.app = app
        self.db = db
        self.Cliente = Cliente
        self.enviar_aviso_vencimiento = enviar_aviso_vencimiento
        self.enviar_recordatorio_pago = enviar_recordatorio_pago
        self.scheduler = BackgroundScheduler()
        self.logger = app.logger
        
    def iniciar(self):
        """
        Inicia el scheduler con tareas programadas en 3 momentos estratégicos
        
        ESTRATEGIA NO MOLESTA:
        - 9:00 AM: Avisos preventivos (3 días antes)
        - 10:00 AM: Recordatorios urgentes (1 día después de vencer)
        - 2:00 PM: Recordatorios críticos (7+ días vencidos)
        """
        try:
            # ========================================
            # TAREA 1: AVISOS PREVENTIVOS (9:00 AM)
            # ========================================
            self.scheduler.add_job(
                func=self.enviar_avisos_preventivos,
                trigger='cron',
                hour=9,
                minute=0,
                id='avisos_preventivos_9am',
                name='Avisos preventivos (3 días antes)',
                replace_existing=True
            )
            self.logger.info("✅ Programado: Avisos preventivos a las 9:00 AM")
            
            # ========================================
            # TAREA 2: RECORDATORIOS URGENTES (10:00 AM)
            # ========================================
            self.scheduler.add_job(
                func=self.enviar_recordatorios_urgentes,
                trigger='cron',
                hour=10,
                minute=0,
                id='recordatorios_urgentes_10am',
                name='Recordatorios urgentes (1 día vencido)',
                replace_existing=True
            )
            self.logger.info("✅ Programado: Recordatorios urgentes a las 10:00 AM")
            
            # ========================================
            # TAREA 3: RECORDATORIOS CRÍTICOS (2:00 PM)
            # ========================================
            self.scheduler.add_job(
                func=self.enviar_recordatorios_criticos,
                trigger='cron',
                hour=14,
                minute=0,
                id='recordatorios_criticos_2pm',
                name='Recordatorios críticos (7+ días vencidos)',
                replace_existing=True
            )
            self.logger.info("✅ Programado: Recordatorios críticos a las 2:00 PM")
            
            # Iniciar scheduler
            self.scheduler.start()
            self.logger.info("=" * 70)
            self.logger.info("🎯 SCHEDULER DE RECORDATORIOS INICIADO CORRECTAMENTE")
            self.logger.info("=" * 70)
            self.logger.info("📅 Horarios programados:")
            self.logger.info("   - 9:00 AM: Avisos preventivos (3 días antes)")
            self.logger.info("   - 10:00 AM: Recordatorios urgentes (1 día vencido)")
            self.logger.info("   - 2:00 PM: Recordatorios críticos (7+ días vencidos)")
            self.logger.info("=" * 70)
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error iniciando scheduler: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def enviar_avisos_preventivos(self):
        """
        📅 TAREA 1: Avisos preventivos (3 días antes de vencer)
        
        ESTRATEGIA:
        - Solo a estudiantes que vencen EXACTAMENTE en 3 días
        - Tono amigable y preventivo
        - No es molesto porque solo se envía UNA vez
        """
        with self.app.app_context():
            try:
                self.logger.info("=" * 70)
                self.logger.info("📅 INICIANDO AVISOS PREVENTIVOS (3 días antes)")
                self.logger.info("=" * 70)
                
                # Obtener estudiantes activos
                estudiantes_activos = self.Cliente.query.filter_by(activo=True).all()
                
                enviados = 0
                errores = 0
                saltados = 0
                
                for estudiante in estudiantes_activos:
                    # ✅ VALIDACIÓN: Debe tener curso y fecha_fin
                    if not estudiante.curso or not estudiante.fecha_fin:
                        saltados += 1
                        continue
                    
                    # ✅ VALIDACIÓN: Debe tener al menos 1 mensualidad pagada
                    if estudiante.mensualidades_canceladas == 0:
                        saltados += 1
                        continue
                    
                    # Calcular días para vencer
                    dias_para_vencer = (estudiante.fecha_fin - datetime.now()).days
                    
                    # 🎯 CONDICIÓN: Solo si vence EXACTAMENTE en 3 días
                    if dias_para_vencer == 3:
                        if self._enviar_aviso_seguro(estudiante, dias_para_vencer):
                            enviados += 1
                            self.logger.info(
                                f"   ✅ Aviso preventivo: {estudiante.nombre_completo} "
                                f"({estudiante.email}) - Vence: {estudiante.fecha_fin.strftime('%d/%m/%Y')}"
                            )
                        else:
                            errores += 1
                
                # Resumen
                self.logger.info("=" * 70)
                self.logger.info(f"📊 RESUMEN AVISOS PREVENTIVOS:")
                self.logger.info(f"   ✅ Enviados: {enviados}")
                self.logger.info(f"   ❌ Errores: {errores}")
                self.logger.info(f"   ⏭️  Saltados: {saltados}")
                self.logger.info("=" * 70)
                
            except Exception as e:
                self.logger.error(f"❌ Error en avisos preventivos: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
    
    def enviar_recordatorios_urgentes(self):
        """
        ⚠️ TAREA 2: Recordatorios urgentes (1 día después de vencer)
        
        ESTRATEGIA:
        - Solo a estudiantes vencidos hace EXACTAMENTE 1 día
        - Tono urgente pero amable
        - No es molesto porque solo se envía UNA vez
        """
        with self.app.app_context():
            try:
                self.logger.info("=" * 70)
                self.logger.info("⚠️ INICIANDO RECORDATORIOS URGENTES (1 día vencido)")
                self.logger.info("=" * 70)
                
                estudiantes_activos = self.Cliente.query.filter_by(activo=True).all()
                
                enviados = 0
                errores = 0
                saltados = 0
                
                for estudiante in estudiantes_activos:
                    # Validaciones
                    if not estudiante.curso or not estudiante.fecha_fin:
                        saltados += 1
                        continue
                    
                    if estudiante.mensualidades_canceladas == 0:
                        saltados += 1
                        continue
                    
                    # Calcular días vencido (negativo = vencido)
                    dias_para_vencer = (estudiante.fecha_fin - datetime.now()).days
                    
                    # 🎯 CONDICIÓN: Solo si venció EXACTAMENTE hace 1 día
                    if dias_para_vencer == -1:
                        dias_vencido = abs(dias_para_vencer)
                        
                        if self._enviar_recordatorio_seguro(estudiante, dias_vencido):
                            enviados += 1
                            self.logger.info(
                                f"   ⚠️ Recordatorio urgente: {estudiante.nombre_completo} "
                                f"({estudiante.email}) - Vencido hace {dias_vencido} día"
                            )
                        else:
                            errores += 1
                
                # Resumen
                self.logger.info("=" * 70)
                self.logger.info(f"📊 RESUMEN RECORDATORIOS URGENTES:")
                self.logger.info(f"   ✅ Enviados: {enviados}")
                self.logger.info(f"   ❌ Errores: {errores}")
                self.logger.info(f"   ⏭️  Saltados: {saltados}")
                self.logger.info("=" * 70)
                
            except Exception as e:
                self.logger.error(f"❌ Error en recordatorios urgentes: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
    
    def enviar_recordatorios_criticos(self):
        """
        🚨 TAREA 3: Recordatorios críticos (7+ días vencidos)
        
        ESTRATEGIA:
        - Solo cada 7 días (para estudiantes muy vencidos)
        - Envía solo si: dias_vencido % 7 == 0 (múltiplo de 7)
        - Ejemplo: envía a los 7, 14, 21, 28 días... pero NO todos los días
        """
        with self.app.app_context():
            try:
                self.logger.info("=" * 70)
                self.logger.info("🚨 INICIANDO RECORDATORIOS CRÍTICOS (7+ días vencidos)")
                self.logger.info("=" * 70)
                
                estudiantes_activos = self.Cliente.query.filter_by(activo=True).all()
                
                enviados = 0
                errores = 0
                saltados = 0
                
                for estudiante in estudiantes_activos:
                    # Validaciones
                    if not estudiante.curso or not estudiante.fecha_fin:
                        saltados += 1
                        continue
                    
                    if estudiante.mensualidades_canceladas == 0:
                        saltados += 1
                        continue
                    
                    # Calcular días vencido
                    dias_para_vencer = (estudiante.fecha_fin - datetime.now()).days
                    
                    # 🎯 CONDICIÓN: Vencido 7+ días Y que sea múltiplo de 7
                    if dias_para_vencer < -6:  # Vencido hace 7 o más días
                        dias_vencido = abs(dias_para_vencer)
                        
                        # Solo enviar si es múltiplo de 7 (cada semana)
                        if dias_vencido % 7 == 0:
                            if self._enviar_recordatorio_seguro(estudiante, dias_vencido):
                                enviados += 1
                                self.logger.info(
                                    f"   🚨 Recordatorio crítico: {estudiante.nombre_completo} "
                                    f"({estudiante.email}) - Vencido hace {dias_vencido} días"
                                )
                            else:
                                errores += 1
                
                # Resumen
                self.logger.info("=" * 70)
                self.logger.info(f"📊 RESUMEN RECORDATORIOS CRÍTICOS:")
                self.logger.info(f"   ✅ Enviados: {enviados}")
                self.logger.info(f"   ❌ Errores: {errores}")
                self.logger.info(f"   ⏭️  Saltados: {saltados}")
                self.logger.info("=" * 70)
                
            except Exception as e:
                self.logger.error(f"❌ Error en recordatorios críticos: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
    
    def _enviar_aviso_seguro(self, estudiante, dias_para_vencer):
        """
        Envía aviso preventivo (3 días antes) con manejo de errores
        
        Returns:
            bool: True si se envió correctamente
        """
        try:
            if not estudiante.email:
                self.logger.warning(f"⚠️ {estudiante.nombre_completo} sin email")
                return False
            
            # Enviar aviso preventivo
            if self.enviar_aviso_vencimiento(estudiante, dias_para_vencer):
                return True
            else:
                self.logger.error(f"❌ Error enviando aviso a {estudiante.email}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Excepción enviando aviso a {estudiante.email}: {e}")
            return False
    
    def _enviar_recordatorio_seguro(self, estudiante, dias_vencido):
        """
        Envía recordatorio de pago (vencidos) con manejo de errores
        
        Returns:
            bool: True si se envió correctamente
        """
        try:
            if not estudiante.email:
                self.logger.warning(f"⚠️ {estudiante.nombre_completo} sin email")
                return False
            
            # Enviar recordatorio urgente
            if self.enviar_recordatorio_pago(estudiante, dias_vencido):
                return True
            else:
                self.logger.error(f"❌ Error enviando recordatorio a {estudiante.email}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Excepción enviando recordatorio a {estudiante.email}: {e}")
            return False
    
    def enviar_ahora(self):
        """
        Envía todos los recordatorios inmediatamente (para testing)
        """
        self.logger.info("=" * 70)
        self.logger.info("🚀 ENVÍO MANUAL DE RECORDATORIOS (TESTING)")
        self.logger.info("=" * 70)
        
        self.enviar_avisos_preventivos()
        self.enviar_recordatorios_urgentes()
        self.enviar_recordatorios_criticos()
        
        self.logger.info("=" * 70)
        self.logger.info("✅ ENVÍO MANUAL COMPLETADO")
        self.logger.info("=" * 70)
    
    def detener(self):
        """Detiene el scheduler limpiamente"""
        try:
            if self.scheduler.running:
                self.scheduler.shutdown()
                self.logger.info("⏹️ Scheduler detenido correctamente")
        except Exception as e:
            self.logger.error(f"❌ Error deteniendo scheduler: {e}")
    
    def obtener_estado(self):
        """
        Obtiene el estado actual del scheduler y próximas ejecuciones
        
        Returns:
            dict: Estado del scheduler
        """
        try:
            if not self.scheduler.running:
                return {
                    'activo': False,
                    'mensaje': 'Scheduler detenido'
                }
            
            jobs = self.scheduler.get_jobs()
            proximas_ejecuciones = []
            
            for job in jobs:
                proximas_ejecuciones.append({
                    'nombre': job.name,
                    'proxima_ejecucion': job.next_run_time.strftime('%d/%m/%Y %H:%M:%S') if job.next_run_time else 'N/A'
                })
            
            return {
                'activo': True,
                'mensaje': 'Scheduler funcionando correctamente',
                'proximas_ejecuciones': proximas_ejecuciones
            }
            
        except Exception as e:
            self.logger.error(f"❌ Error obteniendo estado: {e}")
            return {
                'activo': False,
                'mensaje': f'Error: {str(e)}'
            }


def init_reminder_scheduler(app, db, Cliente, enviar_aviso_vencimiento, enviar_recordatorio_pago=None):
    """
    Función de inicialización del scheduler
    
    Args:
        app: Flask app
        db: SQLAlchemy db
        Cliente: Modelo Cliente
        enviar_aviso_vencimiento: Función para avisos preventivos
        enviar_recordatorio_pago: Función para recordatorios urgentes (OPCIONAL)
    
    Returns:
        ReminderScheduler: Instancia del scheduler
    """
    # Si no se proporciona enviar_recordatorio_pago, intentar importarla
    if enviar_recordatorio_pago is None:
        try:
            from email_service import enviar_recordatorio_pago as recordatorio_func
            enviar_recordatorio_pago = recordatorio_func
            app.logger.info("✅ enviar_recordatorio_pago importada automáticamente")
        except ImportError:
            app.logger.warning("⚠️ No se pudo importar enviar_recordatorio_pago")
            # Usar enviar_aviso_vencimiento como fallback
            enviar_recordatorio_pago = enviar_aviso_vencimiento
    
    scheduler = ReminderScheduler(
        app, 
        db, 
        Cliente, 
        enviar_aviso_vencimiento,
        enviar_recordatorio_pago
    )
    
    if scheduler.iniciar():
        app.logger.info("✅ ReminderScheduler inicializado correctamente")
    else:
        app.logger.error("❌ Error inicializando ReminderScheduler")
    
    return scheduler