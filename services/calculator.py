"""
Pega la asistencia y devocionales que cada tutora registra manualmente
en su Drive sobre el reporte "unido" (notas + checks de Moodle),
calcula la nota de asistencia, compara Drive vs Aula Virtual, y da
formato final al Excel — incluyendo el resaltado de APROBADO (amarillo)
/ DESAPROBADO (rojo, letras blancas) que pide el punto 5 del pedido original.

DISEÑO: todas las columnas del reporte principal se ubican buscando su
ENCABEZADO (fila 1) por nombre, nunca por número de columna fijo. Así,
si un curso no tiene TF o EF, esas columnas simplemente no existen y el
resto del reporte no se desalinea (antes, una posición fija como
`col_ef_drive = 11` se corría entera apenas cambiaba una columna
anterior — esto es lo que el punto 2 y 3 del pedido describían).

⚠️ Los offsets de lectura del archivo de la TUTORA (fila de inicio,
columna del DNI, rango de asistencia, columna de EF, rango de
devocionales) se preservaron tal cual estaban en el código original
porque no hay un archivo de ejemplo de una tutora para verificarlos.
Viven en config.py (TUTOR_*), listos para ajustar si no calzan.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl
from openpyxl.styles import PatternFill, Font, Border, Side, Alignment
from openpyxl.worksheet.worksheet import Worksheet

import config
from domain.curso import ConfiguracionCurso
from services.utils import autoajustar_columnas, set_fill_por_valor, contar_celdas_con_valor

logger = logging.getLogger(__name__)


class ReporteFinalError(Exception):
    pass


@dataclass
class ResultadoCalculo:
    dnis_no_encontrados_en_reporte: list[str] = field(default_factory=list)
    tutores_procesados: list[str] = field(default_factory=list)
    archivos_tutor_sin_hoja_asistencia: list[str] = field(default_factory=list)


BORDE_FINO = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"), bottom=Side(style="thin"),
)


# ============================================================
# Utilidades para ubicar columnas por nombre de encabezado
# ============================================================

def _mapa_encabezados(ws: Worksheet) -> dict[str, int]:
    mapa = {}
    for col in range(1, ws.max_column + 1):
        valor = ws.cell(1, col).value
        if valor:
            mapa[str(valor).strip()] = col
    return mapa


def _col(mapa: dict[str, int], nombre: str, obligatoria: bool = True) -> int | None:
    if nombre in mapa:
        return mapa[nombre]
    if obligatoria:
        raise ReporteFinalError(
            f"No se encontró la columna '{nombre}' en el reporte unido. "
            f"Columnas disponibles: {list(mapa.keys())}. Esto normalmente indica que "
            "reporte_unido no generó esa columna: revisa los pasos previos."
        )
    return None


def _agregar_columna(ws: Worksheet, titulo: str, mapa: dict[str, int]) -> int:
    """Agrega una columna nueva al final de la hoja y la registra en el mapa."""
    col = ws.max_column + 1
    cell = ws.cell(1, col, titulo)
    cell.font = Font(bold=True, color=config.COLOR_BLANCO)
    cell.fill = PatternFill("solid", fgColor=config.COLOR_MORADO_HEADER)
    mapa[titulo] = col
    return col


def _a_entero(valor) -> int:
    try:
        return round(float(str(valor).strip()))
    except (TypeError, ValueError):
        return 0


# ============================================================
# Paso 1: preparar columnas nuevas en el reporte principal
# ============================================================

def _preparar_columnas(ws: Worksheet, curso: ConfiguracionCurso) -> dict:
    """Agrega todas las columnas calculadas al final del reporte y
    devuelve un dict con los índices de columna relevantes."""
    mapa = _mapa_encabezados(ws)

    idx = {
        "dni": _col(mapa, "DNI"),
        "nombre": _col(mapa, "Nombre"),
        "asistencia_av": _col(mapa, "Asistencia AV"),
        "ef_av": _col(mapa, "EF (AV)", obligatoria=False),
        "tf_av": _col(mapa, "TF (AV)", obligatoria=False),
    }

    idx["clases_drive"] = _agregar_columna(ws, "Clases Drive", mapa)
    idx["asistencia_drive"] = _agregar_columna(ws, "Asistencia Drive", mapa)

    if curso.tiene_examen_final and idx["ef_av"]:
        idx["ef_drive"] = _agregar_columna(ws, "EF Drive", mapa)
    else:
        idx["ef_drive"] = None

    if curso.tiene_trabajo_final and idx["tf_av"]:
        idx["tf_drive"] = _agregar_columna(ws, "TF Drive", mapa)
    else:
        idx["tf_drive"] = None

    if curso.tiene_trabajo_libro:
        idx["devo_total"] = _agregar_columna(ws, "Devocionales Entregados", mapa)
        idx["devo_pct"] = _agregar_columna(ws, "% Devocionales", mapa)
    else:
        idx["devo_total"] = idx["devo_pct"] = None

    idx["estado_final"] = _agregar_columna(ws, "Estado Final", mapa)

    # Columnas S1..S{num_clases}: asistencia por clase copiada del Drive
    idx["clases_drive_inicio"] = ws.max_column + 1
    for i in range(1, curso.num_clases + 1):
        _agregar_columna(ws, f"S{i}", mapa)

    idx["mapa"] = mapa
    return idx


# ============================================================
# Paso 2: nota de asistencia (0-20) según clases asistidas
# ============================================================

def calcular_nota_asistencia(clases_asistidas: int, curso: ConfiguracionCurso) -> int:
    if curso.num_clases == 9:
        return config.TABLA_NOTA_ASISTENCIA_9_CLASES.get(clases_asistidas, 0)
    # Curso con un número de clases distinto de 9: escala proporcional.
    nota = round((clases_asistidas / curso.num_clases) * config.NOTA_MAXIMA_ASISTENCIA)
    return max(0, min(config.NOTA_MAXIMA_ASISTENCIA, nota))


def _aprobo_por_asistencia(clases_asistidas: int, curso: ConfiguracionCurso) -> bool:
    minimo = round(curso.num_clases * config.FRACCION_MINIMA_ASISTENCIA_APROBAR)
    return clases_asistidas >= minimo


#