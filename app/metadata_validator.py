"""
metadata_validator.py
---------------------
Barrera entre lo que devuelve el modelo y lo que se le muestra al usuario.

Hace cuatro cosas:
  1. Normaliza la forma (que existan todos los campos).
  2. Fuerza los catalogos controlados.
  3. Degrada a "No identificado" los campos declarativos sin evidencia.
  4. Calcula nivel de confianza y una bandera de revision por campo.
"""

from __future__ import annotations

import random
import string
import unicodedata

from . import taxonomy

NO_ID_TEXTO = {"", "n/a", "na", "none", "null", "-", "sin dato", "desconocido"}


def _sin_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def _match_catalogo(valor, catalogo: list[str], fallback: str) -> str:
    if not isinstance(valor, str) or valor.strip().lower() in NO_ID_TEXTO:
        return fallback
    objetivo = _sin_acentos(valor.strip().lower())
    for opcion in catalogo:
        if _sin_acentos(opcion.lower()) == objetivo:
            return opcion
    for opcion in catalogo:
        if objetivo in _sin_acentos(opcion.lower()):
            return opcion
    return fallback


def _generar_id() -> str:
    sufijo = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"POC-ACT-{sufijo}"


def _tiene_evidencia(campo: str, evidencias: dict) -> bool:
    ev = evidencias.get(campo) or {}
    if not isinstance(ev, dict):
        return False
    metodo = str(ev.get("metodo", "")).lower()
    origen = str(ev.get("origen", "")).strip()
    if metodo in ("no_identificado", "inferido", ""):
        return False
    return bool(origen) and origen.lower() not in NO_ID_TEXTO


def validar(datos: dict, candidatos: dict, parsed: dict) -> dict:
    datos = dict(datos or {})
    evidencias = datos.get("evidencias") or {}
    if not isinstance(evidencias, dict):
        evidencias = {}
    observaciones = list(datos.get("observaciones") or [])

    salida = {}

    # --- id -----------------------------------------------------------------
    id_val = str(datos.get("id") or "").strip()
    id_generado = not id_val or id_val.lower() in NO_ID_TEXTO
    if id_generado:
        id_val = _generar_id()
        observaciones.append(
            "El documento no trae identificador oficial. Se asigno un ID temporal "
            "de la POC; no debe usarse como clave definitiva.")
    salida["id"] = id_val

    # --- enums --------------------------------------------------------------
    salida["tipo"] = _match_catalogo(datos.get("tipo"), taxonomy.TIPOS, "Entregable")
    salida["tipo_activo"] = _match_catalogo(datos.get("tipo_activo"), taxonomy.TIPOS_ACTIVO, "documento")
    salida["fase"] = _match_catalogo(datos.get("fase"), taxonomy.FASES, "No identificada")
    salida["estado"] = _match_catalogo(
        datos.get("estado"), taxonomy.ESTADOS, "No identificado")
    salida["confidencialidad"] = _match_catalogo(
        datos.get("confidencialidad"), taxonomy.CONFIDENCIALIDAD, "No identificado")

    # --- texto libre --------------------------------------------------------
    for campo, fallback in (("descripcion", "No identificada"),
                            ("version", "No identificada"),
                            ("responsable", "No identificado"),
                            ("fecha", "No identificada"),
                            ("fuente", "No identificada"),
                            ("trazabilidad", "No identificada")):
        valor = datos.get(campo)
        valor = valor.strip() if isinstance(valor, str) else ""
        salida[campo] = valor if valor and valor.lower() not in NO_ID_TEXTO else fallback

    # --- contexto -----------------------------------------------------------
    ctx_in = datos.get("contexto")
    if isinstance(ctx_in, str):
        ctx_in = {"contexto_funcional": ctx_in}
    if not isinstance(ctx_in, dict):
        ctx_in = {}
    salida["contexto"] = {
        eje: (str(ctx_in.get(eje) or "").strip() or "No identificado")
        for eje in taxonomy.EJES_CONTEXTO
    }

    # --- relaciones ---------------------------------------------------------
    relaciones, vistos = [], set()
    for rel in (datos.get("relaciones") or []):
        if not isinstance(rel, dict):
            continue
        nombre = str(rel.get("nombre") or "").strip()
        if not nombre:
            continue
        tipo = _match_catalogo(rel.get("tipo"), taxonomy.TIPOS_RELACION, "Sistema")
        clave = (tipo, nombre.lower())
        if clave in vistos:
            continue
        vistos.add(clave)
        relaciones.append({"tipo": tipo, "nombre": nombre})
    salida["relaciones"] = relaciones[:25]

    # --- arbitraje: regla determinista vs. modelo ---------------------------
    # Si el analizador encontro el valor literal en el archivo y el modelo dice
    # otra cosa, gana el analizador salvo que el modelo aporte evidencia propia.
    # Este es el caso peligroso: un documento marcado BORRADOR que el modelo
    # clasifica como Aprobado porque "se ve formal".
    # Solo los candidatos "extraido" (leidos literalmente en el contenido) tienen
    # autoridad para sobrescribir al modelo. Los "derivado" (propiedades de Word,
    # nombre de archivo) son pistas: se ofrecen en el prompt pero no ganan aqui,
    # porque una plantilla reutilizada arrastra autor y fecha del archivo original.
    fuertes = {k: v for k, v in candidatos.items() if v["metodo"] == "extraido"}

    corregidos, degradados = [], []
    for campo in taxonomy.CAMPOS_CON_EVIDENCIA_OBLIGATORIA:
        fallback = taxonomy.ATRIBUTOS[campo]["fallback"]
        actual = salida.get(campo)

        if campo in fuertes:
            det = fuertes[campo]["valor"]
            if campo in ("estado", "confidencialidad"):
                catalogo = (taxonomy.ESTADOS if campo == "estado"
                            else taxonomy.CONFIDENCIALIDAD)
                det = _match_catalogo(det, catalogo, fallback)
            if _sin_acentos(str(actual).lower()) != _sin_acentos(str(det).lower()):
                if _tiene_evidencia(campo, evidencias):
                    observaciones.append(
                        f"Discrepancia en '{campo}': el analizador leyo '{det}' en "
                        f"{fuertes[campo]['evidencia']} y el modelo propone "
                        f"'{actual}'. Se conservo el valor del modelo porque cito "
                        f"evidencia propia. Confirmar con una persona.")
                else:
                    corregidos.append(f"{campo}: '{actual}' -> '{det}'")
                    salida[campo] = det
            continue

        if actual == fallback:
            continue
        if not _tiene_evidencia(campo, evidencias):
            degradados.append(f"{campo} ('{actual}')")
            salida[campo] = fallback

    if corregidos:
        observaciones.append(
            "Se corrigieron con la evidencia literal del archivo: "
            + "; ".join(corregidos) + ".")
    if degradados:
        observaciones.append(
            "Se degradaron a 'No identificado' por falta de evidencia literal: "
            + ", ".join(degradados) + ".")

    # --- confianza ----------------------------------------------------------
    conf_in = datos.get("confianza") or {}
    confianza = {}
    for campo in taxonomy.CAMPOS_CONFIANZA:
        valor = salida.get(campo)
        tiene_valor = bool(valor) and not (
            isinstance(valor, str) and valor.startswith("No identificad"))
        # Si el modelo omitio el score, no se asume 0: se usa un piso neutro
        # que deja el campo en "requiere revision" sin fingir certeza.
        por_defecto = 60 if tiene_valor else 20
        try:
            score = int(conf_in[campo])
        except (KeyError, TypeError, ValueError):
            score = por_defecto
        score = max(0, min(100, score))
        if campo in fuertes:
            score = max(score, 85)
        elif campo in candidatos:
            score = min(max(score, 55), 69)   # pista derivada: siempre a revision
        if campo == "relaciones" and not salida["relaciones"]:
            score = min(score, 35)
        if campo == "id" and id_generado:
            score = min(score, 30)
        # Ultimo, para que ningun piso anterior lo contradiga: un campo sin
        # valor identificado nunca puede reportar confianza alta.
        if not tiene_valor:
            score = min(score, 35)
        confianza[campo] = score
    salida["confianza"] = confianza
    salida["niveles"] = {c: taxonomy.nivel_confianza(s) for c, s in confianza.items()}
    salida["requiere_revision"] = sorted(
        c for c, s in confianza.items() if s < taxonomy.UMBRALES_CONFIANZA["media"])

    # --- evidencias normalizadas -------------------------------------------
    ev_norm = {}
    for campo in taxonomy.ATRIBUTOS:
        if campo in fuertes:
            ev_norm[campo] = {
                "metodo": fuertes[campo]["metodo"],
                "origen": fuertes[campo]["evidencia"],
                "cita": fuertes[campo]["valor"],
            }
            continue
        if campo in candidatos and salida.get(campo) == candidatos[campo]["valor"]:
            ev_norm[campo] = {
                "metodo": candidatos[campo]["metodo"],
                "origen": candidatos[campo]["evidencia"],
                "cita": candidatos[campo]["valor"],
            }
            continue
        ev = evidencias.get(campo)
        if isinstance(ev, dict):
            ev_norm[campo] = {
                "metodo": (str(ev.get("metodo") or "no_identificado").lower()
                           if str(ev.get("metodo") or "").lower() in taxonomy.METODOS
                           else "inferido"),
                "origen": str(ev.get("origen") or "").strip() or "No identificado",
                "cita": str(ev.get("cita") or "").strip()[:280],
            }
        else:
            ev_norm[campo] = {"metodo": "no_identificado",
                              "origen": "No identificado", "cita": ""}
    salida["evidencias"] = ev_norm

    salida["observaciones"] = [str(o) for o in observaciones if str(o).strip()][:12]

    # --- metricas del archivo (no contenido) --------------------------------
    salida["_documento"] = {
        "nombre_archivo": parsed["nombre_archivo"],
        "parrafos": parsed["n_parrafos"],
        "secciones": parsed["n_titulos"],
        "tablas": parsed["n_tablas"],
        "imagenes_analizadas": parsed["n_imagenes"],
    }
    salida["_uso"] = datos.get("_uso", {})
    return salida
