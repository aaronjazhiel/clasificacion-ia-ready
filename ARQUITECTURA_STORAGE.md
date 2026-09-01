# Repositorio IA-Ready — Project Knowledge Hub
## Tecnológico de Monterrey · Gobernanza de Aplicativos · VPAF · OmniSys

---

## 1. Propósito

Este documento define el **Repositorio IA-Ready**: la estructura de carpetas en **Azure Blob Storage** donde se almacenan los activos de conocimiento del PKH, el punto donde se insertan los metadatos generados por el clasificador y el origen desde el cual los usuarios del equipo consultan el conocimiento del proyecto directamente desde **Microsoft Teams**.

El repositorio garantiza que Teams (vía Copilot Studio) encuentre únicamente activos aprobados, con metadatos completos y trazabilidad verificada — nunca borradores, nunca activos obsoletos, nunca datos restringidos.

---

## 2. Tecnología recomendada

| Componente | Servicio Azure | Para qué |
|---|---|---|
| Archivos y metadatos | Azure Blob Storage | Guardar .docx, JSON de metadatos y chunks |
| Búsqueda semántica | Azure AI Search | Índice vectorial + búsqueda híbrida |
| Embeddings | Azure OpenAI (text-embedding-3-large) | Vectorizar chunks para RAG |
| Orquestación RAG | Azure AI Foundry | Pipeline de ingestión, chunking y consulta |
| Modelo de lenguaje | Azure OpenAI (GPT-4o) | Generación de respuestas del copiloto |
| Identidad y acceso | Azure Active Directory (Entra ID) | Control de acceso por rol (RBAC) |
| Copiloto conversacional | Copilot Studio | Interfaz de consulta para usuarios del Tec |
| Integración Teams | Microsoft Teams + Power Platform | Canal de consumo para el equipo del proyecto |
| Monitoreo | Azure Monitor + App Insights | Logs, trazas y alertas del pipeline |
| Secretos y llaves | Azure Key Vault | Guardar API keys y connection strings |
| CI/CD del pipeline | Azure DevOps | Automatizar ingestión y reindexado |

---

## 3. Diagrama de servicios

```
┌─────────────────────────────────────────────────────────────┐
│                     INGESTIÓN                               │
│                                                             │
│  Clasificador IA-Ready (esta POC)                           │
│         │                                                   │
│         ▼                                                   │
│  Azure Blob Storage                                         │
│  ├── raw/          ← documentos sin clasificar              │
│  ├── curated/      ← activos aprobados + metadata.json      │
│  ├── metadata/     ← catálogo y trazabilidad del proyecto   │
│  ├── indexes/      ← embeddings y definición del índice     │
│  └── archive/      ← activos obsoletos                      │
│         │                                                   │
│         ▼                                                   │
│  Azure AI Foundry                                           │
│  ├── Chunking de documentos                                 │
│  ├── Azure OpenAI Embeddings (text-embedding-3-large)       │
│  └── Escritura en Azure AI Search                           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                     CONSULTA DESDE TEAMS                    │
│                                                             │
│  Usuario pregunta en Microsoft Teams                        │
│         │                                                   │
│         ▼                                                   │
│  Copilot Studio (bot integrado al canal de Teams)           │
│         │                                                   │
│         ▼                                                   │
│  Azure AI Search  ←──── búsqueda híbrida (vector + keyword) │
│  filtros: dominio · tipo · estado · fase · confidencialidad │
│         │                                                   │
│         ▼                                                   │
│  Azure OpenAI GPT-4o  ←── genera respuesta con contexto     │
│         │                                                   │
│         ▼                                                   │
│  Respuesta con fuente, ID de activo y nivel de confianza    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                  GOBIERNO Y SEGURIDAD                       │
│                                                             │
│  Azure Entra ID  ── RBAC por rol (Architect, AI Ops, etc.)  │
│  Azure Key Vault ── API keys, connection strings            │
│  Azure Monitor   ── logs del pipeline y del copiloto        │
│  Azure DevOps    ── CI/CD para reindexado automático        │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. ¿Cómo se determina el dominio de destino?

El clasificador IA-Ready usa la **Opción C: inferencia + confirmación humana**:

1. Claude analiza el contenido del documento y extrae `contexto.dominio` durante el ETL
2. El dominio inferido aparece en la ficha de validación — el usuario lo ve antes de aprobar
3. Si el dominio es correcto, el usuario aprueba sin cambiar nada
4. Si el dominio es incorrecto, el usuario lo corrige en la misma ficha antes de aprobar
5. El dominio confirmado (inferido o corregido) determina la carpeta de destino en Blob Storage: `curated/{dominio}/{proyecto}/{ID}/`

Esto garantiza que el flujo no se interrumpe en casos claros, pero siempre hay supervisión humana antes de que el activo entre al repositorio.

---

## 5. Estructura de contenedores

El Tec de Monterrey tiene documentos de múltiples dominios (procesos, gobierno de datos, tecnología, integraciones, etc.) que son transversales a proyectos. Por eso la estructura agrega un nivel de `{dominio}/` antes del `{proyecto-id}/`, lo que permite filtrar y gobernar por dominio sin mezclar activos de naturaleza distinta.

```
azure-blob-storage/
│
├── raw/                                   # Documentos originales sin procesar
│   └── {dominio}/
│       └── {proyecto-id}/
│           └── {año-mes}/
│               └── {ID-ACTIVO}_nombre-documento.docx
│
├── curated/                               # Activos aprobados — única fuente del RAG
│   └── {dominio}/
│       └── {proyecto-id}/
│           └── {ID-ACTIVO}/
│               ├── documento.docx         # Archivo original
│               ├── metadata.json          # Ficha PKH completa (generada por esta POC)
│               └── chunks/               # Fragmentos listos para indexar
│                   ├── chunk_001.json
│                   ├── chunk_002.json
│                   └── ...
│
├── metadata/                              # Índice central por dominio y proyecto
│   └── {dominio}/
│       └── {proyecto-id}/
│           ├── catalogo.json             # Todos los activos registrados (equivale a KH2)
│           ├── trazabilidad.json         # Relaciones entre activos
│           └── taxonomy.json            # Taxonomía vigente del proyecto
│
├── indexes/                              # Insumos para Azure AI Search
│   └── {dominio}/
│       └── {proyecto-id}/
│           ├── search-index.json         # Definición del índice
│           └── embeddings/
│               └── {ID-ACTIVO}.json     # Vector del activo
│
└── archive/                              # Activos obsoletos — excluidos del índice
    └── {dominio}/
        └── {proyecto-id}/
            └── {ID-ACTIVO}/
                ├── documento.docx
                └── metadata.json
```

### Dominios del Tec de Monterrey

| Dominio (carpeta) | Qué contiene |
|---|---|
| `gobierno-aplicativos` | Procesos de alta/baja, modelo operativo, gobernanza VPAF |
| `gobierno-datos` | Políticas de datos, catálogos, lineamientos de calidad |
| `gobierno-integraciones` | Arquitectura de integraciones, APIs, contratos de servicio |
| `tecnologia` | Estándares técnicos, arquitectura de referencia, decisiones tecnológicas |
| `procesos` | Procesos institucionales, procedimientos, manuales operativos |
| `seguridad` | Políticas de seguridad, controles, evidencias de cumplimiento |

---

## 5. Convención de nombres

| Elemento | Formato | Ejemplo |
|---|---|---|
| dominio | kebab-case, sin espacios | `gobierno-datos` |
| proyecto-id | kebab-case, sin espacios | `gobernanza-vpaf` |
| ID de activo | prefijo PKH + 3 dígitos | `ENT-001`, `REQ-004` |
| Carpeta de activo | igual al ID | `ENT-001/` |
| Archivo de metadatos | siempre `metadata.json` | `curated/gobierno-aplicativos/gobernanza-vpaf/ENT-001/metadata.json` |
| Chunks | `chunk_NNN.json` con 3 dígitos | `chunk_001.json` |

---

## 6. Ventajas del Repositorio IA-Ready

**Para el RAG y la búsqueda**
- Cada activo llega al índice con metadatos completos extraídos en el ETL — el modelo no necesita inferir qué es el documento ni de qué fase es, ya lo sabe antes de buscar.
- Los filtros por `dominio`, `tipo`, `estado`, `fase` y `confidencialidad` acotan el universo antes del vector search, lo que reduce ruido y mejora la precisión de las respuestas.
- `Restringida` nunca llega al índice — la exclusión es estructural, no depende de una instrucción al modelo.

**Para el gobierno del conocimiento**
- Un documento sin `metadata.json` completo no puede entrar a `curated/` — la calidad es un requisito de entrada, no una revisión posterior.
- El ID del activo es la carpeta: aunque el documento cambie de nombre o versión, la ruta en el repositorio no cambia y las relaciones entre activos se mantienen.
- `archive/` separa físicamente los activos obsoletos — nunca compiten con los vigentes en el índice.

**Para el Tec de Monterrey específicamente**
- El nivel de `{dominio}/` permite que gobierno de datos, gobierno de integraciones, tecnología y procesos coexistan en el mismo storage sin mezclarse.
- Un mismo activo puede relacionarse con activos de otro dominio (ej. un proceso que `depende de` una decisión tecnológica) sin mover archivos — la relación vive en el `metadata.json`.
- El catálogo por dominio (`catalogo.json`) es el equivalente digital del KH2 del Tec, siempre actualizado y consultable por máquina.

**Para el equipo**
- El copiloto en Teams responde con fuente (`blob_path`) e ID de activo — el usuario sabe exactamente qué documento respalda la respuesta.
- El nivel de confianza del ETL viaja con el chunk: si un campo fue inferido con baja confianza, el copiloto puede advertirlo.

---

## 7. Esquema del metadata.json

Cada activo en `curated/` tiene un `metadata.json` con la ficha completa generada por el clasificador IA-Ready:

```json
{
  "id": "ENT-001",
  "tipo": "Entregable",
  "tipo_activo": "documento",
  "fase": "Fase 1",
  "version": "v1.0",
  "estado": "Aprobado",
  "responsable": "Architect",
  "fecha": "2026-07-15",
  "confidencialidad": "Interna",
  "fuente": "Taller de diseño 15-jul",
  "descripcion": "Modelo operativo de gobernanza de aplicativos para el proyecto VPAF.",
  "contexto": {
    "contexto_funcional": "Gobierno de aplicativos críticos del Tec",
    "contexto_tecnico": "Integración con herramienta APM",
    "dominio": "Gobernanza de Aplicativos",
    "sistemas_involucrados": "APM, Portal DHTI, OmniSys",
    "proceso_relacionado": "Proceso de alta y baja de aplicativos"
  },
  "relaciones": [
    { "tipo": "satisface", "nombre": "REQ-004" },
    { "tipo": "tiene evidencia", "nombre": "EVI-010" },
    { "tipo": "deriva de", "nombre": "DEC-002" }
  ],
  "blob_path": "curated/gobierno-aplicativos/gobernanza-vpaf/ENT-001/documento.docx",
  "confianza": {
    "tipo": 95,
    "estado": 90,
    "responsable": 88,
    "fecha": 92,
    "confidencialidad": 85
  },
  "trazabilidad": "Clasificado desde sección 1 y tabla de control de versiones del documento.",
  "observaciones": []
}
```

---

## 8. Esquema del chunk

Cada fragmento en `chunks/` incluye el texto y los metadatos necesarios para que Azure AI Search lo recupere con contexto:

```json
{
  "chunk_id": "ENT-001_001",
  "activo_id": "ENT-001",
  "dominio": "gobierno-aplicativos",
  "proyecto_id": "gobernanza-vpaf",
  "tipo": "Entregable",
  "estado": "Aprobado",
  "confidencialidad": "Interna",
  "fase": "Fase 1",
  "responsable": "Architect",
  "fecha": "2026-07-15",
  "dominio_semantico": "Gobernanza de Aplicativos",
  "texto": "El modelo operativo define los 9 pilares de gobierno...",
  "blob_path": "curated/gobierno-aplicativos/gobernanza-vpaf/ENT-001/documento.docx",
  "posicion": 1,
  "total_chunks": 5
}
```

---

## 9. Ejemplos de preguntas y cómo los metadatos del ETL las resuelven

Estos son ejemplos reales de preguntas que un usuario del Tec haría en Teams y cómo el repositorio las resuelve usando los metadatos extraídos en el ETL.

---

**"¿Cuál es el proceso aprobado para dar de alta un aplicativo en el Tec?"**

```
Filtros aplicados:
  dominio       = "gobierno-aplicativos"
  tipo          = "Proceso"
  estado        = "Aprobado"

Vector search sobre: "alta de aplicativo proceso pasos"

Resultado: PRO-003 · "Proceso de alta y baja de aplicativos" · Fase 2 · Aprobado
Fuente: curated/gobierno-aplicativos/gobernanza-vpaf/PRO-003/documento.docx
```

---

**"¿Qué decisiones tecnológicas se tomaron en la Fase 1 del proyecto?"**

```
Filtros aplicados:
  dominio       = "tecnologia"
  tipo          = "Decisión"
  fase          = "Fase 1"
  estado        IN ["Aprobado", "Publicado"]

Vector search sobre: "decisión tecnológica arquitectura"

Resultados: DEC-001, DEC-002, DEC-005 · ordenados por fecha desc
```

---

**"¿Qué requerimientos están pendientes de aprobación en gobierno de datos?"**

```
Filtros aplicados:
  dominio       = "gobierno-datos"
  tipo          = "Requerimiento"
  estado        = "En revisión"

Vector search sobre: "requerimiento pendiente aprobación"

Resultados: REQ-012, REQ-015 · con responsable y fecha de última modificación
```

---

**"¿Qué evidencias respaldan el entregable ENT-001?"**

```
Filtros aplicados:
  activo_id     = "ENT-001"   (o relaciones.tipo = "tiene evidencia")

Sin vector search — consulta directa al grafo de relaciones del metadata.json

Resultado: EVI-010 · "Acta de aprobación taller 15-jul" · Aprobado
```

---

**"¿Cuáles son los riesgos activos en el proyecto de integraciones?"**

```
Filtros aplicados:
  dominio       = "gobierno-integraciones"
  tipo          = "Riesgo"
  estado        IN ["Borrador", "En revisión", "Aprobado"]

Vector search sobre: "riesgo activo mitigación"

Resultados: RSG-004, RSG-007 · con responsable y fase
```

---

**"¿Qué lecciones aprendidas hay sobre el proceso de gobierno de datos?"**

```
Filtros aplicados:
  dominio       = "gobierno-datos"
  tipo          = "Lección aprendida"
  estado        IN ["Aprobado", "Publicado"]

Vector search sobre: "lección aprendida mejora proceso datos"

Resultados: LEC-002, LEC-006 · con contexto_funcional y fecha
```

---

## 10. Reglas de gobierno del storage

| Regla | Detalle |
|---|---|
| `raw/` nunca se indexa | Los documentos sin clasificar no llegan al RAG |
| Solo `curated/` alimenta Azure AI Search | El estado del activo debe ser `Aprobado` o `Publicado` |
| El ID del activo es la carpeta | Nunca cambia aunque cambie el nombre del documento |
| `Restringida` nunca va a `indexes/` | Activos con datos de menores o sensibles quedan fuera del índice sin excepción |
| `archive/` se excluye del índice | Los activos `Obsoletos` no deben recuperarse como vigentes |
| Un activo no llega a `curated/` sin `metadata.json` completo | Sin responsable, fecha y evidencia no se mueve de `raw/` |

---

## 11. Flujo de vida de un activo

```
Documento .docx
      │
      ▼
  raw/{dominio}/{proyecto}/{año-mes}/    ← Se deposita al recibirse
      │
      ▼
  Clasificador IA-Ready (esta POC)       ← ETL: extrae y genera metadata.json
      │
      ▼
  Validación humana (human-in-the-loop)
      │
      ├── Pendiente → se queda en raw/
      │
      └── Aprobado
            │
            ▼
        curated/{dominio}/{proyecto}/{ID}/   ← documento.docx + metadata.json
            │
            ▼
        Chunking + Embeddings               ← Azure OpenAI
            │
            ▼
        indexes/{dominio}/{proyecto}/       ← Azure AI Search
            │
            ▼
        RAG · Copilot Studio · Teams
```

---

## 12. Estructura de ejemplo — Tec de Monterrey

```
curated/
├── gobierno-aplicativos/
│   └── gobernanza-vpaf/
│       ├── ENT-001/   ← Modelo operativo
│       ├── PRO-003/   ← Proceso de alta/baja de aplicativos
│       └── DEC-002/   ← Decisión de arquitectura APM
│
├── gobierno-datos/
│   └── gobernanza-vpaf/
│       ├── REQ-012/   ← Requerimiento de calidad de datos
│       └── LEC-002/   ← Lección aprendida sobre catálogo
│
├── gobierno-integraciones/
│   └── gobernanza-vpaf/
│       ├── RSG-004/   ← Riesgo de integración con Portal DHTI
│       └── DEC-005/   ← Decisión de contrato de API
│
└── tecnologia/
    └── gobernanza-vpaf/
        ├── DEC-001/   ← Decisión de stack tecnológico
        └── CMP-008/   ← Componente OmniSys
```

---

## 13. Próximos pasos

| Paso | Qué hacer |
|---|---|
| 1 | Crear el Azure Blob Storage con los contenedores `raw`, `curated`, `metadata`, `indexes`, `archive` |
| 2 | Conectar el clasificador IA-Ready para que al validar un activo lo escriba directo en `curated/` |
| 3 | Implementar el pipeline de chunking sobre `curated/` |
| 4 | Crear el índice en Azure AI Search con el esquema del chunk (sección 8) |
| 5 | Conectar el índice a Copilot Studio y publicar el bot en el canal de Teams del proyecto |
