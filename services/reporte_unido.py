"""
Construye el reporte "unido": notas de Moodle + estado de finalización
de cada clase (checks), cruzados por DNI — para cada grupo que ingresó
la tutora (C11, C21, o ambos), y luego combinados en un solo reporte.

El filtrado por grupo ya viene hecho desde la descarga (se le pide a
Moodle el ID numérico de cada grupo por separado), así que acá solo se
combinan los resultados de cada grupo.

Cambio clave respecto al original: antes se pegaban notas y checks
"lado a lado" (concat por posición), asumiendo que las filas venían en
el mismo orden en los dos exports de Moodle. Si un alumno faltaba o
estaba en otro orden en uno de los dos archivos, todo el reporte se
desalineaba silenciosamente. Ahora se cruza por DNI, que es una
columna real en ambos archivos, así que un desorden o alumno faltante
ya no corrompe el resto de las filas — en el peor caso, ese alumno
puntual queda marcado como incompleto y se reporta al usuario.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field

import pandas as pd

from domain.curso import ConfiguracionCurso
from services import layout

logger = logging.getLogger(__name__)


@dataclass
class ResultadoReporteUnido:
    df: pd.DataFrame
    indicadores_av: dict          # {"tiene_tf_av": bool, "tiene_ef_av": bool}
    num_clases_detectado: int     # clases encontradas en el CSV de checks
    alumnos_sin_checks: list[str] = field(default_factory=list)  # DNIs en notas sin match en checks
    advertencias: list[str] = field(default_factory=list)


def _procesar_un_grupo(grupo_id: str, notas_bytes: bytes, checks_bytes: bytes) -> tuple[pd.DataFrame, dict, int]:
    df_notas_crudo = pd.read_excel(io.BytesIO(notas_bytes))
    df_notas, indicadores_av = layout.aplicar_layout_notas(df_notas_crudo)
    df_notas["DNI"] = df_notas["DNI"].astype(str).str.strip()

    df_checks = layout.leer_checks(checks_bytes)
    df_checks["DNI"] = df_checks["DNI"].astype(str).str.strip()
    num_clases_detectado = len([c for c in df_checks.columns if c != "DNI"])

    df = df_notas.merge(df_checks, on="DNI", how="left", indicator=True)
    df["_grupo_id"] = grupo_id
    return df, indicadores_av, num_clases_detectado


def construir_reporte_unido(
    archivos_por_grupo: dict[str, tuple[bytes, bytes]], curso: ConfiguracionCurso
) -> ResultadoReporteUnido:
    """
    archivos_por_grupo: { "45094": (notas_bytes, checks_bytes), "45071": (...) }
    Una entrada por cada ID de grupo que ingresó la tutora (C11 / C21).
    """
    advertencias = []
    partes = []
    indicadores_por_grupo = {}
    num_clases_por_grupo = {}

    for grupo_id, (notas_bytes, checks_bytes) in archivos_por_grupo.items():
        df, indicadores_av, num_clases_detectado = _procesar_un_grupo(grupo_id, notas_bytes, checks_bytes)
        partes.append(df)
        indicadores_por_grupo[grupo_id] = indicadores_av
        num_clases_por_grupo[grupo_id] = num_clases_detectado

    df = pd.concat(partes, ignore_index=True)

    # Si algún alumno aparece en más de un grupo (no debería pasar, pero
    # por seguridad), se conserva solo la primera aparición y se avisa.
    duplicados = df[df.duplicated("DNI", keep=False)]
    if not duplicados.empty:
        dnis_dup = sorted(duplicados["DNI"].unique())
        advertencias.append(
            f"{len(dnis_dup)} alumno(s) aparecen en más de un grupo descargado, se usó solo "
            f"la primera aparición: {', '.join(dnis_dup)}"
        )
        df = df.drop_duplicates("DNI", keep="first")

    # Los indicadores (tiene EF/TF en AV) deberían ser iguales para todos
    # los grupos de un mismo curso; si no lo son, es una señal real de
    # que algo no calza y hay que avisar en vez de elegir uno en silencio.
    valores_indicadores = list(indicadores_por_grupo.values())
    indicadores_av = valores_indicadores[0] if valores_indicadores else {}
    if any(v != indicadores_av for v in valores_indicadores):
        advertencias.append(
            f"Los grupos descargados no coinciden en qué indicadores tienen en el Aula "
            f"Virtual: {indicadores_por_grupo}. Se usó el del primer grupo; revisa que "
            "los IDs de grupo correspondan al mismo curso."
        )
        for otros in valores_indicadores[1:]:
            indicadores_av = {k: (indicadores_av.get(k) or otros.get(k)) for k in indicadores_av}

    valores_num_clases = list(num_clases_por_grupo.values())
    num_clases_detectado = max(valores_num_clases) if valores_num_clases else 0
    if len(set(valores_num_clases)) > 1:
        advertencias.append(
            f"Los grupos descargados no tienen el mismo número de clases en el CSV de "
            f"checks: {num_clases_por_grupo}."
        )
    if num_clases_detectado != curso.num_clases:
        advertencias.append(
            f"Marcaste {curso.num_clases} clases en el formulario, pero el archivo de "
            f"checks trae {num_clases_detectado} columnas de clase. Se usará lo que "
            f"indica el formulario para calcular notas; revisa que sea correcto."
        )

    alumnos_sin_checks = (
        df.loc[df["_merge"] == "left_only", "Nombre"] + " " + df.loc[df["_merge"] == "left_only", "Apellidos"]
    ).tolist()
    if alumnos_sin_checks:
        advertencias.append(
            f"{len(alumnos_sin_checks)} alumno(s) están en el reporte de notas pero no "
            "se encontraron en el reporte de checks (puede que no hayan iniciado ninguna "
            "actividad todavía): " + ", ".join(alumnos_sin_checks[:10])
            + ("..." if len(alumnos_sin_checks) > 10 else "")
        )
    df = df.drop(columns=["_merge", "_grupo_id"])

    logger.info(
        "Reporte unido construido: %d alumnos (%d grupo(s)), %d sin match en checks.",
        len(df), len(archivos_por_grupo), len(alumnos_sin_checks),
    )

    return ResultadoReporteUnido(
        df=df,
        indicadores_av=indicadores_av,
        num_clases_detectado=num_clases_detectado,
        alumnos_sin_checks=alumnos_sin_checks,
        advertencias=advertencias,
    )