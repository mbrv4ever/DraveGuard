# -*- coding: utf-8 -*-
# DraveCare voor Android - Copyright (C) 2026 Dravenlock (Roger & Claudio). Vrije software onder de GNU GPL v3.0.
"""care_app.py - DraveCare: je telefoon gezond en schoon, groot en duidelijk.

Opslag (grote/dubbele bestanden, oude downloads, prullenbak met 30 dagen terugzetten), batterij,
apps (laatst gebruikt, rechten) en veiligheid. Leon leest voor. Het zware werk (bestanden naar de pc,
alle caches) doet DraveGuard op de pc, tabblad Telefoon.
"""
import os
import threading
import time

import pygame

import droid
import opruim as O

VERSIE = "0.2"
ANDROID = droid.ANDROID
HIER = os.path.dirname(os.path.abspath(__file__))

ZWART = (10, 8, 16)
PANEEL = (22, 22, 30)
BLAUW = (111, 163, 214)
BLAUW_D = (34, 52, 78)
ZILVER = (230, 230, 236)
GRIJS = (150, 150, 162)
GOUD = (255, 179, 71)
GEEL = (255, 222, 60)
ROOD = (225, 70, 70)
ROOD_D = (122, 36, 36)
GROEN = (90, 210, 140)
GROEN_D = (28, 80, 52)
WIT = (250, 250, 255)
KLEUR = {"goed": GROEN, "letop": GEEL, "slecht": ROOD, "?": GRIJS}


class Stem:
    """Leon: vaste zinnetjes bij de app. Ontbreekt er een, dan leest de stem van Android de tekst voor."""

    def __init__(self):
        self.vast, self.cache, self.rij = {}, {}, []
        self.kanaal, self.vrij = None, 0
        self.tts, self.tts_klaar, self.tts_bezig_tot, self.tts_start = None, False, 0, 0
        try:
            pygame.mixer.init(22050, -16, 1, 1024)
            m = os.path.join(HIER, "stem_care")
            for f in os.listdir(m):
                if f.endswith(".wav"):
                    self.vast[f[:-4]] = os.path.join(m, f)
        except Exception:
            pass

    def zeg(self, delen):
        self.stil()
        self.rij = list(delen)

    def stil(self):
        self.rij = []
        try:
            if self.kanaal:
                self.kanaal.stop()
            if self.tts:
                self.tts.stop()
        except Exception:
            pass

    def bezig(self):
        return bool(self.rij) or (self.kanaal is not None and self.kanaal.get_busy()) or \
            time.time() < self.tts_bezig_tot

    def _android_zeg(self, tekst):
        try:
            if self.tts is None:
                from jnius import autoclass, PythonJavaClass, java_method

                class Klaar(PythonJavaClass):
                    __javainterfaces__ = ["android/speech/tts/TextToSpeech$OnInitListener"]

                    def __init__(s2, stem):
                        super().__init__()
                        s2.stem = stem

                    @java_method("(I)V")
                    def onInit(s2, status):
                        s2.stem.tts_klaar = status == 0

                act = autoclass("org.kivy.android.PythonActivity").mActivity
                self._klaar = Klaar(self)
                self.tts = autoclass("android.speech.tts.TextToSpeech")(act, self._klaar)
                t0 = time.time()
                while not self.tts_klaar and time.time() - t0 < 3:
                    time.sleep(0.05)
                self.tts.setLanguage(autoclass("java.util.Locale")("nl", "NL"))
                self.tts.setSpeechRate(0.9)
            self.tts.speak(tekst, 1, None, "drave")
            self.tts_start = time.time()
            self.tts_bezig_tot = time.time() + 1.0 + len(tekst) * 0.1
        except Exception:
            self.tts_bezig_tot = 0

    def update(self):
        nu = time.time()
        if self.kanaal is not None and self.kanaal.get_busy():
            self.vrij = nu + 0.06
            return
        if nu < self.tts_bezig_tot:
            try:
                if self.tts is not None and nu - self.tts_start > 1.0 and not self.tts.isSpeaking():
                    self.tts_bezig_tot = 0
            except Exception:
                pass
            return
        if self.rij and nu >= self.vrij:
            d = self.rij.pop(0)
            if isinstance(d, tuple):
                self.tts_start, self.tts_bezig_tot = nu, nu + 1.5
                self._android_zeg(d[1])            # op de hoofddraad (Android/JNI)
            else:
                p = self.vast.get(d)
                try:
                    s = self.cache.get(d) or (pygame.mixer.Sound(p) if p else None)
                except Exception:
                    s = None
                if s is not None:
                    self.cache[d] = s
                    self.kanaal = s.play()
            self.vrij = nu + 0.25


def patch_maanden(patch):
    try:
        j, m = int(patch[:4]), int(patch[5:7])
        nu = time.localtime()
        return (nu.tm_year - j) * 12 + (nu.tm_mon - m)
    except Exception:
        return -1


def stuks(n):
    return "1 bestand" if n == 1 else "%d bestanden" % n


def dagen_geleden(t):
    if not t:
        return "onbekend"
    d = int((time.time() - t) / 86400)
    if d <= 0:
        return "vandaag"
    if d == 1:
        return "gisteren"
    if d < 60:
        return "%d dagen geleden" % d
    return "%d maanden geleden" % (d // 30)


class App:
    def __init__(self):
        pygame.init()
        if ANDROID:
            info = pygame.display.Info()
            pw, ph = max(1, info.current_w), max(1, info.current_h)
            self.W, self.H = 540, int(540 * max(pw, ph) / min(pw, ph))
            self.venster = pygame.display.set_mode((self.W, self.H), pygame.FULLSCREEN | pygame.SCALED)
        else:
            self.W, self.H = 540, 1040
            self.venster = pygame.display.set_mode((self.W, self.H))
        pygame.display.set_caption("DraveCare")
        fb = os.path.join(HIER, "assets", "DejaVuSans-Bold.ttf")
        fr = os.path.join(HIER, "assets", "DejaVuSans.ttf")
        self.f_reus = pygame.font.Font(fb, 72)
        self.f_groot = pygame.font.Font(fb, 38)
        self.f = pygame.font.Font(fb, 28)
        self.f_mid = pygame.font.Font(fb, 24)
        self.f_klein = pygame.font.Font(fr, 22)
        self.f_mini = pygame.font.Font(fr, 18)
        self.klok = pygame.time.Clock()
        self.stem = Stem()
        self.scherm = "start"
        self.knoppen, self.sleep, self.scroll, self.max_scroll = [], None, 0, 0
        self.melding = None
        self.vraag = None              # (tekst, ja-actie)
        self.stop = False
        self.bezig = None              # tekst als er iets in de achtergrond draait
        self.stoppen = False
        # gegevens
        self.opslag = (0, 0)
        self.bat = {}
        self.veilig = {}
        self.apps = None
        self.app_open = None
        self.lijst_titel, self.lijst, self.gekozen, self.lijst_soort = "", [], set(), ""
        self.bak, self.bak_gekozen = [], set()
        self.taken = []                # (wanneer, functie): Android-dingen altijd op de hoofddraad
        self.lees_alles()
        self.later(0.3, self._laad_apps)
        threading.Thread(target=self._start_werk, daemon=True).start()

    # ------------------------------------------------------------ gegevens
    def lees_alles(self):
        self._bestanden_ok = droid.alle_bestanden_ok()
        self._gebruik_ok = droid.gebruik_ok()
        self.opslag = droid.opslag()
        self.bat = droid.batterij()
        self.veilig = droid.veiligheid()

    def later(self, sec, fn):
        self.taken.append((time.time() + sec, fn))

    def _laad_apps(self):
        try:
            self.apps = droid.apps()
        except Exception:
            self.apps = []

    def _start_werk(self):
        try:
            if self._bestanden_ok:
                O.oud_opruimen()           # alleen bestanden, geen Android-aanroepen
        except Exception:
            pass

    def oordeel_opslag(self):
        tot, vrij = self.opslag
        if not tot:
            return "?", "Opslag onbekend"
        pct = 100 * (tot - vrij) / tot
        k = "slecht" if pct > 90 else "letop" if pct > 75 else "goed"
        return k, "%d%% vol · %s vrij" % (pct, O.mooi(vrij))

    def oordeel_bat(self):
        b = self.bat
        if not b or b.get("niveau", -1) < 0:
            return "?", "Batterij onbekend"
        k = "goed"
        if b["code"] in (4, 5, 6) or b["temp"] > 45:
            k = "slecht"
        elif b["code"] in (3, 7) or b["temp"] > 40 or (b["niveau"] < 15 and not b["laadt"]):
            k = "letop"
        return k, "%d%% · %s · %.0f °C" % (b["niveau"], b["gezondheid"], b["temp"])

    def veilig_punten(self):
        v = self.veilig
        p = []
        if v.get("slot") is True:
            p.append(("goed", "Schermslot staat aan", None))
        elif v.get("slot") is False:
            p.append(("slecht", "Geen schermslot! Iedereen kan in je telefoon.", ("Schermslot instellen", droid.open_schermslot)))
        mnd = patch_maanden(v.get("patch", ""))
        if mnd >= 0:
            k = "slecht" if mnd > 12 else "letop" if mnd > 4 else "goed"
            t = "Beveiligingsupdate: %s (%d maanden oud)" % (v["patch"], mnd)
            if k != "goed":
                t += ". Zoek naar een update; komt er geen meer, dan krijgt dit toestel geen updates meer."
            p.append((k, t, ("Updates zoeken", droid.open_updates) if k != "goed" else None))
        if v.get("ontw"):
            p.append(("letop", "Ontwikkelaarsopties staan aan. Nodig voor DraveGuard op de pc; anders mag het uit.",
                      ("Ontwikkelaarsopties", droid.open_ontwikkelaar)))
        if self.apps is not None:
            inst = [a for a in self.apps if a["installeert"]]
            if inst:
                p.append(("letop", "Deze apps mogen zelf apps installeren: " + ", ".join(a["naam"] for a in inst[:6]) +
                          (" en meer" if len(inst) > 6 else "") + ". Alleen aan laten als je dat echt wilt.", None))
            else:
                p.append(("goed", "Geen enkele app mag zomaar apps installeren", None))
        return p

    def oordeel_veilig(self):
        p = self.veilig_punten()
        if any(k == "slecht" for k, _, _ in p):
            return "slecht", "Er is iets niet veilig"
        if any(k == "letop" for k, _, _ in p):
            return "letop", "%d punt(en) om naar te kijken" % sum(1 for k, _, _ in p if k == "letop")
        return "goed", "Alles in orde"

    def oordeel_apps(self):
        if self.apps is None:
            return "?", "Apps laden..."
        oud = [a for a in self.apps if a["gebruikt"] and time.time() - a["gebruikt"] > 90 * 86400]
        if not self._gebruik_ok:
            return "letop", "%d apps · tik om toegang te geven" % len(self.apps)
        if oud:
            return "letop", "%d apps · %d al 3 maanden niet gebruikt" % (len(self.apps), len(oud))
        return "goed", "%d apps" % len(self.apps)

    # ------------------------------------------------------------ Leon
    def lees_voor(self):
        if self.stem.bezig():
            self.stem.stil()
            return
        d = []
        ko, _ = self.oordeel_opslag()
        d.append({"goed": "c_opslag_goed", "letop": "c_opslag_letop", "slecht": "c_opslag_vol"}.get(ko, "c_opslag_goed"))
        b = self.bat
        kb, _ = self.oordeel_bat()
        if b.get("temp", 0) > 40:
            d.append("c_bat_warm")
        elif b.get("code") in (4, 5, 6):
            d.append("c_bat_slecht")
        elif b.get("niveau", 100) < 15 and not b.get("laadt"):
            d.append("c_bat_laag")
        else:
            d.append("c_bat_goed")
        v = self.veilig
        if v.get("slot") is False:
            d.append("c_slot_uit")
        mnd = patch_maanden(v.get("patch", ""))
        d.append("c_patch_oud" if mnd > 4 else "c_patch_goed")
        if self.apps and any(a["installeert"] for a in self.apps):
            d.append("c_installeer")
        if self.apps and any(a["gebruikt"] and time.time() - a["gebruikt"] > 90 * 86400 for a in self.apps):
            d.append("c_ongebruikt")
        if all(k == "goed" for k in (ko, kb, self.oordeel_veilig()[0])):
            d = ["c_alles_goed"] + d
        self.stem.zeg(d)

    # ------------------------------------------------------------ teken-hulp
    def meld(self, t, s=3.5):
        self.melding = (t, time.time() + s)

    def tekst(self, t, font, kl, x, y, midden=False, rechts=False, max_b=None):
        if max_b:
            while font.size(t)[0] > max_b and len(t) > 3:
                t = t[:-4] + "..."
        img = font.render(t, True, kl)
        r = img.get_rect()
        if midden:
            r.midtop = (x, y)
        elif rechts:
            r.topright = (x, y)
        else:
            r.topleft = (x, y)
        self.venster.blit(img, r)
        return r

    def breek(self, tekst, font, breed):
        regels, nu = [], ""
        for w in tekst.split():
            if font.size((nu + " " + w).strip())[0] <= breed:
                nu = (nu + " " + w).strip()
            else:
                if nu:
                    regels.append(nu)
                nu = w
        if nu:
            regels.append(nu)
        return regels or [""]

    def knop(self, rect, label, actie, kl=BLAUW_D, rand=BLAUW, font=None, tk=ZILVER):
        r = pygame.Rect(rect)
        pygame.draw.rect(self.venster, kl, r, border_radius=14)
        pygame.draw.rect(self.venster, rand, r, 3, border_radius=14)
        if label:
            f = font or self.f
            while f.size(label)[0] > r.w - 16 and f is not self.f_mini:
                f = {self.f_groot: self.f, self.f: self.f_mid, self.f_mid: self.f_klein}.get(f, self.f_mini)
            img = f.render(label, True, tk)
            self.venster.blit(img, img.get_rect(center=r.center))
        self.knoppen.append((r, actie))
        return r

    def naar(self, s):
        self.scherm = s
        self.scroll = 0

    def kop(self, titel, terug="start"):
        self.knop((16, 16, 140, 72), "Terug", lambda: self.naar(terug), kl=PANEEL)
        self.tekst(titel, self.f_groot, ZILVER, 176, 30, max_b=self.W - 190)

    def achtergrond(self, tekst, fn):
        if self.bezig:
            return
        self.bezig = tekst
        self.stoppen = False

        def werk():
            try:
                fn()
            except Exception as e:
                self.meld("Er ging iets mis: %s" % e, 8)
            finally:
                self.bezig = None
        threading.Thread(target=werk, daemon=True).start()

    # ------------------------------------------------------------ schermen
    def tegel(self, y, h, titel, oordeel, actie):
        k, t = oordeel
        r = pygame.Rect(20, y, self.W - 40, h)
        pygame.draw.rect(self.venster, PANEEL, r, border_radius=18)
        pygame.draw.rect(self.venster, KLEUR[k], r, 4, border_radius=18)
        pygame.draw.circle(self.venster, KLEUR[k], (r.x + 40, r.centery), 18)
        self.tekst(titel, self.f_groot, WIT, r.x + 76, r.y + 18)
        for i, regel in enumerate(self.breek(t, self.f_klein, r.w - 100)[:2]):
            self.tekst(regel, self.f_klein, ZILVER, r.x + 76, r.y + 68 + i * 28)
        self.knoppen.append((r, actie))

    def scherm_start(self):
        W, H = self.W, self.H
        self.tekst("DraveCare", self.f_groot, ZILVER, 20, 26)
        self.tekst("v" + VERSIE, self.f_mini, GRIJS, W - 20, 40, rechts=True)
        y, h = 110, 122
        gap = max(10, min(28, (H - 110 - 5 * h - 220) // 5))
        self.tegel(y, h, "Opslag", self.oordeel_opslag(), lambda: self.naar("opslag"))
        y += h + gap
        self.tegel(y, h, "Batterij", self.oordeel_bat(), lambda: (self.lees_alles(), self.naar("batterij")))
        y += h + gap
        self.tegel(y, h, "Apps", self.oordeel_apps(), lambda: self.naar("apps"))
        y += h + gap
        self.tegel(y, h, "Veiligheid", self.oordeel_veilig(), lambda: self.naar("veilig"))
        y += h + gap
        self.tegel(y, h, "Back-up", self.oordeel_backup(), lambda: self.naar("backup"))
        b = H - 200
        self.knop((20, b, W - 40, 82), "Stop met voorlezen" if self.stem.bezig() else "Lees voor (Leon)",
                  self.lees_voor, kl=GROEN_D, rand=GROEN)
        self.knop((20, b + 96, W - 40, 82), "Alles opnieuw nakijken", self.opnieuw, kl=PANEEL)

    def opnieuw(self):
        self.lees_alles()
        self.apps = None
        self.later(0.2, self._laad_apps)
        self.stem.zeg(["c_klaar"])

    def toegang_blok(self, y, tekst, knoptekst, actie):
        W = self.W
        for i, r in enumerate(self.breek(tekst, self.f_mid, W - 60)):
            self.tekst(r, self.f_mid, GEEL, 30, y + i * 34)
        y += len(self.breek(tekst, self.f_mid, W - 60)) * 34 + 16
        self.knop((20, y, W - 40, 82), knoptekst, actie, kl=BLAUW_D)
        return y + 100

    def scherm_opslag(self):
        W, H = self.W, self.H
        self.kop("Opslag")
        tot, vrij = self.opslag
        y = 110
        if tot:
            pct = (tot - vrij) / tot
            k, t = self.oordeel_opslag()
            r = pygame.Rect(20, y, W - 40, 54)
            pygame.draw.rect(self.venster, PANEEL, r, border_radius=12)
            pygame.draw.rect(self.venster, KLEUR[k], (r.x, r.y, int(r.w * pct), r.h), border_radius=12)
            self.tekst("%d%% vol" % (pct * 100), self.f, WIT, r.centerx, r.y + 10, midden=True)
            self.tekst("%s gebruikt · %s vrij · %s totaal" % (O.mooi(tot - vrij), O.mooi(vrij), O.mooi(tot)),
                       self.f_klein, ZILVER, W // 2, y + 66, midden=True)
        y += 116
        if not self._bestanden_ok:
            self.toegang_blok(y, "Om bestanden te zoeken en op te ruimen heeft DraveCare toegang tot je bestanden nodig. "
                                 "Tik op de knop en zet de schakelaar aan.", "Toegang geven", self._vraag_bestanden)
            return
        if time.time() - getattr(self, "_bak_t", 0) > 3:           # prullenbak-telling niet elk beeldje opnieuw
            self._bak_n, self._bak_t = len(O.inhoud()), time.time()
        n = self._bak_n
        for label, actie in (("Grote bestanden (> 50 MB)", lambda: self.zoek("groot")),
                             ("Dubbele foto's en video's", lambda: self.zoek("dubbel")),
                             ("Oude downloads (> 3 maanden)", lambda: self.zoek("down")),
                             ("Prullenbak (%d)" % n, self.open_bak)):
            self.knop((20, y, W - 40, 86), label, actie)
            y += 102
        uitleg = "Opruimen gaat eerst naar de prullenbak. Daar kun je 30 dagen alles terugzetten. " \
                 "Alle caches tegelijk opruimen en foto's naar de pc halen doe je met DraveGuard op de pc (tabblad Telefoon)."
        for i, r in enumerate(self.breek(uitleg, self.f_mini, W - 50)):
            self.tekst(r, self.f_mini, GRIJS, 25, y + 6 + i * 24)

    def _vraag_bestanden(self):
        droid.vraag_alle_bestanden()
        self.stem.zeg(["c_toegang"])

    def zoek(self, soort):
        self.lijst_soort = soort
        self.lijst, self.gekozen = [], set()
        self.lijst_titel = {"groot": "Grote bestanden", "dubbel": "Dubbele foto's", "down": "Oude downloads"}[soort]
        self.naar("lijst")

        def werk():
            if soort == "groot":
                r = O.grote(50, lambda: self.stoppen)
            elif soort == "dubbel":
                r = O.dubbel(lambda: self.stoppen, lambda t: setattr(self, "bezig", "Zoeken... " + t))
                self.stem.zeg(["c_dubbel" if r else "c_geen_dubbel"])
                self.gekozen = set(p for p, g, t in r)          # dubbele: alvast aangevinkt (de oudste blijft)
            else:
                r = O.oude_downloads(90, lambda: self.stoppen)
            self.lijst = r
        self.achtergrond("Zoeken...", werk)

    def scherm_lijst(self):
        W, H = self.W, self.H
        self.kop(self.lijst_titel, "opslag")
        boven, onder = 104, H - 200
        if self.bezig:
            self.tekst(self.bezig, self.f, GEEL, W // 2, 160, midden=True)
            self.knop((W // 2 - 110, 230, 220, 76), "Stop", lambda: setattr(self, "stoppen", True), kl=ROOD_D, rand=ROOD)
            return
        if not self.lijst:
            self.tekst("Niets gevonden.", self.f, GROEN, W // 2, 180, midden=True)
            return
        if self.lijst_soort == "dubbel":
            self.tekst("Het oudste exemplaar blijft altijd staan.", self.f_mini, GRIJS, 24, boven)
            boven += 28
        v = self.venster
        oud = v.get_clip()
        v.set_clip(pygame.Rect(0, boven, W, onder - boven))
        y = boven + 4 - self.scroll
        rh = 96
        for p, g, t in self.lijst:
            if boven - rh < y < onder:
                r = pygame.Rect(16, y, W - 32, rh - 10)
                aan = p in self.gekozen
                pygame.draw.rect(v, BLAUW_D if aan else PANEEL, r, border_radius=12)
                vak = pygame.Rect(r.x + 14, r.y + 22, 40, 40)
                pygame.draw.rect(v, GROEN if aan else GRIJS, vak, 3, border_radius=8)
                if aan:
                    pygame.draw.lines(v, GROEN, False, [(vak.x + 8, vak.y + 20), (vak.x + 17, vak.y + 30),
                                                        (vak.x + 33, vak.y + 10)], 5)
                self.tekst(os.path.basename(p), self.f_mid, WIT, r.x + 68, r.y + 10, max_b=r.w - 80)
                self.tekst("%s · %s" % (O.mooi(g), time.strftime("%d-%m-%Y", time.localtime(t))),
                           self.f_klein, ZILVER, r.x + 68, r.y + 44)
                map_ = os.path.dirname(p).replace(O.ROOT, "")
                self.tekst(map_, self.f_mini, GRIJS, r.x + 300, r.y + 48, max_b=r.w - 310)
                self.knoppen.append((r, lambda p=p: self.wissel(p)))
            y += rh
        v.set_clip(oud)
        self.max_scroll = max(0, len(self.lijst) * rh - (onder - boven))
        tot = sum(g for p, g, t in self.lijst if p in self.gekozen)
        self.knop((20, H - 186, W - 40, 76), "Kies niets" if self.gekozen else "Kies alles", self.alles_wissel,
                  kl=PANEEL)
        self.knop((20, H - 98, W - 40, 82), "Naar prullenbak (%d · %s)" % (len(self.gekozen), O.mooi(tot)),
                  self.weg, kl=ROOD_D, rand=ROOD)

    def wissel(self, p):
        self.gekozen ^= {p}

    def alles_wissel(self):
        alle = {p for p, g, t in self.lijst}
        self.gekozen = set() if self.gekozen >= alle else alle

    def weg(self):
        if not self.gekozen:
            return
        paden = list(self.gekozen)

        def ja():
            def werk():
                n, b = O.naar_prullenbak(paden)
                self.lijst = [x for x in self.lijst if x[0] not in self.gekozen]
                self.gekozen = set()
                self.meld("%s (%s) in de prullenbak." % (stuks(n), O.mooi(b)), 5)
                self.later(0, lambda: setattr(self, "opslag", droid.opslag()))
                self.stem.zeg(["c_prullenbak"])
            self.achtergrond("Verplaatsen...", werk)
        self.vraag = ("%s naar de prullenbak? Je kunt ze 30 dagen terugzetten." % stuks(len(paden)).capitalize(), ja)

    # ---- prullenbak
    def open_bak(self):
        self.bak, self.bak_gekozen = O.inhoud(), set()
        self.naar("bak")

    def scherm_bak(self):
        W, H = self.W, self.H
        self.kop("Prullenbak", "opslag")
        boven, onder = 104, H - 200
        if not self.bak:
            self.tekst("De prullenbak is leeg.", self.f, GROEN, W // 2, 180, midden=True)
            return
        v = self.venster
        oud = v.get_clip()
        v.set_clip(pygame.Rect(0, boven, W, onder - boven))
        y = boven + 4 - self.scroll
        rh = 96
        for naam, van, g, t in self.bak:
            if boven - rh < y < onder:
                r = pygame.Rect(16, y, W - 32, rh - 10)
                aan = naam in self.bak_gekozen
                pygame.draw.rect(v, BLAUW_D if aan else PANEEL, r, border_radius=12)
                vak = pygame.Rect(r.x + 14, r.y + 22, 40, 40)
                pygame.draw.rect(v, GROEN if aan else GRIJS, vak, 3, border_radius=8)
                if aan:
                    pygame.draw.lines(v, GROEN, False, [(vak.x + 8, vak.y + 20), (vak.x + 17, vak.y + 30),
                                                        (vak.x + 33, vak.y + 10)], 5)
                self.tekst(os.path.basename(van), self.f_mid, WIT, r.x + 68, r.y + 10, max_b=r.w - 80)
                over = max(0, O.DAGEN_BEWAREN - int((time.time() - t) / 86400))
                self.tekst("%s · nog %d dagen" % (O.mooi(g), over), self.f_klein, ZILVER, r.x + 68, r.y + 44)
                self.knoppen.append((r, lambda n=naam: self.bak_wissel(n)))
            y += rh
        v.set_clip(oud)
        self.max_scroll = max(0, len(self.bak) * rh - (onder - boven))
        half = (W - 52) // 2
        self.knop((20, H - 186, W - 40, 76), "Kies alles" if not self.bak_gekozen else "Kies niets",
                  self.bak_alles, kl=PANEEL)
        self.knop((20, H - 98, half, 82), "Terugzetten", self.bak_terug, kl=GROEN_D, rand=GROEN)
        self.knop((32 + half, H - 98, half, 82), "Echt weg", self.bak_weg, kl=ROOD_D, rand=ROOD)

    def bak_wissel(self, n):
        self.bak_gekozen ^= {n}

    def bak_alles(self):
        self.bak_gekozen = set() if self.bak_gekozen else {n for n, v, g, t in self.bak}

    def bak_terug(self):
        if self.bak_gekozen:
            n = O.terugzetten(list(self.bak_gekozen))
            self.meld("%s weer op de plek." % stuks(n).capitalize())
            self.stem.zeg(["c_terug"])
            self.open_bak()

    def bak_weg(self):
        if not self.bak_gekozen:
            return
        namen = list(self.bak_gekozen)

        def ja():
            n, b = O.definitief(namen)
            self.meld("%s echt verwijderd (%s vrij)." % (stuks(n).capitalize(), O.mooi(b)))
            self.opslag = droid.opslag()
            self.open_bak()
        self.vraag = ("%s ECHT verwijderen? Dit kan niet terug." % stuks(len(namen)).capitalize(), ja)

    # ---- batterij
    def scherm_batterij(self):
        W, H = self.W, self.H
        self.kop("Batterij")
        b = self.bat
        k, _ = self.oordeel_bat()
        y = 120
        n = b.get("niveau", -1)
        r = pygame.Rect(W // 2 - 90, y, 180, 300)
        pygame.draw.rect(self.venster, ZILVER, (r.centerx - 30, r.y - 18, 60, 22), border_radius=6)
        pygame.draw.rect(self.venster, ZILVER, r, 6, border_radius=20)
        if n >= 0:
            hh = int((r.h - 24) * n / 100)
            pygame.draw.rect(self.venster, KLEUR[k], (r.x + 12, r.bottom - 12 - hh, r.w - 24, hh), border_radius=12)
            self.tekst("%d%%" % n, self.f_reus, WIT, W // 2, r.centery - 40, midden=True)
        y = r.bottom + 30
        regels = [("Gezondheid", b.get("gezondheid", "?")),
                  ("Temperatuur", "%.1f °C" % b.get("temp", 0)),
                  ("Spanning", "%.2f V" % b.get("spanning", 0)),
                  ("Lader", "aangesloten" if b.get("laadt") else "niet aangesloten")]
        for a, w in regels:
            self.tekst(a, self.f, GRIJS, 30, y)
            self.tekst(w, self.f, WIT, W - 30, y, rechts=True)
            y += 50
        tip = "Tip: laad liefst tussen 20 en 80 procent, en laat de telefoon niet in de zon of onder je kussen liggen."
        if b.get("temp", 0) > 40:
            tip = "Je telefoon is warm. Leg hem even weg, uit de zon, en haal hem van de lader."
        for i, rr in enumerate(self.breek(tip, self.f_klein, W - 60)):
            self.tekst(rr, self.f_klein, BLAUW, 30, y + 10 + i * 30)
        self.knop((20, H - 98, W - 40, 82), "Opnieuw meten", lambda: setattr(self, "bat", droid.batterij()), kl=PANEEL)

    # ---- apps
    def scherm_apps(self):
        W, H = self.W, self.H
        self.kop("Apps")
        y = 104
        if not self._gebruik_ok:
            y = self.toegang_blok(y, "Om te zien wanneer je een app voor het laatst gebruikte en hoe groot hij is, "
                                     "heeft DraveCare 'Gebruikstoegang' nodig.", "Gebruikstoegang geven",
                                  lambda: (droid.vraag_gebruik(), self.stem.zeg(["c_toegang"])))
        if self.apps is None:
            self.tekst("Apps laden...", self.f, GEEL, W // 2, y + 30, midden=True)
            return
        lijst = sorted(self.apps, key=lambda a: (a["gebruikt"] or 0, a["naam"].lower()))
        self.tekst("Bovenaan: het langst niet gebruikt. Tik op een app.", self.f_mini, GRIJS, 24, y)
        boven, onder = y + 30, H - 20
        v = self.venster
        oud = v.get_clip()
        v.set_clip(pygame.Rect(0, boven, W, onder - boven))
        yy = boven - self.scroll
        rh = 100
        for a in lijst:
            if boven - rh < yy < onder:
                r = pygame.Rect(16, yy, W - 32, rh - 10)
                oud_ = a["gebruikt"] and time.time() - a["gebruikt"] > 90 * 86400
                pygame.draw.rect(v, PANEEL, r, border_radius=12)
                if oud_ or a["installeert"]:
                    pygame.draw.rect(v, GEEL, r, 3, border_radius=12)
                self.tekst(a["naam"], self.f_mid, WIT, r.x + 16, r.y + 10, max_b=r.w - 140)
                if a["grootte"]:
                    self.tekst(O.mooi(a["grootte"]), self.f_klein, ZILVER, r.right - 14, r.y + 12, rechts=True)
                self.tekst("Gebruikt: " + dagen_geleden(a["gebruikt"]), self.f_klein, GEEL if oud_ else ZILVER,
                           r.x + 16, r.y + 46)
                rechten = [naam for sl, naam in (("camera", "camera"), ("micro", "microfoon"), ("locatie", "locatie"))
                           if a[sl]]
                if rechten:
                    self.tekst(" · ".join(rechten), self.f_mini, BLAUW, r.right - 14, r.y + 50, rechts=True)
                self.knoppen.append((r, lambda a=a: self.open_app(a)))
            yy += rh
        v.set_clip(oud)
        self.max_scroll = max(0, len(lijst) * rh - (onder - boven))

    def open_app(self, a):
        self.app_open = a
        self.naar("app")

    def scherm_app(self):
        W, H = self.W, self.H
        a = self.app_open
        self.kop(a["naam"], "apps")
        y = 120
        regels = [("Laatst gebruikt", dagen_geleden(a["gebruikt"])),
                  ("Geïnstalleerd", time.strftime("%d-%m-%Y", time.localtime(a["sinds"])) if a["sinds"] else "?"),
                  ("Grootte", O.mooi(a["grootte"]) if a["grootte"] else "?"),
                  ("Camera", "ja" if a["camera"] else "nee"),
                  ("Microfoon", "ja" if a["micro"] else "nee"),
                  ("Locatie", "ja" if a["locatie"] else "nee"),
                  ("Mag apps installeren", "JA" if a["installeert"] else "nee")]
        for k, w in regels:
            self.tekst(k, self.f_mid, GRIJS, 30, y)
            self.tekst(w, self.f_mid, GEEL if w == "JA" else WIT, W - 30, y, rechts=True)
            y += 48
        self.tekst(a["pkg"], self.f_mini, GRIJS, 30, y + 6, max_b=W - 60)
        b = H - 290
        if a["installeert"]:
            self.knop((20, b - 96, W - 40, 82), "Apps installeren uitzetten", lambda: droid.open_onbekende_bronnen(a["pkg"]),
                      kl=PANEEL, rand=GEEL)
        self.knop((20, b, W - 40, 82), "Rechten en opslag (instellingen)", lambda: droid.open_app(a["pkg"]))
        self.knop((20, b + 96, W - 40, 82), "App verwijderen", lambda: (droid.verwijder_app(a["pkg"]),
                                                                       self._na_verwijderen()), kl=ROOD_D, rand=ROOD)
        self.knop((20, b + 192, W - 40, 82), "Terug naar de lijst", lambda: self.naar("apps"), kl=PANEEL)

    def _na_verwijderen(self):
        self.later(6, self._laad_apps)

    # ---- veiligheid
    def scherm_veilig(self):
        W, H = self.W, self.H
        self.kop("Veiligheid")
        v = self.veilig
        y = 110
        self.tekst("%s · Android %s" % (v.get("model", ""), v.get("android", "")), self.f_klein, GRIJS, 24, y,
                   max_b=W - 48)
        y += 44
        for k, t, knop in self.veilig_punten():
            pygame.draw.circle(self.venster, KLEUR[k], (40, y + 16), 13)
            regels = self.breek(t, self.f_klein, W - 90)
            for i, r in enumerate(regels):
                self.tekst(r, self.f_klein, WIT, 66, y + i * 30)
            y += len(regels) * 30 + 10
            if knop:
                self.knop((66, y, W - 86, 66), knop[0], knop[1], kl=PANEEL, font=self.f_mid)
                y += 80
            y += 12

    # ---- back-up (de pc doet het werk via DraveGuard; hier zie je het en vraag je erom)
    def _bk_pad(self, naam):
        return os.path.join(droid.OPSLAG, "DraveCare", naam)

    def backup_info(self):
        """(tekst, tijd) van de laatste back-up die DraveGuard hier achterliet."""
        try:
            with open(self._bk_pad("laatste_backup.txt"), encoding="utf-8") as f:
                t = f.read().strip()
            dag = t.split("|")[0].strip()
            tijd = time.mktime(time.strptime(dag, "%d-%m-%Y %H:%M"))
            return t, tijd
        except Exception:
            return "", 0

    def verzoek_open(self):
        return os.path.exists(self._bk_pad("backup_verzoek.txt"))

    def oordeel_backup(self):
        t, tijd = self.backup_info()
        if self.verzoek_open():
            return "letop", "Gevraagd · wacht op de pc"
        if not tijd:
            return "slecht", "Nog nooit gemaakt"
        d = max(0, int((time.time() - tijd) // 86400))
        k = "goed" if d <= 14 else "letop" if d <= 45 else "slecht"
        return k, "Laatste: " + ("vandaag" if d == 0 else "gisteren" if d == 1 else "%d dagen geleden" % d)

    def vraag_backup(self):
        try:
            os.makedirs(os.path.dirname(self._bk_pad("x")), exist_ok=True)
            with open(self._bk_pad("backup_verzoek.txt"), "w", encoding="utf-8") as f:
                f.write(time.strftime("%d-%m-%Y %H:%M"))
            self.meld("Gevraagd! DraveGuard op de pc begint zodra hij openstaat en je telefoon verbonden is.", 6)
        except Exception as e:
            self.meld("Dat lukte niet: %s" % e, 6)

    def trek_in(self):
        try:
            os.remove(self._bk_pad("backup_verzoek.txt"))
        except Exception:
            pass

    def scherm_backup(self):
        W, H = self.W, self.H
        self.kop("Back-up")
        y = 110
        if not self._bestanden_ok:
            y = self.toegang_blok(y, "Om de back-up te kunnen bijhouden heeft DraveCare toegang tot je bestanden "
                                     "nodig.", "Toegang geven", self._vraag_bestanden)
        k, kort = self.oordeel_backup()
        t, tijd = self.backup_info()
        pygame.draw.circle(self.venster, KLEUR[k], (40, y + 18), 15)
        self.tekst(kort, self.f, WIT, 70, y, max_b=W - 90)
        y += 54
        if t:
            for r in self.breek(t.replace("|", "·"), self.f_klein, W - 60)[:4]:
                self.tekst(r, self.f_klein, ZILVER, 30, y)
                y += 30
        y += 16
        uitleg = ("De back-up wordt op je pc gemaakt door DraveGuard (tabblad Telefoon → Back-up): je "
                  "telefoonnummers, je sms'jes en al je foto's, video's en andere bestanden, ook van de SD-kaart. "
                  "Alleen wat nieuw is wordt gekopieerd. Er gaat niets weg van je telefoon.")
        for r in self.breek(uitleg, self.f_klein, W - 60):
            self.tekst(r, self.f_klein, ZILVER, 30, y)
            y += 30
        y += 10
        tip = "Zorg dat DraveGuard op de pc openstaat en dat Draadloze foutopsporing aan staat."
        for r in self.breek(tip, self.f_klein, W - 60):
            self.tekst(r, self.f_klein, BLAUW, 30, y)
            y += 30
        if self.verzoek_open():
            self.knop((20, H - 196, W - 40, 82), "Verzoek intrekken", self.trek_in, kl=PANEEL)
        else:
            self.knop((20, H - 196, W - 40, 82), "Back-up naar pc", self.vraag_backup, kl=GROEN_D, rand=GROEN)
        self.knop((20, H - 98, W - 40, 82), "Vernieuwen", lambda: None, kl=PANEEL)

    # ------------------------------------------------------------ algemeen
    def teken(self):
        self.venster.fill(ZWART)
        self.knoppen = []
        getattr(self, "scherm_" + self.scherm)()
        W, H = self.W, self.H
        if self.bezig and self.scherm not in ("lijst",):
            self.tekst(self.bezig, self.f_mid, GEEL, W // 2, H - 240, midden=True)
        if self.vraag:
            self.knoppen = []
            s = pygame.Surface((W, H), pygame.SRCALPHA)
            s.fill((0, 0, 0, 200))
            self.venster.blit(s, (0, 0))
            r = pygame.Rect(24, H // 2 - 200, W - 48, 380)
            pygame.draw.rect(self.venster, PANEEL, r, border_radius=18)
            pygame.draw.rect(self.venster, GEEL, r, 3, border_radius=18)
            for i, rr in enumerate(self.breek(self.vraag[0], self.f, r.w - 40)[:5]):
                self.tekst(rr, self.f, WIT, r.centerx, r.y + 30 + i * 40, midden=True)
            ja = self.vraag[1]
            self.knop((r.x + 20, r.bottom - 110, (r.w - 60) // 2, 86), "Ja", lambda: (setattr(self, "vraag", None), ja()),
                      kl=GROEN_D, rand=GROEN)
            self.knop((r.centerx + 10, r.bottom - 110, (r.w - 60) // 2, 86), "Nee",
                      lambda: setattr(self, "vraag", None), kl=ROOD_D, rand=ROOD)
        if self.melding:
            t, tot = self.melding
            if time.time() > tot:
                self.melding = None
            else:
                regels = self.breek(t, self.f_mid, W - 80)
                hh = 30 + len(regels) * 32
                r = pygame.Rect(20, H - 120 - hh, W - 40, hh)
                pygame.draw.rect(self.venster, BLAUW_D, r, border_radius=14)
                pygame.draw.rect(self.venster, BLAUW, r, 3, border_radius=14)
                for i, rr in enumerate(regels):
                    self.tekst(rr, self.f_mid, WIT, r.centerx, r.y + 15 + i * 32, midden=True)
        pygame.display.flip()

    def klik(self, pos):
        for r, actie in reversed(self.knoppen):
            if r.collidepoint(pos):
                actie()
                return

    def terug(self):
        if self.vraag:
            self.vraag = None
        elif self.scherm == "start":
            self.stop = True
        elif self.scherm in ("lijst", "bak"):
            self.naar("opslag")
        elif self.scherm == "app":
            self.naar("apps")
        else:
            self.naar("start")

    def run(self):
        while not self.stop:
            self.klok.tick(30)
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.stop = True
                elif e.type == pygame.KEYDOWN and e.key in (pygame.K_AC_BACK, pygame.K_ESCAPE):
                    self.terug()
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    self.sleep = (e.pos, self.scroll, False)
                elif e.type == pygame.MOUSEMOTION and self.sleep and e.buttons[0]:
                    (sx, sy), s0, _ = self.sleep
                    if abs(e.pos[1] - sy) > 20 and self.scherm in ("lijst", "bak", "apps"):
                        self.scroll = max(0, min(self.max_scroll, s0 - (e.pos[1] - sy)))
                        self.sleep = ((sx, sy), s0, True)
                elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
                    if self.sleep and not self.sleep[2]:
                        self.klik(e.pos)
                    self.sleep = None
                elif e.type == getattr(pygame, "APP_WILLENTERFOREGROUND", -1) or \
                        e.type == getattr(pygame, "WINDOWFOCUSGAINED", -2):
                    self.lees_alles()          # terug uit de instellingen: opnieuw kijken
                    if self.scherm in ("apps", "app", "start"):
                        self.later(0.5, self._laad_apps)
            nu = time.time()
            klaar = [t for t in self.taken if t[0] <= nu]
            if klaar:
                self.taken = [t for t in self.taken if t[0] > nu]
                for _, fn in klaar:
                    try:
                        fn()
                    except Exception:
                        pass
            droid.scan_flush()
            self.stem.update()
            self.teken()
        pygame.quit()


def main():
    app = App()
    app.stem.zeg(["c_welkom"])
    app.run()


if __name__ == "__main__":
    main()
