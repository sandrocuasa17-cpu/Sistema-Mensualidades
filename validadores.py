# -*- coding: utf-8 -*-
"""
Validadores para el Sistema de Mensualidades
"""

import re
from flask import current_app


def validar_email(email):
    """Valida formato de email"""
    patron = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(patron, email) is not None


def validar_cedula_ecuador(cedula):
    """
    Valida cédula ecuatoriana (10 dígitos con algoritmo módulo 10)
    Retorna: (es_valida, mensaje_error)
    """
    if not cedula:
        return True, None  # Permitir vacío (campo opcional)
    
    # Limpiar espacios y guiones
    cedula = cedula.strip().replace('-', '').replace(' ', '')
    
    # Debe tener exactamente 10 dígitos
    if not cedula.isdigit():
        return False, "La cédula debe contener solo números"
    
    if len(cedula) != 10:
        return False, "La cédula debe tener exactamente 10 dígitos"
    
    # Los dos primeros dígitos deben estar entre 01 y 24 (provincias)
    provincia = int(cedula[0:2])
    if provincia < 1 or provincia > 24:
        return False, "Código de provincia inválido (primeros 2 dígitos)"
    
    # Algoritmo de validación módulo 10
    try:
        coeficientes = [2, 1, 2, 1, 2, 1, 2, 1, 2]
        suma = 0
        
        for i in range(9):
            valor = int(cedula[i]) * coeficientes[i]
            suma += valor if valor < 10 else (valor - 9)
        
        resultado = suma % 10
        verificador = 0 if resultado == 0 else (10 - resultado)
        
        if verificador != int(cedula[9]):
            return False, "Dígito verificador incorrecto"
        
        return True, None
        
    except Exception as e:
        current_app.logger.error(f"Error validando cédula: {e}")
        return False, "Error al validar cédula"


def validar_cedula_generica(cedula):
    """
    Validación genérica para cédulas/DNI de cualquier país
    Acepta entre 6 y 20 caracteres alfanuméricos
    """
    if not cedula:
        return True, None
    
    # Limpiar espacios y guiones
    cedula = cedula.strip().replace('-', '').replace(' ', '')
    
    # Debe tener entre 6 y 20 caracteres
    if len(cedula) < 6:
        return False, "La cédula debe tener al menos 6 caracteres"
    
    if len(cedula) > 20:
        return False, "La cédula no puede exceder 20 caracteres"
    
    # Permitir solo números y letras
    if not cedula.isalnum():
        return False, "La cédula solo puede contener números y letras"
    
    return True, None


def validar_telefono(telefono):
    """
    Valida número de teléfono (formato flexible)
    Acepta: números, espacios, guiones, paréntesis, símbolo +
    """
    if not telefono:
        return True, None
    
    # Limpiar y obtener solo dígitos
    digitos = re.sub(r'[^\d]', '', telefono)
    
    # Debe tener entre 7 y 15 dígitos
    if len(digitos) < 7:
        return False, "El teléfono debe tener al menos 7 dígitos"
    
    if len(digitos) > 15:
        return False, "El teléfono no puede tener más de 15 dígitos"
    
    return True, None


def validar_monto(monto, min_valor=0, max_valor=999999):
    """
    Valida un monto monetario
    """
    try:
        monto_float = float(monto)
        
        if monto_float < min_valor:
            return False, f"El monto debe ser mayor o igual a ${min_valor:.2f}"
        
        if monto_float > max_valor:
            return False, f"El monto no puede exceder ${max_valor:.2f}"
        
        return True, None
        
    except (ValueError, TypeError):
        return False, "Monto inválido"


# ============================================
# FUNCIÓN HELPER PARA EL FORMULARIO
# ============================================

def validar_formulario_cliente(form_data, cliente_existente=None):
    """
    Valida todos los datos del formulario de cliente
    
    Args:
        form_data: request.form
        cliente_existente: objeto Cliente si es edición, None si es nuevo
    
    Returns:
        (es_valido, lista_errores)
    """
    errores = []
    
    # Validar email
    email = form_data.get('email', '').strip()
    if not validar_email(email):
        errores.append("Email inválido")
    
    # Validar cédula (usar validación ecuatoriana o genérica según necesidad)
    cedula = form_data.get('cedula', '').strip()
    
    # Opción 1: Validación estricta para Ecuador
    # es_valida, mensaje = validar_cedula_ecuador(cedula)
    
    # Opción 2: Validación genérica (recomendada para múltiples países)
    es_valida, mensaje = validar_cedula_generica(cedula)
    
    if not es_valida and mensaje:
        errores.append(mensaje)
    
    # Validar teléfono
    telefono = form_data.get('telefono', '').strip()
    es_valida, mensaje = validar_telefono(telefono)
    if not es_valida and mensaje:
        errores.append(mensaje)
    
    # Validar nombre y apellido
    nombre = form_data.get('nombre', '').strip()
    apellido = form_data.get('apellido', '').strip()
    
    if not nombre or len(nombre) < 2:
        errores.append("El nombre debe tener al menos 2 caracteres")
    
    if not apellido or len(apellido) < 2:
        errores.append("El apellido debe tener al menos 2 caracteres")
    
    return (len(errores) == 0, errores)