# Cómo usa Claude el Clasificador IA-Ready

**Tecnológico de Monterrey · Gobernanza de Aplicativos · VPAF · OmniSys**  
Versión 1.0 · Junio 2025

---

## 1. Visión general

Claude no clasifica el documento solo. El sistema lo usa como **capa semántica** dentro de un pipeline de tres etapas donde el código hace primero todo lo que puede hacer con reglas, y solo entonces le pasa el trabajo a la IA.

```
Documento
    │
    ▼
┌─────────────────────────────────────────┐
│  ETAPA 1 · Parser (código puro)         │
│  Extrae texto, tablas, propiedades      │
│  Detecta 5 campos con regex             │
└──────────────┬──────────────────────────┘
               │  texto estructurado
               │  + candidatos con evidencia
               ▼
┌─────────────────────────────────────────┐
│  ETAPA 2 · Claude (IA semántica)        │
│  Interpreta, clasifica, resume          │
│  Devuelve JSON con 14 campos            │
└──────────────┬──────────────────────────┘
               │  JSON crudo
               ▼
┌─────────────────────────────────────────┐
│  ETAPA 3 · Validador (código puro)      │
│  Verifica catálogos, aplica arbitraje   │
│  Calcula confianza final                │
└─────────────────────────────────────────┘
               │
               ▼
         metadata.json
```

---

## 2. Qué le pasamos a Claude

En cada llamada se envían exactamente **tres bloques** a la API de Anthropic.

---

### Bloque 1 — System prompt (instrucciones fijas)

Se genera dinámicamente desde `taxonomy.py` en cada arranque del servidor. Nunca está escrito a mano con los catálogos copiados: si se agrega una categoría nueva a la taxonomía, el prompt se actualiza solo.

Contiene cuatro secciones:

**a) Contexto institucional**

```
Estás analizando documentación del Project Knowledge Hub (PKH)
del Tecnológico de Monterrey, proyecto de Gobernanza de
Aplicativos · VPAF · OmniSys.

Las 12 categorías del PKH y sus prefijos:
  ENT Entregable · REQ Requerimiento · DEC Decisión · RSG Riesgo
  SUP Supuesto · EVI Evidencia · CRA Criterio de aceptación
  CMP Componente · PRO Proceso · RES Responsable
  DEP Dependencia · LEC Lección aprendida
```

**b) La regla central: dos clases de atributo**

Esta es la instrucción más importante del sistema. Le dice a Claude qué puede inferir y qué solo puede leer:

```
A) ATRIBUTOS INTERPRETABLES
   → tipo, tipo_activo, descripcion, contexto, relaciones,
     trazabilidad, fuente
   Puedes deducirlos leyendo el documento aunque no estén
   escritos de forma literal.

B) ATRIBUTOS DECLARATIVOS
   → version, estado, responsable, fecha, confidencialidad
   Solo puedes llenarlos si el valor aparece ESCRITO en el
   documento. Si no aparece: "No identificado".
   NUNCA los deduzcas por el tono o el aspecto del documento.
   Un documento bien formateado NO significa que esté aprobado.
```

**c) Los catálogos controlados**

Claude solo puede devolver valores que estén en estas listas. Si inventa uno, el validador lo rechaza y aplica el fallback.

```
tipo:
  - Entregable · Requerimiento · Decisión · Riesgo · Supuesto
  - Evidencia · Criterio de aceptación · Componente · Proceso
  - Responsable · Dependencia · Lección aprendida

estado:
  - Borrador · En revisión · Aprobado · Publicado · Obsoleto
  - No identificado

confidencialidad:
  - Pública · Interna · Confidencial · Restringida
  - No identificado

relaciones[].tipo:
  - deriva de · satisface · tiene evidencia · depende de
  - reemplaza · se relaciona con
```

**d) El esquema JSON exacto que debe devolver**

```json
{
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
  "contexto": {
    "contexto_funcional": "",
    "contexto_tecnico": "",
    "dominio": "",
    "sistemas_involucrados": "",
    "proceso_relacionado": ""
  },
  "relaciones": [{"tipo": "", "nombre": ""}],
  "trazabilidad": "",
  "evidencias": {"campo": {"metodo": "", "origen": "", "cita": ""}},
  "confianza": {"tipo": 0, "estado": 0, "responsable": 0, ...},
  "observaciones": []
}
```

---

### Bloque 2 — Candidatos deterministas

Antes del documento, el prompt incluye lo que el parser ya encontró con expresiones regulares. Claude los recibe como hechos verificados y los usa como punto de partida.

**Ejemplo cuando el parser encontró valores:**
```
DETECCIÓN DETERMINISTA PREVIA (reglas del analizador,
ya verificadas contra el archivo):
  - version: '2.1'     (origen: portada, método: extraido)
  - estado: 'Borrador' (origen: encabezado/pie, método: extraido)
  - fecha: '2024-03-15' (origen: portada, método: extraido)

Usa estos valores salvo que el contenido los contradiga.
Si los contradices, explica por qué en observaciones.
```

**Ejemplo cuando el parser no encontró nada:**
```
DETECCIÓN DETERMINISTA PREVIA: el analizador no encontró
marcas explícitas de versión, fecha, responsable, estado
ni confidencialidad. Trata esos campos como no identificados
salvo que los veas literalmente en el contenido.
```

---

### Bloque 3 — El documento completo

El texto del archivo serializado con estructura explícita:

```
NOMBRE DEL ARCHIVO: Acta_Reunion_Kickoff_v1.docx

PROPIEDADES DEL DOCUMENTO:
  - titulo: Acta de Reunión Kickoff
  - autor: Juan Pérez
  - modificado: 2024-03-15

ENCABEZADOS Y PIES DE PÁGINA:
  - BORRADOR | Gobernanza de Aplicativos | Tec de Monterrey

ESTRUCTURA DE SECCIONES:
  - Objetivo de la reunión
  - Participantes
    - Equipo OmniSys
    - Equipo TEC
  - Acuerdos y decisiones
  - Próximos pasos

CONTENIDO:
  [texto completo del documento...]

TABLA 1 (5 filas):
  | Acuerdo | Responsable | Fecha compromiso |
  | ...     | ...         | ...              |
```

Si el documento tiene imágenes (diagramas, arquitecturas, organigramas), se envían como bloques `image` en base64 con la instrucción de usarlas para enriquecer `tipo`, `contexto` y `relaciones`. Máximo 4 imágenes por documento, priorizando las de mayor tamaño. Imágenes menores a 12 KB se descartan (logos, viñetas).

Si el texto supera 45,000 caracteres se trunca simétricamente: primera mitad + última mitad, preservando portada y cierre del documento.

---

## 3. Qué le pedimos que haga

Claude resuelve exactamente lo que el código **no puede hacer con regex**: la interpretación semántica.

| Campo | Por qué necesita IA | Ejemplo |
|---|---|---|
| `tipo` | Requiere entender la función del documento, no su formato | Una minuta con decisiones → `Decisión`, no `Entregable` |
| `descripcion` | Requiere resumir el propósito en 1-3 oraciones | "Registra los acuerdos del kickoff del proyecto..." |
| `contexto` | Requiere identificar dominio, sistemas, proceso relacionado | `dominio: "Gestión de proyectos"` |
| `relaciones` | Requiere identificar entidades nombradas y su tipo de relación | `[{"tipo": "depende de", "nombre": "RFC-001"}]` |
| `trazabilidad` | Requiere citar secciones concretas que justifican la clasificación | "Clasificado como Decisión por la sección 'Acuerdos'..." |
| `fuente` | Requiere inferir el origen del conocimiento | `"Reunión de kickoff, equipo OmniSys-TEC"` |
| `tipo_activo` | Requiere entender el formato del activo | `"documento"`, `"diagrama"`, `"tabla"` |
| `confianza` | Requiere calibrar qué tan respaldado está cada valor | `{"tipo": 88, "estado": 20, "responsable": 95}` |
| `observaciones` | Requiere detectar vacíos, contradicciones o riesgos | `["No se identificó fecha documental"]` |

Los campos `version`, `estado`, `responsable`, `fecha`, `confidencialidad` **Claude no los infiere** — solo los copia si los ve escritos, o devuelve `"No identificado"`.

---

## 4. El flujo completo con un ejemplo real

Supongamos que se sube `Acta_Kickoff_v1.docx` con el encabezado `BORRADOR` y la línea `Elaborado por: Juan Pérez`.

### Paso 1 — El parser detecta con regex

```
candidatos = {
  "version":      {"valor": "1",        "evidencia": "nombre del archivo",   "metodo": "derivado"},
  "estado":       {"valor": "Borrador", "evidencia": "encabezado/pie",        "metodo": "extraido"},
  "responsable":  {"valor": "Juan Pérez","evidencia": "portada",              "metodo": "extraido"}
}
```

### Paso 2 — Claude recibe y clasifica

Claude lee el documento completo, ve los candidatos y devuelve:

```json
{
  "tipo": "Decisión",
  "tipo_activo": "documento",
  "fase": "Fase 1",
  "descripcion": "Registra los acuerdos y decisiones tomadas en la reunión de kickoff del proyecto de Gobernanza de Aplicativos.",
  "version": "1",
  "estado": "Borrador",
  "responsable": "Juan Pérez",
  "fecha": "No identificada",
  "fuente": "Reunión de kickoff, equipo OmniSys-TEC",
  "confidencialidad": "No identificado",
  "contexto": {
    "contexto_funcional": "Inicio formal del proyecto de gobernanza",
    "contexto_tecnico": "No identificado",
    "dominio": "Gestión de proyectos",
    "sistemas_involucrados": "No identificado",
    "proceso_relacionado": "Kickoff y planeación"
  },
  "relaciones": [
    {"tipo": "deriva de", "nombre": "Plan de proyecto VPAF"}
  ],
  "trazabilidad": "Clasificado como Decisión por la sección 'Acuerdos y decisiones'. Estado Borrador confirmado por encabezado. Responsable extraído de la línea 'Elaborado por'.",
  "confianza": {
    "tipo": 82, "estado": 95, "responsable": 91,
    "fecha": 15, "confidencialidad": 20, "descripcion": 78
  },
  "observaciones": [
    "No se identificó fecha documental en el contenido.",
    "No hay marca explícita de confidencialidad; se aplicará 'Interna' por defecto del PKH."
  ]
}
```

### Paso 3 — El validador aplica el arbitraje

```
✓ estado = "Borrador"  → parser extrajo "Borrador" del encabezado,
                          Claude también dice "Borrador" → coinciden, se conserva

✓ responsable = "Juan Pérez" → parser extrajo de portada,
                                Claude confirma → confianza sube a 91

✓ confidencialidad = "No identificado" → sin evidencia literal,
                                          el validador lo deja como "No identificado"
                                          (no aplica el default "Interna" aquí,
                                          eso lo hace el RAG al indexar)

✓ confianza["fecha"] = 15 → campo sin valor → tope máximo 35 aplicado
```

### Resultado final

```json
{
  "id": "POC-ACT-X7K2",
  "tipo": "Decisión",
  "estado": "Borrador",
  "responsable": "Juan Pérez",
  "fecha": "No identificada",
  "confidencialidad": "No identificado",
  "requiere_revision": ["fecha", "confidencialidad", "id"],
  "niveles": {
    "tipo": "Alta",
    "estado": "Alta",
    "responsable": "Alta",
    "fecha": "Requiere revisión",
    "confidencialidad": "Requiere revisión"
  }
}
```

---

## 5. Lo que Claude NO hace

| Restricción | Razón |
|---|---|
| No inventa estados (`"Vigente"` si no está escrito) | Contaminaría el índice RAG con metadatos falsos |
| No deduce responsable por el tono formal del documento | Un documento bien redactado no implica autoría conocida |
| No asume confidencialidad por el contenido | Solo una leyenda explícita es evidencia válida |
| No genera IDs definitivos | El ID oficial lo asigna el PKH, no la IA |
| No persiste nada | El archivo temporal se borra en el `finally` |
| No indexa activos `Restringida` | Datos de menores o sensibles nunca llegan al RAG |

---

## 6. Por qué este diseño

El principio central es: **la IA amplifica, no reemplaza la evidencia documental**.

Si Claude pudiera inferir libremente `estado = "Aprobado"` porque el documento se ve formal, un borrador bien redactado entraría al índice como aprobado. Eso contamina el RAG y rompe la confianza del sistema.

La separación entre atributos interpretables y declarativos garantiza que:
- Lo que Claude clasifica (tipo, descripción, contexto) puede ser incorrecto sin consecuencias graves — el humano lo corrige en la validación.
- Lo que Claude no puede inventar (estado, responsable, fecha) son los campos que determinan si un activo es confiable para el RAG.

---

**OmniSys S.A. de C.V.** · Gobernanza de Aplicativos · VPAF · Tecnológico de Monterrey · uso interno del equipo
