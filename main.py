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


def limpiar_codigo_python(raw_code: str) -> str:
    """
    Reemplaza espacios invisibles/NBSP (\xa0) por espacios normales (\x20)
    y normaliza saltos de línea para evitar errores de sangría en Python.
    """
    if not raw_code:
        return ""
    # Convertir caracteres de espacio no separable (NBSP) a espacio estándar
    codigo_limpio = raw_code.replace("\xa0", " ").replace("\r\n", "\n")
    return codigo_limpio


@app.post("/ejecutar")
def ejecutar_codigo(req: CodigoRequest):
    # 1. Normalizar y sanitizar el código de caracteres invisibles del editor
    codigo_sanitizado = limpiar_codigo_python(req.codigo)
    codigo_trim = codigo_sanitizado.strip()

    # CASO 1: Código vacío
    if not codigo_trim:
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
        "files": [{"content": codigo_sanitizado}],
    }

    try:
        res = requests.post(piston_url, json=payload, timeout=10).json()
        run_data = res.get("run", {})
        output = run_data.get("output", "").strip()
        stderr = run_data.get("stderr", "").strip()
        exit_code = run_data.get("code", 0)

        # Determinar si la ejecución falló realmente
        errores_conocidos = [
            "SyntaxError",
            "IndentationError",
            "NameError",
            "TypeError",
            "TabError",
            "Traceback",
        ]
        tiene_error_sintaxis = exit_code != 0 or any(
            err in stderr or err in output for err in errores_conocidos
        )

        # CASO 2: Hay un error explícito en Python
        if tiene_error_sintaxis:
            detalle_error = stderr if stderr else output
            prompt = (
                f"Eres un tutor amigable de Python para principiantes.\n"
                f"El alumno escribió el siguiente código:\n```python\n{codigo_sanitizado}\n```\n\n"
                f"Ocurrió este error al ejecutarlo:\n{detalle_error}\n\n"
                f"Explica brevemente y de forma sencilla qué falló y cómo solucionarlo sin dar la respuesta completa directamente."
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
                "salida": output if output else stderr,
                "error": detalle_error,
                "explicacion_ia": explicacion,
            }

        # CASO 3: Se ejecutó sin error pero no produjo ninguna salida por consola (print)
        if not output:
            prompt = (
                f"El alumno ejecutó este código en Python:\n```python\n{codigo_sanitizado}\n```\n"
                f"El código no dio ningún error pero tampoco imprimió nada en pantalla.\n"
                f"Explícale amablemente que debe usar la función print() o revisar la condición para ver salida en consola."
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
                "salida": "Sin salida de pantalla.",
                "explicacion_ia": explicacion,
            }

        # CASO 4: ¡Éxito! Imprimiendo salida correcta
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
            "explicacion_ia": f"Ocurrió un problema de red o servidor: {str(e)}",
        }