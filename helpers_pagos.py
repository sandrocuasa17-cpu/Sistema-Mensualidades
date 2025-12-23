# -*- coding: utf-8 -*-
"""
Helpers y Validaciones para Sistema de Pagos
Funciones auxiliares que simplifican el código principal

USO:
    from helpers_pagos import (
        calcular_distribucion_pago,
        validar_pago,
        obtener_sugerencias_pago,
        generar_resumen_estado
    )
"""

from datetime import datetime, timedelta
from flask import current_app as app


def calcular_distribucion_pago(monto, cliente, concepto='auto'):
    """
    🧮 Calcula cómo se distribuirá un pago ANTES de registrarlo
    
    CASOS DE USO:
    - Vista previa en el formulario de pagos (JavaScript)
    - Validar montos antes de procesar
    - Mostrar desglose en confirmaciones
    
    EJEMPLO DE USO:
    ```python
    resultado = calcular_distribucion_pago(150.00, cliente, 'auto')
    
    if resultado['es_valido']:
        print(f"Inscripción: ${resultado['inscripcion_cubierta']}")
        print(f"Mensualidades: {resultado['mensualidades_completas']}")
        print(f"Crédito: ${resultado['carry_final']}")
    ```
    
    Args:
        monto (float): Monto del pago a simular
        cliente (Cliente): Objeto del estudiante
        concepto (str): 'auto', 'inscripcion', 'mensualidad'
    
    Returns:
        dict con:
        - desglose (list): Lista detallada del desglose
        - inscripcion_cubierta (float): Monto que cubre de inscripción
        - mensualidades_completas (int): Mensualidades completas que cubre
        - carry_final (float): Crédito acumulado final
        - es_valido (bool): Si el pago es procesable
        - mensaje (str): Mensaje descriptivo
    """
    
    # Validación: Cliente sin curso
    if not cliente.curso:
        return {
            'desglose': [],
            'inscripcion_cubierta': 0,
            'mensualidades_completas': 0,
            'carry_final': 0,
            'es_valido': False,
            'mensaje': '❌ El estudiante no tiene curso asignado'
        }
    
    # Obtener precios del curso
    precio_mensual = float(cliente.curso.precio_mensual or 0)
    precio_inscripcion = float(cliente.curso.precio_inscripcion or 0)
    
    # Validación: Precio mensual inválido
    if precio_mensual <= 0:
        return {
            'desglose': [],
            'inscripcion_cubierta': 0,
            'mensualidades_completas': 0,
            'carry_final': 0,
            'es_valido': False,
            'mensaje': '❌ El curso no tiene precio mensual válido'
        }
    
    # Estado actual del estudiante
    inscripcion_pendiente = cliente.inscripcion_pendiente
    carry_actual = float(cliente.carry_mensualidad or 0)
    
    # Variables de tracking
    desglose = []
    saldo = monto
    inscripcion_cubierta = 0
    mensualidades_completas = 0
    carry_final = carry_actual
    
    # ===================================
    # CONCEPTO: AUTOMÁTICO
    # ===================================
    if concepto == 'auto':
        # Paso 1: Inscripción primero
        if inscripcion_pendiente > 0:
            if saldo >= inscripcion_pendiente:
                inscripcion_cubierta = inscripcion_pendiente
                desglose.append({
                    'tipo': 'inscripcion',
                    'monto': inscripcion_pendiente,
                    'descripcion': f"✅ Inscripción completa: ${inscripcion_pendiente:.2f}",
                    'completo': True
                })
                saldo -= inscripcion_pendiente
            else:
                inscripcion_cubierta = saldo
                desglose.append({
                    'tipo': 'inscripcion',
                    'monto': saldo,
                    'descripcion': f"💰 Abono inscripción: ${saldo:.2f} (falta ${inscripcion_pendiente - saldo:.2f})",
                    'completo': False
                })
                saldo = 0
        
        # Paso 2: Mensualidades
        if saldo > 0:
            carry_total = carry_actual + saldo
            mensualidades_completas = int(carry_total // precio_mensual)
            carry_final = carry_total % precio_mensual
            
            if mensualidades_completas > 0:
                desglose.append({
                    'tipo': 'mensualidad',
                    'monto': mensualidades_completas * precio_mensual,
                    'descripcion': f"✅ {mensualidades_completas} mensualidad(es): ${mensualidades_completas * precio_mensual:.2f}",
                    'completo': True
                })
            
            if carry_final > 0:
                desglose.append({
                    'tipo': 'carry',
                    'monto': carry_final,
                    'descripcion': f"💰 Crédito: ${carry_final:.2f} (falta ${precio_mensual - carry_final:.2f})",
                    'completo': False
                })
    
    # ===================================
    # CONCEPTO: SOLO INSCRIPCIÓN
    # ===================================
    elif concepto == 'inscripcion':
        if inscripcion_pendiente > 0:
            inscripcion_cubierta = min(saldo, inscripcion_pendiente)
            completo = (inscripcion_cubierta >= inscripcion_pendiente)
            
            desglose.append({
                'tipo': 'inscripcion',
                'monto': inscripcion_cubierta,
                'descripcion': f"{'✅' if completo else '💰'} Inscripción: ${inscripcion_cubierta:.2f}",
                'completo': completo
            })
        else:
            desglose.append({
                'tipo': 'info',
                'monto': 0,
                'descripcion': "⚠️ La inscripción ya está pagada",
                'completo': False
            })
    
    # ===================================
    # CONCEPTO: SOLO MENSUALIDAD
    # ===================================
    elif concepto == 'mensualidad':
        carry_total = carry_actual + saldo
        mensualidades_completas = int(carry_total // precio_mensual)
        carry_final = carry_total % precio_mensual
        
        if mensualidades_completas > 0:
            desglose.append({
                'tipo': 'mensualidad',
                'monto': mensualidades_completas * precio_mensual,
                'descripcion': f"✅ {mensualidades_completas} mensualidad(es): ${mensualidades_completas * precio_mensual:.2f}",
                'completo': True
            })
        
        if carry_final > 0:
            desglose.append({
                'tipo': 'carry',
                'monto': carry_final,
                'descripcion': f"💰 Crédito: ${carry_final:.2f} (falta ${precio_mensual - carry_final:.2f})",
                'completo': False
            })
    
    # ===================================
    # GENERAR MENSAJE RESUMEN
    # ===================================
    if not desglose:
        mensaje = "⚠️ Este pago no cubre ningún concepto"
        es_valido = False
    else:
        partes_mensaje = []
        
        if inscripcion_cubierta > 0:
            if inscripcion_cubierta >= inscripcion_pendiente:
                partes_mensaje.append(f"✅ Inscripción completa")
            else:
                partes_mensaje.append(f"💰 Abono inscripción")
        
        if mensualidades_completas > 0:
            partes_mensaje.append(f"✅ {mensualidades_completas} mes(es)")
        
        if carry_final > carry_actual:
            partes_mensaje.append(f"💰 +${carry_final - carry_actual:.2f} crédito")
        
        mensaje = " | ".join(partes_mensaje) if partes_mensaje else "✅ Pago procesado"
        es_valido = True
    
    return {
        'desglose': desglose,
        'inscripcion_cubierta': inscripcion_cubierta,
        'mensualidades_completas': mensualidades_completas,
        'carry_final': carry_final,
        'es_valido': es_valido,
        'mensaje': mensaje
    }


def validar_pago(monto, cliente, concepto='auto'):
    """
    ✅ Valida que un pago sea procesable
    
    CASOS DE USO:
    - Antes de mostrar el formulario de pago
    - Antes de procesar un pago
    - En validaciones de API
    
    EJEMPLO DE USO:
    ```python
    es_valido, error = validar_pago(100.00, cliente, 'auto')
    
    if not es_valido:
        flash(error, 'danger')
        return redirect(url_for('clientes'))
    ```
    
    Args:
        monto (float): Monto a validar
        cliente (Cliente): Objeto del estudiante
        concepto (str): 'auto', 'inscripcion', 'mensualidad'
    
    Returns:
        tuple: (es_valido: bool, mensaje_error: str|None)
    """
    
    # Validar monto
    if monto <= 0:
        return False, "❌ El monto debe ser mayor a 0"
    
    # Validar cliente
    if not cliente:
        return False, "❌ Cliente no encontrado"
    
    if not cliente.activo:
        return False, "❌ El estudiante está inactivo"
    
    # Validar curso
    if not cliente.curso:
        return False, "❌ El estudiante no tiene curso asignado"
    
    # Validar precios del curso
    try:
        precio_mensual = float(cliente.curso.precio_mensual or 0)
        precio_inscripcion = float(cliente.curso.precio_inscripcion or 0)
    except (TypeError, ValueError):
        return False, "❌ Error en los precios del curso"
    
    if precio_mensual <= 0:
        return False, "❌ El curso no tiene precio mensual válido"
    
    # Validar concepto
    if concepto not in ['auto', 'inscripcion', 'mensualidad']:
        return False, f"❌ Concepto inválido: {concepto}"
    
    # Validar que tenga fecha de inicio de clases
    if not cliente.fecha_inicio_clases:
        return False, "❌ El estudiante no tiene fecha de inicio de clases"
    
    # Todo OK
    return True, None


def obtener_sugerencias_pago(cliente):
    """
    💡 Genera sugerencias inteligentes de pago
    
    CASOS DE USO:
    - Mostrar "botones rápidos" en el formulario
    - Sugerencias en el dashboard
    - Notificaciones personalizadas
    
    EJEMPLO DE USO:
    ```python
    sugerencias = obtener_sugerencias_pago(cliente)
    
    for sugerencia in sugerencias:
        print(f"{sugerencia['titulo']}: ${sugerencia['monto']}")
    ```
    
    Args:
        cliente (Cliente): Objeto del estudiante
    
    Returns:
        list: Lista de diccionarios con sugerencias
        Cada sugerencia contiene:
        - titulo (str): Nombre de la sugerencia
        - monto (float): Monto sugerido
        - descripcion (str): Descripción detallada
        - concepto (str): Concepto a usar
        - prioridad (str): 'alta', 'media', 'baja'
        - icono (str): Icono de Bootstrap
        - color (str): Color del botón
    """
    if not cliente.curso:
        return []
    
    sugerencias = []
    
    precio_mensual = float(cliente.curso.precio_mensual or 0)
    precio_inscripcion = float(cliente.curso.precio_inscripcion or 0)
    inscripcion_pendiente = cliente.inscripcion_pendiente
    carry = float(cliente.carry_mensualidad or 0)
    
    # Sugerencia 1: Inscripción completa (si está pendiente)
    if inscripcion_pendiente > 0:
        sugerencias.append({
            'titulo': 'Inscripción Completa',
            'monto': inscripcion_pendiente,
            'descripcion': f'Completa el pago de inscripción',
            'concepto': 'inscripcion',
            'prioridad': 'alta',
            'icono': 'file-earmark-check',
            'color': 'primary'
        })
    
    # Sugerencia 2: Completar mensualidad en progreso (si tiene carry)
    if carry > 0:
        faltante = precio_mensual - carry
        sugerencias.append({
            'titulo': 'Completar Mensualidad',
            'monto': faltante,
            'descripcion': f'Completa la mensualidad en progreso (tienes ${carry:.2f})',
            'concepto': 'mensualidad',
            'prioridad': 'alta',
            'icono': 'hourglass-split',
            'color': 'info'
        })
    
    # Sugerencia 3: 1 Mensualidad
    sugerencias.append({
        'titulo': '1 Mensualidad',
        'monto': precio_mensual,
        'descripcion': f'Paga 1 mes de clases',
        'concepto': 'mensualidad',
        'prioridad': 'media',
        'icono': 'calendar-check',
        'color': 'success'
    })
    
    # Sugerencia 4: Inscripción + 1 Mensualidad (si aplica)
    if inscripcion_pendiente > 0:
        total_completo = inscripcion_pendiente + precio_mensual
        sugerencias.append({
            'titulo': 'Inscripción + 1 Mes',
            'monto': total_completo,
            'descripcion': f'Completa inscripción y paga 1 mes',
            'concepto': 'auto',
            'prioridad': 'alta',
            'icono': 'check-all',
            'color': 'warning'
        })
    
    # Sugerencia 5: 3 Mensualidades (descuento simbólico)
    sugerencias.append({
        'titulo': '3 Mensualidades',
        'monto': precio_mensual * 3,
        'descripcion': f'Paga 3 meses (${precio_mensual * 3:.2f})',
        'concepto': 'mensualidad',
        'prioridad': 'baja',
        'icono': 'calendar3',
        'color': 'secondary'
    })
    
    return sugerencias


def generar_resumen_estado(cliente):
    """
    📊 Genera un resumen estructurado del estado del estudiante
    
    CASOS DE USO:
    - Mostrar estado en el detalle del cliente
    - Dashboard personalizado
    - Reportes
    - APIs
    
    EJEMPLO DE USO:
    ```python
    resumen = generar_resumen_estado(cliente)
    
    if resumen['tiene_curso']:
        print(f"Curso: {resumen['curso']['nombre']}")
        print(f"Inscripción: {resumen['inscripcion']['porcentaje']:.0f}%")
        print(f"Mensualidades: {resumen['mensualidades']['completas']}")
    ```
    
    Args:
        cliente (Cliente): Objeto del estudiante
    
    Returns:
        dict con estructura completa del estado
    """
    if not cliente.curso:
        return {
            'tiene_curso': False,
            'mensaje': 'Sin curso asignado'
        }
    
    precio_inscripcion = float(cliente.curso.precio_inscripcion or 0)
    precio_mensual = float(cliente.curso.precio_mensual or 0)
    
    return {
        'tiene_curso': True,
        'curso': {
            'id': cliente.curso.id,
            'nombre': cliente.curso.nombre,
            'precio_mensual': precio_mensual,
            'precio_inscripcion': precio_inscripcion
        },
        'inscripcion': {
            'total': precio_inscripcion,
            'abonado': float(cliente.abono_inscripcion or 0),
            'pendiente': cliente.inscripcion_pendiente,
            'pagada': cliente.inscripcion_pagada,
            'porcentaje': cliente.porcentaje_inscripcion
        },
        'mensualidades': {
            'completas': int(cliente.mensualidades_canceladas or 0),
            'carry': float(cliente.carry_mensualidad or 0),
            'fecha_fin': cliente.fecha_fin,
            'dias_restantes': cliente.dias_restantes
        },
        'estado': {
            'pago': cliente.estado_pago,
            'activo': cliente.activo,
            'ha_iniciado': cliente.ha_iniciado_clases,
            'vencido': cliente.plan_vencido,
            'proximo_vencer': cliente.proximo_a_vencer
        },
        'totales': {
            'pagado': cliente.total_pagado,
            'cantidad_pagos': len(cliente.pagos)
        }
    }


def formatear_desglose_html(desglose):
    """
    🎨 Formatea el desglose para mostrar en templates HTML
    
    CASOS DE USO:
    - Mostrar desglose en confirmaciones
    - Emails de notificación
    - Reportes PDF
    
    Args:
        desglose (list): Lista de diccionarios con el desglose
    
    Returns:
        str: HTML formateado listo para usar
    """
    if not desglose:
        return "<p class='text-muted'>Sin desglose</p>"
    
    html_parts = ["<ul class='list-unstyled mb-0'>"]
    
    for item in desglose:
        icono = {
            'inscripcion': '📝',
            'mensualidad': '📅',
            'carry': '💰',
            'info': 'ℹ️'
        }.get(item['tipo'], '•')
        
        clase = 'text-success' if item.get('completo') else 'text-muted'
        
        html_parts.append(
            f"<li class='{clase}'>"
            f"  <strong>{icono}</strong> {item['descripcion']}"
            f"</li>"
        )
    
    html_parts.append("</ul>")
    
    return '\n'.join(html_parts)