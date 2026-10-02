"""
Descarga los reportes de Moodle (notas y checks de actividad) para un
curso completo (group=0, "todos los grupos"). El filtrado por grupo
(C11/C21) NO se hace acá: se hace después, por texto, comparando contra
la columna "Grupo" del export (ver infrastructure/excel/layout_moodle.filtrar_por_grupo).

Se descarga el curso completo una sola vez, sin importar cuántos grupos
tenga la tutora a cargo — es más simple y más rápido que pedirle a
Moodle un grupo a la vez (que requeriría 2 descargas si la tutora tiene
C11 y C21).

Ambos métodos devuelven bytes crudos (no un DataFrame ya parseado):
quien decide cómo interpretar esos bytes es infrastructure/excel/layout_moodle.py, que es
el único lugar del proyecto que conoce el formato exacto de cada archivo.
"""
from __future__ import annotations

import logging
from typing import Optional

import requests

from infrastructure.moodle.auth import MoodleSession
# Re-exportada: el resto del proyecto sigue importando
# `from infrastructure.moodle.downloader import DownloadError`.
from domain.excepciones import DownloadError

logger = logging.getLogger(__name__)

__all__ = ["ReportDownloader", "DownloadError"]


class ReportDownloader:
    """
    Recibe una MoodleSession ya construida (inyectada) en vez de
    armarla internamente a partir de usuario/contraseña — y, muy
    importante, el constructor NO hace ninguna llamada de red: solo
    guarda la referencia. El login real ocurre en `iniciar_sesion()`,
    un paso explícito y separado.

    Por qué importa: antes, `ReportDownloader(usuario, password)` ya
    disparaba un login real dentro del `__init__`. Eso mezclaba dos
    responsabilidades (construir el objeto vs. autenticarse) y hacía
    imposible instanciar un ReportDownloader en un test sin que se
    intentara una conexión real a Moodle. Con el login afuera, un test
    puede inyectar una MoodleSession que envuelve un
    `requests.Session` falso y llamar a `descargar_*` directamente,
    sin pasar por `iniciar_sesion()` en absoluto (ver
    tests/test_moodle_downloader.py).
    """

    def __init__(self, moodle_session: MoodleSession, timeout: Optional[int] = None):
        self.moodle_session = moodle_session
        self.timeout = timeout if timeout is not None else moodle_session.settings.timeout_segundos

    def iniciar_sesion(self) -> None:
        """Inicia sesión en Moodle. Hay que llamarlo antes de
        `descargar_csv_checks` / `descargar_excel_notas` cuando la
        MoodleSession inyectada todavía no está autenticada (el caso
        normal en producción; en un test se puede inyectar una sesión
        ya "autenticada" y saltarse este paso)."""
        self.moodle_session.login(timeout=self.timeout)

    @property
    def session(self) -> requests.Session:
        """La sesión HTTP subyacente. Es la MISMA instancia de
        `requests.Session` que usa `self.moodle_session` — login() no
        crea una sesión nueva, autentica la que ya había (con
        cookies), así que no hace falta guardar una copia aparte acá."""
        return self.moodle_session.session

    def descargar_csv_checks(self, course_id: int, group_id: int = 0) -> bytes:
        """Descarga el CSV de finalización de actividades (checks) del curso completo."""
        params = {
            "course": course_id,
            "group": group_id,
            "activityinclude": "all",
            "activityorder": "orderincourse",
            "format": "excelcsv",
        }
        logger.info("Descargando CSV de checks (curso=%s)...", course_id)
        export_url = f"{self.moodle_session.base_url}/report/progress/index.php"
        resp = self.session.get(export_url, params=params, timeout=self.timeout)

        if not resp.ok:
            raise DownloadError(f"Moodle respondió con error HTTP {resp.status_code} al descargar el CSV de checks.")

        content_type = resp.headers.get("Content-Type", "")
        if "text/html" in content_type or resp.content.strip().startswith(b"<!DOCTYPE html"):
            raise DownloadError(
                "No se pudo descargar el CSV de checks: Moodle devolvió una página HTML en "
                "lugar del archivo (la sesión pudo haber expirado, o el ID de curso no existe)."
            )
        return resp.content

    def descargar_excel_notas(self, course_id: int, group_id: int = 0) -> bytes:
        """Descarga el Excel de calificaciones del curso completo."""
        try:
            sesskey, itemids = self.moodle_session.obtener_sesskey(course_id, group_id)
        except Exception as e:
            raise DownloadError(
                f"No se pudo preparar la descarga de notas para el curso {course_id}. "
                "Verifica que el ID de curso sea correcto y que tu usuario tenga acceso a él."
            ) from e

        export_url = f"{self.moodle_session.base_url}/grade/export/xls/export.php"

        payload = [
            ("mform_isexpanded_id_gradeitems", "1"),
            ("checkbox_controller1", "1"),
            ("mform_isexpanded_id_options", "1"),
            ("export_onlyactive", "1"),
            ("id", str(course_id)),
            ("group", str(group_id)),
            ("sesskey", sesskey),
            ("_qf__grade_export_form", "1"),
        ]
        payload += [
            ("display[real]", "0"),
            ("display[real]", "1"),
            ("display[percentage]", "0"),
            ("display[letter]", "0"),
        ]
        payload += [
            ("export_feedback", "0"),
            ("decimals", "0"),
            ("submitbutton", "Descargar"),
        ]
        for key, value in itemids.items():
            payload.append((key, value))

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{self.moodle_session.base_url}/grade/export/xls/index.php?id={course_id}&group={group_id}",
        }

        logger.info("Enviando solicitud de exportación de notas (curso=%s)...", course_id)
        resp = self.session.post(export_url, data=payload, headers=headers, timeout=self.timeout)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")
        if "spreadsheetml" not in content_type:
            raise DownloadError(
                "No se recibió un archivo Excel de Moodle. Puede que el ID de curso sea "
                f"incorrecto o que haya ocurrido un error en la exportación (Content-Type: {content_type})."
            )
        return resp.content