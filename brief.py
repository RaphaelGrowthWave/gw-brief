import anthropic
import smtplib
import os
import re
from urllib.parse import quote
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

# ── CONFIG ────────────────────────────────────────────────────
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]
GMAIL_USER         = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
TO_EMAIL           = os.environ.get("TO_EMAIL", GMAIL_USER)

GW_CONTEXT = """Tu es l'assistant stratégique de Raphaël, fondateur de Growth Wave.
Growth Wave est une agence B2B Data & CRM Intelligence française (ETI 50–500 salariés, CA >10M€).
Framework : Data Governance → Data Audit → Data Production → Data Automation.
Positionnement : "L'IA commerciale commence par une donnée propre."
Partenariat Anthropic validé. Vision : agents IA dans HubSpot/Salesforce à 30–80K€/an.
"""


# ── ÉTAPE 1 : Générer le brief ────────────────────────────────

def generate_brief():
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    today  = datetime.now().strftime("%A %d %B %Y")

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
Recherche les actualités des dernières 48h. NE CITE QUE DES FAITS VÉRIFIÉS avec source URL réelle.

SUJETS :
1. CRM & DATA B2B — HubSpot, Salesforce, data CRM, revenue operations, B2B data quality
2. CLAUDE & ANTHROPIC — Anthropic news, Claude API, programme partenaire, agents IA
3. IA COMMERCIALE & SALES TECH — AI sales agents, CRM automation, AI revenue ops

FORMAT — commence DIRECTEMENT par ## Résumé exécutif, rien avant :

## Résumé exécutif
[3 lignes max]

## 1. CRM & Data B2B

### [Titre actu]
- **Fait** : [2–3 phrases]
- **Source** : [URL complète — obligatoire]
- **Impact GW** : [concret]
- **Opportunité** : [action concrète, ou "Pas d'opportunité immédiate"]

[répéter pour chaque actu]

## 2. Claude & Anthropic
[même structure]

## 3. IA Commerciale & Sales Tech
[même structure]

## Top 3 actions du jour
1. [action]
2. [action]
3. [action]

RÈGLES :
- Commence DIRECTEMENT par ## Résumé exécutif
- Source obligatoire pour chaque actu — pas de source = ne pas inclure
- Termine TOUJOURS par ## Top 3 actions du jour
- Direct, dense, 5 min de lecture max
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=6000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )

    brief_text = ""
    for block in response.content:
        if block.type == "text":
            brief_text += block.text

    # Supprimer tout ce qui précède le premier ##
    first_header = brief_text.find('## ')
    if first_header > 0:
        brief_text = brief_text[first_header:]

    # Supprimer toutes les lignes --- (redondant avec les titres de section)
    lines = brief_text.split('\n')
    lines = [l for l in lines if l.strip() != '---']
    brief_text = '\n'.join(lines)

    return brief_text


# ── HELPER : Lien Claude.ai pré-contextualisé ────────────────

def make_claude_link(action_text):
    """
    Génère une URL claude.ai/new?q=... avec contexte GW + l'opportunité.
    Un clic = conversation Claude prête à travailler sur ce sujet.
    """
    full_prompt = f"""{GW_CONTEXT}
SUJET : {action_text}

Analyse cette opportunité en détail et propose des premières étapes concrètes et actionnables pour Raphaël."""
    return f"https://claude.ai/new?q={quote(full_prompt)}"


# ── ÉTAPE 2 : Formater en HTML ────────────────────────────────

def format_email_html(brief_text):
    today = datetime.now().strftime("%d/%m/%Y")

    lines      = brief_text.split('\n')
    html_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # H2
        if line.startswith('## '):
            html_lines.append(
                f'<h2 style="color:#005CF4;border-bottom:2px solid #005CF4;'
                f'padding-bottom:6px;margin-top:32px;margin-bottom:12px">{line[3:]}</h2>'
            )

        # H3
        elif line.startswith('### '):
            html_lines.append(
                f'<h3 style="color:#1a1a1a;background:#F0F5FF;padding:8px 12px;'
                f'border-left:4px solid #005CF4;margin-top:20px;margin-bottom:8px;'
                f'border-radius:0 4px 4px 0">{line[4:]}</h3>'
            )

        # Ligne vide
        elif line.strip() == '':
            html_lines.append('<div style="height:4px"></div>')

        # Ligne normale
        else:
            formatted = line

            # Gras **texte**
            while '**' in formatted:
                formatted = formatted.replace('**', '<strong>', 1)
                formatted = formatted.replace('**', '</strong>', 1)

            # Lien markdown [texte](url)
            formatted = re.sub(
                r'\[([^\]]+)\]\((https?://[^\)]+)\)',
                r'<a href="\2" style="color:#005CF4">\1</a>',
                formatted
            )

            # URL brute dans les lignes Source → lien cliquable
            if 'Source' in formatted:
                formatted = re.sub(
                    r'(https?://[^\s<"]+)',
                    r'<a href="\1" style="color:#005CF4;font-size:12px;word-break:break-all">\1</a>',
                    formatted
                )

            # Puce - texte → bloc avec barre latérale
            if formatted.strip().startswith('- '):
                content = formatted.strip()[2:]

                # Cas spécial : ligne Opportunité → ajouter bouton automatiquement
                is_opportunite = (
                    '<strong>Opportunité</strong>' in content
                    and 'Pas d\'opportunité' not in content
                    and 'Pas d'opportunité' not in content
                )

                html_lines.append(
                    f'<div style="margin:6px 0 6px 8px;padding:6px 12px;'
                    f'border-left:3px solid #B8D3FA;font-size:14px">{content}</div>'
                )

                # Bouton généré automatiquement depuis le texte de l'opportunité
                if is_opportunite:
                    # Extraire le texte brut sans HTML pour le lien
                    clean = re.sub(r'<[^>]+>', '', content)
                    clean = re.sub(r'^Opportunité\s*:\s*', '', clean).strip()
                    if clean:
                        link = make_claude_link(clean)
                        html_lines.append(
                            f'<div style="margin:8px 0 14px 8px">'
                            f'<a href="{link}" style="display:inline-block;background:#005CF4;'
                            f'color:#ffffff;text-decoration:none;padding:7px 16px;'
                            f'border-radius:5px;font-size:12px;font-weight:bold">'
                            f'⚡ Explorer cette opportunité →</a></div>'
                        )

            # Numéroté 1. 2. 3.
            elif re.match(r'^\d+\.', formatted.strip()):
                html_lines.append(
                    f'<p style="margin:6px 0;padding-left:8px;font-size:14px">{formatted.strip()}</p>'
                )
            else:
                html_lines.append(f'<p style="margin:4px 0">{formatted}</p>')

        i += 1

    html_body = '\n'.join(html_lines)

    return f"""
    <html>
    <body style="font-family:'Arial',sans-serif;max-width:680px;margin:auto;
                 padding:24px;color:#1a1a1a;background:#ffffff">

      <!-- Header -->
      <div style="background:#010513;padding:18px 24px;border-radius:10px;margin-bottom:28px">
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


# ── ÉTAPE 3 : Envoyer ────────────────────────────────────────

def send_email(subject, html_content):
    msg            = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = GMAIL_USER
    msg['To']      = TO_EMAIL
    msg.attach(MIMEText(html_content, 'html'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, TO_EMAIL, msg.as_string())

    print(f"✓ Brief envoyé à {TO_EMAIL}")


# ── MAIN ─────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Génération du brief...")

    brief_text = generate_brief()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Brief généré ✓ ({len(brief_text)} caractères)")

    html = format_email_html(brief_text)

    today_str = datetime.now().strftime("%d/%m")
    send_email(f"⚡ GW Brief — {today_str}", html)

    print("Done.")
