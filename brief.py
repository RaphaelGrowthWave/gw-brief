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

# Contexte GW injecté dans les liens d'action Claude.ai
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
Recherche les actualités des dernières 48h. NE CITE QUE DES FAITS VÉRIFIÉS avec une source URL réelle.
Si tu ne trouves pas de source pour une news, ne l'inclus pas.

SUJETS :
1. CRM & DATA B2B — HubSpot, Salesforce, data CRM, revenue operations, B2B data quality
2. CLAUDE & ANTHROPIC — Anthropic news, Claude API, programme partenaire, agents IA
3. IA COMMERCIALE & SALES TECH — AI sales agents, CRM automation, AI revenue ops

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RÈGLE ABSOLUE SUR LE FORMAT :
Ta réponse doit commencer DIRECTEMENT par "## Résumé exécutif".
Pas d'introduction, pas de "Voilà le brief", pas de phrase avant le premier ##.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FORMAT STRICT — respecte-le à la lettre :

## Résumé exécutif
[3 lignes max, l'essentiel du jour]

---

## 1. CRM & Data B2B

### 📌 [Titre de l'actu]
- **Fait** : [2–3 phrases]
- **Source** : [URL complète — obligatoire. Si pas de source = ne pas inclure cette news]
- **Impact GW** : [concret, direct]
- **Opportunité** : [action concrète]
[ACTION: Rédiger un pitch court pour les CRO HubSpot sur le pricing Breeze à l'outcome]

[Répéter pour chaque actu]

---

## 2. Claude & Anthropic

### 📌 [Titre de l'actu]
- **Fait** : [2–3 phrases]
- **Source** : [URL complète]
- **Impact GW** : [concret, direct]
- **Opportunité** : [action concrète]
[ACTION: Tester Claude Managed Agents sur un enrichissement SIRENE → push HubSpot]

[Répéter pour chaque actu]

---

## 3. IA Commerciale & Sales Tech

### 📌 [Titre de l'actu]
- **Fait** : [2–3 phrases]
- **Source** : [URL complète]
- **Impact GW** : [concret, direct]
- **Opportunité** : [action concrète]
[ACTION: Identifier 10 partenaires HubSpot mid-market à approcher en co-selling]

[Répéter pour chaque actu]

---

## Top 3 actions du jour
1. [action concrète]
2. [action concrète]
3. [action concrète]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RÈGLES :
- Commence DIRECTEMENT par ## Résumé exécutif, rien avant
- Le tag [ACTION: texte] est OBLIGATOIRE après chaque bloc Opportunité — copie exactement ce format avec les crochets
- L'action doit décrire quelque chose que Claude peut faire pour Raphaël (analyse, liste, pitch, séquence...)
- Termine TOUJOURS par ## Top 3 actions du jour — c'est la section la plus importante
- Direct, dense, zéro blabla. Lecture 5 min max.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4500,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}]
    )

    brief_text = ""
    for block in response.content:
        if block.type == "text":
            brief_text += block.text

    # ── FIX 1 : Supprimer tout ce qui précède le premier ## ───
    # Claude ajoute parfois une phrase d'intro avant le vrai contenu
    first_header = brief_text.find('## ')
    if first_header > 0:
        brief_text = brief_text[first_header:]

    return brief_text


# ── HELPER : Lien Claude.ai pré-contextualisé ────────────────

def make_claude_link(action_description):
    """
    Génère une URL claude.ai/new?q=... avec contexte GW + action.
    Un clic = une conversation Claude prête à travailler.
    """
    full_prompt = f"""{GW_CONTEXT}
ACTION DEMANDÉE : {action_description}

Produis une analyse détaillée et des premières étapes concrètes et actionnables pour Raphaël."""

    encoded = quote(full_prompt)
    return f"https://claude.ai/new?q={encoded}"


# ── ÉTAPE 2 : Formater en HTML ────────────────────────────────

def format_email_html(brief_text):
    today = datetime.now().strftime("%d/%m/%Y")

    lines      = brief_text.split('\n')
    html_lines = []

    for line in lines:

        # Séparateur --- → <hr>
        if line.strip() == '---':
            html_lines.append(
                '<hr style="border:none;border-top:1px solid #e5e5e5;margin:20px 0">'
            )

        # H2
        elif line.startswith('## '):
            html_lines.append(
                f'<h2 style="color:#005CF4;border-bottom:2px solid #005CF4;'
                f'padding-bottom:6px;margin-top:28px;margin-bottom:12px">{line[3:]}</h2>'
            )

        # H3
        elif line.startswith('### '):
            html_lines.append(
                f'<h3 style="color:#002A7A;margin-top:20px;margin-bottom:8px">{line[4:]}</h3>'
            )

        # [ACTION: ...] → bouton cliquable
        elif line.strip().startswith('[ACTION:') and line.strip().endswith(']'):
            action_text = line.strip()[8:-1].strip()
            link        = make_claude_link(action_text)
            html_lines.append(
                f'<div style="margin:14px 0">'
                f'<a href="{link}" style="display:inline-block;background:#005CF4;color:#ffffff;'
                f'text-decoration:none;padding:9px 18px;border-radius:6px;font-size:13px;'
                f'font-weight:bold;letter-spacing:0.2px">⚡ {action_text} →</a>'
                f'</div>'
            )

        # Ligne vide
        elif line.strip() == '':
            html_lines.append('<br>')

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

            # URL brute dans une ligne Source → lien cliquable
            if 'Source' in formatted:
                formatted = re.sub(
                    r'(https?://[^\s<"]+)',
                    r'<a href="\1" style="color:#005CF4;font-size:12px">\1</a>',
                    formatted
                )

            # Puce - texte → bloc avec barre latérale bleue
            if formatted.strip().startswith('- '):
                formatted = (
                    f'<div style="margin:6px 0 6px 8px;padding:6px 12px;'
                    f'border-left:3px solid #B8D3FA;font-size:14px">'
                    f'{formatted.strip()[2:]}</div>'
                )
            # Numéroté 1. 2. 3.
            elif re.match(r'^\d+\.', formatted.strip()):
                formatted = f'<p style="margin:6px 0;padding-left:8px">{formatted.strip()}</p>'
            else:
                formatted = f'<p style="margin:4px 0">{formatted}</p>'

            html_lines.append(formatted)

    html_body = '\n'.join(html_lines)

    html = f"""
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

    return html


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
