"""Persistencia + enriquecimiento de feedback de EVA.

Sobre la base de sage-agent (un append a JSON con session_id, texto y
categoría plana), este módulo agrega:

- clasificación multi-categoría por embeddings (recepción, ceremonia,
  organización, catering, logística, ...) con score por categoría;
- happiness score 0-10 estimado por keywords con manejo de negaciones;
- NPS 0-10 (promotor/pasivo/detractor) con override por keywords NPS;
- return_likelihood 0-10 (probabilidad de volver) con override por keywords
  de retorno.

El archivo JSON sigue siendo el sink temporal; la versión productiva
ingestará estos campos en Postgres (ver `db/schema.sql`).
"""

import json
import uuid
from datetime import datetime
from pathlib import Path

from embeddings import IntentMatcher
import db  # Persistencia opcional en Postgres (no-op si DATABASE_URL no está seteada)

FEEDBACK_FILE = Path(__file__).parent / "feedback_log.json"

DEFAULT_FEEDBACK_CATEGORY = "general"

FEEDBACK_CATEGORY_EXAMPLES = {
    "recepcion": [
        "la acreditación fue muy rápida",
        "esperé mucho en la fila para registrarme",
        "el acceso al evento estuvo desorganizado",
        "tardaron en registrarme en la entrada",
        "la fila para entrar era larguísima",
        "me atendieron bien en la recepción",
        "el registro fue sencillo y ordenado",
    ],
    "ceremonia": [
        "la ceremonia estuvo muy emotiva",
        "la entrega de diplomas fue increíble",
        "el acto me pareció muy bien organizado",
        "el salón estaba muy lindo para el evento",
        "los discursos fueron interesantes",
        "la ceremonia fue demasiado larga",
        "me encantó el momento de la entrega",
    ],
    "organizacion": [
        "la organización del evento estuvo excelente",
        "todo estuvo muy bien coordinado",
        "me pareció que la planificación fue impecable",
        "el orden general del evento fue muy bueno",
        "faltó mejor coordinación entre el personal",
        "la organización dejó mucho que desear",
        "todo fluyó muy bien gracias a la organización",
        "hubo mucha desorganización",
        "el evento estuvo mal organizado",
        "los horarios no se respetaron",
        "hubo problemas de coordinación",
        "todo estuvo perfectamente organizado",
        "la logística estuvo muy bien coordinada",
        "el cronograma se cumplió correctamente",
    ],
    "catering": [
        "la comida estuvo excelente",
        "las bebidas fueron de buena calidad",
        "el servicio gastronómico fue muy bueno",
        "la comida llegó tarde",
        "las bebidas estaban calientes",
        "el catering dejó mucho que desear",
    ],
    "logistica": [
        "la salida del evento fue un caos",
        "el ingreso estuvo bien señalizado",
        "costó mucho moverse dentro del lugar",
        "la señalización para llegar al salón fue confusa",
        "el movimiento de gente estuvo bien",
        "no había carteles que indicaran por dónde ir",
        "la logística del evento funcionó muy bien",
    ],
}

FEEDBACK_CATEGORY_THRESHOLD = 0.72

_FEEDBACK_CLASSIFIER: IntentMatcher | None = None


def _get_feedback_classifier() -> IntentMatcher:
    global _FEEDBACK_CLASSIFIER
    if _FEEDBACK_CLASSIFIER is None:
        _FEEDBACK_CLASSIFIER = IntentMatcher(
            intents=FEEDBACK_CATEGORY_EXAMPLES,
            thresholds={cat: FEEDBACK_CATEGORY_THRESHOLD for cat in FEEDBACK_CATEGORY_EXAMPLES},
        )
    return _FEEDBACK_CLASSIFIER


POSITIVE_KEYWORDS = [
    "excelente", "muy bien", "me encantó", "felicitaciones", "perfecto", "genial",
    "fantástico", "muy bueno", "recomend", "estuvo bien", "buenísimo",
    "increíble", "maravilloso", "espectacular", "impecable", "brillante",
    "muy lindo", "hermoso", "outstanding", "notable",
    # Conjugaciones de "gustar" — la heurística matchea por substring, así que
    # hay que listar cada conjugación. La detección de negaciones (_is_negated)
    # invalida estos matches cuando aparecen precedidos por "no"/"nunca"/etc.
    "me gustó", "me gusta", "me gustaron", "me gustan",
    # Adjetivos como "malísimo"/"espectacular" ya están arriba; agregamos
    # variantes positivas de superlativos comunes.
    "buenísima", "buenísimos", "buenísimas",
]
NEGATIVE_KEYWORDS = [
    "horrible", "desorganizado", "lento", "problema",
    "peor", "esperé mucho", "tardaron", "falta", "deficiente",
    "decepcionante", "me decepcionó", "pésimo", "terrible",
    "mal organizado", "estuvo mal",
    # Conjugaciones de "no me gusta(r)" — sin esto, "no me gustaron las bebidas"
    # quedaba como happy=5 (neutral) cuando debería ser bajo.
    "no me gustó", "no me gusta", "no me gustaron", "no me gustan",
    # Superlativos negativos comunes en español.
    "malísimo", "malísima", "malísimos", "malísimas",
    "feísimo", "feísima",
]
PROMOTER_KEYWORDS = [
    "lo recomiendo", "muy probable", "seguro lo recomendaría",
    "excelente experiencia", "super recomendable", "recomendaría",
]
DETRACTOR_KEYWORDS = [
    "no lo recomiendo", "poco probable", "nunca más",
    "no estoy satisfecho", "no recomendaría",
]
RETURN_POSITIVE_KEYWORDS = [
    "volveré", "regresaría", "próxima edición", "próxima vez",
    "me gustaría volver", "seguro vuelvo", "quiero volver",
    "asistiré de nuevo",
]
RETURN_NEGATIVE_KEYWORDS = [
    "no vuelvo", "no regreso", "no volveré",
    "no pienso volver", "no asistiré de nuevo", "no volvería",
]
RETURN_PASSIVE_KEYWORDS = [
    "tal vez vuelva", "quizás vuelva", "no sé si vuelvo",
    "si puedo vuelvo", "puede ser que vuelva",
]
PASSIVE_KEYWORDS = [
    "quizás", "no sé", "regular", "ni fu ni fa", "más o menos", "tal vez",
]

NEGATION_PREFIXES = ["no ", "nunca ", "jamás ", "ni "]


def _normalize_text(text: str) -> str:
    return text.strip().lower()


def _is_negated(text: str, keyword: str) -> bool:
    idx = text.find(keyword)
    if idx == -1:
        return False
    prefix = text[max(0, idx - 10):idx]
    return any(prefix.strip().endswith(neg.strip()) for neg in NEGATION_PREFIXES)


def _contains_positive(text: str, keywords: list[str]) -> bool:
    return any(
        keyword in text and not _is_negated(text, keyword)
        for keyword in keywords
    )


def _contains_negative(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def has_explicit_sentiment(message: str) -> bool:
    """¿El mensaje contiene una keyword INEQUÍVOCA de sentimiento?

    Sirve como "capa 3" de detección de feedback en agent.py — un override
    bulletproof por encima del IntentMatcher (capa 1) y el FeedbackDetector
    semántico (capa 2). Captura casos tipo "me gustaron mucho los discursos"
    donde el embedding semántico se confunde por el sustantivo específico
    pero la intención de feedback es clara por las palabras de sentimiento.

    Usa las MISMAS keywords que el scoring de happiness, con la misma
    detección de negaciones (positivas con `no` adelante NO disparan).
    """
    normalized = _normalize_text(message)
    if _contains_positive(normalized, POSITIVE_KEYWORDS):
        return True
    if _contains_negative(normalized, NEGATIVE_KEYWORDS):
        return True
    return False


def classify_feedback(message: str) -> list[str]:
    matches = classify_feedback_with_scores(message)
    return [intent for intent, _ in matches] or [DEFAULT_FEEDBACK_CATEGORY]


def classify_feedback_with_scores(
    message: str,
    min_score: float | None = None,
    top_k: int | None = None,
) -> list[tuple[str, float]]:
    """Devuelve `[(categoria, score)]` ordenado por score descendente.

    - `min_score`: piso de similitud coseno. Si es None, usa los thresholds
      por categoría configurados en `_get_feedback_classifier()`.
    - `top_k`: si se especifica, devuelve solo los primeros `top_k` matches.
    """
    classifier = _get_feedback_classifier()
    matches = classifier.match_all(message, min_score=min_score)
    if not matches:
        return [(DEFAULT_FEEDBACK_CATEGORY, 1.0)]
    if top_k is not None and top_k > 0:
        matches = matches[:top_k]
    return matches


def estimate_happiness_score(message: str) -> int:
    normalized = _normalize_text(message)
    score = 5
    if _contains_positive(normalized, POSITIVE_KEYWORDS):
        score += 3
    if _contains_negative(normalized, NEGATIVE_KEYWORDS):
        score -= 3
    if "muy" in normalized and _contains_positive(
        normalized, ["bien", "bueno", "excelente", "recomend", "increíble"]
    ):
        score += 1
    if "nada" in normalized or "peor" in normalized:
        score -= 1
    return max(0, min(10, score))


def estimate_nps_score(message: str, happiness_score: int) -> int:
    normalized = _normalize_text(message)
    if _contains_positive(normalized, PROMOTER_KEYWORDS):
        return 9
    if _contains_negative(normalized, DETRACTOR_KEYWORDS):
        return 1
    if _contains_any(normalized, PASSIVE_KEYWORDS):
        return 6
    return max(0, min(10, happiness_score))


def estimate_return_likelihood_score(message: str, happiness_score: int | None = None) -> int:
    normalized = _normalize_text(message)
    if _contains_positive(normalized, RETURN_POSITIVE_KEYWORDS):
        return 9
    if _contains_negative(normalized, RETURN_NEGATIVE_KEYWORDS):
        return 1
    if _contains_any(normalized, RETURN_PASSIVE_KEYWORDS):
        return 5
    if happiness_score is not None:
        return max(0, min(10, happiness_score))
    return 5


def save_feedback(
    session_id: str,
    user_message: str,
    eva_response: str,
    category: str | None = None,
    categories: list[str] | None = None,
    message_id: str | None = None,
    source: str = "auto_intent",
):
    if categories is None:
        matches = classify_feedback_with_scores(user_message)
        categories = [intent for intent, _ in matches]
        categorias_scores = [
            {"categoria": intent, "score": round(float(score), 4)}
            for intent, score in matches
        ]
    else:
        categories = [cat.strip() for cat in categories if cat and isinstance(cat, str)]
        categorias_scores = []

    primary_category = (
        category or (categories[0] if categories else DEFAULT_FEEDBACK_CATEGORY)
    )
    if category and category not in categories:
        categories.insert(0, category)

    happiness_score = estimate_happiness_score(user_message)
    net_promoter_score = estimate_nps_score(user_message, happiness_score)
    return_likelihood_score = estimate_return_likelihood_score(user_message, happiness_score)

    entry = {
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "timestamp": datetime.now().isoformat(),
        "mensaje_invitado": user_message,
        "respuesta_eva": eva_response,
        "categoria": primary_category,
        "categorias": categories,
        "categorias_scores": categorias_scores,
        "happiness_score": happiness_score,
        "net_promoter_score": net_promoter_score,
        "return_likelihood_score": return_likelihood_score,
    }

    existing = []
    if FEEDBACK_FILE.exists():
        with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)

    existing.append(entry)

    with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print(
        f"[EVA] Feedback guardado — categoría: {primary_category} "
        f"({', '.join(categories)}) — happiness: {happiness_score} "
        f"— NPS: {net_promoter_score} — volver: {return_likelihood_score}"
    )

    # Persistencia opcional en Postgres. Si DATABASE_URL no está seteada o
    # psycopg no está instalado, db.insert_feedback es no-op.
    if message_id:
        try:
            fb_id = db.insert_feedback(entry, message_id, source=source)
            if fb_id:
                print(f"[EVA DB] Feedback persistido en Postgres: {fb_id}")
        except Exception as e:
            print(f"[EVA DB] No se pudo persistir feedback: {e}")

    return entry
