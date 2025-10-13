import pandas as pd
from pathlib import Path

from services.utils import normalizar_dni


class MergePadron:
    def __init__(self, padron_file: Path):
        self.padron_file = padron_file

    def merge(self, reporte_file: str, output_file) -> str:
        df = pd.read_excel(reporte_file, dtype=str)
        df_tutores = pd.read_excel(self.padron_file, skiprows=4, header=None, dtype=str)

        df_tutores = df_tutores[[0, 3, 5]].rename(columns={0: "DNI", 3: "ALUMNO(A)", 5: "Equipo"})
        df = df.rename(columns={df.columns[0]: "Nombre", df.columns[1]: "DNI", df.columns[2]: "Equipo - Tutor"})

        df_tutores["DNI"] = normalizar_dni(df_tutores["DNI"])

        df = df.merge(df_tutores[["DNI", "Equipo"]], on="DNI", how="left")
        df = df.merge(df_tutores[["DNI", "ALUMNO(A)"]], on="DNI", how="left")

        df["Equipo - Tutor"] = df["Equipo"]
        df["Nombre"] = df["ALUMNO(A)"]
        df = df.drop(columns=["Equipo", "ALUMNO(A)"])

        df.to_excel(output_file, index=False)
        return output_file
