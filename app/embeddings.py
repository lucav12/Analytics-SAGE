import requests
import math
import os

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_URL = f"{OLLAMA_BASE_URL}/api/embed"
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

INTENTS = {
    "orientacion_banos": [
        "necesito el baño urgente", "toilette por favor",
        "baños", "sanitarios", "donde está el baño",
        "necesito ir al baño", "toilette", "ir al baño",
        "dónde están los baños", "baño por favor"
    ],
    "orientacion_salida_emergencia": [
        "salida de emergencia", "evacuación", "salida de incendio",
        "donde salgo si hay un problema", "emergencia",
        "salida de seguridad", "evacuarme", "hay un incendio"
    ],
    "orientacion_salon": [
        "salon principal", "donde es la ceremonia",
        "donde entregan los diplomas", "salón A",
        "donde me siento", "donde es el acto"
    ],
    "orientacion_entrada": [
        "entrada principal", "donde entro", "acceso",
        "por donde se entra", "recepción", "acreditación",
        "donde me acredito", "ingreso al evento"
    ],
    "orientacion_guardarropa": [
        "guardarropa", "donde dejo el abrigo",
        "donde guardo mis cosas", "dejo el bolso",
        "dejo mi cartera", "donde dejar las cosas"
    ],
    "feedback": [
        "quiero dejar un comentario", "tengo una opinión",
        "estuvo muy bien", "me encantó el evento",
        "estuvo mal", "no me gustó", "muy desorganizado",
        "larga espera", "tardaron mucho", "felicitaciones",
        "queja", "sugerencia", "me pareció", "la organización estuvo",
        "la ceremonia estuvo", "el catering estuvo",
        "esperé mucho", "excelente", "mejorar",
        "esperé mucho para acreditarme", "la acreditación tardó",
        "tardaron en atenderme", "la fila estuvo larga"
    ],
    "info_egresados": [
        "egresados", "quienes se reciben", "los graduados",
        "quienes son los chicos", "de qué carrera",
        "quién se gradúa", "los alumnos", "los estudiantes"
    ],
    "info_agenda": [
        "a qué hora empieza", "cuándo es la entrega",
        "agenda del evento", "horarios", "programa",
        "cuándo arranca", "a qué hora termina",
        "qué viene después", "cuándo es la foto"
    ],
    "info_catering": [
        "hay comida", "donde comer", "catering",
        "buffet", "algo para tomar", "hay bebidas",
        "dónde es el catering", "el networking",
        "algo para comer o tomar", "donde hay comida"
    ],
    "info_vestimenta": [
        "como tengo que venir vestido", "código de vestimenta",
        "ropa", "formal", "smart casual", "que me pongo"
    ],
}

THRESHOLD_DEFAULT = 0.78
THRESHOLD_BY_INTENT = {
    "feedback": 0.82,
}


def get_embedding(text: str) -> list[float]:
    response = requests.post(OLLAMA_URL, json={
        "model": EMBED_MODEL,
        "input": text
    })
    response.raise_for_status()
    return response.json()["embeddings"][0]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x ** 2 for x in a))
    mag_b = math.sqrt(sum(x ** 2 for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


class IntentMatcher:
    """Matcher de intents por similitud coseno sobre embeddings.

    Si no se pasan `intents`/`thresholds`, usa los globales — comportamiento
    backward-compatible con sage-agent. Cuando se pasa un dict propio, sirve
    como clasificador genérico (ej: categorías de feedback en feedback.py).
    """

    def __init__(
        self,
        intents: dict[str, list[str]] | None = None,
        thresholds: dict[str, float] | None = None,
    ):
        self.intents = intents if intents is not None else INTENTS
        self.thresholds = thresholds if thresholds is not None else THRESHOLD_BY_INTENT
        self.intent_vectors: dict[str, list[list[float]]] = {}
        self._build_index()

    def _build_index(self):
        print("[EVA Embeddings] Vectorizando intents...")
        for intent, phrases in self.intents.items():
            self.intent_vectors[intent] = [
                get_embedding(phrase) for phrase in phrases
            ]
        print(f"[EVA Embeddings] Listo — {len(self.intent_vectors)} intents indexados.")

    def get_embedding(self, text: str) -> list[float]:
        return get_embedding(text)

    def _threshold_for(self, intent: str) -> float:
        # `_check_jailbreak()` en agent.py construye un IntentMatcher temporal
        # con `__new__` (saltándose __init__) para no re-vectorizar todos los
        # intents — ese matcher no tiene `self.thresholds`. Usamos getattr para
        # ser defensivos y caer al diccionario global.
        thresholds = getattr(self, "thresholds", None) or THRESHOLD_BY_INTENT
        return thresholds.get(intent, THRESHOLD_DEFAULT)

    def match(self, message: str) -> tuple[str | None, float]:
        message_vec = get_embedding(message)
        best_intent = None
        best_score = 0.0

        for intent, vectors in self.intent_vectors.items():
            for vec in vectors:
                score = cosine_similarity(message_vec, vec)
                if score > best_score:
                    best_score = score
                    best_intent = intent

        if best_intent and best_score >= self._threshold_for(best_intent):
            return best_intent, best_score
        return None, best_score

    def match_all(
        self,
        message: str,
        min_score: float | None = None,
    ) -> list[tuple[str, float]]:
        """Devuelve TODAS las categorías por encima del umbral, ordenadas desc.

        Útil para clasificación multi-etiqueta (un mensaje puede hablar de
        catering Y de organización al mismo tiempo).
        """
        message_vec = get_embedding(message)
        matches: list[tuple[str, float]] = []
        for intent, vectors in self.intent_vectors.items():
            best_score = max(cosine_similarity(message_vec, vec) for vec in vectors)
            threshold = min_score if min_score is not None else self._threshold_for(intent)
            if best_score >= threshold:
                matches.append((intent, best_score))
        return sorted(matches, key=lambda pair: pair[1], reverse=True)

    def is_feedback(self, message: str) -> bool:
        detector = get_feedback_detector()
        is_fb, _ = detector.is_feedback(message)
        return is_fb


# ---------------------------------------------------------------------------
# Detector binario de feedback (capa fina por encima del matcher de intents)
# ---------------------------------------------------------------------------
# El detector compara el mensaje contra dos corpus chicos — uno de OPINIONES
# (lo que queremos detectar) y otro de PREGUNTAS (resto de intents) — y
# devuelve True si está más cerca del corpus de opiniones y supera el piso.
FEEDBACK_DETECTION_EXAMPLES = [
    # Opiniones explícitas
    "la comida estuvo muy rica",
    "las bebidas estuvieron malas",
    "me encantó la ceremonia",
    "el acto fue muy interesante",
    "me pareció que la organización estuvo excelente",
    "estuvo mal la salida",
    "no me gustó el acceso al evento",
    "la acreditación fue bastante rápida pero muy desorganizada",
    "la espera fue bastante corta pero tardaron en traer comida",
    "tengo que decir que realmente las bebidas estuvieron malas",
    "me pareció un evento muy bien organizado",
    "la planificación estuvo excelente",
    "no me gusta la comida",
    "me gusta mucho la ceremonia",
    # Negación de gusto sobre sustantivos de categorías. Sin estas frases, el
    # sustantivo (catering, comida, bebidas) domina la similitud y el detector
    # se confunde con info_catering — ver issue del 06/2026.
    "no me gustó el catering",
    "no me gustaron las bebidas",
    "no me gustó la comida del catering",
    "el catering estuvo mal",
    "el catering me decepcionó",
    "no me gustó la organización",
    "no me gustó la ceremonia",
    "no me gustó la recepción",
    "no me gustó cómo nos atendieron",
    # Quejas experienciales con juicio implícito
    "esperé muchísimo para acreditarme",
    "tardé una hora en entrar",
    "no encontré dónde sentarme",
    "me perdí dentro del lugar",
    "tuve que hacer una fila enorme",
    "no llegué a comer nada porque se acabó todo",
    "casi no escucho nada desde donde estaba",
]

FEEDBACK_DETECTION_THRESHOLD = 0.80

_FEEDBACK_DETECTOR: "FeedbackDetector | None" = None


class FeedbackDetector:
    def __init__(self):
        print("[EVA] Vectorizando detector de feedback...")
        self.feedback_vecs = [get_embedding(p) for p in FEEDBACK_DETECTION_EXAMPLES]
        # Corpus negativo: todas las frases de los intents NO-feedback.
        non_feedback_phrases = [
            phrase
            for intent, phrases in INTENTS.items()
            if intent != "feedback"
            for phrase in phrases
        ]
        self.non_feedback_vecs = [get_embedding(p) for p in non_feedback_phrases]
        print("[EVA] Detector de feedback listo.")

    def is_feedback(self, message: str) -> tuple[bool, float]:
        vec = get_embedding(message)
        feedback_score = max(cosine_similarity(vec, v) for v in self.feedback_vecs)
        non_feedback_score = max(cosine_similarity(vec, v) for v in self.non_feedback_vecs)
        is_fb = (
            feedback_score > non_feedback_score
            and feedback_score >= FEEDBACK_DETECTION_THRESHOLD
        )
        return is_fb, feedback_score


def get_feedback_detector() -> FeedbackDetector:
    global _FEEDBACK_DETECTOR
    if _FEEDBACK_DETECTOR is None:
        _FEEDBACK_DETECTOR = FeedbackDetector()
    return _FEEDBACK_DETECTOR
