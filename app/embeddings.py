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
    def __init__(self):
        self.intent_vectors: dict[str, list[list[float]]] = {}
        self._build_index()

    def _build_index(self):
        print("[EVA Embeddings] Vectorizando intents...")
        for intent, phrases in INTENTS.items():
            self.intent_vectors[intent] = [
                get_embedding(phrase) for phrase in phrases
            ]
        print(f"[EVA Embeddings] Listo — {len(INTENTS)} intents indexados.")

    def get_embedding(self, text: str) -> list[float]:
        return get_embedding(text)

    def match(self, message: str) -> tuple[str | None, float]:
        message_vec = get_embedding(message)
        best_intent = None
        best_score = 0.0

        for intent, vectors in self.intent_vectors.items():
            threshold = THRESHOLD_BY_INTENT.get(intent, THRESHOLD_DEFAULT)
            for vec in vectors:
                score = cosine_similarity(message_vec, vec)
                if score > best_score:
                    best_score = score
                    best_intent = intent

        if best_intent:
            threshold = THRESHOLD_BY_INTENT.get(best_intent, THRESHOLD_DEFAULT)
            if best_score >= threshold:
                return best_intent, best_score

        return None, best_score

    def is_feedback(self, message: str) -> bool:
        intent, _ = self.match(message)
        return intent == "feedback"
