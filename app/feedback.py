import json
import uuid
from datetime import datetime
from pathlib import Path

FEEDBACK_FILE = Path(__file__).parent / "feedback_log.json"

def save_feedback(session_id: str, user_message: str, eva_response: str, category: str = "general"):
    entry = {
        "id": str(uuid.uuid4()),
        "session_id": session_id,
        "timestamp": datetime.now().isoformat(),
        "mensaje_invitado": user_message,
        "respuesta_eva": eva_response,
        "categoria": category,
    }

    existing = []
    if FEEDBACK_FILE.exists():
        with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)

    existing.append(entry)

    with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"[EVA] Feedback guardado — categoría: {category}")
    return entry
