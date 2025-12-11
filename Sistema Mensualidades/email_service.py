# -*- coding: utf-8 -*-
"""
Servicio de Correo - VERSIÓN MEJORADA
Con mensajes adaptados al momento exacto
"""

from flask_mail import Mail, Message
from flask import render_template_string, current_app
from datetime import datetime
import traceback

mail = Mail()


def cargar_config_correo_desde_bd():
    """
    🔥 FUNCIÓN CRÍTICA: Carga la configuración de correo desde la BD
    y actualiza Flask-Mail en tiempo real
    """
    try:
        from app import Configuracion, app
        
        mail_server = Configuracion.obtener('MAIL_SERVER')
        mail_port = Configuracion.obtener('MAIL_PORT')
        mail_username = Configuracion.obtener('MAIL_USERNAME')
        mail_password = Configuracion.obtener('MAIL_PASSWORD')
        mail_sender = Configuracion.obtener('MAIL_DEFAULT_SENDER')
        
        if all([mail_server, mail_username, mail_password]):
            current_app.config['MAIL_SERVER'] = mail_server
            current_app.config['MAIL_PORT'] = int(mail_port)
            current_app.config['MAIL_USERNAME'] = mail_username
            current_app.config['MAIL_PASSWORD'] = mail_password
            current_app.config['MAIL_DEFAULT_SENDER'] = mail_sender
            current_app.config['MAIL_USE_TLS'] = True
            current_app.config['MAIL_USE_SSL'] = False
            
            mail.init_app(current_app)
            
            current_app.logger.info(f"✅ Configuración de correo cargada desde BD: {mail_username}")
            return True
        else:
            current_app.logger.warning("⚠️ No hay configuración de correo en BD")
            return False
            
    except Exception as e:
        current_app.logger.error(f"❌ Error cargando config de correo: {e}")
        return False


def enviar_confirmacion_pago(cliente, pago):
    """
    ✅ CORREO 1: Confirmación de pago recibido
    Se envía INMEDIATAMENTE al registrar un pago
    """
    try:
        cargar_config_correo_desde_bd()
        
        if not cliente.email:
            current_app.logger.error(f"Cliente {cliente.nombre_completo} no tiene email")
            return False
        
        # Calcular nueva fecha de vencimiento
        fecha_vencimiento = cliente.fecha_fin.strftime('%d/%m/%Y') if cliente.fecha_fin else 'No definida'
        
        asunto = f"✅ Pago Recibido - ${pago.monto:.2f}"
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                .highlight {{ background: #e8f5e9; border-left: 4px solid #4caf50; padding: 15px; margin: 20px 0; }}
                .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>✅ ¡Pago Recibido!</h1>
                </div>
                <div class="content">
                    <h2>Hola {cliente.nombre_completo},</h2>
                    <p>Hemos recibido tu pago exitosamente. ¡Gracias por tu confianza y puntualidad!</p>
                    
                    <div class="highlight">
                        <p><strong>📋 Detalles del pago:</strong></p>
                        <ul>
                            <li><strong>Monto:</strong> ${pago.monto:.2f}</li>
                            <li><strong>Fecha:</strong> {pago.fecha_pago.strftime('%d/%m/%Y %H:%M')}</li>
                            <li><strong>Plan:</strong> {cliente.plan.nombre if cliente.plan else 'N/A'}</li>
                            {'<li><strong>Método:</strong> ' + pago.metodo_pago + '</li>' if pago.metodo_pago else ''}
                            {'<li><strong>Referencia:</strong> ' + pago.referencia + '</li>' if pago.referencia else ''}
                        </ul>
                        <p style="margin-top: 15px;"><strong>📅 Tu servicio está activo hasta:</strong> {fecha_vencimiento}</p>
                    </div>
                    
                    <p>Tu cuenta está al día. Te enviaremos un recordatorio 3 días antes del próximo vencimiento.</p>
                    
                    <div class="footer">
                        <p>Gracias por confiar en nosotros 💚</p>
                        <p>Este es un correo automático, por favor no responder.</p>
                        <p>&copy; 2025 Sistema de Mensualidades</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        msg = Message(
            subject=asunto,
            recipients=[cliente.email],
            html=html_body
        )
        
        mail.send(msg)
        current_app.logger.info(f"✅ Confirmación de pago enviada a {cliente.email}")
        return True
        
    except Exception as e:
        current_app.logger.error(f"❌ Error enviando confirmación a {cliente.email}: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        return False


def enviar_aviso_vencimiento(cliente, dias_para_vencer):
    """
    📧 CORREO 2 y 3: Avisos estratégicos
    
    Casos:
    - dias_para_vencer = 3: "Tu plan vence en 3 días" (PREVIO)
    - dias_para_vencer = 1: "Tu plan venció ayer" (POST-VENCIMIENTO)
    """
    try:
        cargar_config_correo_desde_bd()
        
        if not cliente.email:
            current_app.logger.error(f"Cliente {cliente.nombre_completo} no tiene email")
            return False
        
        if not cliente.plan:
            current_app.logger.error(f"Cliente {cliente.nombre_completo} no tiene plan asignado")
            return False
        
        # 🎯 DETERMINAR TIPO DE MENSAJE
        if dias_para_vencer > 0:
            # RECORDATORIO PREVIO (3 días antes)
            asunto = f"⏰ Recordatorio: Tu plan vence en {dias_para_vencer} días"
            titulo = "⏰ Recordatorio de Renovación"
            emoji_header = "⏰"
            color_degradado = "linear-gradient(135deg, #667eea 0%, #764ba2 100%)"
            
            mensaje_principal = f"""
                <p>Te recordamos de manera <strong>amigable</strong> que tu plan vence en <strong>{dias_para_vencer} días</strong>.</p>
                <p>Para continuar disfrutando del servicio sin interrupciones, te sugerimos realizar tu pago antes del <strong>{cliente.fecha_fin.strftime('%d/%m/%Y')}</strong>.</p>
            """
            
            mensaje_footer = "Te enviaremos un recordatorio si no recibimos tu pago a tiempo. 😊"
            
        else:
            # RECORDATORIO POST-VENCIMIENTO (1 día después)
            asunto = f"⚠️ Tu plan venció - Renueva pronto"
            titulo = "⚠️ Plan Vencido"
            emoji_header = "⚠️"
            color_degradado = "linear-gradient(135deg, #f093fb 0%, #f5576c 100%)"
            
            dias_vencido = abs(dias_para_vencer)
            
            mensaje_principal = f"""
                <p>Tu plan venció hace <strong>{dias_vencido} día{'s' if dias_vencido > 1 else ''}</strong>.</p>
                <p>Para reactivar tu servicio, por favor realiza tu pago lo antes posible.</p>
                <p>Si ya realizaste el pago, ignora este mensaje. 🙏</p>
            """
            
            mensaje_footer = "Estamos aquí para ayudarte. 💙"
        
        # 📧 PLANTILLA HTML
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: {color_degradado}; color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
                .info-box {{ background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0; }}
                .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
                .plan-details {{ background: white; padding: 15px; border-radius: 5px; margin: 15px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{emoji_header} {titulo}</h1>
                </div>
                <div class="content">
                    <h2>Hola {cliente.nombre_completo},</h2>
                    
                    {mensaje_principal}
                    
                    <div class="plan-details">
                        <p><strong>📋 Detalles de tu plan:</strong></p>
                        <ul>
                            <li><strong>Plan:</strong> {cliente.plan.nombre}</li>
                            <li><strong>Monto:</strong> ${cliente.plan.precio:.2f}</li>
                            <li><strong>Fecha de vencimiento:</strong> {cliente.fecha_fin.strftime('%d/%m/%Y')}</li>
                        </ul>
                    </div>
                    
                    <p style="margin-top: 20px;">{mensaje_footer}</p>
                    
                    <div class="footer">
                        <p>Este es un correo automático, por favor no responder.</p>
                        <p>&copy; 2025 Sistema de Mensualidades</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        msg = Message(
            subject=asunto,
            recipients=[cliente.email],
            html=html_body
        )
        
        mail.send(msg)
        current_app.logger.info(f"✅ Aviso enviado a {cliente.email} (días: {dias_para_vencer})")
        return True
        
    except Exception as e:
        current_app.logger.error(f"❌ Error enviando aviso a {cliente.email}: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        return False


def enviar_recordatorio_pago(cliente, dias_vencido=0):
    """
    ⚠️ CORREO LEGACY: Mantener para compatibilidad
    Ahora usa la función mejorada enviar_aviso_vencimiento
    """
    # Redirigir a la función mejorada
    return enviar_aviso_vencimiento(cliente, -dias_vencido if dias_vencido > 0 else 0)


def test_email_config():
    """Función para probar la configuración de correo"""
    try:
        cargar_config_correo_desde_bd()
        
        msg = Message(
            subject="✅ Prueba de Configuración - Sistema de Mensualidades",
            recipients=[current_app.config['MAIL_USERNAME']],
            html="""
            <h2>✅ Configuración de Correo Exitosa</h2>
            <p>Si estás leyendo este mensaje, significa que la configuración de correo está funcionando correctamente.</p>
            <p><strong>Sistema de Mensualidades</strong></p>
            """
        )
        mail.send(msg)
        current_app.logger.info("✅ Correo de prueba enviado exitosamente")
        return True, "Correo de prueba enviado exitosamente"
    except Exception as e:
        current_app.logger.error(f"❌ Error en correo de prueba: {str(e)}")
        return False, f"Error: {str(e)}"