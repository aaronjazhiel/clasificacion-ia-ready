"""
taxonomy.py
-----------
Fuente unica de verdad de la clasificacion.

Todo lo que este aqui se usa DOS veces:
  1. Se inyecta al prompt de Claude (para que clasifique dentro del catalogo).
  2. Se usa para validar la respuesta (para que no invente valores fuera del catalogo).

Si se agrega un valor nuevo, se agrega aqui y se propaga solo.
"""

# Categorias del PKH con su prefijo de ID
TIPOS = [
    "Entregable",        # ENT
    "Requerimiento",     # REQ
    "Decision",          # DEC
    "Riesgo",            # RSG
    "Supuesto",          # SUP
    "Evidencia",         # EVI
    "Criterio de aceptacion",  # CRA
    "Componente",        # CMP
    "Proceso",           # PRO
    "Responsable",       # RES
    "Dependencia",       # DEP
    "Leccion aprendida", # LEC
]

PREFIJOS = {
    "Entregable": "ENT",
    "Requerimiento": "REQ",
    "Decision": "DEC",
    "Riesgo": "RSG",
    "Supuesto": "SUP",
    "Evidencia": "EVI",
    "Criterio de aceptacion": "CRA",
    "Componente": "CMP",
    "Proceso": "PRO",
    "Responsable": "RES",
    "Dependencia": "DEP",
    "Leccion aprendida": "LEC",
}

ESTADOS = [
    "Borrador",
    "En revision",
    "Aprobado",
    "Publicado",
    "Obsoleto",
    "No identificado",
]

CONFIDENCIALIDAD = [
    "Publica",
    "Interna",
    "Confidencial",
    "Restringida",
    "No identificado",
]

TIPOS_RELACION = [
    "deriva de",
    "satisface",
    "tiene evidencia",
    "depende de",
    "reemplaza",
    "se relaciona con",
]

FASES = [
    "Fase 1",
    "Fase 2",
    "Fase 3",
    "No identificada",
]

TIPOS_ACTIVO = [
    "documento",
    "tabla",
    "diagrama",
    "registro",
    "politica",
]

METODOS = [
    "extraido",
    "derivado",
    "inferido",
    "no_identificado",
]

ATRIBUTOS = {
    "id": {
        "capa": "Identidad",
        "valor": "texto",
        "metodos_permitidos": ["extraido", "derivado"],
        "fallback": None,
    },
    "tipo": {
        "capa": "Naturaleza",
        "valor": "enum",
        "catalogo": TIPOS,
        "metodos_permitidos": ["extraido", "inferido"],
        "fallback": "Entregable",
    },
    "tipo_activo": {
        "capa": "Naturaleza",
        "valor": "enum",
        "catalogo": TIPOS_ACTIVO,
        "metodos_permitidos": ["extraido", "inferido"],
        "fallback": "documento",
    },
    "fase": {
        "capa": "Identidad",
        "valor": "enum",
        "catalogo": FASES,
        "metodos_permitidos": ["extraido"],
        "fallback": "No identificada",
    },
    "descripcion": {
        "capa": "Semantica",
        "valor": "texto",
        "metodos_permitidos": ["inferido"],
        "fallback": "No identificada",
    },
    "version": {
        "capa": "Identidad",
        "valor": "texto",
        "metodos_permitidos": ["extraido", "derivado"],
        "fallback": "No identificada",
    },
    "estado": {
        "capa": "Gobierno",
        "valor": "enum",
        "catalogo": ESTADOS,
        "metodos_permitidos": ["extraido"],
        "fallback": "No identificado",
    },
    "responsable": {
        "capa": "Gobierno",
        "valor": "texto",
        "metodos_permitidos": ["extraido"],
        "fallback": "No identificado",
    },
    "fecha": {
        "capa": "Identidad",
        "valor": "fecha",
        "metodos_permitidos": ["extraido"],
        "fallback": "No identificada",
    },
    "fuente": {
        "capa": "Procedencia",
        "valor": "texto",
        "metodos_permitidos": ["extraido", "derivado", "inferido"],
        "fallback": "No identificada",
    },
    "confidencialidad": {
        "capa": "Gobierno",
        "valor": "enum",
        "catalogo": CONFIDENCIALIDAD,
        "metodos_permitidos": ["extraido"],
        "fallback": "No identificado",
    },
    "contexto": {
        "capa": "Semantica",
        "valor": "objeto",
        "metodos_permitidos": ["inferido"],
        "fallback": None,
    },
    "relaciones": {
        "capa": "Grafo",
        "valor": "lista",
        "metodos_permitidos": ["extraido", "inferido"],
        "fallback": [],
    },
    "trazabilidad": {
        "capa": "Calidad",
        "valor": "texto",
        "metodos_permitidos": ["derivado"],
        "fallback": "No identificada",
    },
}

EJES_CONTEXTO = [
    "contexto_funcional",
    "contexto_tecnico",
    "dominio",
    "sistemas_involucrados",
    "proceso_relacionado",
]

CAMPOS_CON_EVIDENCIA_OBLIGATORIA = [
    "version",
    "estado",
    "responsable",
    "fecha",
    "confidencialidad",
]

CAMPOS_CONFIANZA = list(ATRIBUTOS.keys())

UMBRALES_CONFIANZA = {
    "alta": 90,
    "media": 70,
    "revision": 0,
}


def nivel_confianza(score: int) -> str:
    if score >= UMBRALES_CONFIANZA["alta"]:
        return "Alta"
    if score >= UMBRALES_CONFIANZA["media"]:
        return "Media"
    return "Requiere revision"
