# Analytics-SAGE

Trabajo personal del rol de **Data Architect / Analytics** dentro del proyecto
[SAGE](https://github.com/SAGE-AHK) (Sistema de Administración y Gestión de Eventos —
AHK 2026). Este repo no pisa el código del backend público
[`sage-agent`](https://github.com/SAGE-AHK/sage-agent); contiene una **propuesta
local** para la API de feedback y su documentación técnica.

## Contenido

| Ruta | Qué es |
|---|---|
| [`feedback_api.py`](feedback_api.py) | API REST self-contained (FastAPI + SQLite) para insertar feedback ya formateado. Define la estructura de datos sobre la que se apoya el modelo definitivo. |
| [`SAGE-Agent_y_FeedbackAPI.docx`](SAGE-Agent_y_FeedbackAPI.docx) | Documento técnico completo: análisis del backend `sage-agent` archivo por archivo + explicación detallada de `feedback_api.py`. |
| [`poc_data_model/`](poc_data_model/) | **Prueba de concepto** del modelo de datos extendido (5 tablas). Incluye `schema.sql`, scripts de build/seed/queries y `Modelo_de_Datos.docx` con la explicación pedagógica completa pensada para presentación. |

## ¿Qué resuelve `feedback_api.py`?

Tres pedidos concretos del equipo IA:

1. **Categorías y criterios de evaluación** acordados — base para que el
   pipeline NLP derive un listado de palabras clave alineado.
2. **Estructura de datos** (schema Pydantic) sobre la que se asienta el modelo
   de datos definitivo. No es un modelo cerrado: es la *forma*.
3. **API REST mínima** (`POST /feedback`) para insertar una fila ya
   formateada desde el clasificador.

Persistencia local en SQLite (`feedback.db`, generado al arrancar). La
migración futura a Postgres es mecánica: solo cambia `_connect()` y los tipos
del `CREATE TABLE`.

## Correrlo localmente

```powershell
pip install "fastapi>=0.115" "uvicorn[standard]>=0.30" "pydantic>=2.7"
python feedback_api.py
```

Abrir Swagger en <http://localhost:8000/docs>.

### Ejemplo de payload — `POST /feedback`

```json
{
  "raw_signal": "el catering estuvo bueno pero la espera fue larga",
  "category": "organización",
  "sentiment": "mixed",
  "sentiment_score": 0.1,
  "source": "auto_nlp",
  "classifier_version": "embeddings-v2",
  "confidence": 0.82
}
```

## Estado

Trabajo **local, en evaluación**. La integración a `sage-agent` se hará cuando
esté validada con el equipo IA — son dos líneas en `app/main.py`:

```python
from feedback_api import router as feedback_router
app.include_router(feedback_router)
```

## Documento técnico

El `.docx` cubre:

- **Parte 1 — SAGE-Agent**: stack, estructura, recorrido por `main.py`,
  `agent.py`, `prompts.py`, `feedback.py` y `feedback_log.json`, con
  fragmentos de código reales del repo público.
- **Parte 2 — feedback_api.py**: por qué existe, los 5 bloques del archivo
  explicados uno por uno, tabla campo-por-campo del schema Pydantic.
- **Parte 3 — Cómo correrlo**: setup, Swagger, PowerShell, lectura de SQLite.
- **Parte 4 — Próximos pasos**: roadmap de integración y evolución a Postgres.

Para leerlo cómodamente, subir a Google Drive y abrir con Google Docs.
