import os
import requests
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
ai_client = genai.Client(api_key=GEMINI_API_KEY)


@app.get("/")
def leer_index():
    return FileResponse("index.html")


class CodigoRequest(BaseModel):
    codigo: str


@app.post("/ejecutar")
def ejecutar_codigo(req: CodigoRequest):
    piston_url = "https://emkc.org/api/v2/piston/execute"
    payload = {
        "language": "python",
        "version": "3.10.0",
        "files": [{"content": req.codigo}],
    }

    try:
        res = requests.post(piston_url, json=payload, timeout=10).json()
        run_data = res.get("run", {})
        output = run_data.get("output", "").strip()
        stderr = run_data.get("stderr", "").strip()

        # Se considera error solo si Piston retorna código de salida distinto de 0 o mensajes explicitos de error
        hay_error = (
            bool(stderr)
            or "Traceback" in output
            or "SyntaxError" in output
            or "NameError" in output
            or "TypeError" in output
        )

        if hay_error:
            mensaje_error = stderr if stderr else output

            prompt = (
                f"Eres un profesor de Python para principiantes. El alumno escribió este código:\n"
                f"```python\n{req.codigo}\n```\n"
                f"Y ocurrió el siguiente error:\n{mensaje_error}\n\n"
                f"Explícale en español, de forma muy sencilla y breve, cuál es el error y cómo solucionarlo."
            )

            try:
                ai_res = ai_client.models.generate_content(
                    model="gemini-3.6-flash", contents=prompt
                )
                explicacion = ai_res.text
            except Exception as ex_ia:
                explicacion = f"Error al consultar la IA: {str(ex_ia)}"

            return {
                "exito": False,
                "salida": output,
                "error": mensaje_error,
                "explicacion_ia": explicacion,
            }

        # Si no hubo errores, retornar éxito directo sin llamar a la IA
        mensaje_exito = "¡Excelente trabajo! Tu código se ejecutó correctamente."
        return {
            "exito": True,
            "salida": output if output else "Ejecutado sin salida de texto.",
            "mensaje": mensaje_exito,
            "explicacion_ia": None,
        }

    except Exception as e:
        return {
            "exito": False,
            "salida": "Error de servidor",
            "explicacion_ia": f"Ocurrió un problema en el backend: {str(e)}",
        }