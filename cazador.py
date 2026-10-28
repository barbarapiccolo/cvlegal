import base64
import glob
import json
import os
import re
import time
import urllib.parse
from fpdf import FPDF
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

# 1.5 Obtener Issues ya creados para NO repetir ofertas
links_existentes = set()
try:
  res_issues = requests.get(
      f"https://api.github.com/repos/{REPO}/issues?state=all&per_page=100",
      headers={"Authorization": f"Bearer {GITHUB_TOKEN}"},
  )
  if res_issues.status_code == 200:
    for iss in res_issues.json():
      links_existentes.add(iss.get("body") or "")
except Exception:
  pass

# 2. Búsqueda X-Ray: Remoto (Global/LatAm/España) + Presencial/Híbrido en España (aprovechando Ciudadanía UE)
queries = [
    # 1. ATS de empresas tech en España y Remoto (Lever, Greenhouse, Workable, Teamtailor, Factorial, Welcome to the Jungle)
    (
        '(site:jobs.lever.co OR site:boards.greenhouse.io OR'
        ' site:apply.workable.com OR site:teamtailor.com OR'
        ' site:factorialhr.es OR site:welcometothejungle.com) ("Legal" OR'
        ' "Abogado" OR "Jurista" OR "Compliance" OR "Privacidad" OR "RGPD")'
        ' ("España" OR "Madrid" OR "Barcelona" OR "Remoto" OR "Teletrabajo" OR'
        ' "LATAM")'
    ),
    # 2. Portales de empleo españoles y remotos (InfoJobs, Indeed España, Get on Board, Tecnoempleo)
    (
        '(site:infojobs.net OR site:es.indeed.com/viewjob OR'
        ' site:getonbrd.com/empleos OR site:tecnoempleo.com) ("Legal'
        ' Operations" OR "LegalOps" OR "LegalTech" OR "RGPD" OR "Compliance"'
        ' OR "Inteligencia Artificial") ("Madrid" OR "Barcelona" OR "Valencia"'
        ' OR "Teletrabajo" OR "Remoto")'
    ),
    # 3. Vacantes directas de Innovación Legal, IA y Privacidad en España o Remoto
    (
        'intitle:"oferta" OR intitle:"vacante" OR intitle:"empleo" ("Legal'
        ' Operations" OR "LegalTech" OR "RGPD" OR "Compliance" OR "Gobernanza'
        ' de IA") ("España" OR "Madrid" OR "Barcelona" OR "Remoto" OR'
        ' "Teletrabajo") -curso -master -universidad -facebook -blog'
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
  exit(0)

# 3. Filtrar con Gemini incluyendo tu ventaja de Ciudadanía Europea
prompt = (
    "Analiza la siguiente lista de resultados de búsqueda:\n"
    f"{json.dumps(ofertas_crudas, ensure_ascii=False, indent=2)}\n\n"
    "Mi perfil base (Bárbara Piccolo, con CIUDADANÍA EUROPEA / Pasaporte UE,"
    " permiso de trabajo inmediato en España/UE sin necesidad de visado):\n"
    f"{cv_base[:5500]}\n\n"
    "REGLAS ESTRICTAS DE FILTRADO:\n"
    "1. SOLO ACEPTA OFERTAS DE EMPLEO REALES (vacantes abiertas para"
    " contratar). Descarta cursos, másteres, noticias, blogs o agencias"
    " vendiendo servicios.\n"
    "2. MODALIDAD Y UBICACIÓN: Como tengo CIUDADANÍA EUROPEA y no necesito"
    " visado, ACEPTA tanto vacantes 100% Remotas / Teletrabajo (España, LATAM"
    " o Global en español) COMO vacantes presenciales o híbridas en España"
    " (Madrid, Barcelona, etc.) donde pueda trasladarme.\n"
    "3. Si exige 'Inglés fluido / C1' como requisito excluyente o colegiación"
    " obligatoria para litigar en juzgados españoles (procesal puro),"
    " DESCÁRTALA.\n"
    "4. Para cada oferta aceptada, redacta un CV COMPLETO optimizado para"
    " sistemas ATS usando mis datos reales e inyectando las palabras clave"
    " exactas de la vacante. En la carta y en el resumen deja muy claro que"
    " poseo Ciudadanía Europea (permiso de trabajo en España/UE sin trámites"
    " de extranjería) y disponibilidad inmediata remota o de traslado.\n\n"
    "Devuelve ÚNICAMENTE un objeto JSON válido con esta estructura:\n"
    "{\n"
    '  "ofertas_seleccionadas": [\n'
    "    {\n"
    '      "empresa_o_rol": "Nombre del Puesto - Empresa",\n'
    '      "modalidad": "Indica si es Remoto, Híbrido en España o Presencial en'
    ' España",\n'
    '      "link": "URL original de la vacante",\n'
    '      "asunto_correo": "Candidatura: [Nombre del Puesto] - Bárbara'
    ' Piccolo (Ciudadanía UE)",\n'
    '      "mensaje_postulacion": "Carta corta, directa y persuasiva en'
    " español destacando mi encaje en LegalOps/IA/RGPD, mi portafolio"
    " https://github.com/barbarapiccolo/cvlegal y que cuento con Ciudadanía"
    ' Europea para contratación inmediata",\n'
    '      "cv_ats": {\n'
    '        "titulo_adaptado": "Titular profesional con las keywords exactas'
    ' del puesto",\n'
    '        "resumen_ejecutivo": "Párrafo potente de 4 líneas alineado 100% a'
    " la vacante, mencionando Ciudadanía Europea y disponibilidad para España"
    ' o Remoto",\n'
    '        "competencias_ats": ["Keyword 1", "Keyword 2", "Keyword 3",'
    ' "Keyword 4", "Keyword 5", "Keyword 6"],\n'
    '        "experiencia_adaptada": [\n'
    "          {\n"
    '            "cargo_y_empresa": "Cargo y proyecto/empresa real de mi CV",\n'
    '            "logros": ["Logro 1 reescrito con keywords de la oferta",'
    ' "Logro 2 reescrito con keywords de la oferta"]\n'
    "          }\n"
    "        ],\n"
    '        "educacion_y_certificaciones": ["Título / Certificación relevante'
    ' 1", "Título / Certificación 2"]\n'
    "      }\n"
    "    }\n"
    "  ]\n"
    "}"
)

modelos_disponibles = []
try:
  for m in client.models.list():
    nombre = m.name.replace("models/", "")
    if "gemini" in nombre and not any(
        x in nombre
        for x in ["embedding", "vision", "imagen", "veo", "audio", "tts"]
    ):
      modelos_disponibles.append(nombre)
except Exception:
  pass

modelos_ordenados = sorted(
    modelos_disponibles,
    key=lambda x: (0 if "lite" in x else (1 if "flash" in x else 2)),
) or ["gemini-3.8-flash-lite", "gemini-3.8-flash"]

resultado = {"ofertas_seleccionadas": []}
for modelo_actual in modelos_ordenados[:6]:
  try:
    respuesta = client.models.generate_content(
        model=modelo_actual,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        ),
    )
    resultado = json.loads(respuesta.text)
    print(f"✅ ¡Filtrado y adaptación ATS completados con {modelo_actual}!")
    break
  except Exception as e:
    print(f"⚠️ {modelo_actual} ocupado ({e}). Saltando...")
    time.sleep(5)


def limpiar_texto(t):
  if not t:
    return ""
  reemplazos = {
      "“": '"',
      "”": '"',
      "’": "'",
      "‘": "'",
      "–": "-",
      "—": "-",
      "•": "-",
      "…": "...",
  }
  for k, v in reemplazos.items():
    t = t.replace(k, v)
  return t.encode("latin-1", "ignore").decode("latin-1")


def crear_pdf_ats(cv_data, ruta_archivo):
  pdf = FPDF()
  pdf.set_auto_page_break(auto=True, margin=15)
  pdf.add_page()

  # Encabezado limpio para lectura perfecta de ATS
  pdf.set_font("Helvetica", "B", 18)
  pdf.cell(
      0,
      9,
      limpiar_texto("BARBARA ISABEL PICCOLO OBALDO"),
      new_x="LMARGIN",
      new_y="NEXT",
  )

  pdf.set_font("Helvetica", "B", 11)
  pdf.set_text_color(40, 80, 140)
  pdf.multi_cell(0, 6, limpiar_texto(cv_data.get("titulo_adaptado", "")))

  # Línea destacada de Ciudadanía Europea (Evita descarte inmediato de RRHH en España)
  pdf.set_font("Helvetica", "B", 9)
  pdf.set_text_color(0, 110, 60)
  pdf.cell(
      0,
      6,
      limpiar_texto(
          "CIUDADANIA EUROPEA (UE) - Permiso de trabajo inmediato en España y"
          " UE (Sin necesidad de visado)"
      ),
      new_x="LMARGIN",
      new_y="NEXT",
  )

  pdf.set_font("Helvetica", "", 9)
  pdf.set_text_color(80, 80, 80)
  pdf.cell(
      0,
      5,
      limpiar_texto(
          "Portafolio Web & GitHub: https://github.com/barbarapiccolo/cvlegal |"
          " Modalidad: Remoto / Traslado a España"
      ),
      new_x="LMARGIN",
      new_y="NEXT",
  )
  pdf.ln(3)

  # Resumen Ejecutivo
  pdf.set_font("Helvetica", "B", 11)
  pdf.set_text_color(0, 0, 0)
  pdf.cell(
      0,
      7,
      "PERFIL PROFESIONAL",
      border="B",
      new_x="LMARGIN",
      new_y="NEXT",
  )
  pdf.ln(2)
  pdf.set_font("Helvetica", "", 10)
  pdf.multi_cell(0, 5, limpiar_texto(cv_data.get("resumen_ejecutivo", "")))
  pdf.ln(4)

  # Competencias / Keywords ATS
  pdf.set_font("Helvetica", "B", 11)
  pdf.cell(
      0,
      7,
      "COMPETENCIAS CLAVE Y TECNOLOGIAS (ATS KEYWORDS)",
      border="B",
      new_x="LMARGIN",
      new_y="NEXT",
  )
  pdf.ln(2)
  pdf.set_font("Helvetica", "", 10)
  skills = " | ".join(cv_data.get("competencias_ats", []))
  pdf.multi_cell(0, 5, limpiar_texto(skills))
  pdf.ln(4)

  # Experiencia Relevante Adaptada
  pdf.set_font("Helvetica", "B", 11)
  pdf.cell(
      0,
      7,
      "EXPERIENCIA RELEVANTE Y PROYECTOS LEGALTECH",
      border="B",
      new_x="LMARGIN",
      new_y="NEXT",
  )
  pdf.ln(2)
  for exp in cv_data.get("experiencia_adaptada", []):
    pdf.set_font("Helvetica", "B", 10)
    pdf.multi_cell(0, 6, limpiar_texto(exp.get("cargo_y_empresa", "")))
    pdf.set_font("Helvetica", "", 10)
    for logro in exp.get("logros", []):
      pdf.multi_cell(0, 5, limpiar_texto(f"- {logro}"))
    pdf.ln(2)

  # Educación
  pdf.set_font("Helvetica", "B", 11)
  pdf.cell(
      0,
      7,
      "FORMACION ACADEMICA Y CERTIFICACIONES",
      border="B",
      new_x="LMARGIN",
      new_y="NEXT",
  )
  pdf.ln(2)
  pdf.set_font("Helvetica", "", 10)
  for edu in cv_data.get("educacion_y_certificaciones", []):
    pdf.multi_cell(0, 5, limpiar_texto(f"- {edu}"))

  pdf.output(ruta_archivo)


# 4. Generar el PDF para cada vacante, subirlo al repo y crear el Issue con el botón de descarga
seleccionadas = resultado.get("ofertas_seleccionadas", [])
print(f"Procesando {len(seleccionadas)} vacantes y generando PDFs...")

for idx, of in enumerate(seleccionadas):
  nombre_limpio = (
      re.sub(r"[^a-zA-Z0-9]", "_", of.get("empresa_o_rol", "Vacante"))[:30]
      + f"_{int(time.time())}"
  )
  nombre_pdf = f"CV_Barbara_Piccolo_{nombre_limpio}.pdf"
  crear_pdf_ats(of.get("cv_ats", {}), nombre_pdf)

  with open(nombre_pdf, "rb") as f_pdf:
    contenido_b64 = base64.b64encode(f_pdf.read()).decode("utf-8")

  ruta_repo = f"cvs_adaptados/{nombre_pdf}"
  requests.put(
      f"https://api.github.com/repos/{REPO}/contents/{ruta_repo}",
      headers={
          "Authorization": f"Bearer {GITHUB_TOKEN}",
          "Accept": "application/vnd.github+json",
      },
      json={
          "message": (
              f"CV adaptado automáticamente para {of.get('empresa_o_rol')}"
          ),
          "content": contenido_b64,
      },
  )

  url_descarga_pdf = f"https://github.com/{REPO}/raw/main/{ruta_repo}"
  asunto_encoded = urllib.parse.quote(of.get("asunto_correo", ""))
  cuerpo_encoded = urllib.parse.quote(of.get("mensaje_postulacion", ""))
  link_mailto = f"mailto:?subject={asunto_encoded}&body={cuerpo_encoded}"

  cuerpo_issue = (
      f"🔔 Hola @{USUARIO}, encontré una vacante **{of.get('modalidad')}**"
      " ideal para tu perfil con Ciudadanía UE:\n\n### 🎯 Vacante"
      f" Detectada\n**Puesto y Empresa:** {of.get('empresa_o_rol')}\n🌍"
      f" **Modalidad:** {of.get('modalidad')}\n🔗 **[1. Ir al Portal de la"
      f" Oferta para Postular]({of.get('link')})**\n\n---\n\n### 📄 Tu CV en"
      " PDF Adaptado a esta Oferta (Anti-ATS + Ciudadanía UE)\nYa generé tu"
      " archivo PDF limpio con las palabras clave de la empresa y destacando"
      " tu permiso de trabajo europeo:\n👉 **[2. 📥 TOCA AQUÍ PARA DESCARGAR TU"
      f" CV EN PDF ADAPTADO]({url_descarga_pdf})**\n\n---\n\n### ✉️ Mensaje /"
      " Carta de Presentación para Pegar en el Portal\n> **Asunto sugerido:**"
      f" {of.get('asunto_correo')}\n\n```text\n"
      f"{of.get('mensaje_postulacion')}\n```\n\n🚀 **[O toca aquí para abrir"
      " este texto directo en tu Correo]({link_mailto})**"
  )

  requests.post(
      f"https://api.github.com/repos/{REPO}/issues",
      headers={
          "Authorization": f"Bearer {GITHUB_TOKEN}",
          "Accept": "application/vnd.github+json",
      },
      json={
          "title": (
              f"🇪🇺 [{of.get('modalidad', 'España/Remoto')}]"
              f" {of.get('empresa_o_rol')}"
          ),
          "body": cuerpo_issue,
          "assignees": [USUARIO],
      },
  )
