import pandas as pd
import logging

from services.auth import LoginError
from services.downloader import DownloadError
from services.utils import normalizar_dni

# ---------- Config / Logging ----------
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

class ProcessingError(Exception):
    pass


class ReporteUnido:
    def __init__(self, downloader):
        self.downloader = downloader

    def generar_reporte(self, course: int, grupos: list[int], output_file) -> str:

      try:
        dfs = [self.downloader.descargar_csv(course, g) for g in grupos]
        df = pd.concat(dfs, ignore_index=True)

        cols_to_drop = [4, 6, 8, 10, 12, 14, 16, 18, 20]
        df = df.drop(df.columns[cols_to_drop], axis=1)



        df = df.rename(columns={df.columns[0]: "Nombre",
                                            df.columns[1]: "DNI",
                                            df.columns[2]: "Equipo - Tutor"})

        df["DNI"] = normalizar_dni(df["DNI"])

        df.to_excel(output_file, index=False)
        print("Reporte unido guardado en", output_file)
        return output_file


      except LoginError as e:

          logger.error(f"Error de autenticación: {e}")

          raise LoginError("Credenciales incorrectas o error en el login.")

      except PermissionError as e:

          logger.error(f"Error de permisos o sesión expirada: {e}")

          raise PermissionError("No tienes permisos o la sesión expiró.")

      except DownloadError as e:

          logger.error(f"Error descargando CSV: {e}")

          raise DownloadError(f"Error descargando CSV: {e}")

      except Exception as e:

          logger.exception("Error inesperado en main_pipeline.")

          raise RuntimeError(f"Error inesperado en pipeline: {e}")
