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
    codigo_limpio = req.codigo.strip()

    # CASO 1: El usuario no escribió nada o mandó el editor vacío
    if not codigo_limpio:
        return {
            "exito": False,
            "salida": "Advertencia: No hay código para ejecutar.",
            "mensaje_alerta": "Por favor, ingrese el código solicitado antes de ejecutar.",
            "explicacion_ia": None,
        }

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
        exit_code = run_data.get("code", 0)

        # CASO 2: Ocurrió un error de ejecución/sintaxis O no se imprimió ninguna salida
        hay_error = (
            exit_code != 0
            or bool(stderr)
            or "Traceback" in output
            or "SyntaxError" in output
            or "NameError" in output
            or "TypeError" in output
            or "IndentationError" in output
            or not output  # Si no hay print, se considera incompleto y la IA le ayuda
        )

        if hay_error:
            # Construir el detalle del problema para que la IA dé una respuesta precisa
            if not output and not stderr:
                detalle_problema = "El código se ejecutó pero no imprimió ningún texto en consola. Falta usar la función print() o la condición del 'if' no se cumplió."
            else:
                detalle_problema = stderr if stderr else output

            prompt = (
                f"Eres un profesor de Python paciente y amigable para principiantes.\n"
                f"El alumno intentó resolver un ejercicio con este código:\n"
                f"```python\n{req.codigo}\n```\n\n"
                f"El problema o mensaje del sistema fue:\n{detalle_problema}\n\n"
                f"Por favor, explica en español, de forma muy sencilla, concisa y clara, "
                f"en dónde está el error en su código y cómo puede solucionarlo."
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
                "salida": output if output else "Sin salida de pantalla.",
                "error": detalle_problema,
                "explicacion_ia": explicacion,
            }

        # CASO 3: El código está bien y generó salida correctamente
        return {
            "exito": True,
            "salida": output,
            "mensaje": "¡Excelente trabajo! Tu código se ejecutó correctamente.",
            "explicacion_ia": None,
        }

    except Exception as e:
        return {
            "exito": False,
            "salida": "Error de conexión",
            "explicacion_ia": f"Ocurrió un problema en el servidor: {str(e)}",
        }