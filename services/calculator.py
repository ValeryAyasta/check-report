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

        self.error = PatternFill(
            start_color="FFF4CCCC",
            end_color="FFF4CCCC",
            fill_type="solid"
        )

    def calcular_faltas(self, wb: openpyxl.Workbook):
        ws = wb.active
        col_inicio = 1
        col_fin = 23

        # Encabezados
        for col in range(col_inicio, col_fin + 1):
            cell = ws.cell(row=1, column=col)
            cell.font = Font(color=self.colors["blanco"], bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = self.thin_border
            if col > 5:
                cell.fill = PatternFill("solid", fgColor=self.colors["azul"])
            else:
                cell.fill = PatternFill("solid", fgColor=self.colors["verde"])


        c22 = ws.cell(row=1, column=34, value="Falta check")
        c22.fill = PatternFill("solid", fgColor=self.colors["negro"])
        c22.font = Font(color=self.colors["amarillo"])

        c23 = ws.cell(row=1, column=35, value="Falta apreciación")
        c23.fill = PatternFill("solid", fgColor=self.colors["rojo"])
        c23.font = Font(color=self.colors["blanco"])

        last_row = ws.max_row
        last_col = ws.max_column

        for i in range(2, last_row + 1):
            clases_faltas_apreciacion = []
            clases_faltas_check = []

            for j in range(1, 10):  # clases 1 a 9
                col_clase = 15 + j    # columns 16..24
                col_resumen = 24 + j # 25..31

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

            ws.cell(i, 34, falta_check)
            ws.cell(i, 35, falta_apreciacion)

        # Bordes para todo rango con datos
        for row in ws.iter_rows(min_row=1, max_row=last_row, min_col=1, max_col=last_col):
            for cell in row:
                cell.border = self.thin_border

def contar_asistencias(celdas):
    total = 0
    for c in celdas:
        val = c.value
        if val is None:
            continue
        try:
            if float(val) > 0:
                total += 1
        except (ValueError, TypeError):
            pass
    return total

ASISTENCIA_A_NOTA = {
    1: 2,
    2: 4,
    3: 6,
    4: 8,
    5: 10,
    6: 13,
    7: 16,
    8: 18,
    9: 20,
}

FILL_ERROR = PatternFill(
    fill_type="solid",
    fgColor="FFCCCC"  # rojo suave
)


def calcular_nota_asistencia(total_asist):
    return ASISTENCIA_A_NOTA.get(total_asist, 0)
def pegar_asistencias_y_calcular(
    reporte_con_padron_path: Path,
    tutores_dir: Path,
    out_path: Path
) -> Path:
    """
    Pega asistencias desde archivos de tutores, calcula faltas
    y genera el Excel final optimizado.
    """

    # ================== ABRIR WORKBOOK PRINCIPAL ==================
    try:
        wb_main = openpyxl.load_workbook(reporte_con_padron_path)
        ws_main = wb_main.active
    except Exception as e:
        logger.exception("No se pudo abrir el reporte con padrón")
        raise ProcessingError("Lectura workbook principal falló") from e

    DEVO_START_COL = 6  # G
    DEVO_END_COL = 69  # BQ + 1 (slice)
    TOTAL_DEVO_DIAS = 63

    # ================== CREAR ÍNDICE DNI ==================
    dni_index: dict[str, int] = {}
    for r in range(2, ws_main.max_row + 1):
        val = ws_main.cell(r, 3).value
        if val:
            dni_index[str(val).strip()] = r

    logger.info("Índice de DNI cargado: %d registros", len(dni_index))

    # ================== CONFIGURAR COLUMNAS ==================
    headers = [f"S{i}" for i in range(1, 10)]

    col_total = ws_main.max_column - 12
    ws_main.insert_cols(col_total)
    ws_main.cell(1, col_total, "Clases Drive")

    col_nota_drive = col_total + 1
    ws_main.insert_cols(col_nota_drive)
    ws_main.cell(1, col_nota_drive, "Asistencia Drive")

    col_nota_av = col_nota_drive -2

    col_tf = col_nota_drive + 1
    ws_main.cell(1, col_tf, "TF")

    col_ef_drive = 11
    ws_main.insert_cols(col_ef_drive)
    ws_main.cell(1, col_ef_drive, "EF Drive")

    col_ef_av = col_ef_drive -1

    col_devo_total = 13
    ws_main.insert_cols(col_devo_total)
    ws_main.cell(1, col_devo_total, "Devocionales Entregados")

    col_devo_pct = col_devo_total + 1
    ws_main.insert_cols(col_devo_pct)
    ws_main.cell(1, col_devo_pct, "% Devocionales")

    start_col = ws_main.max_column + 1
    header_font = Font(bold=True, color="FFFFFFFF")
    header_fill = PatternFill("solid", "FF7030A0")

    for i, header in enumerate(headers, start=start_col):
        cell = ws_main.cell(1, i, header)
        cell.font = header_font
        cell.fill = header_fill

    # ================== PROCESAR ARCHIVOS DE TUTORES ==================
    archivos_tutores = sorted(Path(tutores_dir).glob("*.xlsx"))
    dni_no_encontrados: set[str] = set()

    for archivo in archivos_tutores:
        try:
            wb_tutor = openpyxl.load_workbook(archivo, data_only=True, read_only=True)
            if "ASISTENCIA" not in wb_tutor.sheetnames:
                logger.warning("Archivo %s sin hoja ASISTENCIA", archivo)
                continue
            ws_tutor_asistencia = wb_tutor["ASISTENCIA"]
            ws_tutor_devo = wb_tutor["DEVO"]
        except Exception:
            logger.exception("No se pudo abrir archivo tutor %s", archivo)
            continue

        tutor = archivo.stem.split("-", 1)[-1].replace("_", " - ")
        logger.info("Procesando tutor: %s", tutor)

        for row in ws_tutor_asistencia.iter_rows(min_row=4):
            row_idx = row[0].row  # número real de fila en Excel
            devo_row = ws_tutor_devo[row_idx +1]

            dni = row[4].value
            if not dni:
                break

            dni_tutor = str(dni).strip()

            if dni_tutor not in dni_index:
                dni_no_encontrados.add(dni_tutor)
                continue

            r = dni_index[dni_tutor]
            asistencias = row[5:14]
            total_asist = contar_asistencias(asistencias)
            nota_asist = calcular_nota_asistencia(total_asist)
            ef_drive = row[36].value or 0

            # -------- copiar asistencias --------
            for j, cell in enumerate(asistencias, start=start_col):
                target = ws_main.cell(r, j, cell.value)
                try:
                    set_fill_by_value(cell.value, target)
                except Exception:
                    pass

            ws_main.cell(r, 5, tutor)
            cell_cantidad_clases = ws_main.cell(r, col_total, total_asist)
            ws_main.cell(r, col_nota_drive, nota_asist)
            ws_main.cell(r, col_ef_drive, ef_drive)

            if total_asist == 9:
                cell_cantidad_clases.fill = PatternFill("solid", "00B050")
            elif 9 > total_asist >= 6:
                cell_cantidad_clases.fill = PatternFill("solid", "92D050")

            # -------- validaciones --------
            cell_av = ws_main.cell(r, col_nota_av)
            val_av = int(cell_av.value or 0) if str(cell_av.value).isdigit() else 0

            cell_ef_av = ws_main.cell(r, col_ef_av)
            val_ef_av = int(cell_ef_av.value or 0) if str(cell_ef_av.value).isdigit() else 0

            cell_tf = ws_main.cell(r, col_tf)
            val_tf = cell_tf.value

            if val_av != nota_asist:
                cell_av.fill = FILL_ERROR

            if val_ef_av != int(ef_drive):
                ws_main.cell(r, col_ef_drive).fill = FILL_ERROR

            estado = "APROBADO" if total_asist >= 6 and val_ef_av != 0 and val_tf != "-" else "DESAPROBADO"
            ws_main.cell(r, 12, estado)

            devo_cells = devo_row[6:69]  # G..BQ
            total_devo = sum(1 for c in devo_cells if c.value == 1)
            pct_devo = round((total_devo / 63) * 100, 2)

            ws_main.cell(r, col_devo_total, total_devo)
            ws_main.cell(r, col_devo_pct, pct_devo)



    # ================== REPORTAR DNIs NO ENCONTRADOS ==================
    if dni_no_encontrados:
        logger.warning("DNIs no encontrados en padrón:")
        for d in sorted(dni_no_encontrados):
            logger.warning(" - %s", d)
    else:
        logger.info("Todos los DNIs fueron encontrados")

    # ================== POST-PROCESO ==================
    formatter = ExcelChecksAttendanceCalculator()
    formatter.calcular_faltas(wb_main)
    autoajustar_columnas(ws_main)

    wb_main.save(out_path)
    logger.info("Archivo final generado: %s", out_path)

    return out_path
