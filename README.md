# TEC | Clasificador de Activos de Conocimiento IA-Ready

POC que toma un documento Word, lo analiza temporalmente con Claude y devuelve
una ficha de metadatos revisable por una persona.

No es un repositorio documental. El archivo no se guarda: se escribe en un
temporal, se procesa y se elimina en un `finally`. No hay base de datos, no hay
carpeta de uploads, no hay storage.

---

## 1. Qué demuestra

```
DOCUMENTO -> EXTRACCION -> ANALISIS IA -> CLASIFICACION -> METADATOS -> VALIDACION HUMANA -> ACTIVO IA-READY
```

El punto no es "subir un archivo". El punto es que un documento plano se
convierte en un activo con tipo, contexto, relaciones, vigencia, responsable y
trazabilidad, para que una solución RAG posterior no dependa solo de la
similitud semántica del texto.

---

## 2. Cómo se clasifica

El modelo de metadatos tiene siete capas:

| Capa | Responde a | Campos |
|---|---|---|
| Identidad | qué documento es | `id`, `version`, `fecha` |
| Naturaleza | qué clase de activo es | `tipo` |
| Semántica | de qué trata | `descripcion`, `contexto` |
| Gobierno | si se puede confiar en él | `estado`, `responsable`, `confidencialidad` |
| Procedencia | de dónde viene | `fuente` |
| Grafo | con qué se conecta | `relaciones` |
| Calidad | qué tan sólido es | `trazabilidad`, `confianza`, `observaciones` |

La regla que sostiene todo está en `app/taxonomy.py`: cada atributo declara qué
métodos de obtención acepta.

**Atributos interpretables** (`tipo`, `descripcion`, `contexto`, `relaciones`,
`fuente`): Claude puede deducirlos leyendo, aunque no estén escritos literalmente.

**Atributos declarativos** (`version`, `estado`, `responsable`, `fecha`,
`confidencialidad`): solo se llenan si el valor aparece escrito. Si no aparece,
quedan en `"No identificado"`. Un documento bien formateado no está aprobado.

Tres controles hacen que esto se cumpla de verdad y no solo en el prompt:

1. **Detección determinista previa** (`document_parser.detectar_candidatos`).
   Antes de llamar al modelo, reglas de expresión regular buscan versión, fecha,
   responsable, estado y confidencialidad en portada, encabezado/pie, tablas,
   nombre de archivo y propiedades de Word. Lo que se encuentra se marca como
   `extraido` (leído en el contenido) o `derivado` (metadata del archivo, menos
   confiable) y se le entrega al modelo como contexto verificado.

2. **Arbitraje en el validador** (`metadata_validator.validar`). Si el analizador
   leyó "BORRADOR" en la portada y el modelo dice "Aprobado" sin citar evidencia,
   gana el analizador y queda registrado en `observaciones`. Solo la evidencia
   `extraido` tiene esa autoridad: una fecha sacada de las propiedades de Word no
   sobrescribe nada, porque una plantilla reutilizada arrastra la fecha original.

3. **Confianza calibrada por respaldo, no por sensación.** Un campo que quedó en
   "No identificado" nunca reporta confianza alta; un valor apoyado en pista
   derivada se topa en 69 para que caiga en "requiere revisión".

Catálogos controlados: `tipo` (19 valores), `estado` (6), `confidencialidad` (5),
`relaciones[].tipo` (13). El validador hace *match* contra el catálogo, así que
un valor fuera de lista cae al fallback en vez de contaminar el índice.

---

## 3. Arquitectura

```
/poc-ia-ready
    /app
        main.py                 FastAPI, endpoints, ciclo de vida del temporal
        taxonomy.py             catálogos y contrato por atributo (fuente única)
        document_parser.py      extracción .docx + reglas deterministas
        claude_service.py       prompt generado desde la taxonomía + llamada API
        metadata_validator.py   catálogos, arbitraje, confianza
        models.py               contratos de entrada/salida
    /templates/index.html
    /static/styles.css, app.js
    .env.example  requirements.txt  README.md
```

`taxonomy.py` se usa dos veces: se inyecta al prompt y se usa para validar la
respuesta. Agregar un tipo nuevo se hace en un solo archivo.

---

## 4. Instalación

Requiere Python 3.10 o superior (`python --version`). Si no lo tienes:
descárgalo de python.org y marca "Add Python to PATH" en la instalación.

```bash
cd poc-ia-ready

# entorno virtual
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### Token de Anthropic

```bash
cp .env.example .env              # Windows: copy .env.example .env
```

Edita `.env` y coloca tu token:

```
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-5
```

El token se lee solo del lado servidor. Nunca llega al HTML ni al JavaScript.
`.env` está en `.gitignore`.

### Arrancar

```bash
uvicorn app.main:app --reload --port 8000
```

Abre <http://localhost:8000>.

---

## 5. Endpoints

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/` | pantalla principal |
| GET | `/api/taxonomy` | catálogos, para que el formulario use listas cerradas |
| POST | `/api/analyze` | recibe el .docx, extrae, clasifica, devuelve el JSON |
| POST | `/api/validate` | cierra el ciclo human-in-the-loop; no persiste |

---

## 6. Seguridad

- El documento se escribe en un `NamedTemporaryFile` y se elimina en un `finally`,
  incluso si el análisis falla.
- Validación de extensión, MIME, firma del archivo (`PK`) y tamaño (20 MB).
- `.docm` rechazado: no se procesan macros.
- Nombre de archivo saneado.
- Las imágenes se extraen a base64 en memoria y viajan a la API para enriquecer
  la clasificación; no se guardan.
- Los logs registran duración, número de párrafos, tablas, imágenes y campos en
  revisión. No registran contenido, imágenes, token ni datos extraídos.

---

## 7. Límites conocidos

- Solo `.docx`. La arquitectura deja el hueco para `.pdf`, `.pptx` y `.xlsx`:
  basta con agregar un parser que devuelva la misma estructura que `parse_docx`.
- Documentos muy largos se truncan por la mitad antes de enviarse al modelo
  (`bloque_para_modelo`, 45 000 caracteres). Para documentos grandes conviene
  clasificar por secciones y consolidar.
- Se analizan hasta 4 imágenes, las de mayor peso, descartando las menores a
  12 KB para no gastar tokens en logos.
- No hay base vectorial. Esta POC termina en el activo validado; la ingesta al
  índice es la siguiente etapa.
