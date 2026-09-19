"""
Configuración y constantes globales de la aplicación.

REGLA GENERAL DEL PROYECTO:
- Lo que NUNCA cambia entre ejecuciones (URLs, nombres de hoja fijos,
  colores del formato, timeouts) vive AQUÍ como constante en MAYÚSCULAS.
- Lo que SÍ cambia según el curso (número de clases, si tiene examen,
  códigos de grupo, etc.) NO va aquí: lo ingresa la tutora en el
  formulario y viaja en un objeto ConfiguracionCurso
  (ver domain/curso.py). Nunca debe quedar hardcodeado en la lógica.
"""
import os
from pathlib import Path

# ============================================================
# Seguridad / Flask
# ============================================================
# La secret key YA NO tiene un valor por defecto hardcodeado.
# Debes definirla como variable de entorno antes de iniciar la app.
# Genera una con: python -c "import secrets; print(secrets.token_hex(32))"
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY")

# ============================================================
# Moodle
# ============================================================
MOODLE_BASE_URL = "https://escuela.ccaguaviva.org"
REQUEST_TIMEOUT_SEGUNDOS = 30

# ============================================================
# Rutas de archivos temporales
# ============================================================
BASE_DIR = Path(__file__).parent
TEMP_DIR = BASE_DIR / "temp"
NOMBRE_HOJA_ASISTENCIA_TUTOR = "ASISTENCIA"
NOMBRE_HOJA_DEVOCIONALES_TUTOR = "DEVO"

# ============================================================
# Layout del export de NOTAS de Moodle (grade export .xlsx)
# ============================================================
# Verificado contra archivos reales de Moodle (Discipulado I sin TF,
# Discipulado II con TF). Las columnas se identifican por NOMBRE
# (no por posición), así que el orden y la presencia/ausencia de
# columnas opcionales (Examen Final, Tarea Final) ya NO rompe nada:
# antes, un índice fijo como [3, 9] funcionaba para un curso y se
# desalineaba en otro apenas cambiaba el número de columnas.
#
# "patrones": texto (o textos alternativos) que debe contener el
#             nombre de columna, sin importar mayúsculas/tildes.
# "descartar": True = se lee pero no se conserva en el reporte final.
# "condicional":
#     None         -> siempre debe existir en el archivo (obligatoria).
#     "opcional"   -> su presencia se usa para DETECTAR automáticamente
#                     si el curso tiene ese indicador en el Aula Virtual
#                     (Examen Final / Trabajo Final).
#     "informativa" -> se incluye si existe, pero no es obligatoria ni
#                      se usa para nada más. Actualmente ninguna columna
#                      usa esta categoría ("Grupo" volvió a ser
#                      obligatoria: es la que se usa para filtrar por
#                      C11/C21, ver services/layout.filtrar_por_grupo).
COLUMNAS_NOTAS_MOODLE = {
    "nombre":        {"patrones": ["nombre"],               "descartar": False, "condicional": None,     "clave_final": "Nombre"},
    "apellidos":     {"patrones": ["apellido"],              "descartar": False, "condicional": None,     "clave_final": "Apellidos"},
    "dni":           {"patrones": ["nombre de usuario"],     "descartar": False, "condicional": None,     "clave_final": "DNI"},
    "correo":        {"patrones": ["direcci", "correo"],     "descartar": True,  "condicional": None,     "clave_final": None},
    "telefono":      {"patrones": ["tel"],                   "descartar": True,  "condicional": None,     "clave_final": None},
    "grupo":         {"patrones": ["grupo"],                 "descartar": False, "condicional": None,     "clave_final": "Grupo"},
    "asistencia_av": {"patrones": ["asistencia"],             "descartar": False, "condicional": None,     "clave_final": "Asistencia AV"},
    "tf_av":         {"patrones": ["tarea final", "trabajo final"], "descartar": False, "condicional": "opcional", "clave_final": "TF (AV)"},
    "ef_av":         {"patrones": ["examen final"],           "descartar": False, "condicional": "opcional", "clave_final": "EF (AV)"},
    "total_av":      {"patrones": ["total del curso"],        "descartar": True,  "condicional": None,     "clave_final": None},
    "ultima_descarga": {"patrones": ["última descarga", "ultima descarga"], "descartar": True, "condicional": None, "clave_final": None},
}

# ============================================================
# Layout del CSV de "checks" de Moodle (reporte de finalización de
# actividades, una columna "Clase N" con estado Finalizado/vacío por
# cada clase, más una columna de fecha que no se usa en el reporte).
# ============================================================
CHECKS_ENCODING = "utf-16-le"
CHECKS_SEPARADOR = "\t"
CHECKS_PATRON_COLUMNA_CLASE = "clase"  # columnas "Clase 1", "Clase 2", ...
CHECKS_PATRON_DNI = "nombre de usuario"

# ============================================================
# Colores / formato del Excel final
# ============================================================
COLOR_NEGRO = "000000"
COLOR_BLANCO = "FFFFFF"
COLOR_ROJO = "FF0000"
COLOR_AMARILLO = "FFFF00"
COLOR_AZUL_HEADER = "0070C0"
COLOR_VERDE_HEADER = "00B050"
COLOR_MORADO_HEADER = "7030A0"

COLOR_ASISTENCIA_COMPLETA = "00B050"   # verde: asistió a todas las clases
COLOR_ASISTENCIA_PARCIAL = "92D050"    # verde claro: asistió a la mayoría
COLOR_CHECK_PRESENTE = "34A853"        # verde: check marcado en Drive
COLOR_CHECK_AUSENTE = "595959"         # gris: check vacío en Drive
COLOR_CELDA_INCONSISTENCIA = "FFCCCC"  # rojo suave: AV y Drive no coinciden

# Estado final del alumno (punto 5 del pedido)
COLOR_APROBADO_FONDO = "FFFF00"   # amarillo
COLOR_APROBADO_TEXTO = "000000"   # negro (para que se lea sobre amarillo)
COLOR_DESAPROBADO_FONDO = "FF0000"  # rojo
COLOR_DESAPROBADO_TEXTO = "FFFFFF"  # blanco

# ============================================================
# Regla de nota de asistencia (0-20) según clases asistidas.
# ============================================================
# Tabla EXACTA que ya se usaba para cursos de 9 clases (se mantiene
# igual para no cambiar la nota de cursos existentes). Para cursos con
# un número distinto de clases (ej: 8), la nota se recalcula de forma
# proporcional en services/calculator.py (no hay que tocar nada aquí).
TABLA_NOTA_ASISTENCIA_9_CLASES = {
    1: 2, 2: 4, 3: 6, 4: 8, 5: 10, 6: 13, 7: 16, 8: 18, 9: 20,
}
NOTA_MAXIMA_ASISTENCIA = 20

# Mínimo de clases asistidas para aprobar por asistencia. Es un número
# FIJO (no proporcional al número de clases del curso): un curso de 8
# clases exige el mismo mínimo de 6 que uno de 9.
NUM_CLASES_MINIMAS_PARA_APROBAR = 6

# Umbral de % de clases asistidas para considerar "asistencia completa"
# a efectos de color (no de nota), aplicado sobre num_clases del curso.
UMBRAL_ASISTENCIA_PARCIAL = 0.6  # 60% o más = verde claro

# Además del mínimo de asistencia (y de haber entregado TF/resuelto EF
# cuando el curso los tiene), el promedio de los indicadores que
# apliquen (Asistencia, Examen si aplica, Trabajo Final si aplica) debe
# ser mayor o igual a este valor para aprobar.
PROMEDIO_MINIMO_PARA_APROBAR = 10.5

# ============================================================
# Layout del archivo de asistencia/devocionales de cada TUTORA (Drive)
# ============================================================
# ⚠️ Estos offsets vienen tal cual del código original (no se pudieron
# verificar contra un archivo real de una tutora). Si al probar con un
# archivo real no calzan, este es el único lugar donde hay que corregirlos.
TUTOR_FILA_INICIO_DATOS = 4       # primera fila con datos de alumnos (1-indexado)
TUTOR_COL_DNI = 5                 # columna E: DNI del alumno
TUTOR_COL_ASISTENCIA_INICIO = 6   # columna F: primera clase (se extiende num_clases columnas)
TUTOR_COL_TF_DRIVE = 35           # columna AI ("T1"): nota de Trabajo Final registrada en Drive
TUTOR_COL_EF_DRIVE = 37           # columna AK ("E1"): nota de Examen Final registrada en Drive
TUTOR_DEVO_FILA_OFFSET = 1        # la fila de devocionales está 1 fila debajo de la de asistencia
TUTOR_DEVO_COL_INICIO = 7         # columna G: primer día de devocional
TUTOR_DEVO_TOTAL_DIAS = 63        # cantidad de días de devocional en la hoja DEVO
TUTOR_COL_NOMBRE = 4
# ✅ Verificado contra un archivo real de tutora: todos estos offsets calzan exacto.