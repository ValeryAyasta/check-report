import pytest

from infrastructure.moodle.settings import MoodleSettings


class TestMoodleSettings:
    def test_se_puede_construir_directo_sin_tocar_config(self):
        """Este es el punto central de la inyección: para testear con
        una URL/timeout distintos no hace falta monkeypatchear
        config.py, se pasa por constructor."""
        settings = MoodleSettings(base_url="https://fake.moodle.test", timeout_segundos=5)
        assert settings.base_url == "https://fake.moodle.test"
        assert settings.timeout_segundos == 5

    def test_timeout_tiene_default_razonable(self):
        settings = MoodleSettings(base_url="https://fake.moodle.test")
        assert settings.timeout_segundos == 30

    def test_es_inmutable(self):
        settings = MoodleSettings(base_url="https://fake.moodle.test")
        with pytest.raises(Exception):
            settings.base_url = "https://otro.test"  # type: ignore[misc]

    def test_desde_config_lee_config_py(self):
        import config
        settings = MoodleSettings.desde_config()
        assert settings.base_url == config.MOODLE_BASE_URL
        assert settings.timeout_segundos == config.REQUEST_TIMEOUT_SEGUNDOS
