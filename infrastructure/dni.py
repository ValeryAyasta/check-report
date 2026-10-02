"""
Normalización de DNI/carnet de extranjería para poder CRUZAR alumnos
entre las distintas fuentes de datos (Moodle y el archivo de cada
tutora). No depende de openpyxl ni de ningún formato de archivo
concreto — solo de pandas, para poder aplicarse a una columna entera
de una sola vez — así que vive separado de infrastructure/excel/, que
sí es específico de manipular archivos .xlsx.
"""
from __future__ import annotations

import pandas as pd


def normalizar_dni_valor(valor) -> str:
    """Normaliza un identificador de alumno (DNI o carnet de extranjería)
    para poder CRUZARLO entre Moodle y el archivo de la tutora.

    Moodle exporta este campo como NÚMERO tanto en el Excel de notas
    como en el CSV de checks, así que cualquier cero a la izquierda se
    pierde ahí (ej: DNI "07144588" -> 7144588, carnet "003112762" -> 3112762).
    El archivo de la tutora, en cambio, sí guarda el valor como texto,
    con los ceros.

    Como el DNI siempre tiene 8 dígitos, pero el carnet de extranjería NO
    tiene un largo fijo (puede ser de 9 o más), no se puede "adivinar"
    cuántos ceros había forzando un ancho fijo — eso funciona para DNI,
    pero rompe carnets de extranjería. En su lugar, para cruzar ambos
    lados se quitan TODOS los ceros a la izquierda de los dos por igual:
    así "07144588" y "7144588" cruzan entre sí, y también "003112762"
    con "3112762", sin importar el largo real de cada uno.

    Esto es solo para USAR COMO LLAVE DE CRUCE, no para mostrar en el
    reporte — para eso, se prefiere el valor tal como está escrito en el
    archivo de la tutora (ver infrastructure/excel/excel_writer.py), que
    si está en texto ya tiene el formato/ceros correctos.
    """
    texto = str(valor).strip()
    if texto.endswith(".0"):
        texto = texto[:-2]
    return texto.lstrip("0") or "0"


def normalizar_dni(serie: pd.Series) -> pd.Series:
    """Igual que normalizar_dni_valor(), pero aplicado a una columna completa."""
    return serie.apply(normalizar_dni_valor)
