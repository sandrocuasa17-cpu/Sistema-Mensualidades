# -*- coding: utf-8 -*-
"""
Reportes Excel Mejorados - Sistema de Mensualidades
===================================================

Este módulo genera un Excel MULTI-HOJA (reporte completo) con formato profesional:

1) 📊 Resumen (KPIs gerenciales)
2) 👥 Estudiantes (control académico/financiero)
3) 💳 Pagos (auditoría / contabilidad)
4) 🚨 Morosos y Vencidos (cobranza)
5) 📚 Cursos (ingresos y proyección)

Compatible con:
- Cliente: id, nombre_completo, cedula, email, telefono, activo, fecha_registro, fecha_inicio_clases, fecha_inicio, fecha_fin,
          dias_restantes (propiedad), mensualidades_canceladas, valor_inscripcion, curso (relación)
- Curso: nombre, precio_mensual, precio_inscripcion, activo
- Pago: id, fecha_pago, monto, metodo_pago, referencia, periodo, cliente (relación)

Recomendación: úsalo como reemplazo de tu excel_reports.py actual.
"""

import io
from datetime import datetime
from collections import defaultdict

import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter


def _money(v):
    try:
        return float(v or 0)
    except Exception:
        return 0.0


class ExcelReportGenerator:
    def __init__(self):
        self.workbook = None

        # Paleta (hex sin #)
        self.colors = {
            "header": "1F4E78",
            "subheader": "2F75B5",
            "ok": "70AD47",
            "warn": "FFC000",
            "danger": "C00000",
            "soft": "F2F2F2",
            "total": "FFD966",
        }

        thin = Side(style="thin", color="BFBFBF")
        self.border = Border(left=thin, right=thin, top=thin, bottom=thin)

        self.font_title = Font(bold=True, size=18, color="FFFFFF")
        self.font_header = Font(bold=True, size=11, color="FFFFFF")
        self.font_bold = Font(bold=True)
        self.align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
        self.align_left = Alignment(horizontal="left", vertical="center", wrap_text=True)
        self.align_right = Alignment(horizontal="right", vertical="center")

        self.fill_header = PatternFill(start_color=self.colors["header"], end_color=self.colors["header"], fill_type="solid")
        self.fill_subheader = PatternFill(start_color=self.colors["subheader"], end_color=self.colors["subheader"], fill_type="solid")
        self.fill_soft = PatternFill(start_color=self.colors["soft"], end_color=self.colors["soft"], fill_type="solid")

    # =========================
    # API PÚBLICA
    # =========================
    def generar_reporte_completo(self, estudiantes, pagos, cursos):
        """Excel multi-hoja con resumen + estudiantes + pagos + morosos + cursos"""
        self.workbook = openpyxl.Workbook()
        # quitar hoja por defecto
        if "Sheet" in self.workbook.sheetnames:
            self.workbook.remove(self.workbook["Sheet"])

        # Crear hojas (Resumen primero)
        self._sheet_resumen(estudiantes, pagos, cursos)
        self._sheet_estudiantes(estudiantes, pagos)
        self._sheet_pagos(pagos)
        self._sheet_morosos(estudiantes, pagos)
        self._sheet_cursos(estudiantes, pagos, cursos)

        # Guardar en memoria
        output = io.BytesIO()
        self.workbook.save(output)
        output.seek(0)
        return output

    # =========================
    # HELPERS DE FORMATO
    # =========================
    def _set_col_widths_auto(self, ws, min_width=10, max_width=45, padding=2):
        """Auto-ajusta el ancho según contenido (rápido y suficiente)."""
        for col in ws.columns:
            col_letter = get_column_letter(col[0].column)
            max_len = 0
            for cell in col:
                if cell.value is None:
                    continue
                s = str(cell.value)
                if len(s) > max_len:
                    max_len = len(s)
            width = max(min_width, min(max_width, max_len + padding))
            ws.column_dimensions[col_letter].width = width

    def _apply_table_header(self, ws, row, headers):
        for c, h in enumerate(headers, start=1):
            cell = ws.cell(row=row, column=c, value=h)
            cell.font = self.font_header
            cell.fill = self.fill_subheader
            cell.alignment = self.align_center
            cell.border = self.border
        ws.row_dimensions[row].height = 20

    def _title_block(self, ws, title, subtitle=None, merge_to_col=8):
        end_col = get_column_letter(merge_to_col)
        ws.merge_cells(f"A1:{end_col}1")
        t = ws["A1"]
        t.value = title
        t.font = self.font_title
        t.fill = self.fill_header
        t.alignment = self.align_center
        ws.row_dimensions[1].height = 34

        ws.merge_cells(f"A2:{end_col}2")
        s = ws["A2"]
        s.value = subtitle or f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        s.font = Font(italic=True, size=10, color="404040")
        s.alignment = self.align_center
        ws.row_dimensions[2].height = 18

    def _currency(self, cell):
        cell.number_format = '"$"#,##0.00'

    # =========================
    # CÁLCULOS
    # =========================
    def _clasificar_estudiantes(self, estudiantes):
        activos = [e for e in estudiantes if getattr(e, "activo", True)]
        sin_cobertura = [e for e in activos if getattr(e, "mensualidades_canceladas", 0) == 0]
        vencidos = [e for e in activos if getattr(e, "dias_restantes", None) is not None and e.dias_restantes < 0]
        criticos = [e for e in activos if getattr(e, "dias_restantes", None) is not None and 0 <= e.dias_restantes <= 3]
        proximos = [e for e in activos if getattr(e, "dias_restantes", None) is not None and 4 <= e.dias_restantes <= 7]
        al_dia = [e for e in activos if getattr(e, "dias_restantes", None) is not None and e.dias_restantes > 7]
        return activos, sin_cobertura, vencidos, criticos, proximos, al_dia

    def _pagos_por_cliente(self, pagos):
        mp = defaultdict(list)
        for p in pagos:
            mp[getattr(p, "cliente_id", None) or getattr(p.cliente, "id", None)].append(p)
        return mp

    # =========================
    # HOJAS
    # =========================
    def _sheet_resumen(self, estudiantes, pagos, cursos):
        ws = self.workbook.create_sheet("📊 Resumen", 0)
        self._title_block(ws, "RESUMEN EJECUTIVO", merge_to_col=4)

        activos, sin_cobertura, vencidos, criticos, proximos, al_dia = self._clasificar_estudiantes(estudiantes)

        total_recaudado = sum(_money(p.monto) for p in pagos)
        total_pagos = len(pagos)
        promedio = (total_recaudado / total_pagos) if total_pagos else 0

        # ingresos del mes actual
        now = datetime.now()
        inicio_mes = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        pagos_mes = [p for p in pagos if getattr(p, "fecha_pago", now) >= inicio_mes]
        total_mes = sum(_money(p.monto) for p in pagos_mes)

        # cursos activos
        cursos_activos = [c for c in cursos if getattr(c, "activo", True)]

        # KPIs (tabla simple 2 columnas)
        start_row = 4
        ws["A3"].value = "INDICADORES"
        ws["A3"].font = Font(bold=True, size=12)
        ws.merge_cells("A3:D3")
        ws["A3"].fill = self.fill_soft
        ws["A3"].alignment = self.align_left

        kpis = [
            ("Total estudiantes (activos)", len(activos), None),
            ("Sin cobertura (no pagó aún)", len(sin_cobertura), "danger" if len(sin_cobertura) else "ok"),
            ("Vencidos", len(vencidos), "danger" if len(vencidos) else "ok"),
            ("Críticos (≤3 días)", len(criticos), "warn" if len(criticos) else "ok"),
            ("Próximos (4-7 días)", len(proximos), "warn" if len(proximos) else "ok"),
            ("Al día (>7 días)", len(al_dia), "ok"),
            ("", "", None),
            ("Total recaudado (histórico)", total_recaudado, "ok"),
            ("Total recaudado (este mes)", total_mes, "ok"),
            ("Cantidad de pagos (histórico)", total_pagos, None),
            ("Promedio por pago", promedio, None),
            ("Cursos activos", len(cursos_activos), None),
        ]

        row = start_row
        for label, value, tag in kpis:
            if label == "":
                row += 1
                continue

            ws.cell(row=row, column=1, value=label).alignment = self.align_left
            ws.cell(row=row, column=1).border = self.border

            c2 = ws.cell(row=row, column=2, value=value)
            c2.border = self.border
            c2.alignment = self.align_center
            c2.font = Font(bold=True, size=12)

            # format dinero si corresponde
            if "recaudado" in label.lower() or "promedio" in label.lower():
                self._currency(c2)

            # color por severidad
            if tag == "danger":
                c2.fill = PatternFill(start_color=self.colors["danger"], end_color=self.colors["danger"], fill_type="solid")
                c2.font = Font(bold=True, size=12, color="FFFFFF")
            elif tag == "warn":
                c2.fill = PatternFill(start_color=self.colors["warn"], end_color=self.colors["warn"], fill_type="solid")
            elif tag == "ok":
                c2.fill = PatternFill(start_color=self.colors["ok"], end_color=self.colors["ok"], fill_type="solid")
                c2.font = Font(bold=True, size=12, color="FFFFFF")

            row += 1

        ws.column_dimensions["A"].width = 35
        ws.column_dimensions["B"].width = 18
        ws.column_dimensions["C"].width = 5
        ws.column_dimensions["D"].width = 5
        ws.freeze_panes = "A4"

    def _sheet_estudiantes(self, estudiantes, pagos):
        ws = self.workbook.create_sheet("👥 Estudiantes")
        self._title_block(ws, "REGISTRO DE ESTUDIANTES", merge_to_col=16)

        pagos_por_cliente = self._pagos_por_cliente(pagos)

        headers = [
            "ID", "Nombre", "Cédula", "Email", "Teléfono", "Curso",
            "Precio mensual", "Fecha registro", "Inicio clases",
            "Fecha vencimiento", "Días restantes",
            "Mensualidades pagadas", "Valor inscripción",
            "Total pagado", "Estado", "Activo"
        ]
        self._apply_table_header(ws, 4, headers)

        row = 5
        for e in estudiantes:
            curso = getattr(e, "curso", None)
            precio_mensual = _money(getattr(curso, "precio_mensual", 0)) if curso else 0

            pagos_cliente = pagos_por_cliente.get(getattr(e, "id", None), [])
            total_pagado = sum(_money(p.monto) for p in pagos_cliente)

            dias = getattr(e, "dias_restantes", None)
            if getattr(e, "mensualidades_canceladas", 0) == 0:
                estado = "Sin cobertura"
                sem = "danger"
            elif dias is None:
                estado = "N/A"
                sem = None
            elif dias < 0:
                estado = "Vencido"
                sem = "danger"
            elif dias <= 7:
                estado = "Por vencer"
                sem = "warn"
            else:
                estado = "Al día"
                sem = "ok"

            values = [
                getattr(e, "id", ""),
                getattr(e, "nombre_completo", f"{getattr(e,'nombre','')} {getattr(e,'apellido','')}").strip(),
                getattr(e, "cedula", None) or "Sin registrar",
                getattr(e, "email", ""),
                getattr(e, "telefono", None) or "N/A",
                getattr(curso, "nombre", None) if curso else "Sin curso",
                precio_mensual,
                getattr(e, "fecha_registro", None).strftime("%d/%m/%Y") if getattr(e, "fecha_registro", None) else "N/A",
                getattr(e, "fecha_inicio_clases", None).strftime("%d/%m/%Y") if getattr(e, "fecha_inicio_clases", None) else "N/A",
                getattr(e, "fecha_fin", None).strftime("%d/%m/%Y") if getattr(e, "fecha_fin", None) else "N/A",
                dias if dias is not None else "N/A",
                getattr(e, "mensualidades_canceladas", 0),
                _money(getattr(e, "valor_inscripcion", 0)),
                total_pagado,
                estado,
                "Sí" if getattr(e, "activo", True) else "No",
            ]

            for c, v in enumerate(values, start=1):
                cell = ws.cell(row=row, column=c, value=v)
                cell.border = self.border
                cell.alignment = self.align_left

                if c in (1, 11, 12):
                    cell.alignment = self.align_center
                if c in (7, 13, 14):
                    cell.alignment = self.align_right
                if c in (7, 13, 14):
                    self._currency(cell)

                # colorear estado
                if c == 15 and sem:
                    if sem == "danger":
                        cell.fill = PatternFill(start_color=self.colors["danger"], end_color=self.colors["danger"], fill_type="solid")
                        cell.font = Font(bold=True, color="FFFFFF")
                        cell.alignment = self.align_center
                    elif sem == "warn":
                        cell.fill = PatternFill(start_color=self.colors["warn"], end_color=self.colors["warn"], fill_type="solid")
                        cell.font = Font(bold=True)
                        cell.alignment = self.align_center
                    elif sem == "ok":
                        cell.fill = PatternFill(start_color=self.colors["ok"], end_color=self.colors["ok"], fill_type="solid")
                        cell.font = Font(bold=True, color="FFFFFF")
                        cell.alignment = self.align_center

            row += 1

        ws.freeze_panes = "A5"
        ws.auto_filter.ref = f"A4:{get_column_letter(len(headers))}{max(4, row-1)}"
        self._set_col_widths_auto(ws)

    def _sheet_pagos(self, pagos):
        ws = self.workbook.create_sheet("💳 Pagos")
        self._title_block(ws, "HISTORIAL DE PAGOS", merge_to_col=10)

        headers = ["ID", "Fecha", "Estudiante", "Cédula", "Curso", "Periodo", "Monto", "Método", "Referencia", "Notas"]
        self._apply_table_header(ws, 4, headers)

        row = 5
        total = 0.0
        for p in pagos:
            c = getattr(p, "cliente", None)
            curso = getattr(c, "curso", None) if c else None

            monto = _money(getattr(p, "monto", 0))
            total += monto

            values = [
                getattr(p, "id", ""),
                getattr(p, "fecha_pago", None).strftime("%d/%m/%Y %H:%M") if getattr(p, "fecha_pago", None) else "N/A",
                getattr(c, "nombre_completo", "N/A") if c else "N/A",
                getattr(c, "cedula", None) if c else None,
                getattr(curso, "nombre", None) if curso else "Sin curso",
                getattr(p, "periodo", None) or "-",
                monto,
                getattr(p, "metodo_pago", None) or "-",
                getattr(p, "referencia", None) or "-",
                getattr(p, "notas", None) or "-",
            ]

            for col, v in enumerate(values, start=1):
                cell = ws.cell(row=row, column=col, value=v)
                cell.border = self.border
                cell.alignment = self.align_left
                if col in (1,):
                    cell.alignment = self.align_center
                if col == 7:
                    cell.alignment = self.align_right
                    self._currency(cell)
            row += 1

        # total final
        row += 1
        ws.merge_cells(f"A{row}:F{row}")
        tcell = ws.cell(row=row, column=1, value="TOTAL RECAUDADO")
        tcell.font = Font(bold=True, size=13)
        tcell.fill = PatternFill(start_color=self.colors["total"], end_color=self.colors["total"], fill_type="solid")
        tcell.alignment = self.align_center
        tcell.border = self.border

        mcell = ws.cell(row=row, column=7, value=total)
        mcell.font = Font(bold=True, size=13)
        mcell.fill = PatternFill(start_color=self.colors["total"], end_color=self.colors["total"], fill_type="solid")
        mcell.alignment = self.align_right
        mcell.border = self.border
        self._currency(mcell)

        ws.freeze_panes = "A5"
        ws.auto_filter.ref = f"A4:{get_column_letter(len(headers))}{max(4, row-2)}"
        self._set_col_widths_auto(ws)

    def _sheet_morosos(self, estudiantes, pagos):
        ws = self.workbook.create_sheet("🚨 Morosos")
        self._title_block(ws, "MOROSOS Y VENCIDOS", merge_to_col=9)

        pagos_por_cliente = self._pagos_por_cliente(pagos)

        headers = ["Estudiante", "Cédula", "Curso", "Email", "Teléfono", "Días", "Último pago", "Total pagado", "Estado"]
        self._apply_table_header(ws, 4, headers)

        row = 5
        for e in estudiantes:
            if not getattr(e, "activo", True):
                continue

            dias = getattr(e, "dias_restantes", None)
            sin_cob = getattr(e, "mensualidades_canceladas", 0) == 0

            if sin_cob:
                estado = "Sin cobertura"
            elif dias is not None and dias < 0:
                estado = "Vencido"
            elif dias is not None and dias <= 7:
                estado = "Por vencer"
            else:
                continue  # no entra en cobranza

            pagos_cliente = pagos_por_cliente.get(getattr(e, "id", None), [])
            total_pagado = sum(_money(p.monto) for p in pagos_cliente)
            ultimo = pagos_cliente[0].fecha_pago.strftime("%d/%m/%Y") if pagos_cliente else "-"

            curso = getattr(e, "curso", None)

            values = [
                getattr(e, "nombre_completo", "").strip(),
                getattr(e, "cedula", None) or "Sin registrar",
                getattr(curso, "nombre", None) if curso else "Sin curso",
                getattr(e, "email", ""),
                getattr(e, "telefono", None) or "-",
                dias if dias is not None else ("0" if sin_cob else "N/A"),
                ultimo,
                total_pagado,
                estado,
            ]

            for col, v in enumerate(values, start=1):
                cell = ws.cell(row=row, column=col, value=v)
                cell.border = self.border
                cell.alignment = self.align_left
                if col in (6,):
                    cell.alignment = self.align_center
                if col == 8:
                    cell.alignment = self.align_right
                    self._currency(cell)
                if col == 9:
                    cell.alignment = self.align_center
                    if estado in ("Vencido", "Sin cobertura"):
                        cell.fill = PatternFill(start_color=self.colors["danger"], end_color=self.colors["danger"], fill_type="solid")
                        cell.font = Font(bold=True, color="FFFFFF")
                    else:
                        cell.fill = PatternFill(start_color=self.colors["warn"], end_color=self.colors["warn"], fill_type="solid")
                        cell.font = Font(bold=True)

            row += 1

        ws.freeze_panes = "A5"
        ws.auto_filter.ref = f"A4:{get_column_letter(len(headers))}{max(4, row-1)}"
        self._set_col_widths_auto(ws)

    def _sheet_cursos(self, estudiantes, pagos, cursos):
        ws = self.workbook.create_sheet("📚 Cursos")
        self._title_block(ws, "ANÁLISIS POR CURSO", merge_to_col=9)

        # agrupar pagos por curso
        pagos_por_curso = defaultdict(float)
        for p in pagos:
            c = getattr(p, "cliente", None)
            curso = getattr(c, "curso", None) if c else None
            nombre = getattr(curso, "nombre", None) if curso else "Sin curso"
            pagos_por_curso[nombre] += _money(p.monto)

        # conteos por curso
        estudiantes_activos = [e for e in estudiantes if getattr(e, "activo", True)]
        conteo = defaultdict(int)
        for e in estudiantes_activos:
            curso = getattr(e, "curso", None)
            nombre = getattr(curso, "nombre", None) if curso else "Sin curso"
            conteo[nombre] += 1

        headers = [
            "Curso", "Activo", "Estudiantes activos", "Precio mensual",
            "Ingreso esperado (mes)", "Ingreso real (histórico)", "Diferencia", "Inscripción", "Descripción"
        ]
        self._apply_table_header(ws, 4, headers)

        row = 5
        for curso in cursos:
            nombre = getattr(curso, "nombre", "")
            activos = conteo.get(nombre, 0)
            precio = _money(getattr(curso, "precio_mensual", 0))
            esperado = activos * precio
            real = pagos_por_curso.get(nombre, 0.0)
            diff = real - esperado

            values = [
                nombre,
                "Sí" if getattr(curso, "activo", True) else "No",
                activos,
                precio,
                esperado,
                real,
                diff,
                _money(getattr(curso, "precio_inscripcion", 0)),
                getattr(curso, "descripcion", None) or "-",
            ]

            for col, v in enumerate(values, start=1):
                cell = ws.cell(row=row, column=col, value=v)
                cell.border = self.border
                cell.alignment = self.align_left
                if col in (2, 3):
                    cell.alignment = self.align_center
                if col in (4, 5, 6, 7, 8):
                    cell.alignment = self.align_right
                    self._currency(cell)

                # color diferencia (positivo ok, negativo warning)
                if col == 7:
                    if diff >= 0:
                        cell.fill = PatternFill(start_color=self.colors["ok"], end_color=self.colors["ok"], fill_type="solid")
                        cell.font = Font(bold=True, color="FFFFFF")
                    else:
                        cell.fill = PatternFill(start_color=self.colors["warn"], end_color=self.colors["warn"], fill_type="solid")
                        cell.font = Font(bold=True)

            row += 1

        # incluir "Sin curso" si existe (para datos sucios)
        if "Sin curso" in conteo or "Sin curso" in pagos_por_curso:
            activos = conteo.get("Sin curso", 0)
            real = pagos_por_curso.get("Sin curso", 0.0)
            values = ["Sin curso", "-", activos, 0, 0, real, real, 0, "-"]
            for col, v in enumerate(values, start=1):
                cell = ws.cell(row=row, column=col, value=v)
                cell.border = self.border
                cell.alignment = self.align_left
                if col in (2, 3):
                    cell.alignment = self.align_center
                if col in (4, 5, 6, 7, 8):
                    cell.alignment = self.align_right
                    self._currency(cell)
            row += 1

        ws.freeze_panes = "A5"
        ws.auto_filter.ref = f"A4:{get_column_letter(len(headers))}{max(4, row-1)}"
        self._set_col_widths_auto(ws)


# Instancia global (igual que tu sistema actual usa)
excel_generator = ExcelReportGenerator()
