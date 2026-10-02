"""
Jerarquía de excepciones de negocio de la aplicación.

Todas las excepciones que una usuaria final (la tutora) puede llegar a
ver comparten esta raíz común: CheckReportError. Esto permite que
app.py tenga un único `except CheckReportError` en vez de un except
por cada tipo de error de cada servicio — y garantiza que si mañana se
agrega un nuevo tipo de error en algún servicio nuevo, con solo
heredar de CheckReportError (o de una de sus subclases) ya queda
atrapado correctamente sin tocar app.py.

REGLA: el mensaje (str(excepcion)) de CUALQUIER subclase de
CheckReportError se considera SEGURO para mostrar tal cual a la
usuaria final: en español, claro, y sin detalles técnicos internos
(rutas de archivo del servidor, tracebacks, nombres de variables).
Por eso, cuando se atrape una excepción de bajo nivel que NO sea de
esta jerarquía (ValueError, requests.RequestException, un KeyError de
openpyxl, etc.), hay que traducirla a una de estas antes de dejarla
subir — nunca dejar pasar el texto crudo de una excepción de librería
hasta el usuario.

Cada subclase tiene un `codigo` corto y estable: útil en logs, para
que el frontend reaccione distinto según el tipo de error en el
futuro, o para que soporte técnico identifique la categoría de un
problema sin tener que leer el mensaje completo.
"""
from __future__ import annotations


class CheckReportError(Exception):
    """Raíz de todas las excepciones de negocio de la aplicación.

    No se instancia directamente en el código de negocio: se usa
    siempre una de sus subclases, que ya trae su propio `codigo`.
    """
    codigo: str = "ERROR_GENERICO"

    def __init__(self, mensaje: str, *, codigo: str | None = None):
        super().__init__(mensaje)
        if codigo is not None:
            self.codigo = codigo


class ConfiguracionInvalidaError(CheckReportError):
    """La tutora ingresó datos incompletos o inconsistentes en el
    formulario (ID de curso, grupos, número de clases, etc.)."""
    codigo = "CONFIGURACION_INVALIDA"


class MoodleError(CheckReportError):
    """Raíz de errores relacionados a la comunicación con el Aula
    Virtual (Moodle). No se instancia directamente: usar una de sus
    subclases (LoginError, DownloadError, LayoutMoodleError)."""
    codigo = "MOODLE_ERROR"


class LoginError(MoodleError):
    """No se pudo iniciar sesión en Moodle: credenciales incorrectas,
    Moodle caído, o un cambio en la página de login que rompe el
    scraping del token/sesskey (recordar: es una API no documentada)."""
    codigo = "MOODLE_LOGIN_FALLIDO"


class DownloadError(MoodleError):
    """La sesión inició correctamente pero la descarga de notas o de
    checks falló (curso inexistente, error HTTP, respuesta con un
    Content-Type inesperado)."""
    codigo = "MOODLE_DESCARGA_FALLIDA"


class LayoutMoodleError(MoodleError):
    """El archivo descargado de Moodle no tiene la forma que
    config.py espera (columna obligatoria faltante, grupo inexistente
    en el archivo, etc.). El caso más probable con el tiempo: Moodle
    cambió el nombre de alguna columna y hay que ajustar
    config.COLUMNAS_NOTAS_MOODLE."""
    codigo = "MOODLE_FORMATO_INESPERADO"


class ReporteFinalError(CheckReportError):
    """Error procesando los archivos de las tutoras (Drive) o
    generando el Excel final: archivo corrupto, hoja faltante,
    reporte unido ilegible, ningún archivo .xlsx subido, etc."""
    codigo = "REPORTE_FINAL_FALLIDO"


class PipelineError(CheckReportError):
    """Envoltorio genérico para un error de negocio que ocurre en la
    orquestación del pipeline y no encaja en ninguna categoría más
    específica de arriba.

    Úsalo solo si de verdad no aplica ninguna de las excepciones más
    concretas — en pipeline.py, lo normal es dejar que LoginError,
    DownloadError, LayoutMoodleError o ReporteFinalError suban tal
    cual (ya son CheckReportError, así que app.py las atrapa igual);
    no hace falta "traducirlas" a PipelineError solo para cambiarles
    el tipo.
    """
    codigo = "PIPELINE_FALLIDO"
