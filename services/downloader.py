import requests
import io
import pandas as pd
from services.auth import logger

BASE_URL = "https://escuela.ccaguaviva.org/report/progress/index.php"

# ---------- Custom Exceptions ----------

class DownloadError(Exception):
    pass

# ---------- Downloader ----------
class ReportDownloader:
    def __init__(self, session: requests.Session):
        self.session = session

    def descargar_csv(self, course: int, group: int, params_extra: dict = None, timeout: int = 30) -> pd.DataFrame:
        params = {
            "course": course,
            "group": group,
            "activityinclude": "all",
            "activityorder": "orderincourse",
            "format": "excelcsv"
        }
        if params_extra:
            params.update(params_extra)

        logger.info(f"Descargando CSV (course={course}, group={group})...")
        resp = self.session.get(BASE_URL, params=params, timeout=timeout)

        if not resp.ok:
            raise DownloadError(f"Fallo HTTP {resp.status_code} al descargar CSV.")

        # Si la respuesta no parece CSV
        content_type = resp.headers.get("Content-Type", "")
        if "text/html" in content_type or resp.text.strip().startswith("<!DOCTYPE html"):
            raise PermissionError(
                "No tienes permisos o la sesión expiró. Moodle devolvió una página HTML en lugar del CSV."
            )

        try:
            df = pd.read_csv(io.StringIO(resp.text), sep="\t", dtype=str)
            return df
        except Exception as e:
            raise DownloadError("Error procesando el CSV recibido.") from e