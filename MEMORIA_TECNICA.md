# Memoria Técnica — Clasificador de Activos de Conocimiento IA-Ready

**Tecnológico de Monterrey · Gobernanza de Aplicativos · VPAF · OmniSys**  
Versión 1.0 · Junio 2025

---

## 1. Propósito del artefacto

El clasificador convierte documentos del proyecto (Word, PDF, PowerPoint, imágenes, JSON) en **activos IA-ready**: fichas estructuradas con 14 campos de metadatos, trazabilidad verificada y nivel de confianza calibrado, listas para ingresar al catálogo del Project Knowledge Hub (PKH) y ser ingestadas en Azure AI Search para búsqueda semántica (RAG).

---

## 2. Arquitectura general

```
Documento subido por el usuario
        │
        ▼
┌─────────────────────────────────────────────────────┐
│  FastAPI  (main.py)                                 │
│  · Validación de extensión, MIME y firma de archivo │
│  · Escritura en NamedTemporaryFile                  │
│  · Eliminación garantizada en bloque finally        │
└──────────────┬──────────────────────────────────────┘
               │
       ┌───────▼─────────┐
       │ document_parser  │  Extracción determinista por formato
       └───────┬──────────┘
               │  parsed{}  +  candidatos{}
       ┌───────▼─────────┐
       │ claude_service   │  Prompt generado desde taxonomy.py → API Anthropic
       └───────┬──────────┘
               │  crudo{}
       ┌───────▼──────────────┐
       │ metadata_validator    │  Arbitraje · catálogos · confianza
       └───────┬───────────────┘
               │
        metadata.json  →  respuesta JSON al frontend
```

El sistema opera en **tres capas secuenciales** con responsabilidades estrictamente separadas.

---

## 3. Capa 1 — Extracción determinista (`document_parser.py`)

### 3.1 Parsers por formato

| Formato | Librería | Qué extrae |
|---|---|---|
| `.docx` | `python-docx` | Párrafos, tablas, títulos con nivel jerárquico, encabezados/pies, propiedades del archivo, imágenes embebidas |
| `.pdf` | `pdfplumber` | Texto línea a línea por página, tablas detectadas automáticamente |
| `.pptx` | `python-pptx` | Texto de cada forma por diapositiva, notas del presentador, imágenes |
| `.png/.jpg/.jpeg` | lectura binaria | Imagen completa en base64 para análisis visual por Claude |
| `.json` | stdlib `json` | Serialización completa del objeto como texto plano |

### 3.2 Detección determinista de candidatos

Antes de llamar al modelo, el parser aplica **reglas de expresiones regulares** para detectar 5 campos declarativos directamente del texto. Si el valor está escrito en el documento, no hace falta que la IA lo infiera.

**Versión** — busca en este orden de prioridad:
1. Patrón `versión: X.X` / `v1.3` en propiedades, encabezados, portada, tablas
2. Patrón `_v1.3` en el nombre del archivo
3. Propiedad `revision` de Word (solo si no es `"0"` o `"1"`)

**Fecha** — busca primero en el contenido (no en propiedades del archivo, porque una plantilla reutilizada arrastra la fecha de creación del archivo original):
1. Formato ISO `2024-03-15` en encabezados, portada, tablas
2. Formato texto `15 de marzo de 2024`
3. Solo como último recurso: propiedad `modified`/`created` de Word, marcada como `derivado`

**Responsable** — busca etiquetas explícitas:
- `responsable:`, `autor:`, `elaborado por:`, `aprobado por:`, `preparado por:`, `dueño:`
- Si no hay etiqueta, usa la propiedad `author` de Word, pero solo si no es un autor genérico (`python-docx`, `admin`, `usuario`, etc.)

**Estado** — busca marcas literales:

| Marca en el documento | Estado asignado |
|---|---|
| `borrador`, `draft`, `WIP` | Borrador |
| `en revisión`, `in review` | En revisión |
| `aprobado`, `approved`, `visto bueno` | Aprobado |
| `vigente`, `liberado` | Vigente |
| `obsoleto`, `deprecado` | Obsoleto |

**Confidencialidad** — busca leyendas explícitas:

| Leyenda en el documento | Nivel asignado |
|---|---|
| `público`, `public` | Pública |
| `uso interno`, `interno` | Interna |
| `confidencial` | Confidencial |
| `restringido`, `restricted`, `uso exclusivo` | Restringida |

Cada candidato detectado lleva tres atributos: `valor`, `evidencia` (de dónde se leyó) y `método` (`extraido` si viene del contenido, `derivado` si viene de propiedades del archivo).

### 3.3 Zonas de búsqueda y su prioridad

El parser busca en este orden de confiabilidad:

1. Propiedades del documento (metadatos de Word)
2. Encabezados y pies de página
3. Portada (primeros 25 párrafos)
4. Nombre del archivo
5. Primeras 3 tablas (hasta 12 filas cada una)

### 3.4 Bloque para el modelo

El texto que se envía a Claude se construye con estructura explícita: nombre del archivo, propiedades, encabezados/pies, estructura de secciones con niveles jerárquicos, contenido completo y tablas. Si supera 45,000 caracteres se trunca simétricamente (primera mitad + última mitad) para preservar portada y cierre.

---

## 4. Capa 2 — Análisis semántico con Claude (`claude_service.py`)

### 4.1 Generación dinámica del prompt

El system prompt **no está escrito a mano con los catálogos copiados**. Se genera en tiempo de ejecución desde `taxonomy.py`, lo que garantiza que agregar un nuevo tipo o estado en un solo archivo se propague automáticamente al prompt y a la validación.

### 4.2 Dos clases de atributo en el prompt

El prompt instruye a Claude a tratar los campos de forma radicalmente diferente según su naturaleza:

**Atributos interpretables** — `tipo`, `tipo_activo`, `descripcion`, `contexto`, `relaciones`, `trazabilidad`, `fuente`:  
Claude puede deducirlos leyendo el contenido aunque no estén escritos de forma literal.

**Atributos declarativos** — `version`, `estado`, `responsable`, `fecha`, `confidencialidad`:  
Claude solo puede llenarlos si el valor aparece **escrito** en el documento. Si no aparece, debe devolver `"No identificado"`. La instrucción es explícita: *"Un documento bien formateado NO significa que esté aprobado"*.

### 4.3 Bloque de candidatos deterministas

Antes del documento, el prompt incluye los candidatos detectados por el parser con su evidencia. Claude los usa como punto de partida pero puede contradecirlos si encuentra evidencia propia, en cuyo caso debe explicarlo en `observaciones`.

### 4.4 Análisis multimodal

Si el documento contiene imágenes (diagramas, arquitecturas, organigramas), se envían como bloques `image` en la API de Anthropic junto con una instrucción para usarlas en el enriquecimiento de `tipo`, `contexto` y `relaciones`. Imágenes decorativas o muy pequeñas (< 12 KB) se descartan antes de enviar. El límite es 4 imágenes por documento, priorizando las de mayor tamaño en bytes.

### 4.5 Reparación de JSON

La respuesta de Claude se parsea con `json.loads`. Si falla, se intenta extraer el bloque JSON con regex y se repara con la librería `json_repair` antes de lanzar error.

---

## 5. Capa 3 — Validación y arbitraje (`metadata_validator.py`)

Esta capa es la barrera de calidad. Recibe el JSON crudo del modelo y aplica cuatro operaciones en orden:

### 5.1 Normalización de forma

Garantiza que todos los campos existan en la salida aunque el modelo los haya omitido. Aplica los valores de fallback definidos en `taxonomy.py` por campo.

### 5.2 Forzado de catálogos controlados

Para campos enum (`tipo`, `estado`, `confidencialidad`, `fase`, `tipo_activo`), aplica `_match_catalogo()`: normaliza acentos, compara en minúsculas, busca coincidencia exacta y luego parcial. Si no hay match, aplica el fallback del catálogo. Esto impide que el modelo invente valores fuera de la taxonomía.

### 5.3 Arbitraje determinista vs. modelo

Esta es la regla más importante del sistema: **el texto del documento gana sobre la inferencia del modelo**.

- Si el parser detectó un valor con método `extraido` (leído literalmente del contenido) y el modelo propone algo diferente, **gana el parser**, salvo que el modelo haya citado evidencia propia en el campo `evidencias`.
- Si hay discrepancia con evidencia del modelo, se conserva el valor del modelo pero se registra la discrepancia en `observaciones` para revisión humana.
- Los candidatos `derivado` (propiedades de Word, nombre de archivo) **no tienen autoridad de sobrescritura** — son pistas que se ofrecen en el prompt pero no ganan en el arbitraje, porque una plantilla reutilizada arrastra metadatos del archivo original.
- Si el modelo asignó un valor a un campo declarativo sin que haya evidencia verificable, el valor se **degrada a `"No identificado"`** y se registra en `observaciones`.

### 5.4 Cálculo de confianza calibrada

Por cada uno de los 14 campos se calcula un score 0–100 con estas reglas:

| Condición | Efecto en el score |
|---|---|
| Campo sin valor identificado | Tope máximo de 35 |
| Candidato `extraido` por el parser | Piso mínimo de 85 |
| Candidato `derivado` (pista) | Rango forzado 55–69 (siempre "Requiere revisión") |
| ID generado automáticamente | Tope de 30 |
| Sin relaciones identificadas | Tope de 35 en campo `relaciones` |
| Modelo omitió el score | 60 si tiene valor, 20 si no |

El score final se convierte en nivel:

| Score | Nivel |
|---|---|
| ≥ 90 | Alta |
| ≥ 70 | Media |
| < 70 | Requiere revisión |

Los campos con score < 70 se listan en `requiere_revision`.

---

## 6. Taxonomía PKH (`taxonomy.py`)

Es la **fuente única de verdad** del sistema. Define:

- 12 categorías de activos con sus prefijos de ID
- 5 estados del ciclo de vida
- 4 niveles de confidencialidad
- 6 tipos de relación entre activos
- 3 fases del proyecto
- 5 tipos de activo (formato)
- 4 métodos de obtención de evidencia
- Contrato por atributo: capa, tipo de valor, métodos permitidos, fallback
- 5 ejes del contexto semántico
- Umbrales de confianza (Alta: 90, Media: 70)

Cualquier cambio en la taxonomía se propaga automáticamente al prompt de Claude y a todas las validaciones sin modificar ningún otro archivo.

### 6.1 Catálogo de categorías PKH

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

---

## 7. Modelo de metadatos de salida

El `metadata.json` resultante tiene 7 capas:

| Capa | Campos | Método de obtención |
|---|---|---|
| Identidad | `id`, `version`, `fecha`, `fase` | Extraído o derivado del archivo |
| Naturaleza | `tipo`, `tipo_activo` | Inferido por Claude dentro del catálogo |
| Semántica | `descripcion`, `contexto` | Inferido por Claude |
| Gobierno | `estado`, `responsable`, `confidencialidad` | Solo si aparece escrito — nunca inferido |
| Procedencia | `fuente` | Extraído o inferido |
| Grafo | `relaciones` | Extraído o inferido con tipos del modelo PKH |
| Calidad | `trazabilidad`, `confianza`, `niveles`, `requiere_revision`, `observaciones` | Calculado por el validador |

Más dos campos internos: `_documento` (métricas del archivo procesado) y `_uso` (modelo usado, tokens consumidos).

---

## 8. API REST (`main.py`)

| Método | Ruta | Función |
|---|---|---|
| GET | `/` | Sirve el frontend HTML |
| GET | `/api/taxonomy` | Expone los catálogos para los selectores del formulario |
| POST | `/api/analyze` | Recibe el archivo, ejecuta las 3 capas, devuelve el activo |
| POST | `/api/validate` | Registra la decisión humana (aceptado / pendiente) |

### 8.1 Seguridad del endpoint `/api/analyze`

- Validación de extensión contra lista blanca (`.docx`, `.pdf`, `.pptx`, `.json`, `.png`, `.jpg`, `.jpeg`)
- Validación de MIME type contra lista blanca
- Verificación de firma `PK` para `.docx`
- Rechazo explícito de `.docm` (macros)
- Límite de 50 MB por archivo
- Archivo escrito en `NamedTemporaryFile` y eliminado en bloque `finally` (garantizado incluso si hay excepción)
- Todos los errores devuelven JSON — nunca HTML

---

## 9. Stack tecnológico

| Componente | Tecnología |
|---|---|
| Backend | Python 3.11 · FastAPI · Uvicorn |
| Modelo de IA | Claude (Anthropic API) — `claude-sonnet-5` por defecto |
| Parser Word | `python-docx` |
| Parser PDF | `pdfplumber` |
| Parser PowerPoint | `python-pptx` |
| Reparación JSON | `json-repair` |
| Validación de datos | Pydantic v2 |
| Frontend | HTML + CSS + JavaScript vanilla (sin frameworks) |
| Despliegue | Render (Web Service) |

---

## 10. Estructura del repositorio

```
/poc-ia-ready
    /app
        main.py               FastAPI · endpoints · ciclo de vida del temporal
        taxonomy.py           catálogos PKH y contrato por atributo
        document_parser.py    extracción por formato + reglas deterministas
        claude_service.py     prompt generado desde taxonomy + llamada API
        metadata_validator.py arbitraje · catálogos · confianza
        models.py             contratos Pydantic de entrada/salida
    /templates
        index.html            interfaz de usuario
    /static
        styles.css            estilos
        app.js                lógica del frontend
    .env.example
    requirements.txt
    render.yaml
    ARQUITECTURA_STORAGE.md
    MEMORIA_TECNICA.md        este documento
```

---

## 11. Reglas de calidad garantizadas por código

1. **Campos declarativos nunca se infieren** — `estado`, `responsable`, `fecha`, `version` y `confidencialidad` solo se llenan si el valor aparece escrito. Si no: `"No identificado"`.

2. **El texto gana sobre la IA** — si el parser detectó `"BORRADOR"` en el documento y Claude dice `"Aprobado"`, gana el documento. Un activo mal clasificado contamina el índice.

3. **Confianza calibrada** — un campo sin valor nunca reporta confianza alta. Una pista derivada (propiedades de Word) se topa en 69 para que caiga en "Requiere revisión".

4. **Sin responsable + fuente + evidencia → no es Aprobado** — coherente con la regla de oro del PKH.

5. **Restringida nunca llega al RAG** — activos con datos de menores o sensibles quedan marcados y no se indexan.

6. **Human-in-the-loop** — el ciclo no se cierra hasta que un humano valida o marca como pendiente desde la interfaz.

---

## 12. Instalación local

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

Abre [http://localhost:8000](http://localhost:8000).

---

**OmniSys S.A. de C.V.** · Gobernanza de Aplicativos · VPAF · Tecnológico de Monterrey · uso interno del equipo
