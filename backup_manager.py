# -*- coding: utf-8 -*-
"""
Sistema de Backup de Base de Datos
✅ COMPATIBLE CON SQLite (local) y PostgreSQL (Render)
"""

import os
import shutil
from datetime import datetime
from pathlib import Path


class BackupManager:
    def __init__(self, app, db_path=None):
        """
        Inicializa el gestor de backups
        
        Args:
            app: Instancia de Flask
            db_path: Ruta al archivo database.db (solo para SQLite)
        """
        self.app = app
        self.db_path = Path(db_path) if db_path else None
        self.backup_dir = Path(app.config.get('BACKUP_DIR', 'backups'))
        self.logger = app.logger
        
        # Detectar tipo de base de datos
        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
        self.is_sqlite = 'sqlite:///' in db_uri
        self.is_postgres = 'postgresql://' in db_uri or 'postgres://' in db_uri
        
        # Crear directorio de backups
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"📦 BackupManager inicializado")
        self.logger.info(f"   - SQLite: {self.is_sqlite}")
        self.logger.info(f"   - PostgreSQL: {self.is_postgres}")
        
        if self.is_sqlite and self.db_path:
            self.logger.info(f"   - DB Path: {self.db_path}")
        elif self.is_postgres:
            self.logger.info(f"   - PostgreSQL detectado (backups deshabilitados)")
    
    def _backups_disponibles(self):
        """Verifica si los backups están disponibles"""
        if not self.is_sqlite:
            return False, "⚠️ Los backups solo funcionan con SQLite"

        return True, "✅ Backups disponibles"
    
    def obtener_ruta_bd(self):
        """
        Obtiene la ruta completa de la base de datos (solo SQLite)
        
        Returns:
            str: Ruta completa al archivo database.db o None
        """
        if not self.is_sqlite:
            self.logger.warning("⚠️ No es SQLite, no hay archivo físico")
            return None
        
        # Intentar varias ubicaciones comunes
        rutas_posibles = [
            self.db_path,
            Path('instance') / 'database.db',
            Path('database.db'),
        ]
        
        # Filtrar None y probar cada ubicación
        for ruta in filter(None, rutas_posibles):
            if ruta.exists():
                self.logger.info(f"✅ Base de datos encontrada en: {ruta}")
                return str(ruta)
        
        # Intentar obtener desde config
        db_uri = self.app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if 'sqlite:///' in db_uri:
            ruta_config = db_uri.replace('sqlite:///', '')
            ruta_path = Path(ruta_config)
            
            if ruta_path.exists():
                self.logger.info(f"✅ Base de datos encontrada desde config: {ruta_path}")
                return str(ruta_path)
        
        self.logger.error(f"❌ No se encontró la base de datos")
        return None
    
    def obtener_info_bd(self):
        """
        Obtiene información de la base de datos
        
        Returns:
            dict: Información de la BD o None
        """
        # Si es PostgreSQL, retornar info básica
        if self.is_postgres:
            return {
                'existe': True,
                'tipo': 'PostgreSQL',
                'ruta': 'Render PostgreSQL',
                'nombre': 'PostgreSQL Database',
                'tamano_bytes': None,
                'tamano_mb': 'N/A',
                'fecha_modificacion': None,
                'fecha_modificacion_str': 'N/A',
                'backups_disponibles': False
            }
        
        # Para SQLite, obtener info del archivo
        if not self.is_sqlite:
            return None
        
        ruta_bd = self.obtener_ruta_bd()
        
        if not ruta_bd:
            self.logger.error("❌ No se pudo obtener info: BD no encontrada")
            return None
        
        ruta_bd_path = Path(ruta_bd)
        
        if not ruta_bd_path.exists():
            self.logger.error(f"❌ Archivo no existe: {ruta_bd_path}")
            return None
        
        try:
            stats = ruta_bd_path.stat()
            
            info = {
                'existe': True,
                'tipo': 'SQLite',
                'ruta': str(ruta_bd_path),
                'nombre': ruta_bd_path.name,
                'tamano_bytes': stats.st_size,
                'tamano_mb': round(stats.st_size / (1024 * 1024), 2),
                'fecha_modificacion': datetime.fromtimestamp(stats.st_mtime),
                'fecha_modificacion_str': datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                'backups_disponibles': True
            }
            
            self.logger.info(f"📊 Info BD: {info['nombre']} - {info['tamano_mb']} MB")
            return info
            
        except Exception as e:
            self.logger.error(f"❌ Error obteniendo stats: {e}")
            return None
    
    def crear_backup_temporal(self, nombre_personalizado=None):
        """
        Crea una copia temporal de la BD (solo SQLite)
        
        Args:
            nombre_personalizado: Nombre opcional para el backup
            
        Returns:
            tuple: (success, mensaje, ruta_backup)
        """
        disponible, mensaje = self._backups_disponibles()
        if not disponible:
            return False, mensaje, None
        
        try:
            ruta_bd = self.obtener_ruta_bd()
            
            if not ruta_bd:
                return False, "❌ No existe la base de datos", None
            
            # Generar nombre para el backup
            if nombre_personalizado:
                backup_filename = nombre_personalizado
            else:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_filename = f"database_backup_{timestamp}.db"
            
            backup_path = self.backup_dir / backup_filename
            
            # Copiar la base de datos
            self.logger.info(f"📋 Copiando {ruta_bd} → {backup_path}")
            shutil.copy2(ruta_bd, backup_path)
            
            self.logger.info(f"✅ Backup temporal creado: {backup_filename}")
            
            return True, f"✅ Backup creado: {backup_filename}", str(backup_path)
            
        except Exception as e:
            self.logger.error(f"❌ Error creando backup: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False, f"❌ Error: {str(e)}", None
    
    def restaurar_desde_archivo(self, archivo_subido):
        """
        Restaura la base de datos desde un archivo (solo SQLite)
        
        Args:
            archivo_subido: Archivo FileStorage de Flask
            
        Returns:
            tuple: (success, mensaje)
        """
        disponible, mensaje = self._backups_disponibles()
        if not disponible:
            return False, mensaje
        
        try:
            ruta_bd = self.obtener_ruta_bd()
            
            if not ruta_bd:
                # Si no existe, usar instance/database.db por defecto
                ruta_bd = 'instance/database.db'
                self.logger.warning(f"⚠️ BD no encontrada, usando ubicación por defecto: {ruta_bd}")
            
            ruta_bd_path = Path(ruta_bd)
            
            # Asegurar que el directorio padre existe
            ruta_bd_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Crear backup de seguridad de la BD actual (si existe)
            if ruta_bd_path.exists():
                safety_backup = self.backup_dir / f"pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                shutil.copy2(ruta_bd_path, safety_backup)
                self.logger.info(f"🔒 Backup de seguridad: {safety_backup.name}")
            
            # Guardar el archivo subido como nueva BD
            self.logger.info(f"📥 Guardando archivo subido en: {ruta_bd_path}")
            archivo_subido.save(str(ruta_bd_path))
            
            self.logger.info("✅ Base de datos restaurada desde archivo subido")
            return True, "✅ Base de datos restaurada exitosamente"
            
        except Exception as e:
            self.logger.error(f"❌ Error restaurando BD: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False, f"❌ Error: {str(e)}"
    
    def limpiar_backups_temporales(self):
        """Elimina backups temporales antiguos (más de 1 hora)"""
        if not self.is_sqlite:
            return
        
        try:
            hora_actual = datetime.now().timestamp()
            eliminados = 0
            
            for backup in self.backup_dir.glob("database_backup_*.db"):
                # Si el backup tiene más de 1 hora, eliminarlo
                if hora_actual - backup.stat().st_mtime > 3600:
                    backup.unlink()
                    self.logger.info(f"🗑️ Backup temporal eliminado: {backup.name}")
                    eliminados += 1
            
            if eliminados > 0:
                self.logger.info(f"🧹 Total de backups limpiados: {eliminados}")
                    
        except Exception as e:
            self.logger.error(f"⚠️ Error limpiando backups: {e}")