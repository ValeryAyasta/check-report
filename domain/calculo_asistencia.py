"""
Reglas de negocio PURAS sobre asistencia y aprobación de un alumno.

Estas funciones NO dependen de openpyxl, pandas, ni de ningún formato
de archivo concreto — reciben y devuelven tipos simples (int, bool,
float). Antes vivían mezcladas, en services/calculator.py, con el
código que lee y escribe celdas de Excel; eso obligaba a cualquier
test de "¿aprobó o no?" a construir un Workbook completo de por medio
para poder ejercitar la regla. Separadas acá, se testean con simples
`assert calcular_nota_asistencia(7, curso) == 16`.

La escritura en el Excel final (infrastructure/excel/excel_writer.py)
llama a estas funciones y solo se encarga de VOLCAR el resultado en
la celda correcta con el color correcto — no decide nada de negocio
por su cuenta.
"""
from __future__ import annotations

import config
from domain.curso import ConfiguracionCurso


def calcular_nota_asistencia(clases_asistidas: int, curso: ConfiguracionCurso) -> int:
    """Nota de asistencia (0-20) según cuántas clases asistió el alumno.

    Para cursos de 9 clases (el caso normal) se usa la tabla exacta que
    ya se usaba antes, para no cambiar la nota de cursos existentes.
    Para cualquier otro número de clases, se recalcula de forma
    proporcional.
    """
    if curso.num_clases == 9:
        return config.TABLA_NOTA_ASISTENCIA_9_CLASES.get(clases_asistidas, 0)
    nota = round((clases_asistidas / curso.num_clases) * config.NOTA_MAXIMA_ASISTENCIA)
    return max(0, min(config.NOTA_MAXIMA_ASISTENCIA, nota))


def aprobo_por_asistencia(clases_asistidas: int) -> bool:
    """Mínimo de clases asistidas para aprobar por asistencia. Es un
    número FIJO (no proporcional al número de clases del curso): un
    curso de 8 clases exige el mismo mínimo que uno de 9."""
    return clases_asistidas >= config.NUM_CLASES_MINIMAS_PARA_APROBAR


def a_entero(valor) -> int:
    """Convierte el valor crudo de una celda (str, float, None, "-"...)
    a un entero, tolerando basura: cualquier cosa no convertible da 0."""
    try:
        return round(float(str(valor).strip()))
    except (TypeError, ValueError):
        return 0


def fue_entregado(valor_crudo) -> bool:
    """True si el valor representa una entrega/nota real: no vacío, no
    un placeholder tipo '-', y distinto de cero."""
    if valor_crudo in (None, "", "-"):
        return False
    return a_entero(valor_crudo) != 0


def calcular_aprobacion_final(
    *,
    clases_asistidas: int,
    notas_a_promediar: list[int],
    ef_resuelto: bool,
    tf_entregado: bool,
) -> tuple[bool, float]:
    """Determina si el alumno aprueba el curso completo.

    Condiciones (TODAS deben cumplirse):
      1) mínimo de clases asistidas (aprobo_por_asistencia),
      2) resolvió el examen final, si el curso lo tiene,
      3) entregó el trabajo final, si el curso lo tiene,
      4) el promedio de `notas_a_promediar` (asistencia + EF/TF que
         apliquen) es mayor o igual al umbral configurado.

    `notas_a_promediar` ya viene armada por quien llama (típicamente
    [nota_asistencia] + [ef] si aplica + [tf] si aplica), porque decidir
    qué notas entran al promedio depende de qué indicadores tiene el
    curso — esa decisión es del llamador (application/infrastructure),
    no de esta función.

    Devuelve (aprobo, promedio) — se devuelve también el promedio para
    poder mostrarlo o loguearlo si hace falta, sin tener que
    recalcularlo aparte.
    """
    promedio = sum(notas_a_promediar) / len(notas_a_promediar)
    aprobo = (
        aprobo_por_asistencia(clases_asistidas)
        and ef_resuelto
        and tf_entregado
        and promedio >= config.PROMEDIO_MINIMO_PARA_APROBAR
    )
    return aprobo, promedio
