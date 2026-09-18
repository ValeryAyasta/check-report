"""
Modelo de dominio: configuración de un curso de Discipulado.

Antes, todo el comportamiento condicional (número de clases, si hay TF,
si hay examen, etc.) estaba implícito o hardcodeado en distintos archivos.
Ahora vive en un solo lugar: ConfiguracionCurso. El resto del pipeline
recibe este objeto y actúa en base a sus atributos, en vez de asumir
una estructura fija.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


class ConfiguracionInvalidaError(Exception):
    """La tutora ingresó datos incompletos o inconsistentes en el formulario."""
    pass


# Separa por comas, punto y coma, o cualquier espacio en blanco — así
# "C11, C21", "C11 C21" y "c11,c21" funcionan todos igual.
_SEPARADOR_GRUPOS = re.compile(r"[,;\s]+")


@dataclass
class ConfiguracionCurso:
    curso_id: int
    nombre: str

    # Códigos de grupo tal como los escribe la tutora en un solo campo,
    # separados por coma/espacio (ej. "C11, C21"). Se parsean con la
    # propiedad `grupos` más abajo — nunca se usa este campo crudo
    # directamente en el resto del código.
    grupos_texto: str = ""

    # ---- Particularidades del curso (excepciones a lo "normal") ----
    # Lo normal es: 9 clases, con examen, y con trabajo final visible en
    # el Aula Virtual. Estos flags representan EXCEPCIONES para que el
    # valor por defecto (todo en False/9) sea siempre el caso más común,
    # y la tutora solo marque lo distinto.
    #
    # Los devocionales / % de devocionales NO tienen flag: se calculan
    # siempre, para todo curso, sin excepción.
    num_clases: int = 9
    sin_examen_final: bool = False
    sin_trabajo_final: bool = False
    trabajo_final_no_visible_en_av: bool = False

    # ---- Propiedades derivadas (para que el resto del código no
    # tenga que negar flags constantemente) ----
    @property
    def tiene_examen_final(self) -> bool:
        return not self.sin_examen_final

    @property
    def tiene_trabajo_final(self) -> bool:
        return not self.sin_trabajo_final

    @property
    def trabajo_final_visible_en_av(self) -> bool:
        # Si el curso no tiene TF, tampoco puede estar "visible en AV".
        return self.tiene_trabajo_final and not self.trabajo_final_no_visible_en_av

    @property
    def grupos(self) -> list[str]:
        """Códigos de grupo (C11 / C21) a filtrar, parseados de
        `grupos_texto`, en MAYÚSCULAS, sin duplicados y en el orden en
        que se escribieron. La comparación contra la columna "Grupo"
        del Excel también normaliza a mayúsculas, así que no importa
        cómo la tutora los haya escrito."""
        partes = _SEPARADOR_GRUPOS.split(self.grupos_texto.strip())
        vistos: list[str] = []
        for p in partes:
            p = p.strip().upper()
            if p and p not in vistos:
                vistos.append(p)
        return vistos

    def validar(self) -> None:
        if self.curso_id <= 0:
            raise ConfiguracionInvalidaError("El ID de curso debe ser un número positivo.")
        if not self.grupos:
            raise ConfiguracionInvalidaError(
                "Debes ingresar al menos un código de grupo (ej: C11, C21)."
            )
        if self.num_clases <= 0 or self.num_clases > 20:
            raise ConfiguracionInvalidaError(
                "El número de clases debe ser un valor razonable (entre 1 y 20)."
            )

    @classmethod
    def desde_formulario(cls, form) -> "ConfiguracionCurso":
        """Construye la configuración a partir de request.form (Flask)."""
        try:
            curso_id = int(form["curso_id"])
        except (KeyError, ValueError):
            raise ConfiguracionInvalidaError("El ID de curso debe ser un número (ej: 440).")

        try:
            num_clases = int(form.get("num_clases") or 9)
        except ValueError:
            raise ConfiguracionInvalidaError("El número de clases debe ser un número entero.")

        nombre = (form.get("nombre_curso") or "").strip() or f"Curso {curso_id}"

        config = cls(
            curso_id=curso_id,
            nombre=nombre,
            grupos_texto=(form.get("grupos") or "").strip(),
            num_clases=num_clases,
            sin_examen_final="sin_examen_final" in form,
            sin_trabajo_final="sin_trabajo_final" in form,
            trabajo_final_no_visible_en_av="trabajo_final_no_visible_en_av" in form,
        )
        config.validar()
        return config
