# -*- coding: utf-8 -*-
"""DraveGuard - totaal onderhoud (motor, zonder venster).

Onderdelen:
  1. Adware / ongewenste programma's (PUP): geinstalleerde programma's,
     taakplanner, diensten en opstartitems.
  2. Browser-controle: extensies (Chrome, Edge, Brave, Vivaldi, Opera, Firefox,
     LibreWolf), gekaapte startpagina/zoekmachine, browser-beleid dat iets
     afdwingt, proxy en het hosts-bestand.
  3. Systeemherstel en schijf: herstelpunt, sfc / DISM, schijfgezondheid,
     Windows.old en de onderdelen-opslag (WinSxS).
  4. Programma-updates via winget.

Regel: ALLES hier kijkt eerst alleen. Iets veranderen gebeurt pas in de
`doe_...`-functies, en die roept het venster alleen aan na jouw OK.
Een registry-cleaner zit er bewust NIET in (levert niets op, kan veel stuk maken).
Dravenlock (Roger & Claudio).
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field

import engine          # CACHE-pad (portable)

WINDOWS = os.name == "nt"
NO_WIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)
try:
    import winreg
    HAVE_REG = True
except Exception:
    HAVE_REG = False

RAPPORT_MAP = os.path.join(engine.CACHE, "rapporten")
BACKUP_MAP = os.path.join(engine.CACHE, "onderhoud_backup")

# ernst
INFO, LET_OP, VERDACHT = 0, 1, 2


@dataclass
class Vondst:
    soort: str                 # "programma", "taak", "dienst", "opstart", "extensie",
                               # "browser", "beleid", "proxy", "hosts", "schijf", "update"
    naam: str
    detail: str = ""
    ernst: int = LET_OP
    reden: str = ""
    actie: str = ""            # wat "Oplossen" doet (leesbaar)
    data: dict = field(default_factory=dict)


# ---------------------------------------------------------------- hulp

def _run(args, timeout=60):
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout,
                           creationflags=NO_WIN)
        raw = p.stdout or b""
        for enc in ("utf-8", "cp1252", "utf-16"):
            try:
                return raw.decode(enc), p.returncode
            except Exception:
                continue
        return raw.decode("utf-8", "replace"), p.returncode
    except Exception as e:
        return str(e), -1


def ps(cmd, timeout=60):
    """PowerShell, uitvoer als tekst (UTF-8)."""
    pre = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; $ProgressPreference='SilentlyContinue'; "
    out, _ = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", pre + cmd],
                  timeout=timeout)
    return out.strip()


def ps_json(cmd, timeout=60):
    out = ps(cmd + " | ConvertTo-Json -Depth 4 -Compress", timeout=timeout)
    if not out:
        return []
    try:
        d = json.loads(out)
    except Exception:
        return []
    return d if isinstance(d, list) else [d]


def is_admin():
    if not WINDOWS:
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def human(n):
    n = float(n or 0)
    for e in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or e == "TB":
            return ("%.0f %s" % (n, e)) if e == "B" else ("%.1f %s" % (n, e))
        n /= 1024


def _nep_pad(p):
    """Gebruikersmap korter tonen: C:\\Users\\naam -> %USERPROFILE%."""
    home = os.path.expanduser("~")
    return p.replace(home, "%USERPROFILE%") if p else p


# ---------------------------------------------------------------- 1. adware / PUP

# Bekende families van adware en 'mogelijk ongewenste programma's' (PUP).
# Alleen een signaal: jij beslist. Kleine letters, deel van naam of uitgever.
PUP_NAMEN = [
    "web companion", "webcompanion", "lavasoft", "adaware web", "conduit",
    "ask toolbar", "ask.com", "babylon", "mywebsearch", "mindspark", "opencandy",
    "wajam", "crossrider", "sweetim", "search protect", "searchprotect",
    "segurazo", "shield antivirus", "bytefence", "reimage", "restoro",
    "driver support", "driversupport", "driver updater", "driverupdate",
    "onesafe", "pc cleaner", "pccleaner", "mypc backup", "pc accelerate",
    "advanced pc care", "pc speed maximizer", "speedupmypc", "regclean",
    "registry reviver", "pc optimizer pro", "systweak", "iobit toolbar",
    "hola vpn", "hola better internet", "superfish", "browsefox", "multiplug",
    "yontoo", "linkury", "smartbar", "delta toolbar", "snap.do", "qone8",
    "trovi", "safe finder", "safefinder", "searchmine", "mystartsearch",
    "istartsurf", "nationzoom", "sweet-page", "coupon", "shopper pro",
    "price gong", "superweb", "awesomehp", "wincleaner", "total av",
    "pc app store", "appsforpc", "wave browser", "wavebrowser", "shift browser",
    "onelaunch", "one launch", "clara browser", "kiwi software",
]

# Programma's die op een PUP-naam lijken maar gewoon goed zijn.
PUP_UITZONDERING = ["adaware antivirus", "malwarebytes", "ccleaner"]

VERDACHTE_MAPPEN = ("\\appdata\\local\\temp\\", "\\windows\\temp\\", "\\appdata\\roaming\\",
                    "\\appdata\\local\\", "\\programdata\\", "\\users\\public\\")
VERDACHTE_CMD = re.compile(
    r"(-enc\b|-encodedcommand|frombase64string|downloadstring|downloadfile|"
    r"invoke-webrequest|iwr\s|\biex\b|invoke-expression|mshta\s+https?:|"
    r"regsvr32\s+/s\s+/n\s+/u\s+/i:https?:|bitsadmin\s+/transfer|certutil\s+-urlcache)", re.I)
# (een verborgen venster alleen is normaal: veel eigen taken doen dat)


def _pup_reden(*teksten):
    t = " ".join(x for x in teksten if x).lower()
    if any(u in t for u in PUP_UITZONDERING):
        return ""
    for n in PUP_NAMEN:
        if n in t:
            return n
    return ""


def geinstalleerde_programmas():
    """Uit het register (alleen lezen): naam, uitgever, versie, uninstall-commando."""
    res = []
    if not HAVE_REG:
        return res
    plekken = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    gezien = set()
    for hive, pad in plekken:
        try:
            k = winreg.OpenKey(hive, pad)
        except OSError:
            continue
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(k, i)
            except OSError:
                break
            i += 1
            try:
                s = winreg.OpenKey(k, sub)
            except OSError:
                continue

            def val(n):
                try:
                    return str(winreg.QueryValueEx(s, n)[0])
                except OSError:
                    return ""
            naam = val("DisplayName")
            if not naam or val("SystemComponent") == "1":
                continue
            sleutel = (naam.lower(), val("DisplayVersion"))
            if sleutel in gezien:
                continue
            gezien.add(sleutel)
            res.append({"naam": naam, "uitgever": val("Publisher"),
                        "versie": val("DisplayVersion"),
                        "uninstall": val("QuietUninstallString") or val("UninstallString"),
                        "locatie": val("InstallLocation")})
    return res


def scan_adware(progress=None):
    """Zoekt adware/PUP. Geeft lijst Vondst."""
    v = []
    say = progress or (lambda s: None)

    say("Geïnstalleerde programma's" if True else "")
    for p in geinstalleerde_programmas():
        r = _pup_reden(p["naam"], p["uitgever"])
        if r:
            v.append(Vondst("programma", p["naam"], "%s  %s" % (p["uitgever"], p["versie"]),
                            LET_OP, "Lijkt op een bekend ongewenst programma (%s)." % r,
                            "De-installeren (opent het eigen verwijderprogramma)", p))

    say("Taakplanner")
    if WINDOWS:
        taken = ps_json(
            "Get-ScheduledTask | ? { $_.TaskPath -notlike '\\Microsoft\\*' } | % { "
            "[pscustomobject]@{Naam=$_.TaskName; Pad=$_.TaskPath; Staat=\"$($_.State)\"; "
            "Exe=(($_.Actions | % { $_.Execute }) -join ';'); "
            "Arg=(($_.Actions | % { $_.Arguments }) -join ';')} }", timeout=90)
        for t in taken:
            exe, arg = t.get("Exe") or "", t.get("Arg") or ""
            alles = (exe + " " + arg)
            low = alles.lower()
            reden = ""
            ernst = LET_OP
            if VERDACHTE_CMD.search(alles):
                reden, ernst = "Start een verborgen of gecodeerd commando, of downloadt iets.", VERDACHT
            elif any(m in low for m in ("\\appdata\\local\\temp\\", "\\windows\\temp\\")):
                reden, ernst = "Start een programma uit een tijdelijke map.", VERDACHT
            else:
                r = _pup_reden(t.get("Naam"), exe)
                if r:
                    reden = "Lijkt op een bekend ongewenst programma (%s)." % r
            if reden and t.get("Staat", "").lower() != "disabled":
                v.append(Vondst("taak", t.get("Naam", "?"), _nep_pad(alles.strip())[:220], ernst,
                                reden, "Taak uitzetten (kan terug)", t))

    say("Diensten")
    if WINDOWS:
        dien = ps_json("Get-CimInstance Win32_Service | Select Name,DisplayName,State,StartMode,PathName",
                       timeout=60)
        for d in dien:
            pad = (d.get("PathName") or "")
            low = pad.lower()
            reden = ""
            if any(m in low for m in ("\\appdata\\", "\\temp\\", "\\users\\public\\")):
                reden = "Dienst draait vanuit een gebruikers- of tijdelijke map (ongebruikelijk)."
            else:
                r = _pup_reden(d.get("Name"), d.get("DisplayName"), pad)
                if r:
                    reden = "Lijkt op een bekend ongewenst programma (%s)." % r
            if reden:
                v.append(Vondst("dienst", d.get("DisplayName") or d.get("Name", "?"),
                                _nep_pad(pad)[:220], LET_OP, reden,
                                "Dienst stoppen en op 'handmatig' zetten (kan terug)", d))

    say("Opstartitems")
    try:
        import startup
        for it in startup.list_items():
            r = _pup_reden(it.naam, it.waarde)
            low = (it.waarde or "").lower()
            reden = ""
            ernst = LET_OP
            if VERDACHTE_CMD.search(it.waarde or ""):
                reden, ernst = "Start een verborgen of gecodeerd commando.", VERDACHT
            elif "\\temp\\" in low:
                reden, ernst = "Start iets uit een tijdelijke map.", VERDACHT
            elif r:
                reden = "Lijkt op een bekend ongewenst programma (%s)." % r
            if reden and not it.uit:
                v.append(Vondst("opstart", it.naam, _nep_pad(it.waarde)[:220], ernst, reden,
                                "Uitzetten bij opstarten (kan terug)", {"item": it}))
    except Exception:
        pass
    return v


def doe_adware(vd: Vondst):
    """Lost een adware-vondst op. Geeft (ok, bericht)."""
    try:
        if vd.soort == "programma":
            cmd = vd.data.get("uninstall") or ""
            if not cmd:
                return False, "Geen verwijderprogramma gevonden."
            subprocess.Popen(cmd, shell=True)
            return True, "Verwijderprogramma gestart - volg de stappen op het scherm."
        if vd.soort == "taak":
            naam = (vd.data.get("Pad") or "\\") + vd.data.get("Naam", "")
            out, rc = _run(["schtasks", "/Change", "/TN", naam, "/DISABLE"], timeout=30)
            return rc == 0, ("Taak uitgezet." if rc == 0 else out.strip() or "Mislukt (beheerder nodig?)")
        if vd.soort == "dienst":
            n = vd.data.get("Name", "")
            _run(["sc", "stop", n], timeout=30)
            out, rc = _run(["sc", "config", n, "start=", "demand"], timeout=30)
            return rc == 0, ("Dienst gestopt en op handmatig gezet." if rc == 0
                             else out.strip() or "Mislukt (beheerder nodig?)")
        if vd.soort == "opstart":
            import startup
            ok, msg = startup.disable(vd.data["item"])
            return ok, msg
    except Exception as e:
        return False, str(e)
    return False, "Onbekend soort."


# ---------------------------------------------------------------- 2. browser

CHROMIUM = [
    ("Chrome", r"Google\Chrome\User Data", "chrome.exe", "chrome://extensions"),
    ("Edge", r"Microsoft\Edge\User Data", "msedge.exe", "edge://extensions"),
    ("Brave", r"BraveSoftware\Brave-Browser\User Data", "brave.exe", "brave://extensions"),
    ("Vivaldi", r"Vivaldi\User Data", "vivaldi.exe", "vivaldi://extensions"),
]
GECKO = [
    ("Firefox", r"Mozilla\Firefox\Profiles", "firefox.exe"),
    ("LibreWolf", r"librewolf\Profiles", "librewolf.exe"),
    ("Waterfox", r"Waterfox\Profiles", "waterfox.exe"),
]
WINKELS = ("clients2.google.com/service/update2/crx", "edge.microsoft.com/extensionwebstorebase",
           "chromewebstore", "extension-updates.opera.com")
BREED = ("<all_urls>", "*://*/*", "http://*/*", "https://*/*")
GOEDE_ZOEK = ("google.", "bing.com", "duckduckgo.com", "ecosia.org", "startpage.com",
              "qwant.com", "search.brave.com", "yahoo.com", "search.yahoo", "ixquick",
              "mojeek", "swisscows", "kagi.com", "you.com", "perplexity.ai", "gibiru",
              "searx", "metager")
SLECHTE_ZOEK = ("trovi", "mystartsearch", "istartsurf", "snap.do", "delta-search", "qone8",
                "searchmine", "safefinder", "safe-finder", "yahoo.com/yhs/", "search.yahoo.com/yhs",
                "searchlee", "bing.com/?pc=", "nationzoom", "sweet-page", "awesomehp",
                "mysearch", "search.conduit", "ask.com", "babylon.com", "wajam", "hao123")
SLECHTE_EXT = PUP_NAMEN + ["search manager", "searchmanager", "new tab search", "pdf converter pro",
                           "weather tab", "video downloader professional", "easy pdf combine",
                           "fastsearch", "quick searcher", "superfish"]


def _lees_json(p):
    try:
        with open(p, encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}


def _ext_naam(map_, m):
    naam = m.get("name", "") or ""
    if naam.startswith("__MSG_") and naam.endswith("__"):
        sleutel = naam[6:-2]
        for taal in ("nl", m.get("default_locale") or "en", "en", "en_US"):
            msg = _lees_json(os.path.join(map_, "_locales", taal, "messages.json"))
            for k, v in msg.items():
                if k.lower() == sleutel.lower():
                    return v.get("message", naam)
    return naam


def _zoek_oordeel(url):
    low = (url or "").lower()
    if not low:
        return None
    if any(s in low for s in SLECHTE_ZOEK):
        return VERDACHT
    if any(s in low for s in GOEDE_ZOEK):
        return None
    return LET_OP


def scan_browsers(progress=None):
    """Extensies, startpagina, zoekmachine. Geeft (vondsten, alle_extensies)."""
    say = progress or (lambda s: None)
    vond, alle = [], []
    local = os.environ.get("LOCALAPPDATA", "")
    roam = os.environ.get("APPDATA", "")

    for br, rel, exe, pagina in CHROMIUM:
        ud = os.path.join(local, rel)
        if not os.path.isdir(ud):
            continue
        say(br)
        for prof in sorted(os.listdir(ud)):
            pmap = os.path.join(ud, prof)
            if not os.path.isfile(os.path.join(pmap, "Preferences")) or prof == "System Profile":
                continue
            pref = _lees_json(os.path.join(pmap, "Preferences"))
            sec = _lees_json(os.path.join(pmap, "Secure Preferences"))
            inst = {}
            for d in (pref, sec):
                inst.update(((d.get("extensions") or {}).get("settings") or {}))
            pnaam = (pref.get("profile") or {}).get("name") or prof
            emap = os.path.join(pmap, "Extensions")
            for eid in (os.listdir(emap) if os.path.isdir(emap) else []):
                vers = sorted(glob.glob(os.path.join(emap, eid, "*", "manifest.json")))
                if not vers:
                    continue
                vmap = os.path.dirname(vers[-1])
                m = _lees_json(vers[-1])
                s = inst.get(eid, {})
                loc = s.get("location")
                if loc in (5, 10):          # onderdelen van de browser zelf
                    continue
                naam = _ext_naam(vmap, m)
                upd = (m.get("update_url") or "").lower()
                winkel = bool(s.get("from_webstore")) or any(w in upd for w in WINKELS)
                aan = not s.get("disable_reasons") and s.get("state", 1) != 0
                perms = [str(x) for x in (m.get("permissions") or []) + (m.get("host_permissions") or [])
                         + [h for cs in (m.get("content_scripts") or []) for h in (cs.get("matches") or [])]]
                breed = any(b in perms for b in BREED)
                info = {"browser": br, "profiel": pnaam, "id": eid, "naam": naam, "aan": aan,
                        "winkel": winkel, "breed": breed, "exe": exe, "pagina": pagina,
                        "map": os.path.join(emap, eid), "loc": loc}
                alle.append(info)
                reden, ernst = "", LET_OP
                r = _pup_reden(naam) or next((x for x in SLECHTE_EXT if x in naam.lower()), "")
                if r:
                    reden, ernst = "Bekende ongewenste extensie (%s)." % r, VERDACHT
                elif loc in (2, 3, 6, 8) and not winkel and not s.get("was_installed_by_default"):
                    reden = "Door een ander programma geïnstalleerd, niet uit de winkel (klassieke adware-truc)."
                    ernst = VERDACHT if breed else LET_OP
                elif not winkel and loc != 4 and breed:
                    reden = "Niet uit de officiële winkel, en mag alle websites lezen."
                if reden and aan:
                    vond.append(Vondst("extensie", "%s  (%s, %s)" % (naam, br, pnaam), eid, ernst, reden,
                                       "Extensiepagina van %s openen om hem te verwijderen" % br, info))
            # startpagina en zoekmachine
            dsp = ((pref.get("default_search_provider_data") or {}).get("template_url_data") or {})
            zurl = dsp.get("url") or ""
            o = _zoek_oordeel(zurl)
            if o is not None:
                vond.append(Vondst("browser", "Zoekmachine in %s (%s): %s" % (br, pnaam, dsp.get("short_name") or "?"),
                                   zurl[:160], o, "Onbekende of gekaapte zoekmachine.",
                                   "Instellingen van %s openen" % br,
                                   {"exe": exe, "pagina": pagina.replace("extensions", "settings/search")}))
            urls = list((pref.get("session") or {}).get("startup_urls") or [])
            if pref.get("homepage"):
                urls.append(pref.get("homepage"))
            for u in urls:
                o2 = _zoek_oordeel(u)
                if o2 == VERDACHT:
                    vond.append(Vondst("browser", "Startpagina in %s (%s)" % (br, pnaam), u[:160], VERDACHT,
                                       "Startpagina wijst naar een bekende kaper.",
                                       "Instellingen van %s openen" % br,
                                       {"exe": exe, "pagina": pagina.replace("extensions", "settings/onStartup")}))

    for br, rel, exe in GECKO:
        pm = os.path.join(roam, rel)
        if not os.path.isdir(pm):
            continue
        say(br)
        for prof in sorted(os.listdir(pm)):
            pmap = os.path.join(pm, prof)
            d = _lees_json(os.path.join(pmap, "extensions.json"))
            for a in d.get("addons", []):
                if a.get("type") != "extension" or a.get("location") not in ("app-profile", "app-system-share",
                                                                             "winreg-app-user", "winreg-app-global"):
                    continue
                naam = (a.get("defaultLocale") or {}).get("name") or a.get("id", "?")
                info = {"browser": br, "profiel": prof.split(".", 1)[-1], "id": a.get("id"), "naam": naam,
                        "aan": bool(a.get("active")), "winkel": a.get("signedState") in (2, 3, 4),
                        "breed": "<all_urls>" in json.dumps(a.get("userPermissions") or {}),
                        "exe": exe, "pagina": "about:addons", "map": a.get("path") or ""}
                alle.append(info)
                reden, ernst = "", LET_OP
                r = _pup_reden(naam) or next((x for x in SLECHTE_EXT if x in naam.lower()), "")
                if r:
                    reden, ernst = "Bekende ongewenste extensie (%s)." % r, VERDACHT
                elif str(a.get("location", "")).startswith("winreg"):
                    reden = "Via het register door een ander programma geïnstalleerd."
                elif a.get("signedState") in (-1, -2, 0) and a.get("signedState") is not None:
                    reden = "Niet ondertekend door Mozilla."
                if reden and info["aan"]:
                    vond.append(Vondst("extensie", "%s  (%s)" % (naam, br), a.get("id", ""), ernst, reden,
                                       "Add-ons-pagina van %s openen" % br, info))
            prefs = os.path.join(pmap, "prefs.js")
            try:
                tekst = open(prefs, encoding="utf-8", errors="replace").read()
                mt = re.search(r'user_pref\("browser\.startup\.homepage",\s*"([^"]*)"', tekst)
                if mt and _zoek_oordeel(mt.group(1)) == VERDACHT:
                    vond.append(Vondst("browser", "Startpagina in %s" % br, mt.group(1)[:160], VERDACHT,
                                       "Startpagina wijst naar een bekende kaper.",
                                       "Instellingen van %s openen" % br, {"exe": exe, "pagina": "about:preferences#home"}))
            except Exception:
                pass

    say("Browser-beleid, proxy en hosts")
    vond += scan_beleid()
    vond += scan_proxy()
    vond += scan_hosts()
    return vond, alle


BELEID = [
    ("Chrome", r"SOFTWARE\Policies\Google\Chrome"),
    ("Edge", r"SOFTWARE\Policies\Microsoft\Edge"),
    ("Brave", r"SOFTWARE\Policies\BraveSoftware\Brave"),
    ("Firefox", r"SOFTWARE\Policies\Mozilla\Firefox"),
]
GEVAAR_BELEID = {
    "extensioninstallforcelist": "Dwingt extensies af die je niet kunt verwijderen.",
    "homepagelocation": "Dwingt een startpagina af.",
    "restoreonstartupurls": "Dwingt pagina's bij het opstarten af.",
    "defaultsearchprovidersearchurl": "Dwingt een zoekmachine af.",
    "defaultsearchproviderenabled": "Regelt de zoekmachine via beleid.",
    "newtabpagelocation": "Dwingt een nieuwe-tabbladpagina af.",
    "proxyserver": "Dwingt een proxy af (verkeer loopt via een andere computer).",
    "proxypacurl": "Dwingt een proxy-script af.",
    "extensions": "Firefox-beleid installeert extensies.",
    "homepage": "Firefox-beleid dwingt een startpagina af.",
    "searchengines": "Firefox-beleid regelt de zoekmachine.",
}


def scan_beleid():
    v = []
    if not HAVE_REG:
        return v
    for br, pad in BELEID:
        for hive, hnaam in ((winreg.HKEY_LOCAL_MACHINE, "HKLM"), (winreg.HKEY_CURRENT_USER, "HKCU")):
            try:
                k = winreg.OpenKey(hive, pad)
            except OSError:
                continue
            namen = []
            i = 0
            while True:                     # waarden
                try:
                    n, w, _ = winreg.EnumValue(k, i)
                except OSError:
                    break
                i += 1
                namen.append((n, str(w), False))
            i = 0
            while True:                     # subsleutels (zoals ExtensionInstallForcelist)
                try:
                    n = winreg.EnumKey(k, i)
                except OSError:
                    break
                i += 1
                inhoud = []
                try:
                    s = winreg.OpenKey(k, n)
                    j = 0
                    while True:
                        try:
                            _, w, _ = winreg.EnumValue(s, j)
                        except OSError:
                            break
                        j += 1
                        inhoud.append(str(w))
                except OSError:
                    pass
                namen.append((n, "; ".join(inhoud), True))
            for n, w, sub in namen:
                reden = GEVAAR_BELEID.get(n.lower())
                if not reden:
                    continue
                ernst = VERDACHT if n.lower() in ("extensioninstallforcelist", "proxyserver", "proxypacurl") else LET_OP
                v.append(Vondst("beleid", "%s-beleid: %s" % (br, n), w[:200], ernst, reden,
                                "Beleidsregel verwijderen (met back-up, beheerder nodig)",
                                {"hive": hnaam, "pad": pad, "naam": n, "sub": sub}))
    return v


def scan_proxy():
    v = []
    if not HAVE_REG:
        return v
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
    except OSError:
        return v

    def val(n):
        try:
            return winreg.QueryValueEx(k, n)[0]
        except OSError:
            return None
    if val("ProxyEnable") == 1 and val("ProxyServer"):
        v.append(Vondst("proxy", "Proxy staat aan", str(val("ProxyServer")), LET_OP,
                        "Je internetverkeer loopt via een andere computer. Klopt dat niet, dan is het verdacht.",
                        "Proxy uitzetten (kan terug)", {"soort": "proxy"}))
    if val("AutoConfigURL"):
        v.append(Vondst("proxy", "Proxy-script ingesteld", str(val("AutoConfigURL")), LET_OP,
                        "Een script bepaalt waar je verkeer heen gaat. Klopt dat niet, dan is het verdacht.",
                        "Proxy-script verwijderen (met back-up)", {"soort": "pac"}))
    return v


HOSTS = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "drivers", "etc", "hosts")
BELANGRIJK = ("google.", "bing.", "microsoft.", "windowsupdate", "live.com", "office", "facebook.",
              "apple.", "paypal.", "ing.nl", "rabobank", "abnamro", "sns", "asnbank", "bunq",
              "digid", "belastingdienst", "mijnoverheid", "github.", "amazon.", "bol.com",
              "avast", "avg.", "malwarebytes", "kaspersky", "eset", "norton", "bitdefender",
              "virustotal")


def scan_hosts():
    v = []
    try:
        regels = open(HOSTS, encoding="utf-8", errors="replace").read().splitlines()
    except Exception:
        return v
    for nr, r in enumerate(regels, 1):
        r2 = r.split("#", 1)[0].strip()
        if not r2:
            continue
        delen = r2.split()
        if len(delen) < 2:
            continue
        ip, namen = delen[0], [x.lower() for x in delen[1:]]
        blok = ip in ("0.0.0.0", "127.0.0.1", "::1", "::")
        lokaal = bool(re.match(r"^(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.|100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.|fe80:|fd)", ip))
        for n in namen:
            if n in ("localhost", "localhost.localdomain"):
                continue
            if any(b in n for b in BELANGRIJK):
                if blok:
                    v.append(Vondst("hosts", "Hosts blokkeert %s" % n, "regel %d: %s" % (nr, r.strip()), LET_OP,
                                    "Een belangrijke site of beveiligingssite wordt geblokkeerd.",
                                    "Regel uit het hosts-bestand halen (met back-up)", {"regel": nr, "tekst": r}))
                elif not lokaal:
                    v.append(Vondst("hosts", "Hosts stuurt %s om" % n, "regel %d: %s" % (nr, r.strip()), VERDACHT,
                                    "Een belangrijke site wordt naar een ander adres gestuurd (phishing-truc).",
                                    "Regel uit het hosts-bestand halen (met back-up)", {"regel": nr, "tekst": r}))
    return v


def open_browser_pagina(info):
    exe, pagina = info.get("exe"), info.get("pagina")
    try:
        subprocess.Popen(["cmd", "/c", "start", "", exe, pagina], creationflags=NO_WIN)
        return True, "Browser geopend op %s." % pagina
    except Exception as e:
        return False, str(e)


def _reg_backup(volledig, naam):
    os.makedirs(BACKUP_MAP, exist_ok=True)
    doel = os.path.join(BACKUP_MAP, "%s_%s.reg" % (naam, time.strftime("%Y-%m-%d_%H%M%S")))
    _run(["reg", "export", volledig, doel, "/y"], timeout=30)
    return doel


def doe_browser(vd: Vondst):
    try:
        if vd.soort in ("extensie", "browser"):
            return open_browser_pagina(vd.data)
        if vd.soort == "beleid":
            d = vd.data
            volledig = "%s\\%s" % (d["hive"], d["pad"])
            b = _reg_backup(volledig, "beleid")
            if d["sub"]:
                out, rc = _run(["reg", "delete", volledig + "\\" + d["naam"], "/f"], timeout=30)
            else:
                out, rc = _run(["reg", "delete", volledig, "/v", d["naam"], "/f"], timeout=30)
            return rc == 0, ("Verwijderd. Back-up: %s" % b if rc == 0 else
                             (out.strip() or "Mislukt") + " (start DraveGuard als beheerder)")
        if vd.soort == "proxy":
            volledig = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
            b = _reg_backup(volledig, "proxy")
            if vd.data.get("soort") == "proxy":
                out, rc = _run(["reg", "add", volledig, "/v", "ProxyEnable", "/t", "REG_DWORD", "/d", "0", "/f"])
            else:
                out, rc = _run(["reg", "delete", volledig, "/v", "AutoConfigURL", "/f"])
            return rc == 0, ("Gedaan. Back-up: %s" % b if rc == 0 else out.strip() or "Mislukt")
        if vd.soort == "hosts":
            os.makedirs(BACKUP_MAP, exist_ok=True)
            b = os.path.join(BACKUP_MAP, "hosts_%s.bak" % time.strftime("%Y-%m-%d_%H%M%S"))
            shutil.copy2(HOSTS, b)
            regels = open(HOSTS, encoding="utf-8", errors="replace").read().splitlines(True)
            nr = vd.data["regel"]
            if 1 <= nr <= len(regels) and regels[nr - 1].strip() == vd.data["tekst"].strip():
                regels[nr - 1] = "# (uitgezet door DraveGuard) " + regels[nr - 1]
                with open(HOSTS, "w", encoding="utf-8", newline="") as f:
                    f.writelines(regels)
                _run(["ipconfig", "/flushdns"], timeout=20)
                return True, "Regel uitgezet. Back-up: %s" % b
            return False, "Het hosts-bestand is intussen veranderd; scan opnieuw."
    except PermissionError:
        return False, "Geen toestemming: start DraveGuard als beheerder."
    except Exception as e:
        return False, str(e)
    return False, "Onbekend soort."


# ---------------------------------------------------------------- 3. herstel en schijf

def herstelpunt_maken(beschrijving="DraveGuard - voor onderhoud"):
    """Maakt een Windows-herstelpunt. Geeft (ok, bericht)."""
    if not WINDOWS:
        return False, "Alleen op Windows."
    if not is_admin():
        return False, "Voor een herstelpunt moet DraveGuard als beheerder draaien."
    voor = ps("(Get-ComputerRestorePoint | Measure-Object).Count", timeout=60)
    out = ps("try { Enable-ComputerRestore -Drive \"$env:SystemDrive\\\" -ErrorAction SilentlyContinue; "
             "Checkpoint-Computer -Description '%s' -RestorePointType MODIFY_SETTINGS -ErrorAction Stop; 'OK' } "
             "catch { 'FOUT: ' + $_.Exception.Message }" % beschrijving.replace("'", ""), timeout=300)
    na = ps("(Get-ComputerRestorePoint | Measure-Object).Count", timeout=60)
    if out.endswith("OK") and na != voor:
        return True, "Herstelpunt gemaakt."
    if out.endswith("OK"):
        return True, "Windows maakt maar één herstelpunt per 24 uur; het recentste herstelpunt blijft gelden."
    return False, out.replace("FOUT: ", "") or "Herstelpunt maken mislukt."


def herstelpunten():
    return ps_json("Get-ComputerRestorePoint | Select Description,@{n='Datum';e={$_.ConvertToDateTime($_.CreationTime).ToString('dd-MM-yyyy HH:mm')}}",
                   timeout=60) if WINDOWS else []


def schijven():
    """Gezondheid per fysieke schijf (+ slijtage/temperatuur als beheerder)."""
    if not WINDOWS:
        return []
    d = ps_json("Get-PhysicalDisk | % { $r = $_ | Get-StorageReliabilityCounter -ErrorAction SilentlyContinue; "
                "[pscustomobject]@{Naam=$_.FriendlyName; Soort=\"$($_.MediaType)\"; Gezond=\"$($_.HealthStatus)\"; "
                "Status=\"$($_.OperationalStatus)\"; Grootte=$_.Size; Temp=$r.Temperature; Slijtage=$r.Wear; "
                "Fouten=$r.ReadErrorsUncorrected; Uren=$r.PowerOnHours} }", timeout=90)
    return d


def scan_schijf():
    v = []
    for s in schijven():
        gezond = (s.get("Gezond") or "").lower()
        detail = "%s, %s" % (s.get("Soort") or "?", human(s.get("Grootte") or 0))
        if s.get("Temp"):
            detail += ", %s °C" % s["Temp"]
        if s.get("Slijtage") not in (None, ""):
            detail += ", slijtage %s%%" % s["Slijtage"]
        if gezond and gezond != "healthy":
            v.append(Vondst("schijf", s.get("Naam", "?"), detail, VERDACHT,
                            "Windows meldt dat deze schijf NIET gezond is. Maak meteen een back-up!", "", s))
        elif (s.get("Slijtage") or 0) >= 80:
            v.append(Vondst("schijf", s.get("Naam", "?"), detail, LET_OP,
                            "De SSD is flink versleten. Denk aan vervangen en maak een back-up.", "", s))
        elif (s.get("Fouten") or 0) > 0:
            v.append(Vondst("schijf", s.get("Naam", "?"), detail, LET_OP,
                            "Er waren leesfouten die niet hersteld konden worden.", "", s))
        else:
            v.append(Vondst("schijf", s.get("Naam", "?"), detail, INFO, "Gezond.", "", s))
    return v


def map_grootte(p):
    tot = 0
    for r, _, fs in os.walk(p):
        for f in fs:
            try:
                tot += os.path.getsize(os.path.join(r, f))
            except OSError:
                pass
    return tot


def windows_old():
    p = os.path.join(os.environ.get("SystemDrive", "C:") + "\\", "Windows.old")
    return (p, map_grootte(p)) if os.path.isdir(p) else (p, 0)


def run_lang(args, on_line=None, timeout=3600):
    """Lang commando (sfc/DISM) met regel-voor-regel uitvoer."""
    try:
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=NO_WIN)
    except Exception as e:
        return -1, str(e)
    laatste = []
    buf = b""
    start = time.time()
    while True:
        ch = p.stdout.read(256)
        if not ch:
            break
        buf += ch
        tekst = buf.replace(b"\x00", b"").decode("utf-8", "replace") if b"\x00" in buf else buf.decode("cp850", "replace")
        delen = re.split(r"[\r\n]+", tekst)
        if len(delen) > 1:
            for d in delen[:-1]:
                d = d.strip()
                if d:
                    laatste.append(d)
                    if on_line:
                        on_line(d)
            rest = delen[-1]
            buf = rest.encode("cp850", "replace")
        if time.time() - start > timeout:
            p.kill()
            break
    p.wait()
    return p.returncode, "\n".join(laatste[-6:])


def doe_sfc(on_line=None):
    if not is_admin():
        return False, "Hiervoor moet DraveGuard als beheerder draaien."
    rc, laatst = run_lang(["sfc", "/scannow"], on_line)
    return rc == 0, laatst or ("Klaar." if rc == 0 else "sfc gaf foutcode %s" % rc)


def doe_dism(on_line=None):
    if not is_admin():
        return False, "Hiervoor moet DraveGuard als beheerder draaien."
    rc, laatst = run_lang(["DISM", "/Online", "/Cleanup-Image", "/RestoreHealth"], on_line)
    return rc == 0, laatst or ("Klaar." if rc == 0 else "DISM gaf foutcode %s" % rc)


def doe_winsxs(on_line=None):
    if not is_admin():
        return False, "Hiervoor moet DraveGuard als beheerder draaien."
    rc, laatst = run_lang(["DISM", "/Online", "/Cleanup-Image", "/StartComponentCleanup"], on_line)
    return rc == 0, laatst or ("Klaar." if rc == 0 else "DISM gaf foutcode %s" % rc)


def doe_windows_old(on_line=None):
    p, g = windows_old()
    if not g:
        return True, "Er is geen Windows.old."
    if not is_admin():
        return False, "Hiervoor moet DraveGuard als beheerder draaien."
    say = on_line or (lambda s: None)
    say("Eigenaar worden van Windows.old ...")
    _run(["takeown", "/F", p, "/R", "/A", "/D", "Y"], timeout=1800)
    say("Rechten geven ...")
    _run(["icacls", p, "/grant", "*S-1-5-32-544:F", "/T", "/C", "/Q"], timeout=1800)
    say("Verwijderen ...")
    _run(["cmd", "/c", "rd", "/s", "/q", p], timeout=1800)
    over = map_grootte(p) if os.path.isdir(p) else 0
    if over == 0:
        return True, "Windows.old verwijderd (%s vrij)." % human(g)
    return False, "Deels verwijderd; %s bleef staan (in gebruik)." % human(over)


# ---------------------------------------------------------------- 4. programma-updates (winget)

def winget_pad():
    return shutil.which("winget") or ""


def _winget_tabel(tekst):
    """Leest de winget-tabel, taal-onafhankelijk (via de kolomposities)."""
    tekst = tekst.replace("\r\n", "\n").replace("\r", "\n")
    regels = [r.rstrip() for r in tekst.split("\n")]
    for i, r in enumerate(regels):
        if re.fullmatch(r"-{20,}", r.strip()) and i > 0:
            kop = regels[i - 1]
            kop = kop[kop.find(kop.lstrip()[:1]):] if kop.strip() else kop
            # ruis (spinner) voor de kop weghalen
            m = re.search(r"\S", kop)
            kop = kop[m.start():] if m else kop
            starts = [mm.start() for mm in re.finditer(r"\S+", kop)]
            if len(starts) < 4:
                return []
            uit = []
            for r2 in regels[i + 1:]:
                if not r2.strip():
                    continue
                if re.match(r"^\d+\s+\S+", r2.strip()) and len(r2.strip().split()) <= 8 and \
                        not re.search(r"\s{2,}", r2.strip()):
                    break           # slotzin, bv. '19 upgrades available.'
                if r2.strip().startswith("-"):
                    break
                if len(r2) < starts[3]:
                    continue
                cel = [r2[starts[k]:(starts[k + 1] if k + 1 < len(starts) else None)].strip()
                       for k in range(len(starts))]
                if len(cel) >= 4 and cel[1] and " " not in cel[1]:
                    uit.append({"naam": cel[0], "id": cel[1], "versie": cel[2], "nieuw": cel[3],
                                "bron": cel[4] if len(cel) > 4 else ""})
            return uit
    return []


def updates_zoeken():
    """Lijst programma's met een nieuwere versie. Geeft (lijst, bericht)."""
    w = winget_pad()
    if not w:
        return [], "winget ontbreekt. Installeer 'App Installer' uit de Microsoft Store."
    out, rc = _run([w, "upgrade", "--accept-source-agreements", "--disable-interactivity"], timeout=180)
    lijst = _winget_tabel(out)
    return lijst, ("%d programma's kunnen bijgewerkt worden." % len(lijst)) if lijst else "Alles is bijgewerkt."


def update_een(pid, on_line=None):
    w = winget_pad()
    if not w:
        return False, "winget ontbreekt."
    rc, laatst = run_lang([w, "upgrade", "--id", pid, "-e", "--silent", "--accept-package-agreements",
                           "--accept-source-agreements", "--disable-interactivity"], on_line, timeout=1800)
    return rc == 0, laatst or ("Bijgewerkt." if rc == 0 else "winget gaf foutcode %s" % rc)


def scan_updates():
    lijst, msg = updates_zoeken()
    return [Vondst("update", u["naam"], "%s  ->  %s" % (u["versie"], u["nieuw"]), INFO,
                   "Er is een nieuwere versie.", "Bijwerken via winget", u) for u in lijst], msg


# ---------------------------------------------------------------- rapport

def rapport_opslaan(regels):
    os.makedirs(RAPPORT_MAP, exist_ok=True)
    p = os.path.join(RAPPORT_MAP, "onderhoud_%s.txt" % time.strftime("%Y-%m-%d_%H%M"))
    with open(p, "w", encoding="utf-8") as f:
        f.write("DraveGuard - Totaal onderhoud - %s\n\n" % time.strftime("%d-%m-%Y %H:%M"))
        f.write("\n".join(regels) + "\n")
    return p


def herstart_als_beheerder():
    """Start DraveGuard opnieuw met beheerdersrechten (Windows vraagt om toestemming)."""
    if not WINDOWS:
        return False
    try:
        import ctypes
        if getattr(sys, "frozen", False):
            exe, args = sys.executable, ""
        else:
            exe = sys.executable.replace("python.exe", "pythonw.exe")
            args = '"%s"' % os.path.abspath(sys.argv[0])
        r = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, None, 1)
        return r > 32
    except Exception:
        return False
