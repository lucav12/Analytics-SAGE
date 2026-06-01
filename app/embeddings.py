import requests
import math

OLLAMA_URL = "http://localhost:11434/api/embed"
EMBED_MODEL = "nomic-embed-text"

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

THRESHOLD_DEFAULT = 0.65
THRESHOLD_BY_INTENT = {
    "feedback": 0.82,
}

FEEDBACK_SIGNAL_KEYWORDS = [
    # Positive signals
    "estuvo", "salió", "quedó", "fue", "me pareció", "me gustó",
    "me encantó", "perfecto", "genial", "muy bien", "excelente",
    # Negative signals  
    "mal", "tarde", "espera", "lento", "desorganizado", "problema",
    "mejorar", "faltó", "podría ser mejor", "decepcionante",
    # Opinion markers
    "creo que", "pienso que", "en mi opinión", "a mi parecer",
    "la verdad", "sinceramente", "honestamente",
]

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
    def __init__(self, intents: dict[str, list[str]] | None = None, thresholds: dict[str, float] | None = None):
        self.intents = intents or INTENTS
        self.thresholds = thresholds or THRESHOLD_BY_INTENT
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

        if best_intent:
            thresholds = getattr(self, "thresholds", THRESHOLD_BY_INTENT)
            threshold = thresholds.get(best_intent, THRESHOLD_DEFAULT)
            if best_score >= threshold:
                return best_intent, best_score

        return None, best_score

    def match_all(self, message: str, min_score: float | None = None) -> list[tuple[str, float]]:
        message_vec = get_embedding(message)
        matches: list[tuple[str, float]] = []

        for intent, vectors in self.intent_vectors.items():
            best_score = max(cosine_similarity(message_vec, vec) for vec in vectors)
            thresholds = getattr(self, "thresholds", THRESHOLD_BY_INTENT)
            threshold = thresholds.get(intent, THRESHOLD_DEFAULT)
            if min_score is not None:
                threshold = min_score
            if best_score >= threshold:
                matches.append((intent, best_score))

        return sorted(matches, key=lambda pair: pair[1], reverse=True)

    # def is_feedback(self, message: str) -> bool:
    #     """Two-stage feedback detection: embedding similarity + keyword fallback."""
    #     # Stage 1: embedding-based intent match (your existing logic)
    #     intent, score = self.match(message)
    #     if intent == "feedback":
    #         return True

    #     # Stage 2: keyword fallback for indirect feedback
    #     # Only triggers if embedding score was close but below threshold
    #     _, raw_score = self.match(message)  # already computed, but explicit here
    #     normalized = message.strip().lower()
    #     has_signal = any(kw in normalized for kw in FEEDBACK_SIGNAL_KEYWORDS)

    #     # Soft threshold: if score is close (≥0.70) AND there's a lexical signal, count it
    #     SOFT_THRESHOLD = 0.70
    #     if raw_score >= SOFT_THRESHOLD and has_signal:
    #         return True

    #     return False
    def is_feedback(self, message: str) -> bool:
        detector = get_feedback_detector()
        is_fb, _ = detector.is_feedback(message)
        return is_fb

#first it checks if the message is feedback or a question, then it classifies the intent.
FEEDBACK_DETECTION_EXAMPLES = [
    # Opinions / evaluations
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
    # Experiential complaints — personal experience with implicit negative judgment
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
        # Flatten all INTENTS phrases as the non-feedback corpus
        non_feedback_phrases = [phrase for phrases in INTENTS.values() for phrase in phrases]
        self.non_feedback_vecs = [get_embedding(p) for p in non_feedback_phrases]
        print("[EVA] Detector de feedback listo.")

    def is_feedback(self, message: str) -> tuple[bool, float]:
        vec = get_embedding(message)
        feedback_score = max(cosine_similarity(vec, v) for v in self.feedback_vecs)
        non_feedback_score = max(cosine_similarity(vec, v) for v in self.non_feedback_vecs)
        # It's feedback if it's closer to opinions than to questions
        is_fb = feedback_score > non_feedback_score and feedback_score >= FEEDBACK_DETECTION_THRESHOLD
        return is_fb, feedback_score    

def get_feedback_detector() -> FeedbackDetector:
    global _FEEDBACK_DETECTOR
    if _FEEDBACK_DETECTOR is None:
        _FEEDBACK_DETECTOR = FeedbackDetector()
    return _FEEDBACK_DETECTOR