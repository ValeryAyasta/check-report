import pandas as pd
import logging

from services.auth import LoginError
from services.downloader import DownloadError, ReportDownloader
from services.utils import normalizar_dni

# ---------- Config / Logging ----------
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

class ProcessingError(Exception):
    pass


class ReporteUnido:
    def __init__(self, downloader: ReportDownloader):
        self.downloader = downloader

    def generar_reporte(self, course: int, grupos: list[int], output_file) -> str:

      try:

        notas_dfs = [self.downloader.descargar_excel_notas(course, g) for g in grupos]
        print("Notas dfs length:", len(notas_dfs))
        df_notas = pd.concat(notas_dfs, ignore_index=True)


        checks_dfs = [self.downloader.descargar_csv_checks(course, g) for g in grupos]
        df_checks = pd.concat(checks_dfs, ignore_index=True)

        cols_to_drop_checks = [0, 1, 4, 6, 8, 10, 12, 14, 16, 18, 20]
        df_checks = df_checks.drop(df_checks.columns[cols_to_drop_checks], axis=1)

        cols_to_drop_notas = [3, 9]

        df_notas = df_notas.drop(df_notas.columns[cols_to_drop_notas], axis=1)

        df_checks.to_excel("checks.xlsx", index=False)

        df_final = pd.concat(
            [df_notas, df_checks],
            axis=1
        )

        df_final = df_final.rename(columns={df_final.columns[2]: "DNI",
                                            df_final.columns[4]: "Equipo - Tutor",
                                            df_final.columns[6]: "EF (AV)",
                                            df_final.columns[5]: "Asistencia AV",
                                            df_final.columns[8]: "Situación"})

        df_final["DNI"] = normalizar_dni(df_final["DNI"])

        df_final.to_excel(output_file, index=False)
        print(f"✅ Reporte unido generado correctamente: {output_file}")

        return output_file

      except PermissionError as e:

          logger.error(f"Error de permisos o sesión expirada: {e}")

          raise PermissionError("No tienes permisos o la sesión expiró.")

      except DownloadError as e:

          logger.error(f"Error descargando CSV: {e}")

          raise DownloadError(f"Error descargando CSV: {e}")

      except Exception as e:

          logger.exception("Error inesperado en main_pipeline.")

          raise RuntimeError(f"Error inesperado en pipeline: {e}")
