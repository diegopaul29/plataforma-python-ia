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
    codigo = codigo_raw.replace("\xa0", " ").replace("\x00", "").replace("\r\n", "\n")
    codigo = codigo.replace("\t", "    ")
    return codigo


def extraer_codigo_alumno(codigo_completo: str) -> str:
    """
    Separa el código escrito por el usuario del encabezado/plantilla inicial.
    """
    marcador = "# Escribe tu código aquí abajo:"
    if marcador in codigo_completo:
        partes = codigo_completo.split(marcador)
        return partes[1].strip()
    return codigo_completo.strip()


@app.post("/ejecutar")
def ejecutar_codigo(req: CodigoRequest):
    codigo_limpio = sanitizar_codigo(req.codigo)
    codigo_alumno = extraer_codigo_alumno(codigo_limpio)

    # 1. CASO: EL ALUMNO NO HA ESCRITO NADA DEBAJO DEL COMENTARIO GUÍA
    if not codigo_alumno:
        return {
            "exito": False,
            "salida": "(Consola vacía)",
            "mensaje_alerta": "ingrese el codigo solicitado",
            "explicacion_ia": None,
        }

    buffer_salida = io.StringIO()
    sys.stdout = buffer_salida
    sys.stderr = buffer_salida

    entorno_global = {}
    entorno_local = {}
    error_ocurrido = None

    try:
        exec(codigo_limpio, entorno_global, entorno_local)
    except Exception:
        error_ocurrido = traceback.format_exc()
    finally:
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__

    salida_consola = buffer_salida.getvalue().strip()

    # 2. CASO: ERROR DE SINTAXIS O EJECUCIÓN
    if error_ocurrido:
        explicacion = "Ocurrió un error al ejecutar tu código."

        if ai_client:
            prompt = (
                f"Eres un tutor de programación en Python amigable y pedagógico.\n"
                f"El alumno escribió este código:\n```python\n{codigo_limpio}\n```\n\n"
                f"El intérprete de Python reportó este error:\n{error_ocurrido}\n\n"
                f"Explícale en español, de forma muy concisa y clara en un solo párrafo, "
                f"exactamente cuál es el error y en qué parte o línea está para que pueda solucionarlo."
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

    # 3. CASO: CÓDIGO VÁLIDO PERO SIN IMPRESIÓN (no hizo print)
    if not salida_consola:
        explicacion = "Tu código no tiene errores de sintaxis, pero no imprimió nada en la consola. Asegúrate de incluir la instrucción print() dentro de tu condición."

        if ai_client:
            prompt = (
                f"El alumno escribió este código en Python:\n```python\n{codigo_limpio}\n```\n\n"
                f"El código no arrojó errores pero tampoco mostró ningún resultado en pantalla.\n"
                f"Explícale amablemente y en un párrafo corto en dónde debe agregar el print() para resolver la instrucción."
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
            "salida": "(Sin salida de pantalla)",
            "explicacion_ia": explicacion,
        }

    # 4. CASO: CÓDIGO CORRECTO CON SALIDA POR PANTALLA
    return {
        "exito": True,
        "salida": salida_consola,
        "mensaje": "¡Excelente trabajo! Tu código se ejecutó correctamente.",
        "explicacion_ia": None,
    }