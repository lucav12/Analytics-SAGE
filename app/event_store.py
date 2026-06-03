from pathlib import Path
import json

EVENT_FILE = Path(__file__).parent / "current_event.json"

DEFAULT_EVENT = {
    "id": "ahk-2026",
    "nombre": "Entrega de Diplomas AHK 2026",
    "fecha": "15 de Agosto de 2026",
    "ubicacion": "Centro de Convenciones, Av. Corrientes, Buenos Aires",
    "tipo": "entrega de diplomas",
    "institucion": "AHK",
    "descripcion": "Ceremonia de reconocimiento a egresados de Sistemas IT y Data Science por finalizar su formación.",
    "asistente": {
        "nombre": "EVA",
        "nombre_completo": "Asistente Virtual de Eventos",
        "idioma": "es-AR",
        "tono": "amable, claro y profesional",
        "max_oraciones": 3
    },
    "proyecto": {
        "nombre": "SAGE",
        "nombre_completo": "Sistema de Administración y Gestión de Eventos"
    },
    "venue": {
        "entrada_principal": "Planta baja, frente a Av. Corrientes",
        "recepcion": "Planta baja, mostrador central",
        "guardarropa": "Planta baja, a la izquierda de la entrada",
        "salon_principal": "Primer piso, Salón A",
        "banos": "Planta baja a la derecha de la entrada; primer piso al fondo del pasillo",
        "salidas_emergencia": "Planta baja, puerta lateral izquierda señalizada en verde; primer piso, escalera al fondo del Salón A"
    },
    "agenda": [
        {"hora": "18:00", "descripcion": "Acreditación y recepción"},
        {"hora": "18:30", "descripcion": "Bienvenida institucional"},
        {"hora": "18:45", "descripcion": "Palabras de autoridades"},
        {"hora": "19:00", "descripcion": "Entrega de diplomas"},
        {"hora": "19:45", "descripcion": "Foto grupal"},
        {"hora": "20:00", "descripcion": "Networking y catering"},
        {"hora": "21:00", "descripcion": "Cierre estimado"}
    ],
    "faqs": [
        {"pregunta": "¿Cuál es el código de vestimenta?", "respuesta": "Formal o smart casual"},
        {"pregunta": "¿Cuánto dura el evento?", "respuesta": "Aproximadamente 3 horas"},
        {"pregunta": "¿Se sacan fotos?", "respuesta": "Se tomarán fotos durante la ceremonia y una foto grupal luego de la entrega"},
        {"pregunta": "¿Hay catering?", "respuesta": "Sí, disponible durante el espacio de networking a partir de las 20:00"},
        {"pregunta": "¿Puedo traer acompañantes?", "respuesta": "Los invitados acreditados pueden ingresar y participar de la ceremonia"}
    ],
    "few_shot_examples": [
        {
            "pregunta": "¿Puedo subir con mi hijo a recibir el diploma?",
            "respuesta": "Esa información no la tengo disponible, pero podés consultarla con el equipo en el mostrador de recepción."
        },
        {
            "pregunta": "¿Cuántas personas hay en el evento?",
            "respuesta": "Esa información no la tengo disponible, pero podés consultarla con el equipo en el mostrador de recepción."
        },
        {
            "pregunta": "¿Hay estacionamiento?",
            "respuesta": "Esa información no la tengo disponible, pero podés consultarla con el equipo en el mostrador de recepción."
        },
        {
            "pregunta": "¿Hay wifi?",
            "respuesta": "Esa información no la tengo disponible, pero podés consultarla con el equipo en el mostrador de recepción."
        },
        {
            "pregunta": "¿A qué hora termina el evento?",
            "respuesta": "El cierre estimado es a las 21:00 hs."
        }
    ],
    "informacion_adicional": [
        {
            "titulo": "Egresados de Sistemas IT",
            "contenido": "1. Valentina Ríos | Área: Frontend | Rol: interfaz web de gestión | Hobbies: diseño gráfico, fotografía | Dato curioso: empezó sin saber programar y terminó liderando el diseño del sistema\n2. Mateo Gutiérrez | Área: Backend | Rol: API principal y base de datos | Hobbies: ajedrez, ciclismo | Dato curioso: resolvió un bug crítico durante el recreo de un parcial\n3. Lucía Paredes | Área: Gestión | Rol: coordinación y documentación técnica | Hobbies: ciencia ficción, running | Dato curioso: mantuvo el tablero del proyecto actualizado todos los días sin faltar uno\n4. Ignacio Herrera | Área: Backend | Rol: autenticación y generación de QR | Hobbies: música electrónica, cocina | Dato curioso: generó más de 500 QRs de prueba durante el desarrollo\n5. Sofía Ibáñez | Área: Frontend | Rol: avatar visual y animaciones | Hobbies: ilustración digital, videojuegos | Dato curioso: diseñó tres versiones del avatar antes de llegar a la definitiva\n6. Tomás Acuña | Área: Gestión | Rol: gestión de invitados y envío de emails | Hobbies: fotografía, senderismo | Dato curioso: automatizó el envío de 200 invitaciones en menos de un minuto\n7. Renata Flores | Área: Frontend | Rol: dashboard de métricas | Hobbies: yoga, cerámica | Dato curioso: convirtió una hoja de cálculo enorme en un dashboard interactivo en una semana\n8. Nicolás Vargas | Área: Backend | Rol: integración con servicios externos | Hobbies: robótica, natación | Dato curioso: construyó un brazo robótico como proyecto personal mientras cursaba"
        },
        {
            "titulo": "Egresados de Data Science",
            "contenido": "1. Martina Solís | Área: Analítica | Rol: análisis de permanencia y movimiento | Hobbies: astronomía, caminatas | Dato curioso: procesó más de 10.000 registros de prueba para calibrar el modelo\n2. Agustín Peralta | Área: Inteligencia Artificial | Rol: asistente conversacional EVA | Hobbies: filosofía, escalada | Dato curioso: evaluó cinco modelos de lenguaje antes de elegir el stack final\n3. Camila Juárez | Área: Analítica | Rol: análisis de sentimiento del feedback | Hobbies: piano, escritura | Dato curioso: su modelo de sentimiento superó el baseline en el primer intento\n4. Luca Ferreyra | Área: Analítica | Rol: pipeline de datos y heatmaps | Hobbies: cocina italiana, tenis | Dato curioso: encontró un patrón en los datos de prueba que nadie había notado\n5. Abril Méndez | Área: Inteligencia Artificial | Rol: speech-to-text y text-to-speech | Hobbies: podcasts de tecnología, natación | Dato curioso: redujo la latencia del pipeline de voz a menos de dos segundos\n6. Santiago Romero | Área: Gestión | Rol: métricas y reportes finales | Hobbies: ajedrez, ciclismo urbano | Dato curioso: automatizó el reporte final en un script de menos de 50 líneas\n7. Julieta Vázquez | Área: Analítica | Rol: datos de cámaras y sensores | Hobbies: fotografía analógica, origami | Dato curioso: calibró el sistema de detección usando videos del pasillo de la facultad"
        }
    ],
    "reglas_adicionales": [
        "No dar información de participantes de eventos o carreras no listadas en este prompt"
    ],
    "respuesta_sin_datos": "Esa información no la tengo disponible, pero podés consultarla con el equipo en el mostrador de recepción."
}

def get_current_event() -> dict:
    if EVENT_FILE.exists():
        with open(EVENT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_EVENT

def save_event(event_data: dict):
    with open(EVENT_FILE, "w", encoding="utf-8") as f:
        json.dump(event_data, f, ensure_ascii=False, indent=2)
    print(f"[EVA] Evento guardado: {event_data.get('nombre', '')}")
