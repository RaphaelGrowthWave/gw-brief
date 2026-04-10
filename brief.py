import anthropic
import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

# ── CONFIG ────────────────────────────────────────────────────
# Ces variables viennent des secrets GitHub Actions (jamais en dur dans le code)
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GMAIL_USER        = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
TO_EMAIL          = os.environ.get("TO_EMAIL", GMAIL_USER)  # Par défaut, s'envoie à soi-même


# ── ÉTAPE 1 : Générer le brief via Claude + web search ────────

def generate_brief():
    """
    Demande à Claude de chercher les news des 48h et de les analyser
    sous l'angle Growth Wave. Un seul appel API — Claude décide lui-même
    quoi chercher selon le prompt.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    today = datetime.now().strftime("%A %d %B %Y")

    prompt = f"""Tu es l'assistant stratégique de Raphaël, fondateur de Growth Wave.

CONTEXTE GROWTH WAVE :
- Agence B2B Data & CRM Intelligence française
- Cibles : ETI B2B (50–500 salariés, CA > 10M€, 15+ commerciaux)
- Framework : Data Governance → Data Audit → Data Production → Data Automation
- Positionnement IA : "L'IA commerciale commence par une donnée propre"
- Revenue : prestations one-shot (min 10K€) + retainer + BDD.fr (fichiers SIRENE enrichis)
- Partenariat Anthropic/Claude : première étape du programme partenaire validée
- Vision 18–42 mois : agents IA intégrés dans HubSpot/Salesforce à 30–80K€/an
- Différenciateur : double légitimité sales B2B + data + IA

MISSION DU JOUR ({today}) :
Recherche les actualités des dernières 48h sur ces 3 sujets et produis un brief actionnable.

SUJETS À COUVRIR :

1. CRM & DATA B2B
   Mots-clés : HubSpot, Salesforce, data CRM, revenue operations, sales enablement, B2B data quality

2. CLAUDE & ANTHROPIC
   Mots-clés : Anthropic news, Claude API updates, Claude partner program, Claude agents

3. IA COMMERCIALE & SALES TECH
   Mots-clés : AI sales agents, CRM automation, AI revenue ops, sales AI tools

FORMAT DE RÉPONSE :

## Résumé exécutif
3 lignes max. L'essentiel du jour — ce que Raphaël doit savoir avant tout.

## 1. CRM & Data B2B
Pour chaque actu trouvée :
- **Fait** : [2–3 phrases]
- **Impact GW** : [concret, direct]
- **Opportunité** : [action possible ou "pas d'opportunité immédiate"]

## 2. Claude & Anthropic
[même structure]

## 3. IA Commerciale & Sales Tech
[même structure]

## Top 3 actions du jour
Les 3 trucs à faire ou surveiller suite à ces news. Concret, pas de bullshit.

RÈGLES :
- Direct, dense, zéro blabla
- Si une news n'a pas d'angle GW, dis-le en une ligne et passe
- Raphaël lit ce brief en 5 minutes maximum
- Privilégie les opportunités business concrètes (prospect à cibler, angle de pitch, feature à surveiller)
"""

    # Appel Claude avec l'outil de recherche web natif
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2500,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )

    # Extraire uniquement les blocs texte (pas les appels d'outil)
    brief_text = ""
    for block in response.content:
        if block.type == "text":
            brief_text += block.text

    return brief_text


# ── ÉTAPE 2 : Formater en HTML ────────────────────────────────

def format_email_html(brief_text):
    """
    Convertit le brief markdown en HTML lisible.
    Utilise les couleurs Growth Wave.
    """
    today = datetime.now().strftime("%d/%m/%Y")

    # Conversion basique markdown → HTML ligne par ligne
    lines = brief_text.split('\n')
    html_lines = []

    for line in lines:
        if line.startswith('## '):
            # Titre de section → H2 bleu GW
            html_lines.append(
                f'<h2 style="color:#005CF4;border-bottom:2px solid #005CF4;'
                f'padding-bottom:6px;margin-top:28px">{line[3:]}</h2>'
            )
        elif line.startswith('### '):
            html_lines.append(f'<h3 style="color:#002A7A">{line[4:]}</h3>')
        elif line.strip() == '':
            html_lines.append('<br>')
        else:
            # Gestion du gras inline **texte**
            formatted = line
            while '**' in formatted:
                formatted = formatted.replace('**', '<strong>', 1)
                formatted = formatted.replace('**', '</strong>', 1)
            # Tiret de liste → puce simple
            if formatted.strip().startswith('- '):
                formatted = f'&bull; {formatted.strip()[2:]}'
            html_lines.append(f'<p style="margin:4px 0">{formatted}</p>')

    html_body = '\n'.join(html_lines)

    # Template email Growth Wave
    html = f"""
    <html>
    <body style="font-family:'Arial',sans-serif;max-width:680px;margin:auto;
                 padding:24px;color:#1a1a1a;background:#ffffff">

      <!-- Header -->
      <div style="background:#010513;padding:18px 24px;border-radius:10px;
                  margin-bottom:28px;display:flex;align-items:center">
        <span style="color:#F7F7F8;font-size:20px;font-weight:bold;letter-spacing:-0.5px">
          ⚡ Growth Wave Brief
        </span>
        <span style="color:#B8D3FA;font-size:13px;margin-left:14px">{today}</span>
      </div>

      <!-- Corps -->
      <div style="line-height:1.75;font-size:15px">
        {html_body}
      </div>

      <!-- Footer -->
      <div style="margin-top:36px;padding-top:16px;border-top:1px solid #e5e5e5;
                  color:#aaa;font-size:12px">
        Généré automatiquement · Growth Wave Assistant · Claude Sonnet via Anthropic API
      </div>

    </body>
    </html>
    """

    return html


# ── ÉTAPE 3 : Envoyer via Gmail SMTP ─────────────────────────

def send_email(subject, html_content):
    """
    Envoi via Gmail SMTP avec App Password.
    Plus simple qu'OAuth pour un cron — aucune expiration de token.
    """
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = GMAIL_USER
    msg['To']      = TO_EMAIL

    # On attache uniquement la version HTML (pas de fallback texte pour l'instant)
    msg.attach(MIMEText(html_content, 'html'))

    # Connexion SSL port 465 — plus robuste que STARTTLS pour les crons
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, TO_EMAIL, msg.as_string())

    print(f"✓ Brief envoyé à {TO_EMAIL}")


# ── MAIN ──────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Génération du brief...")

    brief_text = generate_brief()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Brief généré ✓ ({len(brief_text)} caractères)")

    html = format_email_html(brief_text)

    today_str = datetime.now().strftime("%d/%m")
    send_email(f"⚡ GW Brief — {today_str}", html)

    print("Done.")
