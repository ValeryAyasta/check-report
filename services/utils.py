from openpyxl.styles import PatternFill
from openpyxl.utils import get_column_letter
import pandas as pd


# ---------- Utilities ----------
def normalizar_dni(serie: pd.Series) -> pd.Series:
    return (
        serie.astype(str)
             .str.strip()
             .str.split(".").str[0]
             .str.zfill(8)
    )

def autoajustar_columnas(ws):
    for col in ws.columns:
        max_length = 0
        column = col[0].column
        column_letter = get_column_letter(column)
        for cell in col:
            try:
                if cell.value:
                    length = len(str(cell.value))
                    if length > max_length:
                        max_length = length
            except Exception:
                pass
        ws.column_dimensions[column_letter].width = max_length + 2

def set_fill_by_value(value, target):
    """Asigna color verde o gris a la celda destino según el valor."""
    if value not in (0, None, ""):
        color = "FF34A853"  # verde
    else:
        color = "FF595959"  # gris
    target.fill = PatternFill(start_color=color, end_color=color, fill_type="solid")