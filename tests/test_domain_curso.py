import pytest

from domain.curso import ConfiguracionCurso, ConfiguracionInvalidaError


class TestValidacion:
    def test_curso_valido_minimo(self):
        curso = ConfiguracionCurso(curso_id=440, nombre="Discipulado I", grupos_texto="C11")
        curso.validar()  # no debe lanzar nada
        assert curso.grupos == ["C11"]

    def test_curso_id_invalido(self):
        curso = ConfiguracionCurso(curso_id=0, nombre="X", grupos_texto="C11")
        with pytest.raises(ConfiguracionInvalidaError, match="ID de curso"):
            curso.validar()

    def test_sin_ningun_grupo(self):
        curso = ConfiguracionCurso(curso_id=440, nombre="X", grupos_texto="")
        with pytest.raises(ConfiguracionInvalidaError, match="grupo"):
            curso.validar()

    def test_grupo_se_normaliza_a_mayusculas_sin_espacios(self):
        curso = ConfiguracionCurso(curso_id=440, nombre="X", grupos_texto=" c11 ")
        assert curso.grupos == ["C11"]

    def test_num_clases_fuera_de_rango(self):
        curso = ConfiguracionCurso(curso_id=440, nombre="X", grupos_texto="C11", num_clases=0)
        with pytest.raises(ConfiguracionInvalidaError, match="clases"):
            curso.validar()


class TestParseoDeGrupos:
    @pytest.mark.parametrize("texto,esperado", [
        ("C11, C21", ["C11", "C21"]),
        ("c11,c21", ["C11", "C21"]),
        ("C11 C21", ["C11", "C21"]),  # separado por espacio también funciona
        ("C11;C21", ["C11", "C21"]),  # separado por punto y coma también
        ("  C11  ,  C21  ", ["C11", "C21"]),  # espacios de más
        ("C11", ["C11"]),  # uno solo
        ("C11, C11, C21", ["C11", "C21"]),  # duplicados se eliminan
        ("", []),
    ])
    def test_variantes_de_separador(self, texto, esperado):
        curso = ConfiguracionCurso(curso_id=1, nombre="X", grupos_texto=texto)
        assert curso.grupos == esperado


class TestPropiedadesDerivadas:
    def test_caso_normal_todo_true(self):
        curso = ConfiguracionCurso(curso_id=1, nombre="X", grupos_texto="C11")
        assert curso.tiene_examen_final is True
        assert curso.tiene_trabajo_final is True
        assert curso.trabajo_final_visible_en_av is True

    def test_sin_trabajo_final_implica_no_visible_en_av(self):
        curso = ConfiguracionCurso(curso_id=1, nombre="X", grupos_texto="C11", sin_trabajo_final=True)
        assert curso.tiene_trabajo_final is False
        assert curso.trabajo_final_visible_en_av is False

    def test_tf_no_visible_en_av_pero_existe(self):
        curso = ConfiguracionCurso(curso_id=1, nombre="X", grupos_texto="C11", trabajo_final_no_visible_en_av=True)
        assert curso.tiene_trabajo_final is True
        assert curso.trabajo_final_visible_en_av is False


class TestDesdeFormulario:
    def test_formulario_minimo(self):
        form = {"curso_id": "440", "grupos": "C11, C21"}
        curso = ConfiguracionCurso.desde_formulario(form)
        assert curso.curso_id == 440
        assert curso.grupos == ["C11", "C21"]
        assert curso.num_clases == 9  # default
        assert curso.tiene_examen_final is True

    def test_formulario_con_excepciones_marcadas(self):
        form = {
            "curso_id": "440", "grupos": "C11",
            "num_clases": "8", "sin_examen_final": "on", "sin_trabajo_final": "on",
        }
        curso = ConfiguracionCurso.desde_formulario(form)
        assert curso.num_clases == 8
        assert curso.tiene_examen_final is False
        assert curso.tiene_trabajo_final is False

    def test_curso_id_no_numerico_da_error_claro(self):
        form = {"curso_id": "abc", "grupos": "C11"}
        with pytest.raises(ConfiguracionInvalidaError, match="número"):
            ConfiguracionCurso.desde_formulario(form)
