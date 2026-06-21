name: Morning Briefing
on: {schedule: [{cron: "30 4 * * *"}], workflow_dispatch: {}}
jobs:
  briefing:
    runs-on: ubuntu-latest
    steps:
      - {uses: actions/checkout@v4}
      - {uses: actions/setup-python@v5, with: {python-version: "3.12"}}
      - {run: pip install -r requirements.txt}
      - {run: python briefing.py, env: {TTS_VOICE: de-DE-ConradNeural}}
