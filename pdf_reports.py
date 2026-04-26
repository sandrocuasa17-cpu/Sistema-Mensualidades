# -*- coding: utf-8 -*-
"""pdf_reports.py — Premium CCP Edition

Diseño institucional de alto nivel:
  - Encabezado con franja lateral azul + logo + datos institución
  - Tipografía jerárquica, espaciado cuidadoso
  - Tablas con cabeceras degradadas, filas alternas y bordes redondeados
  - Pie de página con número de página y sello institucional
  - Paleta: Azul marino #0D3B8E, Verde #2E7D32, Gris #F5F7FA
"""

import io
import os
from datetime import datetime, date

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Image, KeepTogether, PageBreak
)
from reportlab.platypus.flowables import Flowable
from reportlab.pdfgen import canvas as pdfcanvas

# ═══════════════════════════════════════════════════════════════════════════════
# PALETA INSTITUCIONAL
# ═══════════════════════════════════════════════════════════════════════════════
C_AZUL_NAVY  = colors.HexColor("#0D3B8E")   # Azul marino principal
C_AZUL_MED   = colors.HexColor("#1A56C4")   # Azul medio
C_AZUL_LIGHT = colors.HexColor("#EBF0FB")   # Azul muy claro (fondo)
C_AZUL_PALE  = colors.HexColor("#F0F4FF")   # Azul pálido (fila par)
C_VERDE      = colors.HexColor("#2E7D32")   # Verde institucional
C_VERDE_LITE = colors.HexColor("#E8F5E9")   # Verde pálido
C_GRIS_BG    = colors.HexColor("#F5F7FA")   # Fondo gris suave
C_GRIS_LINE  = colors.HexColor("#D0D8E8")   # Líneas de tabla
C_GRIS_TEXT  = colors.HexColor("#374151")   # Texto principal
C_GRIS_SOFT  = colors.HexColor("#6B7280")   # Texto secundario
C_WHITE      = colors.white
C_GOLD       = colors.HexColor("#F59E0B")   # Acento dorado

PAGE_W, PAGE_H = A4
MARGIN_X = 1.6 * cm
MARGIN_Y = 1.6 * cm
CONTENT_W = PAGE_W - 2 * MARGIN_X


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════
def _safe(v, default="—"):
    if v is None: return default
    s = str(v).strip()
    return s if s else default

def _money(v):
    try:    return f"${float(v or 0):,.2f}"
    except: return _safe(v)

def _date(v, t=False):
    if v is None: return "—"
    try:
        if isinstance(v, datetime): dt = v
        elif isinstance(v, date):   dt = datetime(v.year, v.month, v.day)
        else:                        dt = datetime.fromisoformat(str(v))
        return dt.strftime("%d/%m/%Y %H:%M" if t else "%d/%m/%Y")
    except: return _safe(v)

def _logo():
    base = os.path.dirname(os.path.abspath(__file__))
    for p in [
        os.path.join(base, "static", "img", "logo.jpg"),
        os.path.join(base, "static", "img", "logo.png"),
        os.path.join(base, "logo.jpg"),
        "/mnt/user-data/uploads/logo.jpg",
    ]:
        if os.path.exists(p): return p
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# FLOWABLE: LÍNEA DECORATIVA
# ═══════════════════════════════════════════════════════════════════════════════
class ColorBar(Flowable):
    """Barra decorativa de color sólido."""
    def __init__(self, width, height, color, radius=0):
        Flowable.__init__(self)
        self.bar_w = width
        self.bar_h = height
        self.color = color
        self.radius = radius
        self.width = width
        self.height = height

    def draw(self):
        self.canv.setFillColor(self.color)
        if self.radius:
            self.canv.roundRect(0, 0, self.bar_w, self.bar_h, self.radius, fill=1, stroke=0)
        else:
            self.canv.rect(0, 0, self.bar_w, self.bar_h, fill=1, stroke=0)


# ═══════════════════════════════════════════════════════════════════════════════
# CANVAS CALLBACK: encabezado/pie repetidos en cada página
# ═══════════════════════════════════════════════════════════════════════════════
class _PageTemplate:
    """Callback para canvas.build() que dibuja pie de página en cada hoja."""
    def __init__(self, generator):
        self.gen = generator
        self._page = [0]

    def __call__(self, canv, doc):
        self._page[0] += 1
        self._draw_footer(canv, doc, self._page[0])

    def _draw_footer(self, canv, doc, page_num):
        canv.saveState()
        footer_y = MARGIN_Y - 0.8 * cm
        w = PAGE_W - 2 * MARGIN_X

        # Línea superior del pie
        canv.setStrokeColor(C_AZUL_NAVY)
        canv.setLineWidth(1.2)
        canv.line(MARGIN_X, footer_y + 0.5*cm, MARGIN_X + w, footer_y + 0.5*cm)

        # Texto izquierda
        canv.setFont("Helvetica", 7)
        canv.setFillColor(C_GRIS_SOFT)
        inst = self.gen.nombre_empresa
        canv.drawString(MARGIN_X, footer_y + 0.15*cm, inst)

        # Texto derecha — número de página
        canv.setFont("Helvetica-Bold", 7)
        canv.setFillColor(C_AZUL_NAVY)
        pag_text = f"Página {page_num}"
        canv.drawRightString(MARGIN_X + w, footer_y + 0.15*cm, pag_text)

        canv.restoreState()


# ═══════════════════════════════════════════════════════════════════════════════
# GENERADOR PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════
class PDFGenerator:

    def __init__(self, nombre_empresa="Centro de Capacitación Profesional del Norte"):
        self.nombre_empresa = nombre_empresa
        self.eslogan_empresa = "Calidad y Profesionalismo"
        self._styles()

    def _styles(self):
        base = getSampleStyleSheet()

        def S(name, **kw):
            return ParagraphStyle(name, parent=base["Normal"], **kw)

        # Institución
        self.sInstNombre = S("InstNombre",
            fontSize=15, leading=18, textColor=C_AZUL_NAVY,
            fontName="Helvetica-Bold")
        self.sInstSlogan = S("InstSlogan",
            fontSize=9, leading=12, textColor=C_VERDE,
            fontName="Helvetica-Oblique")
        self.sInstMeta = S("InstMeta",
            fontSize=7.5, leading=10, textColor=C_GRIS_SOFT,
            fontName="Helvetica")

        # Título documento
        self.sDocTitulo = S("DocTitulo",
            fontSize=13, leading=16, textColor=C_WHITE,
            fontName="Helvetica-Bold", alignment=TA_CENTER)

        # Sección
        self.sSeccion = S("Seccion",
            fontSize=9, leading=12, textColor=C_WHITE,
            fontName="Helvetica-Bold", leftIndent=4)

        # KV
        self.sKLabel = S("KLabel",
            fontSize=8, leading=11, textColor=C_AZUL_NAVY,
            fontName="Helvetica-Bold")
        self.sKValue = S("KValue",
            fontSize=8.5, leading=11, textColor=C_GRIS_TEXT,
            fontName="Helvetica")

        # Tabla
        self.sTHead = S("THead",
            fontSize=8, leading=11, textColor=C_WHITE,
            fontName="Helvetica-Bold", alignment=TA_CENTER)
        self.sTCell = S("TCell",
            fontSize=7.5, leading=10, textColor=C_GRIS_TEXT,
            fontName="Helvetica")
        self.sTCellC = S("TCellC",
            fontSize=7.5, leading=10, textColor=C_GRIS_TEXT,
            fontName="Helvetica", alignment=TA_CENTER)
        self.sTMoney = S("TMoney",
            fontSize=8, leading=11, textColor=C_VERDE,
            fontName="Helvetica-Bold", alignment=TA_CENTER)

        # Totales
        self.sTotal = S("Total",
            fontSize=11, leading=14, textColor=C_AZUL_NAVY,
            fontName="Helvetica-Bold", alignment=TA_RIGHT)
        self.sTotalBox = S("TotalBox",
            fontSize=13, leading=16, textColor=C_WHITE,
            fontName="Helvetica-Bold", alignment=TA_CENTER)

        # Misc
        self.sNormal = base["Normal"]
        self.sSmall  = S("Small",
            fontSize=8, leading=11, textColor=C_GRIS_SOFT,
            fontName="Helvetica")

    # ── helpers ───────────────────────────────────────────────────────────────

    def _nombre(self, c):
        v = getattr(c, "nombre", None)
        if v:
            ap = getattr(c, "apellido", None)
            return f"{v} {ap}".strip() if ap else str(v)
        return "Estudiante"

    def _concepto(self, p):
        c = (getattr(p, "concepto", None) or "auto").lower()
        return {"auto":"Distribución automática","inscripcion":"Inscripción",
                "mensualidad":"Mensualidad","unico":"Pago único"}.get(c, c.capitalize())

    # ── componentes ───────────────────────────────────────────────────────────

    def _encabezado(self, titulo):
        """Bloque de encabezado premium."""
        logo_p = _logo()
        story  = []

        # ── Fila logo + datos institución
        logo_cell = Image(logo_p, 2.8*cm, 2.8*cm) if logo_p else \
                    Paragraph("<b>CCP</b>", self.sInstNombre)

        info_col = [
            Paragraph(_safe(self.nombre_empresa), self.sInstNombre),
            Spacer(1, 3),
            Paragraph(_safe(self.eslogan_empresa), self.sInstSlogan),
            Spacer(1, 5),
            Paragraph(f"Fecha de emisión: <b>{_date(datetime.now(), t=True)}</b>", self.sInstMeta),
        ]

        top = Table([[logo_cell, info_col]],
                    colWidths=[3.2*cm, CONTENT_W - 3.2*cm])
        top.setStyle(TableStyle([
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("LEFTPADDING",(0,0),(-1,-1),0),
            ("RIGHTPADDING",(0,0),(-1,-1),0),
            ("TOPPADDING",(0,0),(-1,-1),0),
            ("BOTTOMPADDING",(0,0),(-1,-1),0),
        ]))
        story.append(top)
        story.append(Spacer(1, 8))

        # ── Línea doble decorativa
        story.append(HRFlowable(width="100%", thickness=3,
                                color=C_AZUL_NAVY, spaceAfter=2))
        story.append(HRFlowable(width="100%", thickness=1,
                                color=C_GOLD, spaceAfter=8))

        # ── Barra de título
        tbar = Table([[Paragraph(titulo, self.sDocTitulo)]],
                     colWidths=[CONTENT_W])
        tbar.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1), C_AZUL_NAVY),
            ("TOPPADDING",(0,0),(-1,-1), 9),
            ("BOTTOMPADDING",(0,0),(-1,-1), 9),
            ("LEFTPADDING",(0,0),(-1,-1), 12),
            ("RIGHTPADDING",(0,0),(-1,-1), 12),
        ]))
        story.append(tbar)
        story.append(Spacer(1, 12))
        return story

    def _barra_seccion(self, texto, color=None):
        color = color or C_AZUL_MED
        t = Table([[Paragraph(f"  {texto}", self.sSeccion)]],
                  colWidths=[CONTENT_W])
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1), color),
            ("TOPPADDING",(0,0),(-1,-1), 5),
            ("BOTTOMPADDING",(0,0),(-1,-1), 5),
            ("LEFTPADDING",(0,0),(-1,-1), 8),
        ]))
        return t

    def _tabla_kv(self, filas, cols=2):
        col_lbl = 3.8 * cm
        col_val = (CONTENT_W / cols) - col_lbl
        rows = []
        for i in range(0, len(filas), cols):
            row = []
            for j in range(cols):
                if i+j < len(filas):
                    k, v = filas[i+j]
                    row += [Paragraph(k, self.sKLabel),
                            Paragraph(_safe(v), self.sKValue)]
                else:
                    row += ["", ""]
            rows.append(row)

        t = Table(rows, colWidths=[col_lbl, col_val]*cols)
        style = [
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("TOPPADDING",(0,0),(-1,-1),5),
            ("BOTTOMPADDING",(0,0),(-1,-1),5),
            ("LEFTPADDING",(0,0),(-1,-1),8),
            ("RIGHTPADDING",(0,0),(-1,-1),8),
            ("LINEBELOW",(0,0),(-1,-1),0.4, C_GRIS_LINE),
        ]
        for r in range(len(rows)):
            style.append(("BACKGROUND",(0,r),(-1,r),
                          C_AZUL_LIGHT if r%2==0 else C_WHITE))
        t.setStyle(TableStyle(style))
        return t

    def _tabla_pagos(self, pagos, con_estudiante=False):
        if con_estudiante:
            hdrs = ["Fecha","Estudiante","Monto","Concepto","Método","Periodo","Ref."]
            cws  = [2.6*cm, 4.6*cm, 1.9*cm, 3.1*cm, 2.2*cm, 2.0*cm, 2.6*cm]
        else:
            hdrs = ["Fecha","Monto","Concepto","Método","Periodo","Referencia"]
            cws  = [3.0*cm, 2.2*cm, 4.6*cm, 3.0*cm, 2.2*cm, 4.0*cm]

        data = [[Paragraph(h, self.sTHead) for h in hdrs]]

        for p in pagos or []:
            fec = _date(getattr(p,"fecha_pago",None), t=True)
            mon = float(getattr(p,"monto",0) or 0)
            con = self._concepto(p)
            met = _safe(getattr(p,"metodo_pago",None))
            per = _safe(getattr(p,"periodo",None))
            ref = _safe(getattr(p,"referencia",None))

            if con_estudiante:
                cli = getattr(p,"cliente",None)
                est = self._nombre(cli) if cli else "—"
                row = [
                    Paragraph(fec, self.sTCellC),
                    Paragraph(_safe(est), self.sTCell),
                    Paragraph(_money(mon), self.sTMoney),
                    Paragraph(con, self.sTCell),
                    Paragraph(met, self.sTCellC),
                    Paragraph(per, self.sTCellC),
                    Paragraph(ref, self.sTCellC),
                ]
            else:
                row = [
                    Paragraph(fec, self.sTCellC),
                    Paragraph(_money(mon), self.sTMoney),
                    Paragraph(con, self.sTCell),
                    Paragraph(met, self.sTCellC),
                    Paragraph(per, self.sTCellC),
                    Paragraph(ref, self.sTCell),
                ]
            data.append(row)

        t = Table(data, colWidths=cws, repeatRows=1)
        style = [
            # Cabecera
            ("BACKGROUND",(0,0),(-1,0), C_AZUL_NAVY),
            ("TOPPADDING",(0,0),(-1,0), 7),
            ("BOTTOMPADDING",(0,0),(-1,0), 7),
            # Cuerpo
            ("GRID",(0,0),(-1,-1), 0.35, C_GRIS_LINE),
            ("VALIGN",(0,0),(-1,-1), "MIDDLE"),
            ("TOPPADDING",(0,1),(-1,-1), 5),
            ("BOTTOMPADDING",(0,1),(-1,-1), 5),
            ("LEFTPADDING",(0,0),(-1,-1), 5),
            ("RIGHTPADDING",(0,0),(-1,-1), 5),
            # Línea inferior cabecera
            ("LINEBELOW",(0,0),(-1,0), 2, C_GOLD),
        ]
        for r in range(1, len(data)):
            style.append(("BACKGROUND",(0,r),(-1,r),
                          C_WHITE if r%2==0 else C_AZUL_PALE))
        t.setStyle(TableStyle(style))
        return t

    def _caja_total(self, label, valor):
        t = Table(
            [[Paragraph(f"{label}<br/><font size='16'>{valor}</font>",
                        self.sTotalBox)]],
            colWidths=[CONTENT_W],
        )
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1), C_AZUL_NAVY),
            ("TOPPADDING",(0,0),(-1,-1), 10),
            ("BOTTOMPADDING",(0,0),(-1,-1), 10),
            ("ALIGN",(0,0),(-1,-1),"CENTER"),
        ]))
        return t

    def _tarjetas_resumen(self, n, total):
        """Dos tarjetas: transacciones (azul) y total (verde)."""
        sN = ParagraphStyle("CardN", parent=self.sDocTitulo,
                            fontSize=22, leading=26)
        sL = ParagraphStyle("CardL", parent=self.sDocTitulo,
                            fontSize=8, leading=11,
                            textColor=colors.HexColor("#DBEAFE"))
        sV = ParagraphStyle("CardV", parent=self.sDocTitulo,
                            fontSize=20, leading=24, textColor=C_WHITE,
                            fontName="Helvetica-Bold")
        sLV= ParagraphStyle("CardLV",parent=self.sDocTitulo,
                            fontSize=8, leading=11,
                            textColor=colors.HexColor("#D1FAE5"))

        t = Table([[
            [Paragraph(str(n), sN), Paragraph("TRANSACCIONES", sL)],
            [Paragraph(_money(total), sV), Paragraph("TOTAL RECAUDADO", sLV)],
        ]], colWidths=[CONTENT_W/2, CONTENT_W/2])
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(0,0), C_AZUL_MED),
            ("BACKGROUND",(1,0),(1,0), C_VERDE),
            ("TOPPADDING",(0,0),(-1,-1), 14),
            ("BOTTOMPADDING",(0,0),(-1,-1), 14),
            ("ALIGN",(0,0),(-1,-1),"CENTER"),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("LINEAFTER",(0,0),(0,-1), 2, C_WHITE),
        ]))
        return t

    def _build(self, story, buffer):
        tpl = _PageTemplate(self)
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=MARGIN_X, rightMargin=MARGIN_X,
            topMargin=MARGIN_Y, bottomMargin=MARGIN_Y + 0.8*cm,
        )
        doc.build(story, onFirstPage=tpl, onLaterPages=tpl)

    # ═════════════════════════════════════════════════════════════════════════
    # REPORTE ESTUDIANTE
    # ═════════════════════════════════════════════════════════════════════════
    def generar_reporte_estudiante(self, cliente, pagos=None, pago=None):
        if pagos is None:
            try:    pagos = list(getattr(cliente, "pagos", []))
            except: pagos = []

        buf = io.BytesIO()
        story = []

        story += self._encabezado("ESTADO DE CUENTA — ESTUDIANTE")

        # ── Datos personales
        story.append(KeepTogether([
            self._barra_seccion("Información del Estudiante"),
            Spacer(1,6),
            self._tabla_kv([
                ("Nombre completo",    self._nombre(cliente)),
                ("Cédula / ID",        _safe(getattr(cliente,"cedula",None))),
                ("Correo electrónico", _safe(getattr(cliente,"email",None))),
                ("Teléfono",           _safe(getattr(cliente,"telefono",None))),
                ("Dirección",          _safe(getattr(cliente,"direccion",None))),
                ("Estado",             "Activo" if getattr(cliente,"activo",True) else "Inactivo"),
            ]),
            Spacer(1,12),
        ]))

        # ── Programa académico
        curso = getattr(cliente, "curso", None)
        story.append(KeepTogether([
            self._barra_seccion("Programa Académico"),
            Spacer(1,6),
            self._tabla_kv([
                ("Curso / Programa",     _safe(getattr(curso,"nombre",None),"No asignado")),
                ("Mensualidad",          _money(getattr(curso,"precio_mensual",0)) if curso else "—"),
                ("Valor de inscripción", _money(getattr(curso,"precio_inscripcion",0)) if curso else "—"),
                ("Fecha de inicio",      _date(getattr(cliente,"fecha_inicio",None))),
                ("Fecha de vencimiento", _date(getattr(cliente,"fecha_fin",None))),
                ("Mensualidades pagas",  _safe(getattr(cliente,"mensualidades_canceladas",None),"0")),
            ]),
            Spacer(1,12),
        ]))

        # ── Último pago
        if pago is not None:
            story.append(KeepTogether([
                self._barra_seccion("Último Pago Registrado", color=C_VERDE),
                Spacer(1,6),
                self._tabla_kv([
                    ("Monto",      _money(getattr(pago,"monto",0))),
                    ("Fecha",      _date(getattr(pago,"fecha_pago",None),t=True)),
                    ("Concepto",   self._concepto(pago)),
                    ("Método",     _safe(getattr(pago,"metodo_pago",None))),
                    ("Referencia", _safe(getattr(pago,"referencia",None))),
                    ("Periodo",    _safe(getattr(pago,"periodo",None))),
                ]),
                Spacer(1,12),
            ]))

        # ── Historial
        total = sum(float(getattr(p,"monto",0) or 0) for p in pagos) if pagos else 0
        story.append(self._barra_seccion(f"Historial de Pagos  ({len(pagos)} registros)"))
        story.append(Spacer(1,6))

        if pagos:
            story.append(self._tabla_pagos(pagos, con_estudiante=False))
            story.append(Spacer(1,10))
            story.append(self._caja_total("TOTAL PAGADO", _money(total)))
        else:
            story.append(Paragraph("No hay pagos registrados.", self.sSmall))

        story.append(Spacer(1,8))

        self._build(story, buf)
        buf.seek(0)
        return buf

    # ═════════════════════════════════════════════════════════════════════════
    # REPORTE DE PAGOS (LISTA)
    # ═════════════════════════════════════════════════════════════════════════
    def generar_reporte_pagos(self, pagos, filtros=None):
        filtros = filtros or {}
        buf     = io.BytesIO()
        story   = []

        story += self._encabezado("REPORTE GENERAL DE PAGOS")

        # Tarjetas de resumen
        total = sum(float(getattr(p,"monto",0) or 0) for p in (pagos or []))
        n     = len(pagos or [])
        story.append(self._tarjetas_resumen(n, total))
        story.append(Spacer(1,12))

        # Filtros
        if filtros:
            story.append(self._barra_seccion("Filtros Aplicados"))
            story.append(Spacer(1,6))
            story.append(self._tabla_kv(
                [(k.replace("_"," ").title(), str(v)) for k,v in filtros.items()],
                cols=2,
            ))
            story.append(Spacer(1,12))

        # Tabla de transacciones
        story.append(self._barra_seccion(f"Detalle de Transacciones  ({n} registros)"))
        story.append(Spacer(1,6))

        if pagos:
            story.append(self._tabla_pagos(pagos, con_estudiante=True))
            story.append(Spacer(1,10))
            story.append(self._caja_total("TOTAL RECAUDADO", _money(total)))
        else:
            story.append(Paragraph("No hay pagos para el período seleccionado.", self.sSmall))

        story.append(Spacer(1,8))

        self._build(story, buf)
        buf.seek(0)
        return buf

    # Alias requerido por app.py
    generar_reporte_pagos_lista = generar_reporte_pagos


# Instancia global
pdf_generator = PDFGenerator()