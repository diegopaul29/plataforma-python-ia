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

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "TU_API_KEY_DE_GEMINI_AQUI")
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

        # Detección de errores en Python (SyntaxError, NameError, etc.)
        hay_error = (
            bool(stderr)
            or "Traceback" in output
            or "Error:" in output
            or "SyntaxError" in output
        )

        # Si hay un error explícito o la salida está totalmente vacía
        if hay_error or not output:
            mensaje_error = stderr if stderr else output
            if not mensaje_error:
                mensaje_error = (
                    "El código no produjo ninguna salida ni imprimió nada en consola."
                )

            prompt = (
                f"Eres un profesor de Python para principiantes. El alumno escribió este código:\n"
                f"```python\n{req.codigo}\n```\n"
                f"Y el resultado/error de ejecución fue:\n{mensaje_error}\n\n"
                f"Explícale en español, de forma muy sencilla y amable, dónde está el error en su código "
                f"(o indícale qué debe escribir si no ha completado el ejercicio) y cómo solucionarlo."
            )

            try:
                ai_res = ai_client.models.generate_content(
                    model="gemini-2.5-flash", contents=prompt
                )
                explicacion = ai_res.text
            except Exception as ex_ia:
                explicacion = (
                    f"No se pudo consultar al Tutor IA (Verifica tu API Key). Detalle: {str(ex_ia)}"
                )

            return {
                "exito": False,
                "salida": output if output else "Sin salida de consola",
                "error": mensaje_error,
                "explicacion_ia": explicacion,
            }

        return {"exito": True, "salida": output, "explicacion_ia": None}

    except Exception as e:
        return {
            "exito": False,
            "salida": "Error de servidor",
            "explicacion_ia": f"Ocurrió un problema en el backend: {str(e)}",
        }