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
    if not codigo_raw:
        return ""
    # Reemplaza caracteres invisibles de sangría que Monaco genera (NBSP)
    codigo = codigo_raw.replace("\xa0", " ").replace("\x00", "").replace("\r\n", "\n")
    codigo = codigo.replace("\t", "    ")
    return codigo


@app.post("/ejecutar")
def ejecutar_codigo(req: CodigoRequest):
    codigo_limpio = sanitizar_codigo(req.codigo)
    
    # 1. VALIDACIÓN DE CÓDIGO VACÍO
    if not codigo_limpio.strip():
        return {
            "exito": False,
            "salida": "Consola vacía.",
            "mensaje_alerta": "Ingrese el código solicitado antes de ejecutar.",
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
        
        # Piston puede enviar un error global en la raíz si la API falla
        if "message" in res and "run" not in res:
            return {
                "exito": False,
                "salida": "Error de servicio Piston",
                "explicacion_ia": res.get("message"),
            }

        run_data = res.get("run", {})
        stdout = run_data.get("stdout", "")
        stderr = run_data.get("stderr", "")
        output = run_data.get("output", "")
        exit_code = run_data.get("code", 0)

        # Unificar todo el texto retornado para inspección
        texto_completo = f"{stdout}\n{stderr}\n{output}"

        # Palabras clave que indican indiscutiblemente un error de Python
        indicadores_error = [
            "SyntaxError:",
            "IndentationError:",
            "NameError:",
            "TypeError:",
            "TabError:",
            "ValueError:",
            "AttributeError:",
            "ZeroDivisionError:",
            "IndexError:",
            "KeyError:",
            "Traceback (most recent call last):",
        ]

        # Comprobación de error
        hay_error_python = (
            exit_code != 0
            or bool(stderr.strip())
            or any(err in texto_completo for err in indicadores_error)
        )

        # 2. ESCENARIO DE ERROR: Consultar a Gemini para explicar la falla
        if hay_error_python:
            mensaje_error = stderr.strip() if stderr.strip() else output.strip()
            
            explicacion = "Ocurrió un error en la ejecución de tu código."
            if ai_client:
                prompt = (
                    f"Eres un tutor de programación en Python amigable y claro.\n"
                    f"El alumno escribió el siguiente código:\n```python\n{codigo_limpio}\n```\n\n"
                    f"El intérprete de Python devolvió este mensaje de error:\n{mensaje_error}\n\n"
                    f"Explícale en español, de forma concisa y en un solo párrafo, exactamente "
                    f"qué está mal en su código (ejemplo: falta de dos puntos, mala sangría, variable no definida) "
                    f"y cómo corregirlo."
                )
                try:
                    ai_res = ai_client.models.generate_content(
                        model="gemini-3.6-flash", contents=prompt
                    )
                    explicacion = ai_res.text
                except Exception as ex_ia:
                    explicacion = f"Error al generar explicación: {str(ex_ia)}"

            return {
                "exito": False,
                "salida": mensaje_error,
                "explicacion_ia": explicacion,
            }

        # 3. ESCENARIO DE ÉXITO CON IMPRESIÓN (print)
        salida_pantalla = stdout.strip() if stdout.strip() else output.strip()
        
        if salida_pantalla:
            return {
                "exito": True,
                "salida": salida_pantalla,
                "mensaje": "¡Excelente trabajo! Tu código se ejecutó correctamente.",
                "explicacion_ia": None,
            }

        # 4. ESCENARIO DE ÉXITO SIN IMPRESIÓN
        # (El código no falló pero el usuario no colocó print() o la condición if evaluó en False)
        return {
            "exito": True,
            "salida": "(El código no produjo ninguna salida en consola)",
            "mensaje": "El código se ejecutó sin errores, pero no imprimió nada. Verifica que la condición del 'if' se cumpla o que estés usando print().",
            "explicacion_ia": None,
        }

    except Exception as e:
        return {
            "exito": False,
            "salida": "Error de conexión",
            "explicacion_ia": f"Ocurrió un problema de red o servidor: {str(e)}",
        }