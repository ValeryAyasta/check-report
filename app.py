import logging

from flask import Flask, render_template, request, send_file, flash
from pathlib import Path
from reporte_asistencia import main_pipeline
import os, tempfile
import traceback

from services.auth import LoginError
from services.downloader import DownloadError
from services.reporte_unido import ProcessingError

# courses.py
CURSOS = {
    372: {"nombre":"DISCIPULADO 1 2025-II", "grupos": [37172,37226]}, #37172, 37226 (maritza)
    373: {"nombre": "DISCIPULADO 2 2025-II", "grupos": [37229,37190]}, #37229, 37190 (lucy)
    374: {"nombre": "DISCIPULADO 3 2025-II", "grupos": [37240, 37233]}, #valery
    440: {"nombre":"DISCIPULADO 1 2025-III", "grupos": [45094,45071]}, # (valery) 45094 (c11), 45071 (c21)
    441: {"nombre":"DISCIPULADO 2 2025-III", "grupos": []}, # (maritza)
    442: {"nombre":"DISCIPULADO 3 2025-III", "grupos": [45112,45203]}, #(lucy) #45112 (c21), 45203 (c11),
    516:{"nombre":"DISCIPULADO 2 2026-I", "grupos": [53829,53777]},
    587:{"nombre":"DISCIPULADO 2 2026-II", "grupos": [62009,62020]},
}


app = Flask(__name__)
app.secret_key = "e4c8a43c5b11d2f87f9f422d4dfb13e3"

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
      try:
        usuario = request.form["usuario"]
        password = request.form["password"]
        curso_id = int(request.form["curso"])
        grupos = CURSOS[curso_id]["grupos"]

        # Base del proyecto
        BASE_DIR = Path(__file__).parent

        # Carpeta segura dentro del proyecto
        TEMP_BASE = BASE_DIR / "temp"
        TEMP_BASE.mkdir(exist_ok=True)

        # Crear subcarpeta temporal única dentro de temp/
        temp_dir = tempfile.mkdtemp(prefix="drive-", dir=TEMP_BASE)

        # 1) Chequeamos si el usuario quiere usar padrón
        use_padron = "use_padron" in request.form
        padron_path = None
        if use_padron:
            padron_file = request.files.get("padron")
            if padron_file and padron_file.filename:
                padron_path = Path(temp_dir) / padron_file.filename
                padron_file.save(padron_path)


        # Recibir los archivos de tutores
        tutores_files = request.files.getlist("tutores")

        # Guardar todos en un directorio temporal
        tutores_dir = Path(temp_dir) / "drive-tutores"
        tutores_dir.mkdir(exist_ok=True)

        for f in tutores_files:
            if f and f.filename:  # <-- Verifica que tenga nombre
                save_path = tutores_dir / f.filename
                f.save(save_path)
            else:
                print("⚠️ Archivo sin nombre, omitido.")

        # Ejecutar pipeline
        path_final = main_pipeline(usuario, password, use_padron, padron_path, curso_id, grupos, tutores_dir)

        return send_file(path_final, as_attachment=True)



      except LoginError as e:
          flash(str(e), "error")

      except PermissionError as e:
          flash("Permisos insuficientes o sesión expirada en Moodle.", "error")

      except DownloadError as e:
          flash(f"Error al descargar CSV: {e}", "error")

      except ProcessingError as e:
          flash("Error al generar el reporte unido. Intenta nuevamente.", "error")

      except Exception as e:
          raise ProcessingError(f"generar_reporte_unido falló ({type(e).__name__}: {e})") from e

    return render_template("index.html", cursos=CURSOS)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)