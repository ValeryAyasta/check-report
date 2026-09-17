"""
Modelo de dominio: configuración de un curso de Discipulado.

Antes, todo el comportamiento condicional (número de clases, si hay TF,
si hay examen, etc.) estaba implícito o hardcodeado en distintos archivos.
Ahora vive en un solo lugar: ConfiguracionCurso. El resto del pipeline
recibe este objeto y actúa en base a sus atributos, en vez de asumir
una estructura fija.
"""
from __future__ import annotations

from dataclasses import dataclass


class ConfiguracionInvalidaError(Exception):
    """La tutora ingresó datos incompletos o inconsistentes en el formulario."""
    pass


@dataclass
class ConfiguracionCurso:
    curso_id: int
    nombre: str

    # ID numérico del grupo en Moodle (lo encuentra la tutora en la URL
    # de su grupo dentro del curso). Aunque conceptualmente sea siempre
    # "C11"/"C21" para esta iglesia, Moodle usa un ID interno DISTINTO
    # por cada curso — por eso se ingresa el número, no el texto.
    grupo_c11: str = ""
    grupo_c21: str = ""

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
        """IDs numéricos de grupo de Moodle a consultar (C11 / C21), sin vacíos."""
        return [g.strip() for g in (self.grupo_c11, self.grupo_c21) if g and g.strip()]

    def validar(self) -> None:
        if self.curso_id <= 0:
            raise ConfiguracionInvalidaError("El ID de curso debe ser un número positivo.")
        if not self.grupos:
            raise ConfiguracionInvalidaError(
                "Debes ingresar al menos un ID de grupo (C11 o C21)."
            )
        for g in self.grupos:
            if not g.isdigit():
                raise ConfiguracionInvalidaError(
                    f"'{g}' no parece un ID de grupo de Moodle válido (debe ser un número, "
                    "ej: 45094). Lo encuentras en la URL del grupo dentro del curso en Moodle."
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
            grupo_c11=(form.get("grupo_c11") or "").strip(),
            grupo_c21=(form.get("grupo_c21") or "").strip(),
            num_clases=num_clases,
            sin_examen_final="sin_examen_final" in form,
            sin_trabajo_final="sin_trabajo_final" in form,
            trabajo_final_no_visible_en_av="trabajo_final_no_visible_en_av" in form,
        )
        config.validar()
        return config