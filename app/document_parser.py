"""
document_parser.py
------------------
Extraccion determinista del .docx. Todo en memoria / archivo temporal.
No persiste nada.

Lo que sale de aqui alimenta dos cosas:
  - el bloque de texto que se manda a Claude
  - los "candidatos deterministas" (version, fecha, responsable, estado,
    confidencialidad) que se detectan con reglas ANTES de preguntarle al modelo
"""

from __future__ import annotations

import base64
import io
import os
import re
from datetime import datetime

import json as _json

import pdfplumber
from pptx import Presentation as _Presentation
from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT

MAX_IMAGENES = 4
MIN_BYTES_IMAGEN = 12_000          # descarta logos y vinetas
MAX_BYTES_IMAGEN = 4_500_000
MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

# ---------------------------------------------------------------------------
# Patrones deterministas
# ---------------------------------------------------------------------------

RE_VERSION = re.compile(
    r"(?:versi[oó]n|version|ver\.?|v)\s*[:\-]?\s*"
    r"(\d+(?:\.\d+){0,2}[a-zA-Z]?)",
    re.IGNORECASE,
)
RE_VERSION_ARCHIVO = re.compile(r"[_\-\s]v(\d+(?:\.\d+){0,2})", re.IGNORECASE)

RE_FECHA_ISO = re.compile(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b")
RE_FECHA_TEXTO = re.compile(
    r"\b(\d{1,2})\s+de\s+"
    r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|setiembre|octubre|noviembre|diciembre)"
    r"\s+(?:de\s+)?(20\d{2})\b",
    re.IGNORECASE,
)
MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

RE_RESPONSABLE = re.compile(
    r"(?:responsable|propietario|owner|autor|elabor[oó]|elaborado por|"
    r"preparado por|aprobado por|revisado por|due[nñ]o)\s*[:\-]\s*"
    r"([^\n\|]{3,80})",
    re.IGNORECASE,
)

# Autores que Word o las herramientas dejan por defecto: no son responsables reales.
AUTORES_GENERICOS = {
    "", "python-docx", "usuario", "user", "admin", "administrador",
    "microsoft office user", "windows user", "autor", "unknown", "office",
}

MARCAS_ESTADO = {
    "Borrador": [r"\bborrador\b", r"\bdraft\b", r"\bwork in progress\b", r"\bwip\b"],
    "En revision": [r"\ben revisi[oó]n\b", r"\bpara revisi[oó]n\b", r"\bin review\b"],
    "Aprobado": [r"\baprobado\b", r"\bapproved\b", r"\bvisto bueno\b"],
    "Vigente": [r"\bvigente\b", r"\bversi[oó]n vigente\b", r"\bliberado\b"],
    "Obsoleto": [r"\bobsoleto\b", r"\bdeprecad[oa]\b", r"\bsuperad[oa] por\b"],
}

MARCAS_CONFIDENCIALIDAD = {
    "Publico": [r"\bp[uú]blico\b", r"\bpublic\b", r"\buso p[uú]blico\b"],
    "Interno": [r"\buso interno\b", r"\binterno\b", r"\binternal use\b"],
    "Confidencial": [r"\bconfidencial\b", r"\bconfidential\b"],
    "Restringido": [r"\brestringid[oa]\b", r"\brestricted\b", r"\buso exclusivo\b"],
}


# ---------------------------------------------------------------------------
# Extraccion
# ---------------------------------------------------------------------------

def _iter_bloques(doc: Document):
    """Recorre parrafos y tablas en el orden real del documento."""
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    body = doc.element.body
    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            yield Paragraph(child, doc)
        elif tag == "tbl":
            yield Table(child, doc)


def _texto_tabla(tabla) -> dict:
    filas = []
    for fila in tabla.rows:
        celdas = [c.text.strip().replace("\n", " ") for c in fila.cells]
        if any(celdas):
            filas.append(celdas)
    return {"filas": filas, "n_filas": len(filas)}


def _propiedades(doc: Document) -> dict:
    p = doc.core_properties

    def _fmt(valor):
        if isinstance(valor, datetime):
            return valor.strftime("%Y-%m-%d")
        return valor or ""

    return {
        "titulo": p.title or "",
        "autor": p.author or "",
        "ultimo_modificado_por": p.last_modified_by or "",
        "creado": _fmt(p.created),
        "modificado": _fmt(p.modified),
        "revision": p.revision or "",
        "categoria": p.category or "",
        "asunto": p.subject or "",
        "palabras_clave": p.keywords or "",
        "estado_contenido": p.content_status or "",
        "comentarios": p.comments or "",
    }


def _encabezados_pies(doc: Document) -> list[str]:
    textos = []
    for seccion in doc.sections:
        for contenedor in (seccion.header, seccion.footer,
                           seccion.first_page_header, seccion.first_page_footer):
            if contenedor is None:
                continue
            for parrafo in contenedor.paragraphs:
                t = parrafo.text.strip()
                if t and t not in textos:
                    textos.append(t)
    return textos


def _imagenes(doc: Document) -> list[dict]:
    salida = []
    for rel in doc.part.rels.values():
        if rel.reltype != RT.IMAGE or rel.is_external:
            continue
        try:
            blob = rel.target_part.blob
        except Exception:
            continue
        ext = os.path.splitext(rel.target_part.partname)[1].lower()
        media = MEDIA_TYPES.get(ext)
        if not media:
            continue
        if len(blob) < MIN_BYTES_IMAGEN or len(blob) > MAX_BYTES_IMAGEN:
            continue
        salida.append({
            "media_type": media,
            "bytes": len(blob),
            "base64": base64.b64encode(blob).decode("ascii"),
        })
    salida.sort(key=lambda i: i["bytes"], reverse=True)
    return salida[:MAX_IMAGENES]


def parse_docx(ruta: str, nombre_original: str) -> dict:
    doc = Document(ruta)

    titulos, parrafos, tablas = [], [], []
    for bloque in _iter_bloques(doc):
        if hasattr(bloque, "text"):
            texto = bloque.text.strip()
            if not texto:
                continue
            estilo = (bloque.style.name or "") if bloque.style else ""
            if estilo.lower().startswith(("heading", "titulo", "título")):
                nivel = "".join(ch for ch in estilo if ch.isdigit()) or "1"
                titulos.append({"nivel": int(nivel), "texto": texto})
                parrafos.append(f"[H{nivel}] {texto}")
            else:
                parrafos.append(texto)
        else:
            tablas.append(_texto_tabla(bloque))

    props = _propiedades(doc)
    headers = _encabezados_pies(doc)
    imgs = _imagenes(doc)

    portada = "\n".join(parrafos[:25])
    cuerpo = "\n".join(parrafos)

    return {
        "nombre_archivo": nombre_original,
        "propiedades": props,
        "encabezados_pies": headers,
        "titulos": titulos,
        "parrafos": parrafos,
        "portada": portada,
        "texto": cuerpo,
        "tablas": tablas,
        "imagenes": imgs,
        "n_parrafos": len(parrafos),
        "n_tablas": len(tablas),
        "n_imagenes": len(imgs),
        "n_titulos": len(titulos),
    }


# ---------------------------------------------------------------------------
# Candidatos deterministas
# ---------------------------------------------------------------------------

def _zonas_prioritarias(parsed: dict) -> list[tuple[str, str]]:
    """(origen, texto) ordenado por confiabilidad de la evidencia."""
    zonas = [("propiedades del documento", " | ".join(
        f"{k}={v}" for k, v in parsed["propiedades"].items() if v))]
    zonas.append(("encabezado/pie de pagina", " | ".join(parsed["encabezados_pies"])))
    zonas.append(("portada", parsed["portada"]))
    zonas.append(("nombre del archivo", parsed["nombre_archivo"]))
    for i, tabla in enumerate(parsed["tablas"][:3], start=1):
        plano = " | ".join(" ; ".join(f) for f in tabla["filas"][:12])
        zonas.append((f"tabla {i}", plano))
    return [(o, t) for o, t in zonas if t]


def detectar_candidatos(parsed: dict) -> dict:
    """Reglas deterministas. Lo que sale de aqui NO lo tiene que adivinar el modelo."""
    cand = {}
    zonas = _zonas_prioritarias(parsed)

    # version
    props_ver = parsed["propiedades"].get("revision", "")
    for origen, texto in zonas:
        m = RE_VERSION.search(texto)
        if m:
            cand["version"] = {"valor": m.group(1), "evidencia": origen,
                               "metodo": "extraido"}
            break
    if "version" not in cand:
        m = RE_VERSION_ARCHIVO.search(parsed["nombre_archivo"])
        if m:
            cand["version"] = {"valor": m.group(1), "evidencia": "nombre del archivo",
                               "metodo": "derivado"}
        elif props_ver and str(props_ver) not in ("1", "0"):
            cand["version"] = {"valor": str(props_ver),
                               "evidencia": "propiedad revision de Word",
                               "metodo": "derivado"}

    # fecha
    # Las propiedades de Word traen la fecha de creacion del ARCHIVO, no la del
    # documento: una plantilla reutilizada arrastra la fecha de la plantilla.
    # Por eso primero se busca en el contenido y solo al final en las propiedades,
    # y en ese caso el metodo es "derivado", no "extraido".
    zonas_contenido = [(o, t) for o, t in zonas if o != "propiedades del documento"]
    for origen, texto in zonas_contenido:
        m = RE_FECHA_ISO.search(texto)
        if m:
            y, mo, d = m.groups()
            cand["fecha"] = {"valor": f"{y}-{int(mo):02d}-{int(d):02d}",
                             "evidencia": origen, "metodo": "extraido"}
            break
        m = RE_FECHA_TEXTO.search(texto)
        if m:
            d, mes, y = m.groups()
            cand["fecha"] = {"valor": f"{y}-{MESES[mes.lower()]:02d}-{int(d):02d}",
                             "evidencia": origen, "metodo": "extraido"}
            break
    if "fecha" not in cand:
        prop_fecha = (parsed["propiedades"].get("modificado")
                      or parsed["propiedades"].get("creado"))
        if prop_fecha:
            cand["fecha"] = {"valor": prop_fecha,
                             "evidencia": "propiedad de fecha de Word "
                                          "(no es fecha documental confirmada)",
                             "metodo": "derivado"}

    # responsable
    for origen, texto in zonas:
        m = RE_RESPONSABLE.search(texto)
        if m:
            valor = m.group(1).strip(" .;-")
            if valor and valor.lower() not in ("", "n/a", "na"):
                cand["responsable"] = {"valor": valor, "evidencia": origen,
                                       "metodo": "extraido"}
                break
    autor = (parsed["propiedades"].get("autor") or "").strip()
    if "responsable" not in cand and autor.lower() not in AUTORES_GENERICOS:
        if autor:
            cand["responsable"] = {"valor": autor,
                                   "evidencia": "propiedad autor de Word",
                                   "metodo": "derivado"}

    # estado
    for origen, texto in zonas:
        bajo = texto.lower()
        for estado, patrones in MARCAS_ESTADO.items():
            if any(re.search(p, bajo) for p in patrones):
                cand["estado"] = {"valor": estado, "evidencia": origen,
                                  "metodo": "extraido"}
                break
        if "estado" in cand:
            break

    # confidencialidad
    for origen, texto in zonas:
        bajo = texto.lower()
        for nivel, patrones in MARCAS_CONFIDENCIALIDAD.items():
            if any(re.search(p, bajo) for p in patrones):
                cand["confidencialidad"] = {"valor": nivel, "evidencia": origen,
                                            "metodo": "extraido"}
                break
        if "confidencialidad" in cand:
            break

    return cand


def bloque_para_modelo(parsed: dict, max_chars: int = 45_000) -> str:
    """Serializa el documento para el prompt, conservando estructura."""
    partes = [f"NOMBRE DEL ARCHIVO: {parsed['nombre_archivo']}"]

    props = {k: v for k, v in parsed["propiedades"].items() if v}
    if props:
        partes.append("PROPIEDADES DEL DOCUMENTO:\n" +
                      "\n".join(f"  - {k}: {v}" for k, v in props.items()))

    if parsed["encabezados_pies"]:
        partes.append("ENCABEZADOS Y PIES DE PAGINA:\n" +
                      "\n".join(f"  - {t}" for t in parsed["encabezados_pies"]))

    if parsed["titulos"]:
        partes.append("ESTRUCTURA DE SECCIONES:\n" + "\n".join(
            f"  {'  ' * (t['nivel'] - 1)}- {t['texto']}" for t in parsed["titulos"][:60]))

    partes.append("CONTENIDO:\n" + parsed["texto"])

    for i, tabla in enumerate(parsed["tablas"][:10], start=1):
        filas = "\n".join("  | " + " | ".join(f) for f in tabla["filas"][:15])
        partes.append(f"TABLA {i} ({tabla['n_filas']} filas):\n{filas}")

    texto = "\n\n".join(partes)
    if len(texto) > max_chars:
        mitad = max_chars // 2
        texto = (texto[:mitad] +
                 "\n\n[... contenido intermedio truncado por longitud ...]\n\n" +
                 texto[-mitad:])
    return texto


# ---------------------------------------------------------------------------
# Parsers por formato
# ---------------------------------------------------------------------------

def parse_pdf(ruta: str, nombre_original: str) -> dict:
    parrafos, tablas = [], []
    with pdfplumber.open(ruta) as pdf:
        for page in pdf.pages:
            texto = page.extract_text() or ""
            for linea in texto.splitlines():
                linea = linea.strip()
                if linea:
                    parrafos.append(linea)
            for tabla in (page.extract_tables() or []):
                filas = [[str(c or "").strip() for c in fila] for fila in tabla if any(fila)]
                if filas:
                    tablas.append({"filas": filas, "n_filas": len(filas)})

    portada = "\n".join(parrafos[:25])
    cuerpo = "\n".join(parrafos)
    return {
        "nombre_archivo": nombre_original,
        "propiedades": {},
        "encabezados_pies": [],
        "titulos": [],
        "parrafos": parrafos,
        "portada": portada,
        "texto": cuerpo,
        "tablas": tablas,
        "imagenes": [],
        "n_parrafos": len(parrafos),
        "n_tablas": len(tablas),
        "n_imagenes": 0,
        "n_titulos": 0,
    }


def parse_json_file(ruta: str, nombre_original: str) -> dict:
    with open(ruta, encoding="utf-8") as f:
        datos = _json.load(f)
    texto = _json.dumps(datos, ensure_ascii=False, indent=2)
    parrafos = [linea.strip() for linea in texto.splitlines() if linea.strip()]
    return {
        "nombre_archivo": nombre_original,
        "propiedades": {},
        "encabezados_pies": [],
        "titulos": [],
        "parrafos": parrafos,
        "portada": "\n".join(parrafos[:25]),
        "texto": texto,
        "tablas": [],
        "imagenes": [],
        "n_parrafos": len(parrafos),
        "n_tablas": 0,
        "n_imagenes": 0,
        "n_titulos": 0,
    }


def parse_pptx(ruta: str, nombre_original: str) -> dict:
    prs = _Presentation(ruta)
    parrafos, imagenes = [], []
    for i, slide in enumerate(prs.slides, start=1):
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    texto = para.text.strip()
                    if texto:
                        parrafos.append(texto)
            if hasattr(shape, "image"):
                try:
                    blob = shape.image.blob
                    ext = "." + shape.image.ext.lower()
                    media = MEDIA_TYPES.get(ext)
                    if media and MIN_BYTES_IMAGEN <= len(blob) <= MAX_BYTES_IMAGEN:
                        imagenes.append({
                            "media_type": media,
                            "bytes": len(blob),
                            "base64": base64.b64encode(blob).decode("ascii"),
                        })
                except Exception:
                    pass
        if slide.has_notes_slide:
            nota = slide.notes_slide.notes_text_frame.text.strip()
            if nota:
                parrafos.append(f"[Nota diapositiva {i}] {nota}")
    imagenes.sort(key=lambda x: x["bytes"], reverse=True)
    imagenes = imagenes[:MAX_IMAGENES]
    portada = "\n".join(parrafos[:25])
    return {
        "nombre_archivo": nombre_original,
        "propiedades": {},
        "encabezados_pies": [],
        "titulos": [],
        "parrafos": parrafos,
        "portada": portada,
        "texto": "\n".join(parrafos),
        "tablas": [],
        "imagenes": imagenes,
        "n_parrafos": len(parrafos),
        "n_tablas": 0,
        "n_imagenes": len(imagenes),
        "n_titulos": 0,
    }


def parse_image(ruta: str, nombre_original: str) -> dict:
    ext = os.path.splitext(nombre_original)[1].lower()
    media_type = MEDIA_TYPES.get(ext, "image/jpeg")
    with open(ruta, "rb") as f:
        blob = f.read()
    imagen = {
        "media_type": media_type,
        "bytes": len(blob),
        "base64": base64.b64encode(blob).decode("ascii"),
    }
    return {
        "nombre_archivo": nombre_original,
        "propiedades": {},
        "encabezados_pies": [],
        "titulos": [],
        "parrafos": [],
        "portada": "",
        "texto": "",
        "tablas": [],
        "imagenes": [imagen],
        "n_parrafos": 0,
        "n_tablas": 0,
        "n_imagenes": 1,
        "n_titulos": 0,
    }


def parse(ruta: str, nombre_original: str) -> dict:
    """Enruta al parser correcto segun la extension."""
    ext = os.path.splitext(nombre_original)[1].lower()
    if ext == ".docx":
        return parse_docx(ruta, nombre_original)
    if ext == ".pdf":
        return parse_pdf(ruta, nombre_original)
    if ext == ".json":
        return parse_json_file(ruta, nombre_original)
    if ext in (".pptx", ".ppt"):
        return parse_pptx(ruta, nombre_original)
    if ext in (".png", ".jpg", ".jpeg"):
        return parse_image(ruta, nombre_original)
    raise ValueError(f"Formato no soportado: {ext}")
    """Serializa el documento para el prompt, conservando estructura."""
    partes = [f"NOMBRE DEL ARCHIVO: {parsed['nombre_archivo']}"]

    props = {k: v for k, v in parsed["propiedades"].items() if v}
    if props:
        partes.append("PROPIEDADES DEL DOCUMENTO:\n" +
                      "\n".join(f"  - {k}: {v}" for k, v in props.items()))

    if parsed["encabezados_pies"]:
        partes.append("ENCABEZADOS Y PIES DE PAGINA:\n" +
                      "\n".join(f"  - {t}" for t in parsed["encabezados_pies"]))

    if parsed["titulos"]:
        partes.append("ESTRUCTURA DE SECCIONES:\n" + "\n".join(
            f"  {'  ' * (t['nivel'] - 1)}- {t['texto']}" for t in parsed["titulos"][:60]))

    partes.append("CONTENIDO:\n" + parsed["texto"])

    for i, tabla in enumerate(parsed["tablas"][:10], start=1):
        filas = "\n".join("  | " + " | ".join(f) for f in tabla["filas"][:15])
        partes.append(f"TABLA {i} ({tabla['n_filas']} filas):\n{filas}")

    texto = "\n\n".join(partes)
    if len(texto) > max_chars:
        mitad = max_chars // 2
        texto = (texto[:mitad] +
                 "\n\n[... contenido intermedio truncado por longitud ...]\n\n" +
                 texto[-mitad:])
    return texto
