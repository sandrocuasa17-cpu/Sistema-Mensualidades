# -*- coding: utf-8 -*-
"""pdf_reports.py (FIX DEFINITIVO)

Exporta `pdf_generator`.

El archivo anterior estaba truncado (SyntaxError). Por eso:
- `from pdf_reports import pdf_generator` fallaba
- email_service enviaba el correo SIN PDF (atrapaba el ImportError)

Este archivo está hecho para ser IMPORTABLE siempre.
"""

import io
from datetime import datetime, date

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


def _safe(value, default="—"):
    if value is None:
        return default
    s = str(value).strip()
    return s if s else default


def _fmt_money(value):
    try:
        n = float(value or 0)
    except Exception:
        return _safe(value)
    return f"${n:,.2f}"


def _fmt_date(value, with_time=False):
    if value is None:
        return "—"
    try:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, date):
            dt = datetime(value.year, value.month, value.day)
        else:
            dt = datetime.fromisoformat(str(value))
        return dt.strftime("%d/%m/%Y %H:%M" if with_time else "%d/%m/%Y")
    except Exception:
        return _safe(value)


class PDFGenerator:
    """Generador de PDFs (no depende de Flask)."""

    def __init__(self, nombre_empresa="Sistema de Mensualidades"):
        self.nombre_empresa = nombre_empresa
        self.subtitulo_reporte = "Reporte de Estudiante"
        base = getSampleStyleSheet()
        self.s_brand = ParagraphStyle("brand", parent=base["Title"], fontSize=16, leading=18, spaceAfter=6)
        self.s_title = ParagraphStyle("title", parent=base["Heading2"], fontSize=12, leading=14, spaceAfter=6)
        self.s_section = ParagraphStyle("section", parent=base["Heading3"], fontSize=11, leading=13, spaceBefore=10, spaceAfter=6)
        self.s_small = ParagraphStyle("small", parent=base["Normal"], fontSize=9, leading=11)
        self.s_normal = base["Normal"]

    def _cliente_nombre(self, cliente):
        for attr in ("nombre_completo", "nombre", "nombres"):
            v = getattr(cliente, attr, None)
            if v:
                if attr == "nombre":
                    ap = getattr(cliente, "apellido", None)
                    return (f"{v} {ap}").strip() if ap else str(v)
                return str(v)
        return "Estudiante"

    def _pago_concepto(self, pago):
        concepto = (getattr(pago, "concepto", None) or "auto").lower()
        return {
            "auto": "Distribución automática",
            "inscripcion": "Inscripción",
            "mensualidad": "Mensualidad",
            "unico": "Pago único",
        }.get(concepto, _safe(concepto))

    def _tabla_kv(self, filas, col_widths=(4.3*cm, 11.7*cm)):
        data = [[Paragraph(f"<b>{_safe(k)}</b>", self.s_small), Paragraph(_safe(v), self.s_small)] for k, v in filas]
        t = Table(data, colWidths=list(col_widths))
        t.setStyle(TableStyle([
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("LINEBELOW", (0,0), (-1,-1), 0.25, colors.lightgrey),
            ("LEFTPADDING", (0,0), (-1,-1), 2),
            ("RIGHTPADDING", (0,0), (-1,-1), 2),
            ("TOPPADDING", (0,0), (-1,-1), 3),
            ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ]))
        return t

    def _tabla_pagos(self, pagos):
        header = ["Fecha", "Monto", "Concepto", "Método", "Ref."]
        data = [[Paragraph(f"<b>{h}</b>", self.s_small) for h in header]]
        for p in pagos or []:
            data.append([
                Paragraph(_fmt_date(getattr(p, "fecha_pago", None), with_time=True), self.s_small),
                Paragraph(_fmt_money(getattr(p, "monto", 0)), self.s_small),
                Paragraph(_safe(self._pago_concepto(p)), self.s_small),
                Paragraph(_safe(getattr(p, "metodo_pago", None), "—"), self.s_small),
                Paragraph(_safe(getattr(p, "referencia", None), "—"), self.s_small),
            ])
        t = Table(data, colWidths=[3.2*cm, 2.2*cm, 4.0*cm, 3.0*cm, 3.6*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
            ("LINEBELOW", (0,0), (-1,0), 0.5, colors.grey),
            ("GRID", (0,0), (-1,-1), 0.25, colors.lightgrey),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
        ]))
        return t

    def generar_reporte_estudiante(self, cliente, pagos=None, pago=None):
        if pagos is None:
            try:
                pagos = list(getattr(cliente, "pagos", []))
            except Exception:
                pagos = []
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
        story = []
        story.append(Paragraph(_safe(self.nombre_empresa), self.s_brand))
        story.append(Paragraph(_safe(self.subtitulo_reporte), self.s_title))
        story.append(Paragraph(f"<b>Estudiante:</b> {_safe(self._cliente_nombre(cliente))}", self.s_normal))
        story.append(Paragraph(f"<b>Generado:</b> {_fmt_date(datetime.now(), with_time=True)}", self.s_small))
        story.append(Spacer(1, 12))
        story.append(Paragraph("Datos personales", self.s_section))
        story.append(self._tabla_kv([
            ("Cédula", _safe(getattr(cliente, "cedula", None))),
            ("Email", _safe(getattr(cliente, "email", None))),
            ("Teléfono", _safe(getattr(cliente, "telefono", None))),
            ("Dirección", _safe(getattr(cliente, "direccion", None))),
        ]))
        story.append(Spacer(1, 10))
        story.append(Paragraph("Programa / Membresía", self.s_section))
        curso = getattr(cliente, "curso", None)
        story.append(self._tabla_kv([
            ("Curso", _safe(getattr(curso, "nombre", None), "No asignado")),
            ("Mensualidad", _fmt_money(getattr(curso, "precio_mensual", 0)) if curso else "—"),
            ("Inscripción", _fmt_money(getattr(curso, "precio_inscripcion", 0)) if curso else "—"),
            ("Fecha inicio", _fmt_date(getattr(cliente, "fecha_inicio", None))),
            ("Fecha vencimiento", _fmt_date(getattr(cliente, "fecha_fin", None))),
            ("Mensualidades pagadas", _safe(getattr(cliente, "mensualidades_canceladas", None), "0")),
        ]))
        story.append(Spacer(1, 10))
        if pago is not None:
            story.append(Paragraph("Pago registrado", self.s_section))
            story.append(self._tabla_kv([
                ("Monto", _fmt_money(getattr(pago, "monto", 0))),
                ("Fecha", _fmt_date(getattr(pago, "fecha_pago", None), with_time=True)),
                ("Concepto", self._pago_concepto(pago)),
                ("Método", _safe(getattr(pago, "metodo_pago", None))),
                ("Referencia", _safe(getattr(pago, "referencia", None))),
                ("Periodo", _safe(getattr(pago, "periodo", None))),
            ]))
            story.append(Spacer(1, 10))
        story.append(Paragraph("Historial de pagos", self.s_section))
        if pagos:
            story.append(self._tabla_pagos(pagos))
        else:
            story.append(Paragraph("No hay pagos registrados.", self.s_small))
        doc.build(story)
        buffer.seek(0)
        return buffer

    def generar_reporte_pagos(self, pagos, filtros=None):
        filtros = filtros or {}
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
        story = []
        story.append(Paragraph(_safe(self.nombre_empresa), self.s_brand))
        story.append(Paragraph("Reporte de Pagos", self.s_title))
        story.append(Paragraph(f"Generado: {_fmt_date(datetime.now(), with_time=True)}", self.s_small))
        story.append(Spacer(1, 10))
        if filtros:
            story.append(Paragraph("Filtros", self.s_section))
            story.append(self._tabla_kv([(k, str(v)) for k, v in filtros.items()]))
            story.append(Spacer(1, 10))
        header = ["Fecha", "Estudiante", "Monto", "Concepto", "Método", "Ref."]
        data = [[Paragraph(f"<b>{h}</b>", self.s_small) for h in header]]
        total = 0.0
        for p in pagos or []:
            cli = getattr(p, "cliente", None)
            estudiante = self._cliente_nombre(cli) if cli else "—"
            monto = float(getattr(p, "monto", 0) or 0)
            total += monto
            data.append([
                Paragraph(_fmt_date(getattr(p, "fecha_pago", None), with_time=True), self.s_small),
                Paragraph(_safe(estudiante), self.s_small),
                Paragraph(_fmt_money(monto), self.s_small),
                Paragraph(_safe(self._pago_concepto(p)), self.s_small),
                Paragraph(_safe(getattr(p, "metodo_pago", None), "—"), self.s_small),
                Paragraph(_safe(getattr(p, "referencia", None), "—"), self.s_small),
            ])
        t = Table(data, colWidths=[3.1*cm, 5.0*cm, 2.2*cm, 3.4*cm, 2.6*cm, 2.7*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
            ("GRID", (0,0), (-1,-1), 0.25, colors.lightgrey),
            ("LINEBELOW", (0,0), (-1,0), 0.5, colors.grey),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
        ]))
        story.append(t)
        story.append(Spacer(1, 10))
        story.append(Paragraph(f"<b>Total:</b> {_fmt_money(total)}", self.s_title))
        doc.build(story)
        buffer.seek(0)
        return buffer


pdf_generator = PDFGenerator()
