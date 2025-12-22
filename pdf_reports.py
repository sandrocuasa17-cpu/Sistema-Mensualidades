# pdf_reports.py
# -*- coding: utf-8 -*-
"""
Generador de PDFs Profesional - Sistema de Gestión de Mensualidades
Versión Mejorada con diseño moderno y estructura clara
"""

import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, Frame, PageTemplate
)
from reportlab.pdfgen import canvas


class PDFGenerator:
    """Generador profesional de reportes PDF"""
    
    # Colores corporativos
    COLOR_PRIMARY = colors.HexColor("#1e40af")      # Azul principal
    COLOR_SECONDARY = colors.HexColor("#64748b")    # Gris
    COLOR_SUCCESS = colors.HexColor("#059669")      # Verde
    COLOR_WARNING = colors.HexColor("#d97706")      # Naranja
    COLOR_DANGER = colors.HexColor("#dc2626")       # Rojo
    COLOR_INFO = colors.HexColor("#0284c7")         # Azul claro
    COLOR_LIGHT_BG = colors.HexColor("#f8fafc")     # Fondo claro
    COLOR_BORDER = colors.HexColor("#e2e8f0")       # Borde suave
    
    def __init__(self):
        """Inicializa el generador con configuración por defecto"""
        self.nombre_empresa = "Preuniversitario"
        self.subtitulo_reporte = "REPORTE ACADÉMICO"
        self.eslogan_empresa = "Excelencia Académica"
        
        # Crear estilos personalizados
        self._crear_estilos()
    
    def _crear_estilos(self):
        """Crea estilos de párrafo personalizados"""
        styles = getSampleStyleSheet()
        
        # Título principal de la empresa
        self.s_brand = ParagraphStyle(
            "brand",
            parent=styles["Heading1"],
            fontSize=16,
            leading=20,
            textColor=self.COLOR_PRIMARY,
            fontName="Helvetica-Bold",
            spaceAfter=2,
            alignment=TA_LEFT
        )
        
        # Subtítulo del reporte
        self.s_title = ParagraphStyle(
            "title",
            parent=styles["Heading2"],
            fontSize=20,
            leading=24,
            textColor=self.COLOR_PRIMARY,
            fontName="Helvetica-Bold",
            spaceAfter=4,
            spaceBefore=0
        )
        
        # Información secundaria
        self.s_subtitle = ParagraphStyle(
            "subtitle",
            parent=styles["BodyText"],
            fontSize=10,
            leading=12,
            textColor=self.COLOR_SECONDARY,
            spaceAfter=2
        )
        
        # Secciones con ícono ■
        self.s_section = ParagraphStyle(
            "section",
            parent=styles["BodyText"],
            fontSize=12,
            leading=14,
            textColor=self.COLOR_PRIMARY,
            fontName="Helvetica-Bold",
            spaceAfter=8,
            spaceBefore=12
        )
        
        # Etiquetas (keys)
        self.s_label = ParagraphStyle(
            "label",
            parent=styles["BodyText"],
            fontSize=9,
            leading=11,
            textColor=self.COLOR_SECONDARY,
            fontName="Helvetica-Bold"
        )
        
        # Valores
        self.s_value = ParagraphStyle(
            "value",
            parent=styles["BodyText"],
            fontSize=9,
            leading=11,
            textColor=colors.HexColor("#1e293b")
        )
        
        # Estados (éxito, advertencia, peligro)
        self.s_success = ParagraphStyle(
            "success",
            parent=styles["BodyText"],
            fontSize=11,
            leading=13,
            textColor=self.COLOR_SUCCESS,
            fontName="Helvetica-Bold"
        )
        
        self.s_warning = ParagraphStyle(
            "warning",
            parent=styles["BodyText"],
            fontSize=11,
            leading=13,
            textColor=self.COLOR_WARNING,
            fontName="Helvetica-Bold"
        )
        
        self.s_danger = ParagraphStyle(
            "danger",
            parent=styles["BodyText"],
            fontSize=11,
            leading=13,
            textColor=self.COLOR_DANGER,
            fontName="Helvetica-Bold"
        )
        
        # Texto de tabla
        self.s_table_header = ParagraphStyle(
            "table_header",
            parent=styles["BodyText"],
            fontSize=9,
            leading=11,
            textColor=colors.white,
            fontName="Helvetica-Bold",
            alignment=TA_CENTER
        )
        
        self.s_table_cell = ParagraphStyle(
            "table_cell",
            parent=styles["BodyText"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#334155")
        )
    
    def _safe(self, valor, default="—"):
        """Convierte valor a string seguro"""
        if valor is None or valor == "":
            return default
        s = str(valor).strip()
        return s if s else default
    
    def _fmt_date(self, dt, with_time=False):
        """Formatea fecha"""
        if not dt:
            return "—"
        try:
            if with_time:
                return dt.strftime("%d/%m/%Y - %H:%M")
            return dt.strftime("%d/%m/%Y")
        except Exception:
            return str(dt)
    
    def _fmt_money(self, val):
        """Formatea dinero"""
        try:
            return f"${float(val):,.2f}"
        except Exception:
            return "$0.00"
    
    def _cliente_nombre(self, cliente):
        """Obtiene nombre completo del cliente"""
        if not cliente:
            return "Estudiante"
        
        # Intentar obtener nombre completo
        nc = getattr(cliente, "nombre_completo", None)
        if nc and str(nc).strip():
            return str(nc).strip()
        
        # Construir desde nombre y apellido
        nombre = str(getattr(cliente, "nombre", "") or "").strip()
        apellido = str(getattr(cliente, "apellido", "") or "").strip()
        full = f"{nombre} {apellido}".strip()
        
        return full if full else "Estudiante"
    
    def _get_estado_info(self, cliente):
        """Obtiene información completa del estado del estudiante"""
        # Estado general (activo/inactivo)
        activo = getattr(cliente, "activo", None)
        if isinstance(activo, bool):
            estado_general = "✓ ACTIVO" if activo else "✗ INACTIVO"
            color_general = self.COLOR_SUCCESS if activo else self.COLOR_DANGER
        else:
            estado_general = "✓ ACTIVO"
            color_general = self.COLOR_SUCCESS
        
        # Estado financiero
        estado_pago = getattr(cliente, "estado_pago", None)
        dias_rest = getattr(cliente, "dias_restantes", None)
        
        # Determinar días restantes numéricos
        try:
            dias_rest_n = int(dias_rest) if dias_rest is not None else None
        except (ValueError, TypeError):
            dias_rest_n = None
        
        # Estado financiero por defecto
        estado_fin = "✓ AL DÍA"
        estilo_fin = self.s_success
        
        # Analizar estado
        if estado_pago:
            ep = str(estado_pago).lower()
            
            if "venc" in ep:
                estado_fin = "⌛ VENCIDO"
                estilo_fin = self.s_danger
            elif "proximo" in ep or "por_vencer" in ep:
                estado_fin = "⚠️ POR VENCER"
                estilo_fin = self.s_warning
            elif "pendiente" in ep:
                estado_fin = "⏳ PENDIENTE"
                estilo_fin = self.s_warning
        else:
            # Análisis por días restantes
            if dias_rest_n is not None:
                if dias_rest_n < 0:
                    estado_fin = "⌛ VENCIDO"
                    estilo_fin = self.s_danger
                elif dias_rest_n <= 7:
                    estado_fin = "⚠️ POR VENCER"
                    estilo_fin = self.s_warning
        
        return {
            'estado_general': estado_general,
            'color_general': color_general,
            'estado_financiero': estado_fin,
            'estilo_financiero': estilo_fin
        }
    
    def _crear_tabla_info(self, filas, col_widths=(4.2*cm, 12.3*cm)):
        """Crea tabla de información con estilo mejorado"""
        data = []
        
        for label, value in filas:
            data.append([
                Paragraph(f"<b>{self._safe(label)}</b>", self.s_label),
                Paragraph(self._safe(value), self.s_value)
            ])
        
        tabla = Table(data, colWidths=list(col_widths))
        tabla.setStyle(TableStyle([
            # Alineación y padding
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            
            # Bordes sutiles
            ('LINEBELOW', (0, 0), (-1, -2), 0.5, self.COLOR_BORDER),
        ]))
        
        return tabla
    
    def _draw_header(self, canvas_obj, doc):
        """Dibuja encabezado en cada página"""
        canvas_obj.saveState()
        
        # Línea superior decorativa
        canvas_obj.setStrokeColor(self.COLOR_PRIMARY)
        canvas_obj.setLineWidth(3)
        canvas_obj.line(doc.leftMargin, A4[1] - 1.5*cm, 
                       A4[0] - doc.rightMargin, A4[1] - 1.5*cm)
        
        canvas_obj.restoreState()
    
    def _draw_footer(self, canvas_obj, doc):
        """Dibuja pie de página"""
        canvas_obj.saveState()
        
        # Línea inferior
        canvas_obj.setStrokeColor(self.COLOR_BORDER)
        canvas_obj.setLineWidth(0.5)
        canvas_obj.line(doc.leftMargin, 1.5*cm, 
                       A4[0] - doc.rightMargin, 1.5*cm)
        
        # Texto del pie
        canvas_obj.setFont('Helvetica', 8)
        canvas_obj.setFillColor(self.COLOR_SECONDARY)
        
        # Fecha de generación (izquierda)
        fecha_gen = datetime.now().strftime("%d/%m/%Y %H:%M")
        canvas_obj.drawString(doc.leftMargin, 1*cm, 
                            f"Generado: {fecha_gen}")
        
        # Número de página (derecha)
        canvas_obj.drawRightString(A4[0] - doc.rightMargin, 1*cm, 
                                  f"Página {doc.page}")
        
        canvas_obj.restoreState()
    
    def generar_reporte_estudiante(self, cliente, pagos=None, pago=None):
        """
        Genera reporte completo del estudiante
        
        Args:
            cliente: Objeto Cliente con toda la información
            pagos: Lista de pagos (opcional, se toma de cliente.pagos si no se proporciona)
            pago: Pago individual (no usado, mantener compatibilidad)
        
        Returns:
            BytesIO: Buffer con el PDF generado
        """
        buffer = io.BytesIO()
        
        # Configurar documento
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=2*cm,
            rightMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm,
            title=f"Reporte_{self._cliente_nombre(cliente)}",
            author=self.nombre_empresa
        )
        
        story = []
        
        # ============================================
        # ENCABEZADO
        # ============================================
        story.append(Paragraph(
            f"<b>{self._safe(self.nombre_empresa)}</b>",
            self.s_brand
        ))
        
        story.append(Paragraph(
            f"<b>{self.subtitulo_reporte}</b>",
            self.s_title
        ))
        
        story.append(Paragraph(
            "Información del Estudiante",
            self.s_subtitle
        ))
        
        story.append(Paragraph(
            f"<b>{self._cliente_nombre(cliente)}</b>",
            self.s_subtitle
        ))
        
        story.append(Paragraph(
            self._fmt_date(datetime.now(), with_time=True),
            self.s_subtitle
        ))
        
        story.append(Spacer(1, 12))
        
        # ============================================
        # SECCIÓN: DATOS PERSONALES
        # ============================================
        story.append(Paragraph(
            "■ <b>DATOS PERSONALES</b>",
            self.s_section
        ))
        
        # Obtener estado
        estado_info = self._get_estado_info(cliente)
        
        # Datos personales
        datos_personales = [
            ("Nombre", self._cliente_nombre(cliente)),
            ("Cédula", self._safe(getattr(cliente, "cedula", None))),
            ("Email", self._safe(getattr(cliente, "email", None))),
            ("Teléfono", self._safe(getattr(cliente, "telefono", None))),
            ("Dirección", self._safe(getattr(cliente, "direccion", None))),
            ("Estado", estado_info['estado_general'])
        ]
        
        story.append(self._crear_tabla_info(datos_personales))
        story.append(Spacer(1, 10))
        
        # ============================================
        # SECCIÓN: PROGRAMA ACADÉMICO
        # ============================================
        story.append(Paragraph(
            "■ <b>PROGRAMA ACADÉMICO</b>",
            self.s_section
        ))
        
        curso = getattr(cliente, "curso", None)
        
        if curso:
            programa = self._safe(getattr(curso, "nombre", None), "No asignado")
            mensualidad = self._fmt_money(getattr(curso, "precio_mensual", 0))
            duracion_meses = getattr(curso, "duracion_meses", None)
            duracion = f"{int(duracion_meses)} meses" if duracion_meses else "—"
            descripcion = self._safe(getattr(curso, "descripcion", None), "Sin descripción")
        else:
            programa = "No asignado"
            mensualidad = "$0.00"
            duracion = "—"
            descripcion = "—"
        
        datos_programa = [
            ("Programa", programa),
            ("Mensualidad", mensualidad),
            ("Duración", duracion),
            ("Descripción", descripcion)
        ]
        
        story.append(self._crear_tabla_info(datos_programa))
        story.append(Spacer(1, 10))
        
        # ============================================
        # SECCIÓN: ESTADO FINANCIERO
        # ============================================
        story.append(Paragraph(
            "■ <b>ESTADO FINANCIERO</b>",
            self.s_section
        ))
        
        # Fechas importantes
        fecha_insc = getattr(cliente, "fecha_registro", None) or getattr(cliente, "fecha_creacion", None)
        fecha_inicio = getattr(cliente, "fecha_inicio_clases", None) or getattr(cliente, "fecha_inicio", None)
        fecha_venc = getattr(cliente, "fecha_fin", None)
        
        datos_fechas = [
            ("Inscripción", self._fmt_date(fecha_insc)),
            ("Inicio Clases", self._fmt_date(fecha_inicio)),
            ("Vencimiento", self._fmt_date(fecha_venc))
        ]
        
        story.append(self._crear_tabla_info(datos_fechas))
        story.append(Spacer(1, 8))
        
        # Información financiera
        dias_rest = getattr(cliente, "dias_restantes", None)
        try:
            dias_rest_str = str(int(dias_rest)) if dias_rest is not None else "—"
        except (ValueError, TypeError):
            dias_rest_str = self._safe(dias_rest)
        
        mensualidades = int(getattr(cliente, "mensualidades_canceladas", 0) or 0)
        valor_insc = self._fmt_money(getattr(cliente, "valor_inscripcion", 0) or 0)
        
        # Total pagado
        total_pagado = getattr(cliente, "total_pagado", None)
        if total_pagado is None:
            try:
                pagos_list = pagos or getattr(cliente, "pagos", []) or []
                total_pagado = sum(float(p.monto or 0) for p in pagos_list)
            except Exception:
                total_pagado = 0.0
        
        # Saldo pendiente
        saldo = getattr(cliente, "saldo_pendiente", None)
        if saldo is None:
            total_programa = getattr(cliente, "total_programa", None)
            try:
                saldo = float(total_programa or 0) - float(total_pagado or 0)
                saldo = max(0.0, saldo)
            except Exception:
                saldo = 0.0
        
        datos_financieros = [
            ("Días Restantes", dias_rest_str),
            ("Mensualidades", str(mensualidades)),
            ("Inscripción", valor_insc),
            ("Total Pagado", self._fmt_money(total_pagado)),
            ("Saldo", self._fmt_money(saldo))
        ]
        
        story.append(self._crear_tabla_info(datos_financieros))
        story.append(Spacer(1, 10))
        
        # Estado financiero destacado
        story.append(Paragraph(
            f"<b>{estado_info['estado_financiero']}</b>",
            estado_info['estilo_financiero']
        ))
        
        story.append(Spacer(1, 14))
        
        # ============================================
        # SECCIÓN: HISTORIAL DE PAGOS
        # ============================================
        story.append(Paragraph(
            "■ <b>HISTORIAL DE PAGOS</b>",
            self.s_section
        ))
        
        # Obtener y ordenar pagos
        if pagos is None:
            pagos = getattr(cliente, "pagos", None)
        
        pagos_list = list(pagos) if pagos else []
        
        def _get_fecha_pago(p):
            return getattr(p, "fecha_pago", None) or getattr(p, "fecha", None) or datetime.min
        
        pagos_list.sort(key=_get_fecha_pago, reverse=True)
        
        # Crear tabla de pagos
        table_data = [[
            Paragraph("<b>Fecha</b>", self.s_table_header),
            Paragraph("<b>Monto</b>", self.s_table_header),
            Paragraph("<b>Método</b>", self.s_table_header),
            Paragraph("<b>Referencia</b>", self.s_table_header),
            Paragraph("<b>Período</b>", self.s_table_header)
        ]]
        
        total_pagos = 0.0
        
        for p in pagos_list:
            fecha = _get_fecha_pago(p)
            monto = float(getattr(p, "monto", 0) or 0)
            total_pagos += monto
            
            metodo = self._safe(getattr(p, "metodo_pago", None), "-")
            referencia = self._safe(getattr(p, "referencia", None), "-")
            periodo = self._safe(getattr(p, "periodo", None), "-")
            
            table_data.append([
                Paragraph(self._fmt_date(fecha), self.s_table_cell),
                Paragraph(self._fmt_money(monto), self.s_table_cell),
                Paragraph(metodo, self.s_table_cell),
                Paragraph(referencia, self.s_table_cell),
                Paragraph(periodo, self.s_table_cell)
            ])
        
        # Fila de total
        table_data.append([
            Paragraph("<b>TOTAL</b>", self.s_table_cell),
            Paragraph(f"<b>{self._fmt_money(total_pagos)}</b>", self.s_table_cell),
            Paragraph(f"<b>{len(pagos_list)} pagos</b>", self.s_table_cell),
            Paragraph("", self.s_table_cell),
            Paragraph("", self.s_table_cell)
        ])
        
        # Crear tabla
        tabla_pagos = Table(
            table_data,
            colWidths=[3.2*cm, 2.8*cm, 3.2*cm, 4*cm, 3.3*cm]
        )
        
        tabla_pagos.setStyle(TableStyle([
            # Encabezado
            ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_PRIMARY),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
            
            # Celdas
            ('FONTSIZE', (0, 1), (-1, -2), 8),
            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),  # Monto alineado a derecha
            ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
            
            # Líneas de separación
            ('LINEBELOW', (0, 0), (-1, 0), 1, self.COLOR_PRIMARY),
            ('GRID', (0, 1), (-1, -2), 0.5, self.COLOR_BORDER),
            
            # Fila de total
            ('BACKGROUND', (0, -1), (-1, -1), self.COLOR_LIGHT_BG),
            ('LINEABOVE', (0, -1), (-1, -1), 1.5, self.COLOR_PRIMARY),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            
            # Padding
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]))
        
        story.append(tabla_pagos)
        
        # ============================================
        # CONSTRUIR PDF
        # ============================================
        doc.build(story, onFirstPage=self._draw_header, onLaterPages=self._draw_header)
        
        buffer.seek(0)
        return buffer
    
    def generar_reporte_pagos_lista(self, pagos, filtros=None):
        """
        Genera reporte de lista de pagos
        
        Args:
            pagos: Lista de objetos Pago
            filtros: Diccionario con filtros aplicados (opcional)
        
        Returns:
            BytesIO: Buffer con el PDF generado
        """
        buffer = io.BytesIO()
        
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=2*cm,
            rightMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm,
            title="Reporte_Pagos",
            author=self.nombre_empresa
        )
        
        story = []
        
        # Encabezado
        story.append(Paragraph(
            f"<b>{self._safe(self.nombre_empresa)}</b>",
            self.s_brand
        ))
        
        story.append(Paragraph(
            "<b>REPORTE DE PAGOS</b>",
            self.s_title
        ))
        
        story.append(Paragraph(
            self._fmt_date(datetime.now(), with_time=True),
            self.s_subtitle
        ))
        
        # Mostrar filtros si existen
        if filtros:
            story.append(Spacer(1, 8))
            filtros_text = []
            
            if filtros.get('fecha_inicio'):
                filtros_text.append(f"Desde: {filtros['fecha_inicio']}")
            if filtros.get('fecha_fin'):
                filtros_text.append(f"Hasta: {filtros['fecha_fin']}")
            if filtros.get('estudiante'):
                filtros_text.append(f"Estudiante: {filtros['estudiante']}")
            if filtros.get('metodo'):
                filtros_text.append(f"Método: {filtros['metodo']}")
            
            if filtros_text:
                story.append(Paragraph(
                    f"<i>Filtros: {' | '.join(filtros_text)}</i>",
                    self.s_subtitle
                ))
        
        story.append(Spacer(1, 12))
        
        # Tabla de pagos
        table_data = [[
            Paragraph("<b>Fecha</b>", self.s_table_header),
            Paragraph("<b>Estudiante</b>", self.s_table_header),
            Paragraph("<b>Monto</b>", self.s_table_header),
            Paragraph("<b>Método</b>", self.s_table_header),
            Paragraph("<b>Referencia</b>", self.s_table_header),
            Paragraph("<b>Período</b>", self.s_table_header)
        ]]
        
        total = 0.0
        
        for p in (pagos or []):
            fecha = getattr(p, "fecha_pago", None) or getattr(p, "fecha", None)
            cliente = getattr(p, "cliente", None)
            estudiante = self._cliente_nombre(cliente) if cliente else "—"
            
            monto = float(getattr(p, "monto", 0) or 0)
            total += monto
            
            metodo = self._safe(getattr(p, "metodo_pago", None), "-")
            referencia = self._safe(getattr(p, "referencia", None), "-")
            periodo = self._safe(getattr(p, "periodo", None), "-")
            
            # Truncar nombres largos
            if len(estudiante) > 30:
                estudiante = estudiante[:27] + "..."
            if len(referencia) > 18:
                referencia = referencia[:15] + "..."
            
            table_data.append([
                Paragraph(self._fmt_date(fecha), self.s_table_cell),
                Paragraph(estudiante, self.s_table_cell),
                Paragraph(self._fmt_money(monto), self.s_table_cell),
                Paragraph(metodo, self.s_table_cell),
                Paragraph(referencia, self.s_table_cell),
                Paragraph(periodo, self.s_table_cell)
            ])
        
        # Fila de total
        table_data.append([
            Paragraph("<b>TOTAL</b>", self.s_table_cell),
            Paragraph("", self.s_table_cell),
            Paragraph(f"<b>{self._fmt_money(total)}</b>", self.s_table_cell),
            Paragraph("", self.s_table_cell),
            Paragraph("", self.s_table_cell),
            Paragraph(f"<b>{len(pagos or [])} pagos</b>", self.s_table_cell)
        ])
        
        tabla = Table(
            table_data,
            colWidths=[2.6*cm, 5.8*cm, 2.6*cm, 2.8*cm, 3.2*cm, 2.5*cm]
        )
        
        tabla.setStyle(TableStyle([
            # Encabezado
            ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_PRIMARY),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            
            # Celdas
            ('FONTSIZE', (0, 1), (-1, -2), 8),
            ('ALIGN', (2, 1), (2, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Líneas
            ('LINEBELOW', (0, 0), (-1, 0), 1, self.COLOR_PRIMARY),
            ('GRID', (0, 1), (-1, -2), 0.5, self.COLOR_BORDER),
            
            # Fila de total
            ('BACKGROUND', (0, -1), (-1, -1), self.COLOR_LIGHT_BG),
            ('LINEABOVE', (0, -1), (-1, -1), 1.5, self.COLOR_PRIMARY),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            
            # Padding
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]))
        
        story.append(tabla)
        
        # Construir PDF
        doc.build(story, onFirstPage=self._draw_header, onLaterPages=self._draw_header)
        
        buffer.seek(0)
        return buffer


# Instancia global para importar
pdf_generator = PDFGenerator()