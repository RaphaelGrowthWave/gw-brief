import anthropic
import smtplib
import os
import re
import json
import markdown
from urllib.parse import quote
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── CONFIG ────────────────────────────────────────────────────
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]
GMAIL_USER         = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
TO_EMAIL           = os.environ.get("TO_EMAIL", GMAIL_USER)
PAGES_URL          = os.environ.get("PAGES_URL", "https://raphaelgrowthwave.github.io/gw-brief/")
MEMORY_FILE        = "news_memory.json"
MEMORY_DAYS        = 14

GW_CONTEXT = """Tu es l'assistant stratégique de Raphaël, fondateur de Growth Wave.
Growth Wave est une agence B2B Data & CRM Intelligence française (ETI 50–500 salariés, CA >10M€).
Framework : Data Governance → Data Audit → Data Production → Data Automation.
Positionnement : "L'IA commerciale commence par une donnée propre."
Partenariat Anthropic validé. Vision : agents IA dans HubSpot/Salesforce à 30–80K€/an.
"""

SYSTEM_PROMPT = """Tu es l'assistant stratégique de Raphaël Masson, fondateur de Growth Wave.

RÈGLES ABSOLUES :
1. Ta réponse commence IMMÉDIATEMENT par "## Résumé exécutif". Aucun texte avant. Le premier caractère est #.
2. "## Top 3 actions du jour" vient EN DEUXIÈME, juste après le Résumé exécutif, AVANT les sections détaillées.
3. FILTRE SIGNAL/BRUIT : N'inclus une actu QUE si elle génère une action concrète pour GW dans les 7 prochains jours.
4. DÉDUPLICATION : N'inclus JAMAIS une actu déjà vue dans les jours précédents (liste fournie). S'il n'y a que 2 vraies nouvelles news actionnables, le brief fait 2 actus — c'est normal."""


# ── MÉMOIRE ───────────────────────────────────────────────────

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {}
    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        memory = json.load(f)
    cutoff = (datetime.now() - timedelta(days=MEMORY_DAYS)).strftime("%Y-%m-%d")
    return {k: v for k, v in memory.items() if v >= cutoff}

def save_memory(memory, new_titles):
    today = datetime.now().strftime("%Y-%m-%d")
    for title in new_titles:
        key = title.strip().lower()[:120]
        if key:
            memory[key] = today
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)
    print(f"✓ Mémoire mise à jour ({len(memory)} entrées)")

def format_memory_for_prompt(memory):
    if not memory:
        return "Aucune actu mémorisée."
    titles = sorted(memory.keys(), key=lambda k: memory[k], reverse=True)[:40]
    return "\n".join(f"- {t}" for t in titles)

def extract_titles_from_brief(brief_text):
    return re.findall(r'^### (.+)$', brief_text, re.MULTILINE)


# ── ÉTAPE 1 : Générer le brief ────────────────────────────────

def generate_brief(memory):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    today  = datetime.now().strftime("%A %d %B %Y")
    memory_str = format_memory_for_prompt(memory)

    user_prompt = f"""MISSION ({today}) — Recherche les actualités des dernières 48h.
Ne cite que des faits vérifiés avec source URL réelle. Pas de source = pas d'actu.

ACTUS DÉJÀ VUES — NE PAS RÉUTILISER :
{memory_str}

FILTRE : Nouvelle actu ? Action concrète pour GW dans les 7 jours ? Si non → ignore.

SUJETS :
1. CRM & DATA B2B — HubSpot, Salesforce, data CRM, revenue operations
2. CLAUDE & ANTHROPIC — Anthropic news, Claude API, agents, programme partenaire
3. CLAUDE PARTNER NETWORK — Cherche spécifiquement :
   - Reddit r/ClaudeAI : discussions CPN, retours d'expérience, certifications CCA
   - "Claude Partner Network" site:reddit.com OR site:linkedin.com OR site:anthropic.com
   - Anthropic Academy : nouveaux cours, deadlines, contenu CCA Foundations
   - Témoignages de partners sur LinkedIn ou forums
4. IA COMMERCIALE & SALES TECH — AI sales agents, CRM automation, revenue ops

CONTEXTE GW :
- Agence B2B Data & CRM Intelligence française, ETI 50–500 salariés
- Positionnement : "L'IA commerciale commence par une donnée propre."
- Partenariat Anthropic validé (avril 2026). Deadline CCA Foundations : 21 mai 2026.
- Vision agents IA dans HubSpot/Salesforce.

FORMAT STRICT :

## Résumé exécutif
[3 lignes max]

## Top 3 actions du jour
1. [action concrète cette semaine]
2. [action concrète cette semaine]
3. [action concrète cette semaine]

## 1. CRM & Data B2B

### [Titre actu]
- **Fait** : [2–3 phrases]
- **Source** : [URL complète]
- **Impact GW** : [concret]
- **Opportunité** : [action dans les 7 jours]

[MAX 3 actus par section]

## 2. Claude & Anthropic
[même structure, max 3]

## 3. Claude Partner Network
[même structure, max 3 — inclure retours Reddit/LinkedIn si trouvés]

## 4. IA Commerciale & Sales Tech
[même structure, max 3]
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=6000,
        system=SYSTEM_PROMPT,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": user_prompt}]
    )

    brief_text = ""
    for block in response.content:
        if block.type == "text":
            brief_text += block.text

    if not brief_text.startswith('#'):
        idx = brief_text.find('\n#')
        if idx >= 0:
            brief_text = brief_text[idx:].lstrip('\n')

    brief_text = re.sub(r'\n\s*---+\s*\n', '\n', brief_text)
    return brief_text


# ── HELPERS ───────────────────────────────────────────────────

def extract_summary(brief_text):
    match = re.search(r'## Résumé exécutif\s*\n(.*?)(?=\n##)', brief_text, re.DOTALL)
    if match:
        s = match.group(1).strip()
        s = re.sub(r'\*\*(.+?)\*\*', r'\1', s)
        s = re.sub(r'\*(.+?)\*', r'\1', s)
        return s[:600]
    return "Brief du jour disponible."

def extract_toc(brief_text):
    toc = []
    current_section = ""
    for line in brief_text.split('\n'):
        if line.startswith('## ') and not line.startswith('### '):
            current_section = line[3:].strip()
        elif line.startswith('### '):
            toc.append((current_section, line[4:].strip()))
    return toc

def make_claude_link(action_text):
    full_prompt = f"""{GW_CONTEXT}
OPPORTUNITÉ À ANALYSER : {action_text}

Analyse cette opportunité et propose des premières étapes concrètes pour Raphaël."""
    return f"https://claude.ai/new?q={quote(full_prompt)}"

def inject_buttons(html):
    button_style = (
        "display:inline-block;background:#005CF4;color:#ffffff;"
        "text-decoration:none;padding:8px 18px;border-radius:6px;"
        "font-size:13px;font-weight:bold;margin:6px 0 16px 0"
    )
    def replace_match(m):
        full_li   = m.group(0)
        text_only = re.sub(r'<[^>]+>', '', full_li)
        if re.search(r"pas d.opportunit", text_only, re.IGNORECASE):
            return full_li
        opp = re.search(r"[Oo]pportunit[ée]\s*:?\s*(.+)", text_only, re.DOTALL)
        if opp:
            action = opp.group(1).strip()[:300]
            link   = make_claude_link(action)
            btn    = (f'<div style="margin:4px 0 12px 20px">'
                      f'<a href="{link}" style="{button_style}">⚡ Explorer avec Claude →</a>'
                      f'</div>')
            return full_li + btn
        return full_li
    return re.sub(
        r'<li[^>]*>(?:(?!</li>).)*[Oo]pportunit[ée](?:(?!</li>).)*</li>',
        replace_match, html, flags=re.DOTALL
    )


# ── ÉTAPE 2 : Page HTML ───────────────────────────────────────

def generate_html_page(brief_text):
    today_label = datetime.now().strftime("%d/%m/%Y")
    today_iso   = datetime.now().strftime("%Y-%m-%d")

    md      = markdown.Markdown(extensions=['extra'])
    content = md.convert(brief_text)
    content = re.sub(r'<h2>', '<h2 style="color:#005CF4;border-bottom:2px solid #005CF4;padding-bottom:8px;margin-top:36px">', content)
    content = re.sub(r'<h3>', '<h3 style="background:#F0F5FF;padding:10px 14px;border-left:4px solid #005CF4;border-radius:0 6px 6px 0;margin-top:24px">', content)
    content = re.sub(r'<li>', '<li style="margin:6px 0;font-size:15px;line-height:1.6">', content)
    content = re.sub(r'<a href="http', '<a style="color:#005CF4;word-break:break-all" href="http', content)
    content = inject_buttons(content)

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>GW Brief — {today_label}</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Arial',sans-serif;background:#f5f7fa;color:#1a1a1a}}
    .header{{background:#010513;padding:20px 32px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:10}}
    .header-title{{color:#F7F7F8;font-size:20px;font-weight:bold;letter-spacing:-.5px}}
    .header-date{{color:#B8D3FA;font-size:13px}}
    .container{{max-width:720px;margin:32px auto;background:#fff;border-radius:12px;padding:36px 40px;box-shadow:0 2px 12px rgba(0,0,0,.07)}}
    ul{{padding-left:20px}}p{{margin:8px 0;line-height:1.7}}strong{{color:#002A7A}}
    .footer{{text-align:center;color:#aaa;font-size:12px;padding:24px}}
    @media(max-width:600px){{.container{{margin:12px;padding:20px}}}}
  </style>
</head>
<body>
  <div class="header"><span class="header-title">⚡ Growth Wave Brief</span><span class="header-date">{today_label}</span></div>
  <div class="container">{content}</div>
  <div class="footer">Généré automatiquement · Growth Wave Assistant · Claude Sonnet via Anthropic API · {today_iso}</div>
</body></html>"""


# ── ÉTAPE 3 : Email avec TOC ──────────────────────────────────

def send_email(summary_text, toc, pages_url):
    today_label = datetime.now().strftime("%d/%m")

    # TOC groupée par section
    toc_html = ""
    if toc:
        current_section = ""
        toc_html = '<div style="margin:20px 0;padding:16px;background:#F0F5FF;border-radius:8px;font-size:13px">'
        toc_html += '<div style="font-weight:bold;color:#002A7A;margin-bottom:10px">📋 Au programme aujourd\'hui</div>'
        for section, title in toc:
            if section != current_section:
                current_section = section
                short = re.sub(r'^\d+\.\s*', '', section)
                toc_html += f'<div style="color:#005CF4;font-weight:bold;margin-top:8px;margin-bottom:3px">{short}</div>'
            toc_html += f'<div style="color:#444;padding-left:12px;margin:2px 0">· {title}</div>'
        toc_html += '</div>'

    html = f"""<html><body style="font-family:'Arial',sans-serif;max-width:560px;margin:auto;padding:24px;color:#1a1a1a;background:#fff">
      <div style="background:#010513;padding:16px 24px;border-radius:10px;margin-bottom:24px">
        <span style="color:#F7F7F8;font-size:18px;font-weight:bold">⚡ Growth Wave Brief</span>
        <span style="color:#B8D3FA;font-size:13px;margin-left:12px">{today_label}</span>
      </div>
      <p style="font-size:15px;line-height:1.75;margin-bottom:16px">{summary_text}</p>
      {toc_html}
      <div style="text-align:center;margin:24px 0">
        <a href="{pages_url}" style="display:inline-block;background:#005CF4;color:#fff;text-decoration:none;padding:12px 32px;border-radius:8px;font-size:15px;font-weight:bold">→ Lire le brief complet</a>
      </div>
      <div style="margin-top:28px;padding-top:14px;border-top:1px solid #e5e5e5;color:#aaa;font-size:12px;text-align:center">Généré automatiquement · Growth Wave Assistant</div>
    </body></html>"""

    msg            = MIMEMultipart('alternative')
    msg['Subject'] = f"⚡ GW Brief — {today_label}"
    msg['From']    = GMAIL_USER
    msg['To']      = TO_EMAIL
    msg.attach(MIMEText(html, 'html'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, TO_EMAIL, msg.as_string())
    print(f"✓ Email envoyé à {TO_EMAIL}")


# ── MAIN ─────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Chargement mémoire...")
    memory = load_memory()
    print(f"  → {len(memory)} actus mémorisées")

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Génération du brief...")
    brief_text = generate_brief(memory)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Brief généré ✓ ({len(brief_text)} chars)")

    new_titles = extract_titles_from_brief(brief_text)
    save_memory(memory, new_titles)

    html_page = generate_html_page(brief_text)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_page)
    print("✓ index.html généré")

    summary = extract_summary(brief_text)
    toc     = extract_toc(brief_text)
    send_email(summary, toc, PAGES_URL)
    print("Done.")
