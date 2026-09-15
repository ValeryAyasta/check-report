"""Utilidades genéricas de formato y manejo de DataFrames/Excel."""
from __future__ import annotations

from openpyxl.styles import PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
import pandas as pd

import config


def normalizar_dni(serie: pd.Series) -> pd.Series:
    """Normaliza una columna de DNI a texto de 8 dígitos, sin decimales
    residuales (Excel a veces guarda el DNI como número tipo 12345678.0)."""
    return (
        serie.astype(str)
             .str.strip()
             .str.split(".").str[0]
             .str.zfill(8)
    )


def autoajustar_columnas(ws: Worksheet) -> None:
    """Ajusta el ancho de cada columna al contenido más largo que tenga."""
    for col in ws.columns:
        max_length = 0
        column_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            except Exception:
                pass
        ws.column_dimensions[column_letter].width = max_length + 2


def set_fill_por_valor(value, target_cell) -> None:
    """Colorea una celda de asistencia: verde si hay un valor real
    (el alumno asistió), gris si está vacía (no asistió)."""
    if value not in (0, None, ""):
        color = config.COLOR_CHECK_PRESENTE
    else:
        color = config.COLOR_CHECK_AUSENTE
    target_cell.fill = PatternFill(start_color=color, end_color=color, fill_type="solid")


def contar_celdas_con_valor(celdas) -> int:
    """Cuenta cuántas celdas de una fila de asistencia tienen un valor > 0."""
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