import glob
import json
import os
import time
import urllib.parse
from google import genai
from google.genai import types
import requests

# Credenciales automáticas desde GitHub
SERPER_API_KEY = os.environ.get("SERPER_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO = os.environ.get("GITHUB_REPOSITORY")
USUARIO = os.environ.get("GITHUB_ACTOR")

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
    for item in res.json().get("organic", []):
      ofertas_crudas.append({
          "titulo": item.get("title", ""),
          "link": item.get("link", ""),
          "snippet": item.get("snippet", ""),
      })

print(f"Se encontraron {len(ofertas_crudas)} ofertas en bruto.")

# 3. Preparar el prompt en una sola llamada
prompt = (
    "Analiza la siguiente lista de vacantes o páginas de empresas:\n"
    f"{json.dumps(ofertas_crudas, ensure_ascii=False, indent=2)}\n\n"
    f"Mi CV actual en el repositorio:\n{cv_base[:6000]}\n\n"
    "REGLAS DE FILTRADO:\n"
    '1. Si la oferta está en inglés o exige "Inglés fluido / C1 / High English"'
    " excluyente, DESCÁRTALA.\n"
    "2. Si exige colegiación obligatoria en España para litigar en juzgados"
    " (procesal puro), DESCÁRTALA.\n"
    "3. Selecciona las ofertas en español que busquen LegalOps, Compliance,"
    " RGPD, IA, Contratos, Consultoría o Innovación Legal.\n\n"
    "Devuelve ÚNICAMENTE un objeto JSON válido con una lista llamada"
    ' "ofertas_seleccionadas" con esta estructura exacta:\n'
    "{\n"
    '  "ofertas_seleccionadas": [\n'
    "    {\n"
    '      "empresa_o_rol": "Nombre del puesto y empresa",\n'
    '      "link": "URL original de la oferta",\n'
    '      "asunto_correo": "Asunto atractivo para postular o contactar",\n'
    '      "mensaje_postulacion": "Carta/mensaje corto, directo y persuasivo en'
    " español adaptado a esta oferta e incluyendo mi portafolio"
    ' https://github.com/barbarapiccolo/cvlegal",\n'
    '      "puntos_clave_cv": "3 puntos de mi CV reescritos con las palabras'
    ' clave de esta oferta"\n'
    "    }\n"
    "  ]\n"
    "}"
)

# Detectar automáticamente todos los modelos Gemini disponibles en tu cuenta para saltar si uno da 503
modelos_disponibles = []
try:
  for m in client.models.list():
    nombre = m.name.replace("models/", "")
    if (
        "gemini" in nombre
        and "embedding" not in nombre
        and "vision" not in nombre
        and "imagen" not in nombre
        and "veo" not in nombre
        and "audio" not in nombre
        and "tts" not in nombre
    ):
      modelos_disponibles.append(nombre)
except Exception as e:
  print(f"Aviso listando modelos: {e}")

# Ordenar priorizando modelos ligeros/rápidos (lite/flash) que nunca se saturan
modelos_ordenados = sorted(
    modelos_disponibles,
    key=lambda x: (0 if "lite" in x else (1 if "flash" in x else 2)),
)
if not modelos_ordenados:
  modelos_ordenados = [
      "gemini-3.8-flash-lite",
      "gemini-3.8-flash",
      "gemini-3.8-pro",
      "gemini-2.0-flash",
  ]

print(f"Modelos en cola de respaldo anti-503: {modelos_ordenados[:6]}")

resultado = {"ofertas_seleccionadas": []}
for modelo_actual in modelos_ordenados[:6]:
  try:
    print(f"Probando con modelo: {modelo_actual}...")
    respuesta = client.models.generate_content(
        model=modelo_actual,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        ),
    )
    resultado = json.loads(respuesta.text)
    print(f"✅ ¡Análisis completado con éxito usando {modelo_actual}!")
    break
  except Exception as e:
    print(f"⚠️ {modelo_actual} ocupado o no compatible ({e}). Saltando al siguiente...")
    time.sleep(5)

# 4. Crear una tarjeta (Issue) en GitHub por cada oferta aprobada
seleccionadas = resultado.get("ofertas_seleccionadas", [])
print(f"Creando {len(seleccionadas)} tarjetas en GitHub Issues...")

for of in seleccionadas:
  asunto_encoded = urllib.parse.quote(of.get("asunto_correo", ""))
  cuerpo_encoded = urllib.parse.quote(of.get("mensaje_postulacion", ""))
  link_mailto = f"mailto:?subject={asunto_encoded}&body={cuerpo_encoded}"

  cuerpo_issue = (
      f"🔔 Hola @{USUARIO}, encontré una oferta en español ideal para tu"
      " perfil:\n\n### 🎯 Oferta Detectada\n**Rol / Empresa:**"
      f" {of.get('empresa_o_rol')}\n🔗 **[Ver Oferta"
      f" Original]({of.get('link')})**\n\n---\n\n### ✉️ Mensaje Listo para"
      " Enviar o Pegar\n> **Asunto sugerido:**"
      f" {of.get('asunto_correo')}\n\n```text\n"
      f"{of.get('mensaje_postulacion')}\n```\n\n🚀 **[Toca aquí desde el"
      " móvil para abrir tu Correo con el texto ya"
      f" pegado]({link_mailto})**\n\n---\n\n### 🛠️ Ajuste sugerido para tu CV"
      f" en esta oferta:\n{of.get('puntos_clave_cv')}"
  )

  res_issue = requests.post(
      f"https://api.github.com/repos/{REPO}/issues",
      headers={
          "Authorization": f"Bearer {GITHUB_TOKEN}",
          "Accept": "application/vnd.github+json",
      },
      json={
          "title": f"💼 Oferta: {of.get('empresa_o_rol')}",
          "body": cuerpo_issue,
          "assignees": [USUARIO],
      },
  )
  print(
      f"Issue creado para {of.get('empresa_o_rol')}: Status"
      f" {res_issue.status_code}"
  )
