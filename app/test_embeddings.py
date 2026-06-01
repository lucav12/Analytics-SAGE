from embeddings import IntentMatcher, get_feedback_detector
from feedback import classify_feedback_with_scores, estimate_happiness_score

matcher = IntentMatcher()
detector = get_feedback_detector()


test_cases_non_feedback = [
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

test_cases_feedback = [
    "no me gusta la comida",
    "tengo que decir que realmente las bebidas estuvieron malas",
    "me gusta mucho la ceremonia",
    "el acto fue muy interesante",
    "me encantó la planificación del evento",
    "me pareció que la organización estuvo excelente",
    "estuvo mal la salida",
    "no me gustó el acceso al evento",
    "la acreditación fue bastante rápida pero muy desorganizada",
    "la espera fue bastante corta pero tardaron en traer comida",
]

test_cases_mixed = test_cases_non_feedback + test_cases_feedback

print("\n=== Prueba de feedback + categorización ===\n")

for msg in test_cases_non_feedback: #modificar a test_cases_mixed para probar ambos
    is_fb, fb_score = detector.is_feedback(msg)
    print(f"{'✓' if is_fb else '~'} '{msg}'")
    print(f"  → feedback detector: {'SÍ' if is_fb else 'NO'} ({fb_score:.3f})")

    if is_fb:
        categories = classify_feedback_with_scores(msg, top_k=2)
        happiness = estimate_happiness_score(msg)
        cats_str = ", ".join(f"{cat} ({s:.3f})" for cat, s in categories)
        print(f"  → categorías: {cats_str}")
        print(f"  → happiness:  {happiness}/10")

    print()