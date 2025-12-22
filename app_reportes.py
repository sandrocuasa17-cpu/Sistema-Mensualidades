# -*- coding: utf-8 -*-
"""
Rutas para Reportes Mejorados
Agregar/reemplazar estas rutas en app.py
"""

from flask import send_file, render_template, redirect, url_for, flash
from datetime import datetime

# ============================================
# RUTA PRINCIPAL DE REPORTES
# ============================================

@app.route('/reportes')
@requiere_licencia_y_auth
def reportes():
    """Página de reportes mejorada"""
    total_estudiantes = Cliente.query.filter_by(activo=True).count()
    total_pagos = Pago.query.count()
    total_cursos = Curso.query.filter_by(activo=True).count()
    
    estudiantes_activos = Cliente.query.filter_by(activo=True).all()
    proximos_vencer = [e for e in estudiantes_activos if e.proximo_a_vencer]
    
    # Calcular ingresos del mes
    inicio_mes = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    pagos_mes = Pago.query.filter(Pago.fecha_pago >= inicio_mes).all()
    total_mes = sum(p.monto for p in pagos_mes)
    
    return render_template('reportes/index.html',
                         total_estudiantes=total_estudiantes,
                         total_pagos=total_pagos,
                         total_cursos=total_cursos,
                         total_proximos_vencer=len(proximos_vencer),
                         total_mes=total_mes)


# ============================================
# REPORTE EXCEL COMPLETO (MULTIHOJA)
# ============================================

@app.route('/reportes/completo/excel')
@requiere_licencia_y_auth
def reporte_completo_excel():
    """Genera reporte completo con múltiples hojas en Excel"""
    try:
        # Obtener todos los datos
        estudiantes = Cliente.query.order_by(Cliente.nombre).all()
        pagos = Pago.query.order_by(Pago.fecha_pago.desc()).all()
        cursos = Curso.query.all()
        
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
# PDF INDIVIDUAL DE ESTUDIANTE
# ============================================

@app.route('/reportes/estudiante/<int:id>/pdf')
@requiere_licencia_y_auth
def reporte_estudiante_pdf(id):
    """Genera reporte PDF de un estudiante específico"""
    try:
        from pdf_reports import pdf_generator
        
        cliente = Cliente.query.get_or_404(id)
        
        # Obtener configuración de empresa
        nombre_empresa = Configuracion.obtener('NOMBRE_EMPRESA', 'Sistema de Gestión')
        eslogan_empresa = Configuracion.obtener('ESLOGAN_EMPRESA', 'Control de Mensualidades')
        
        # Configurar PDF generator
        pdf_generator.nombre_empresa = nombre_empresa
        pdf_generator.eslogan_empresa = eslogan_empresa
        
        # Generar PDF
        pdf_file = pdf_generator.generar_reporte_estudiante(cliente)
        
        # Nombre del archivo
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
        return redirect(url_for('cliente_detalle', id=id))


# ============================================
# COMPROBANTE DE PAGO PDF
# ============================================

@app.route('/reportes/pago/<int:id>/comprobante')
@requiere_licencia_y_auth
def comprobante_pago_pdf(id):
    """Genera comprobante de pago en PDF"""
    try:
        from pdf_reports import pdf_generator
        
        pago = Pago.query.get_or_404(id)
        
        # Obtener configuración de empresa
        nombre_empresa = Configuracion.obtener('NOMBRE_EMPRESA', 'Sistema de Gestión')
        eslogan_empresa = Configuracion.obtener('ESLOGAN_EMPRESA', 'Control de Mensualidades')
        
        # Configurar PDF generator
        pdf_generator.nombre_empresa = nombre_empresa
        pdf_generator.eslogan_empresa = eslogan_empresa
        
        # Generar PDF
        pdf_file = pdf_generator.generar_comprobante_pago(pago)
        
        # Nombre del archivo
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'comprobante_{str(pago.id).zfill(6)}_{timestamp}.pdf'
        
        app.logger.info(f'📄 Comprobante generado para pago #{pago.id}')
        
        return send_file(
            pdf_file,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        app.logger.error(f'❌ Error generando comprobante: {e}')
        import traceback
        app.logger.error(traceback.format_exc())
        flash(f'❌ Error al generar comprobante: {str(e)}', 'danger')
        return redirect(url_for('pagos'))


# ============================================
# REPORTES INDIVIDUALES (compatibilidad)
# ============================================

@app.route('/reportes/estudiantes/excel')
@requiere_licencia_y_auth
def reporte_estudiantes_excel():
    """Genera solo hoja de estudiantes (para compatibilidad)"""
    # Redirigir al reporte completo
    return redirect(url_for('reporte_completo_excel'))


@app.route('/reportes/pagos/excel')
@requiere_licencia_y_auth
def reporte_pagos_excel():
    """Genera solo hoja de pagos (para compatibilidad)"""
    # Redirigir al reporte completo
    return redirect(url_for('reporte_completo_excel'))


@app.route('/reportes/proximos-vencer/excel')
@requiere_licencia_y_auth
def reporte_proximos_vencer_excel():
    """Genera solo hoja de próximos a vencer (para compatibilidad)"""
    # Redirigir al reporte completo
    return redirect(url_for('reporte_completo_excel'))