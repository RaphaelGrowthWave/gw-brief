import anthropic
import smtplib
import os
import re
import markdown
from urllib.parse import quote
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

# ── CONFIG ────────────────────────────────────────────────────
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]
GMAIL_USER         = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
TO_EMAIL           = os.environ.get("TO_EMAIL", GMAIL_USER)
PAGES_URL          = os.environ.get("PAGES_URL", "https://raphaelgrowthwave.github.io/gw-brief/")

GW_CONTEXT = """Tu es l'assistant stratégique de Raphaël, fondateur de Growth Wave.
Growth Wave est une agence B2B Data & CRM Intelligence française (ETI 50–500 salariés, CA >10M€).
Framework : Data Governance → Data Audit → Data Production → Data Automation.
Positionnement : "L'IA commerciale commence par une donnée propre."
Partenariat Anthropic validé. Vision : agents IA dans HubSpot/Salesforce à 30–80K€/an.
"""

SYSTEM_PROMPT = """Tu es l'assistant stratégique de Raphaël Masson, fondateur de Growth Wave.

RÈGLE ABSOLUE : Ta réponse commence IMMÉDIATEMENT par "## Résumé exécutif".
Aucun texte avant. Le premier caractère est #.
Termine TOUJOURS par "## Top 3 actions du jour"."""


# ── ÉTAPE 1 : Générer le brief ────────────────────────────────

def generate_brief():
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    today  = datetime.now().strftime("%A %d %B %Y")

    user_prompt = f"""MISSION ({today}) — Recherche les actualités des dernières 48h.
Ne cite que des faits vérifiés avec source URL réelle. Pas de source = pas d'actu.

SUJETS :
1. CRM & DATA B2B — HubSpot, Salesforce, data CRM, revenue operations
2. CLAUDE & ANTHROPIC — Anthropic news, Claude API, agents, programme partenaire
3. IA COMMERCIALE & SALES TECH — AI sales agents, CRM automation, revenue ops

CONTEXTE GW : Agence B2B Data & CRM Intelligence française, ETI 50–500 salariés.
Positionnement : "L'IA commerciale commence par une donnée propre."
Partenariat Anthropic validé. Vision agents IA dans HubSpot/Salesforce.

FORMAT STRICT :

## Résumé exécutif
[3 lignes max]

## 1. CRM & Data B2B

### [Titre actu]
- **Fait** : [2–3 phrases]
- **Source** : [URL complète — obligatoire]
- **Impact GW** : [concret]
- **Opportunité** : [action concrète]

[MAXIMUM 3 actus par section — pas plus]

## 2. Claude & Anthropic
[même structure, max 3 actus]

## 3. IA Commerciale & Sales Tech
[même structure, max 3 actus]

## Top 3 actions du jour
1. [action]
2. [action]
3. [action]
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

    # Supprimer tout ce qui précède le premier #
    if not brief_text.startswith('#'):
        idx = brief_text.find('\n#')
        if idx >= 0:
            brief_text = brief_text[idx:].lstrip('\n')

    # Supprimer les --- (redondant avec les titres)
    brief_text = re.sub(r'\n\s*---+\s*\n', '\n', brief_text)

    return brief_text


# ── HELPER : Résumé exécutif extrait pour l'email ────────────

def extract_summary(brief_text):
    """Extrait les 3 lignes du Résumé exécutif pour le corps du mail."""
    match = re.search(r'## Résumé exécutif\s*\n(.*?)(?=\n##)', brief_text, re.DOTALL)
    if match:
        summary = match.group(1).strip()
        # Nettoyer le markdown basique
        summary = re.sub(r'\*\*(.+?)\*\*', r'\1', summary)
        summary = re.sub(r'\*(.+?)\*', r'\1', summary)
        return summary[:600]
    return "Brief du jour disponible."


# ── HELPER : Lien Claude.ai pré-contextualisé ────────────────

def make_claude_link(action_text):
    full_prompt = f"""{GW_CONTEXT}
OPPORTUNITÉ À ANALYSER : {action_text}

Analyse cette opportunité et propose des premières étapes concrètes pour Raphaël."""
    return f"https://claude.ai/new?q={quote(full_prompt)}"


# ── HELPER : Injecter boutons sur les lignes Opportunité ──────

def inject_buttons(html):
    """
    Cherche les <li> contenant <strong>Opportunité</strong> et injecte
    un bouton Claude.ai juste après le </li>.
    """
    button_style = (
        "display:inline-block;background:#005CF4;color:#ffffff;"
        "text-decoration:none;padding:8px 18px;border-radius:6px;"
        "font-size:13px;font-weight:bold;margin:6px 0 16px 0"
    )

    def replace_match(m):
        full_li   = m.group(0)
        text_only = re.sub(r'<[^>]+>', '', full_li)

        # Pas de bouton si "pas d'opportunité"
        if re.search(r"pas d.opportunit", text_only, re.IGNORECASE):
            return full_li

        # Extraire le texte après "Opportunité :"
        opp = re.search(r"[Oo]pportunit[ée]\s*:?\s*(.+)", text_only, re.DOTALL)
        if opp:
            action = opp.group(1).strip()[:300]
            link   = make_claude_link(action)
            btn    = (
                f'<div style="margin:4px 0 12px 20px">'
                f'<a href="{link}" style="{button_style}">⚡ Explorer avec Claude →</a>'
                f'</div>'
            )
            return full_li + btn

        return full_li

    # Match les <li> qui contiennent "Opportunité" (avec le gras HTML)
    html = re.sub(
        r'<li[^>]*>(?:(?!</li>).)*[Oo]pportunit[ée](?:(?!</li>).)*</li>',
        replace_match,
        html,
        flags=re.DOTALL
    )
    return html


# ── ÉTAPE 2 : Générer la page HTML complète ──────────────────

def generate_html_page(brief_text):
    today_label = datetime.now().strftime("%d/%m/%Y")
    today_iso   = datetime.now().strftime("%Y-%m-%d")

    # Markdown → HTML
    md       = markdown.Markdown(extensions=['extra'])
    content  = md.convert(brief_text)

    # Styles GW sur les balises
    content = re.sub(r'<h2>', '<h2 style="color:#005CF4;border-bottom:2px solid #005CF4;padding-bottom:8px;margin-top:36px">', content)
    content = re.sub(r'<h3>', '<h3 style="background:#F0F5FF;padding:10px 14px;border-left:4px solid #005CF4;border-radius:0 6px 6px 0;margin-top:24px">', content)
    content = re.sub(r'<li>', '<li style="margin:6px 0;font-size:15px;line-height:1.6">', content)
    content = re.sub(r'<a href="http', '<a style="color:#005CF4;word-break:break-all" href="http', content)

    # Injecter les boutons
    content = inject_buttons(content)

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>GW Brief — {today_label}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Arial', sans-serif;
      background: #f5f7fa;
      color: #1a1a1a;
      padding: 0;
    }}
    .header {{
      background: #010513;
      padding: 20px 32px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      position: sticky;
      top: 0;
      z-index: 10;
    }}
    .header-title {{
      color: #F7F7F8;
      font-size: 20px;
      font-weight: bold;
      letter-spacing: -0.5px;
    }}
    .header-date {{
      color: #B8D3FA;
      font-size: 13px;
    }}
    .container {{
      max-width: 720px;
      margin: 32px auto;
      background: #ffffff;
      border-radius: 12px;
      padding: 36px 40px;
      box-shadow: 0 2px 12px rgba(0,0,0,0.07);
    }}
    ul {{ padding-left: 20px; }}
    p {{ margin: 8px 0; line-height: 1.7; }}
    strong {{ color: #002A7A; }}
    .footer {{
      text-align: center;
      color: #aaa;
      font-size: 12px;
      padding: 24px;
    }}
    @media (max-width: 600px) {{
      .container {{ margin: 12px; padding: 20px; }}
    }}
  </style>
</head>
<body>
  <div class="header">
    <span class="header-title">⚡ Growth Wave Brief</span>
    <span class="header-date">{today_label}</span>
  </div>

  <div class="container">
    {content}
  </div>

  <div class="footer">
    Généré automatiquement · Growth Wave Assistant · Claude Sonnet via Anthropic API · {today_iso}
  </div>
</body>
</html>"""


# ── ÉTAPE 3 : Email court avec lien ──────────────────────────

def send_email(summary_text, pages_url):
    today_label = datetime.now().strftime("%d/%m")

    subject = f"⚡ GW Brief — {today_label}"

    # Corps HTML de l'email : résumé + bouton vers la page
    html = f"""
    <html>
    <body style="font-family:'Arial',sans-serif;max-width:560px;margin:auto;
                 padding:24px;color:#1a1a1a;background:#ffffff">

      <div style="background:#010513;padding:16px 24px;border-radius:10px;margin-bottom:24px">
        <span style="color:#F7F7F8;font-size:18px;font-weight:bold">⚡ Growth Wave Brief</span>
        <span style="color:#B8D3FA;font-size:13px;margin-left:12px">{today_label}</span>
      </div>

      <p style="font-size:15px;line-height:1.75;margin-bottom:24px">{summary_text}</p>

      <div style="text-align:center;margin:28px 0">
        <a href="{pages_url}" style="display:inline-block;background:#005CF4;color:#ffffff;
           text-decoration:none;padding:12px 32px;border-radius:8px;font-size:15px;
           font-weight:bold">→ Lire le brief complet</a>
      </div>

      <div style="margin-top:32px;padding-top:14px;border-top:1px solid #e5e5e5;
                  color:#aaa;font-size:12px;text-align:center">
        Généré automatiquement · Growth Wave Assistant
      </div>

    </body>
    </html>
    """

    msg            = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = GMAIL_USER
    msg['To']      = TO_EMAIL
    msg.attach(MIMEText(html, 'html'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, TO_EMAIL, msg.as_string())

    print(f"✓ Email envoyé à {TO_EMAIL}")


# ── MAIN ─────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Génération du brief...")

    brief_text = generate_brief()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Brief généré ✓ ({len(brief_text)} chars)")

    # Sauvegarder la page HTML (sera commitée par GitHub Actions)
    html_page = generate_html_page(brief_text)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_page)
    print("✓ index.html généré")

    # Extraire le résumé pour l'email
    summary = extract_summary(brief_text)

    # Envoyer l'email court
    send_email(summary, PAGES_URL)

    print("Done.")
