"""
Orquesta el pipeline completo:
  login a Moodle -> descargar notas y checks -> filtrar por grupo (C11/C21)
  -> pegar asistencia/devocionales de cada tutora -> generar Excel final
  con formato.

Las credenciales de Moodle SIEMPRE vienen como parámetro (las ingresa la
tutora en el formulario en cada ejecución) — nunca se guardan en el
servidor ni tienen un valor por defecto en el código.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from domain.curso import ConfiguracionCurso
from services.auth import LoginError
from services.downloader import ReportDownloader, DownloadError
from services.reporte_unido import construir_reporte_unido
from services.calculator import generar_reporte_final, ReporteFinalError, ResultadoCalculo
from services.layout import LayoutMoodleError

logger = logging.getLogger(__name__)


class PipelineError(Exception):
    """Error de negocio esperado en algún paso (el mensaje ya está listo para mostrarse al usuario)."""
    pass


@dataclass
class ResultadoPipeline:
    ruta_excel_final: Path
    advertencias: list[str] = field(default_factory=list)
    calculo: Optional[ResultadoCalculo] = None


def ejecutar_pipeline(
    usuario: str,
    password: str,
    curso: ConfiguracionCurso,
    tutores_dir: Path,
    dir_trabajo: Path,
    on_progreso: Optional[Callable[[str], None]] = None,
) -> ResultadoPipeline:
    def avisar(mensaje: str) -> None:
        logger.info(mensaje)
        if on_progreso:
            on_progreso(mensaje)

    dir_trabajo.mkdir(parents=True, exist_ok=True)

    avisar("Iniciando sesión en Moodle...")
    try:
        downloader = ReportDownloader(usuario, password)
    except LoginError as e:
        raise PipelineError(str(e)) from e

    avisar(f"Descargando notas y checks del curso {curso.curso_id} (grupos: {', '.join(curso.grupos)})...")
    archivos_por_grupo = {}
    for grupo_id in curso.grupos:
        try:
            avisar(f"  Descargando notas del grupo {grupo_id}...")
            notas_bytes = downloader.descargar_excel_notas(curso.curso_id, int(grupo_id))
            avisar(f"  Descargando checks del grupo {grupo_id}...")
            checks_bytes = downloader.descargar_csv_checks(curso.curso_id, int(grupo_id))
        except DownloadError as e:
            raise PipelineError(f"Grupo {grupo_id}: {e}") from e
        archivos_por_grupo[grupo_id] = (notas_bytes, checks_bytes)

    avisar("Cruzando notas y checks por DNI...")
    try:
        resultado_unido = construir_reporte_unido(archivos_por_grupo, curso)
    except LayoutMoodleError as e:
        raise PipelineError(str(e)) from e

    df_reporte = resultado_unido.df
    ruta_reporte = dir_trabajo / "reporte_unido.xlsx"
    df_reporte.to_excel(ruta_reporte, index=False)

    avisar("Pegando asistencia y devocionales de cada tutora...")
    nombre_archivo = "Reporte_" + "".join(
        c if c.isalnum() else "_" for c in curso.nombre
    ) + ".xlsx"
    ruta_final = dir_trabajo / nombre_archivo
    try:
        ruta_final, calculo = generar_reporte_final(ruta_reporte, tutores_dir, ruta_final, curso)
    except ReporteFinalError as e:
        raise PipelineError(str(e)) from e

    advertencias = list(resultado_unido.advertencias)
    if calculo.dnis_no_encontrados_en_reporte:
        dnis_unicos = sorted(set(calculo.dnis_no_encontrados_en_reporte))
        advertencias.append(
            f"{len(dnis_unicos)} DNI(s) de los archivos de tutora no se encontraron en el "
            f"reporte principal (puede que ese alumno no esté en el grupo/curso seleccionado): "
            + ", ".join(dnis_unicos[:15]) + ("..." if len(dnis_unicos) > 15 else "")
        )
    if calculo.archivos_tutor_sin_hoja_asistencia:
        advertencias.append(
            "Estos archivos no tienen una hoja 'ASISTENCIA' y se ignoraron: "
            + ", ".join(calculo.archivos_tutor_sin_hoja_asistencia)
        )
    if not calculo.tutores_procesados:
        advertencias.append(
            "No se pudo leer asistencia de ningún archivo de tutora: revisa que hayas "
            "subido los archivos correctos."
        )

    avisar("¡Reporte final generado!")
    return ResultadoPipeline(ruta_excel_final=ruta_final, advertencias=advertencias, calculo=calculo)