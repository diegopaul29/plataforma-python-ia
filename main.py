import os
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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

# Se recomienda usar variable de entorno en Render para proteger la API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "TU_API_KEY_DE_GEMINI_AQUI")
ai_client = genai.Client(api_key=GEMINI_API_KEY)


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
        output = run_data.get("output", "")
        stderr = run_data.get("stderr", "")

        if stderr:
            prompt = (
                f"Eres un profesor de Python. Analiza este codigo: {req.codigo} "
                f"y este error: {stderr}. Indica el numero de linea exacto y la explicacion."
            )
            ai_res = ai_client.models.generate_content(
                model="gemini-2.5-flash", contents=prompt
            )
            return {
                "exito": False,
                "salida": output,
                "error": stderr,
                "explicacion_ia": ai_res.text,
            }

        return {"exito": True, "salida": output, "explicacion_ia": None}

    except Exception as e:
        return {"exito": False, "salida": "Error", "explicacion_ia": str(e)}