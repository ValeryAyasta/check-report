import requests
import io
import pandas as pd
from services.auth import logger, MoodleSession

# ---------- Custom Exceptions ----------

class DownloadError(Exception):
    pass

# ---------- Downloader ----------
class ReportDownloader:
    def __init__(self, usuario: str, password: str):
        self.moodle_session = MoodleSession(usuario, password)
        self.session = self.moodle_session.login();

    def descargar_csv_checks(self, course: int, group: int, params_extra: dict = None, timeout: int = 30) -> pd.DataFrame:
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
        export_url = f"{self.moodle_session.base_url}/report/progress/index.php"
        resp = self.session.get(export_url, params=params, timeout=timeout)

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


    def descargar_excel_notas(self, course_id: int, group_id: int, output_path: str = "calificaciones.xlsx"):
        (sesskey, itemids) = self.moodle_session.obtener_sesskey(course_id, group_id)
        export_url = f"{self.moodle_session.base_url}/grade/export/xls/export.php"

        payload = [
            ("mform_isexpanded_id_gradeitems", "1"),
            ("checkbox_controller1", "1"),
            ("mform_isexpanded_id_options", "1"),
            ("export_onlyactive", "1"),
            ("id", str(course_id)),
            ("group", str(group_id)),  # 🔥 IMPORTANTE
            ("sesskey", sesskey),
            ("_qf__grade_export_form", "1"),  # 🔥 NOMBRE EXACTO
        ]

        # 🔥 display[real] DEBE IR DOS VECES
        payload += [
            ("display[real]", "0"),
            ("display[real]", "1"),
            ("display[percentage]", "0"),
            ("display[letter]", "0"),
        ]

        payload += [
            ("export_feedback", "0"),
            ("decimals", "0"),
            ("submitbutton", "Descargar"),
        ]

        # 🔥 itemids
        for key, value in itemids.items():
            payload.append((key, value))

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": f"{self.moodle_session.base_url}/grade/export/xls/index.php?id={course_id}&group={group_id}",
        }

        print("📤 Enviando solicitud de exportación...")
        resp = self.session.post(export_url, data=payload, headers=headers)
        resp.raise_for_status()

        # Moodle devuelve el archivo Excel directamente
        if "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" not in resp.headers.get("Content-Type", ""):
            print(resp.headers.get("Content-Type", ""))
            raise ValueError("No se recibió un archivo Excel. Puede que haya ocurrido un error en la exportación.")

        # 🔥 AQUÍ ESTÁ LA CLAVE
        excel_buffer = io.BytesIO(resp.content)
        df_notas = pd.read_excel(excel_buffer, dtype=str)
        return df_notas

