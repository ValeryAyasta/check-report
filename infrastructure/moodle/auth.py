from __future__ import annotations

import logging
import re
from typing import Optional

import requests
from bs4 import BeautifulSoup

# Re-exportada: el resto del proyecto sigue importando
# `from infrastructure.moodle.auth import LoginError`. La definición
# real vive en domain/excepciones.py junto al resto de la jerarquía.
from domain.excepciones import LoginError
from infrastructure.moodle.settings import MoodleSettings

logger = logging.getLogger(__name__)

__all__ = ["MoodleSession", "LoginError"]


def _valor_atributo(v) -> str:
    """BeautifulSoup a veces devuelve un atributo HTML como lista
    (AttributeValueList) en vez de string, dependiendo del parser y del
    atributo. Como una lista no se puede usar como llave de diccionario
    (el error que viste: "unhashable type"), esto normaliza siempre a
    un string plano, sea cual sea el tipo real que haya devuelto bs4."""
    if isinstance(v, (list, tuple)):
        return v[0] if v else ""
    return str(v) if v is not None else ""


class MoodleSession:
    """Representa una sesión (autenticada o no) contra UN Moodle,
    definido por `settings`. `settings` se recibe por constructor en
    vez de leerse de config.py acá adentro — así se puede armar una
    MoodleSession de test contra una URL falsa sin tocar ningún estado
    global (ver tests/test_moodle_auth.py)."""

    def __init__(
        self,
        usuario: str,
        password: str,
        settings: MoodleSettings,
        session: Optional[requests.Session] = None,
    ):
        self.settings = settings
        self.base_url = settings.base_url
        self.usuario = usuario
        self.password = password
        self._session = session or requests.Session()

    def login(self, timeout: Optional[int] = None) -> requests.Session:
        """Inicia sesión en Moodle. Lanza LoginError si falla.

        `timeout` es opcional: si no se pasa, se usa
        `self.settings.timeout_segundos` (así no hace falta repetir el
        mismo número en cada llamador; solo se pasa explícito cuando
        un caso puntual necesita otro valor)."""
        timeout = timeout if timeout is not None else self.settings.timeout_segundos
        login_url = f"{self.base_url}/login/index.php"

        try:
            logger.info("Iniciando sesión en Moodle...")
            r = self._session.get(login_url, timeout=timeout)
            r.raise_for_status()
        except Exception as e:
            raise LoginError("No se pudo acceder a la página de login de Moodle.") from e

        soup = BeautifulSoup(r.text, "html.parser")
        token_input = soup.find("input", {"name": "logintoken"})
        if not token_input or not token_input.get("value"):
            raise LoginError("No se encontró el token de login en la página de Moodle.")

        payload = {
            "username": self.usuario,
            "password": self.password,
            "logintoken": token_input["value"],
        }

        try:
            resp = self._session.post(login_url, data=payload, timeout=timeout, allow_redirects=True)
            resp.raise_for_status()
        except Exception as e:
            raise LoginError("Ocurrió un error de red durante el login a Moodle.") from e

        if "login/index.php" in resp.url or "incorrect" in resp.text.lower():
            raise LoginError(
                "Usuario o contraseña de Moodle incorrectos (o la sesión fue rechazada)."
            )

        logger.info("Login a Moodle exitoso.")
        return self._session

    def obtener_sesskey(self, course_id: int, group_id: int) -> tuple[str, dict[str, str]]:
        """Obtiene el sesskey y los itemids desde la página de exportación de notas."""
        index_url = f"{self.base_url}/grade/export/xls/index.php?id={course_id}&group={group_id}"
        resp = self._session.get(index_url, timeout=self.settings.timeout_segundos)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        itemids: dict[str, str] = {}
        for checkbox in soup.select('input[name^="itemids["]'):
            name = _valor_atributo(checkbox.get("name"))
            value = _valor_atributo(checkbox.get("value", "1"))
            if name:
                itemids[name] = value

        match = re.search(r'"sesskey":"([A-Za-z0-9]+)"', resp.text)
        if not match:
            raise ValueError(
                f"No se encontró el sesskey en la página de exportación del curso {course_id}. "
                "Verifica que el ID de curso sea correcto."
            )

        sesskey = match.group(1)
        logger.info("sesskey obtenido para curso %s (%d indicadores detectados)", course_id, len(itemids))
        return sesskey, itemids

    @property
    def session(self):
        return self._session