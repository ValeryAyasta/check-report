"""
Orquesta el pipeline completo:
  login a Moodle -> descargar notas y checks del curso completo ->
  filtrar por grupo (C11/C21) -> pegar asistencia/devocionales de cada
  tutora -> generar Excel final con formato.

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
from services.reporte_unido import construir_reporte_unido, rescatar_alumnos_de_otro_grupo
from services.calculator import generar_reporte_final, extraer_dnis_tutor, ReporteFinalError, ResultadoCalculo
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


def _bullets(items: list[str], limite: int = 15) -> str:
    """Arma una lista en viñetas (una por línea) para mostrar en las
    advertencias, cortando en `limite` ítems si hay muchos."""
    mostrar = items[:limite]
    texto = "\n".join(f"• {item}" for item in mostrar)
    if len(items) > limite:
        texto += f"\n… y {len(items) - limite} más"
    return texto


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

    avisar(f"Descargando notas y checks del curso {curso.curso_id}...")
    try:
        notas_bytes = downloader.descargar_excel_notas(curso.curso_id)
        checks_bytes = downloader.descargar_csv_checks(curso.curso_id)
    except DownloadError as e:
        raise PipelineError(str(e)) from e

    avisar(f"Filtrando alumnos de los grupos {curso.grupos}...")
    try:
        resultado_unido = construir_reporte_unido(notas_bytes, checks_bytes, curso)
    except LayoutMoodleError as e:
        raise PipelineError(str(e)) from e

    df_reporte = resultado_unido.df

    # "Rescate": si la tutora tiene en su Drive un alumno que Moodle
    # asignó a otro grupo (o que quedó afuera del filtro por cualquier
    # motivo), se busca en el curso completo (sin filtrar) y, si existe,
    # se agrega igual al reporte final — lo que importa es que la
    # tutora sí lo tiene registrado. Esto es barato: el curso completo
    # ya está en memoria (un par de cientos de filas), así que no agrega
    # ninguna descarga ni cruce adicional, solo una búsqueda por DNI.
    avisar("Revisando si algún alumno del Drive quedó en otro grupo...")
    dnis_tutor_todos: set[str] = set()
    for archivo in Path(tutores_dir).glob("*.xlsx"):
        dnis_tutor_todos |= extraer_dnis_tutor(archivo)

    df_reporte, alumnos_recuperados = rescatar_alumnos_de_otro_grupo(
        df_reporte, resultado_unido.df_todos_los_grupos, dnis_tutor_todos
    )

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

    if alumnos_recuperados:
        advertencias.append(
            f"{len(alumnos_recuperados)} alumno(s) estaban asignados a OTRO grupo en Moodle, "
            "pero como la tutora sí los tiene en su Drive, se agregaron igual al reporte final "
            "(revisa que el grupo asignado en Moodle sea el correcto):\n"
            + _bullets(alumnos_recuperados)
        )
    if calculo.dnis_no_encontrados_en_drive_pero_no_en_moodle:
        dnis_unicos = sorted(set(calculo.dnis_no_encontrados_en_drive_pero_no_en_moodle))
        advertencias.append(
            f"{len(dnis_unicos)} DNI(s) están en el Drive de alguna tutora pero NO se "
            "encontraron en Moodle en absoluto (ni en este grupo ni en otro — revisa si el "
            "DNI está mal tipeado en el Drive, o si el alumno no está matriculado en este "
            "curso):\n" + _bullets(dnis_unicos)
        )
    if calculo.alumnos_en_moodle_sin_registro_en_drive:
        advertencias.append(
            f"{len(calculo.alumnos_en_moodle_sin_registro_en_drive)} alumno(s) están en el "
            "reporte de Moodle (en el grupo correcto) pero NINGUNA tutora tiene su registro "
            "de asistencia en Drive (su fila queda sin 'Estado Final'):\n"
            + _bullets(calculo.alumnos_en_moodle_sin_registro_en_drive)
        )
    if calculo.archivos_tutor_sin_hoja_asistencia:
        advertencias.append(
            "Estos archivos no tienen una hoja 'ASISTENCIA' y se ignoraron:\n"
            + _bullets(calculo.archivos_tutor_sin_hoja_asistencia)
        )
    if not calculo.tutores_procesados:
        advertencias.append(
            "No se pudo leer asistencia de ningún archivo de tutora: revisa que hayas "
            "subido los archivos correctos."
        )

    avisar("¡Reporte final generado!")
    return ResultadoPipeline(ruta_excel_final=ruta_final, advertencias=advertencias, calculo=calculo)
