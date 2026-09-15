"""
Traduce config.COLUMNAS_NOTAS_MOODLE en operaciones concretas sobre el
DataFrame de notas descargado de Moodle: qué columnas quedarse, cómo
renombrarlas, y qué indicadores (Examen Final / Trabajo Final) tiene
el curso EN EL AULA VIRTUAL — detectado automáticamente a partir de
qué columnas trae el archivo, no de un checkbox que la tutora podría
olvidar marcar.

El filtrado por grupo (C11/C21) NO se hace acá: se hace directamente
en la descarga (services/downloader.py), pasando el ID numérico de
grupo que ingresa la tutora. Este módulo recibe archivos que ya vienen
filtrados a un solo grupo.

Esto reemplaza los `cols_to_drop = [3, 9]` / `columns[6]` fijos del
código original, que se desalineaban apenas un curso no tenía Trabajo
Final (la columna "Total del curso" se corría un puesto y el índice
fijo agarraba la columna equivocada).
"""
from __future__ import annotations

import io
import logging
import unicodedata
import pandas as pd

import config

logger = logging.getLogger(__name__)


class LayoutMoodleError(Exception):
    """El archivo descargado de Moodle no tiene la forma que config.py espera."""
    pass


def _normalizar(texto: str) -> str:
    texto = str(texto).strip().lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def _buscar_columna(df: pd.DataFrame, patrones: list[str]) -> str | None:
    columnas_norm = {col: _normalizar(col) for col in df.columns}
    for patron in patrones:
        patron_norm = _normalizar(patron)
        for col_real, col_norm in columnas_norm.items():
            if patron_norm in col_norm:
                return col_real
    return None


def aplicar_layout_notas(df_notas: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Devuelve (df_recortado_y_renombrado, indicadores_detectados).

    indicadores_detectados = {
        "tiene_examen_final_av": bool,
        "tiene_tf_av": bool,
    }
    Estos booleans reflejan lo que el Aula Virtual REALMENTE tiene,
    detectado del archivo — no lo que la tutora marcó en el formulario.
    El pipeline usa esto para no asumir columnas que no existen.
    """
    df = df_notas.copy()
    columnas_finales = {}
    indicadores = {}
    faltantes_obligatorias = []

    for clave, spec in config.COLUMNAS_NOTAS_MOODLE.items():
        col_real = _buscar_columna(df, spec["patrones"])

        if spec["condicional"] == "opcional":
            existe = col_real is not None
            indicadores[f"tiene_{clave}"] = existe
            if not existe:
                continue
        elif spec["condicional"] == "informativa":
            if col_real is None:
                continue  # no es obligatoria: si no está, simplemente se omite
        elif col_real is None:
            faltantes_obligatorias.append((clave, spec["patrones"]))
            continue

        if not spec["descartar"] and col_real is not None:
            columnas_finales[col_real] = spec["clave_final"]

    if faltantes_obligatorias:
        detalle = ", ".join(f"'{c}' (buscado como {p})" for c, p in faltantes_obligatorias)
        raise LayoutMoodleError(
            f"El archivo de notas descargado de Moodle no tiene las columnas obligatorias: "
            f"{detalle}. Columnas encontradas en el archivo: {list(df.columns)}. "
            "Es posible que Moodle haya cambiado el nombre de alguna columna: si es así, "
            "ajusta 'patrones' en config.COLUMNAS_NOTAS_MOODLE."
        )

    df = df[list(columnas_finales.keys())].rename(columns=columnas_finales)
    logger.info(
        "Layout de notas aplicado. Columnas finales: %s | Indicadores detectados: %s",
        list(df.columns), indicadores,
    )
    return df, indicadores


def leer_checks(contenido_csv: bytes) -> pd.DataFrame:
    """
    Lee el CSV de finalización de actividades de Moodle (una columna de
    estado + una de fecha por cada clase) y devuelve solo lo que se usa
    en el reporte: DNI y el estado ('Finalizado' / vacío) de cada clase,
    descartando las columnas de fecha (no se muestran en el reporte final).
    """
    df = pd.read_csv(
        io.BytesIO(contenido_csv), sep=config.CHECKS_SEPARADOR, encoding=config.CHECKS_ENCODING
    )

    col_dni = _buscar_columna(df, [config.CHECKS_PATRON_DNI])
    if col_dni is None:
        raise LayoutMoodleError(
            "El CSV de checks no tiene una columna de 'Nombre de usuario' (DNI). "
            f"Columnas encontradas: {list(df.columns)}."
        )

    columnas_clase = [c for c in df.columns if config.CHECKS_PATRON_COLUMNA_CLASE in _normalizar(c)]
    if not columnas_clase:
        raise LayoutMoodleError(
            "El CSV de checks no tiene columnas de clase (se esperaba encontrar "
            f"columnas con 'Clase' en el nombre). Columnas encontradas: {list(df.columns)}."
        )

    resultado = df[[col_dni] + columnas_clase].copy()
    resultado = resultado.rename(columns={col_dni: "DNI"})
    logger.info(
        "CSV de checks leído: %d clases detectadas (%s)",
        len(columnas_clase), columnas_clase,
    )
    return resultado