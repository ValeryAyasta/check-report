import pytest

from infrastructure.moodle.auth import MoodleSession, LoginError
from infrastructure.moodle.settings import MoodleSettings
from tests._fakes import FakeSession, FakeResponse, HTML_LOGIN_OK, HTML_LOGIN_SIN_TOKEN

BASE_URL = "https://fake.moodle.test"
SETTINGS = MoodleSettings(base_url=BASE_URL, timeout_segundos=5)


class TestLogin:
    def test_login_exitoso(self):
        fake = FakeSession(
            respuestas_get={"/login/index.php": FakeResponse(text=HTML_LOGIN_OK, url=f"{BASE_URL}/login/index.php")},
            respuestas_post={"/login/index.php": FakeResponse(text="Bienvenida", url=f"{BASE_URL}/my/")},
        )
        sesion = MoodleSession("usuario", "clave", SETTINGS, session=fake)

        resultado = sesion.login()

        assert resultado is fake  # login() no crea una sesión nueva
        assert ("GET", f"{BASE_URL}/login/index.php") in fake.llamadas
        assert ("POST", f"{BASE_URL}/login/index.php") in fake.llamadas

    def test_credenciales_incorrectas_lanza_login_error(self):
        fake = FakeSession(
            respuestas_get={"/login/index.php": FakeResponse(text=HTML_LOGIN_OK, url=f"{BASE_URL}/login/index.php")},
            respuestas_post={"/login/index.php": FakeResponse(
                text="usuario o contraseña incorrect", url=f"{BASE_URL}/login/index.php",
            )},
        )
        sesion = MoodleSession("usuario", "clave-mala", SETTINGS, session=fake)

        with pytest.raises(LoginError, match="incorrectos"):
            sesion.login()

    def test_pagina_de_login_sin_token_lanza_login_error(self):
        fake = FakeSession(
            respuestas_get={"/login/index.php": FakeResponse(text=HTML_LOGIN_SIN_TOKEN, url=f"{BASE_URL}/login/index.php")},
        )
        sesion = MoodleSession("usuario", "clave", SETTINGS, session=fake)

        with pytest.raises(LoginError, match="token"):
            sesion.login()

    def test_error_de_red_en_el_get_inicial_lanza_login_error(self):
        fake = FakeSession(respuestas_get={})  # cualquier URL revienta con AssertionError -> se envuelve en LoginError
        sesion = MoodleSession("usuario", "clave", SETTINGS, session=fake)

        with pytest.raises(LoginError, match="No se pudo acceder"):
            sesion.login()

    def test_usa_el_timeout_de_settings_si_no_se_pasa_uno_explicito(self):
        llamadas_con_timeout = []

        class FakeSessionQueRegistraTimeout(FakeSession):
            def get(self, url, timeout=None, params=None):
                llamadas_con_timeout.append(timeout)
                return super().get(url, timeout=timeout, params=params)

        fake = FakeSessionQueRegistraTimeout(
            respuestas_get={"/login/index.php": FakeResponse(text=HTML_LOGIN_OK, url=f"{BASE_URL}/login/index.php")},
            respuestas_post={"/login/index.php": FakeResponse(text="ok", url=f"{BASE_URL}/my/")},
        )
        sesion = MoodleSession("usuario", "clave", SETTINGS, session=fake)  # SETTINGS.timeout_segundos = 5

        sesion.login()

        assert llamadas_con_timeout == [5]


class TestObtenerSesskey:
    def test_extrae_sesskey_e_itemids(self):
        html = (
            '<html><body>'
            '<input name="itemids[1]" value="1">'
            '<input name="itemids[2]" value="1">'
            '<script>var config = {"sesskey":"abc123XYZ"};</script>'
            '</body></html>'
        )
        fake = FakeSession(
            respuestas_get={"/grade/export/xls/index.php": FakeResponse(text=html)},
        )
        sesion = MoodleSession("usuario", "clave", SETTINGS, session=fake)

        sesskey, itemids = sesion.obtener_sesskey(course_id=440, group_id=0)

        assert sesskey == "abc123XYZ"
        assert itemids == {"itemids[1]": "1", "itemids[2]": "1"}

    def test_sin_sesskey_en_la_pagina_lanza_value_error(self):
        """Este caso NO pasa por LoginError: lo atrapa DownloadError en
        infrastructure/moodle/downloader.py (ver test_moodle_downloader.py),
        porque ocurre después del login, al preparar una descarga puntual."""
        fake = FakeSession(
            respuestas_get={"/grade/export/xls/index.php": FakeResponse(text="<html>sin sesskey</html>")},
        )
        sesion = MoodleSession("usuario", "clave", SETTINGS, session=fake)

        with pytest.raises(ValueError, match="sesskey"):
            sesion.obtener_sesskey(course_id=440, group_id=0)
