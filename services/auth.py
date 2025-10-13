from typing import Optional
from bs4 import BeautifulSoup
import requests
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

class LoginError(Exception):
    """Error al iniciar sesión en Moodle."""
    pass

class MoodleSession:
    LOGIN_URL = "https://escuela.ccaguaviva.org/login/index.php"

    def __init__(self, usuario: str, password: str, session: Optional[requests.Session] = None):
        self.usuario = usuario
        self.password = password
        self._session = session or requests.Session()

    def login(self, timeout: int = 10) -> requests.Session:
        """Inicia sesión en Moodle. Lanza LoginError si falla."""
        try:
            print("Logging in...")
            r = self._session.get(self.LOGIN_URL, timeout=timeout)
            r.raise_for_status()
        except Exception as e:
            logger.exception("No se pudo acceder a la página de login.")
            raise LoginError("No se pudo acceder a la página de login.") from e

        soup = BeautifulSoup(r.text, "html.parser")
        token_input = soup.find("input", {"name": "logintoken"})
        if not token_input or not token_input.get("value"):
            raise LoginError("No se encontró logintoken en la página de login.")

        logintoken = token_input["value"]
        payload = {
            "username": self.usuario,
            "password": self.password,
            "logintoken": logintoken
        }

        try:
            resp = self._session.post(self.LOGIN_URL, data=payload, timeout=timeout, allow_redirects=True)
            resp.raise_for_status()
        except Exception as e:
            logger.exception("Error en el POST de login.")
            raise LoginError("Error durante POST de login.") from e

        # Si aún estamos en la página de login, el login falló
        if "login/index.php" in resp.url or "incorrect" in resp.text.lower():
            raise LoginError("Credenciales inválidas o login fallido.")

        print("✅ Login exitoso.")
        return self._session
