import sys
import io
import traceback
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from google import genai

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


@app.get("/")
def leer_index():
    return FileResponse("index.html")


class CodigoRequest(BaseModel):
    codigo: str


def sanitizar_codigo(codigo_raw: str) -> str:
    if not codigo_raw:
        return ""
    # Reemplaza espacios invisibles (NBSP) por espacios estándar
    codigo = codigo_raw.replace("\xa0", " ").replace("\x00", "").replace("\r\n", "\n")
    codigo = codigo.replace("\t", "    ")
    return codigo


@app.post("/ejecutar")
def ejecutar_codigo(req: CodigoRequest):
    codigo_limpio = sanitizar_codigo(req.codigo)

    # 1. CASO: CÓDIGO VACÍO
    if not codigo_limpio.strip():
        return {
            "exito": False,
            "salida": "Consola vacía.",
            "mensaje_alerta": "Por favor, ingrese el código solicitado antes de ejecutar.",
            "explicacion_ia": None,
        }

    # Redireccionar stdout y stderr para capturar la salida en memoria de forma segura
    buffer_salida = io.StringIO()
    sys.stdout = buffer_salida
    sys.stderr = buffer_salida

    entorno_global = {}
    entorno_local = {}
    error_ocurrido = None

    try:
        # Ejecutar el código Python directamente en el servidor
        exec(codigo_limpio, entorno_global, entorno_local)
    except Exception:
        # Capturar la traza exacta del error si falla la sintaxis o ejecución
        error_ocurrido = traceback.format_exc()
    finally:
        # Restaurar la salida estándar
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

    salida_consola = buffer_salida.getvalue().strip()

    # 2. CASO: ERROR DE SINTAXIS O EJECUCIÓN EN PYTHON
    if error_ocurrido:
        explicacion = "Ocurrió un error al ejecutar tu código."

        if ai_client:
            prompt = (
                f"Eres un tutor de programación en Python amigable y pedagógico.\n"
                f"El alumno escribió este código:\n```python\n{codigo_limpio}\n```\n\n"
                f"El intérprete de Python reportó este error:\n{error_ocurrido}\n\n"
                f"Explícale en español, de forma muy concisa y clara en un solo párrafo, "
                f"exactamente cuál es el error y cómo solucionarlo."
            )
            try:
                ai_res = ai_client.models.generate_content(
                    model="gemini-3.6-flash", contents=prompt
                )
                explicacion = ai_res.text
            except Exception as ex_ia:
                explicacion = f"Error de IA: {str(ex_ia)}"

        return {
            "exito": False,
            "salida": error_ocurrido,
            "explicacion_ia": explicacion,
        }

    # 3. CASO: CÓDIGO CORRECTO CON IMPRESIÓN PANTALLA (print)
    if salida_consola:
        return {
            "exito": True,
            "salida": salida_consola,
            "mensaje": "¡Excelente trabajo! Tu código se ejecutó correctamente.",
            "explicacion_ia": None,
        }

    # 4. CASO: CÓDIGO VÁLIDO PERO SIN IMPRESIÓN
    return {
        "exito": True,
        "salida": "(El código se ejecutó con éxito pero no generó texto en pantalla)",
        "mensaje": "El código es válido. Asegúrate de incluir la función print() para ver resultados en consola.",
        "explicacion_ia": None,
    }