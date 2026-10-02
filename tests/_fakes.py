"""
Fakes livianos de requests.Session / Response, para testear
MoodleSession y ReportDownloader SIN hacer ninguna llamada de red real.

Esto es justamente lo que la inyección de dependencias habilita: antes,
`ReportDownloader(usuario, password)` armaba su propia `MoodleSession`
por dentro y esa `MoodleSession` leía `config.MOODLE_BASE_URL` directo
del módulo — no había forma de interceptar nada sin hacer monkeypatch
de config.py o de la librería requests. Ahora se inyecta una
MoodleSession que envuelve uno de estos fakes, y listo.
"""
from __future__ import annotations


class FakeResponse:
    """Sustituto mínimo de requests.Response."""

    def __init__(self, *, status_code: int = 200, text: str = "", content: bytes = b"",
                 url: str = "", headers: dict | None = None):
        self.status_code = status_code
        self.text = text
        self.content = content or text.encode("utf-8")
        self.url = url
        self.headers = headers or {}
        self.ok = 200 <= status_code < 400

    def raise_for_status(self) -> None:
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code} (fake)")


class FakeSession:
    """Sustituto mínimo de requests.Session: en vez de hacer una
    petición real, devuelve una FakeResponse pre-armada según qué
    fragmento de la URL coincida. Guarda cada llamada en `.llamadas`
    para poder verificar qué se pidió (o que no se pidió nada)."""

    def __init__(self, respuestas_get: dict[str, FakeResponse] | None = None,
                 respuestas_post: dict[str, FakeResponse] | None = None):
        self._get = respuestas_get or {}
        self._post = respuestas_post or {}
        self.llamadas: list[tuple[str, str]] = []

    def get(self, url, timeout=None, params=None):
        self.llamadas.append(("GET", url))
        return self._resolver(self._get, url)

    def post(self, url, data=None, timeout=None, headers=None, allow_redirects=True):
        self.llamadas.append(("POST", url))
        return self._resolver(self._post, url)

    @staticmethod
    def _resolver(mapa: dict[str, FakeResponse], url: str) -> FakeResponse:
        for patron, respuesta in mapa.items():
            if patron in url:
                return respuesta
        raise AssertionError(f"FakeSession: no hay respuesta configurada para la URL: {url}")


HTML_LOGIN_OK = '<html><body><form><input type="hidden" name="logintoken" value="tok123"></form></body></html>'
HTML_LOGIN_SIN_TOKEN = "<html><body>Sin formulario de login</body></html>"
