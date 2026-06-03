from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

import asyncio
import json
import os
import threading
from typing import AsyncIterator
import subprocess
import tempfile
from fastapi.responses import FileResponse
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from prompt_builder import build_prompt
from event_store import get_current_event, save_event
from prompts import get_prompt

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

agent = None

PROMPT_SOURCE = os.getenv("PROMPT_SOURCE", "hardcoded")

@app.on_event("startup")
async def startup():
    global agent
    if PROMPT_SOURCE == "dynamic":
        print("[EVA] Usando prompt dinámico desde event_store")
        event_data = get_current_event()
        system_prompt = build_prompt(event_data)
    else:
        print("[EVA] Usando prompt hardcodeado desde prompts.py")
        system_prompt = get_prompt(
            event_name="Entrega de Diplomas AHK 2026",
            event_location="Centro de Convenciones, Av. Corrientes, Buenos Aires",
            event_date="15 de Agosto de 2026"
        )
    agent = SageAgent(system_prompt=system_prompt)
    threading.Thread(target=_background_warmup, daemon=True).start()

def _background_warmup():
    import asyncio
    asyncio.run(warmup_piper())

async def warmup_piper():
    try:
        print("[EVA TTS] Primeando Piper...")
        process = subprocess.run(
            [PIPER_BIN, "--model", PIPER_MODEL, "--output_file", "/tmp/warmup.wav"],
            input="hola".encode(),
            capture_output=True
        )
        if process.returncode == 0:
            print("[EVA TTS] Piper listo.")
        else:
            print("[EVA TTS] Warmup de Piper falló.")
    except Exception as e:
        print(f"[EVA TTS] Error en warmup: {e}")

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

PIPER_BIN = os.getenv("PIPER_BIN", "/home/martin/piper/piper/piper")
PIPER_MODEL = os.getenv("PIPER_MODEL", "/home/martin/piper/models/es_AR-daniela-high.onnx")

class TTSRequest(BaseModel):
    texto: str

@app.get("/eventos/actual")
def get_evento_actual():
    return get_current_event()

@app.post("/configure")
async def configure(event_data: dict):
    global agent
    save_event(event_data)
    new_prompt = build_prompt(event_data)
    agent = SageAgent(system_prompt=new_prompt)
    threading.Thread(target=warmup_piper).start()
    print(f"[EVA] Reconfigurada para: {event_data.get('nombre', '')}")
    return {"status": f"EVA configurada para {event_data.get('nombre', '')}"}

@app.post("/tts")
async def tts(request: TTSRequest):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        output_path = f.name

    process = subprocess.run(
        [PIPER_BIN, "--model", PIPER_MODEL, "--output_file", output_path],
        input=request.texto.encode(),
        capture_output=True
    )

    if process.returncode != 0:
        return {"error": "TTS falló"}

    return FileResponse(
        output_path,
        media_type="audio/wav",
        filename="eva_tts.wav",
        background=None
    )

@app.post("/reset")
def reset():
    threading.Thread(target=agent.reset).start()
    return {"status": "Sesión reiniciada, warm-up en proceso"}
