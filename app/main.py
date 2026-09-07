"""
main.py
-------
POC "TEC | Clasificador de Activos de Conocimiento IA-Ready".

Regla de arquitectura: el archivo vive en un temporal que se borra en un finally.
No hay carpeta de uploads, no hay base de datos, no hay storage.
"""

from __future__ import annotations

import logging
import os
import tempfile
import time
import zipfile
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import claude_service, document_parser, metadata_validator, taxonomy
from .models import RespuestaValidacion, SolicitudValidacion

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
MAX_MB = 50
MAX_BYTES = MAX_MB * 1024 * 1024
EXTENSIONES = {".docx", ".pdf", ".json", ".png", ".jpg", ".jpeg"}
MIME_VALIDOS = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/octet-stream",
    "application/pdf",
    "application/json",
    "text/plain",
    "image/png",
    "image/jpeg",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("poc-ia-ready")

app = FastAPI(title="TEC | Clasificador de Activos de Conocimiento IA-Ready")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


def _nombre_seguro(nombre: str) -> str:
    limpio = os.path.basename(nombre or "documento.docx")
    limpio = "".join(c for c in limpio if c.isalnum() or c in " ._-()")
    return limpio.strip() or "documento.docx"


@app.get("/", response_class=HTMLResponse)
def inicio():
    return (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")


@app.get("/api/taxonomy")
def taxonomia():
    """Expone los catalogos para que el formulario de edicion use listas cerradas."""
    return {
        "tipos": taxonomy.TIPOS,
        "estados": taxonomy.ESTADOS,
        "confidencialidad": taxonomy.CONFIDENCIALIDAD,
        "tipos_relacion": taxonomy.TIPOS_RELACION,
        "tipos_activo": taxonomy.TIPOS_ACTIVO,
        "fases": taxonomy.FASES,
        "ejes_contexto": taxonomy.EJES_CONTEXTO,
        "campos_con_evidencia": taxonomy.CAMPOS_CON_EVIDENCIA_OBLIGATORIA,
    }


@app.post("/api/analyze")
async def analizar(file: UploadFile = File(...)):
    inicio_t = time.perf_counter()
    nombre = _nombre_seguro(file.filename)
    extension = Path(nombre).suffix.lower()

    if extension not in EXTENSIONES:
        raise HTTPException(400, f"Formato no soportado ({extension}). "
                                 f"Formatos aceptados: .docx, .pdf, .json, .png, .jpg, .jpeg")
    if extension == ".docm" or nombre.lower().endswith(".docm"):
        raise HTTPException(400, "Los archivos con macros (.docm) no se procesan.")
    if file.content_type and file.content_type not in MIME_VALIDOS:
        raise HTTPException(400, f"Tipo MIME no valido: {file.content_type}")

    contenido = await file.read()
    if not contenido:
        raise HTTPException(400, "El archivo llego vacio.")
    if extension == ".docx" and not contenido.startswith(b"PK"):
        raise HTTPException(400, "El archivo no es un .docx valido.")

    ruta_temporal = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as tmp:
            tmp.write(contenido)
            ruta_temporal = tmp.name
        del contenido

        try:
            parsed = document_parser.parse(ruta_temporal, nombre)
        except (zipfile.BadZipFile, KeyError, ValueError) as exc:
            raise HTTPException(400, f"No se pudo leer el documento: {exc}")

        if parsed["n_parrafos"] == 0 and parsed["n_tablas"] == 0 and parsed["n_imagenes"] == 0:
            raise HTTPException(400, "El documento no contiene texto ni imagenes extraibles.")

        candidatos = document_parser.detectar_candidatos(parsed)
        texto = document_parser.bloque_para_modelo(parsed)

        try:
            crudo = claude_service.clasificar(texto, candidatos, parsed["imagenes"])
        except RuntimeError as exc:
            raise HTTPException(500, str(exc))
        except Exception as exc:
            log.exception("Fallo la llamada al modelo")
            raise HTTPException(502, f"La clasificacion no se completo: {exc}")

        activo = metadata_validator.validar(crudo, candidatos, parsed)
        duracion = round(time.perf_counter() - inicio_t, 2)

        # Log sin contenido documental ni datos extraidos.
        log.info(
            "analisis ok | duracion=%ss | parrafos=%s | tablas=%s | imagenes=%s | "
            "campos_en_revision=%s",
            duracion, parsed["n_parrafos"], parsed["n_tablas"],
            parsed["n_imagenes"], len(activo["requiere_revision"]),
        )

        return JSONResponse({
            "ok": True,
            "duracion_segundos": duracion,
            "activo": activo,
        })

    finally:
        if ruta_temporal and os.path.exists(ruta_temporal):
            try:
                os.remove(ruta_temporal)
                log.info("archivo temporal eliminado")
            except OSError:
                log.warning("no se pudo eliminar el temporal %s", ruta_temporal)


@app.post("/api/validate", response_model=RespuestaValidacion)
def validar_activo(payload: SolicitudValidacion):
    """Cierra el ciclo human-in-the-loop. No persiste: solo confirma."""
    activo = payload.activo or {}
    pendientes = [
        campo for campo in taxonomy.ATRIBUTOS
        if isinstance(activo.get(campo), str)
        and activo[campo].startswith("No identificad")
    ]
    if payload.decision == "pendiente":
        mensaje = "Activo marcado como pendiente de informacion."
    else:
        mensaje = "Activo de conocimiento validado."
    log.info("validacion | decision=%s | pendientes=%s",
             payload.decision, len(pendientes))
    return RespuestaValidacion(
        ok=True, mensaje=mensaje, decision=payload.decision,
        campos_pendientes=pendientes,
    )
