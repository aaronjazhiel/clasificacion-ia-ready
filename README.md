# Clasificador de Activos de Conocimiento IA-Ready
## Tecnológico de Monterrey · Gobernanza de Aplicativos · VPAF · OmniSys

---

## ¿Qué es este repositorio?

Este repositorio es el **clasificador automático de activos de conocimiento** del
Project Knowledge Hub (PKH) del proyecto de Gobernanza de Aplicativos del
Tecnológico de Monterrey.

Su función es convertir cualquier documento Word del proyecto en un
**activo IA-ready**: una ficha estructurada con metadatos completos, trazabilidad
verificada y nivel de confianza calibrado, lista para ingresar al catálogo del PKH
y ser ingestada en el índice de búsqueda semántica (RAG) sobre Azure AI Search.

Sin este clasificador, un documento plano entra al índice sin contexto. Con él,
el RAG sabe qué es el documento, en qué fase se generó, quién responde por él,
qué tan vigente está y con qué otros activos se relaciona — y puede filtrar por
todo eso antes de recuperarlo.

---

## Lugar en la arquitectura del PKH

```
Documento .docx
      │
      ▼
┌─────────────────────────────────────┐
│   Clasificador IA-Ready (este repo) │
│                                     │
│   1. Extracción determinista        │  ← reglas antes que IA
│   2. Análisis semántico con Claude  │  ← 12 categorías PKH
│   3. Arbitraje y confianza          │  ← texto gana sobre inferencia
│   4. Validación humana              │  ← human-in-the-loop
└─────────────────────────────────────┘
      │
      ▼
  metadata.json  ←─── ficha PKH completa
      │
      ▼
┌─────────────────────────────────────┐
│   Azure Blob Storage                │
│   curated/{proyecto}/{ID-ACTIVO}/   │
│   ├── documento.docx                │
│   ├── metadata.json                 │
│   └── chunks/                       │
└─────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────┐
│   Azure AI Search                   │  ← búsqueda híbrida
│   + Azure OpenAI Embeddings         │  ← vectorización
└─────────────────────────────────────┘
      │
      ▼
  RAG · Copilot Studio · Teams · Agentes
```

---

## Qué produce

Por cada documento analizado genera un `metadata.json` con las 7 capas del
modelo de metadatos del PKH:

| Capa | Campos | Cómo se obtiene |
|---|---|---|
| Identidad | `id`, `version`, `fecha`, `fase` | Extraído del texto o derivado del archivo |
| Naturaleza | `tipo`, `tipo_activo` | Inferido por Claude dentro del catálogo PKH |
| Semántica | `descripcion`, `contexto` | Inferido por Claude |
| Gobierno | `estado`, `responsable`, `confidencialidad` | Solo si aparece escrito — nunca inferido |
| Procedencia | `fuente` | Extraído o inferido |
| Grafo | `relaciones` | Extraído o inferido — tipos del modelo PKH |
| Calidad | `trazabilidad`, `confianza`, `observaciones` | Calculado por el validador |

---

## Taxonomía del PKH integrada

El clasificador usa exactamente los catálogos definidos en
`OmniSys_KH2_Plantilla_Metadatos_Taxonomia_Trazabilidad.xlsx`:

**12 categorías de activos**

| Prefijo | Categoría |
|---|---|
| ENT | Entregable |
| REQ | Requerimiento |
| DEC | Decisión |
| RSG | Riesgo |
| SUP | Supuesto |
| EVI | Evidencia |
| CRA | Criterio de aceptación |
| CMP | Componente |
| PRO | Proceso |
| RES | Responsable |
| DEP | Dependencia |
| LEC | Lección aprendida |

**Estados del ciclo de vida:** Borrador · En revisión · Aprobado · Publicado · Obsoleto

**Confidencialidad:** Pública · Interna _(default)_ · Confidencial · Restringida

**Tipos de relación:** deriva de · satisface · tiene evidencia · depende de · reemplaza · se relaciona con

---

## Reglas que garantizan calidad para el RAG

Estas reglas se aplican con código, no solo con instrucciones al modelo:

1. **Campos declarativos nunca se infieren** — `estado`, `responsable`, `fecha`,
   `version` y `confidencialidad` solo se llenan si el valor aparece escrito en
   el documento. Si no aparece: `"No identificado"`.

2. **El texto gana sobre la IA** — si el analizador detectó `"BORRADOR"` en el
   documento y Claude dice `"Aprobado"`, gana el documento. Un activo mal
   clasificado contamina el índice.

3. **Confianza calibrada** — un campo sin valor nunca reporta confianza alta.
   Una pista derivada (propiedades de Word) se topa en 69 para que caiga en
   "requiere revisión".

4. **Restringida nunca llega al RAG** — activos con datos de menores o sensibles
   quedan marcados y no se indexan.

5. **Sin responsable + fuente + evidencia → no es Aprobado** — coherente con la
   regla de oro del PKH.

---

## Arquitectura del código

```
/poc-ia-ready
    /app
        main.py               FastAPI · endpoints · ciclo de vida del temporal
        taxonomy.py           catálogos PKH y contrato por atributo
        document_parser.py    extracción .docx + reglas deterministas
        claude_service.py     prompt generado desde taxonomy + llamada API
        metadata_validator.py arbitraje · catálogos · confianza
        models.py             contratos Pydantic de entrada/salida
    /templates/index.html
    /static/styles.css, app.js
    .env.example
    requirements.txt
    render.yaml
    ARQUITECTURA_STORAGE.md   estructura Azure Blob Storage + servicios
```

`taxonomy.py` es la fuente única de verdad: se inyecta al prompt de Claude
y se usa para validar su respuesta. Agregar una categoría nueva se hace en
un solo archivo y se propaga solo.

---

## Instalación local

Requiere Python 3.11.

```bash
cd poc-ia-ready
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edita .env y coloca tu ANTHROPIC_API_KEY
uvicorn app.main:app --reload --port 8000
```

Abre http://localhost:8000.

---

## Endpoints

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/` | Pantalla principal |
| GET | `/api/taxonomy` | Catálogos PKH para el formulario |
| POST | `/api/analyze` | Recibe .docx · extrae · clasifica · devuelve JSON |
| POST | `/api/validate` | Cierra el ciclo human-in-the-loop |

---

## Seguridad

- El documento se escribe en un `NamedTemporaryFile` y se elimina en un `finally`.
- Validación de extensión, MIME y firma del archivo (`PK`).
- `.docm` rechazado — no se procesan macros.
- Activos `Restringida` nunca se envían al índice.
- Los logs registran duración y conteos. No registran contenido ni tokens.

---

## Próximo paso

Con el `metadata.json` validado, el activo está listo para:

1. Escribirse en `curated/{proyecto}/{ID}/` en Azure Blob Storage
2. Fragmentarse en chunks con contexto heredado de los metadatos
3. Vectorizarse con Azure OpenAI Embeddings
4. Indexarse en Azure AI Search con filtros por `estado`, `confidencialidad`,
   `fase`, `tipo` y `proyecto`
5. Ser consultado desde Copilot Studio o Microsoft Teams

Ver `ARQUITECTURA_STORAGE.md` para la estructura completa.

---

**OmniSys S.A. de C.V.** · Gobernanza de Aplicativos · VPAF · Tecnológico de Monterrey · uso interno del equipo
