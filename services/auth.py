from __future__ import annotations

import re
from typing import Optional, Any
from bs4 import BeautifulSoup
import requests
import logging
from bs4.element import AttributeValueList


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

class LoginError(Exception):
    """Error al iniciar sesión en Moodle."""
    pass

class MoodleSession:

    def __init__(self, usuario: str, password: str, session: Optional[requests.Session] = None):
        self.base_url = "https://escuela.ccaguaviva.org"
        self.usuario = usuario
        self.password = password
        self._session = session or requests.Session()

    def login(self, timeout: int = 10) -> requests.Session:
        login_url = f"{self.base_url}/login/index.php"

        """Inicia sesión en Moodle. Lanza LoginError si falla."""
        try:
            print("Logging in...")
            r = self._session.get(login_url, timeout=timeout)
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
            resp = self._session.post(login_url, data=payload, timeout=timeout, allow_redirects=True)
            resp.raise_for_status()
        except Exception as e:
            logger.exception("Error en el POST de login.")
            raise LoginError("Error durante POST de login.") from e

        # Si aún estamos en la página de login, el login falló
        if "login/index.php" in resp.url or "incorrect" in resp.text.lower():
            raise LoginError("Credenciales inválidas o login fallido.")

        print("✅ Login exitoso.")
        return self._session

    def obtener_sesskey(self, course_id: int, group_id: int) -> tuple[
        str | Any, dict[str | AttributeValueList, str | AttributeValueList | None]]:
        """Obtiene el sesskey desde la página index.php de exportación."""
        index_url = f"{self.base_url}/grade/export/xls/index.php?id={course_id}&group={group_id}"
        resp = self._session.get(index_url)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        itemids = {}
        for checkbox in soup.select('input[name^="itemids["]'):
            name = checkbox["name"]  # ejemplo: itemids[1957]
            value = checkbox.get("value", "1")
            itemids[name] = value

        match = re.search(r'"sesskey":"([A-Za-z0-9]+)"', resp.text)
        if match:
            sesskey = match.group(1)
            print(f"🔑 sesskey obtenido: {sesskey}")
            print(itemids)
            return sesskey, itemids
        else:
            raise ValueError("No se encontró el sesskey en la página.")

    @property
    def session(self):
        return self._session