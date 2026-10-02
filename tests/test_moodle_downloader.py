import pytest

from infrastructure.moodle.auth import MoodleSession
from infrastructure.moodle.downloader import ReportDownloader, DownloadError
from infrastructure.moodle.settings import MoodleSettings
from tests._fakes import FakeSession, FakeResponse, HTML_LOGIN_OK

BASE_URL = "https://fake.moodle.test"
SETTINGS = MoodleSettings(base_url=BASE_URL, timeout_segundos=5)


class TestConstructorSinIO:
    def test_construir_un_reportdownloader_no_hace_ninguna_llamada_de_red(self):
        """Este es el cambio central de este refactor: antes,
        `ReportDownloader(usuario, password)` ya intentaba loguearse
        dentro del __init__. Ahora el constructor solo guarda la
        referencia a la MoodleSession inyectada — se puede probar acá
        con un FakeSession que ni siquiera tiene respuestas
        configuradas: si el constructor intentara hacer una petición,
        este test fallaría con el AssertionError de FakeSession."""
        fake = FakeSession()  # sin ninguna respuesta configurada a propósito
        sesion = MoodleSession("usuario", "clave", SETTINGS, session=fake)

        downloader = ReportDownloader(sesion)  # no debe lanzar nada

        assert fake.llamadas == []
        assert downloader.timeout == 5  # tomado de SETTINGS.timeout_segundos, no de un default propio

    def test_iniciar_sesion_es_un_paso_explícito_y_separado(self):
        fake = FakeSession(
            respuestas_get={"/login/index.php": FakeResponse(text=HTML_LOGIN_OK, url=f"{BASE_URL}/login/index.php")},
            respuestas_post={"/login/index.php": FakeResponse(text="ok", url=f"{BASE_URL}/my/")},
        )
        sesion = MoodleSession("usuario", "clave", SETTINGS, session=fake)
        downloader = ReportDownloader(sesion)
        assert fake.llamadas == []  # todavía nada, justo después de construir

        downloader.iniciar_sesion()

        assert fake.llamadas != []  # ahora sí se llamó a Moodle


class TestDescargarCsvChecks:
    def test_descarga_exitosa(self):
        fake = FakeSession(
            respuestas_get={
                "/report/progress/index.php": FakeResponse(
                    content=b"dni,nombre\n123,Ana\n",
                    headers={"Content-Type": "text/csv"},
                ),
            },
        )
        sesion = MoodleSession("usuario", "clave", SETTINGS, session=fake)
        downloader = ReportDownloader(sesion)  # sin iniciar_sesion(): no hace falta para este test

        contenido = downloader.descargar_csv_checks(course_id=440)

        assert contenido == b"dni,nombre\n123,Ana\n"

    def test_sesion_expirada_devuelve_html_y_lanza_download_error(self):
        fake = FakeSession(
            respuestas_get={
                "/report/progress/index.php": FakeResponse(
                    content=b"<!DOCTYPE html><html>login otra vez</html>",
                    headers={"Content-Type": "text/html"},
                ),
            },
        )
        sesion = MoodleSession("usuario", "clave", SETTINGS, session=fake)
        downloader = ReportDownloader(sesion)

        with pytest.raises(DownloadError, match="HTML"):
            downloader.descargar_csv_checks(course_id=440)

    def test_error_http_lanza_download_error(self):
        fake = FakeSession(
            respuestas_get={"/report/progress/index.php": FakeResponse(status_code=500)},
        )
        sesion = MoodleSession("usuario", "clave", SETTINGS, session=fake)
        downloader = ReportDownloader(sesion)

        with pytest.raises(DownloadError, match="500"):
            downloader.descargar_csv_checks(course_id=440)


class TestDescargarExcelNotas:
    def _fake_con_sesskey_ok(self) -> FakeSession:
        html_index = '<input name="itemids[1]" value="1"><script>{"sesskey":"tok999"}</script>'
        return FakeSession(
            respuestas_get={"/grade/export/xls/index.php": FakeResponse(text=html_index)},
            respuestas_post={
                "/grade/export/xls/export.php": FakeResponse(
                    content=b"PK\x03\x04...(bytes de un xlsx real)",
                    headers={"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
                ),
            },
        )

    def test_descarga_exitosa(self):
        fake = self._fake_con_sesskey_ok()
        sesion = MoodleSession("usuario", "clave", SETTINGS, session=fake)
        downloader = ReportDownloader(sesion)

        contenido = downloader.descargar_excel_notas(course_id=440)

        assert contenido.startswith(b"PK")

    def test_curso_inexistente_sin_sesskey_lanza_download_error(self):
        fake = FakeSession(
            respuestas_get={"/grade/export/xls/index.php": FakeResponse(text="<html>curso no encontrado</html>")},
        )
        sesion = MoodleSession("usuario", "clave", SETTINGS, session=fake)
        downloader = ReportDownloader(sesion)

        with pytest.raises(DownloadError, match="Verifica que el ID de curso"):
            downloader.descargar_excel_notas(course_id=999999)

    def test_respuesta_no_es_excel_lanza_download_error(self):
        fake = self._fake_con_sesskey_ok()
        fake._post["/grade/export/xls/export.php"] = FakeResponse(
            content=b"<html>algo salio mal</html>", headers={"Content-Type": "text/html"},
        )
        sesion = MoodleSession("usuario", "clave", SETTINGS, session=fake)
        downloader = ReportDownloader(sesion)

        with pytest.raises(DownloadError, match="No se recibió un archivo Excel"):
            downloader.descargar_excel_notas(course_id=440)
