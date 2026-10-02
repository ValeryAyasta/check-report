"""
MoodleSettings agrupa la configuración de CONEXIÓN a Moodle (URL base,
timeout) en un objeto inyectable, en vez de que MoodleSession y
ReportDownloader lean `config.MOODLE_BASE_URL` / `config.REQUEST_TIMEOUT_SEGUNDOS`
directamente como variables globales del módulo config.

Por qué importa (no es solo estilo):
- Sin esto, para testear MoodleSession contra un servidor Moodle falso
  (o contra un stub) había que hacer monkeypatch de `config.MOODLE_BASE_URL`
  a nivel de módulo — un estado global compartido entre tests, frágil
  si dos tests corren en paralelo o si uno se olvida de restaurarlo.
- Con MoodleSettings, se pasa por CONSTRUCTOR: cada test arma su propia
  instancia, sin tocar nada global (ver tests/test_moodle_auth.py).
- El resto de config.py (colores, tabla de notas, layout de columnas)
  se queda tal cual, como constantes de negocio verdaderas: no hace
  falta inyectar TODO, solo lo que de verdad puede necesitar variar
  entre un test y una corrida real (o, a futuro, entre un cliente de
  Moodle y otro).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MoodleSettings:
    base_url: str
    timeout_segundos: int = 30

    @classmethod
    def desde_config(cls) -> "MoodleSettings":
        """Construye la configuración real de la aplicación, leyendo
        config.py. Es el ÚNICO lugar del proyecto que debe llamar a
        esto en código de producción (en application/pipeline.py, que
        es quien arma los colaboradores reales) — el resto del
        proyecto recibe MoodleSettings ya armado, por parámetro."""
        import config
        return cls(
            base_url=config.MOODLE_BASE_URL,
            timeout_segundos=config.REQUEST_TIMEOUT_SEGUNDOS,
        )
