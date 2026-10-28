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

# 2. Búsqueda enfocada en puestos en ESPAÑOL (RGPD, DPO, Compliance, LegalTech, Mercantil Tech)
filtro_anti_ingles = '-"C1" -"C2" -"fluent English" -"inglés fluido" -"inglés muy alto" -"bilingüe"'

queries = [
    # 1. Puestos de Privacidad, RGPD, DPO y Compliance en España y Teletrabajo (100% mercado en español)
    (
        '("Consultor RGPD" OR "Protección de Datos" OR "DPO" OR "Compliance" OR'
        ' "Cumplimiento Normativo" OR "Derecho Digital") ("empleo" OR "oferta"'
        ' OR "vacante" OR "trabaja con nosotros") ("Madrid" OR "Barcelona" OR'
        ' "Valencia" OR "Teletrabajo" OR "Remoto" OR "España") -curso -master'
        f" -blog {filtro_anti_ingles}"
    ),
    # 2. Portales de empleo españoles y remotos hispanos
    (
        '(site:infojobs.net OR site:es.indeed.com OR site:tecnoempleo.com OR'
        ' site:getonbrd.com/empleos OR site:welcometothejungle.com OR'
        ' site:factorialhr.es OR site:teamtailor.com) ("Abogado" OR "Jurista"'
        ' OR "Legal" OR "RGPD" OR "Compliance") ("Inteligencia Artificial" OR'
        ' "Tecnología" OR "Digital" OR "Automatización" OR "LegalTech" OR'
        f' "Mercantil") {filtro_anti_ingles}'
    ),
    # 3. Operaciones Legales, Contratos SaaS y Consultoría Legal en español
    (
        '("Operaciones Legales" OR "Legal Operations" OR "LegalOps" OR "Gestor'
        ' de Contratos" OR "Abogado In-house" OR "Asesor Jurídico") ("Remoto"'
        ' OR "Teletrabajo" OR "Madrid" OR "Barcelona" OR "España") ("vacante"'
        f' OR "oferta" OR "empleo") -curso -master -blog {filtro_anti_ingles}'
    ),
]


def extraer_texto_completo_oferta(url):
  try:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
    }
    r = requests.get(url, headers=headers, timeout=8)
    if r.status_code == 200:
      texto = re.sub(
          r"<script.*?>.*?</script>", "", r.text, flags=re.DOTALL | re.I
      )
      texto = re.sub(
          r"<style.*?>.*?</style>", "", texto, flags=re.DOTALL | re.I
      )
      texto = re.sub(r"<[^>]+>", " ", texto)
      texto = re.sub(r"\s+", " ", texto).strip()
      return texto[:3000]
  except Exception:
    pass
  return ""


# Solo bloquea si pide inglés C1/C2/Fluido/Indispensable explícitamente
patrones_ingles_excluyente = re.compile(
    r"(ingl[eé]s\s+(fluido|muy\s+alto|c1|c2|biling[uü]e|indispensable|imprescindible|excluyente)|nivel\s+(c1|c2|biling[uü]e)\s+de\s+ingl[eé]s|fluent\s+in\s+english|english\s+(c1|c2|fluent|native)|imprescindible\s+nivel\s+alto\s+de\s+ingl[eé]s)",
    re.IGNORECASE,
)

ofertas_crudas = []
urls_vistas = set()

for q in queries:
  res = requests.post(
      "https://google.serper.dev/search",
      headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
      json={"q": q, "gl": "es", "hl": "es", "tbs": "qdr:m", "num": 8},
  )
  if res.status_code == 200:
    for item in res.json().get("organic", []):
      link = item.get("link", "")
      if link not in urls_vistas and not any(
          link in texto for texto in links_existentes
      ):
        urls_vistas.add(link)
        titulo = item.get("title", "")
        snippet = item.get("snippet", "")

        contenido_pagina = extraer_texto_completo_oferta(link)
        texto_total = f"{titulo} {snippet} {contenido_pagina}"

        if patrones_ingles_excluyente.search(texto_total):
          print(f"❌ Descartada por exigir inglés C1/Fluido: {titulo}")
          continue

        ofertas_crudas.append({
            "titulo": titulo,
            "link": link,
            "snippet": snippet,
            "contenido_extraido": (
                contenido_pagina[:2000] if contenido_pagina else snippet
            ),
        })

print(
    f"Se encontraron {len(ofertas_crudas)} candidatas para evaluar con Gemini."
)
if not ofertas_crudas:
  exit(0)

# 3. Filtrar con Gemini con criterio inteligente y equilibrado
prompt = (
    "Analiza la siguiente lista de resultados de búsqueda de empleo:\n"
    f"{json.dumps(ofertas_crudas[:15], ensure_ascii=False, indent=2)}\n\n"
    "Mi perfil base (Bárbara Piccolo, Abogada con CIUDADANÍA EUROPEA /"
    " Pasaporte UE, especialista en Derecho Corporativo, RGPD/Privacidad,"
    " Compliance, Gobernanza de IA y LegalOps):\n"
    f"{cv_base[:4500]}\n\n"
    "CRITERIOS DE SELECCIÓN:\n"
    "1. TIENE QUE SER UNA OFERTA DE EMPLEO O PÁGINA DE VACANTES REALES:"
    " Descarta cursos, másteres, noticias o artículos de blog.\n"
    "2. CRITERIO DE IDIOMA (EQUILIBRADO): Descarta la oferta SOLO si está"
    " redactada íntegramente en inglés o si exige 'Inglés C1 / Fluido /"
    " Imprescindible / Excluyente'. Si la oferta está en español y NO menciona"
    " inglés, o solo dice 'inglés valorable / deseable / básico / medio' (o si"
    " solo hay botones de la web en inglés), ¡ACÉPTALA!\n"
    "3. UBICACIÓN Y PERFIL: Tengo Ciudadanía Europea. Acepta ofertas Remotas /"
    " Teletrabajo Y TAMBIÉN ofertas presenciales o híbridas en España (Madrid,"
    " Barcelona, Valencia, etc.) en áreas de: RGPD/Protección de Datos,"
    " Compliance, LegalTech, IA, Contratos Mercantiles, Asesoría Jurídica"
    " Corporativa o LegalOps. (Solo descarta si exige ser abogado procesalista"
    " litigando en juzgados españoles).\n"
    "4. Para cada oferta aprobada, genera mi CV COMPLETO optimizado para ATS"
    " en español destacando mi Ciudadanía Europea.\n\n"
    "Devuelve ÚNICAMENTE un objeto JSON válido con esta estructura:\n"
    "{\n"
    '  "resumen_descartes": ["Breve línea de por qué descartaste las que no'
    ' elegiste"],\n'
    '  "ofertas_seleccionadas": [\n'
    "    {\n"
    '      "empresa_o_rol": "Nombre del Puesto - Empresa",\n'
    '      "modalidad": "Remoto / Híbrido en España / Presencial en España",\n'
    '      "confirmacion_idioma": "Ej: Oferta 100% en español (sin requisito'
    ' excluyente de inglés)",\n'
    '      "link": "URL original de la vacante",\n'
    '      "asunto_correo": "Candidatura: [Nombre del Puesto] - Bárbara'
    ' Piccolo (Ciudadanía UE)",\n'
    '      "mensaje_postulacion": "Carta corta y persuasiva en español'
    " destacando mi encaje en el puesto, mi portafolio"
    ' https://github.com/barbarapiccolo/cvlegal y mi Ciudadanía Europea",\n'
    '      "cv_ats": {\n'
    '        "titulo_adaptado": "Titular profesional con las keywords exactas'
    ' del puesto",\n'
    '        "resumen_ejecutivo": "Párrafo potente de 4 líneas alineado 100% a'
    ' la vacante, mencionando Ciudadanía Europea",\n'
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
) or ["gemini-flash-lite-latest", "gemini-3.8-flash"]

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
    print(f"✅ ¡Análisis completado con {modelo_actual}!")
    for motivo in resultado.get("resumen_descartes", []):
      print(f"   ℹ️ Descarte IA: {motivo}")
    break
  except Exception as e:
    print(f"⚠️ {modelo_actual} ocupado ({e}). Saltando...")
    time.sleep(5)


def limpiar_texto(t):
  if not t:
    return ""
  t = str(t)
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
  t = re.sub(r"(\S{45})(\S+)", r"\1 \2", t)
  return t.encode("latin-1", "ignore").decode("latin-1")


def escribir_parrafo(pdf, texto, alto=5):
  texto_limpio = limpiar_texto(texto).strip()
  if not texto_limpio:
    return
  pdf.set_x(pdf.l_margin)
  pdf.multi_cell(
      0,
      alto,
      texto_limpio,
      new_x="LMARGIN",
      new_y="NEXT",
      wrapmode="CHAR",
  )


def crear_pdf_ats(cv_data, ruta_archivo):
  pdf = FPDF()
  pdf.set_margins(15, 15, 15)
  pdf.set_auto_page_break(auto=True, margin=15)
  pdf.add_page()

  pdf.set_font("Helvetica", "B", 17)
  escribir_parrafo(pdf, "BARBARA ISABEL PICCOLO OBALDO", 8)

  pdf.set_font("Helvetica", "B", 11)
  pdf.set_text_color(40, 80, 140)
  escribir_parrafo(
      pdf, cv_data.get("titulo_adaptado", "Especialista en LegalOps, IA y RGPD"), 6
  )

  pdf.set_font("Helvetica", "B", 9)
  pdf.set_text_color(0, 110, 60)
  escribir_parrafo(
      pdf,
      "CIUDADANIA EUROPEA (UE) - Permiso de trabajo inmediato en España y UE"
      " (Sin necesidad de visado)",
      6,
  )

  pdf.set_font("Helvetica", "", 9)
  pdf.set_text_color(80, 80, 80)
  escribir_parrafo(
      pdf,
      "Portafolio Web & GitHub: github.com/barbarapiccolo/cvlegal | Modalidad:"
      " Remoto / Traslado a España",
      5,
  )
  pdf.ln(3)

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
  escribir_parrafo(pdf, cv_data.get("resumen_ejecutivo", ""), 5)
  pdf.ln(4)

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
  escribir_parrafo(pdf, skills, 5)
  pdf.ln(4)

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
    escribir_parrafo(pdf, exp.get("cargo_y_empresa", ""), 6)
    pdf.set_font("Helvetica", "", 10)
    for logro in exp.get("logros", []):
      escribir_parrafo(pdf, f"- {logro}", 5)
    pdf.ln(2)

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
    escribir_parrafo(pdf, f"- {edu}", 5)

  pdf.output(ruta_archivo)


# 4. Generar el PDF para cada vacante aprobada
seleccionadas = resultado.get("ofertas_seleccionadas", [])
print(f"Procesando {len(seleccionadas)} vacantes aprobadas...")

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
      f"🔔 Hola @{USUARIO}, encontré una vacante en español ideal para tu"
      " perfil con Ciudadanía UE:\n\n### 🎯 Vacante Detectada\n**Puesto y"
      f" Empresa:** {of.get('empresa_o_rol')}\n🌍 **Modalidad:**"
      f" {of.get('modalidad')}\n✅ **Idioma:**"
      f" {of.get('confirmacion_idioma', 'Español')}\n🔗 **[1. Ir al Portal de"
      f" la Oferta para Postular]({of.get('link')})**\n\n---\n\n### 📄 Tu CV en"
      " PDF Adaptado a esta Oferta (Anti-ATS + Ciudadanía UE)\n👉 **[2. 📥 TOCA"
      " AQUÍ PARA DESCARGAR TU CV EN PDF"
      f" ADAPTADO]({url_descarga_pdf})**\n\n---\n\n### ✉️ Mensaje / Carta de"
      " Presentación para Pegar en el Portal\n> **Asunto sugerido:**"
      f" {of.get('asunto_correo')}\n\n```text\n"
      f"{of.get('mensaje_postulacion')}\n```\n\n🚀 **[O toca aquí para abrir"
      " este texto directo en tu Correo]({link_mailto})**"
  )

  res_issue = requests.post(
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
  print(f"✅ Issue y PDF creados para: {of.get('empresa_o_rol')}")
