from openpyxl.styles import PatternFill, Font, Border, Side, Alignment
import openpyxl
from pathlib import Path
import logging

from services.reporte_unido import ProcessingError
from services.utils import *

# ---------- Config / Logging ----------
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)
# ---------- Excel Formatter / Calculator ----------
class ExcelChecksAttendanceCalculator:
    def __init__(self):
        # Colores / bordes reusables
        self.colors = {
            "negro": "000000",
            "blanco": "FFFFFF",
            "rojo": "FF0000",
            "amarillo": "FFFF00",
            "azul": "0070C0",
            "verde": "00B050",
        }
        self.thin_border = Border(
            left=Side(style="thin"),
            right=Side(style="thin"),
            top=Side(style="thin"),
            bottom=Side(style="thin")
        )

    def calcular_faltas(self, wb: openpyxl.Workbook):
        ws = wb.active
        col_inicio = 1
        col_fin = 12

        # Encabezados
        for col in range(col_inicio, col_fin + 1):
            cell = ws.cell(row=1, column=col)
            cell.font = Font(color=self.colors["blanco"], bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = self.thin_border
            if col > 3:
                cell.fill = PatternFill("solid", fgColor=self.colors["azul"])
            else:
                cell.fill = PatternFill("solid", fgColor=self.colors["verde"])

        # Columnas 22 (V) y 23 (W)
        c22 = ws.cell(row=1, column=22, value="Falta check")
        c22.fill = PatternFill("solid", fgColor=self.colors["negro"])
        c22.font = Font(color=self.colors["amarillo"])

        c23 = ws.cell(row=1, column=23, value="Falta apreciación")
        c23.fill = PatternFill("solid", fgColor=self.colors["rojo"])
        c23.font = Font(color=self.colors["blanco"])

        last_row = ws.max_row
        last_col = ws.max_column

        for i in range(2, last_row + 1):
            clases_faltas_apreciacion = []
            clases_faltas_check = []

            for j in range(1, 10):  # clases 1 a 9
                col_clase = 3 + j    # columns 4..12
                col_resumen = 12 + j # 13..21

                clase_value = ws.cell(i, col_clase).value
                resumen_value = ws.cell(i, col_resumen).value
                cell_clase = ws.cell(i, col_clase)

                if clase_value == "No finalizado":
                    cell_clase.fill = PatternFill("solid", fgColor=self.colors["negro"])
                    if not resumen_value:
                        cell_clase.font = Font(color=self.colors["blanco"])
                    else:
                        cell_clase.font = Font(color=self.colors["amarillo"])

                if clase_value == "Finalizado" and not resumen_value:
                    clases_faltas_apreciacion.append(str(j))
                    cell_clase.fill = PatternFill("solid", fgColor=self.colors["rojo"])
                    cell_clase.font = Font(color=self.colors["blanco"])

                if clase_value == "No finalizado" and resumen_value:
                    clases_faltas_check.append(str(j))

            falta_apreciacion = ""
            falta_check = ""
            if clases_faltas_apreciacion:
                falta_apreciacion = ("Clases " if len(clases_faltas_apreciacion) > 1 else "Clase ") + ", ".join(clases_faltas_apreciacion)
            if clases_faltas_check:
                falta_check = ("Clases " if len(clases_faltas_check) > 1 else "Clase ") + ", ".join(clases_faltas_check)

            ws.cell(i, 22, falta_check)
            ws.cell(i, 23, falta_apreciacion)

        # Bordes para todo rango con datos
        for row in ws.iter_rows(min_row=1, max_row=last_row, min_col=1, max_col=last_col):
            for cell in row:
                cell.border = self.thin_border


def pegar_asistencias_y_calcular(reporte_con_padron_path: Path, tutores_dir: Path, out_path: Path) -> Path:
    """
    Abre el reporte con padrón, pega asistencias desde archivos en tutores_dir y
    calcula faltas y formatea el excel final.
    """
    try:
        wb_main = openpyxl.load_workbook(reporte_con_padron_path)
        ws_main = wb_main.active
    except Exception as e:
        logger.exception("No se pudo abrir el reporte con padrón.")
        raise ProcessingError("Lectura workbook principal falló") from e

    # Agregar encabezados S1..S9 si no existen
    headers = [f"S{i}" for i in range(1,10)]
    start_col = ws_main.max_column + 1
    header_font = Font(bold=True, color="FFFFFFFF")  # Blanco
    header_fill = PatternFill(start_color="FF7030A0", end_color="FF7030A0", fill_type="solid")
    for i, header in enumerate(headers, start=start_col):
        ws_main.cell(row=1, column=i, value=header).font = header_font
        ws_main.cell(row=1, column=i).fill = header_fill

    archivos_tutores = sorted(Path(tutores_dir).glob("*.xlsx"))
    if not archivos_tutores:
        logger.warning("No se encontraron archivos en %s", tutores_dir)

    for archivo in archivos_tutores:
        try:
            wb_tutor = openpyxl.load_workbook(archivo, data_only=True)
            if "ASISTENCIA" not in wb_tutor.sheetnames:
                logger.warning("El archivo %s no tiene hoja 'ASISTENCIA', se salta.", archivo)
                continue
            ws_tutor = wb_tutor["ASISTENCIA"]
            print("Procesando archivo tutor:", archivo)
        except Exception:
            logger.exception("No se pudo abrir archivo de tutor: %s", archivo)
            continue

        base = archivo.stem
        partes = base.split("-", 1)
        tutor = partes[1] if len(partes) > 1 else base
        tutor = tutor.replace("_", " - ")

        # iterar filas desde fila 4 (min_row=4)
        for row in ws_tutor.iter_rows(min_row=4, values_only=False):
            dni = row[4].value  # columna E (índice 4)
            if dni is None or str(dni).strip() == "":
                # asumimos fin de bloque
                break
            asistencias = [c for c in row[5:14]]  # 9 celdas de asistencia
            if not dni:
                continue

            dni_tutor = str(dni).strip()
            # buscar en ws_main por DNI columna 2
            for r in range(2, ws_main.max_row + 1):
                val = ws_main.cell(r, 2).value
                if val is None:
                    continue
                dni_sistema = str(val).strip()
                if dni_sistema == dni_tutor:
                    # copiar asistencias
                    for j, cell in enumerate(asistencias, start=start_col):
                        target = ws_main.cell(r, j)
                        target.value = cell.value
                        try:
                            set_fill_by_value(cell.value, target)
                        except Exception:
                            pass
                    # registrar tutor en columna 3
                    ws_main.cell(row=r, column=3, value=tutor)
                    break

    # Calcular faltas y formatear
    formatter = ExcelChecksAttendanceCalculator()
    formatter.calcular_faltas(wb_main)
    autoajustar_columnas(ws_main)

    wb_main.save(out_path)
    print("Archivo final guardado en %s", out_path)
    return out_path