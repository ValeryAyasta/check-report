from domain.curso import ConfiguracionCurso
from services.reporte_unido import construir_reporte_unido


ALUMNOS_GRUPO_1 = [
    {"nombre": "Ana", "apellidos": "Perez", "dni": "73407925", "asistencia": 20, "tf": 18, "ef": 16},
]
ALUMNOS_GRUPO_2 = [
    {"nombre": "Luis", "apellidos": "Gomez", "dni": "25735600", "asistencia": 13, "tf": 10, "ef": 12},
]


class TestConstruirReporteUnido:
    def test_un_solo_grupo(self, construir_notas_xlsx, construir_checks_csv):
        curso = ConfiguracionCurso(curso_id=1, nombre="X", grupo_c11="111", num_clases=9)
        notas = construir_notas_xlsx(ALUMNOS_GRUPO_1, con_tf=True, con_ef=True)
        checks = construir_checks_csv(ALUMNOS_GRUPO_1, num_clases=9)

        resultado = construir_reporte_unido({"111": (notas, checks)}, curso)

        assert len(resultado.df) == 1
        assert resultado.advertencias == []
        assert resultado.indicadores_av == {"tiene_tf_av": True, "tiene_ef_av": True}

    def test_dos_grupos_se_combinan(self, construir_notas_xlsx, construir_checks_csv):
        curso = ConfiguracionCurso(curso_id=1, nombre="X", grupo_c11="111", grupo_c21="222", num_clases=9)
        archivos = {
            "111": (
                construir_notas_xlsx(ALUMNOS_GRUPO_1, con_tf=True, con_ef=True),
                construir_checks_csv(ALUMNOS_GRUPO_1, num_clases=9),
            ),
            "222": (
                construir_notas_xlsx(ALUMNOS_GRUPO_2, con_tf=True, con_ef=True),
                construir_checks_csv(ALUMNOS_GRUPO_2, num_clases=9),
            ),
        }
        resultado = construir_reporte_unido(archivos, curso)

        assert len(resultado.df) == 2
        assert set(resultado.df["DNI"]) == {"73407925", "25735600"}
        assert resultado.advertencias == []

    def test_alumno_duplicado_entre_grupos_se_reporta(self, construir_notas_xlsx, construir_checks_csv):
        curso = ConfiguracionCurso(curso_id=1, nombre="X", grupo_c11="111", grupo_c21="222", num_clases=9)
        archivos = {
            "111": (
                construir_notas_xlsx(ALUMNOS_GRUPO_1, con_tf=True, con_ef=True),
                construir_checks_csv(ALUMNOS_GRUPO_1, num_clases=9),
            ),
            "222": (
                construir_notas_xlsx(ALUMNOS_GRUPO_1, con_tf=True, con_ef=True),  # mismo alumno
                construir_checks_csv(ALUMNOS_GRUPO_1, num_clases=9),
            ),
        }
        resultado = construir_reporte_unido(archivos, curso)

        assert len(resultado.df) == 1  # se queda con una sola aparición
        assert any("más de un grupo" in a for a in resultado.advertencias)

    def test_indicadores_distintos_entre_grupos_se_reporta(self, construir_notas_xlsx, construir_checks_csv):
        curso = ConfiguracionCurso(curso_id=1, nombre="X", grupo_c11="111", grupo_c21="222", num_clases=9)
        archivos = {
            "111": (
                construir_notas_xlsx(ALUMNOS_GRUPO_1, con_tf=True, con_ef=True),
                construir_checks_csv(ALUMNOS_GRUPO_1, num_clases=9),
            ),
            "222": (
                construir_notas_xlsx(ALUMNOS_GRUPO_2, con_tf=False, con_ef=True),  # sin TF
                construir_checks_csv(ALUMNOS_GRUPO_2, num_clases=9),
            ),
        }
        resultado = construir_reporte_unido(archivos, curso)

        assert any("no coinciden en qué indicadores" in a for a in resultado.advertencias)

    def test_alumno_sin_checks_se_reporta(self, construir_notas_xlsx, construir_checks_csv):
        curso = ConfiguracionCurso(curso_id=1, nombre="X", grupo_c11="111", num_clases=9)
        notas = construir_notas_xlsx(ALUMNOS_GRUPO_1, con_tf=True, con_ef=True)
        checks = construir_checks_csv([], num_clases=9)  # nadie tiene checks

        resultado = construir_reporte_unido({"111": (notas, checks)}, curso)

        assert len(resultado.alumnos_sin_checks) == 1
        assert any("no se encontraron en el reporte de checks" in a for a in resultado.advertencias)

    def test_num_clases_distinto_al_declarado_se_reporta(self, construir_notas_xlsx, construir_checks_csv):
        curso = ConfiguracionCurso(curso_id=1, nombre="X", grupo_c11="111", num_clases=9)  # declara 9
        notas = construir_notas_xlsx(ALUMNOS_GRUPO_1, con_tf=True, con_ef=True)
        checks = construir_checks_csv(ALUMNOS_GRUPO_1, num_clases=8)  # el archivo trae 8

        resultado = construir_reporte_unido({"111": (notas, checks)}, curso)

        assert any("Marcaste 9 clases" in a for a in resultado.advertencias)
