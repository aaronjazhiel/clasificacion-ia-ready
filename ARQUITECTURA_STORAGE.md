# Arquitectura de Storage — Project Knowledge Hub
## Tecnológico de Monterrey · Gobernanza de Aplicativos · VPAF · OmniSys

---

## 1. Propósito

Este documento define la estructura de almacenamiento en **Azure Blob Storage** donde viven los activos de conocimiento del Project Knowledge Hub (PKH), sus metadatos y los índices para búsqueda semántica.

El objetivo es que cualquier solución RAG, copiloto o agente que consuma este storage encuentre únicamente activos aprobados, con metadatos completos y trazabilidad verificada — nunca borradores, nunca activos obsoletos, nunca datos restringidos.

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
│                     CONSULTA                                │
│                                                             │
│  Usuario (Teams / App web)                                  │
│         │                                                   │
│         ▼                                                   │
│  Copilot Studio                                             │
│         │                                                   │
│         ▼                                                   │
│  Azure AI Search  ←──── búsqueda híbrida (vector + keyword) │
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

## 3. Estructura de contenedores

```
azure-blob-storage/
│
├── raw/                          # Documentos originales sin procesar
│   └── {proyecto-id}/
│       └── {año-mes}/
│           └── {ID-ACTIVO}_nombre-documento.docx
│
├── curated/                      # Activos aprobados — única fuente del RAG
│   └── {proyecto-id}/
│       └── {ID-ACTIVO}/
│           ├── documento.docx    # Archivo original
│           ├── metadata.json     # Ficha PKH completa (generada por esta POC)
│           └── chunks/           # Fragmentos listos para indexar
│               ├── chunk_001.json
│               ├── chunk_002.json
│               └── ...
│
├── metadata/                     # Índice central por proyecto
│   └── {proyecto-id}/
│       ├── catalogo.json         # Todos los activos registrados (equivale a KH2)
│       ├── trazabilidad.json     # Relaciones entre activos
│       └── taxonomy.json         # Taxonomía vigente del proyecto
│
├── indexes/                      # Insumos para Azure AI Search
│   └── {proyecto-id}/
│       ├── search-index.json     # Definición del índice
│       └── embeddings/
│           └── {ID-ACTIVO}.json  # Vector del activo
│
└── archive/                      # Activos obsoletos — excluidos del índice
    └── {proyecto-id}/
        └── {ID-ACTIVO}/
            ├── documento.docx
            └── metadata.json
```

---

## 4. Convención de nombres

| Elemento | Formato | Ejemplo |
|---|---|---|
| proyecto-id | kebab-case, sin espacios | `gobernanza-vpaf` |
| ID de activo | prefijo PKH + 3 dígitos | `ENT-001`, `REQ-004` |
| Carpeta de activo | igual al ID | `ENT-001/` |
| Archivo de metadatos | siempre `metadata.json` | `curated/gobernanza-vpaf/ENT-001/metadata.json` |
| Chunks | `chunk_NNN.json` con 3 dígitos | `chunk_001.json` |

---

## 5. Esquema del metadata.json

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
  "blob_path": "curated/gobernanza-vpaf/ENT-001/documento.docx",
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

## 6. Esquema del chunk

Cada fragmento en `chunks/` incluye el texto y los metadatos necesarios para que Azure AI Search lo recupere con contexto:

```json
{
  "chunk_id": "ENT-001_001",
  "activo_id": "ENT-001",
  "proyecto_id": "gobernanza-vpaf",
  "tipo": "Entregable",
  "estado": "Aprobado",
  "confidencialidad": "Interna",
  "fase": "Fase 1",
  "responsable": "Architect",
  "fecha": "2026-07-15",
  "dominio": "Gobernanza de Aplicativos",
  "texto": "El modelo operativo define los 9 pilares de gobierno...",
  "blob_path": "curated/gobernanza-vpaf/ENT-001/documento.docx",
  "posicion": 1,
  "total_chunks": 5
}
```

---

## 7. Reglas de gobierno del storage

| Regla | Detalle |
|---|---|
| `raw/` nunca se indexa | Los documentos sin clasificar no llegan al RAG |
| Solo `curated/` alimenta Azure AI Search | El estado del activo debe ser `Aprobado` o `Publicado` |
| El ID del activo es la carpeta | Nunca cambia aunque cambie el nombre del documento |
| `Restringida` nunca va a `indexes/` | Activos con datos de menores o sensibles quedan fuera del índice sin excepción |
| `archive/` se excluye del índice | Los activos `Obsoletos` no deben recuperarse como vigentes |
| Un activo no llega a `curated/` sin `metadata.json` completo | Sin responsable, fecha y evidencia no se mueve de `raw/` |

---

## 8. Flujo de vida de un activo

```
Documento .docx
      │
      ▼
  raw/{proyecto}/{año-mes}/          ← Se deposita al recibirse
      │
      ▼
  Clasificador IA-Ready (esta POC)   ← Genera metadata.json
      │
      ▼
  Validación humana (human-in-the-loop)
      │
      ├── Pendiente → se queda en raw/
      │
      └── Aprobado
            │
            ▼
        curated/{proyecto}/{ID}/     ← documento.docx + metadata.json
            │
            ▼
        Chunking + Embeddings        ← Azure OpenAI
            │
            ▼
        indexes/{proyecto}/          ← Azure AI Search
            │
            ▼
        RAG · Copiloto · Agentes · Teams
```

---

## 9. Estructura de proyecto de ejemplo

Para el proyecto `gobernanza-vpaf` con tres activos registrados:

```
curated/
└── gobernanza-vpaf/
    ├── ENT-001/
    │   ├── documento.docx
    │   ├── metadata.json
    │   └── chunks/
    │       ├── chunk_001.json
    │       └── chunk_002.json
    ├── REQ-004/
    │   ├── documento.docx
    │   ├── metadata.json
    │   └── chunks/
    │       └── chunk_001.json
    └── DEC-002/
        ├── documento.docx
        ├── metadata.json
        └── chunks/
            ├── chunk_001.json
            └── chunk_002.json

metadata/
└── gobernanza-vpaf/
    ├── catalogo.json
    ├── trazabilidad.json
    └── taxonomy.json
```

---

## 10. Próximos pasos

| Paso | Qué hacer |
|---|---|
| 1 | Crear el Azure Blob Storage con los contenedores `raw`, `curated`, `metadata`, `indexes`, `archive` |
| 2 | Conectar el clasificador IA-Ready para que al validar un activo lo escriba directo en `curated/` |
| 3 | Implementar el pipeline de chunking sobre `curated/` |
| 4 | Crear el índice en Azure AI Search con el esquema del chunk (sección 6) |
| 5 | Conectar el índice a Copilot Studio o la app de consulta |
