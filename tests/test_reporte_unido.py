import pytest

from domain.curso import ConfiguracionCurso
from services.layout import LayoutMoodleError
from services.reporte_unido import construir_reporte_unido


ALUMNOS_MIXTOS = [
    {"nombre": "Ana", "apellidos": "Perez", "dni": "73407925", "grupo": "C11", "asistencia": 20, "tf": 18, "ef": 16},
    {"nombre": "Luis", "apellidos": "Gomez", "dni": "25735600", "grupo": "C21", "asistencia": 13, "tf": 10, "ef": 12},
    {"nombre": "Marco", "apellidos": "Diaz", "dni": "11111111", "grupo": "A23", "asistencia": 15, "tf": 12, "ef": 14},  # otro grupo, no debe salir
]


class TestConstruirReporteUnido:
    def test_filtra_por_un_solo_grupo(self, construir_notas_xlsx, construir_checks_csv):
        curso = ConfiguracionCurso(curso_id=1, nombre="X", grupos_texto="C11", num_clases=9)
        notas = construir_notas_xlsx(ALUMNOS_MIXTOS, con_tf=True, con_ef=True)
        checks = construir_checks_csv(ALUMNOS_MIXTOS, num_clases=9)

        resultado = construir_reporte_unido(notas, checks, curso)

        assert len(resultado.df) == 1
        assert resultado.df["DNI"].tolist() == ["73407925"]
        assert resultado.advertencias == []

    def test_filtra_por_dos_grupos(self, construir_notas_xlsx, construir_checks_csv):
        curso = ConfiguracionCurso(curso_id=1, nombre="X", grupos_texto="C11, C21", num_clases=9)
        notas = construir_notas_xlsx(ALUMNOS_MIXTOS, con_tf=True, con_ef=True)
        checks = construir_checks_csv(ALUMNOS_MIXTOS, num_clases=9)

        resultado = construir_reporte_unido(notas, checks, curso)

        assert len(resultado.df) == 2
        assert set(resultado.df["DNI"]) == {"73407925", "25735600"}
        assert "11111111" not in set(resultado.df["DNI"])  # el de grupo A23 no debe salir

    def test_filtro_insensible_a_mayusculas_y_espacios(self, construir_notas_xlsx, construir_checks_csv):
        curso = ConfiguracionCurso(curso_id=1, nombre="X", grupos_texto=" c11 ", num_clases=9)
        notas = construir_notas_xlsx(ALUMNOS_MIXTOS, con_tf=True, con_ef=True)
        checks = construir_checks_csv(ALUMNOS_MIXTOS, num_clases=9)

        resultado = construir_reporte_unido(notas, checks, curso)

        assert resultado.df["DNI"].tolist() == ["73407925"]

    def test_grupo_inexistente_da_error_claro(self, construir_notas_xlsx, construir_checks_csv):
        curso = ConfiguracionCurso(curso_id=1, nombre="X", grupos_texto="C99", num_clases=9)
        notas = construir_notas_xlsx(ALUMNOS_MIXTOS, con_tf=True, con_ef=True)
        checks = construir_checks_csv(ALUMNOS_MIXTOS, num_clases=9)

        with pytest.raises(LayoutMoodleError, match="Ningún alumno"):
            construir_reporte_unido(notas, checks, curso)

    def test_alumno_sin_checks_se_reporta(self, construir_notas_xlsx, construir_checks_csv):
        curso = ConfiguracionCurso(curso_id=1, nombre="X", grupos_texto="C11", num_clases=9)
        alumno = [ALUMNOS_MIXTOS[0]]
        notas = construir_notas_xlsx(alumno, con_tf=True, con_ef=True)
        checks = construir_checks_csv([], num_clases=9)  # nadie tiene checks

        resultado = construir_reporte_unido(notas, checks, curso)

        assert len(resultado.alumnos_sin_checks) == 1
        assert any("no se encontraron en el reporte de checks" in a for a in resultado.advertencias)

    def test_num_clases_distinto_al_declarado_se_reporta(self, construir_notas_xlsx, construir_checks_csv):
        curso = ConfiguracionCurso(curso_id=1, nombre="X", grupos_texto="C11", num_clases=9)  # declara 9
        alumno = [ALUMNOS_MIXTOS[0]]
        notas = construir_notas_xlsx(alumno, con_tf=True, con_ef=True)
        checks = construir_checks_csv(alumno, num_clases=8)  # el archivo trae 8

        resultado = construir_reporte_unido(notas, checks, curso)

        assert any("Marcaste 9 clases" in a for a in resultado.advertencias)


class TestRescatarAlumnosDeOtroGrupo:
    def test_rescata_alumno_de_otro_grupo(self, construir_notas_xlsx, construir_checks_csv):
        curso = ConfiguracionCurso(curso_id=1, nombre="X", grupos_texto="C11", num_clases=9)
        notas = construir_notas_xlsx(ALUMNOS_MIXTOS, con_tf=True, con_ef=True)
        checks = construir_checks_csv(ALUMNOS_MIXTOS, num_clases=9)
        resultado = construir_reporte_unido(notas, checks, curso)

        assert len(resultado.df) == 1  # solo Ana (C11)

        # Luis (grupo C21) y Marco (grupo A23) están en el Drive de la tutora
        dnis_tutor = {"73407925", "25735600", "11111111"}
        from services.reporte_unido import rescatar_alumnos_de_otro_grupo
        df_rescatado, textos = rescatar_alumnos_de_otro_grupo(
            resultado.df, resultado.df_todos_los_grupos, dnis_tutor
        )

        assert len(df_rescatado) == 3  # los 3 terminan en el reporte
        assert len(textos) == 2  # Luis y Marco se reportan como rescatados
        assert any("grupo real: C21" in t for t in textos)
        assert any("grupo real: A23" in t for t in textos)

    def test_sin_faltantes_no_cambia_nada(self, construir_notas_xlsx, construir_checks_csv):
        curso = ConfiguracionCurso(curso_id=1, nombre="X", grupos_texto="C11", num_clases=9)
        notas = construir_notas_xlsx(ALUMNOS_MIXTOS, con_tf=True, con_ef=True)
        checks = construir_checks_csv(ALUMNOS_MIXTOS, num_clases=9)
        resultado = construir_reporte_unido(notas, checks, curso)

        from services.reporte_unido import rescatar_alumnos_de_otro_grupo
        df_rescatado, textos = rescatar_alumnos_de_otro_grupo(
            resultado.df, resultado.df_todos_los_grupos, {"73407925"}  # ya está en el filtrado
        )
        assert len(df_rescatado) == 1
        assert textos == []

    def test_dni_que_no_existe_en_ningun_lado_no_rescata_nada(self, construir_notas_xlsx, construir_checks_csv):
        curso = ConfiguracionCurso(curso_id=1, nombre="X", grupos_texto="C11", num_clases=9)
        notas = construir_notas_xlsx(ALUMNOS_MIXTOS, con_tf=True, con_ef=True)
        checks = construir_checks_csv(ALUMNOS_MIXTOS, num_clases=9)
        resultado = construir_reporte_unido(notas, checks, curso)

        from services.reporte_unido import rescatar_alumnos_de_otro_grupo
        df_rescatado, textos = rescatar_alumnos_de_otro_grupo(
            resultado.df, resultado.df_todos_los_grupos, {"99999999"}  # no existe en Moodle
        )
        assert len(df_rescatado) == 1  # sin cambios
        assert textos == []
