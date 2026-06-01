import asyncio
import json
import os
import threading
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent import SageAgent

app = FastAPI(title="SAGE Agent API")

# El CORS nos permite intercomunicarnos con el FrontEnd por el navegador de manera profesional y segura.
DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def _get_cors_origins() -> list[str]:
    origins_env = os.getenv("CORS_ORIGINS", "")
    if not origins_env.strip():
        return DEFAULT_CORS_ORIGINS
    return [origin.strip() for origin in origins_env.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

agent = SageAgent(
    event_name="Entrega de Diplomas AHK 2026",
    event_location="Centro de Convenciones, Av. Corrientes, Buenos Aires",
    event_date="15 de Agosto de 2026"
)

class MessageRequest(BaseModel):
    mensaje: str

class MessageResponse(BaseModel):
    respuesta: str
    historial_length: int
    estado: str

# el SSE nos sirve para definir cómo van escritas en el Front las distintas respuestas del agente
def _json_sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _resolve_chat_state(respuesta: str) -> str:
    error_prefixes = (
        "Disculpá, tardé demasiado en responder.",
        "Hubo un problema al procesar tu mensaje.",
    )
    if respuesta.startswith(error_prefixes):
        return "error"
    return "hablando"

@app.get("/")
def root():
    return {"status": "EVA online"}

@app.post("/chat", response_model=MessageResponse)
def chat(request: MessageRequest):
    respuesta = agent.chat(request.mensaje)
    return MessageResponse(
        respuesta=respuesta,
        historial_length=len(agent.history),
        estado=_resolve_chat_state(respuesta),
    )

# El Stream nos permite enviar los estados de SPLINE de manera eficiente y sin bloquear la UI, es decir. Sin esto solo tendriamos las respuestas mientras esperamos a que termine de pensar el Ollama.

@app.post("/chat/stream")
async def chat_stream(request: MessageRequest):
    async def event_generator() -> AsyncIterator[str]:
        yield _json_sse({"estado": "pensando"})
        try:
            respuesta = await asyncio.to_thread(agent.chat, request.mensaje)
            estado = _resolve_chat_state(respuesta)
            yield _json_sse(
                {
                    "estado": estado,
                    "respuesta": respuesta,
                    "historial_length": len(agent.history),
                }
            )
        except Exception:
            yield _json_sse(
                {
                    "estado": "error",
                    "respuesta": "Hubo un problema al procesar tu mensaje. Enseguida consulto con el equipo.",
                }
            )
        finally:
            yield _json_sse({"estado": "esperando"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )

@app.post("/reset")
def reset():
    threading.Thread(target=agent.reset).start()
    return {"status": "Sesión reiniciada, warm-up en proceso"}
