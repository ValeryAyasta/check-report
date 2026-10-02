"""
Tests de las medidas de seguridad de app.py:
  - CSRF: el token generado en GET / es obligatorio en POST /generar-reporte
  - Cabeceras de seguridad en toda respuesta
  - Sanitización de nombres de archivo subidos (path traversal)
  - Rate limiting del endpoint que hace login real a Moodle

No se prueba acá el pipeline completo (login/descarga/generación real
del Excel) — eso ya lo cubren los tests de application/ e
infrastructure/. Estos tests solo verifican que la CAPA DE SEGURIDAD
deje pasar o bloquee lo que corresponde, antes de que el pipeline
entre en juego.
"""
import re

import pytest

import app as app_module


@pytest.fixture(autouse=True)
def _rate_limiter_limpio():
    """El estado del rate limiter propio (ver app.py, sin flask-limiter
    porque en el entorno de despliegue real pip no tiene acceso a
    PyPI) vive en un dict en memoria del proceso, compartido por TODOS
    los tests que corran en este proceso — sin este reset entre tests,
    un test podría fallar (o pasar de casualidad) según qué otros
    tests corrieron antes que él en la misma sesión de pytest."""
    app_module._reiniciar_rate_limiter_para_tests()
    yield
    app_module._reiniciar_rate_limiter_para_tests()


def _obtener_token_csrf(client) -> str:
    resp = client.get("/")
    match = re.search(r'name="csrf_token" value="([a-f0-9]+)"', resp.get_data(as_text=True))
    assert match, "No se encontró el input hidden de csrf_token en el HTML de index.html"
    return match.group(1)


class TestCSRF:
    def test_sin_token_se_rechaza(self):
        with app_module.app.test_client() as client:
            client.get("/")  # arranca la sesión (y genera un token válido, que acá no se usa)
            resp = client.post("/generar-reporte", data={"usuario": "u", "password": "p"})
            assert resp.status_code == 400
            assert resp.get_json()["codigo"] == "CSRF_INVALIDO"

    def test_token_incorrecto_se_rechaza(self):
        with app_module.app.test_client() as client:
            client.get("/")
            resp = client.post("/generar-reporte", data={
                "usuario": "u", "password": "p", "csrf_token": "token-inventado-por-un-atacante",
            })
            assert resp.status_code == 400
            assert resp.get_json()["codigo"] == "CSRF_INVALIDO"

    def test_token_correcto_pasa_la_validacion_csrf(self):
        """No se ejercita el flujo completo (requeriría red real a
        Moodle): alcanza con confirmar que YA NO se rechaza por CSRF,
        sino por el siguiente paso de validación (usuario/password
        vacíos, en este caso) — es decir, que el error cambió de
        'CSRF_INVALIDO' a otra cosa."""
        with app_module.app.test_client() as client:
            token = _obtener_token_csrf(client)
            resp = client.post("/generar-reporte", data={"csrf_token": token})
            assert resp.status_code == 400
            assert resp.get_json().get("codigo") != "CSRF_INVALIDO"

    def test_sin_haber_pasado_por_index_ningun_token_es_valido(self):
        """Un cliente que nunca hizo GET / (por ejemplo, un bot que
        ataca el endpoint directo) no tiene sesión, así que no hay
        ningún token contra el cual comparar."""
        with app_module.app.test_client() as client:
            resp = client.post("/generar-reporte", data={
                "usuario": "u", "password": "p", "csrf_token": "cualquiera",
            })
            assert resp.status_code == 400
            assert resp.get_json()["codigo"] == "CSRF_INVALIDO"


class TestCabecerasDeSeguridad:
    def test_presentes_en_toda_respuesta(self):
        with app_module.app.test_client() as client:
            resp = client.get("/")
            assert resp.headers["X-Content-Type-Options"] == "nosniff"
            assert resp.headers["X-Frame-Options"] == "DENY"
            assert resp.headers["Referrer-Policy"] == "no-referrer"

    def test_hsts_solo_si_la_request_llego_por_https(self):
        with app_module.app.test_client() as client:
            resp_http = client.get("/")
            assert "Strict-Transport-Security" not in resp_http.headers

            resp_https = client.get("/", base_url="https://localhost")
            assert "Strict-Transport-Security" in resp_https.headers


class TestNombreArchivoSeguro:
    @pytest.mark.parametrize("original,esperado", [
        # Nombres reales y válidos: se preservan tal cual, acentos y ñ incluidos.
        ("María_Núñez - C11.xlsx", "María_Núñez - C11.xlsx"),
        ("Equipo1-José Peña.xlsx", "Equipo1-José Peña.xlsx"),
        # Intentos de path traversal: el componente de ruta se descarta.
        ("../../etc/passwd.xlsx", "passwd.xlsx"),
        ("/etc/passwd", "passwd"),
        ("....//....//etc/passwd", "passwd"),
        ("a/../../b.xlsx", "b.xlsx"),
        # Nombre exactamente "." o "..": no queda ambigüedad posible.
        ("..", "archivo.xlsx"),
        (".", "archivo.xlsx"),
        ("", "archivo.xlsx"),
        # Byte nulo (null byte injection): se elimina.
        ("archivo\x00malicioso.xlsx", "archivomalicioso.xlsx"),
        # Espacios sobrantes al inicio/fin: se recortan.
        ("  archivo.xlsx  ", "archivo.xlsx"),
        # Caracteres especiales sueltos: se neutralizan a "_", sin romper el nombre.
        ("Reporte (final) - Tutora #2.xlsx", "Reporte _final_ - Tutora _2.xlsx"),
    ])
    def test_sanitiza(self, original, esperado):
        assert app_module._nombre_archivo_seguro(original) == esperado

    def test_nunca_permite_escapar_del_directorio_destino(self, tmp_path):
        """Prueba de extremo a extremo de la defensa en profundidad:
        para CUALQUIER nombre de archivo (por más agresivo que sea el
        intento de path traversal), el archivo sanitizado siempre debe
        quedar DENTRO del directorio de destino."""
        tutores_dir = tmp_path / "tutores"
        tutores_dir.mkdir()
        intentos = [
            "../fuera.xlsx", "../../fuera.xlsx", "/etc/passwd",
            "....//....//etc/passwd", "..", ".", "", "a/../../b.xlsx",
            "..\\..\\windows\\system32\\archivo.xlsx",
        ]
        for intento in intentos:
            nombre = app_module._nombre_archivo_seguro(intento)
            destino = (tutores_dir / nombre).resolve()
            assert tutores_dir.resolve() in destino.parents, (
                f"{intento!r} se sanitizó como {nombre!r}, que escapa de {tutores_dir}"
            )


class TestRateLimiting:
    def test_bloquea_despues_del_limite_configurado(self):
        """El límite es "6 per minute" (ver app.py). Se mandan más
        pedidos que eso y se confirma que en algún punto Flask-Limiter
        responde 429, no que el pipeline se ejecute 8 veces de verdad
        (las requests fallan antes, por validación normal — lo que se
        está probando es que el LIMITADOR corta, no la lógica de
        negocio)."""
        with app_module.app.test_client() as client:
            token = _obtener_token_csrf(client)
            respuestas = [
                client.post("/generar-reporte", data={"csrf_token": token})
                for _ in range(8)
            ]
            codigos = [r.status_code for r in respuestas]
            assert codigos[0] == 400  # antes del límite: validación normal
            assert 429 in codigos, f"El rate limit nunca se activó: {codigos}"

            respuesta_bloqueada = next(r for r in respuestas if r.status_code == 429)
            assert respuesta_bloqueada.get_json()["codigo"] == "LIMITE_DE_INTENTOS"
