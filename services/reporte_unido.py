"""
Construye el reporte "unido": notas de Moodle (filtradas por grupo de
la tutora) + estado de finalización de cada clase (checks), cruzados
por DNI.

El curso se descarga completo (todos los grupos) una sola vez; el
filtrado a los grupos de la tutora (C11/C21) se hace acá, por texto,
contra la columna "Grupo" (ver services/layout.filtrar_por_grupo). El
cruce con checks se hace ANTES de filtrar, así que el resultado guarda
también la versión sin filtrar (df_todos_los_grupos) — se usa en
pipeline.py para "rescatar" alumnos que la tutora sí tiene en su Drive
pero que Moodle tiene asignados a otro grupo.

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
    df_todos_los_grupos: pd.DataFrame  # notas+checks de TODO el curso, sin filtrar por grupo
    indicadores_av: dict          # {"tiene_tf_av": bool, "tiene_ef_av": bool}
    num_clases_detectado: int     # clases encontradas en el CSV de checks
    alumnos_sin_checks: list[str] = field(default_factory=list)  # DNIs en notas sin match en checks
    advertencias: list[str] = field(default_factory=list)


def construir_reporte_unido(
    notas_bytes: bytes, checks_bytes: bytes, curso: ConfiguracionCurso
) -> ResultadoReporteUnido:
    advertencias = []

    df_notas_crudo = pd.read_excel(io.BytesIO(notas_bytes))
    df_notas, indicadores_av = layout.aplicar_layout_notas(df_notas_crudo)  # TODOS los grupos

    df_checks = layout.leer_checks(checks_bytes)
    columnas_clase = [c for c in df_checks.columns if c != "DNI"]
    num_clases_detectado = len(columnas_clase)

    if num_clases_detectado != curso.num_clases:
        advertencias.append(
            f"Marcaste {curso.num_clases} clases en el formulario, pero el archivo de "
            f"checks trae {num_clases_detectado} columnas de clase. Se usará lo que "
            f"indica el formulario para calcular notas; revisa que sea correcto."
        )

    # Se cruza por DNI UNA sola vez, con el curso completo (todos los
    # grupos) — es barato (un curso normal son un par de cientos de
    # filas), y así se puede filtrar por grupo sin tener que volver a
    # descargar ni volver a cruzar nada. df_todos_los_grupos se guarda
    # completo por si algún alumno del Drive de la tutora terminó
    # asignado a otro grupo en Moodle (ver pipeline.py, que lo usa para
    # "rescatarlo" igual en el reporte final).
    df_todos = df_notas.merge(df_checks, on="DNI", how="left", indicator=True)
    df_filtrado = layout.filtrar_por_grupo(df_todos, curso.grupos)

    alumnos_sin_checks = (
        df_filtrado.loc[df_filtrado["_merge"] == "left_only", "Nombre"]
        + " " + df_filtrado.loc[df_filtrado["_merge"] == "left_only", "Apellidos"]
    ).tolist()
    if alumnos_sin_checks:
        advertencias.append(
            f"{len(alumnos_sin_checks)} alumno(s) están en el reporte de notas pero no "
            "se encontraron en el reporte de checks (puede que no hayan iniciado ninguna "
            "actividad todavía): " + ", ".join(alumnos_sin_checks[:10])
            + ("..." if len(alumnos_sin_checks) > 10 else "")
        )

    df = df_filtrado.drop(columns=["_merge"])
    df_todos = df_todos.drop(columns=["_merge"])

    logger.info(
        "Reporte unido construido: %d alumnos (grupos: %s) de %d en el curso completo, "
        "%d sin match en checks.",
        len(df), curso.grupos, len(df_todos), len(alumnos_sin_checks),
    )

    return ResultadoReporteUnido(
        df=df,
        df_todos_los_grupos=df_todos,
        indicadores_av=indicadores_av,
        num_clases_detectado=num_clases_detectado,
        alumnos_sin_checks=alumnos_sin_checks,
        advertencias=advertencias,
    )


def rescatar_alumnos_de_otro_grupo(
    df_filtrado: pd.DataFrame, df_todos_los_grupos: pd.DataFrame, dnis_tutor: set[str],
) -> tuple[pd.DataFrame, list[str]]:
    """
    Si algún DNI que la tutora tiene en su Drive no aparece en el
    reporte ya filtrado por grupo, se busca en el curso completo (sin
    filtrar). Si existe ahí, se agrega igual al reporte final — lo que
    importa es que la tutora sí lo tiene registrado, aunque Moodle lo
    tenga asignado a otro grupo.

    Devuelve (df_con_los_rescatados_agregados, lista_de_textos_para_advertencia).
    """
    dnis_faltantes = dnis_tutor - set(df_filtrado["DNI"])
    if not dnis_faltantes:
        return df_filtrado, []

    filas_recuperadas = df_todos_los_grupos[df_todos_los_grupos["DNI"].isin(dnis_faltantes)]
    if filas_recuperadas.empty:
        return df_filtrado, []

    textos = [
        f"{fila['Nombre']} {fila['Apellidos']} (DNI {fila['DNI']}, grupo real: {fila['Grupo']})"
        for _, fila in filas_recuperadas.iterrows()
    ]
    df_resultado = pd.concat([df_filtrado, filas_recuperadas], ignore_index=True)
    return df_resultado, textos
