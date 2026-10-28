import glob
import json
import os
import urllib.parse
from google import genai
from google.genai import types
import requests

# Credenciales automáticas desde GitHub
SERPER_API_KEY = os.environ.get("SERPER_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO = os.environ.get("GITHUB_REPOSITORY")  # barbarapiccolo/cvlegal
USUARIO = os.environ.get("GITHUB_ACTOR")  # barbarapiccolo

client = genai.Client(api_key=GEMINI_API_KEY)

# 1. Leer automáticamente el CV que ya tienes en tu repositorio cvlegal
cv_base = ""
for archivo in glob.glob("*.md") + glob.glob("*.html") + glob.glob("*.txt"):
  with open(archivo, "r", encoding="utf-8", errors="ignore") as f:
    cv_base += f"\n--- Contenido de {archivo} ---\n" + f.read()

# 2. Búsqueda quirúrgica en Google España / Remoto en Español
queries = [
    (
        '"Legal Operations" OR "LegalOps" ("España" OR "Madrid" OR "Barcelona"'
        ' OR "Remoto") empleo'
    ),
    (
        '("RGPD" OR "Privacidad" OR "Compliance") AND "Inteligencia Artificial"'
        " empleo España"
    ),
    (
        '"Abogado" OR "Jurista" ("LegalTech" OR "Innovación Legal" OR'
        ' "Automatización") España'
    ),
]

ofertas_crudas = []
for q in queries:
  res = requests.post(
      "https://google.serper.dev/search",
      headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
      json={"q": q, "gl": "es", "hl": "es", "tbs": "qdr:w", "num": 4},
  )
  if res.status_code == 200:
    ofertas_crudas.extend(res.json().get("organic", []))

# 3. Filtrar con Gemini usando tu CV real de cvlegal
for item in ofertas_crudas:
  titulo = item.get("title", "")
  link = item.get("link", "")
  snippet = item.get("snippet", "")

  prompt = f"""
    Analiza esta vacante o página de empresa:
    Título: {titulo}
    Resumen: {snippet}
    Link: {link}

    Mi CV actual en el repositorio:
    {cv_base[:6000]}

    REGLAS ESTRICTAS DE FILTRADO:
    1. Si la oferta está en inglés o exige "Inglés fluido / C1 / High English" excluyente, DESCÁRTALA (aceptada: false).
    2. Si exige colegiación obligatoria en España para litigar en juzgados (procesal puro), DESCÁRTALA (aceptada: false).
    3. Si es en español y busca LegalOps, Compliance, RGPD, IA, Contratos o Innovación Legal, ACÉPTALA (aceptada: true).

    Devuelve ÚNICAMENTE un objeto JSON válido con esta estructura exacta:
    {{
      "aceptada": true,
      "empresa_o_rol": "Nombre del puesto y empresa",
      "asunto_correo": "Asunto atractivo para postular o contactar",
      "mensaje_postulacion": "Carta/mensaje corto, directo y persuasivo en español adaptado a esta oferta e incluyendo el link a mi portafolio https://github.com/barbarapiccolo/cvlegal",
      "puntos_clave_cv": "3 puntos de mi CV reescritos con las palabras clave exactas de esta oferta"
    }}
    """

  try:
    respuesta = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        ),
    )
    resultado = json.loads(respuesta.text)
  except Exception as e:
    print(f"Error procesando oferta: {e}")
    continue

  # 4. Si pasa el filtro, crea la tarjeta (Issue) y dispara notificación a tu móvil
  if resultado.get("aceptada"):
    asunto_encoded = urllib.parse.quote(resultado["asunto_correo"])
    cuerpo_encoded = urllib.parse.quote(resultado["mensaje_postulacion"])
    link_mailto = f"mailto:?subject={asunto_encoded}&body={cuerpo_encoded}"

    cuerpo_issue = f"""🔔 Hola @{USUARIO}, encontré una oferta en español ideal para tu perfil:

### 🎯 Oferta Detectada
**Rol / Empresa:** {resultado['empresa_o_rol']}
🔗 **[Ver Oferta Original]({link})**

---

### ✉️ Mensaje Listo para Enviar o Pegar
> **Asunto sugerido:** {resultado['asunto_correo']}

```text
{resultado['mensaje_postulacion']}
