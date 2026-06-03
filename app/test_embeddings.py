from embeddings import IntentMatcher

matcher = IntentMatcher()

test_cases = [
    "¿dónde puedo ir al baño?",
    "necesito usar el toilette",
    "¿por dónde salgo si hay una emergencia?",
    "¿a qué hora empieza todo?",
    "la organización estuvo increíble",
    "esperé muchísimo para acreditarme",
    "¿quiénes son los egresados de sistemas?",
    "¿hay algo para comer?",
    "buenas tardes, cómo estás",
    "¿cuánto cuesta una pizza?",
]

print("\n=== Prueba de IntentMatcher ===\n")
for msg in test_cases:
    intent, score = matcher.match(msg)
    status = "✓" if intent else "~"
    score_str = f"{score:.3f}"
    intent_str = intent if intent else "sin match — va al modelo"
    print(f"{status} '{msg}'")
    print(f"  → {intent_str} ({score_str})\n")
