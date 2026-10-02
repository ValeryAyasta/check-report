"""
Tests de domain/calculo_asistencia.py: reglas de negocio PURAS, sin
openpyxl ni ningún archivo de por medio — a diferencia de los tests en
test_excel_writer.py, que sí necesitan construir un Excel completo
porque prueban la escritura final, estos son simples `assert` sobre
enteros y booleanos.
"""
import pytest

from domain.curso import ConfiguracionCurso
from domain.calculo_asistencia import (
    calcular_nota_asistencia,
    aprobo_por_asistencia,
    a_entero,
    fue_entregado,
    calcular_aprobacion_final,
)


class TestNotaDeAsistencia:
    @pytest.mark.parametrize("asistidas,esperado", [
        (0, 0), (1, 2), (5, 10), (6, 13), (9, 20),
    ])
    def test_tabla_de_9_clases(self, asistidas, esperado):
        curso = ConfiguracionCurso(curso_id=1, nombre="X", grupos_texto="1", num_clases=9)
        assert calcular_nota_asistencia(asistidas, curso) == esperado

    def test_curso_de_8_clases_usa_escala_proporcional(self):
        curso = ConfiguracionCurso(curso_id=1, nombre="X", grupos_texto="1", num_clases=8)
        assert calcular_nota_asistencia(8, curso) == 20  # asistió a todas
        assert calcular_nota_asistencia(0, curso) == 0
        assert calcular_nota_asistencia(4, curso) == 10  # la mitad


class TestAprobacionPorAsistencia:
    def test_debajo_del_minimo_no_aprueba(self):
        assert aprobo_por_asistencia(5) is False

    def test_en_el_minimo_o_por_encima_aprueba(self):
        assert aprobo_por_asistencia(6) is True
        assert aprobo_por_asistencia(9) is True


class TestAEntero:
    @pytest.mark.parametrize("crudo,esperado", [
        (18, 18), ("18", 18), ("18.0", 18), (18.4, 18),
        (None, 0), ("", 0), ("-", 0), ("no es un número", 0),
    ])
    def test_tolera_valores_crudos_de_celda(self, crudo, esperado):
        assert a_entero(crudo) == esperado


class TestFueEntregado:
    @pytest.mark.parametrize("crudo,esperado", [
        (18, True), ("18", True), (0, False), ("0", False),
        (None, False), ("", False), ("-", False),
    ])
    def test_detecta_entrega_real(self, crudo, esperado):
        assert fue_entregado(crudo) == esperado


class TestCalcularAprobacionFinal:
    """Los mismos 5 escenarios que antes se validaban indirectamente
    generando un Excel completo (ver test_excel_writer.py) — acá se
    prueba la regla en sí, de forma aislada."""

    def test_notas_altas_9_clases_aprueba(self):
        aprobo, promedio = calcular_aprobacion_final(
            clases_asistidas=9, notas_a_promediar=[20, 18, 18],
            ef_resuelto=True, tf_entregado=True,
        )
        assert aprobo is True
        assert promedio == pytest.approx((20 + 18 + 18) / 3)

    def test_asiste_5_no_llega_al_minimo_desaprueba(self):
        aprobo, _ = calcular_aprobacion_final(
            clases_asistidas=5, notas_a_promediar=[10, 20, 20],
            ef_resuelto=True, tf_entregado=True,
        )
        assert aprobo is False

    def test_cumple_minimos_pero_promedio_bajo_desaprueba(self):
        aprobo, _ = calcular_aprobacion_final(
            clases_asistidas=6, notas_a_promediar=[13, 5, 5],
            ef_resuelto=True, tf_entregado=True,
        )
        assert aprobo is False

    def test_no_resuelve_examen_desaprueba(self):
        aprobo, _ = calcular_aprobacion_final(
            clases_asistidas=9, notas_a_promediar=[20, 0, 18],
            ef_resuelto=False, tf_entregado=True,
        )
        assert aprobo is False

    def test_promedio_justo_arriba_del_umbral_aprueba(self):
        # asist=13 (tabla 6->13); (13+8+13)/3 = 11.33 >= 10.5
        aprobo, promedio = calcular_aprobacion_final(
            clases_asistidas=6, notas_a_promediar=[13, 8, 13],
            ef_resuelto=True, tf_entregado=True,
        )
        assert aprobo is True
        assert promedio == pytest.approx(11.33, abs=0.01)
