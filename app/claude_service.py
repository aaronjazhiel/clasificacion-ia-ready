"""
claude_service.py
-----------------
Construye el prompt de catalogacion a partir de taxonomy.py y llama a la API.

El prompt no esta escrito a mano con los catalogos copiados: se genera desde
la taxonomia, asi que agregar un tipo o un estado nuevo solo se hace en un lugar.
"""

from __future__ import annotations

import json
import os
import re

import anthropic
from json_repair import repair_json

from . import taxonomy

MODELO = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
MAX_TOKENS = 8000

CONTEXTO_INSTITUCIONAL = """Estas analizando documentacion del Project Knowledge Hub (PKH) del Tecnologico de Monterrey, proyecto de Gobernanza de Aplicativos · VPAF · OmniSys.

El PKH es la memoria unica, estructurada y gobernada del proyecto. Cada documento
se convierte en un activo de conocimiento IA-ready con categoria, prefijo de ID,
estado de ciclo de vida, responsable, confidencialidad y trazabilidad.

Las 12 categorias del PKH y sus prefijos:
  ENT Entregable · REQ Requerimiento · DEC Decision · RSG Riesgo · SUP Supuesto
  EVI Evidencia · CRA Criterio de aceptacion · CMP Componente · PRO Proceso
  RES Responsable · DEP Dependencia · LEC Leccion aprendida

Regla de confidencialidad no negociable: si el activo toca datos de menores o
datos personales reales → Restringida, nunca se envia a IA.
Si no hay marca explicita de confidencialidad → Interna (valor por defecto del PKH).

Un activo no puede estar en estado Aprobado sin responsable, fuente y evidencia
registrados. Si alguno falta, el estado correcto es Borrador o En revision."""


def _catalogo(nombre: str, valores: list[str]) -> str:
    return f"{nombre}:\n" + "\n".join(f"  - {v}" for v in valores)


def construir_system_prompt() -> str:
    inferibles = [c for c, a in taxonomy.ATRIBUTOS.items()
                  if "inferido" in a["metodos_permitidos"]]
    literales = taxonomy.CAMPOS_CON_EVIDENCIA_OBLIGATORIA

    return f"""{CONTEXTO_INSTITUCIONAL}

Devuelves EXCLUSIVAMENTE un objeto JSON valido. Sin markdown, sin ```json,
sin texto antes ni despues.

=================================================================
REGLA CENTRAL: DOS CLASES DE ATRIBUTO
=================================================================

A) ATRIBUTOS INTERPRETABLES -> {", ".join(inferibles)}
   Son clasificaciones semanticas. Puedes deducirlas leyendo el documento,
   aunque no esten escritas de forma literal.

B) ATRIBUTOS DECLARATIVOS -> {", ".join(literales)}
   Son hechos administrativos. Solo puedes llenarlos si el valor aparece
   escrito en el documento, en sus propiedades, en encabezado/pie, en portada,
   en una tabla de control de cambios o en el nombre del archivo.
   Si no aparece: usa el valor "No identificado" / "No identificada".
   NUNCA los deduzcas por el tono, la formalidad o el aspecto del documento.
   Un documento bien formateado NO significa que este aprobado.

=================================================================
CATALOGOS CONTROLADOS (no inventes valores fuera de estas listas)
=================================================================

{_catalogo("tipo", taxonomy.TIPOS)}

{_catalogo("estado", taxonomy.ESTADOS)}

{_catalogo("confidencialidad", taxonomy.CONFIDENCIALIDAD)}

{_catalogo("relaciones[].tipo", taxonomy.TIPOS_RELACION)}

{_catalogo("metodo (como obtuviste cada valor)", taxonomy.METODOS)}

=================================================================
REGLAS POR CAMPO
=================================================================

id           Usa el identificador oficial si el documento lo trae (codigo de
             documento, folio, clave). Si no existe, devuelve "" y el sistema
             generara uno temporal.

tipo         Un solo valor del catalogo. Elige el que describa la FUNCION del
             documento, no su formato. Una minuta que contiene decisiones sigue
             siendo "Minuta"; un documento cuya razon de ser es registrar una
             decision es "Decision".

descripcion  1 a 3 oraciones. Explica que conocimiento aporta el activo, no
             como se llama. No repitas el titulo.

version      Cadena tal cual aparece ("1.3", "v2", "3.0 final"). Si no aparece:
             "No identificada".

estado       Solo con marca explicita (BORRADOR, VIGENTE, tabla de control de
             cambios, sello de aprobacion). Si no hay marca: "No identificado".

responsable  Persona o area explicitamente senalada como autor, propietario,
             responsable o aprobador. Si no aparece: "No identificado".

fecha        Formato AAAA-MM-DD. Fecha del documento, no la de hoy. Si hay
             varias, la de la version mas reciente. Si no aparece:
             "No identificada".

tipo_activo  Formato del activo: documento, tabla, diagrama, registro o politica.
             Deducelo del contenido si no esta escrito.

fase         Fase del proyecto en que se genera: Fase 1, Fase 2 o Fase 3.
             Solo si aparece explicitamente; si no: "No identificada".

fuente       De donde proviene el conocimiento: proyecto, area, sistema,
             reunion, repositorio o documento origen mencionado.

confidencialidad  Solo con leyenda explicita. Si no hay: "No identificado".

contexto     Objeto con estos ejes: {", ".join(taxonomy.EJES_CONTEXTO)}.
             Cada eje es una cadena breve. Si un eje no aplica, escribe
             "No identificado". sistemas_involucrados va como texto separado
             por comas.

relaciones   Lista de objetos {{"tipo": <catalogo>, "nombre": "..."}}.
             Extrae entidades reales nombradas en el documento o visibles en
             sus diagramas. Sin duplicados. Maximo 25.

trazabilidad Una frase que diga de donde salio la clasificacion, citando
             secciones, tablas, encabezados o imagenes concretas del documento.
             No inventes secciones que no existan.

evidencias   Objeto donde cada llave es un campo y el valor es
             {{"metodo": <catalogo>, "origen": "seccion/tabla/imagen/propiedad
             concreta", "cita": "fragmento breve del documento o cadena vacia"}}.
             Incluye al menos los campos declarativos.

confianza    Entero 0-100 por campo, para: {", ".join(taxonomy.CAMPOS_CONFIANZA)}.
             Calibra de verdad: si pusiste "No identificado" la confianza en ese
             campo debe ser baja (menor a 40). Si un valor es literal y explicito,
             puede pasar de 90. La confianza mide que tan respaldado esta el
             valor, no que tan seguro te sientes.

observaciones Lista de cadenas. Anota vacios relevantes, contradicciones,
             posible obsolescencia o cualquier cosa que un revisor humano deba
             mirar. Si no hay nada: lista vacia.

=================================================================
ESQUEMA DE SALIDA
=================================================================

{{
  "id": "",
  "tipo": "",
  "tipo_activo": "",
  "fase": "",
  "descripcion": "",
  "version": "",
  "estado": "",
  "responsable": "",
  "fecha": "",
  "fuente": "",
  "confidencialidad": "",
  "contexto": {{
    "contexto_funcional": "",
    "contexto_tecnico": "",
    "dominio": "",
    "sistemas_involucrados": "",
    "proceso_relacionado": ""
  }},
  "relaciones": [{{"tipo": "", "nombre": ""}}],
  "trazabilidad": "",
  "evidencias": {{"campo": {{"metodo": "", "origen": "", "cita": ""}}}},
  "confianza": {{"tipo": 0, "tipo_activo": 0, "fase": 0, "descripcion": 0,
                 "version": 0, "estado": 0, "responsable": 0, "fecha": 0,
                 "fuente": 0, "confidencialidad": 0, "contexto": 0,
                 "relaciones": 0, "trazabilidad": 0, "id": 0}},
  "observaciones": []
}}"""


def _bloque_candidatos(candidatos: dict) -> str:
    if not candidatos:
        return ("DETECCION DETERMINISTA PREVIA: el analizador no encontro marcas "
                "explicitas de version, fecha, responsable, estado ni "
                "confidencialidad. Trata esos campos como no identificados salvo "
                "que los veas literalmente en el contenido.")
    lineas = [
        f"  - {campo}: '{d['valor']}'  (origen: {d['evidencia']}, metodo: {d['metodo']})"
        for campo, d in candidatos.items()
    ]
    return ("DETECCION DETERMINISTA PREVIA (reglas del analizador, ya verificadas "
            "contra el archivo):\n" + "\n".join(lineas) +
            "\nUsa estos valores salvo que el contenido los contradiga. Si los "
            "contradices, explica por que en observaciones.")


def _contenido_usuario(texto_doc: str, candidatos: dict, imagenes: list[dict]) -> list:
    bloques = []

    for i, img in enumerate(imagenes, start=1):
        bloques.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": img["media_type"],
                "data": img["base64"],
            },
        })
        bloques.append({
            "type": "text",
            "text": (f"Imagen {i} del documento. Si es un diagrama, arquitectura, "
                     f"organigrama o captura, usa lo que aparece en ella para "
                     f"enriquecer tipo, contexto y relaciones. Si es decorativa, "
                     f"ignorala."),
        })

    bloques.append({
        "type": "text",
        "text": (f"{_bloque_candidatos(candidatos)}\n\n"
                 f"=== DOCUMENTO A CLASIFICAR ===\n\n{texto_doc}\n\n"
                 f"=== FIN DEL DOCUMENTO ===\n\n"
                 f"Devuelve unicamente el JSON del esquema."),
    })
    return bloques


def _extraer_json(texto: str) -> dict:
    texto = texto.strip()
    texto = re.sub(r"^```(?:json)?|```$", "", texto, flags=re.MULTILINE).strip()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass
    inicio = texto.find("{")
    if inicio != -1:
        texto = texto[inicio:]
    reparado = repair_json(texto, return_objects=True)
    if isinstance(reparado, dict):
        return reparado
    raise ValueError("El modelo no devolvio JSON interpretable.")


def clasificar(texto_doc: str, candidatos: dict, imagenes: list[dict]) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta ANTHROPIC_API_KEY. Copia .env.example a .env y coloca tu token."
        )

    client = anthropic.Anthropic(api_key=api_key)

    respuesta = client.messages.create(
        model=MODELO,
        max_tokens=MAX_TOKENS,
        system=construir_system_prompt(),
        messages=[{
            "role": "user",
            "content": _contenido_usuario(texto_doc, candidatos, imagenes),
        }],
    )

    texto = "".join(b.text for b in respuesta.content if b.type == "text")
    datos = _extraer_json(texto)
    datos["_uso"] = {
        "modelo": MODELO,
        "tokens_entrada": respuesta.usage.input_tokens,
        "tokens_salida": respuesta.usage.output_tokens,
    }
    return datos
