name: Morning Briefing

on:
  schedule:
    - cron: "30 4 * * *"
  workflow_dispatch: {}

permissions:
  contents: write

jobs:
  briefing:
    runs-on: ubuntu-latest
    steps:
      - name: Code auschecken
        uses: actions/checkout@v4

      - name: Python einrichten
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Abhaengigkeiten installieren
        run: pip install -r requirements.txt

      - name: Briefing bauen, MP3 erzeugen und Push senden
        env:
          TTS_VOICE: de-DE-ConradNeural
          NTFY_TOPIC: ${{ secrets.NTFY_TOPIC }}
        run: python briefing.py

      - name: Briefing-Archiv committen
        run: |
          git config user.name "github-actions"
          git config user.email "actions@github.com"
          git add briefings/*.html || true
          git commit -m "Briefing $(date +%F)" || echo "Nichts zu committen."
          git push || true
