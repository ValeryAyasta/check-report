"""
Verifica la jerarquía de excepciones de negocio (domain/excepciones.py):
- Todas cuelgan de CheckReportError, para que app.py pueda atraparlas
  con un único `except CheckReportError`.
- Cada una trae su `codigo` esperado.
- Los re-exports desde los módulos originales (domain.curso,
  infrastructure.moodle.auth, infrastructure.moodle.downloader,
  infrastructure.excel.layout_moodle, infrastructure.excel.excel_writer,
  application.pipeline) siguen apuntando a la MISMA clase que
  domain.excepciones — así una tutora que dispara un LoginError
  real, capturado como `except CheckReportError` en app.py, es
  exactamente la misma clase sin importar desde dónde se importe.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from domain.excepciones import (
    CheckReportError,
    ConfiguracionInvalidaError,
    MoodleError,
    LoginError,
    DownloadError,
    LayoutMoodleError,
    ReporteFinalError,
    PipelineError,
)


@pytest.mark.parametrize(
    "excepcion,codigo_esperado",
    [
        (ConfiguracionInvalidaError, "CONFIGURACION_INVALIDA"),
        (LoginError, "MOODLE_LOGIN_FALLIDO"),
        (DownloadError, "MOODLE_DESCARGA_FALLIDA"),
        (LayoutMoodleError, "MOODLE_FORMATO_INESPERADO"),
        (ReporteFinalError, "REPORTE_FINAL_FALLIDO"),
        (PipelineError, "PIPELINE_FALLIDO"),
    ],
)
def test_todas_heredan_de_check_report_error_con_su_codigo(excepcion, codigo_esperado):
    instancia = excepcion("mensaje de prueba")
    assert isinstance(instancia, CheckReportError)
    assert instancia.codigo == codigo_esperado
    assert str(instancia) == "mensaje de prueba"


def test_errores_de_moodle_heredan_de_moodle_error():
    for excepcion in (LoginError, DownloadError, LayoutMoodleError):
        assert issubclass(excepcion, MoodleError)
        assert issubclass(excepcion, CheckReportError)


def test_codigo_se_puede_sobrescribir_por_instancia():
    e = CheckReportError("mensaje", codigo="ALGO_ESPECIFICO")
    assert e.codigo == "ALGO_ESPECIFICO"


def test_atrapar_check_report_error_atrapa_cualquier_subclase():
    """Este es el comportamiento que app.py explota: un único
    `except CheckReportError` cubre cualquier error de negocio actual
    o futuro, sin tener que enumerar cada tipo."""
    for excepcion in (
        ConfiguracionInvalidaError, LoginError, DownloadError,
        LayoutMoodleError, ReporteFinalError, PipelineError,
    ):
        with pytest.raises(CheckReportError):
            raise excepcion("boom")


def test_reexports_apuntan_a_la_misma_clase():
    from domain.curso import ConfiguracionInvalidaError as ReexportCurso
    from infrastructure.moodle.auth import LoginError as ReexportAuth
    from infrastructure.moodle.downloader import DownloadError as ReexportDownloader
    from infrastructure.excel.layout_moodle import LayoutMoodleError as ReexportLayout
    from infrastructure.excel.excel_writer import ReporteFinalError as ReexportCalculator
    from application.pipeline import PipelineError as ReexportPipeline

    assert ReexportCurso is ConfiguracionInvalidaError
    assert ReexportAuth is LoginError
    assert ReexportDownloader is DownloadError
    assert ReexportLayout is LayoutMoodleError
    assert ReexportCalculator is ReporteFinalError
    assert ReexportPipeline is PipelineError
