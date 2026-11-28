# -*- coding: utf-8 -*-
"""DraveGuard - telefoon-onderhoud via adb (DraveCare, pc-kant).

Alles via adb (draadloze foutopsporing). Niets wordt zonder jouw klik veranderd.
Dravenlock (Roger & Claudio).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
import html

NO_WIN = 0x08000000 if os.name == "nt" else 0

# Standaardmappen op de telefoon die je kunt ophalen (naam, pad)
MAPPEN = [
    ("Camera (foto's en video's)", "/sdcard/DCIM/Camera"),
    ("Schermafbeeldingen", "/sdcard/Pictures/Screenshots"),
    ("Afbeeldingen", "/sdcard/Pictures"),
    ("Downloads", "/sdcard/Download"),
    ("Documenten", "/sdcard/Documents"),
    ("Video's", "/sdcard/Movies"),
    ("Muziek", "/sdcard/Music"),
    ("Opnames", "/sdcard/Recordings"),
    ("WhatsApp-media", "/sdcard/Android/media/com.whatsapp/WhatsApp/Media"),
    ("DraveCare-prullenbak", "/sdcard/DraveCare_prullenbak"),
]


def zoek_adb(eigen: str = "") -> str:
    """Vind adb.exe: eigen instelling -> naast de exe -> bekende plek -> PATH."""
    kand = []
    if eigen:
        kand.append(eigen)
    basis = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
    kand += [os.path.join(basis, "platform-tools", "adb.exe"),
             os.path.join(basis, "assets", "platform-tools", "adb.exe"),
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk", "platform-tools", "adb.exe")]
    for k in kand:
        if k and os.path.isfile(k):
            return k
    # Gangbare plekken op elke schijf: X:\platform-tools, X:\<map>\platform-tools, X:\<map>\Tools\platform-tools
    import glob
    for d in "CDEFG":
        for patroon in ("%s:\\*\\Tools\\platform-tools\\adb.exe", "%s:\\platform-tools\\adb.exe",
                        "%s:\\*\\platform-tools\\adb.exe"):
            gevonden = glob.glob(patroon % d)
            if gevonden:
                return gevonden[0]
    w = shutil.which("adb")
    return w or ""


class Adb:
    def __init__(self, pad: str = "", adres: str = ""):
        self.pad = zoek_adb(pad)
        self.adres = adres.strip()

    # ---------------- basis
    def _run(self, args, timeout=60, serial=True):
        if not self.pad:
            raise RuntimeError("adb.exe niet gevonden. Kies de plek van adb.exe bij 'Koppelen'.")
        cmd = [self.pad]
        if serial and self.adres:
            cmd += ["-s", self.adres]
        cmd += list(args)
        p = subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=NO_WIN)
        out = p.stdout.decode("utf-8", "replace")
        err = p.stderr.decode("utf-8", "replace")
        return p.returncode, out, err

    def sh(self, opdracht: str, timeout=60) -> str:
        rc, out, err = self._run(["shell", opdracht], timeout=timeout)
        return out if out.strip() else err

    # ---------------- verbinden
    def verbind(self, adres: str) -> str:
        self.adres = adres.strip()
        rc, out, err = self._run(["connect", self.adres], timeout=20, serial=False)
        return (out + err).strip()

    def zoek_poort(self, ip: str, say=print) -> str:
        """De poort van Draadloze foutopsporing verandert na een herstart. Zoek hem zelf op:
        eerst via mDNS, anders alle mogelijke poorten (30000-49999) op jouw eigen telefoon nalopen."""
        import socket
        from concurrent.futures import ThreadPoolExecutor
        try:
            rc, out, err = self._run(["mdns", "services"], timeout=10, serial=False)
            for r in out.splitlines():
                m = re.search(r"(\d+\.\d+\.\d+\.\d+):(\d+)", r)
                if m and "connect" in r and m.group(1) == ip:
                    return "%s:%s" % (m.group(1), m.group(2))
        except Exception:
            pass
        say("Nieuwe poort zoeken op %s (duurt ongeveer een halve minuut)..." % ip)
        def open_(poort):
            try:
                with socket.create_connection((ip, poort), timeout=0.4):
                    return poort
            except OSError:
                return None
        with ThreadPoolExecutor(max_workers=400) as ex:
            open_poorten = [p for p in ex.map(open_, range(30000, 50000)) if p]
        for poort in open_poorten:
            adres = "%s:%d" % (ip, poort)
            uit = self.verbind(adres)
            if "connected" in uit.lower() and self.verbonden():
                return adres
        return ""

    def verbind_slim(self, say=print) -> bool:
        """Verbinden met het bekende adres; lukt dat niet, dan zelf de nieuwe poort zoeken."""
        if not self.adres:
            return False
        if self.verbonden():
            return True
        self.verbind(self.adres)
        if self.verbonden():
            return True
        ip = self.adres.split(":")[0]
        nieuw = self.zoek_poort(ip, say)
        if nieuw:
            self.adres = nieuw
            return True
        return False

    def koppel(self, adres: str, code: str) -> str:
        rc, out, err = self._run(["pair", adres.strip(), code.strip()], timeout=30, serial=False)
        return (out + err).strip()

    def apparaten(self):
        rc, out, err = self._run(["devices"], timeout=15, serial=False)
        res = []
        for r in out.splitlines()[1:]:
            d = r.split()
            if len(d) >= 2:
                res.append((d[0], d[1]))
        return res

    def verbonden(self) -> bool:
        for s, st in self.apparaten():
            if st == "device" and (not self.adres or s == self.adres):
                if not self.adres:
                    self.adres = s
                return True
        return False

    # ---------------- info
    def info(self) -> dict:
        g = lambda k: self.sh("getprop " + k).strip()
        return {"merk": g("ro.product.manufacturer"), "model": g("ro.product.model"),
                "android": g("ro.build.version.release"), "patch": g("ro.build.version.security_patch")}

    def opslag(self):
        """(totaal_bytes, gebruikt_bytes) van /data."""
        out = self.sh("df -k /data")
        for r in out.splitlines()[1:]:
            d = r.split()
            if len(d) >= 4 and d[1].isdigit():
                return int(d[1]) * 1024, int(d[2]) * 1024
        return 0, 0

    def batterij(self) -> dict:
        out = self.sh("dumpsys battery")
        v = {}
        for r in out.splitlines():
            if ":" in r:
                k, _, w = r.strip().partition(":")
                v[k.strip()] = w.strip()
        gez = {"1": "onbekend", "2": "goed", "3": "te warm", "4": "versleten", "5": "te hoge spanning",
               "6": "fout", "7": "te koud"}
        return {"niveau": v.get("level", "?"), "gezondheid": gez.get(v.get("health", ""), v.get("health", "?")),
                "temp": (int(v["temperature"]) / 10.0) if v.get("temperature", "").isdigit() else None,
                "spanning": v.get("voltage", "?"),
                "laadt": v.get("AC powered") == "true" or v.get("USB powered") == "true"
                or v.get("Wireless powered") == "true"}

    # ---------------- apps
    def uid_naar_pakket(self) -> dict:
        out = self.sh("cmd package list packages -U")
        m = {}
        for r in out.splitlines():
            mm = re.match(r"package:(\S+)\s+uid:(\d+)", r.strip())
            if mm:
                m.setdefault(mm.group(2), []).append(mm.group(1))
        return m

    def gebruikers_apps(self) -> list:
        out = self.sh("pm list packages -3")
        return sorted(r.split(":", 1)[1].strip() for r in out.splitlines() if r.startswith("package:"))

    def app_groottes(self) -> dict:
        """pakket -> (app, data, cache) bytes uit dumpsys diskstats."""
        out = self.sh("dumpsys diskstats", timeout=90)
        def lijst(naam):
            m = re.search(naam + r':\s*\[(.*?)\]', out, re.S)
            if not m:
                return []
            return [x.strip().strip('"') for x in m.group(1).split(",") if x.strip()]
        namen = lijst("Package Names")
        app, data, cache = lijst("App Sizes"), lijst("App Data Sizes"), lijst("Cache Sizes")
        res = {}
        for i, n in enumerate(namen):
            try:
                res[n] = (int(app[i]), int(data[i]), int(cache[i]))
            except (IndexError, ValueError):
                pass
        return res

    def laatst_gebruikt(self) -> dict:
        """pakket -> tijd (sec) van laatste gebruik/zichtbaar, uit usagestats."""
        out = self.sh("dumpsys usagestats", timeout=120)
        res = {}
        for r in out.splitlines():
            m = re.search(r"package=(\S+)", r)
            if not m:
                continue
            p = m.group(1)
            for k, t in re.findall(r'(lastTimeUsed|lastTimeVisible|lastTimeFS)="([^"]+)"', r):
                if t.startswith("1970"):
                    continue
                try:
                    ts = time.mktime(time.strptime(t[:19], "%Y-%m-%d %H:%M:%S"))
                except Exception:
                    continue
                res[p] = max(res.get(p, 0), ts)
        return res

    def apps_met_recht(self, op: str) -> list:
        for vorm in (op, "android:" + op.lower()):
            out = self.sh("cmd appops query-op %s allow" % vorm)
            if "Unknown" not in out and "Error" not in out and "error" not in out:
                return [r.strip() for r in out.splitlines() if r.strip() and "." in r and " " not in r.strip()]
        return []

    def verwijder_app(self, pakket: str, backup_map: str = "", say=print) -> bool:
        if backup_map:
            try:
                os.makedirs(backup_map, exist_ok=True)
                for r in self.sh("pm path " + pakket).splitlines():
                    if r.startswith("package:"):
                        pad = r.split(":", 1)[1].strip()
                        doel = os.path.join(backup_map, pakket + "_" + os.path.basename(pad))
                        self._run(["pull", pad, doel], timeout=300)
                say("  reservekopie (apk) gemaakt: %s" % pakket)
            except Exception as e:
                say("  geen reservekopie gelukt: %s" % e)
        rc, out, err = self._run(["uninstall", pakket], timeout=120)
        ok = "Success" in out
        say(("  verwijderd: %s" if ok else "  NIET verwijderd: %s") % pakket)
        return ok

    # ---------------- batterij per app
    def stroomvreters(self, top=15) -> list:
        """[(pakket, mAh)] uit batterystats --checkin (regels 'pwi'). Leeg als het toestel het niet geeft."""
        out = self.sh("dumpsys batterystats --checkin", timeout=120)
        uidmap = self.uid_naar_pakket()
        per = {}
        for r in out.splitlines():
            d = r.split(",")
            if len(d) > 5 and d[3] == "pwi" and d[4] == "uid":
                try:
                    uid, mah = d[1], float(d[5])
                except ValueError:
                    continue
                pk = uidmap.get(uid, [])
                if not pk or len(pk) > 3 or int(uid) < 10000:
                    naam = "Android-systeem"
                else:
                    naam = ", ".join(pk)
                per[naam] = per.get(naam, 0.0) + mah
        return sorted(per.items(), key=lambda x: -x[1])[:top]

    # ---------------- caches
    def caches_opruimen(self, say=print) -> int:
        tot0, geb0 = self.opslag()
        say("Caches van alle apps opruimen...")
        self.sh("pm trim-caches 9999G", timeout=300)
        time.sleep(2)
        tot1, geb1 = self.opslag()
        vrij = max(0, geb0 - geb1)
        say("Klaar. Vrijgekomen: %s" % mooi(vrij))
        return vrij

    # ---------------- mappen en bestanden
    def map_grootte(self, pad: str) -> int:
        out = self.sh('du -sk "%s" 2>/dev/null' % pad, timeout=120)
        m = re.match(r"\s*(\d+)", out)
        return int(m.group(1)) * 1024 if m else -1

    def bestanden(self, pad: str) -> list:
        """[(pad, grootte)] van alle bestanden onder pad."""
        out = self.sh('find "%s" -type f -exec stat -c "%%s|%%n" {} + 2>/dev/null' % pad, timeout=600)
        res = []
        for r in out.splitlines():
            g, _, n = r.partition("|")
            if g.isdigit() and n:
                res.append((n, int(g)))
        return res

    def ophalen(self, pad: str, doelmap: str, say=print, stop=lambda: False) -> tuple:
        """Haalt alleen NIEUWE bestanden op (zelfde naam + grootte = overslaan). (nieuw, overgeslagen, bytes)."""
        lijst = self.bestanden(pad)
        nieuw = over = byt = 0
        for i, (n, g) in enumerate(lijst, 1):
            if stop():
                say("Gestopt.")
                break
            rel = n[len(pad):].lstrip("/")
            doel = os.path.join(doelmap, *rel.split("/"))
            if os.path.isfile(doel) and os.path.getsize(doel) == g:
                over += 1
                continue
            os.makedirs(os.path.dirname(doel), exist_ok=True)
            rc, out, err = self._run(["pull", "-a", n, doel], timeout=1800)
            if rc == 0 and os.path.isfile(doel):
                nieuw += 1
                byt += g
                if nieuw % 10 == 1:
                    say("  %d/%d  %s" % (i, len(lijst), rel))
            else:
                say("  mislukt: %s" % rel)
        return nieuw, over, byt

    # ---------------- back-up (contacten, berichten, alle bestanden)
    def content(self, uri: str, kolommen: list, timeout=180) -> list:
        """Leest een Android-databank (contacten, sms) via 'content query'. Geeft [dict]."""
        out = self.sh('content query --uri %s --projection %s' % (uri, ":".join(kolommen)), timeout=timeout)
        rijen, huidig = [], None
        for r in out.splitlines():
            m = re.match(r"Row: \d+ (.*)", r)
            if m:
                if huidig is not None:
                    rijen.append(huidig)
                huidig = m.group(1)
            elif huidig is not None:
                huidig += "\n" + r          # waarde met een nieuwe regel (notitie, sms)
        if huidig is not None:
            rijen.append(huidig)
        uit = []
        for tekst in rijen:
            d, rest = {}, tekst
            for i, k in enumerate(kolommen):
                if not rest.startswith(k + "="):
                    break
                rest = rest[len(k) + 1:]
                if i + 1 < len(kolommen):
                    j = rest.find(", " + kolommen[i + 1] + "=")
                    waarde, rest = (rest, "") if j < 0 else (rest[:j], rest[j + 2:])
                else:
                    waarde = rest
                d[k] = None if waarde == "NULL" else waarde
            if d:
                uit.append(d)
        return uit

    def contacten(self) -> list:
        """[{naam, tel:[(nummer,soort)], mail:[], adres:[], org, titel, verjaardag, notitie, web:[], bijnaam}]"""
        kol = ["contact_id", "mimetype", "display_name", "data1", "data2", "data3", "data4", "data5", "data6"]
        rijen = self.content("content://com.android.contacts/data", kol)
        per = {}
        for r in rijen:
            cid = r.get("contact_id")
            if not cid:
                continue
            c = per.setdefault(cid, {"naam": r.get("display_name") or "", "n": None, "tel": [], "mail": [],
                                     "adres": [], "org": "", "titel": "", "verjaardag": "", "notitie": "",
                                     "web": [], "bijnaam": ""})
            mt = (r.get("mimetype") or "").rsplit("/", 1)[-1]
            d1 = (r.get("data1") or "").strip()
            if mt == "name":
                c["n"] = (r.get("data3") or "", r.get("data2") or "", r.get("data5") or "",
                          r.get("data4") or "", r.get("data6") or "")
                if d1 and not c["naam"]:
                    c["naam"] = d1
            elif mt == "phone_v2" and d1:
                soort = {"1": "HOME", "2": "CELL", "3": "WORK"}.get(r.get("data2") or "", "VOICE")
                if all(_cijfers(d1) != _cijfers(t) for t, _ in c["tel"]):
                    c["tel"].append((d1, soort))
            elif mt == "email_v2" and d1 and d1 not in c["mail"]:
                c["mail"].append(d1)
            elif mt == "postal-address_v2" and d1 and d1 not in c["adres"]:
                c["adres"].append(d1)
            elif mt == "organization":
                c["org"] = c["org"] or d1
                c["titel"] = c["titel"] or (r.get("data4") or "")
            elif mt == "contact_event" and (r.get("data2") or "") == "3":
                c["verjaardag"] = d1
            elif mt == "note" and d1:
                c["notitie"] = d1
            elif mt == "website" and d1 and d1 not in c["web"]:
                c["web"].append(d1)
            elif mt == "nickname" and d1:
                c["bijnaam"] = d1
        return sorted([c for c in per.values() if c["naam"] or c["tel"] or c["mail"]],
                      key=lambda c: c["naam"].lower())

    def berichten(self) -> list:
        """Sms'jes: [{adres, datum(ms), soort(1=in,2=uit), tekst}]"""
        return self.content("content://sms", ["address", "date", "type", "body"])

    def sd_kaarten(self) -> list:
        out = self.sh("ls /storage 2>/dev/null")
        return ["/storage/" + n.strip() for n in out.split()
                if n.strip() and n.strip() not in ("emulated", "self")]

    def bestanden_alles(self, pad: str) -> list:
        """Alle bestanden onder pad, zonder app-binnenkant (Android/data, obb), miniaturen en de prullenbak."""
        pad = pad.rstrip("/")
        op = ('find "%s" -path "%s/Android/data" -prune -o -path "%s/Android/obb" -prune '
              '-o -name ".thumbnails" -prune -o -name "DraveCare_prullenbak" -prune '
              '-o -type f -exec stat -c "%%s|%%n" {} + 2>/dev/null' % (pad, pad, pad))
        res = []
        for r in self.sh(op, timeout=1800).splitlines():
            g, _, n = r.partition("|")
            if g.isdigit() and n:
                res.append((n, int(g)))
        return res

    def ophalen_lijst(self, pad: str, lijst: list, doelmap: str, say=print, stop=lambda: False) -> tuple:
        """Zoals ophalen(), maar met een kant-en-klare lijst. (nieuw, overgeslagen, bytes, mislukt)"""
        nieuw = over = byt = fout = 0
        totaal = len(lijst)
        for i, (n, g) in enumerate(lijst, 1):
            if stop():
                say("Gestopt.")
                break
            rel = n[len(pad):].lstrip("/")
            doel = os.path.join(doelmap, *rel.split("/"))
            if os.path.isfile(doel) and os.path.getsize(doel) == g:
                over += 1
                continue
            os.makedirs(os.path.dirname(doel), exist_ok=True)
            rc, out, err = self._run(["pull", "-a", n, doel], timeout=1800)
            if rc == 0 and os.path.isfile(doel):
                nieuw += 1
                byt += g
                if nieuw % 25 == 1:
                    say("  %d/%d  %s" % (i, totaal, rel))
            else:
                fout += 1
        return nieuw, over, byt, fout

    # ---------------- terugzetten (pc -> telefoon)
    def terug_bestanden(self, pc_map: str, pad: str, say=print, stop=lambda: False) -> tuple:
        """Zet bestanden uit de back-up terug, alleen wat op de telefoon ONTBREEKT. (gezet, stonden er al, bytes, mislukt)"""
        pad = pad.rstrip("/")
        say("Kijken wat er al op de telefoon staat...")
        op_tel = {n[len(pad):].lstrip("/") for n, g in self.bestanden_alles(pad)}
        gezet = al = byt = fout = 0
        for d, sub, fs in os.walk(pc_map):
            for f in fs:
                if stop():
                    say("Gestopt.")
                    return gezet, al, byt, fout
                bron = os.path.join(d, f)
                rel = os.path.relpath(bron, pc_map).replace("\\", "/")
                if rel in op_tel:
                    al += 1
                    continue
                doel = pad + "/" + rel
                rc, out, err = self._run(["push", bron, doel], timeout=1800)
                if rc == 0:
                    gezet += 1
                    byt += os.path.getsize(bron)
                    if gezet % 25 == 1:
                        say("  terug: " + rel)
                else:
                    fout += 1
        try:   # de galerij laten weten dat er weer foto's zijn
            self.sh("content call --method scan_volume --uri content://media --arg external_primary", timeout=120)
        except Exception:
            pass
        return gezet, al, byt, fout

    def contacten_klaarzetten(self, vcf: str) -> str:
        """Zet het contactenbestand in Download op de telefoon en opent de app Contacten."""
        naam = os.path.basename(vcf)
        doel = "/sdcard/Download/" + naam
        rc, out, err = self._run(["push", vcf, doel], timeout=120)
        if rc != 0:
            raise RuntimeError((out + err).strip() or "Kopieren mislukt")
        self.sh("am start -a android.intent.action.MAIN -c android.intent.category.APP_CONTACTS", timeout=20)
        return doel

    def zet_backup_merk(self, tekst: str):
        """Laat op de telefoon achter wanneer de laatste back-up was (DraveCare toont dat)."""
        veilig = tekst.replace('"', "").replace("$", "").replace("`", "")
        self.sh('mkdir -p /sdcard/DraveCare && echo "%s" > /sdcard/DraveCare/laatste_backup.txt' % veilig)

    def grote_bestanden(self, min_mb=100) -> list:
        out = self.sh('find /sdcard -type f -size +%dM -exec stat -c "%%s|%%n" {} + 2>/dev/null' % min_mb,
                      timeout=600)
        res = []
        for r in out.splitlines():
            g, _, n = r.partition("|")
            if g.isdigit():
                res.append((n, int(g)))
        return sorted(res, key=lambda x: -x[1])

    # ---------------- volledige controle
    def controle(self, say=print) -> dict:
        say("Toestel uitlezen...")
        r = {"info": self.info()}
        say("Opslag meten...")
        r["opslag"] = self.opslag()
        say("Batterij bekijken...")
        r["batterij"] = self.batterij()
        say("Apps nalopen...")
        r["apps"] = self.gebruikers_apps()
        say("Rechten controleren (installeren, camera, microfoon, locatie)...")
        r["installeren"] = self.apps_met_recht("REQUEST_INSTALL_PACKAGES")
        eigen = set(r["apps"])                      # alleen jouw eigen apps tellen
        r["camera"] = [a for a in self.apps_met_recht("CAMERA") if a in eigen]
        r["microfoon"] = [a for a in self.apps_met_recht("RECORD_AUDIO") if a in eigen]
        r["locatie"] = [a for a in self.apps_met_recht("FINE_LOCATION") if a in eigen]
        say("Grote bestanden zoeken (groter dan 100 MB)...")
        r["groot"] = self.grote_bestanden(100)
        say("Stroomverbruik per app...")
        try:
            r["stroom"] = self.stroomvreters(10)
        except Exception:
            r["stroom"] = []
        say("Klaar met kijken.")
        return r


def _cijfers(t: str) -> str:
    c = "".join(x for x in (t or "") if x.isdigit())
    return c[-9:]


def _v(t: str) -> str:
    return (t or "").replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def maak_vcf(contacten: list) -> str:
    """vCard 3.0 - werkt met elke telefoon (Contacten -> Importeren) en met Outlook/Gmail."""
    r = []
    for c in contacten:
        r += ["BEGIN:VCARD", "VERSION:3.0", "FN:" + _v(c["naam"] or (c["tel"][0][0] if c["tel"] else ""))]
        if c.get("n"):
            r.append("N:" + ";".join(_v(x) for x in c["n"]))
        else:
            r.append("N:;" + _v(c["naam"]) + ";;;")
        if c.get("bijnaam"):
            r.append("NICKNAME:" + _v(c["bijnaam"]))
        for t, soort in c["tel"]:
            r.append("TEL;TYPE=%s:%s" % (soort, t))
        for m in c["mail"]:
            r.append("EMAIL;TYPE=INTERNET:" + m)
        for a in c["adres"]:
            r.append("ADR:;;" + _v(a) + ";;;;")
        if c.get("org"):
            r.append("ORG:" + _v(c["org"]))
        if c.get("titel"):
            r.append("TITLE:" + _v(c["titel"]))
        if c.get("verjaardag"):
            r.append("BDAY:" + c["verjaardag"])
        for w in c["web"]:
            r.append("URL:" + w)
        if c.get("notitie"):
            r.append("NOTE:" + _v(c["notitie"]))
        r.append("END:VCARD")
    return "\r\n".join(r) + "\r\n"


def berichten_html(berichten: list, contacten: list, pad: str) -> str:
    """Leesbaar overzicht van de sms'jes, per persoon, groot lettertype."""
    namen = {}
    for c in contacten:
        for t, _ in c["tel"]:
            namen[_cijfers(t)] = c["naam"]
    per = {}
    for b in berichten:
        per.setdefault(b.get("address") or "?", []).append(b)
    def sleutel(item):
        return -max(int(x.get("date") or 0) for x in item[1])
    h = ["<html><head><meta charset='utf-8'><title>Berichten</title><style>"
         "body{background:#16121f;color:#eee;font:20px Segoe UI,Arial;margin:30px}"
         "h1{color:#b59cff}h2{color:#ffd166;margin-top:34px}"
         ".in,.uit{padding:10px 14px;border-radius:12px;margin:8px 0;max-width:780px;white-space:pre-wrap}"
         ".in{background:#2a2340}.uit{background:#1f3b2c;margin-left:120px}"
         ".t{font-size:15px;color:#aaa}</style></head><body>",
         "<h1>📱 Berichten (sms) — back-up van %s</h1>" % time.strftime("%d-%m-%Y %H:%M"),
         "<p>%d berichten met %d personen.</p>" % (len(berichten), len(per))]
    for adres, lijst in sorted(per.items(), key=sleutel):
        naam = namen.get(_cijfers(adres), "")
        h.append("<h2>%s</h2>" % html.escape((naam + "  ·  " + adres) if naam else adres))
        for b in sorted(lijst, key=lambda x: int(x.get("date") or 0)):
            try:
                wanneer = time.strftime("%d-%m-%Y %H:%M", time.localtime(int(b.get("date") or 0) / 1000))
            except Exception:
                wanneer = ""
            k = "uit" if (b.get("type") or "") == "2" else "in"
            h.append("<div class='%s'><div class='t'>%s · %s</div>%s</div>" %
                     (k, "ik" if k == "uit" else "binnen", wanneer, html.escape(b.get("body") or "")))
    h.append("</body></html>")
    with open(pad, "w", encoding="utf-8") as f:
        f.write("\n".join(h))
    return pad


def mooi(b) -> str:
    if b is None or b < 0:
        return "?"
    for e in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024 or e == "TB":
            return ("%.0f %s" if e in ("B", "KB") else "%.1f %s") % (b, e)
        b /= 1024.0


def patch_oud(patch: str) -> int:
    """Hoeveel maanden de beveiligingsupdate oud is (of -1)."""
    try:
        j, m = int(patch[:4]), int(patch[5:7])
        nu = time.localtime()
        return (nu.tm_year - j) * 12 + (nu.tm_mon - m)
    except Exception:
        return -1


def oordeel(r: dict) -> list:
    """[(kleur, tekst)] — 'goed' / 'letop' / 'slecht'."""
    uit = []
    tot, geb = r["opslag"]
    if tot:
        pct = 100 * geb / tot
        k = "slecht" if pct > 90 else "letop" if pct > 75 else "goed"
        uit.append((k, "Opslag: %d%% vol (%s van %s)." % (pct, mooi(geb), mooi(tot))))
    b = r["batterij"]
    k = "goed" if b["gezondheid"] == "goed" else "letop"
    t = "Batterij: %s%%, gezondheid %s" % (b["niveau"], b["gezondheid"])
    if b["temp"] is not None:
        t += ", %.1f °C" % b["temp"]
        if b["temp"] > 42:
            k = "slecht"
    uit.append((k, t + "."))
    mnd = patch_oud(r["info"].get("patch", ""))
    if mnd >= 0:
        k = "slecht" if mnd > 12 else "letop" if mnd > 4 else "goed"
        uit.append((k, "Beveiligingsupdate: %s (%d maanden oud)." % (r["info"]["patch"], mnd)))
    n = len(r["installeren"])
    uit.append(("letop" if n else "goed",
                "Apps die zelf apps mogen installeren: %d%s" % (n, (" — " + ", ".join(r["installeren"])) if n else "")))
    for soort in ("camera", "microfoon", "locatie"):
        uit.append(("goed", "Eigen apps met toegang tot %s: %d" % (soort, len(r[soort]))))
    if r["groot"]:
        uit.append(("letop", "Grote bestanden (>100 MB): %d, samen %s." %
                    (len(r["groot"]), mooi(sum(g for _, g in r["groot"])))))
    return uit


def rapport_html(r: dict, pad: str) -> str:
    kl = {"goed": "#57d98a", "letop": "#ffd166", "slecht": "#ff6b6b"}
    i = r["info"]
    rijen = "".join('<li style="color:%s">%s</li>' % (kl[k], html.escape(t)) for k, t in oordeel(r))
    groot = "".join("<tr><td>%s</td><td>%s</td></tr>" % (html.escape(n), mooi(g)) for n, g in r["groot"][:30])
    stroom = "".join("<tr><td>%s</td><td>%.0f mAh</td></tr>" % (html.escape(n), m) for n, m in r["stroom"])
    def lijst(x):
        return ", ".join(html.escape(a) for a in x) or "geen"
    doc = f"""<!doctype html><html lang="nl"><meta charset="utf-8"><title>DraveCare rapport</title>
<style>body{{background:#16131f;color:#eee;font:20px/1.5 Segoe UI,sans-serif;margin:30px;}}
h1{{color:#b59cff}} h2{{color:#b59cff;margin-top:30px}} td{{padding:4px 14px;border-bottom:1px solid #333}} li{{margin:6px 0}}</style>
<h1>🐉 DraveCare — telefoonrapport</h1>
<p>{html.escape(i.get('merk',''))} {html.escape(i.get('model',''))} · Android {html.escape(i.get('android',''))} · {time.strftime('%d-%m-%Y %H:%M')}</p>
<h2>Samenvatting</h2><ul>{rijen}</ul>
<h2>Grote bestanden</h2><table>{groot or '<tr><td>geen</td></tr>'}</table>
<h2>Stroomverbruik per app (sinds laatste keer opladen)</h2><table>{stroom or '<tr><td>niet beschikbaar op dit toestel</td></tr>'}</table>
<h2>Rechten</h2>
<p><b>Mag apps installeren:</b> {lijst(r['installeren'])}</p>
<p><b>Camera:</b> {lijst(r['camera'])}</p>
<p><b>Microfoon:</b> {lijst(r['microfoon'])}</p>
<p><b>Locatie:</b> {lijst(r['locatie'])}</p>
<h2>Eigen apps ({len(r['apps'])})</h2><p>{lijst(r['apps'])}</p>
<p style="color:#9c94c0;font-size:16px">DraveGuard · Dravenlock</p></html>"""
    os.makedirs(os.path.dirname(pad), exist_ok=True)
    with open(pad, "w", encoding="utf-8") as f:
        f.write(doc)
    return pad
