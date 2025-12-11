#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sistema de Licencias con Base de Datos Oculta y Protección Avanzada
✅ Binding único a hardware
✅ DEMO: 30 minutos con BD SQLite oculta
✅ Contador de intentos de manipulación
✅ Protección contra eliminación de archivos
✅ Aplica datos de empresa automáticamente
"""

import os
import json
import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import base64
import platform
import uuid
import subprocess

try:
    from subprocess import check_output
except ImportError:
    check_output = subprocess.check_output

class LicenseManager:
    def __init__(self, license_file="license.json"):
        self.base_dir = Path(__file__).parent.resolve()
        self.license_file = self.base_dir / license_file
        self.empresa_config_file = self.base_dir / "empresa_config.json"
        
        # 🆕 BASE DE DATOS OCULTA EN CARPETA DEL SISTEMA
        if platform.system() == "Windows":
            appdata = os.environ.get('LOCALAPPDATA', os.environ.get('APPDATA', '.'))
            self.db_dir = Path(appdata) / ".sysconfig" / "app_state"
        else:
            home = Path.home()
            self.db_dir = home / ".config" / ".sysconfig" / "app_state"
        
        # Crear directorio oculto si no existe
        self.db_dir.mkdir(parents=True, exist_ok=True)
        
        # 🆕 MÚLTIPLES ARCHIVOS DE BASE DE DATOS (redundancia)
        self.db_file = self.db_dir / ".state.db"
        self.db_backup_1 = self.db_dir / ".demo_session"
        self.db_backup_2 = self.db_dir / ".sys_cache"
        
        self.secret_key = "POS_SYSTEM_2025_SECRET_KEY_XYZ"
        self.demo_duracion_minutos = 30
        self.max_intentos = 3  # Máximo de intentos de reseteo
        
        # Inicializar base de datos
        self._inicializar_db()
        self._proteger_carpeta()
    
    def _proteger_carpeta(self):
        """🆕 Protege la carpeta contra eliminación"""
        try:
            if platform.system() == "Windows":
                # Hacer carpeta oculta en Windows
                os.system(f'attrib +h "{self.db_dir}"')
            # En Linux/Mac las carpetas con . ya son ocultas
        except Exception as e:
            print(f"⚠️ No se pudo proteger carpeta: {e}")
    
    def _inicializar_db(self):
        """🆕 Crea las tablas necesarias en la BD"""
        try:
            conn = sqlite3.connect(str(self.db_file))
            cursor = conn.cursor()
            
            # Tabla para sesiones DEMO
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS demo_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hardware_id TEXT NOT NULL UNIQUE,
                    inicio TIMESTAMP NOT NULL,
                    expiracion TIMESTAMP NOT NULL,
                    duracion_minutos INTEGER NOT NULL,
                    checksum TEXT NOT NULL,
                    intentos_reseteo INTEGER DEFAULT 0,
                    bloqueado INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Tabla para registro de eventos (auditoría)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS eventos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo TEXT NOT NULL,
                    descripcion TEXT,
                    hardware_id TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            conn.close()
            
            # Crear backups de la BD
            self._crear_backups_db()
            
        except Exception as e:
            print(f"⚠️ Error inicializando BD: {e}")
    
    def _crear_backups_db(self):
        """🆕 Crea copias de seguridad de la BD"""
        try:
            import shutil
            if self.db_file.exists():
                shutil.copy2(self.db_file, self.db_backup_1)
                shutil.copy2(self.db_file, self.db_backup_2)
        except Exception as e:
            print(f"⚠️ Error creando backups: {e}")
    
    def _restaurar_db_desde_backup(self):
        """🆕 Restaura BD desde backup si fue eliminada"""
        backups = [self.db_backup_1, self.db_backup_2]
        
        for backup in backups:
            if backup.exists():
                try:
                    import shutil
                    shutil.copy2(backup, self.db_file)
                    self._registrar_evento("restauracion_db", f"BD restaurada desde {backup.name}")
                    return True
                except:
                    continue
        
        return False
    
    def _registrar_evento(self, tipo, descripcion, hardware_id=None):
        """🆕 Registra eventos en la BD"""
        try:
            conn = sqlite3.connect(str(self.db_file))
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO eventos (tipo, descripcion, hardware_id)
                VALUES (?, ?, ?)
            ''', (tipo, descripcion, hardware_id or self.generar_hardware_id()))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"⚠️ Error registrando evento: {e}")
    
    def generar_hardware_id(self):
        """Genera un ID ÚNICO e INVIOLABLE del hardware"""
        try:
            identificadores = []
            
            mac = uuid.getnode()
            identificadores.append(str(mac))
            identificadores.append(platform.node())
            identificadores.append(platform.system())
            identificadores.append(platform.version())
            identificadores.append(platform.machine())
            
            try:
                if platform.system() == "Windows":
                    result = subprocess.check_output("wmic csproduct get uuid", shell=True)
                    uuid_sys = result.decode().split('\n')[1].strip()
                    identificadores.append(uuid_sys)
                elif platform.system() == "Linux":
                    with open('/etc/machine-id', 'r') as f:
                        identificadores.append(f.read().strip())
                elif platform.system() == "Darwin":
                    result = subprocess.check_output("ioreg -rd1 -c IOPlatformExpertDevice | grep IOPlatformUUID", shell=True)
                    uuid_sys = result.decode().split('"')[3]
                    identificadores.append(uuid_sys)
            except:
                pass
            
            identificadores.append(platform.processor())
            
            hardware_string = "-".join(identificadores)
            hardware_id = hashlib.sha256(hardware_string.encode()).hexdigest()
            
            return hardware_id
            
        except Exception as e:
            fallback = f"{uuid.getnode()}-{platform.node()}-{platform.system()}"
            return hashlib.sha256(fallback.encode()).hexdigest()
    
    def iniciar_demo(self):
        """Inicia una sesión DEMO de 30 minutos en BD oculta"""
        try:
            # Verificar si la BD fue eliminada y restaurar
            if not self.db_file.exists():
                if not self._restaurar_db_desde_backup():
                    self._inicializar_db()
            
            hardware_id = self.generar_hardware_id()
            ahora = datetime.now()
            expiracion = ahora + timedelta(minutes=self.demo_duracion_minutos)
            checksum = hashlib.sha256(f"{hardware_id}-{self.secret_key}".encode()).hexdigest()[:16]
            
            conn = sqlite3.connect(str(self.db_file))
            cursor = conn.cursor()
            
            # Insertar o actualizar sesión DEMO
            cursor.execute('''
                INSERT OR REPLACE INTO demo_sessions 
                (hardware_id, inicio, expiracion, duracion_minutos, checksum, intentos_reseteo, bloqueado)
                VALUES (?, ?, ?, ?, ?, 0, 0)
            ''', (hardware_id, ahora, expiracion, self.demo_duracion_minutos, checksum))
            
            conn.commit()
            conn.close()
            
            # Crear backups
            self._crear_backups_db()
            self._registrar_evento("demo_iniciado", f"DEMO iniciado - {self.demo_duracion_minutos} min")
            
            return True, f"✅ Modo DEMO iniciado - {self.demo_duracion_minutos} minutos disponibles"
        except Exception as e:
            return False, f"❌ Error iniciando DEMO: {str(e)}"
    
    def verificar_demo(self):
        """Verifica el estado de la sesión DEMO desde BD"""
        try:
            # Verificar si BD existe, sino restaurar
            if not self.db_file.exists():
                self._registrar_evento("intento_eliminacion", "🚨 Intento de eliminar BD detectado")
                
                if self._restaurar_db_desde_backup():
                    # BD restaurada, verificar intentos
                    return self._verificar_intentos_reseteo()
                else:
                    # No hay backups, iniciar nuevo DEMO
                    success, msg = self.iniciar_demo()
                    if success:
                        return True, self.demo_duracion_minutos, msg
                    return False, 0, msg
            
            hardware_id = self.generar_hardware_id()
            
            conn = sqlite3.connect(str(self.db_file))
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT inicio, expiracion, duracion_minutos, checksum, intentos_reseteo, bloqueado
                FROM demo_sessions
                WHERE hardware_id = ?
            ''', (hardware_id,))
            
            resultado = cursor.fetchone()
            conn.close()
            
            if not resultado:
                # No hay sesión, iniciar nueva
                success, msg = self.iniciar_demo()
                if success:
                    return True, self.demo_duracion_minutos, msg
                return False, 0, msg
            
            inicio_str, expiracion_str, duracion, checksum_guardado, intentos, bloqueado = resultado
            
            # Verificar si está bloqueado por intentos
            if bloqueado == 1:
                return False, 0, f"🚨 SISTEMA BLOQUEADO - Demasiados intentos de manipulación ({intentos}/{self.max_intentos})"
            
            # Verificar checksum
            checksum_calculado = hashlib.sha256(f"{hardware_id}-{self.secret_key}".encode()).hexdigest()[:16]
            
            if checksum_guardado != checksum_calculado:
                self._registrar_evento("manipulacion", "🚨 Checksum inválido")
                return False, 0, "🚨 DEMO BLOQUEADO - Datos manipulados"
            
            # Verificar expiración
            expiracion = datetime.fromisoformat(expiracion_str)
            ahora = datetime.now()
            
            if ahora > expiracion:
                return False, 0, "⏰ DEMO EXPIRADO - Los 30 minutos han finalizado"
            
            tiempo_restante = expiracion - ahora
            minutos_restantes = int(tiempo_restante.total_seconds() / 60)
            
            return True, minutos_restantes, f"🔧 MODO DEMO - {minutos_restantes} minutos restantes"
            
        except Exception as e:
            print(f"⚠️ Error verificando DEMO: {e}")
            return False, 0, f"❌ Error verificando DEMO: {str(e)}"
    
    def _verificar_intentos_reseteo(self):
        """🆕 Verifica y actualiza contador de intentos de reseteo"""
        try:
            hardware_id = self.generar_hardware_id()
            
            conn = sqlite3.connect(str(self.db_file))
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT intentos_reseteo, bloqueado
                FROM demo_sessions
                WHERE hardware_id = ?
            ''', (hardware_id,))
            
            resultado = cursor.fetchone()
            
            if resultado:
                intentos, bloqueado = resultado
                intentos += 1
                
                if intentos >= self.max_intentos:
                    # BLOQUEAR permanentemente
                    cursor.execute('''
                        UPDATE demo_sessions
                        SET intentos_reseteo = ?, bloqueado = 1
                        WHERE hardware_id = ?
                    ''', (intentos, hardware_id))
                    conn.commit()
                    conn.close()
                    
                    self._registrar_evento("bloqueo_permanente", f"🚨 Sistema bloqueado tras {intentos} intentos")
                    self._crear_backups_db()
                    
                    return False, 0, f"🚨 SISTEMA BLOQUEADO PERMANENTEMENTE\n\nSe detectaron {intentos} intentos de manipulación.\nContacte al administrador para desbloquear."
                else:
                    # Incrementar contador
                    cursor.execute('''
                        UPDATE demo_sessions
                        SET intentos_reseteo = ?
                        WHERE hardware_id = ?
                    ''', (intentos, hardware_id))
                    conn.commit()
                    conn.close()
                    
                    self._registrar_evento("intento_reseteo", f"Intento {intentos}/{self.max_intentos}")
                    self._crear_backups_db()
                    
                    return False, 0, f"⚠️ INTENTO DE MANIPULACIÓN DETECTADO\n\nIntento {intentos} de {self.max_intentos}\n{self.max_intentos - intentos} intentos restantes antes del bloqueo permanente."
            
            conn.close()
            return False, 0, "Error verificando intentos"
            
        except Exception as e:
            print(f"⚠️ Error verificando intentos: {e}")
            return False, 0, "Error del sistema"
    
    def validar_licencia(self, license_key, license_data_encoded):
        """Valida estructura de licencia"""
        try:
            if not license_key or not license_data_encoded:
                return False, "❌ Debes proporcionar ambos campos", None
            
            try:
                license_json = base64.b64decode(license_data_encoded.encode()).decode()
                license_data = json.loads(license_json)
            except:
                return False, "❌ Datos de licencia inválidos o corruptos", None
            
            required_fields = ["token", "cliente_nombre", "cliente_email", "fecha_expiracion"]
            for field in required_fields:
                if field not in license_data:
                    return False, f"❌ Licencia inválida: falta campo '{field}'", None
            
            token = license_data.get("token", "")
            signature_data = f"{token}-{self.secret_key}"
            expected_signature = hashlib.sha256(signature_data.encode()).hexdigest()[:16]
            
            parts = license_key.split("-")
            if len(parts) != 5 or parts[0] != "POS":
                return False, "❌ Formato de licencia inválido", None
            
            provided_signature = (parts[1] + parts[2] + parts[3] + parts[4]).lower()
            
            if provided_signature != expected_signature:
                return False, "❌ Licencia inválida o manipulada", None
            
            expiracion_str = license_data.get("fecha_expiracion")
            try:
                expiracion = datetime.strptime(expiracion_str, "%Y-%m-%d %H:%M:%S")
            except:
                try:
                    expiracion = datetime.strptime(expiracion_str, "%Y-%m-%d")
                except:
                    return False, "❌ Formato de fecha inválido", None
            
            if datetime.now() > expiracion:
                dias_vencida = (datetime.now() - expiracion).days
                return False, f"❌ Licencia expirada hace {dias_vencida} días", None
            
            dias_restantes = (expiracion - datetime.now()).days
            
            return True, f"✅ Licencia válida ({dias_restantes} días restantes)", license_data
            
        except Exception as e:
            return False, f"❌ Error validando licencia: {str(e)}", None
    
    def aplicar_datos_empresa(self, datos_empresa):
        """Aplica los datos de empresa desde la licencia"""
        try:
            if not datos_empresa:
                return False, "No hay datos de empresa en la licencia"
            
            with open(self.empresa_config_file, 'w', encoding='utf-8') as f:
                json.dump(datos_empresa, f, indent=2, ensure_ascii=False)
            
            return True, "✅ Datos de empresa configurados automáticamente"
            
        except Exception as e:
            return False, f"Error guardando datos de empresa: {str(e)}"
    
    def obtener_datos_empresa(self):
        """Obtiene los datos de empresa guardados"""
        try:
            if self.empresa_config_file.exists():
                with open(self.empresa_config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return None
        except Exception as e:
            print(f"Error leyendo datos empresa: {e}")
            return None
    
    def guardar_licencia_local(self, license_key, license_data_encoded):
        """Guarda licencia con BINDING PERMANENTE y aplica datos de empresa"""
        valida, mensaje, data = self.validar_licencia(license_key, license_data_encoded)
        
        if not valida:
            return False, mensaje
        
        hardware_id_actual = self.generar_hardware_id()
        
        if "hardware_id" in data and data.get("estado") == "activada":
            hardware_id_licencia = data.get("hardware_id")
            
            if hardware_id_licencia != hardware_id_actual:
                return False, "🔒 LICENCIA YA ACTIVADA EN OTRO COMPUTADOR\n\nEsta licencia ya fue activada en otra máquina.\nCada licencia solo puede usarse en UN computador."
        
        try:
            data["hardware_id"] = hardware_id_actual
            data["estado"] = "activada"
            data["fecha_activacion"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            mensaje_empresa = ""
            if "empresa" in data:
                success_emp, msg_emp = self.aplicar_datos_empresa(data["empresa"])
                if success_emp:
                    mensaje_empresa = "\n\n🏢 Datos de empresa configurados automáticamente:\n"
                    mensaje_empresa += f"   • Razón Social: {data['empresa'].get('razon_social', '')}\n"
                    mensaje_empresa += f"   • RUC: {data['empresa'].get('ruc', '')}\n"
                    mensaje_empresa += "   • Puedes modificarlos desde Configuración"
            
            license_json_updated = json.dumps(data)
            license_data_encoded_updated = base64.b64encode(license_json_updated.encode()).decode()
            
            license_info = {
                "license_key": license_key,
                "license_data": license_data_encoded_updated,
                "hardware_id": hardware_id_actual,
                "activacion_fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "cliente_nombre": data.get("cliente_nombre"),
                "cliente_email": data.get("cliente_email"),
                "fecha_expiracion": data.get("fecha_expiracion"),
                "version": "2.2",
                "checksum": self._generar_checksum(license_key, hardware_id_actual),
                "tiene_datos_empresa": "empresa" in data
            }
            
            with open(self.license_file, 'w', encoding='utf-8') as f:
                json.dump(license_info, f, indent=2)
            
            # 🆕 Limpiar DEMO de la BD al activar licencia
            self._limpiar_demo_db()
            self._registrar_evento("licencia_activada", f"Licencia activada: {data.get('cliente_nombre')}")
            
            mensaje_final = "✅ Licencia activada correctamente\n\n🔒 Esta licencia está vinculada PERMANENTEMENTE a este computador"
            mensaje_final += mensaje_empresa
            
            return True, mensaje_final
            
        except Exception as e:
            return False, f"❌ Error guardando licencia: {str(e)}"
    
    def _limpiar_demo_db(self):
        """🆕 Limpia registros DEMO de la BD al activar licencia"""
        try:
            hardware_id = self.generar_hardware_id()
            conn = sqlite3.connect(str(self.db_file))
            cursor = conn.cursor()
            cursor.execute('DELETE FROM demo_sessions WHERE hardware_id = ?', (hardware_id,))
            conn.commit()
            conn.close()
            self._crear_backups_db()
        except Exception as e:
            print(f"⚠️ Error limpiando DEMO: {e}")
    
    def _generar_checksum(self, license_key, hardware_id):
        """Genera checksum para verificar integridad"""
        data = f"{license_key}-{hardware_id}-{self.secret_key}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]
    
    def verificar_licencia_activa(self):
        """Verifica estado del sistema - DEMO o Licencia"""
        if not self.license_file.exists():
            es_valido, minutos, mensaje = self.verificar_demo()
            
            if es_valido:
                return True, mensaje, {
                    "minutos_restantes": minutos,
                    "bloqueado": False
                }
            else:
                return True, mensaje, {
                    "bloqueado": True,
                    "minutos_restantes": 0
                }
        
        try:
            with open(self.license_file, 'r', encoding='utf-8') as f:
                license_info = json.load(f)
            
            license_key = license_info.get("license_key")
            license_data = license_info.get("license_data")
            hardware_id_guardado = license_info.get("hardware_id")
            checksum_guardado = license_info.get("checksum")
            
            if not all([license_key, license_data, hardware_id_guardado, checksum_guardado]):
                self.license_file.unlink()
                return self.verificar_licencia_activa()
            
            hardware_id_actual = self.generar_hardware_id()
            
            if hardware_id_guardado != hardware_id_actual:
                self._bloquear_licencia()
                self._registrar_evento("violacion_seguridad", "🚨 Licencia copiada a otro PC")
                return True, "🚨 CARPETA COPIADA A OTRO PC - DETECTADO\n\n❌ Esta carpeta fue copiada desde otro computador.\n🔒 Licencia bloqueada permanentemente.", {
                    "bloqueado": True
                }
            
            checksum_calculado = self._generar_checksum(license_key, hardware_id_actual)
            
            if checksum_guardado != checksum_calculado:
                self._bloquear_licencia()
                self._registrar_evento("manipulacion", "🚨 Checksum de licencia inválido")
                return True, "🚨 MANIPULACIÓN DETECTADA - Archivo alterado", {
                    "bloqueado": True
                }
            
            valida, mensaje, data = self.validar_licencia(license_key, license_data)
            
            if valida:
                cliente = data.get("cliente_nombre", "Cliente")
                expiracion = data.get("fecha_expiracion", "N/A")
                email = data.get("cliente_email", "")
                
                try:
                    exp_date = datetime.strptime(expiracion, "%Y-%m-%d %H:%M:%S")
                except:
                    try:
                        exp_date = datetime.strptime(expiracion, "%Y-%m-%d")
                    except:
                        exp_date = datetime.now() + timedelta(days=1)
                
                dias_restantes = max(0, (exp_date - datetime.now()).days)
                
                return False, f"📄 LICENCIA ACTIVA - Cliente: {cliente} ({dias_restantes} días restantes)", {
                    "bloqueado": False,
                    "cliente_nombre": cliente,
                    "cliente_email": email,
                    "fecha_expiracion": expiracion,
                    "dias_restantes": dias_restantes
                }
            else:
                self.license_file.unlink()
                return self.verificar_licencia_activa()
                
        except Exception as e:
            print(f"⚠️ Error verificando licencia: {e}")
            return True, f"⚠️ Error verificando licencia", {
                "bloqueado": False
            }
    
    def _bloquear_licencia(self):
        """Bloquea la licencia por violación de seguridad"""
        try:
            if self.license_file.exists():
                blocked_file = self.license_file.parent / f"{self.license_file.stem}.blocked"
                self.license_file.rename(blocked_file)
        except:
            pass
    
    def eliminar_licencia(self):
        """Elimina la licencia local"""
        if self.license_file.exists():
            try:
                self.license_file.unlink()
                self._registrar_evento("licencia_eliminada", "Licencia eliminada manualmente")
                return True, "✅ Licencia eliminada - Volviendo a MODO DEMO"
            except Exception as e:
                return False, f"❌ Error eliminando licencia: {str(e)}"
        return False, "⚠️ No hay licencia para eliminar"
    
    def obtener_info_licencia(self):
        """Obtiene información de la licencia actual"""
        es_demo, mensaje, info = self.verificar_licencia_activa()
        datos_empresa = self.obtener_datos_empresa()
        
        return {
            "es_demo": es_demo,
            "mensaje": mensaje,
            "info": info or {},
            "datos_empresa": datos_empresa
        }


# Instancia global
license_manager = LicenseManager()