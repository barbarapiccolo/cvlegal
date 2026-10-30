import base64
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

# 1. TU CV REAL COMPLETO INCRUSTADO (Enfocado en roles jurídicos corporativos/normativos sin colegiación)
CV_REAL_BARBARA = """
NOMBRE: Bárbara Isabel Piccolo Obaldo
CIUDADANÍA: Ciudadana de la Unión Europea (UE) - Permiso de trabajo inmediato en España y la UE sin necesidad de visado.
CONTACTO: Email: barbaraipiccolo@gmail.com | Tel: +58-414-9065797 | LinkedIn: linkedin.com/in/barbara-piccolo-613705b6 | Portafolio: github.com/barbarapiccolo/cvlegal
PERFIL: Especialista en Cumplimiento Normativo (Compliance), Operaciones Legales (LegalOps), GRC, LegalTech y Regulación Financiera/Digital (+12 años de experiencia). Licenciada en Derecho (Venezuela) con Máster en LegalTech y Derecho de la Ciberseguridad en España (Esneca, 2025). Experta en regulación FinTech (MiCA, AML/PBC), Ley de IA de la UE (EU AI Act), resiliencia operativa digital (DORA), seguridad de la información (ISO 27001), RGPD y gestión de contratos tecnológicos (SaaS, SLAs, DPAs).

EXPERIENCIA PROFESIONAL REAL:
1. BIGTO.ONE | Remoto (España / Global) | Especialista Jurídico-Tecnológico (Consultora) | Julio 2025 - Diciembre 2025
- Consultora estratégico-tecnológica para venture builder global implementando el marco de cumplimiento y operaciones legales (LegalOps) para un portafolio de +8 startups tecnológicas en el mercado europeo.
- Diagnósticos de cumplimiento en sectores de alta regulación: FinTech (MiCA, AML) e Inteligencia Artificial (EU AI Act), DORA e ISO 27001.
- Diseño y estandarización de procesos y contratos tecnológicos (SaaS, SLAs, DPAs) aplicando Legal by Design y privacidad desde el diseño (RGPD).

2. CONSULTORA INDEPENDIENTE | Italia - Venezuela (Remoto) | Asesora Legal y de Estrategia Digital | 2023 - Presente
- Consultoría en cumplimiento normativo, protección de datos, derecho mercantil y estructuración de contratos tecnológicos.
- Optimización y automatización de procesos de contratación digital (CLM) y flujos de trabajo LegalTech.

3. MYSTIC REMODELING LLC | Florida, EE.UU. | Gerente de Operaciones Digitales | Sept 2021 - Sept 2023
- Gestión de operaciones digitales, implementación de herramientas tecnológicas de gestión de proyectos y automatización de procesos internos.
- Supervisión de cumplimiento de normativas de privacidad y seguridad de datos.

4. INVERSIONES QUADRUVIO | Caracas, Venezuela | Consultor Jurídico Senior | Ene 2015 - Nov 2019
- Dirección integral del área legal y de cumplimiento corporativo (Compliance) para holding empresarial.
- Negociación de contratos mercantiles, gobernanza corporativa (Asambleas de Accionistas y Juntas Directivas) y mitigación de riesgos regulatorios.

5. CASA DE CAMBIO ZOOM | Caracas, Venezuela | Especialista en Cumplimiento Normativo y Corporativo | Mar 2012 - Jul 2015
- Responsable del cumplimiento legal y normativo financiero y cambiario, reportando a Presidencia y Consultoría Jurídica.
- Liderazgo en inspecciones de entes reguladores bancarios/financieros (SUDEBAN) y prevención de blanqueo de capitales (AML / PBC / LOCDOFT).

6. BANESCO BANCO UNIVERSAL & BANCRECER | Caracas, Venezuela | Especialista Legal en Créditos y Contratos Bancarios | Ene 2007 - Jul 2010
- Miembro fundador del equipo legal en el lanzamiento de Bancrecer y especialista en estructuración de contratos bancarios, créditos corporativos, garantías y cumplimiento normativo bancario.

FORMACIÓN ACADÉMICA Y CERTIFICACIONES:
- Máster en LegalTech y Derecho de la Ciberseguridad | Esneca Business School, España (2025) - Título con Apostilla de La Haya.
- Licenciada en Derecho (Abogada) | Universidad Santa María, Venezuela (2005).
- Habilidades y Herramientas: ISO 27001, DORA, EU AI Act, MiCA, RGPD, Prevención de Blanqueo de Capitales (AML/PBC), Gestión de Contratos (CLM), VLEX, DocuSign, LegalSurf, Salesforce, Notion, GitHub.
- Idiomas: Español (Nativo), Italiano (Intermedio B1), Inglés (Intermedio B1).
"""

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

# 2. Exclusiones: Bloqueamos palabras en inglés, Inglés C1, Becarios, Ingeniería TI y Colegiación obligatoria
filtro_exclusiones = (
    '-"C1" -"C2" -"fluent" -"inglés fluido" -"inglés alto" -"bilingüe"'
    ' -"requirements" -"responsibilities" -"we are looking" -"becario"'
    ' -"becaria" -"prácticas" -"internship" -"Qualys" -"Pentester" -"CISSP"'
    ' -"CISM" -"ITIL" -"Ingeniería Informática" -"Telecomunicaciones"'
    ' -"colegiado ejerciente" -"colegiación obligatoria" -"procesal"'
    ' -"litigación" -"juzgados" -"Administración Pública" -"temporal"'
)

# Búsquedas obligando a que la oferta esté redactada en español
queries = [
    # 1. Cumplimiento Normativo, Prevención de Blanqueo (PBC), RGPD y Protección de Datos
    (
        '("Cumplimiento Normativo" OR "Técnico de Compliance" OR "Especialista'
        ' en Compliance" OR "Consultor RGPD" OR "Protección de Datos" OR'
        ' "Delegado de Protección de Datos" OR "Prevención de Blanqueo")'
        ' ("funciones" OR "requisitos" OR "experiencia") ("Madrid" OR'
        ' "Barcelona" OR "Teletrabajo" OR "Remoto" OR "España") -curso -master'
        f" -blog {filtro_exclusiones}"
    ),
    # 2. Operaciones Legales, Gestión de Contratos, Derecho Digital y LegalTech en español
    (
        '("Operaciones Legales" OR "Gestor de Contratos" OR "Gestión de'
        ' Contratos" OR "Asesor Jurídico" OR "Consultor Legal" OR "Derecho'
        ' Digital" OR "LegalTech") ("Tecnología" OR "Inteligencia Artificial"'
        ' OR "Contratos" OR "RGPD" OR "FinTech" OR "Mercantil" OR "DORA" OR'
        ' "ISO 27001") ("Madrid" OR "Barcelona" OR "Remoto" OR "Teletrabajo" OR'
        f' "España") -curso -master -blog {filtro_exclusiones}'
    ),
    # 3. Portales de empleo con términos estrictamente en español
    (
        '(site:infojobs.net OR site:es.indeed.com OR'
        ' site:welcometothejungle.com/es OR site:getonbrd.com/empleos OR'
        ' site:factorialhr.es OR site:teamtailor.com) ("Cumplimiento" OR'
        ' "Protección de Datos" OR "RGPD" OR "Contratos" OR "Asesoría Jurídica"'
        ' OR "Operaciones Legales") ("FinTech" OR "Banca" OR "Tecnología" OR'
        ' "Inteligencia Artificial" OR "ISO 27001" OR "DORA" OR "Mercantil")'
        f" {filtro_exclusiones}"
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


# CANDADO 1: Detector de ofertas redactadas en inglés (en título o snippet)
detector_oferta_en_ingles = re.compile(
    r"\b(we are looking|you will|requirements|responsibilities|qualifications|what you'll do|about the role|about us|years of experience|working with|join our team|must have|nice to have|our client|is seeking)\b",
    re.IGNORECASE,
)

# CANDADO 2: Detector de requisitos excluyentes (Inglés C1/B2 alto, Colegiación o Ingeniería TI)
patrones_excluyentes = re.compile(
    r"(ingl[eé]s\s+(fluido|muy\s+alto|alto|avanzado|c1|c2|biling[uü]e|indispensable|imprescindible|excluyente|profesional)|nivel\s+(alto|avanzado|c1|c2|biling[uü]e)\s+de\s+ingl[eé]s|fluent\s+in\s+english|english\s+(c1|c2|fluent|native|required|mandatory)|becario|becaria|convenio\s+de\s+pr[aá]cticas|colegiaci[oó]n\s+obligatoria|abogado\s+ejerciente|colegiado\s+ejerciente|ingenier[ií]a\s+inform[aá]tica|ingenier[ií]a\s+de\s+telecomunicaciones)",
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

        # Si el resumen de Google ya viene redactado en inglés, se descarta en el acto
        if detector_oferta_en_ingles.search(f"{titulo} {snippet}"):
          print(f"❌ Descartada por estar redactada en inglés: {titulo}")
          continue

        contenido_pagina = extraer_texto_completo_oferta(link)
        texto_total = f"{titulo} {snippet} {contenido_pagina}"

        # Si el cuerpo de la página está redactado en inglés (más de 2 frases típicas en inglés), fuera
        if len(detector_oferta_en_ingles.findall(contenido_pagina)) >= 2:
          print(
              f"❌ Descartada porque la descripción de la página está en inglés: {titulo}"
          )
          continue

        if patrones_excluyentes.search(texto_total):
          print(
              f"❌ Descartada por filtro (Inglés Alto / Colegiación / Ingeniería TI): {titulo}"
          )
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
    f"Se encontraron {len(ofertas_crudas)} candidatas 100% en español para evaluar con Gemini."
)
if not ofertas_crudas:
  exit(0)

# 3. Filtrar con Gemini con prohibición absoluta de ofertas en inglés
prompt = (
    "Analiza la siguiente lista de vacantes de empleo:\n"
    f"{json.dumps(ofertas_crudas[:14], ensure_ascii=False, indent=2)}\n\n"
    "MI CV REAL COMPLETO (PROHIBIDO INVENTAR O BORRAR EMPRESAS, FECHAS O"
    " UNIVERSIDADES):\n"
    f"{CV_REAL_BARBARA}\n\n"
    "REGLAS ESTRICTAS E INQUEBRANTABLES DE SELECCIÓN:\n"
    "1. IDIOMA ESPAÑOL OBLIGATORIO: Si el título de la oferta, el snippet o la"
    " descripción del puesto están escritos en inglés, DESCÁRTALA"
    " INMEDIATAMENTE SIN EXCEPCIÓN. Si pide nivel de inglés alto, avanzado,"
    " fluido, C1 o imprescindible, DESCÁRTALA TAMBIÉN. Solo acepta ofertas"
    " redactadas íntegramente en español.\n"
    "2. QUÉ PUEDO EJERCER EN ESPAÑA (SIN COLEGIACIÓN): Soy abogada graduada en"
    " Venezuela con Ciudadanía Europea y Máster español en LegalTech y"
    " Ciberseguridad (2025). NO puedo ejercer como abogada litigante"
    " colegiada en juzgados españoles, PERO SÍ todos los cargos del área"
    " jurídica corporativa, normativa y tecnológica sin colegiación:"
    " Cumplimiento Normativo (Compliance), Prevención de Blanqueo (PBC/AML),"
    " Consultora RGPD / Protección de Datos / DPO, Operaciones Legales"
    " (LegalOps), Gestora de Contratos (SaaS/Mercantil), GRC Normativo (ISO"
    " 27001, DORA, Ley de IA, MiCA) o Consultora LegalTech.\n"
    "3. QUÉ DESCARTAR: Descarta ofertas que exijan colegiación en España, ir a"
    " juzgados, títulos de Ingeniería Informática/Telecomunicaciones,"
    " certificaciones CISSP/ITIL/PMP, puestos de Becario o contratos"
    " temporales.\n"
    "4. REGLA DE ORO PARA EL CV ATS: Todo el CV debe estar en ESPAÑOL. En"
    " 'experiencia_adaptada' DEBES INCLUIR MIS 6 EXPERIENCIAS REALES CON SUS"
    " NOMBRES DE EMPRESA Y FECHAS EXACTAS (BIGTO.ONE hasta dic 2025,"
    " Consultora Independiente, Mystic Remodeling, Inversiones Quadruvio, Casa"
    " de Cambio Zoom, Banesco/Bancrecer).\n\n"
    "Devuelve ÚNICAMENTE un objeto JSON válido con esta estructura:\n"
    "{\n"
    '  "ofertas_seleccionadas": [\n'
    "    {\n"
    '      "empresa_o_rol": "Nombre del Puesto en Español - Empresa",\n'
    '      "modalidad": "Remoto / Híbrido en España / Presencial en España",\n'
    '      "confirmacion_idioma": "Confirmado: Oferta redactada en español sin'
    ' requisito de inglés alto ni colegiación",\n'
    '      "link": "URL original de la vacante",\n'
    '      "asunto_correo": "Candidatura: [Nombre del Puesto] - Bárbara'
    ' Piccolo (Ciudadanía UE)",\n'
    '      "mensaje_postulacion": "Carta ejecutiva en español adaptada a la'
    " empresa y al puesto, destacando mis +12 años de experiencia en"
    " Cumplimiento Normativo, Gestión Contractual, Regulación"
    " Financiera/Tecnológica y Operaciones Legales, mi Máster español en"
    " LegalTech y Ciberseguridad (2025), mi portafolio"
    " https://github.com/barbarapiccolo/cvlegal y mi Ciudadanía Europea para"
    ' contratación inmediata",\n'
    '      "cv_ats": {\n'
    '        "titulo_adaptado": "Titular profesional en español adaptado al'
    ' puesto (Incluir: Ciudadana de la UE)",\n'
    '        "resumen_ejecutivo": "Párrafo ejecutivo de 4 líneas en español'
    " adaptado a la vacante con mis +12 años de experiencia, Máster en"
    ' LegalTech y Ciudadanía Europea",\n'
    '        "competencias_ats": ["Cumplimiento Normativo", "RGPD", "Gestión de'
    ' Riesgos", "Gobernanza de IA", "DORA", "ISO 27001", "Contratos'
    ' Tecnológicos", "Prevención de Blanqueo"],\n'
    '        "experiencia_adaptada": [\n'
    "          {\n"
    '            "cargo_y_empresa": "BIGTO.ONE | Remoto - Especialista'
    ' Jurídico-Tecnológico (Julio 2025 - Diciembre 2025)",\n'
    '            "logros": ["Logro 1 en español adaptado a la vacante", "Logro'
    ' 2 en español adaptado a la vacante"]\n'
    "          }\n"
    "        ]\n"
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
    print(f"✅ ¡Análisis y CV Senior completados con {modelo_actual}!")
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
      wrapmode="WORD",
  )


def crear_pdf_ats(cv_data, ruta_archivo):
  pdf = FPDF()
  pdf.set_margins(14, 14, 14)
  pdf.set_auto_page_break(auto=True, margin=14)
  pdf.add_page()

  pdf.set_font("Helvetica", "B", 16)
  escribir_parrafo(pdf, "BARBARA ISABEL PICCOLO OBALDO", 7)

  pdf.set_font("Helvetica", "B", 10.5)
  pdf.set_text_color(30, 70, 130)
  escribir_parrafo(pdf, cv_data.get("titulo_adaptado", ""), 5.5)

  pdf.set_font("Helvetica", "B", 9)
  pdf.set_text_color(0, 110, 60)
  escribir_parrafo(
      pdf,
      "CIUDADANIA EUROPEA (UE) - Permiso de trabajo inmediato en España y la UE"
      " (Sin necesidad de visado)",
      5,
  )

  pdf.set_font("Helvetica", "", 8.5)
  pdf.set_text_color(60, 60, 60)
  escribir_parrafo(
      pdf,
      "Email: barbaraipiccolo@gmail.com | Tel: +58-414-9065797 | LinkedIn:"
      " linkedin.com/in/barbara-piccolo-613705b6 | Portafolio:"
      " github.com/barbarapiccolo/cvlegal",
      4.5,
  )
  pdf.ln(2)

  pdf.set_font("Helvetica", "B", 10.5)
  pdf.set_text_color(0, 0, 0)
  pdf.cell(
      0,
      6,
      "PERFIL PROFESIONAL",
      border="B",
      new_x="LMARGIN",
      new_y="NEXT",
  )
  pdf.ln(1.5)
  pdf.set_font("Helvetica", "", 9.5)
  escribir_parrafo(pdf, cv_data.get("resumen_ejecutivo", ""), 4.8)
  pdf.ln(3)

  pdf.set_font("Helvetica", "B", 10.5)
  pdf.cell(
      0,
      6,
      "COMPETENCIAS CLAVE Y MARCOS REGULATORIOS (ATS KEYWORDS)",
      border="B",
      new_x="LMARGIN",
      new_y="NEXT",
  )
  pdf.ln(1.5)
  pdf.set_font("Helvetica", "", 9.5)
  skills = " | ".join(cv_data.get("competencias_ats", []))
  escribir_parrafo(pdf, skills, 4.8)
  pdf.ln(3)

  pdf.set_font("Helvetica", "B", 10.5)
  pdf.cell(
      0,
      6,
      "EXPERIENCIA PROFESIONAL",
      border="B",
      new_x="LMARGIN",
      new_y="NEXT",
  )
  pdf.ln(1.5)
  for exp in cv_data.get("experiencia_adaptada", []):
    pdf.set_font("Helvetica", "B", 9.5)
    escribir_parrafo(pdf, exp.get("cargo_y_empresa", ""), 5)
    pdf.set_font("Helvetica", "", 9.5)
    for logro in exp.get("logros", []):
      escribir_parrafo(pdf, f"- {logro}", 4.6)
    pdf.ln(2)

  pdf.set_font("Helvetica", "B", 10.5)
  pdf.cell(
      0,
      6,
      "FORMACION ACADEMICA Y CERTIFICACIONES",
      border="B",
      new_x="LMARGIN",
      new_y="NEXT",
  )
  pdf.ln(1.5)
  pdf.set_font("Helvetica", "B", 9.5)
  escribir_parrafo(
      pdf,
      "- Master en LegalTech y Derecho de la Ciberseguridad | Esneca Business"
      " School (2025) - Titulo con Apostilla de La Haya.",
      4.8,
  )
  escribir_parrafo(
      pdf,
      "- Licenciada en Derecho (Abogada) | Universidad Santa Maria (2005).",
      4.8,
  )
  pdf.set_font("Helvetica", "", 9.5)
  escribir_parrafo(
      pdf,
      "- Certificaciones y Herramientas: ISO 27001, DORA, EU AI Act, MiCA,"
      " RGPD, Prevencion de Blanqueo de Capitales (AML), VLEX, DocuSign,"
      " LegalSurf, Salesforce, Notion, GitHub.",
      4.8,
  )
  escribir_parrafo(
      pdf,
      "- Idiomas: Español (Nativo), Italiano (Intermedio B1), Ingles"
      " (Intermedio B1).",
      4.8,
  )

  pdf.output(ruta_archivo)


# 4. Generar PDFs y crear Issues
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
              f"CV Senior adaptado automáticamente para {of.get('empresa_o_rol')}"
          ),
          "content": contenido_b64,
      },
  )

  url_descarga_pdf = f"https://github.com/{REPO}/raw/main/{ruta_repo}"
  asunto_encoded = urllib.parse.quote(of.get("asunto_correo", ""))
  cuerpo_encoded = urllib.parse.quote(of.get("mensaje_postulacion", ""))
  link_mailto = f"mailto:?subject={asunto_encoded}&body={cuerpo_encoded}"

  cuerpo_issue = (
      f"🔔 Hola @{USUARIO}, encontré una vacante 100% en español del área"
      " jurídica/normativa (sin requisito de colegiación) ideal para tu perfil"
      " con Ciudadanía UE:\n\n"
      f"### 🎯 Vacante Detectada\n**Puesto y Empresa:** {of.get('empresa_o_rol')}\n"
      f"🌍 **Modalidad:** {of.get('modalidad')}\n"
      f"✅ **Verificación:** {of.get('confirmacion_idioma', 'Español - Sin colegiación')}\n"
      f"🔗 **[1. Ir al Portal de la Oferta para Postular]({of.get('link')})**\n\n---\n\n"
      "### 📄 Tu CV Senior Completo en PDF Adaptado (Anti-ATS + Ciudadanía UE)\n"
      "👉 **[2. 📥 TOCA AQUÍ PARA DESCARGAR TU CV EN PDF"
      f" ADAPTADO]({url_descarga_pdf})**\n\n---\n\n### ✉️ Mensaje / Carta de"
      " Presentación para Pegar en el Portal\n> **Asunto sugerido:**"
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
  print(f"✅ Issue y PDF Senior creados para: {of.get('empresa_o_rol')}")
