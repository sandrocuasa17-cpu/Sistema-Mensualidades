# -*- coding: utf-8 -*-
"""
Servicio de Correo - VERSIÓN CORREGIDA
✅ Correcciones críticas para envío de correos
"""

from __future__ import annotations

from flask_mail import Mail, Message
from flask import current_app
from datetime import datetime
import traceback
import smtplib
import socket
import html as _html


# Inicializar Flask-Mail
mail = Mail()

# Variables globales para DB
_db = None
_Configuracion = None

def init_email_service(db, Configuracion):
    """Inicializa el servicio con dependencias"""
    global _db, _Configuracion
    _db = db
    _Configuracion = Configuracion
    print("✅ Email service inicializado con BD")
    return True


def _obtener_config_bd():
    """Obtiene configuración desde BD"""
    global _Configuracion

    if not _Configuracion:
        try:
            from models_extended import Configuracion as ConfigModel
            _Configuracion = ConfigModel
            current_app.logger.info("✅ Configuracion importado automáticamente")
        except Exception as e:
            current_app.logger.error(f"❌ No se pudo importar Configuracion: {e}")
            return None

    try:
        return {
            'mail_server': (_Configuracion.obtener('MAIL_SERVER') or '').strip(),
            'mail_port': (_Configuracion.obtener('MAIL_PORT') or '587').strip(),
            'mail_username': (_Configuracion.obtener('MAIL_USERNAME') or '').strip(),
            'mail_password': _Configuracion.obtener('MAIL_PASSWORD') or '',
            'mail_sender': (_Configuracion.obtener('MAIL_DEFAULT_SENDER') or '').strip(),
            'nombre_empresa': (_Configuracion.obtener('NOMBRE_EMPRESA') or '').strip(),
            'eslogan_empresa': (_Configuracion.obtener('ESLOGAN_EMPRESA') or '').strip(),
            'telefono_empresa': (_Configuracion.obtener('TELEFONO_EMPRESA') or '').strip(),
            'direccion_empresa': (_Configuracion.obtener('DIRECCION_EMPRESA') or '').strip(),
            'web_empresa': (_Configuracion.obtener('WEB_EMPRESA') or '').strip()
        }
    except Exception as e:
        current_app.logger.error(f"❌ Error obteniendo config: {e}")
        return None


def validar_smtp_manual(host, port, user, pwd):
    """
    ✅ CORREGIDO: Valida conexión SMTP con logs detallados
    Returns: tuple (bool, str) - (éxito, mensaje)
    """
    try:
        current_app.logger.info("=" * 70)
        current_app.logger.info("🔍 VALIDACIÓN SMTP INICIADA")
        current_app.logger.info("=" * 70)
        current_app.logger.info(f"📧 Servidor: {host}")
        current_app.logger.info(f"🔌 Puerto: {port}")
        current_app.logger.info(f"👤 Usuario: {user}")
        current_app.logger.info(f"🔑 Contraseña: {'*' * min(len(pwd), 16)} ({len(pwd)} caracteres)")

        # ✅ VALIDACIÓN: Datos obligatorios
        if not host:
            return False, "❌ Falta servidor SMTP"
        if not user:
            return False, "❌ Falta usuario SMTP"
        if not pwd:
            return False, "❌ Falta contraseña SMTP"

        # ✅ VALIDACIÓN: Puerto válido
        try:
            port = int(port)
        except (ValueError, TypeError):
            return False, f"❌ Puerto inválido: {port}"

        if port not in [25, 465, 587, 2525]:
            return False, f"⚠️ Puerto no estándar: {port}. Los puertos comunes son 25, 465, 587, 2525"

        use_ssl = (port == 465)
        use_tls = (port in [587, 25, 2525])

        current_app.logger.info(f"🔐 SSL: {use_ssl}")
        current_app.logger.info(f"🔐 TLS: {use_tls}")

        server = None

        try:
            current_app.logger.info("📡 PASO 1: Conectando al servidor...")

            if use_ssl:
                current_app.logger.info("   → Usando SMTP_SSL (puerto 465)...")
                import ssl
                context = ssl.create_default_context()
                server = smtplib.SMTP_SSL(host, port, timeout=15, context=context)
                current_app.logger.info("   ✅ Conexión SSL establecida")
            else:
                current_app.logger.info(f"   → Usando SMTP + STARTTLS (puerto {port})...")
                server = smtplib.SMTP(host, port, timeout=15)
                current_app.logger.info("   ✅ Conexión inicial establecida")

                server.ehlo()
                current_app.logger.info("   ✅ EHLO enviado")

                if use_tls:
                    server.starttls()
                    current_app.logger.info("   ✅ STARTTLS activado")

                    server.ehlo()
                    current_app.logger.info("   ✅ EHLO post-TLS enviado")

            current_app.logger.info("📡 PASO 2: Autenticando usuario...")
            server.login(user, pwd)
            current_app.logger.info("   ✅ AUTENTICACIÓN EXITOSA")

            server.quit()
            current_app.logger.info("📡 PASO 3: Conexión cerrada correctamente")

            current_app.logger.info("=" * 70)
            current_app.logger.info("🎉 VALIDACIÓN SMTP EXITOSA")
            current_app.logger.info("=" * 70)

            return True, "✅ Conexión SMTP exitosa - Correos listos"

        except smtplib.SMTPAuthenticationError as e:
            error_code = str(e)
            current_app.logger.error(f"❌ ERROR DE AUTENTICACIÓN: {error_code}")

            if "535" in error_code or "Username and Password not accepted" in error_code:
                return False, (
                    "❌ USUARIO O CONTRASEÑA INCORRECTOS\n\n"
                    "Si usas Gmail:\n"
                    "1. Ve a: https://myaccount.google.com/security\n"
                    "2. Activa 'Verificación en 2 pasos'\n"
                    "3. Genera una 'Contraseña de aplicación'\n"
                    "4. Usa esa contraseña (los 16 caracteres EXACTOS)\n\n"
                    f"Detalles técnicos: {error_code}"
                )

            return False, f"❌ Error de autenticación: {error_code}"

        except socket.gaierror as e:
            current_app.logger.error(f"❌ ERROR DE DNS: No se pudo resolver '{host}'")
            return False, f"❌ No se pudo conectar a '{host}'. Verifica el servidor SMTP."

        except socket.timeout:
            current_app.logger.error("❌ TIMEOUT: No responde en 15 segundos")
            return False, f"❌ Timeout: El servidor '{host}' no responde. Verifica firewall y puerto."

        except ConnectionRefusedError:
            current_app.logger.error(f"❌ CONEXIÓN RECHAZADA en puerto {port}")
            return False, f"❌ Conexión rechazada. Verifica que el puerto {port} esté abierto."

        except Exception as e:
            current_app.logger.error(f"❌ ERROR INESPERADO: {e}")
            current_app.logger.error(traceback.format_exc())
            return False, f"❌ Error inesperado: {str(e)}"

        finally:
            if server:
                try:
                    server.quit()
                except Exception:
                    pass

    except Exception as e:
        current_app.logger.error(f"❌ ERROR PREPARANDO CONEXIÓN: {e}")
        current_app.logger.error(traceback.format_exc())
        return False, f"❌ Error preparando conexión: {str(e)}"


def cargar_config_correo_desde_bd():
    """
    ✅ CORREGIDO: Carga y valida configuración SMTP
    Returns: bool - True si todo está OK
    """
    current_app.config['SMTP_LAST_ERROR'] = None

    try:
        current_app.logger.info("=" * 70)
        current_app.logger.info("📧 CARGANDO CONFIGURACIÓN DE CORREO")
        current_app.logger.info("=" * 70)

        config = _obtener_config_bd()

        if not config:
            current_app.config['ENABLE_EMAIL_NOTIFICATIONS'] = False
            current_app.config['SMTP_LAST_ERROR'] = "Error accediendo a BD"
            current_app.logger.error("❌ No se pudo obtener configuración de BD")
            return False

        # ✅ VALIDACIÓN: Datos mínimos requeridos
        if not config['nombre_empresa']:
            current_app.logger.error("❌ Falta NOMBRE_EMPRESA")
            current_app.config['ENABLE_EMAIL_NOTIFICATIONS'] = False
            current_app.config['SMTP_LAST_ERROR'] = "Falta nombre de empresa"
            return False

        if not config['mail_server']:
            current_app.logger.error("❌ Falta MAIL_SERVER")
            current_app.config['ENABLE_EMAIL_NOTIFICATIONS'] = False
            current_app.config['SMTP_LAST_ERROR'] = "Falta servidor SMTP"
            return False

        if not config['mail_username']:
            current_app.logger.error("❌ Falta MAIL_USERNAME")
            current_app.config['ENABLE_EMAIL_NOTIFICATIONS'] = False
            current_app.config['SMTP_LAST_ERROR'] = "Falta usuario (email)"
            return False

        if not config['mail_password']:
            current_app.logger.error("❌ Falta MAIL_PASSWORD")
            current_app.config['ENABLE_EMAIL_NOTIFICATIONS'] = False
            current_app.config['SMTP_LAST_ERROR'] = "Falta contraseña"
            return False

        # ✅ PUERTO: Validar y convertir
        try:
            port_int = int(config['mail_port'])
        except (ValueError, TypeError):
            current_app.logger.warning("⚠️ Puerto inválido, usando 587")
            port_int = 587

        # ✅ CONFIGURAR FLASK-MAIL
        current_app.config['MAIL_SERVER'] = config['mail_server']
        current_app.config['MAIL_PORT'] = port_int
        current_app.config['MAIL_USERNAME'] = config['mail_username']
        current_app.config['MAIL_PASSWORD'] = config['mail_password']

        mail_sender = config['mail_sender'] or config['mail_username']
        current_app.config['MAIL_DEFAULT_SENDER'] = f"{config['nombre_empresa']} <{mail_sender}>"

        use_ssl = (port_int == 465)
        current_app.config['MAIL_USE_SSL'] = use_ssl
        current_app.config['MAIL_USE_TLS'] = not use_ssl
        current_app.config['MAIL_DEBUG'] = True

        current_app.logger.info(f"📧 Servidor: {config['mail_server']}")
        current_app.logger.info(f"🔌 Puerto: {port_int}")
        current_app.logger.info(f"👤 Usuario: {config['mail_username']}")
        current_app.logger.info(f"🔑 Contraseña: {'*' * min(len(config['mail_password']), 16)}")
        current_app.logger.info(f"🔐 SSL: {use_ssl}")
        current_app.logger.info(f"🔐 TLS: {not use_ssl}")

        current_app.logger.info("=" * 70)
        current_app.logger.info("🔍 VALIDANDO SMTP...")
        current_app.logger.info("=" * 70)

        # ✅ VALIDAR SMTP
        ok, mensaje = validar_smtp_manual(
            config['mail_server'],
            port_int,
            config['mail_username'],
            config['mail_password']
        )

        if not ok:
            current_app.config['ENABLE_EMAIL_NOTIFICATIONS'] = False
            current_app.config['SMTP_LAST_ERROR'] = mensaje
            current_app.logger.error("❌ VALIDACIÓN SMTP FALLÓ")
            current_app.logger.error(f"   Motivo: {mensaje}")
            return False

        # ✅ REINICIALIZAR FLASK-MAIL CON NUEVA CONFIG
        try:
            mail.init_app(current_app)
            current_app.logger.info("📧 Flask-Mail reinicializado con nueva configuración")
        except Exception as e:
            current_app.logger.error(f"⚠️ Error reinicializando Flask-Mail: {e}")

        current_app.config['ENABLE_EMAIL_NOTIFICATIONS'] = True
        current_app.config['SMTP_LAST_ERROR'] = None
        current_app.logger.info("=" * 70)
        current_app.logger.info("✅ CONFIGURACIÓN COMPLETA Y SMTP VALIDADO")
        current_app.logger.info("=" * 70)
        return True

    except Exception as e:
        current_app.config['ENABLE_EMAIL_NOTIFICATIONS'] = False
        current_app.config['SMTP_LAST_ERROR'] = str(e)
        current_app.logger.error(f"❌ ERROR: {e}")
        current_app.logger.error(traceback.format_exc())
        return False


def obtener_personalizacion():
    """Obtiene información completa de la empresa"""
    try:
        config = _obtener_config_bd()

        if not config or not config['nombre_empresa']:
            current_app.logger.error("❌ NOMBRE_EMPRESA vacío")
            return None

        return {
            'nombre': config['nombre_empresa'],
            'eslogan': config['eslogan_empresa'],
            'telefono': config['telefono_empresa'],
            'direccion': config['direccion_empresa'],
            'web': config['web_empresa']
        }

    except Exception as e:
        current_app.logger.error(f"❌ Error obteniendo personalización: {e}")
        return None

# ==============================
# Continuación de email_service.py
# Helpers HTML y funciones de envío
# ==============================

def _esc(v) -> str:
    return _html.escape(str(v)) if v is not None else ''


def _fmt_date(dt, *, with_time=False) -> str:
    if not dt:
        return '—'
    try:
        if with_time:
            return dt.strftime('%d/%m/%Y %H:%M')
        return dt.strftime('%d/%m/%Y')
    except Exception:
        return str(dt)


def _fmt_money(v) -> str:
    try:
        return f"${float(v):.2f}"
    except Exception:
        return str(v) if v is not None else '—'


def _attach_logo_inline(msg: Message) -> None:
    """Adjunta el logo como imagen embebida (CID: logo). No falla si no existe."""
    try:
        with current_app.open_resource("static/img/logo.jpg") as fp:
            msg.attach(
                filename="logo.jpg",
                content_type="image/jpeg",
                data=fp.read(),
                disposition="inline",
                headers=[("Content-ID", "<logo>")]
            )
    except Exception as e:
        current_app.logger.warning(f"⚠️ No se pudo adjuntar logo (static/img/logo.jpg): {e}")


def _generar_estilos_email():
    return '''<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    background: #f5f7fa;
    padding: 20px;
    line-height: 1.6;
    color: #111827;
  }
  .email-wrapper {
    max-width: 680px;
    margin: 0 auto;
    background: #ffffff;
    border-radius: 14px;
    overflow: hidden;
    box-shadow: 0 10px 30px rgba(17,24,39,0.10);
  }
  .header {
    padding: 36px 26px;
    text-align: center;
    color: #fff;
  }
  .header.success { background: linear-gradient(135deg, #10b981 0%, #059669 100%); }
  .header.warning { background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); }
  .header.danger  { background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); }
  .icon-circle {
    width: 86px;
    height: 86px;
    margin: 0 auto 14px auto;
    border-radius: 999px;
    background: rgba(255,255,255,0.18);
    border: 2px solid rgba(255,255,255,0.22);
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
  }
  .icon-circle img {
    width: 78px;
    height: 78px;
    object-fit: cover;
    border-radius: 999px;
    display: block;
    background: #ffffff;
  }
  .brand {
    font-size: 26px;
    font-weight: 900;
    letter-spacing: 0.2px;
  }
  .tagline {
    margin-top: 6px;
    font-size: 14px;
    opacity: 0.95;
  }
  .content {
    padding: 26px 26px 10px 26px;
  }
  .greeting {
    font-size: 16px;
    margin-bottom: 14px;
  }
  .message-box {
    border-radius: 12px;
    padding: 16px 16px;
    margin: 14px 0 18px 0;
    border: 1px solid rgba(17,24,39,0.08);
    background: #f9fafb;
  }
  .message-box.success { background: rgba(16,185,129,0.10); border-color: rgba(16,185,129,0.25); }
  .message-box.warning { background: rgba(245,158,11,0.12); border-color: rgba(245,158,11,0.28); }
  .message-box.danger  { background: rgba(239,68,68,0.10); border-color: rgba(239,68,68,0.25); }

  .muted { color: #374151; }

  .section-title {
    margin-top: 18px;
    margin-bottom: 10px;
    font-weight: 900;
    font-size: 14px;
    color: #111827;
    letter-spacing: 0.2px;
    text-transform: uppercase;
  }
  .info-card {
    background: #ffffff;
    border: 1px solid rgba(17,24,39,0.10);
    border-radius: 12px;
    overflow: hidden;
    margin-bottom: 14px;
  }
  .info-row {
    display: flex;
    justify-content: space-between;
    gap: 14px;
    padding: 12px 14px;
    border-top: 1px solid rgba(17,24,39,0.06);
  }
  .info-row:first-child { border-top: 0; }
  .info-label { color: #374151; font-weight: 700; }
  .info-value { color: #111827; font-weight: 800; text-align: right; white-space: nowrap; }
  .pill {
    display: inline-block;
    padding: 6px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 900;
    letter-spacing: 0.2px;
  }
  .pill.success { background: rgba(16,185,129,0.18); color: #065f46; }
  .pill.warning { background: rgba(245,158,11,0.20); color: #92400e; }
  .pill.danger  { background: rgba(239,68,68,0.18); color: #7f1d1d; }

  .footer {
    padding: 18px 26px 24px 26px;
    color: #6b7280;
    font-size: 12px;
  }
  .footer .line { margin-top: 8px; }
  .hr {
    height: 1px;
    background: rgba(17,24,39,0.08);
    margin: 18px 0;
  }

  @media (max-width: 560px) {
    body { padding: 10px; }
    .content { padding: 18px 16px 8px 16px; }
    .header { padding: 28px 16px; }
    .info-row { flex-direction: column; align-items: flex-start; }
    .info-value { text-align: left; white-space: normal; }
  }
</style>'''


def _render_email(*, empresa, tone: str, titulo: str, subtitulo: str | None, cuerpo_html: str) -> str:
    nombre = _esc(empresa.get('nombre', ''))
    eslogan = _esc(empresa.get('eslogan', '')) if empresa.get('eslogan') else ''
    subtitulo_html = f'<div class="tagline">{_esc(subtitulo)}</div>' if subtitulo else ''
    eslogan_html = f'<div class="tagline">{eslogan}</div>' if eslogan else ''

    footer_lines = []
    footer_lines.append(f'<div class="line"><strong>{nombre}</strong>{(" — " + eslogan) if eslogan else ""}</div>')
    if empresa.get('telefono'):
        footer_lines.append(f'<div class="line">📞 {_esc(empresa.get("telefono"))}</div>')
    if empresa.get('direccion'):
        footer_lines.append(f'<div class="line">📍 {_esc(empresa.get("direccion"))}</div>')
    if empresa.get('web'):
        footer_lines.append(f'<div class="line">🌐 {_esc(empresa.get("web"))}</div>')
    footer_lines.append('<div class="line" style="margin-top:10px;">Este correo es generado automáticamente. Por favor, no respondas a este mensaje.</div>')

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  {_generar_estilos_email()}
</head>
<body>
  <div class="email-wrapper">
    <div class="header {tone}">
      <div class="icon-circle"><img src="cid:logo" alt="Logo"></div>
      <div class="brand">{nombre}</div>
      {eslogan_html}
      {subtitulo_html}
    </div>

    <div class="content">
      {cuerpo_html}
      <div class="hr"></div>
      <div class="footer">
        {''.join(footer_lines)}
      </div>
    </div>
  </div>
</body>
</html>"""


def _inscripcion_card(cliente) -> str:
    fecha_registro = getattr(cliente, 'fecha_registro', None)
    fecha_inicio_clases = getattr(cliente, 'fecha_inicio_clases', None)
    valor_inscripcion = getattr(cliente, 'valor_inscripcion', None)
    mensualidades_canceladas = getattr(cliente, 'mensualidades_canceladas', None)

    rows = []
    if fecha_registro:
        rows.append(("📌 Fecha de inscripción", _fmt_date(fecha_registro)))
    if fecha_inicio_clases:
        rows.append(("🏫 Inicio de clases", _fmt_date(fecha_inicio_clases)))
    if valor_inscripcion is not None:
        rows.append(("🧾 Valor de inscripción", _fmt_money(valor_inscripcion)))
    if mensualidades_canceladas is not None:
        rows.append(("✅ Mensualidades canceladas", str(mensualidades_canceladas)))

    if not rows:
        return ''

    body = "\n".join(
        [f'<div class="info-row"><span class="info-label">{_esc(l)}</span><span class="info-value">{_esc(v)}</span></div>' for l, v in rows]
    )
    return f'''<div class="section-title">Datos de inscripción</div>
<div class="info-card">{body}</div>'''


def _cliente_nombre(cliente) -> str:
    return (
        getattr(cliente, 'nombre_completo', None)
        or (f"{getattr(cliente,'nombre','')} {getattr(cliente,'apellido','')}".strip())
        or "Estudiante"
    )


def enviar_confirmacion_pago(cliente, pago):
    """
    ✅ CONFIRMACIÓN DE PAGO - Versión CORREGIDA
    """
    try:
        current_app.logger.info("=" * 70)
        current_app.logger.info("📧 ENVIANDO CONFIRMACIÓN DE PAGO")

        # ✅ PASO 1: Cargar configuración
        if not cargar_config_correo_desde_bd():
            error_msg = current_app.config.get('SMTP_LAST_ERROR', 'Error desconocido')
            current_app.logger.error(f"❌ Config inválida: {error_msg}")
            return False

        # ✅ PASO 2: Verificar que esté habilitado
        if not current_app.config.get('ENABLE_EMAIL_NOTIFICATIONS'):
            current_app.logger.error("❌ Correos deshabilitados")
            return False

        # ✅ PASO 3: Obtener personalización
        empresa = obtener_personalizacion()
        if empresa is None:
            current_app.logger.error("❌ No hay información de empresa")
            return False

        # ✅ PASO 4: Validar email del cliente
        if not getattr(cliente, 'email', None):
            current_app.logger.error("❌ Cliente sin email")
            return False

        # ✅ PASO 5: Preparar datos
        curso_nombre = cliente.curso.nombre if getattr(cliente, 'curso', None) else 'No asignado'
        curso_precio = _fmt_money(cliente.curso.precio_mensual) if getattr(cliente, 'curso', None) else 'N/A'

        fecha_pago = _fmt_date(getattr(pago, 'fecha_pago', None) or datetime.now(), with_time=True)
        fecha_vencimiento = _fmt_date(getattr(cliente, 'fecha_fin', None))

        metodo = getattr(pago, 'metodo_pago', None) or 'No especificado'
        referencia = getattr(pago, 'referencia', None) or 'N/A'
        periodo = getattr(pago, 'periodo', None) or '—'
        monto = _fmt_money(getattr(pago, 'monto', None))

        dias_cobertura = 0
        try:
            if getattr(cliente, 'fecha_fin', None):
                dias_cobertura = (cliente.fecha_fin.date() - datetime.now().date()).days
        except Exception:
            dias_cobertura = 0

        if dias_cobertura >= 15:
            estado_pill = "success"
        elif dias_cobertura >= 0:
            estado_pill = "warning"
        else:
            estado_pill = "danger"

        estado_txt = (
            f"{dias_cobertura} días restantes" if dias_cobertura >= 0 else f"Vencido hace {abs(dias_cobertura)} días"
        )

        asunto = f"✅ Pago Confirmado - {empresa['nombre']}"

        cuerpo = f"""
<p class="greeting">Hola <strong>{_esc(_cliente_nombre(cliente))}</strong>,</p>

<div class="message-box success">
  <div style="font-weight:900; font-size:16px; margin-bottom:6px;">✅ ¡Pago recibido exitosamente!</div>
  <div class="muted">Tu membresía ha sido renovada y está completamente activa.</div>
</div>

<div class="section-title">Resumen del pago</div>
<div class="info-card">
  <div class="info-row"><span class="info-label">📅 Fecha de pago</span><span class="info-value">{_esc(fecha_pago)}</span></div>
  <div class="info-row"><span class="info-label">💳 Método</span><span class="info-value">{_esc(metodo)}</span></div>
  <div class="info-row"><span class="info-label">🔎 Referencia</span><span class="info-value">{_esc(referencia)}</span></div>
  <div class="info-row"><span class="info-label">🧾 Período</span><span class="info-value">{_esc(periodo)}</span></div>
  <div class="info-row"><span class="info-label">💰 Monto pagado</span><span class="info-value">{_esc(monto)}</span></div>
</div>

<div class="section-title">Estado de tu membresía</div>
<div class="info-card">
  <div class="info-row"><span class="info-label">📚 Curso</span><span class="info-value">{_esc(curso_nombre)}</span></div>
  <div class="info-row"><span class="info-label">💵 Mensualidad</span><span class="info-value">{_esc(curso_precio)}</span></div>
  <div class="info-row"><span class="info-label">📌 Próximo vencimiento</span><span class="info-value">{_esc(fecha_vencimiento)}</span></div>
  <div class="info-row"><span class="info-label">⏳ Estado</span><span class="info-value"><span class="pill {estado_pill}">{_esc(estado_txt)}</span></span></div>
</div>

{_inscripcion_card(cliente)}
""".strip()

        html_body = _render_email(
            empresa=empresa,
            tone="success",
            titulo="Pago confirmado",
            subtitulo="Comprobante y detalle de tu membresía",
            cuerpo_html=cuerpo
        )

        # ✅ PASO 6: Crear mensaje
        msg = Message(
            subject=asunto,
            recipients=[cliente.email],
            html=html_body,
            sender=current_app.config['MAIL_DEFAULT_SENDER']
        )
        _attach_logo_inline(msg)

        # ✅ ADJUNTAR PDF DEL ESTUDIANTE (comprobante / reporte)
        try:
            from pdf_reports import pdf_generator
            pdf_generator.nombre_empresa = empresa.get('nombre') or pdf_generator.nombre_empresa
            pdf_generator.eslogan_empresa = empresa.get('eslogan') or pdf_generator.eslogan_empresa

            pdf_io = pdf_generator.generar_reporte_estudiante(cliente)
            pdf_bytes = pdf_io.getvalue() if hasattr(pdf_io, 'getvalue') else pdf_io.read()

            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename_pdf = f"reporte_estudiante_{getattr(cliente,'id','')}_{ts}.pdf"
            msg.attach(filename_pdf, "application/pdf", pdf_bytes)
            current_app.logger.info(f"📎 PDF adjunto: {filename_pdf}")
        except Exception as e:
            current_app.logger.warning(f"⚠️ No se pudo adjuntar PDF: {e}")


        # ✅ PASO 7: Enviar
        current_app.logger.info(f"📤 Enviando a: {cliente.email}")
        mail.send(msg)
        current_app.logger.info("✅ Correo enviado exitosamente")
        current_app.logger.info("=" * 70)
        return True

    except Exception as e:
        current_app.logger.error(f"❌ Error enviando correo: {e}")
        current_app.logger.error(traceback.format_exc())
        return False


def enviar_aviso_vencimiento(cliente, dias_para_vencer):
    """⚠️ AVISO DE VENCIMIENTO - Versión CORREGIDA"""
    try:
        current_app.logger.info("=" * 70)
        current_app.logger.info("⚠️ ENVIANDO AVISO DE VENCIMIENTO")

        if not cargar_config_correo_desde_bd():
            return False

        if not current_app.config.get('ENABLE_EMAIL_NOTIFICATIONS'):
            return False

        empresa = obtener_personalizacion()
        if empresa is None:
            return False

        if not getattr(cliente, 'email', None):
            return False

        curso_nombre = cliente.curso.nombre if getattr(cliente, 'curso', None) else 'No asignado'
        curso_precio = _fmt_money(cliente.curso.precio_mensual) if getattr(cliente, 'curso', None) else 'N/A'
        fecha_vencimiento = _fmt_date(getattr(cliente, 'fecha_fin', None))

        try:
            dias_para_vencer = int(dias_para_vencer or 0)
        except Exception:
            dias_para_vencer = 0

        if dias_para_vencer > 7:
            tone = "warning"
            pill = "warning"
            pill_txt = f"Faltan {dias_para_vencer} días"
            asunto = f"⚠️ Tu membresía vence en {dias_para_vencer} días - {empresa['nombre']}"
            titulo = "Aviso de vencimiento"
            descripcion = f"Tu membresía en <strong>{_esc(curso_nombre)}</strong> vencerá pronto."
        elif dias_para_vencer > 0:
            tone = "warning"
            pill = "danger"
            pill_txt = f"Faltan {dias_para_vencer} días"
            asunto = f"⚠️ Tu membresía vence en {dias_para_vencer} días - {empresa['nombre']}"
            titulo = "Atención: vencimiento cercano"
            descripcion = f"Tu membresía en <strong>{_esc(curso_nombre)}</strong> está por vencer."
        else:
            tone = "danger"
            pill = "danger"
            dias_v = abs(dias_para_vencer)
            pill_txt = f"Vencido hace {dias_v} días"
            asunto = f"🔴 Tu membresía ha vencido - {empresa['nombre']}"
            titulo = "Tu membresía ha vencido"
            descripcion = f"Tu membresía en <strong>{_esc(curso_nombre)}</strong> se encuentra vencida."

        cuerpo = f"""
<p class="greeting">Hola <strong>{_esc(_cliente_nombre(cliente))}</strong>,</p>

<div class="message-box {tone}">
  <div style="font-weight:900; font-size:16px; margin-bottom:6px;">{titulo}</div>
  <div class="muted">{descripcion} Para evitar interrupciones, realiza tu pago lo antes posible.</div>
</div>

<div class="section-title">Información de tu membresía</div>
<div class="info-card">
  <div class="info-row"><span class="info-label">📚 Curso</span><span class="info-value">{_esc(curso_nombre)}</span></div>
  <div class="info-row"><span class="info-label">💵 Mensualidad</span><span class="info-value">{_esc(curso_precio)}</span></div>
  <div class="info-row"><span class="info-label">📌 Fecha de vencimiento</span><span class="info-value">{_esc(fecha_vencimiento)}</span></div>
  <div class="info-row"><span class="info-label">⏳ Estado</span><span class="info-value"><span class="pill {pill}">{_esc(pill_txt)}</span></span></div>
</div>

{_inscripcion_card(cliente)}
""".strip()

        html_body = _render_email(
            empresa=empresa,
            tone=tone,
            titulo=titulo,
            subtitulo="Aviso automático de vencimiento",
            cuerpo_html=cuerpo
        )

        msg = Message(
            subject=asunto,
            recipients=[cliente.email],
            html=html_body,
            sender=current_app.config['MAIL_DEFAULT_SENDER']
        )
        _attach_logo_inline(msg)

        current_app.logger.info(f"📤 Enviando a: {cliente.email}")
        mail.send(msg)
        current_app.logger.info("✅ Correo enviado")
        return True

    except Exception as e:
        current_app.logger.error(f"❌ Error: {e}")
        current_app.logger.error(traceback.format_exc())
        return False


def enviar_recordatorio_pago(cliente, dias_vencido=1):
    """🔴 RECORDATORIO DE PAGO - Versión CORREGIDA"""
    try:
        current_app.logger.info("=" * 70)
        current_app.logger.info("🔴 ENVIANDO RECORDATORIO DE PAGO")

        if not cargar_config_correo_desde_bd():
            return False

        if not current_app.config.get('ENABLE_EMAIL_NOTIFICATIONS'):
            return False

        empresa = obtener_personalizacion()
        if empresa is None:
            return False

        if not getattr(cliente, 'email', None):
            return False

        curso_nombre = cliente.curso.nombre if getattr(cliente, 'curso', None) else 'No asignado'
        curso_precio = _fmt_money(cliente.curso.precio_mensual) if getattr(cliente, 'curso', None) else 'N/A'
        fecha_vencimiento = _fmt_date(getattr(cliente, 'fecha_fin', None))

        try:
            dias_vencido = int(dias_vencido or 0)
        except Exception:
            dias_vencido = 0

        asunto = f"🔴 Recordatorio de Pago Vencido - {empresa['nombre']}"

        cuerpo = f"""
<p class="greeting">Hola <strong>{_esc(_cliente_nombre(cliente))}</strong>,</p>

<div class="message-box danger">
  <div style="font-weight:900; font-size:16px; margin-bottom:6px;">🔴 Pago pendiente</div>
  <div class="muted">Tu membresía en <strong>{_esc(curso_nombre)}</strong> tiene un pago pendiente.</div>
  <div style="margin-top:8px; font-weight:800;">Venció el {_esc(fecha_vencimiento)} ({abs(dias_vencido)} día(s) vencido).</div>
</div>

<div class="section-title">Detalle del pago pendiente</div>
<div class="info-card">
  <div class="info-row"><span class="info-label">📚 Curso</span><span class="info-value">{_esc(curso_nombre)}</span></div>
  <div class="info-row"><span class="info-label">💵 Mensualidad</span><span class="info-value">{_esc(curso_precio)}</span></div>
  <div class="info-row"><span class="info-label">📌 Fecha de vencimiento</span><span class="info-value">{_esc(fecha_vencimiento)}</span></div>
</div>

{_inscripcion_card(cliente)}
""".strip()

        html_body = _render_email(
            empresa=empresa,
            tone="danger",
            titulo="Recordatorio de pago",
            subtitulo="Aviso automático del sistema",
            cuerpo_html=cuerpo
        )

        msg = Message(
            subject=asunto,
            recipients=[cliente.email],
            html=html_body,
            sender=current_app.config['MAIL_DEFAULT_SENDER']
        )
        _attach_logo_inline(msg)

        current_app.logger.info(f"📤 Enviando a: {cliente.email}")
        mail.send(msg)
        current_app.logger.info("✅ Correo enviado")
        return True

    except Exception as e:
        current_app.logger.error(f"❌ Error: {e}")
        current_app.logger.error(traceback.format_exc())
        return False


def test_email_config():
    """Prueba rápida de configuración (usado en Configuración del sistema)"""
    try:
        return cargar_config_correo_desde_bd()
    except Exception:
        return False

def enviar_correo_prueba(destinatario: str):
    """
    Envía un correo REAL para verificar que Flask-Mail está enviando.
    """
    try:
        if not cargar_config_correo_desde_bd():
            return False, current_app.config.get("SMTP_LAST_ERROR", "Config SMTP inválida")

        msg = Message(
            subject="✅ Prueba de correo - Sistema",
            recipients=[destinatario],
            html="<h2>Correo funcionando ✅</h2><p>Si ves este mensaje, el envío está OK.</p>",
            sender=current_app.config.get("MAIL_DEFAULT_SENDER"),
        )
        mail.send(msg)
        return True, "Correo de prueba enviado correctamente"
    except Exception as e:
        return False, str(e)
