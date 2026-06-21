#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Morning Briefing – baut taeglich ein Nachrichten-Briefing aus RSS-Feeds,
erzeugt eine deutsche MP3 (edge-tts) und schickt Push + MP3 an ntfy.sh.

Laeuft komplett in der Cloud (GitHub Actions) – der Mac muss NICHT laufen.

Konfiguration: siehe Abschnitt CONFIG weiter unten. Die einzige Sache, die
du normalerweise anpasst, ist NTFY_TOPIC (oder per Umgebungsvariable setzen).
"""

import os
import re
import sys
import html
import asyncio
import urllib.parse
import datetime as dt
from email.utils import parsedate_to_datetime

# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------

# ntfy-Topic (kann auch per Umgebungsvariable NTFY_TOPIC ueberschrieben werden)
NTFY_TOPIC = os.environ.get("NTFY_TOPIC") or "ute-briefing-501218"
NTFY_BASE =
