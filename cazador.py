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

# 1. Leer automáticamente el CV en tu repositorio cvlegal
cv_base = ""
for archivo in glob.glob("*.md") + glob.glob("*.html") + glob.glob("*.txt"):
  with open(archivo, "r", encoding="utf-8", errors="ignore") as f:
    cv_base += f"\n--- Contenido de {archivo} ---\n" + f.read()

# 1.5 Obtener Issues ya creados para NO repetir ofertas nunca
links_existentes = set()
try:
  res_issues = requests.get(
      f"https://api.github.com/repos/{REPO}/issues?state=all&per_page=100",
      headers={"Authorization": f"Bearer {GITHUB_TOKEN}"},
  )
  if res_issues.status_code == 200:
    for iss in res_issues.json():
      cuerpo = iss.get("body") or ""
      links_existentes.add(cuerpo)
except Exception:
  pass

# 2. Búsqueda X-Ray EXCLUSIVA en portales de empleo y ATS de empresas (Cero blogs/cursos/redes)
queries = [
    # 1. Portales de startups y software de RRHH (ATS) usados en España y Remoto
    (
        '(site:jobs.lever.co OR site:boards.greenhouse.io OR'
        ' site:apply.workable.com OR site:teamtailor.com OR'
        ' site:factorialhr.es OR site:bamboohr.com OR'
        ' site:welcometothejungle.com) ("Legal" OR "Abogado" OR "Jurista" OR'
        ' "Compliance" OR "RGPD" OR "Privacidad") ("España" OR "Madrid" OR'
        ' "Barcelona" OR "Remoto")'
    ),
    # 2. Ofertas directas en portales de empleo españoles (InfoJobs, Indeed, Tecnoempleo)
    (
        '(site:infojobs.net/madrid OR site:infojobs.net/barcelona OR'
        ' site:infojobs.net/teletrabajo OR site:es.indeed.com/viewjob OR'
        ' site:tecnoempleo.com) ("Legal Operations" OR "LegalTech" OR "RGPD" OR'
        ' "Compliance" OR "Inteligencia Artificial")'
    ),
    # 3. Vacantes en páginas corporativas ("Trabaja con nosotros" /Vacante abierta)
    (
        'intitle:"oferta" OR intitle:"vacante" OR intitle:"empleo" ("Legal'
        ' Operations" OR "Abogado" OR "RGPD" OR "Compliance") ("Inteligencia'
        ' Artificial" OR "LegalTech" OR "Automatización") ("Madrid" OR'
        ' "Barcelona" OR "Teletrabajo" OR "Remoto") -curso -master -universidad'
        ' -facebook -instagram -youtube -blog'
    ),
]

ofertas_crudas = []
urls_vistas = set()

for q in queries:
  res = requests.post(
      "https://google.serper.dev/search",
      headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
      json={"q": q, "gl": "es", "hl": "es", "tbs": "qdr:m", "num": 6},
  )
  if res.status_code == 200:
    for item in res.json().get("organic", []):
      link = item.get("link", "")
      # Evitar duplicados o links que ya están en tus Issues
      if link not in urls_vistas and not any(
          link in texto for texto in links_existentes
      ):
        urls_vistas.add(link)
        ofertas_crudas.append({
            "titulo": item.get("title", ""),
            "link": link,
            "snippet": item.get("snippet", ""),
        })

print(f"Se encontraron {len(ofertas_crudas)} posibles vacantes nuevas.")

if not ofertas_crudas:
  print("No hay vacantes nuevas por analizar hoy.")
  exit(0)

# 3. Filtrar con Gemini con regla de ORO: Solo ofertas de empleo reales
prompt = (
    "Analiza la siguiente lista de resultados de búsqueda:\n"
    f"{json.dumps(ofertas_crudas, ensure_ascii=False, indent=2)}\n\n"
    f"Mi CV actual:\n{cv_base[:5000]}\n\n"
    "REGLAS ESTRICTAS E INQUEBRANTABLES DE FILTRADO:\n"
    "1. SOLO ACEPTA OFERTAS DE EMPLEO REALES (vacantes abiertas donde una"
    " empresa busca contratar a una persona). Si el resultado es un curso, un"
    " máster, una noticia, un post de blog/redes sociales, un directorio de"
    " empresas o una agencia vendiendo servicios de automatización, DESCÁRTALO"
    " INMEDIATAMENTE.\n"
    "2. Si la oferta está redactada íntegramente en inglés o exige 'Inglés"
    " fluido / C1 / High English' como requisito excluyente, DESCÁRTALA.\n"
    "3. Si exige colegiación obligatoria en España para litigar en tribunales"
    " (procesal puro), DESCÁRTALA.\n"
    "4. Acepta únicamente vacantes de trabajo en español para roles de:"
    " LegalOps, Compliance, RGPD/Privacidad, Gobernanza de IA, Contratos,"
    " LegalTech o Abogado Corporativo/In-house.\n\n"
    "Devuelve ÚNICAMENTE un objeto JSON válido con una lista llamada"
    ' "ofertas_seleccionadas" (si ninguna es una oferta de trabajo real,'
    ' devuelve la lista vacía []):\n'
    "{\n"
    '  "ofertas_seleccionadas": [\n'
    "    {\n"
    '      "empresa_o_rol": "Nombre del Puesto - Nombre de la Empresa",\n'
    '      "link": "URL original de la vacante",\n'
    '      "asunto_correo": "Candidatura: [Nombre del Puesto] - Bárbara'
    ' Piccolo",\n'
    '      "mensaje_postulacion": "Carta de presentación corta, directa y'
    " persuasiva en español postulándome al puesto vacante, destacando cómo mi"
    " perfil en LegalOps/IA/RGPD encaja en la vacante e incluyendo mi"
    ' portafolio https://github.com/barbarapiccolo/cvlegal",\n'
    '      "puntos_clave_cv": "3 logros o puntos de mi CV adaptados con las'
    ' palabras clave que pide esta vacante"\n'
    "    }\n"
    "  ]\n"
    "}"
)

# Cola inteligente de modelos anti-503
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

modelos_ordenados = sorted(
    modelos_disponibles,
    key=lambda x: (0 if "lite" in x else (1 if "flash" in x else 2)),
)
if not modelos_ordenados:
  modelos_ordenados = [
      "gemini-3.8-flash-lite",
      "gemini-3.8-flash",
      "gemini-3.8-pro",
  ]

resultado = {"ofertas_seleccionadas": []}
for modelo_actual in modelos_ordenados[:6]:
  try:
    print(f"Analizando vacantes con modelo: {modelo_actual}...")
    respuesta = client.models.generate_content(
        model=modelo_actual,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        ),
    )
    resultado = json.loads(respuesta.text)
    print(f"✅ ¡Filtrado completado usando {modelo_actual}!")
    break
  except Exception as e:
    print(f"⚠️ {modelo_actual} ocupado ({e}). Saltando al siguiente...")
    time.sleep(5)

# 4. Crear tarjeta (Issue) en GitHub solo para vacantes reales aprobadas
seleccionadas = resultado.get("ofertas_seleccionadas", [])
print(f"Creando {len(seleccionadas)} tarjetas de empleo real en GitHub Issues...")

for of in seleccionadas:
  asunto_encoded = urllib.parse.quote(of.get("asunto_correo", ""))
  cuerpo_encoded = urllib.parse.quote(of.get("mensaje_postulacion", ""))
  link_mailto = f"mailto:?subject={asunto_encoded}&body={cuerpo_encoded}"

  cuerpo_issue = (
      f"🔔 Hola @{USUARIO}, encontré una **vacante de empleo real** en español"
      " para tu perfil:\n\n### 🎯 Vacante Detectada\n**Puesto y Empresa:**"
      f" {of.get('empresa_o_rol')}\n🔗 **[Ir a la Oferta de Empleo"
      f" Original]({of.get('link')})**\n\n---\n\n### ✉️ Carta de Presentación"
      " Lista para Postular\n> **Asunto sugerido:**"
      f" {of.get('asunto_correo')}\n\n```text\n"
      f"{of.get('mensaje_postulacion')}\n```\n\n🚀 **[Toca aquí desde el"
      " móvil para abrir tu Correo con el texto ya"
      f" pegado]({link_mailto})**\n\n---\n\n### 🛠️ Ajustes clave para tu CV en"
      f" esta vacante:\n{of.get('puntos_clave_cv')}"
  )

  res_issue = requests.post(
      f"https://api.github.com/repos/{REPO}/issues",
      headers={
          "Authorization": f"Bearer {GITHUB_TOKEN}",
          "Accept": "application/vnd.github+json",
      },
      json={
          "title": f"💼 Vacante: {of.get('empresa_o_rol')}",
          "body": cuerpo_issue,
          "assignees": [USUARIO],
      },
  )
  print(
      f"Issue creado para {of.get('empresa_o_rol')}: Status"
      f" {res_issue.status_code}"
  )
