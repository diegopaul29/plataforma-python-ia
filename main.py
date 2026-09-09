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
ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


@app.get("/")
def leer_index():
    return FileResponse("index.html")


class CodigoRequest(BaseModel):
    codigo: str


def sanitizar_codigo(codigo_raw: str) -> str:
    """
    Limpia el código proveniente de Monaco Editor:
    - Reemplaza Non-Breaking Spaces (\xa0) y caracteres nulos por espacios normales.
    - Normaliza saltos de línea (\r\n -> \n).
    - Convierte pestañas (tabs) en 4 espacios para evitar TabError/IndentationError.
    """
    if not codigo_raw:
        return ""
    codigo = codigo_raw.replace("\xa0", " ").replace("\x00", "").replace("\r\n", "\n")
    codigo = codigo.replace("\t", "    ")
    return codigo


@app.post("/ejecutar")
def ejecutar_codigo(req: CodigoRequest):
    codigo_limpio = sanitizar_codigo(req.codigo)
    codigo_trim = codigo_limpio.strip()

    # 1. CASO: El usuario no escribió código o mandó solo espacios/comentarios
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
        "files": [{"content": codigo_limpio}],
    }

    try:
        res = requests.post(piston_url, json=payload, timeout=10).json()
        run_data = res.get("run", {})
        stdout = run_data.get("stdout", "").strip()
        stderr = run_data.get("stderr", "").strip()
        output = run_data.get("output", "").strip()
        exit_code = run_data.get("code", 0)

        # Determinar si ocurrió un error real de compilación o ejecución en Python
        errores_python = [
            "SyntaxError",
            "IndentationError",
            "NameError",
            "TypeError",
            "TabError",
            "ValueError",
            "AttributeError",
            "Traceback",
        ]

        es_error = exit_code != 0 or bool(stderr) or any(err in output for err in errores_python)

        # 2. CASO: Error de ejecución o sintaxis real -> Llamar a la IA para explicar la falla
        if es_error:
            detalle_error = stderr if stderr else output
            
            explicacion = "Se detectó un error en tu código."
            if ai_client:
                prompt = (
                    f"Eres un tutor de Python amigable para estudiantes de programación.\n"
                    f"El alumno escribió el siguiente código:\n```python\n{codigo_limpio}\n```\n\n"
                    f"La consola arrojó este error:\n{detalle_error}\n\n"
                    f"Explícale en español, de forma muy concisa y clara, EXACTAMENTE en qué línea o parte "
                    f"está el error y cómo puede corregirlo."
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
                "salida": detalle_error,
                "error": detalle_error,
                "explicacion_ia": explicacion,
            }

        # 3. CASO: Ejecución correcta con salida en consola (print)
        if stdout or output:
            return {
                "exito": True,
                "salida": stdout if stdout else output,
                "mensaje": "¡Excelente trabajo! Tu código se ejecutó correctamente.",
                "explicacion_ia": None,
            }

        # 4. CASO: El código no tiene errores pero tampoco usó print()
        return {
            "exito": True,
            "salida": "(El código se ejecutó con éxito pero no generó texto en pantalla)",
            "mensaje": "¡El código es válido! Recuerda agregar un print() para ver resultados.",
            "explicacion_ia": None,
        }

    except Exception as e:
        return {
            "exito": False,
            "salida": "Error de servidor",
            "explicacion_ia": f"No se pudo conectar al ejecutor de código: {str(e)}",
        }