import base64
import logging
import os
import shutil
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()  # lee variables desde un archivo .env si existe (solo para desarrollo local;
                # en producción, configura las variables directamente en el servicio de hosting)

import config
from domain.curso import ConfiguracionCurso, ConfiguracionInvalidaError
from pipeline import ejecutar_pipeline, PipelineError

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


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/generar-reporte", methods=["POST"])
def generar_reporte():
    """
    Siempre devuelve JSON: { ok, error } o { ok, archivo_base64, nombre_archivo, advertencias }.
    El frontend (index.html) se encarga de descargar el archivo o mostrar el error/las advertencias.
    """
    temp_dir = None
    try:
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
            return jsonify(ok=False, error="Debes subir al menos un archivo de asistencia de tutora."), 400

        tutores_dir = temp_dir / "tutores"
        tutores_dir.mkdir(exist_ok=True)
        archivos_ignorados = []
        for f in tutores_files:
            if not f.filename.lower().endswith(".xlsx"):
                archivos_ignorados.append(f.filename)
                continue
            f.save(tutores_dir / f.filename)

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

    except ConfiguracionInvalidaError as e:
        return jsonify(ok=False, error=str(e)), 400
    except PipelineError as e:
        return jsonify(ok=False, error=str(e)), 400
    except Exception:
        logger.exception("Error inesperado procesando el formulario")
        return jsonify(
            ok=False,
            error=(
                "Ocurrió un error inesperado generando el reporte. Si el problema persiste, "
                "revisa los logs del servidor o contacta al encargado técnico."
            ),
        ), 500
    finally:
        if temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)