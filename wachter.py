# -*- coding: utf-8 -*-
"""Drave Wachter 1.0 - gedeelde controles voor DraveGuard en DraveMaatje (27-11-2026, idee van pa).

ALLES ALLEEN LEZEN. Deze module verandert nooit iets aan de pc.
  1. privacy(taal)                 -> heeft Windows (na een update) iets weer aangezet?
  2. privacy_veranderd(map, taal)  -> wat is er veranderd sinds de vorige keer kijken?
  3. opstart_nieuw(map, taal)      -> wat start er nieuw mee met Windows sinds de vorige keer?
  4. naar_buiten(taal)             -> welke programma's hebben nu verbinding met internet?
Uitkomsten zijn 'bevindingen' (zelfde vorm als DraveHanden): soort, status, titel, uitleg, advies, extra.
De vorige stand wordt bewaard in de map die de app meegeeft (portable, nooit AppData).
Copyright (C) 2026 Dravenlock (Roger & Claudio). GNU GPL v3.0."""
from __future__ import annotations

import ipaddress
import json
import os
import subprocess
import time

VERSIE = "1.0"
NO_WIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
GOED, LET_OP, SLECHT, ONBEKEND = "goed", "let_op", "slecht", "onbekend"

try:
    import winreg
except ImportError:          # geen Windows (proef in de zandbak)
    winreg = None


def _t(nl, en, taal):
    return nl if taal == "nl" else en


def bevinding(soort, status, titel, uitleg, advies="", extra=None):
    return {"soort": soort, "status": status, "titel": titel, "uitleg": uitleg,
            "advies": advies, "wijzigt": False, "extra": extra or {}}


def _lees(pad):
    """'HKCU\\...\\Sleutel|Waarde' -> waarde of None."""
    if winreg is None:
        return None
    sleutel, naam = pad.split("|")
    hoofd, rest = sleutel.split("\\", 1)
    hk = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}[hoofd]
    for extra in ((winreg.KEY_WOW64_64KEY,) if hoofd == "HKLM" else (0,)):
        try:
            with winreg.OpenKey(hk, rest, 0, winreg.KEY_READ | extra) as k:
                return winreg.QueryValueEx(k, naam)[0]
        except OSError:
            return None
    return None


def _ps(cmd, timeout=40):
    try:
        p = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                           capture_output=True, text=True, timeout=timeout, creationflags=NO_WIN,
                           encoding="utf-8", errors="replace")
        return (p.stdout or "").strip()
    except Exception:
        return ""


def _ps_json(cmd, timeout=40):
    t = _ps("[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + cmd + " | ConvertTo-Json -Compress -Depth 3", timeout)
    try:
        d = json.loads(t) if t else []
    except Exception:
        return []
    return d if isinstance(d, list) else [d]


def _lees_json(pad, standaard):
    try:
        with open(pad, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return standaard


def _schrijf_json(pad, data):
    try:
        os.makedirs(os.path.dirname(pad), exist_ok=True)
        tmp = pad + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, pad)
    except Exception:
        pass


# =====================================================================  1. PRIVACY

INST = "Instellingen > Privacy en beveiliging"
INST_EN = "Settings > Privacy & security"

# (sleutel, titel nl, titel en, uitleg nl, uitleg en, advies nl, advies en, [(pad, goede waarde)], wat als niets ingesteld)
_CONTROLES = [
    ("reclame", "Reclame-ID", "Advertising ID",
     "Met een reclame-ID volgen apps wat je doet, voor reclame op maat.",
     "Apps use an advertising ID to show you targeted ads.",
     INST + " > Algemeen > 'Apps gepersonaliseerde advertenties laten tonen' uit.",
     INST_EN + " > General > 'Let apps show me personalized ads' off.",
     [(r"HKCU\Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo|Enabled", 0)], LET_OP),
    ("tips_diagnose", "Tips op basis van je gegevens", "Tailored experiences",
     "Microsoft gebruikt je diagnosegegevens voor tips en reclame.",
     "Microsoft uses your diagnostic data for tips and ads.",
     INST + " > Diagnose en feedback > 'Afgestemde ervaringen' uit.",
     INST_EN + " > Diagnostics & feedback > 'Tailored experiences' off.",
     [(r"HKCU\Software\Microsoft\Windows\CurrentVersion\Privacy|TailoredExperiencesWithDiagnosticDataEnabled", 0)], LET_OP),
    ("telemetrie", "Gegevens naar Microsoft (telemetrie)", "Data to Microsoft (telemetry)",
     "Hoeveel gegevens Windows over je pc naar Microsoft stuurt.",
     "How much data Windows sends about your pc to Microsoft.",
     INST + " > Diagnose en feedback > 'Optionele diagnosegegevens verzenden' uit.",
     INST_EN + " > Diagnostics & feedback > 'Send optional diagnostic data' off.",
     [(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\DataCollection|AllowTelemetry", (0, 1)),
      (r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\DataCollection|AllowTelemetry", (0, 1))], ONBEKEND),
    ("copilot", "Copilot (AI van Microsoft)", "Copilot (Microsoft AI)",
     "Copilot is de AI van Microsoft in Windows. Wat je erin typt gaat naar Microsoft.",
     "Copilot is Microsoft's AI in Windows. What you type goes to Microsoft.",
     "Verwijder de Copilot-app via Instellingen > Apps, of zet het beleid 'Windows Copilot uitschakelen' aan.",
     "Remove the Copilot app via Settings > Apps, or enable the policy 'Turn off Windows Copilot'.",
     [(r"HKCU\Software\Policies\Microsoft\Windows\WindowsCopilot|TurnOffWindowsCopilot", 1),
      (r"HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsCopilot|TurnOffWindowsCopilot", 1)], None),
    ("recall", "Recall (schermfoto's van alles)", "Recall (snapshots of everything)",
     "Recall maakt steeds schermfoto's van wat je doet. Het bestaat alleen op Copilot+ pc's.",
     "Recall keeps taking snapshots of what you do. It only exists on Copilot+ PCs.",
     INST + " > Recall en momentopnamen > uit.",
     INST_EN + " > Recall & snapshots > off.",
     [(r"HKCU\Software\Policies\Microsoft\Windows\WindowsAI|DisableAIDataAnalysis", 1),
      (r"HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsAI|DisableAIDataAnalysis", 1)], None),
    ("suggesties", "Suggesties en reclame in Start", "Suggestions and ads in Start",
     "Windows laat 'suggesties' zien: dat is vaak reclame voor apps.",
     "Windows shows 'suggestions': often ads for apps.",
     "Instellingen > Persoonlijke instellingen > Start > 'Aanbevelingen voor tips, snelkoppelingen, nieuwe apps' uit.",
     "Settings > Personalization > Start > 'Show recommendations for tips, shortcuts, new apps' off.",
     [(r"HKCU\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager|SubscribedContent-338388Enabled", 0),
      (r"HKCU\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager|SubscribedContent-338389Enabled", 0),
      (r"HKCU\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager|SystemPaneSuggestionsEnabled", 0)], LET_OP),
    ("stil_installeren", "Stiekem apps installeren", "Silently installing apps",
     "Windows mag dan zelf apps (zoals spelletjes) installeren zonder het te vragen.",
     "Windows may then install apps (like games) without asking.",
     "Dit staat niet in Instellingen. DraveGuard of een privacy-programma kan het uitzetten.",
     "Not in Settings. DraveGuard or a privacy tool can switch it off.",
     [(r"HKCU\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager|SilentInstalledAppsEnabled", 0)], LET_OP),
    ("welkom", "Reclame na updates ('Welkom'-scherm)", "Ads after updates ('Welcome' screen)",
     "Na een update laat Windows een welkomstscherm zien met aanbiedingen.",
     "After an update Windows shows a welcome screen with offers.",
     "Instellingen > Systeem > Meldingen > Aanvullende instellingen > alle vinkjes uit.",
     "Settings > System > Notifications > Additional settings > untick all.",
     [(r"HKCU\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager|SubscribedContent-310093Enabled", 0),
      (r"HKCU\Software\Microsoft\Windows\CurrentVersion\UserProfileEngagement|ScoobeSystemSettingEnabled", 0)], LET_OP),
    ("bing", "Internet-zoeken (Bing) in het Startmenu", "Web search (Bing) in Start",
     "Wat je in het Startmenu typt, gaat ook naar Bing op internet.",
     "What you type in Start also goes to Bing on the internet.",
     INST + " > Zoekmachtigingen > 'Zoekmarkeringen' en 'Cloud-inhoud zoeken' uit.",
     INST_EN + " > Search permissions > 'Search highlights' and cloud content search off.",
     [(r"HKCU\Software\Microsoft\Windows\CurrentVersion\Search|BingSearchEnabled", 0),
      (r"HKCU\Software\Policies\Microsoft\Windows\Explorer|DisableSearchBoxSuggestions", 1)], LET_OP),
    ("activiteit", "Activiteitengeschiedenis", "Activity history",
     "Windows houdt bij welke programma's en bestanden je opent.",
     "Windows keeps track of which programs and files you open.",
     INST + " > Activiteitengeschiedenis > uit.",
     INST_EN + " > Activity history > off.",
     [(r"HKLM\SOFTWARE\Policies\Microsoft\Windows\System|PublishUserActivities", 0),
      (r"HKCU\Software\Microsoft\Windows\CurrentVersion\Privacy|PublishUserActivities", 0)], ONBEKEND),
    ("spraak", "Online spraakherkenning", "Online speech recognition",
     "Wat je inspreekt gaat naar Microsoft om het te herkennen.",
     "What you say goes to Microsoft to be recognised.",
     INST + " > Spraak > 'Online spraakherkenning' uit.",
     INST_EN + " > Speech > 'Online speech recognition' off.",
     [(r"HKCU\Software\Microsoft\Speech_OneCore\Settings\OnlineSpeechPrivacy|HasAccepted", 0)], GOED),
    ("typen", "Typen en schrijven leren", "Inking & typing personalization",
     "Windows leert van wat je typt en schrijft, voor een eigen woordenlijst.",
     "Windows learns from what you type and write.",
     INST + " > Persoonlijk woordenboek voor handschrift en typen > uit.",
     INST_EN + " > Inking & typing personalization > off.",
     [(r"HKCU\Software\Microsoft\InputPersonalization|RestrictImplicitTextCollection", 1)], ONBEKEND),
    ("widgets", "Nieuws en widgets op de taakbalk", "News and widgets on the taskbar",
     "De widgetknop haalt nieuws en reclame van internet.",
     "The widgets button fetches news and ads from the internet.",
     "Instellingen > Persoonlijke instellingen > Taakbalk > Widgets uit.",
     "Settings > Personalization > Taskbar > Widgets off.",
     [(r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced|TaskbarDa", 0)], LET_OP),
]


def _past(waarde, goed):
    if waarde is None:
        return None
    if isinstance(goed, tuple):
        return waarde in goed
    return waarde == goed


def _app_aanwezig(woord):
    uit = _ps("(Get-AppxPackage -Name '*%s*' -ErrorAction SilentlyContinue | Select-Object -First 1).Name" % woord, 30)
    return bool(uit)


def privacy(taal="nl"):
    """Per onderdeel: GOED (uit), LET_OP (aan of Windows-standaard), ONBEKEND (niet uit te lezen)."""
    uit = []
    for (sl, tnl, ten, unl, uen, anl, aen, paden, zonder) in _CONTROLES:
        waarden = [(_lees(p), g) for p, g in paden]
        oordelen = [_past(w, g) for w, g in waarden]
        if sl == "copilot":
            app = _app_aanwezig("Copilot")
            if any(o is True for o in oordelen) and not app:
                st, extra_tekst = GOED, _t("Copilot staat uit en de app staat er niet op.", "Copilot is off and the app is not installed.", taal)
            elif app:
                st, extra_tekst = LET_OP, _t("De Copilot-app staat op je pc.", "The Copilot app is on your pc.", taal)
            elif any(o is True for o in oordelen):
                st, extra_tekst = GOED, _t("Copilot is uitgezet.", "Copilot is switched off.", taal)
            else:
                st, extra_tekst = GOED, _t("Geen Copilot-app gevonden.", "No Copilot app found.", taal)
        elif sl == "recall":
            aix = _app_aanwezig("Client.AIX")
            if not aix:
                st, extra_tekst = GOED, _t("Recall staat niet op deze pc.", "Recall is not on this pc.", taal)
            elif any(o is True for o in oordelen):
                st, extra_tekst = GOED, _t("Recall is uitgezet.", "Recall is switched off.", taal)
            else:
                st, extra_tekst = LET_OP, _t("Recall staat op deze pc en is niet uitgezet.", "Recall is on this pc and not switched off.", taal)
        else:
            # Bij een beleid (Policies) is een goede waarde genoeg: het beleid wint van de gewone instelling.
            beleid_goed = any(o is True and "\\Policies\\" in p for o, (p, _) in zip(oordelen, paden))
            if beleid_goed or (any(o is True for o in oordelen) and not any(o is False for o in oordelen)):
                st = GOED
                extra_tekst = _t("Staat uit.", "Is off.", taal)
            elif any(o is False for o in oordelen) and any(o is True for o in oordelen):
                st = LET_OP
                extra_tekst = _t("Staat deels AAN.", "Is partly ON.", taal)
            elif any(o is False for o in oordelen):
                st = LET_OP
                extra_tekst = _t("Staat AAN.", "Is ON.", taal)
            else:
                st = zonder or ONBEKEND
                extra_tekst = _t("Niet vastgezet: Windows gebruikt zijn eigen standaard.", "Not set: Windows uses its own default.", taal)
        uit.append(bevinding("privacy", st, _t(tnl, ten, taal), _t(unl, uen, taal) + " " + extra_tekst,
                             "" if st == GOED else _t(anl, aen, taal),
                             extra={"sleutel": sl, "waarden": [w for w, _ in waarden]}))
    # Kladblok-AI kan ik niet betrouwbaar uitlezen: eerlijk zeggen
    uit.append(bevinding("privacy", ONBEKEND, _t("AI in Kladblok en Paint", "AI in Notepad and Paint", taal),
                         _t("Kladblok en Paint kunnen AI-knoppen (Copilot) hebben. Die stand kan ik niet uitlezen. "
                            "In Paint werkt Copilot alleen als je inlogt met een Microsoft-account: log je niet in, dan gaat er niets naar Microsoft.",
                            "Notepad and Paint may have AI (Copilot) buttons. I can't read that setting. "
                            "In Paint, Copilot only works when you sign in with a Microsoft account: if you don't, nothing goes to Microsoft.", taal),
                         _t("Kijk zelf: Kladblok > tandwiel (Instellingen) > Copilot/AI uit, als die er staat. In Paint: niet inloggen met je Microsoft-account.",
                            "Check yourself: Notepad > gear (Settings) > Copilot/AI off, if present. In Paint: don't sign in with your Microsoft account.", taal),
                         extra={"sleutel": "kladblok"}))
    return uit


def privacy_veranderd(map_, taal="nl"):
    """Vergelijkt met de vorige keer. Geeft (nu, veranderd, eerste_keer). 'veranderd' = van GOED naar niet-GOED."""
    pad = os.path.join(map_, "wachter_privacy.json")
    oud = _lees_json(pad, None)
    nu = privacy(taal)
    stand = {b["extra"].get("sleutel"): b["status"] for b in nu}
    veranderd = []
    if oud:
        for b in nu:
            s = b["extra"].get("sleutel")
            if oud.get("stand", {}).get(s) == GOED and b["status"] != GOED:
                veranderd.append(b)
    _schrijf_json(pad, {"tijd": time.strftime("%Y-%m-%d %H:%M"), "stand": stand})
    return nu, veranderd, oud is None, (oud or {}).get("tijd")


# =====================================================================  2. OPSTART: WAT IS ER NIEUW?

_RUN = [r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
        r"HKCU\Software\Microsoft\Windows\CurrentVersion\RunOnce",
        r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
        r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce",
        r"HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"]


def _run_items():
    uit = {}
    if winreg is None:
        return uit
    for pad in _RUN:
        hoofd, rest = pad.split("\\", 1)
        hk = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}[hoofd]
        try:
            with winreg.OpenKey(hk, rest) as k:
                i = 0
                while True:
                    try:
                        naam, waarde, _ = winreg.EnumValue(k, i)
                    except OSError:
                        break
                    uit["run|%s|%s" % (pad, naam)] = {"soort": "opstart", "naam": naam, "wat": str(waarde)[:300], "waar": pad}
                    i += 1
        except OSError:
            pass
    for map_ in (os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs", "Startup"),
                 os.path.join(os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "Microsoft", "Windows", "Start Menu", "Programs", "StartUp")):
        if os.path.isdir(map_):
            for f in os.listdir(map_):
                if f.lower() != "desktop.ini":
                    uit["map|%s|%s" % (map_, f)] = {"soort": "opstart", "naam": os.path.splitext(f)[0], "wat": os.path.join(map_, f), "waar": map_}
    return uit


def _taken():
    d = _ps_json("Get-ScheduledTask | Where-Object { $_.TaskPath -notlike '\\Microsoft\\*' } | "
                 "Select-Object TaskName, TaskPath, @{n='State';e={[string]$_.State}}, "
                 "@{n='Doet';e={($_.Actions | ForEach-Object { $_.Execute + ' ' + $_.Arguments }) -join ' ; '}}", 60)
    uit = {}
    for t in d:
        if not isinstance(t, dict) or not t.get("TaskName"):
            continue
        sl = "taak|%s%s" % (t.get("TaskPath", ""), t["TaskName"])
        uit[sl] = {"soort": "taak", "naam": t["TaskName"], "wat": (t.get("Doet") or "")[:300],
                   "waar": t.get("TaskPath", ""), "stand": t.get("State", "")}
    return uit


def _diensten():
    d = _ps_json("Get-CimInstance Win32_Service | Where-Object { $_.StartMode -eq 'Auto' -and $_.PathName -and "
                 "$_.PathName -notmatch '\\\\Windows\\\\(System32|SysWOW64|servicing|Microsoft.NET)' } | "
                 "Select-Object Name, DisplayName, PathName", 60)
    uit = {}
    for s in d:
        if isinstance(s, dict) and s.get("Name"):
            uit["dienst|" + s["Name"]] = {"soort": "dienst", "naam": s.get("DisplayName") or s["Name"],
                                          "wat": (s.get("PathName") or "")[:300], "waar": "Windows-diensten"}
    return uit


SOORT_NAAM = {"opstart": ("Start mee", "Startup"), "taak": ("Geplande taak", "Scheduled task"),
              "dienst": ("Dienst", "Service")}


def opstart_nieuw(map_, taal="nl"):
    """Geeft (nieuw, weg, alles, eerste_keer, vorige_tijd). Bewaart de stand voor de volgende keer."""
    pad = os.path.join(map_, "wachter_opstart.json")
    oud = _lees_json(pad, None)
    nu = {}
    nu.update(_run_items())
    nu.update(_taken())
    nu.update(_diensten())
    nieuw, weg = [], []
    if oud:
        oude = oud.get("items", {})
        for k, v in nu.items():
            if k not in oude:
                nieuw.append(v)
        for k, v in oude.items():
            if k not in nu:
                weg.append(v)
    _schrijf_json(pad, {"tijd": time.strftime("%Y-%m-%d %H:%M"), "items": nu})
    return nieuw, weg, list(nu.values()), oud is None, (oud or {}).get("tijd")


def kijk_opstart_nieuw(map_, taal="nl"):
    nieuw, weg, alles, eerste, vorige = opstart_nieuw(map_, taal)
    if eerste:
        return [bevinding("opstart_nieuw", GOED, _t("Opstarten: eerste keer kijken", "Startup: first look", taal),
                          _t("Ik heb opgeschreven wat er nu meestart (%d dingen). Volgende keer zie je wat er nieuw is."
                             % len(alles), "I noted what starts now (%d items). Next time you'll see what's new." % len(alles), taal),
                          extra={"nieuw": [], "weg": [], "aantal": len(alles)})]
    if not nieuw:
        return [bevinding("opstart_nieuw", GOED, _t("Opstarten: niets nieuws", "Startup: nothing new", taal),
                          _t("Sinds de vorige keer (%s) is er niets bijgekomen dat meestart." % vorige,
                             "Since last time (%s) nothing new starts with Windows." % vorige, taal),
                          extra={"nieuw": [], "weg": weg, "aantal": len(alles)})]
    namen = ", ".join(v["naam"] for v in nieuw[:6]) + (" ..." if len(nieuw) > 6 else "")
    return [bevinding("opstart_nieuw", LET_OP, _t("Opstarten: %d nieuw" % len(nieuw), "Startup: %d new" % len(nieuw), taal),
                      _t("Sinds %s start er iets nieuws mee: %s." % (vorige, namen),
                         "Since %s something new starts: %s." % (vorige, namen), taal),
                      _t("Ken je het niet? Kijk het na in DraveGuard of in Taakbeheer > Opstarten.",
                         "Don't recognise it? Check it in DraveGuard or Task Manager > Startup.", taal),
                      extra={"nieuw": nieuw, "weg": weg, "aantal": len(alles)})]


# =====================================================================  3. WIE BELT ER NAAR BUITEN?

_GEWOON = ("\\windows\\", "\\program files\\", "\\program files (x86)\\")


def _publiek(ip):
    try:
        a = ipaddress.ip_address(ip)
        return not (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast or a.is_unspecified)
    except ValueError:
        return False


def naar_buiten(taal="nl"):
    """Programma's met een open verbinding naar internet (nu). Alleen lezen."""
    d = _ps_json("$p=@{}; Get-Process | ForEach-Object { $p[$_.Id] = @($_.ProcessName, $_.Path) }; "
                 "Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue | ForEach-Object { "
                 "[pscustomobject]@{ Id=$_.OwningProcess; Ip=$_.RemoteAddress; Poort=$_.RemotePort; "
                 "Naam=$p[[int]$_.OwningProcess][0]; Pad=$p[[int]$_.OwningProcess][1] } }", 60)
    groep = {}
    for c in d:
        if not isinstance(c, dict) or not _publiek(str(c.get("Ip", ""))):
            continue
        naam = c.get("Naam") or "?"
        g = groep.setdefault(naam, {"naam": naam, "pad": c.get("Pad") or "", "aantal": 0, "adressen": set()})
        g["aantal"] += 1
        g["adressen"].add("%s:%s" % (c.get("Ip"), c.get("Poort")))
    uit = []
    for g in sorted(groep.values(), key=lambda x: -x["aantal"]):
        pad = (g["pad"] or "").lower()
        if not pad:
            st, waar = ONBEKEND, _t("onbekende plek (systeem of beveiligd)", "unknown location (system or protected)", taal)
        elif any(x in pad for x in _GEWOON):
            st, waar = GOED, g["pad"]
        elif any(x in pad for x in ("\\appdata\\local\\temp\\", "\\downloads\\", "\\temp\\")):
            st, waar = SLECHT, g["pad"]
        else:
            st, waar = LET_OP, g["pad"]
        adv = "" if st == GOED else _t("Ken je dit programma? Zo niet: blokkeer het in je firewall of scan het met DraveGuard.",
                                       "Do you know this program? If not: block it in your firewall or scan it with DraveGuard.", taal)
        uit.append(bevinding("buiten", st, g["naam"],
                             _t("%d verbinding(en) naar internet. Staat in: %s" % (g["aantal"], waar),
                                "%d connection(s) to the internet. Located in: %s" % (g["aantal"], waar), taal), adv,
                             extra={"pad": g["pad"], "aantal": g["aantal"], "adressen": sorted(g["adressen"])[:8]}))
    return uit


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    map_ = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
    t0 = time.time()
    print("== PRIVACY ==")
    nu, veranderd, eerste, vorige = privacy_veranderd(map_)
    for b in nu:
        print(" [%s] %s: %s" % (b["status"], b["titel"], b["uitleg"]))
    print(" veranderd sinds vorige keer:", [b["titel"] for b in veranderd], "eerste keer" if eerste else vorige)
    print("== OPSTART ==")
    for b in kijk_opstart_nieuw(map_):
        print(" [%s] %s: %s (totaal %s)" % (b["status"], b["titel"], b["uitleg"], b["extra"].get("aantal")))
    print("== NAAR BUITEN ==")
    for b in naar_buiten():
        print(" [%s] %s: %s" % (b["status"], b["titel"], b["uitleg"]))
    print("klaar in %.1f s" % (time.time() - t0))
