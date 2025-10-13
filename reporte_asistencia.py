# reporte_asistencia.py
import logging
import os

from pathlib import Path

from services.auth import MoodleSession, LoginError
from services.calculator import pegar_asistencias_y_calcular
from services.downloader import ReportDownloader
from services.merge_padron import MergePadron
from services.reporte_unido import ReporteUnido, ProcessingError

# ---------- Config / Logging ----------
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

def main_pipeline(usuario: str, password: str, use_padron: bool, padron_path: Path, codigo_curso: int, grupos: list[int], tutores_dir: Path):
    """
     Ejecuta el pipeline completo de asistencia.
     - usuario, password: credenciales Moodle
     - padron_path: ruta al archivo de padrón (Path o str)
     - codigo_curso: id del curso
     - grupos: lista de IDs de grupos (ej: [37240, 37233])
     Retorna la ruta al archivo final generado.
     """
    base_dir = Path("").resolve()
    out_unido = "reporte-asistencia-unido.xlsx"
    out_final = base_dir / "asistencia_final.xlsx"

    # 1) Login
    try:
        session = MoodleSession(usuario, password).login()
    except LoginError as e:
        logger.error("No se pudo iniciar sesión: %s", e)
        raise

    # 2) Generar reporte unido
    try:
        downloader = ReportDownloader(session)
        reporte_unido = ReporteUnido(downloader).generar_reporte(
            course=codigo_curso,
            grupos=grupos,
            output_file=out_unido
        )
    except ProcessingError as e:
        logger.error("Error en generar_reporte_unido: %s", e)
        raise

    # 3) Merge con padrón
    try:
        if use_padron and padron_path:
            reporte_unido = MergePadron(padron_path).merge(reporte_unido, out_unido)
    except ProcessingError as e:
        logger.error("Error en merge_con_padron: %s", e)
        raise

    # 4) Pegar asistencias y calcular faltas
    try:
        path_final = pegar_asistencias_y_calcular(
            base_dir / reporte_unido,
            tutores_dir,
            out_final
        )
    except ProcessingError as e:
        logger.error("Error en pegar_asistencias_y_calcular: %s", e)
        raise

    logger.info("Pipeline completado. Resultado final: %s", path_final)
    return path_final

# ---------- Ejemplo main (solo 3 llamadas / funciones) ----------
def main():
    USUARIO = os.environ.get("MOO_USER", "73048017")
    PASSWORD = os.environ.get("MOO_PASS", "984850250")
    padron_path = Path("").resolve() / "PADRÓN D3 2K25 - 2.xlsx"

    codigo_curso = 374  # DISCIPULADO 3
    grupos = [37240, 37233]  # mujeres, varones

    main_pipeline(USUARIO, PASSWORD, padron_path, codigo_curso, grupos)

if __name__ == "__main__":
    main()
