import pytest

from domain.curso import ConfiguracionCurso, ConfiguracionInvalidaError


class TestValidacion:
    def test_curso_valido_minimo(self):
        curso = ConfiguracionCurso(curso_id=440, nombre="Discipulado I", grupo_c11="45094")
        curso.validar()  # no debe lanzar nada
        assert curso.grupos == ["45094"]

    def test_curso_id_invalido(self):
        curso = ConfiguracionCurso(curso_id=0, nombre="X", grupo_c11="45094")
        with pytest.raises(ConfiguracionInvalidaError, match="ID de curso"):
            curso.validar()

    def test_sin_ningun_grupo(self):
        curso = ConfiguracionCurso(curso_id=440, nombre="X", grupo_c11="", grupo_c21="")
        with pytest.raises(ConfiguracionInvalidaError, match="grupo"):
            curso.validar()

    def test_grupo_no_numerico(self):
        curso = ConfiguracionCurso(curso_id=440, nombre="X", grupo_c11="C11")
        with pytest.raises(ConfiguracionInvalidaError, match="válido"):
            curso.validar()

    def test_ambos_grupos_se_incluyen(self):
        curso = ConfiguracionCurso(curso_id=440, nombre="X", grupo_c11="45094", grupo_c21="45071")
        assert curso.grupos == ["45094", "45071"]

    def test_num_clases_fuera_de_rango(self):
        curso = ConfiguracionCurso(curso_id=440, nombre="X", grupo_c11="45094", num_clases=0)
        with pytest.raises(ConfiguracionInvalidaError, match="clases"):
            curso.validar()


class TestPropiedadesDerivadas:
    def test_caso_normal_todo_true(self):
        curso = ConfiguracionCurso(curso_id=1, nombre="X", grupo_c11="1")
        assert curso.tiene_examen_final is True
        assert curso.tiene_trabajo_final is True
        assert curso.trabajo_final_visible_en_av is True

    def test_sin_trabajo_final_implica_no_visible_en_av(self):
        curso = ConfiguracionCurso(curso_id=1, nombre="X", grupo_c11="1", sin_trabajo_final=True)
        assert curso.tiene_trabajo_final is False
        assert curso.trabajo_final_visible_en_av is False

    def test_tf_no_visible_en_av_pero_existe(self):
        curso = ConfiguracionCurso(curso_id=1, nombre="X", grupo_c11="1", trabajo_final_no_visible_en_av=True)
        assert curso.tiene_trabajo_final is True
        assert curso.trabajo_final_visible_en_av is False


class TestDesdeFormulario:
    def test_formulario_minimo(self):
        form = {"curso_id": "440", "grupo_c11": "45094", "grupo_c21": ""}
        curso = ConfiguracionCurso.desde_formulario(form)
        assert curso.curso_id == 440
        assert curso.num_clases == 9  # default
        assert curso.tiene_examen_final is True

    def test_formulario_con_excepciones_marcadas(self):
        form = {
            "curso_id": "440", "grupo_c11": "45094", "grupo_c21": "",
            "num_clases": "8", "sin_examen_final": "on", "sin_trabajo_final": "on",
        }
        curso = ConfiguracionCurso.desde_formulario(form)
        assert curso.num_clases == 8
        assert curso.tiene_examen_final is False
        assert curso.tiene_trabajo_final is False

    def test_curso_id_no_numerico_da_error_claro(self):
        form = {"curso_id": "abc", "grupo_c11": "45094"}
        with pytest.raises(ConfiguracionInvalidaError, match="número"):
            ConfiguracionCurso.desde_formulario(form)
