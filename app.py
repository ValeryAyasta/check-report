import base64
import hmac
import logging
import os
import re
import secrets
import shutil
import tempfile
import threading
import time
import uuid
from collections import defaultdict
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session

load_dotenv()  # lee variables desde un archivo .env si existe (solo para desarrollo local;
                # en producción, configura las variables directamente en el servicio de hosting)

import config
from domain.curso import ConfiguracionCurso
# CheckReportError es la raíz de TODA excepción de negocio de la
# aplicación (login a Moodle, descarga, formato inesperado, archivos
# de tutora inválidos, configuración del formulario, etc. — ver
# domain/excepciones.py). Atraparla una sola vez acá reemplaza al
# except-por-cada-tipo que había antes, y cualquier excepción de
# negocio nueva que se agregue en el futuro en cualquier servicio
# queda cubierta automáticamente en cuanto herede de esta clase, sin
# tener que tocar app.py.
from domain.excepciones import CheckReportError
from application.pipeline import ejecutar_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

if not config.FLASK_SECRET_KEY:
    raise RuntimeError(
        "Falta la variable de entorno FLASK_SECRET_KEY. Genera una con:\n"
        "  python -c \"import secrets; print(secrets.token_hex(32))\"\n"
        "y expórtala antes de iniciar la aplicación."
    )

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB de archivos subidos, como máximo

# La cookie de sesión (usada solo para el token CSRF, ver más abajo) no
# lleva datos sensibles, pero igual se protege con lo mínimo estándar:
# no accesible por JS, no se envía en navegación cross-site, y solo por
# HTTPS cuando no se está en modo debug local (en debug local se corre
# por http:// sin certificado, así que exigir "Secure" ahí rompería la
# sesión en desarrollo).
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_DEBUG", "0") != "1"

# ---------------------------------------------------------------------
# Rate limiting SIN dependencias externas.
#
# Se probó primero con flask-limiter, pero en el entorno real donde se
# despliega esta app el `pip install` no tiene acceso a PyPI (proxy
# corporativo restringido) y no hay forma de instalar paquetes nuevos
# — solo lo que ya viene con Python. Esta es una implementación mínima
# con el mismo propósito: este endpoint termina haciendo un LOGIN REAL
# contra Moodle con las credenciales que llegan en el form, así que sin
# límite la app se podría usar (a propósito o por un bug en el
# frontend) para probar credenciales contra Moodle en bucle, usando
# este servidor como intermediario.
#
# Por IP, guarda en memoria la marca de tiempo de cada intento dentro
# de los últimos `ventana_segundos`; si ya hay `max_intentos` o más
# en esa ventana, corta con 429 antes de llegar a la vista.
#
# LIMITACIÓN (la misma que tendría con flask-limiter y su storage en
# memoria por defecto): el conteo vive en memoria del PROCESO. Si el
# servicio corre con más de un worker (gunicorn -w N con N>1), cada
# worker cuenta por separado — no aplica al despliegue actual de un
# solo proceso. Si en el futuro se necesita correr con varios workers,
# esto habría que moverlo a un backend compartido (ej: un archivo, una
# tabla, o sí instalar flask-limiter con Redis si en ese momento hay
# acceso a PyPI).
# ---------------------------------------------------------------------
_rate_limit_lock = threading.Lock()
_rate_limit_hits: dict[str, list[float]] = defaultdict(list)


def _reiniciar_rate_limiter_para_tests() -> None:
    """Solo para tests: limpia el estado entre casos para que no se
    contaminen entre sí (ver tests/test_app_seguridad.py)."""
    with _rate_limit_lock:
        _rate_limit_hits.clear()


def limite_de_tasa(max_intentos: int, ventana_segundos: int):
    def decorador(vista):
        @wraps(vista)
        def envoltura(*args, **kwargs):
            ip = request.remote_addr or "desconocida"
            ahora = time.monotonic()
            with _rate_limit_lock:
                intentos = _rate_limit_hits[ip]
                intentos[:] = [t for t in intentos if ahora - t < ventana_segundos]
                if len(intentos) >= max_intentos:
                    return jsonify(
                        ok=False,
                        error="Se hicieron demasiados intentos en poco tiempo. Espera un minuto y vuelve a intentarlo.",
                        codigo="LIMITE_DE_INTENTOS",
                    ), 429
                intentos.append(ahora)
            return vista(*args, **kwargs)
        return envoltura
    return decorador


@app.after_request
def agregar_cabeceras_de_seguridad(response):
    """Cabeceras estándar de bajo costo para cualquier formulario que
    recibe contraseñas: evitan que el navegador intente adivinar el
    tipo de contenido, que la página se embeba en un iframe ajeno
    (clickjacking), y que la URL completa viaje como Referer hacia
    otro sitio."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.is_secure:
        # Solo se anuncia HSTS cuando la request YA llegó por HTTPS:
        # anunciarlo en una respuesta http:// no tiene efecto real y
        # solo confundiría en un entorno de desarrollo sin certificado.
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def _generar_token_csrf() -> str:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


def _token_csrf_valido(token_recibido: str) -> bool:
    token_esperado = session.get("csrf_token", "")
    # compare_digest en vez de "==": evita que un atacante pueda medir
    # por tiempo de respuesta cuántos caracteres acertó (timing attack).
    # Poco probable de explotar acá en la práctica, pero es el patrón
    # correcto y estándar para comparar tokens/secretos, así que se usa
    # por hábito.
    return bool(token_esperado) and hmac.compare_digest(token_esperado, token_recibido or "")


def _nombre_archivo_seguro(nombre_original: str) -> str:
    """Sanitiza el nombre de un archivo subido antes de guardarlo en
    disco. A propósito NO se usa werkzeug.utils.secure_filename(): esa
    función borra por completo tildes y la ñ (los convierte a ASCII
    plano), y acá el nombre de archivo de cada tutora normalmente tiene
    su nombre real (ej: "María Núñez") — perderlo degradaría el
    reporte final para el caso de uso normal, no solo un detalle
    cosmético. En cambio, esto solo elimina lo peligroso: cualquier
    componente de ruta (/, \\, ..), bytes nulos, y cualquier carácter
    que no sea letra/número/espacio/guion/punto — preservando acentos
    y ñ, que si son válidos en un nombre de archivo real.
    """
    nombre = Path(nombre_original or "").name  # descarta cualquier ruta: "a/b/c.xlsx" -> "c.xlsx"
    nombre = nombre.replace("\x00", "")
    nombre = re.sub(r"[^\w .\-]", "_", nombre)  # \w en Python 3 ya es Unicode: preserva á, é, ñ, etc.
    nombre = nombre.strip(" .")  # Windows no admite nombres que terminen en espacio o punto
    if nombre in ("", ".", ".."):
        nombre = "archivo.xlsx"
    return nombre


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", csrf_token=_generar_token_csrf())


@app.route("/generar-reporte", methods=["POST"])
@limite_de_tasa(max_intentos=6, ventana_segundos=60)
def generar_reporte():
    """
    Siempre devuelve JSON: { ok, error } o { ok, archivo_base64, nombre_archivo, advertencias }.
    El frontend (index.html) se encarga de descargar el archivo o mostrar el error/las advertencias.
    """
    temp_dir = None
    try:
        if not _token_csrf_valido(request.form.get("csrf_token", "")):
            # Esto NO protege un secreto (el atacante no puede adivinar
            # la contraseña de Moodle de la tutora por más que rompa el
            # CSRF), pero sí evita que una página de OTRO sitio pueda
            # disparar generaciones de reporte en nombre de una sesión
            # abierta sin que la usuaria lo haya pedido — relevante
            # justamente porque el endpoint hace un login real.
            return jsonify(
                ok=False,
                error="Tu sesión expiró o la página se abrió hace mucho tiempo. Recarga la página e intenta de nuevo.",
                codigo="CSRF_INVALIDO",
            ), 400

        usuario = request.form.get("usuario", "").strip()
        password = request.form.get("password", "")
        if not usuario or not password:
            return jsonify(ok=False, error="Ingresa tu usuario y contraseña de Moodle."), 400

        curso = ConfiguracionCurso.desde_formulario(request.form)

        config.TEMP_DIR.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="checkreport-", dir=config.TEMP_DIR))

        # ---- archivos de tutoras (obligatorio, al menos 1) ----
        tutores_files = [f for f in request.files.getlist("tutores") if f and f.filename]
        if not tutores_files:
            return jsonify(ok=False, error="Debes subir al menos un archivo de asistencia de tutor."), 400

        tutores_dir = temp_dir / "tutores"
        tutores_dir.mkdir(exist_ok=True)
        tutores_dir_resuelto = tutores_dir.resolve()
        archivos_ignorados = []
        for f in tutores_files:
            if not f.filename.lower().endswith(".xlsx"):
                archivos_ignorados.append(f.filename)
                continue
            nombre_seguro = _nombre_archivo_seguro(f.filename)
            destino = tutores_dir / nombre_seguro
            # Defensa en profundidad: aunque _nombre_archivo_seguro() ya
            # no debería permitirlo, se confirma que el destino cae
            # DENTRO de tutores_dir antes de escribir el archivo.
            if tutores_dir_resuelto not in destino.resolve().parents:
                logger.warning("Nombre de archivo subido rechazado por seguridad: %r", f.filename)
                archivos_ignorados.append(f.filename)
                continue
            f.save(destino)

        resultado = ejecutar_pipeline(
            usuario=usuario,
            password=password,
            curso=curso,
            tutores_dir=tutores_dir,
            dir_trabajo=temp_dir,
        )

        advertencias = list(resultado.advertencias)
        if archivos_ignorados:
            advertencias.append(
                "Estos archivos no son .xlsx y se ignoraron: " + ", ".join(archivos_ignorados)
            )

        # Se lee el archivo a memoria y se borra el directorio temporal
        # (con datos de alumnos y, en algún momento, la sesión de Moodle)
        # ANTES de devolver la respuesta.
        nombre_descarga = resultado.ruta_excel_final.name
        contenido_excel = resultado.ruta_excel_final.read_bytes()
        shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir = None

        return jsonify(
            ok=True,
            nombre_archivo=nombre_descarga,
            archivo_base64=base64.b64encode(contenido_excel).decode("ascii"),
            advertencias=advertencias,
        )

    except CheckReportError as e:
        # Todo error de negocio esperado (configuración inválida del
        # formulario, login/descarga de Moodle fallidos, formato de
        # archivo inesperado, problema con los archivos de tutora,
        # etc.) llega acá. El mensaje de CheckReportError SIEMPRE es
        # seguro para mostrar tal cual a la usuaria (ver
        # domain/excepciones.py). `codigo` viaja también en el JSON
        # por si en el futuro el frontend necesita reaccionar distinto
        # según el tipo de error, sin tener que parsear el texto.
        logger.warning("Error de negocio (%s): %s", e.codigo, e)
        return jsonify(ok=False, error=str(e), codigo=e.codigo), 400
    except Exception:
        # Cualquier otra excepción es, por definición, algo que NO
        # anticipamos (un bug, una librería que cambió de comportamiento,
        # etc.). No se le muestra el detalle técnico a la usuaria — en
        # cambio, se genera un ID corto que queda en el log junto al
        # traceback completo, para poder ubicarlo rápido si la usuaria
        # lo reporta a soporte sin tener que pedirle detalles técnicos.
        error_id = uuid.uuid4().hex[:8]
        logger.exception("Error inesperado [%s] procesando el formulario", error_id)
        return jsonify(
            ok=False,
            error=(
                "Ocurrió un error inesperado generando el reporte. Vuelve a intentarlo; "
                f"si el problema persiste, contacta al encargado técnico con este código: {error_id}."
            ),
            codigo="ERROR_INTERNO",
            error_id=error_id,
        ), 500
    finally:
        if temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)