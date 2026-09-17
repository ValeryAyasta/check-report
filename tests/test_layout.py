import io
import pandas as pd
import pytest

from services import layout


ALUMNOS_BASE = [
    {"nombre": "Ana", "apellidos": "Perez", "dni": "73407925", "grupo": "C11", "asistencia": 20, "tf": 18, "ef": 16},
    {"nombre": "Luis", "apellidos": "Gomez", "dni": "25735600", "grupo": "C21", "asistencia": 13, "tf": 10, "ef": 12},
]


class TestAplicarLayoutNotas:
    def test_detecta_tf_y_ef_cuando_existen(self, construir_notas_xlsx):
        contenido = construir_notas_xlsx(ALUMNOS_BASE, con_tf=True, con_ef=True)
        df = pd.read_excel(io.BytesIO(contenido))
        resultado, indicadores = layout.aplicar_layout_notas(df)

        assert indicadores == {"tiene_tf_av": True, "tiene_ef_av": True}
        assert set(resultado.columns) >= {"Nombre", "Apellidos", "DNI", "Grupo", "Asistencia AV", "TF (AV)", "EF (AV)"}
        assert len(resultado) == 2

    def test_detecta_ausencia_de_tf(self, construir_notas_xlsx):
        """Este es el bug original: un curso sin TF no debe romper ni
        desalinear columnas, y debe detectarse automáticamente."""
        contenido = construir_notas_xlsx(ALUMNOS_BASE, con_tf=False, con_ef=True)
        df = pd.read_excel(io.BytesIO(contenido))
        resultado, indicadores = layout.aplicar_layout_notas(df)

        assert indicadores == {"tiene_tf_av": False, "tiene_ef_av": True}
        assert "TF (AV)" not in resultado.columns
        assert "EF (AV)" in resultado.columns
        # Las columnas que sí deben estar siempre presentes:
        assert list(resultado["Asistencia AV"]) == [20, 13]

    def test_detecta_ausencia_de_ef(self, construir_notas_xlsx):
        contenido = construir_notas_xlsx(ALUMNOS_BASE, con_tf=True, con_ef=False)
        df = pd.read_excel(io.BytesIO(contenido))
        resultado, indicadores = layout.aplicar_layout_notas(df)

        assert indicadores == {"tiene_tf_av": True, "tiene_ef_av": False}
        assert "EF (AV)" not in resultado.columns

    def test_normaliza_dni_con_cero_a_la_izquierda(self, construir_notas_xlsx):
        alumnos = [{"nombre": "Beto", "apellidos": "Ruiz", "dni": "07144588", "asistencia": 20}]
        contenido = construir_notas_xlsx(alumnos, con_tf=False, con_ef=False)
        df = pd.read_excel(io.BytesIO(contenido))
        resultado, _ = layout.aplicar_layout_notas(df)

        # Moodle exporta el DNI como número, así que pandas lo lee sin el
        # cero (7144588). aplicar_layout_notas normaliza quitando CUALQUIER
        # cero a la izquierda de ambos lados para poder cruzar (no rellena
        # a 8 dígitos, porque un carnet de extranjería no tiene ese largo
        # fijo) — el cero se recupera después, en calculator.py, a partir
        # del archivo de la tutora (que sí lo guarda como texto).
        assert resultado["DNI"].tolist() == ["7144588"]

    def test_columna_obligatoria_faltante_da_error_claro(self, construir_notas_xlsx):
        contenido = construir_notas_xlsx(ALUMNOS_BASE, con_tf=False, con_ef=False)
        df = pd.read_excel(io.BytesIO(contenido))
        df = df.rename(columns={"Nombre de usuario": "Otra cosa"})

        with pytest.raises(layout.LayoutMoodleError, match="dni"):
            layout.aplicar_layout_notas(df)


class TestLeerChecks:
    def test_detecta_columnas_de_clase(self, construir_checks_csv):
        contenido = construir_checks_csv(ALUMNOS_BASE, num_clases=9)
        resultado = layout.leer_checks(contenido)

        columnas_clase = [c for c in resultado.columns if c != "DNI"]
        assert len(columnas_clase) == 9
        assert "DNI" in resultado.columns
        assert len(resultado) == 2

    def test_soporta_distinto_numero_de_clases(self, construir_checks_csv):
        contenido = construir_checks_csv(ALUMNOS_BASE, num_clases=8)
        resultado = layout.leer_checks(contenido)

        columnas_clase = [c for c in resultado.columns if c != "DNI"]
        assert len(columnas_clase) == 8

    def test_normaliza_dni_en_checks(self, construir_checks_csv):
        alumnos = [{"nombre": "Beto", "apellidos": "Ruiz", "dni": "07144588"}]
        contenido = construir_checks_csv(alumnos, num_clases=9)
        resultado = layout.leer_checks(contenido)

        assert resultado["DNI"].tolist() == ["7144588"]  # ver nota arriba sobre normalización
