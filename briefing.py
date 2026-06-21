#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Morning Briefing – baut taeglich ein Nachrichten-Briefing aus RSS-Feeds,
erzeugt eine deutsche MP3 (edge-tts) und schickt Push + MP3 + HTML an ntfy.sh.

Laeuft komplett in der Cloud (GitHub Actions) – der Mac muss NICHT laufen.

Audio und Push sind IMMER auf Deutsch: italienische Meldungen werden uebersetzt;
schlaegt eine Uebersetzung fehl, wird die Meldung lieber weggelassen als falsch
auf Italienisch vorgelesen. Die HTML-Seite zeigt die Originalsprache + Quelle.
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

NTFY_TOPIC = os.environ.get("NTFY_TOPIC") or "ute-briefing-501218"
NTFY_BASE = "https://ntfy.sh"

# Vorlesestimme (deutsch, neuronal). Andere: de-DE-KatjaNeural (weiblich)
TTS_VOICE = os.environ.get("TTS_VOICE", "de-DE-ConradNeural")

# Italienische Meldungen fuer Audio/Push nach Deutsch uebersetzen? (1 = ja)
TRANSLATE_IT = os.environ.get("TRANSLATE_IT", "1") == "1"

MAX_AGE_HOURS = 24
PER_SECTION_MIN = 3
PER_SECTION_MAX = 5

# Rubriken in fester Reihenfolge: key, Anzeigename, Emoji (fuer die Handy-Push)
SECTIONS = [
    ("wirtschaft", "1. Wirtschaft", "📊"),
    ("technologie", "2. Technologie", "💻"),
    ("ai", "3. AI", "🤖"),
    ("politik", "4. Politik", "🏛️"),
    ("boerse", "5. Boerse & Maerkte", "📈"),
    ("florenz", "6. Lokal Florenz", "🏖️"),
    ("langenargen", "7. Lokal Langenargen / Bodensee", "🌊"),
]

# Italienische Quellen -> deren Meldungen werden fuer Audio/Push uebersetzt.
ITALIAN_SOURCES = {
    "Il Sole 24 Ore", "Corriere della Sera", "La Repubblica",
    "La Nazione Firenze", "FirenzeToday", "Corriere Fiorentino",
}

FEEDS = [
    # --- National Italien ---
    ("Il Sole 24 Ore", "https://www.ilsole24ore.com/rss/economia.xml", "national"),
    ("Il Sole 24 Ore", "https://www.ilsole24ore.com/rss/tecnologia.xml", "national"),
    ("Il Sole 24 Ore", "https://www.ilsole24ore.com/rss/mondo.xml", "national"),
    ("Il Sole 24 Ore", "https://www.ilsole24ore.com/rss/finanza.xml", "national"),
    ("Corriere della Sera", "https://xml2.corriereobjects.it/rss/homepage.xml", "national"),
    ("Corriere della Sera", "https://xml2.corriereobjects.it/rss/economia.xml", "national"),
    ("Corriere della Sera", "https://xml2.corriereobjects.it/rss/esteri.xml", "national"),
    ("Corriere della Sera", "https://xml2.corriereobjects.it/rss/tecnologia.xml", "national"),
    ("La Repubblica", "https://www.repubblica.it/rss/economia/rss2.0.xml", "national"),
    ("La Repubblica", "https://www.repubblica.it/rss/tecnologia/rss2.0.xml", "national"),
    ("La Repubblica", "https://www.repubblica.it/rss/esteri/rss2.0.xml", "national"),
    # --- National Deutschland ---
    ("Handelsblatt", "https://www.handelsblatt.com/contentexport/feed/schlagzeilen", "national"),
    ("Handelsblatt", "https://www.handelsblatt.com/contentexport/feed/wirtschaft", "national"),
    ("Handelsblatt", "https://www.handelsblatt.com/contentexport/feed/finanzen", "national"),
    ("FAZ", "https://www.faz.net/rss/aktuell/wirtschaft/", "national"),
    ("FAZ", "https://www.faz.net/rss/aktuell/politik/", "national"),
    ("FAZ", "https://www.faz.net/rss/aktuell/", "national"),
    ("Sueddeutsche Zeitung", "https://rss.sueddeutsche.de/rss/Wirtschaft", "national"),
    ("Sueddeutsche Zeitung", "https://rss.sueddeutsche.de/rss/Politik", "national"),
    ("Sueddeutsche Zeitung", "https://rss.sueddeutsche.de/rss/Topthemen", "national"),
    # --- Lokal Florenz ---
    ("La Nazione Firenze", "https://www.lanazione.it/firenze/rss", "florenz"),
    ("FirenzeToday", "https://www.firenzetoday.it/rss", "florenz"),
    ("Corriere Fiorentino", "https://corrierefiorentino.corriere.it/rss/homepage.xml", "florenz"),
    # --- Lokal Langenargen / Bodensee ---
    ("Schwaebische Zeitung", "https://www.schwaebische.de/arc/outboundfeeds/rss/category/bodensee/", "bodensee"),
    ("Suedkurier", "https://www.suedkurier.de/rss/bodenseekreis.rss", "bodensee"),
    ("Newstral Langenargen", "https://newstral.com/de/rss/search?q=Langenargen", "bodensee"),
]

KEYWORDS = [
    ("ai", [
        "ki ", " ki", "k.i.", "kuenstliche intelligenz", "künstliche intelligenz",
        "chatgpt", "openai", "gemini", "anthropic", "claude", "llm", "sprachmodell",
        "machine learning", "ai act", "ai-", "intelligenza artificiale", " ia ",
        "copilot", "grok", "neuronale",
    ]),
    ("boerse", [
        "boerse", "börse", "dax", "aktie", "index", "anleihe", "rendite", "wall street",
        "ftse mib", "dow jones", "nasdaq", "borsa", "mercati", "spread", "bitcoin",
        "krypto", "anleger", "leitzins", "fed", "ezb", "quartalszahlen", "kurs",
    ]),
    ("technologie", [
        "tech", "software", "chip", "halbleiter", "apple", "microsoft", "cyber",
        "daten", "app ", "digital", "smartphone", "internet", "cloud", "robot",
        "tecnologia", "computer", "hacker", "rechenzentrum", "quanten",
    ]),
    ("wirtschaft", [
        "wirtschaft", "konzern", "unternehmen", "konjunktur", "bip", "inflation",
        "export", "industrie", "economia", "azienda", "imprese", "pil", "gewinn",
        "umsatz", "tarif", "zoll", "handel", "lieferkette", "energie", "arbeitsmarkt",
    ]),
    ("politik", [
        "politik", "bundestag", "regierung", "wahl", "minister", " eu ", "krieg",
        "israel", "iran", "ukraine", "russland", "governo", "politica", "parlament",
        "kanzler", "meloni", "merz", "trump", "nato", "gesetz", "koalition", "asyl",
    ]),
]


# ----------------------------------------------------------------------------
# HILFSFUNKTIONEN
# ----------------------------------------------------------------------------

def clean_text(s):
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_title(t):
    t = (t or "").lower()
    t = re.sub(r"[^a-z0-9äöüàèéìòù ]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def categorize(title, summary):
    text = " " + normalize_title(title + " " + (summary or "")) + " "
    for key, words in KEYWORDS:
        for w in words:
            if w in text:
                return key
    return None


def is_duplicate(title, seen_titles):
    n = normalize_title(title)
    if not n:
        return True
    toks = set(n.split())
    for s in seen_titles:
        st = set(s.split())
        if not st or not toks:
            continue
        overlap = len(toks & st) / max(1, min(len(toks), len(st)))
        if n == s or n[:40] == s[:40] or overlap >= 0.7:
            return True
    return False


def entry_datetime(entry):
    for attr in ("published_parsed", "updated_parsed"):
        val = getattr(entry, attr, None) or (entry.get(attr) if hasattr(entry, "get") else None)
        if val:
            try:
                return dt.datetime(*val[:6], tzinfo=dt.timezone.utc)
            except Exception:
                pass
    for attr in ("published", "updated"):
        val = entry.get(attr) if hasattr(entry, "get") else getattr(entry, attr, None)
        if val:
            try:
                d = parsedate_to_datetime(val)
                if d.tzinfo is None:
                    d = d.replace(tzinfo=dt.timezone.utc)
                return d.astimezone(dt.timezone.utc)
            except Exception:
                pass
    return None


# --- Uebersetzung Italienisch -> Deutsch (robust, mit Fallback-Engine) -------

_TRANSLATION_CACHE = {}


def translate_to_de(text):
    """Uebersetzt italienischen Text nach Deutsch. Versucht Google (2x), dann
    MyMemory. Gibt bei komplettem Fehlschlag das Original zurueck."""
    if not text or not TRANSLATE_IT:
        return text
    if text in _TRANSLATION_CACHE:
        return _TRANSLATION_CACHE[text]
    out = text
    try:
        from deep_translator import GoogleTranslator
        for _ in range(2):
            try:
                r = GoogleTranslator(source="auto", target="de").translate(text)
                if r and r.strip():
                    out = r
                    break
            except Exception as ex:
                print("Google-Uebersetzung fehlgeschlagen:", ex)
        else:
            try:
                from deep_translator import MyMemoryTranslator
                r = MyMemoryTranslator(source="it-IT", target="de-DE").translate(text)
                if r and r.strip():
                    out = r
            except Exception as ex:
                print("MyMemory-Uebersetzung fehlgeschlagen:", ex)
    except Exception as ex:
        print("Uebersetzungsmodul nicht verfuegbar, nutze Original:", ex)
    _TRANSLATION_CACHE[text] = out
    return out


def de_text(item):
    """Deutscher Titel fuer Audio/Push. Deutsche Meldungen unveraendert;
    italienische werden uebersetzt. Schlaegt die Uebersetzung fehl, wird die
    Meldung WEGGELASSEN (None) – nie auf Italienisch ausgegeben."""
    if item.get("lang") != "it":
        return item["title"]
    t = translate_to_de(item["title"])
    if t and t.strip() and t.strip().lower() != item["title"].strip().lower():
        return t
    return None


# ----------------------------------------------------------------------------
# FEEDS EINLESEN
# ----------------------------------------------------------------------------

def gather():
    import feedparser  # lazy import

    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(hours=MAX_AGE_HOURS)

    buckets = {key: [] for key, _, _ in SECTIONS}
    seen = {key: [] for key, _, _ in SECTIONS}
    unreachable = []

    for source, url, scope in FEEDS:
        try:
            parsed = feedparser.parse(url, request_headers={"User-Agent": "Mozilla/5.0 MorningBriefing"})
            if getattr(parsed, "bozo", 0) and not parsed.entries:
                unreachable.append((source, url))
                continue
            if not parsed.entries:
                unreachable.append((source, url))
                continue
        except Exception:
            unreachable.append((source, url))
            continue

        for e in parsed.entries:
            title = clean_text(e.get("title", ""))
            if not title:
                continue
            summary = clean_text(e.get("summary", e.get("description", "")))
            link = e.get("link", "")
            when = entry_datetime(e)
            if when is not None and when < cutoff:
                continue

            if scope == "florenz":
                key = "florenz"
            elif scope == "bodensee":
                key = "langenargen"
            else:
                key = categorize(title, summary)
                if key is None:
                    continue

            if is_duplicate(title, seen[key]):
                continue
            seen[key].append(normalize_title(title))
            buckets[key].append({
                "title": title,
                "summary": summary,
                "link": link,
                "source": source,
                "lang": "it" if source in ITALIAN_SOURCES else "de",
                "when": when or now,
            })

    for key in buckets:
        buckets[key].sort(key=lambda x: x["when"], reverse=True)
        buckets[key] = buckets[key][:PER_SECTION_MAX]

    return buckets, unreachable


def build_top3(buckets):
    top = []
    for key in ("politik", "boerse", "wirtschaft", "ai", "technologie"):
        if buckets.get(key):
            top.append(buckets[key][0])
        if len(top) == 3:
            break
    if len(top) < 3:
        for key, _, _ in SECTIONS:
            for item in buckets.get(key, []):
                if item not in top:
                    top.append(item)
                if len(top) == 3:
                    break
            if len(top) == 3:
                break
    return top[:3]


# ----------------------------------------------------------------------------
# AUSGABE: HTML (Originalsprache, mit Claude-Knopf)
# ----------------------------------------------------------------------------

def build_html(buckets, top3, unreachable, datestr):
    def esc(s):
        return html.escape(s or "")

    secs_html = []
    for key, label, _emoji in SECTIONS:
        items = buckets.get(key, [])
        if not items:
            items_html = '<div class="item"><p style="color:#94a3b8">Keine Meldungen der letzten 24 Stunden.</p></div>'
        else:
            rows = []
            for it in items:
                link = ('<a class="link" href="%s">Original</a>' % esc(it["link"])) if it["link"] else ""
                q = urllib.parse.quote(
                    'Ich habe im Morning Briefing diese Meldung gelesen: "%s" (Quelle: %s). '
                    'Bitte gib mir Hintergrund und Kontext dazu und beantworte meine Rueckfragen.'
                    % (it["title"], it["source"])
                )
                ask = '<a class="ask" href="https://claude.ai/new?q=%s" target="_blank" rel="noopener">🤖 Bei Claude nachfragen</a>' % q
                rows.append(
                    '<div class="item"><p>%s</p><div class="meta"><span class="src">%s</span>%s%s</div></div>'
                    % (esc(it["title"]), esc(it["source"]), link, ask)
                )
            items_html = "\n".join(rows)
        num, _, name = label.partition(". ")
        secs_html.append(
            '<section id="r%s"><div class="sec-head"><span class="no">%s</span><h2>%s</h2></div>%s'
            '<a class="totop" href="#top">↑ nach oben</a></section>' % (num, num, esc(name), items_html)
        )

    top_html = "\n".join("<li>%s <span style='font-weight:500;color:#7a5a45'>(%s)</span></li>"
                         % (esc(t["title"]), esc(t["source"])) for t in top3) or "<li>Keine aktuellen Topmeldungen.</li>"

    if unreachable:
        un = ", ".join(sorted(set("%s" % s for s, _ in unreachable)))
        un_note = "Nicht erreichbare Quellen heute: " + esc(un) + "."
    else:
        un_note = "Alle konfigurierten Quellen waren erreichbar."

    nav = "\n".join('<a href="#r%s">%s</a>' % (label.split(".")[0], html.escape(label.split(". ")[1].split(" /")[0]))
                    for _, label, _ in SECTIONS)

    return TEMPLATE.format(datestr=esc(datestr), top=top_html, sections="\n".join(secs_html),
                           nav=nav, unreachable=un_note)


# ----------------------------------------------------------------------------
# AUSGABE: VORLESETEXT + MP3 (durchgehend Deutsch)
# ----------------------------------------------------------------------------

def build_speech(buckets, top3, datestr):
    lines = ["Guten Morgen. Hier ist dein Briefing fuer %s." % datestr, "", "Das Wichtigste zuerst."]
    for t in top3:
        s = de_text(t)
        if s:
            lines.append(s + ".")
    lines.append("")
    for key, label, _emoji in SECTIONS:
        rendered = [s for s in (de_text(it) for it in buckets.get(key, [])) if s]
        if not rendered:
            continue
        lines.append(label.split(". ", 1)[1] + ".")
        for s in rendered:
            lines.append(s + ".")
        lines.append("")
    lines.append("Das war dein Briefing. Einen guten Tag.")
    text = "\n".join(lines)
    text = re.sub(r"https?://\S+", "", text)
    return text


def make_mp3(text, path):
    import edge_tts  # lazy import

    async def _run():
        comm = edge_tts.Communicate(text, TTS_VOICE)
        await comm.save(path)

    asyncio.run(_run())


# ----------------------------------------------------------------------------
# ZUSTELLUNG: ntfy (Push spiegelt die Briefing-Struktur, durchgehend Deutsch)
# ----------------------------------------------------------------------------

def build_push(buckets, top3, datestr):
    parts = ["☕ **Morning Briefing**", "_%s_" % datestr, "", "**⭐ Das Wichtigste zuerst**"]
    n = 0
    for t in top3:
        s = de_text(t)
        if s:
            n += 1
            parts.append("%d. %s" % (n, s))
    for key, label, emoji in SECTIONS:
        rendered = [s for s in (de_text(it) for it in buckets.get(key, [])) if s]
        if not rendered:
            continue
        name = label.split(". ", 1)[1]
        parts.append("")
        parts.append("%s **%s**" % (emoji, name))
        for s in rendered:
            parts.append("• " + s)
    return "\n".join(parts).strip()


def _put_attachment(topic_url, path, filename, title, tags):
    import requests
    with open(path, "rb") as fh:
        r = requests.put(topic_url, data=fh,
                         headers={"Filename": filename, "Title": title, "Tags": tags},
                         timeout=120)
    r.raise_for_status()
    print("Anhang gesendet:", filename, r.status_code)


def send_ntfy(push_text, mp3_path, html_path, datestr_short):
    import requests  # lazy import

    topic_url = "%s/%s" % (NTFY_BASE, NTFY_TOPIC)
    headers = {
        "Title": "Morning Briefing %s" % datestr_short,
        "Tags": "newspaper,coffee",
        "Priority": "default",
        "Markdown": "yes",
    }
    r = requests.post(topic_url, data=push_text.encode("utf-8"), headers=headers, timeout=30)
    r.raise_for_status()
    print("Push gesendet:", r.status_code)

    # Vollstaendige HTML-Seite zum Antippen (zeigt exakt die Drive-Ansicht)
    if html_path and os.path.exists(html_path):
        _put_attachment(topic_url, html_path, "briefing.html",
                        "📄 Briefing oeffnen %s" % datestr_short, "page_facing_up")

    # MP3 zum Anhoeren
    if mp3_path and os.path.exists(mp3_path):
        _put_attachment(topic_url, mp3_path, "briefing_audio.mp3",
                        "🔊 Audio-Briefing %s" % datestr_short, "loud_sound")


# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------

def main():
    now_local = dt.datetime.now()
    datestr = now_local.strftime("%A, %d.%m.%Y").replace("Monday", "Montag")\
        .replace("Tuesday", "Dienstag").replace("Wednesday", "Mittwoch")\
        .replace("Thursday", "Donnerstag").replace("Friday", "Freitag")\
        .replace("Saturday", "Samstag").replace("Sunday", "Sonntag")
    datestr_short = now_local.strftime("%d.%m.")

    print("Sammle Feeds ...")
    buckets, unreachable = gather()
    total = sum(len(v) for v in buckets.values())
    print("Meldungen gesamt:", total, "| nicht erreichbar:", len(unreachable))

    top3 = build_top3(buckets)

    outdir = os.environ.get("OUT_DIR", "briefings")
    os.makedirs(outdir, exist_ok=True)
    html_path = os.path.join(outdir, "briefing.html")
    mp3_path = os.path.join(outdir, "briefing.mp3")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(build_html(buckets, top3, unreachable, datestr))
    print("HTML geschrieben:", html_path)

    try:
        speech = build_speech(buckets, top3, datestr)
        make_mp3(speech, mp3_path)
        print("MP3 geschrieben:", mp3_path)
    except Exception as ex:
        print("MP3-Erzeugung fehlgeschlagen:", ex)
        mp3_path = None

    if os.environ.get("SKIP_NTFY") == "1":
        print("SKIP_NTFY=1 -> keine Zustellung (Testmodus).")
    else:
        try:
            send_ntfy(build_push(buckets, top3, datestr), mp3_path, html_path, datestr_short)
        except Exception as ex:
            print("ntfy-Zustellung fehlgeschlagen:", ex)
            sys.exit(1)

    print("Fertig.")


TEMPLATE = """<!DOCTYPE html>
<html lang="de"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="theme-color" content="#0f1f3d"><title>Morning Briefing</title>
<style>
*{{box-sizing:border-box;-webkit-tap-highlight-color:transparent}}html{{scroll-behavior:smooth}}
body{{margin:0;background:#eef1f6;color:#16223a;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;font-size:19px;line-height:1.5;padding-bottom:48px}}
.wrap{{max-width:720px;margin:0 auto}}
header{{background:linear-gradient(160deg,#0f1f3d,#1b3a6b);color:#fff;padding:calc(26px + env(safe-area-inset-top)) 22px 20px;border-radius:0 0 22px 22px}}
header .kicker{{font-size:14px;letter-spacing:.14em;text-transform:uppercase;opacity:.75;margin:0}}
header h1{{font-size:29px;line-height:1.15;margin:6px 0 4px;font-weight:800}}
header .date{{font-size:16px;opacity:.85;margin:0}}
nav{{position:sticky;top:0;z-index:20;background:rgba(238,241,246,.92);backdrop-filter:saturate(180%) blur(10px);padding:10px 12px;border-bottom:1px solid #e7ebf2;display:flex;gap:8px;overflow-x:auto;scrollbar-width:none}}
nav::-webkit-scrollbar{{display:none}}
nav a{{flex:0 0 auto;text-decoration:none;color:#1b2b46;background:#fff;border:1px solid #e7ebf2;padding:9px 14px;border-radius:999px;font-size:15px;font-weight:600;white-space:nowrap}}
main{{padding:18px 14px 0}}
.top{{background:linear-gradient(165deg,#fff7ed,#fef2e8);border:1px solid #f6d8c2;border-radius:18px;padding:18px 18px 8px;margin:6px 4px 22px;box-shadow:0 6px 22px rgba(194,65,12,.08)}}
.top h2{{margin:0 0 10px;font-size:15px;letter-spacing:.1em;text-transform:uppercase;color:#c2410c}}
.top ol{{margin:0;padding-left:22px}}.top li{{margin:0 0 12px;font-size:19px;line-height:1.45;font-weight:600;color:#3a2415}}
section{{margin:0 4px 26px}}
.sec-head{{display:flex;align-items:center;gap:10px;margin:0 4px 12px}}
.sec-head .no{{flex:0 0 auto;width:30px;height:30px;border-radius:9px;background:#0f1f3d;color:#fff;font-weight:800;font-size:16px;display:flex;align-items:center;justify-content:center}}
.sec-head h2{{margin:0;font-size:21px;font-weight:800;color:#0f1f3d}}
.item{{background:#fff;border:1px solid #e7ebf2;border-radius:16px;padding:15px 16px;margin:0 0 12px;box-shadow:0 2px 8px rgba(15,31,61,.04)}}
.item p{{margin:0 0 10px;font-size:18.5px;line-height:1.46}}
.meta{{display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
.src{{font-size:13.5px;font-weight:700;color:#475569;background:#eef2f9;padding:4px 10px;border-radius:8px}}
.item a.link{{display:inline-flex;align-items:center;gap:6px;text-decoration:none;font-size:14.5px;font-weight:700;color:#1d4ed8}}
.item a.link::after{{content:"↗";font-size:13px}}
.item a.ask{{display:inline-flex;align-items:center;gap:5px;text-decoration:none;font-size:14.5px;font-weight:700;color:#fff;background:#c2410c;padding:5px 11px;border-radius:9px}}
.item a.ask:active{{background:#9a3412}}
footer{{margin:30px 14px 0;padding:16px;background:#fff;border:1px solid #e7ebf2;border-radius:16px;font-size:14px;color:#5b6b82;line-height:1.5}}
.totop{{display:block;text-align:center;margin:18px auto 0;font-size:14px;color:#64748b;text-decoration:none}}
</style></head><body><a id="top"></a><div class="wrap">
<header><p class="kicker">☕ Morning Briefing</p><h1>Das Wichtigste aus DE &amp; IT</h1><p class="date">{datestr} · letzte 24 Stunden</p></header>
<nav>{nav}</nav>
<main>
<div class="top"><h2>Das Wichtigste zuerst</h2><ol>{top}</ol></div>
{sections}
<footer><b>Automatisch erstellt</b> aus RSS-Feeds (Il Sole 24 Ore, Corriere, Repubblica, Handelsblatt, FAZ, SZ, La Nazione, FirenzeToday, Schwäbische, Südkurier u. a.). {unreachable} Italienische Meldungen werden fuer Audio/Push ins Deutsche uebersetzt. Bitte vor geschäftlichen Entscheidungen am Original prüfen.</footer>
</main></div></body></html>"""


if __name__ == "__main__":
    main()
