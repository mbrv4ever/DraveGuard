# -*- coding: utf-8 -*-
"""DraveGuard - tabblad 'Telefoon' (DraveCare, pc-kant via adb).

Eerst kijken, dan pas na jouw klik iets doen. Bestanden gaan naar D: (zelf te kiezen).
Dravenlock (Roger & Claudio).
"""
from __future__ import annotations

import os
import time

from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtGui import QDesktopServices, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QLineEdit, QTextEdit,
    QCheckBox, QFileDialog, QMessageBox, QTableWidgetItem, QHeaderView, QGridLayout)

import telefoon as TF
from onderhoud_ui import Klus, _tabel

NL = True
GOED, LETOP, SLECHT, ACC2 = "#57d98a", "#ffd166", "#ff6b6b", "#b59cff"
KL = {"goed": GOED, "letop": LETOP, "slecht": SLECHT}


def L(nl, en):
    return nl if NL else en


def _std_doel():
    for d in ("D:\\", "F:\\", "E:\\"):
        if os.path.isdir(d):
            return os.path.join(d, "DraveCare", "Telefoon")
    return os.path.join(os.path.expanduser("~"), "DraveCare", "Telefoon")


class TelefoonTab(QWidget):
    def __init__(self, g):
        super().__init__()
        self.g = g
        self.klussen = []
        self._stop = False
        db = g.db
        self.adb = TF.Adb(db.get_meta("tel_adb", ""), db.get_meta("tel_adres", ""))
        self.doel = db.get_meta("tel_doel", "") or _std_doel()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)
        t = QLabel("📱  " + L("Telefoon — DraveCare", "Phone — DraveCare"))
        t.setObjectName("h2")
        lay.addWidget(t)
        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("font-size:18px;")
        lay.addWidget(self.lbl_status)

        self.sub = QTabWidget()
        self.sub.addTab(self._p_verbind(), L("1 · Verbinden", "1 · Connect"))
        self.sub.addTab(self._p_bestanden(), L("2 · Bestanden naar pc", "2 · Files to PC"))
        self.sub.addTab(self._p_backup(), L("3 · Back-up", "3 · Backup"))
        self.sub.addTab(self._p_opruimen(), L("4 · Opruimen", "4 · Clean up"))
        self.sub.addTab(self._p_batterij(), L("5 · Batterij", "5 · Battery"))
        self.sub.addTab(self._p_apps(), L("6 · Apps", "6 · Apps"))
        self.sub.addTab(self._p_controle(), L("7 · Volledige controle", "7 · Full check"))
        lay.addWidget(self.sub, 1)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(170)
        self.log.setStyleSheet("font-size:16px;")
        lay.addWidget(self.log)
        self.lbl_status.setText(L('Telefoon zoeken…', 'Looking for phone…'))
        QTimer.singleShot(1200, self._auto)
        # Vraagt DraveCare op de telefoon om een back-up? Dan kijken we elke halve minuut. (28-10-2026)
        self._bk_bezig = False
        self._verzoek_timer = QTimer(self)
        self._verzoek_timer.timeout.connect(self._kijk_verzoek)
        self._verzoek_timer.start(30000)

    # ------------------------------------------------ hulp
    def say(self, s):
        self.log.append(s)

    def _auto(self):
        """Bij het openen: stil verbinden met het laatst gebruikte adres (in de achtergrond)."""
        oud_adres = self.adb.adres
        def werk(say):
            if self.adb.adres and not self.adb.verbonden():
                self.adb.verbind_slim(say)
            return None
        def klaar(r):
            if self.adb.adres and self.adb.adres != oud_adres and self.adb.verbonden():
                self.g.db.set_meta("tel_adres", self.adb.adres)
                try:
                    self.ed_adres.setText(self.adb.adres)
                except Exception:
                    pass
                self.say(L("✔ Telefoon gevonden op de nieuwe poort: ", "✔ Phone found on new port: ") + self.adb.adres)
            self._status()
        self.klus(werk, klaar)

    def klus(self, fn, klaar=None):
        k = Klus(fn)
        k.regel.connect(self.say)
        if klaar:
            k.klaar.connect(klaar)
        k.klaar.connect(lambda _r, k=k: self.klussen.remove(k) if k in self.klussen else None)
        self.klussen.append(k)
        k.start()

    def _fout(self, r):
        if isinstance(r, Exception):
            self.say("⚠ " + str(r))
            return True
        return False

    def _status(self):
        try:
            ok = self.adb.verbonden()
        except Exception as e:
            ok = False
            self.lbl_status.setText("⚠ " + str(e))
            self.lbl_status.setStyleSheet("font-size:18px; color:%s;" % SLECHT)
            return
        if ok:
            self.lbl_status.setText(L("✔ Telefoon verbonden: ", "✔ Phone connected: ") + self.adb.adres)
            self.lbl_status.setStyleSheet("font-size:18px; color:%s;" % GOED)
        else:
            self.lbl_status.setText(L("✖ Geen telefoon verbonden — ga naar ‘1 · Verbinden’.",
                                      "✖ No phone connected — go to ‘1 · Connect’."))
            self.lbl_status.setStyleSheet("font-size:18px; color:%s;" % LETOP)

    def _uitleg(self, lay, tekst):
        u = QLabel(tekst)
        u.setWordWrap(True)
        u.setStyleSheet("font-size:16px;")
        lay.addWidget(u)

    # ------------------------------------------------ 1 verbinden
    def _p_verbind(self):
        w = QWidget(); lay = QVBoxLayout(w)
        self._uitleg(lay, L(
            "Zet op je telefoon aan: Instellingen → Systeem → Ontwikkelaarsopties → Draadloze foutopsporing. "
            "Daar staat ‘IP-adres en poort’, bijvoorbeeld 192.168.2.4:39231. Na een herstart van de telefoon "
            "verandert de poort — dan vul je hem hier opnieuw in.\n"
            "Eerste keer? Tik daar op ‘Apparaat koppelen met koppelingscode’ en vul hieronder het koppel-adres "
            "en de code in.",
            "On your phone: Settings → System → Developer options → Wireless debugging. Use the 'IP address & "
            "port' shown there. First time? Use 'Pair device with pairing code' and fill in below."))
        r = QHBoxLayout()
        r.addWidget(QLabel(L("Adres:poort", "Address:port")))
        self.ed_adres = QLineEdit(self.adb.adres)
        self.ed_adres.setPlaceholderText("192.168.2.4:39231")
        self.ed_adres.setMinimumHeight(44)
        r.addWidget(self.ed_adres, 1)
        r.addWidget(self.g._btn("🔗  " + L("Verbinden", "Connect"), self.verbind))
        lay.addLayout(r)
        r2 = QHBoxLayout()
        r2.addWidget(QLabel(L("Koppel-adres", "Pair address")))
        self.ed_paar = QLineEdit(); self.ed_paar.setMinimumHeight(44)
        self.ed_paar.setPlaceholderText("192.168.2.4:37011")
        r2.addWidget(self.ed_paar, 1)
        r2.addWidget(QLabel(L("Code", "Code")))
        self.ed_code = QLineEdit(); self.ed_code.setMaximumWidth(140); self.ed_code.setMinimumHeight(44)
        r2.addWidget(self.ed_code)
        r2.addWidget(self.g._btn(L("Koppelen", "Pair"), self.koppel, ghost=True))
        lay.addLayout(r2)
        r3 = QHBoxLayout()
        self.lbl_adb = QLabel("adb: " + (self.adb.pad or L("niet gevonden", "not found")))
        self.lbl_adb.setStyleSheet("color:%s; font-size:15px;" % ACC2)
        r3.addWidget(self.lbl_adb, 1)
        r3.addWidget(self.g._btn(L("adb.exe kiezen…", "Choose adb.exe…"), self.kies_adb, ghost=True))
        lay.addLayout(r3)
        self.lbl_toestel = QLabel("")
        self.lbl_toestel.setStyleSheet("font-size:18px;")
        self.lbl_toestel.setWordWrap(True)
        lay.addWidget(self.lbl_toestel)
        lay.addStretch()
        return w

    def kies_adb(self):
        f, _ = QFileDialog.getOpenFileName(self, "adb.exe", "", "adb.exe (adb.exe)")
        if f:
            self.g.db.set_meta("tel_adb", f)
            self.adb.pad = f
            self.lbl_adb.setText("adb: " + f)

    def _w_verbind(self, say):
        say(self.adb.verbind(self.ed_adres.text()))
        time.sleep(1)
        if not self.adb.verbonden():
            return None
        return self.adb.info()

    def verbind(self):
        if not self.ed_adres.text().strip():
            return
        self.say(L("Verbinden met ", "Connecting to ") + self.ed_adres.text().strip() + " …")
        def klaar(r):
            if self._fout(r):
                return
            self._status()
            if r:
                self.g.db.set_meta("tel_adres", self.adb.adres)
                self.lbl_toestel.setText("📱 %s %s · Android %s · %s %s" % (
                    r["merk"], r["model"], r["android"], L("beveiligingsupdate", "security patch"), r["patch"]))
        self.klus(self._w_verbind, klaar)

    def koppel(self):
        a, c = self.ed_paar.text().strip(), self.ed_code.text().strip()
        if a and c:
            self.klus(lambda say: say(self.adb.koppel(a, c)))

    # ------------------------------------------------ 2 bestanden
    def _p_bestanden(self):
        w = QWidget(); lay = QVBoxLayout(w)
        self._uitleg(lay, L(
            "Vink aan welke mappen je naar de pc wilt halen. Alleen NIEUWE bestanden worden gekopieerd; "
            "wat er al staat wordt overgeslagen. Er wordt NIETS van je telefoon verwijderd.",
            "Tick the folders to copy to the PC. Only NEW files are copied. Nothing is removed from your phone."))
        self.vinkjes = []
        grid = QGridLayout()
        for i, (naam, pad) in enumerate(TF.MAPPEN):
            cb = QCheckBox(naam)
            cb.setStyleSheet("font-size:17px; padding:4px;")
            cb.setToolTip(pad)
            cb.setChecked(pad in ("/sdcard/DCIM/Camera", "/sdcard/Pictures/Screenshots"))
            grid.addWidget(cb, i // 2, i % 2)
            self.vinkjes.append((cb, naam, pad))
        lay.addLayout(grid)
        r = QHBoxLayout()
        self.lbl_doel = QLabel(L("Naar: ", "To: ") + self.doel)
        self.lbl_doel.setStyleSheet("font-size:17px;")
        r.addWidget(self.lbl_doel, 1)
        r.addWidget(self.g._btn(L("Andere map…", "Other folder…"), self.kies_doel, ghost=True))
        r.addWidget(self.g._btn(L("Map openen", "Open folder"), lambda: self._open(self.doel), ghost=True))
        lay.addLayout(r)
        r2 = QHBoxLayout()
        r2.addWidget(self.g._btn("📏  " + L("Groottes bekijken", "Show sizes"), self.groottes, ghost=True))
        r2.addWidget(self.g._btn("⬇  " + L("Ophalen naar pc", "Copy to PC"), self.ophalen))
        r2.addWidget(self.g._btn(L("Stop", "Stop"), self.stop, ghost=True))
        lay.addLayout(r2)
        lay.addStretch()
        return w

    def kies_doel(self):
        d = QFileDialog.getExistingDirectory(self, L("Kies de map", "Choose folder"), self.doel)
        if d:
            if d[:2].upper() == "C:":
                QMessageBox.information(self, "DraveGuard", L(
                    "Liever niet op C: — kies een map op D: of een andere schijf.",
                    "Better not on C: — choose a folder on another drive."))
                return
            self.doel = d
            self.g.db.set_meta("tel_doel", d)
            self.lbl_doel.setText(L("Naar: ", "To: ") + d)

    def _open(self, pad):
        os.makedirs(pad, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(pad))

    def stop(self):
        self._stop = True

    def _gekozen(self):
        return [(n, p) for cb, n, p in self.vinkjes if cb.isChecked()]

    def groottes(self):
        keuze = [(n, p) for cb, n, p in self.vinkjes]
        def werk(say):
            for n, p in keuze:
                g = self.adb.map_grootte(p)
                say("  %-28s %s" % (n, TF.mooi(g) if g >= 0 else L("(bestaat niet)", "(missing)")))
        self.say(L("Groottes op de telefoon:", "Sizes on the phone:"))
        self.klus(werk, lambda r: self._fout(r))

    def ophalen(self):
        keuze = self._gekozen()
        if not keuze:
            return
        self._stop = False
        doel = self.doel
        def werk(say):
            tn = to = tb = 0
            for n, p in keuze:
                say("▶ " + n)
                dm = os.path.join(doel, n.split(" (")[0])
                a, b, c = self.adb.ophalen(p, dm, say, lambda: self._stop)
                say("  %d nieuw, %d stonden er al (%s)" % (a, b, TF.mooi(c)))
                tn, to, tb = tn + a, to + b, tb + c
                if self._stop:
                    break
            say(L("✔ Klaar: %d nieuwe bestanden (%s) in %s", "✔ Done: %d new files (%s) in %s") %
                (tn, TF.mooi(tb), doel))
        self.klus(werk, lambda r: self._fout(r))

    # ------------------------------------------------ 3 back-up
    def _p_backup(self):
        w = QWidget(); lay = QVBoxLayout(w)
        self._uitleg(lay, L(
            "Een back-up van je telefoon op de pc. Je telefoonnummers worden een contactenbestand (.vcf) "
            "dat je op elke telefoon weer kunt inlezen. Je sms'jes worden een leesbaar overzicht. "
            "Van je bestanden komt alleen wat NIEUW of veranderd is. Er wordt NIETS van je telefoon verwijderd.",
            "A backup of your phone on the PC. Contacts become a .vcf file you can import on any phone, "
            "text messages a readable overview, files only what is new or changed. Nothing is removed."))
        self.b_vink = {}
        grid = QGridLayout()
        keuzes = [("contacten", L("📇  Contacten (telefoonnummers)", "📇  Contacts (phone numbers)"), True),
                  ("sms", L("💬  Berichten (sms)", "💬  Text messages (SMS)"), True),
                  ("intern", L("📱  Alle bestanden op de telefoon", "📱  All files on the phone"), True),
                  ("sd", L("💾  SD-kaart (als die erin zit)", "💾  SD card (if present)"), True)]
        for i, (k, naam, aan) in enumerate(keuzes):
            cb = QCheckBox(naam)
            cb.setStyleSheet("font-size:18px; padding:5px;")
            cb.setChecked(aan)
            grid.addWidget(cb, i // 2, i % 2)
            self.b_vink[k] = cb
        lay.addLayout(grid)
        self.lbl_laatste = QLabel("")
        self.lbl_laatste.setStyleSheet("font-size:18px; color:%s;" % ACC2)
        lay.addWidget(self.lbl_laatste)
        self._toon_laatste()
        r = QHBoxLayout()
        r.addWidget(self.g._btn("🛟  " + L("Back-up maken", "Make backup"), self.backup))
        r.addWidget(self.g._btn(L("Map openen", "Open folder"),
                                lambda: self._open(os.path.join(self.doel, "Back-up")), ghost=True))
        r.addWidget(self.g._btn(L("Stop", "Stop"), self.stop, ghost=True))
        lay.addLayout(r)
        t2 = QLabel("↩  " + L("Terugzetten naar de telefoon", "Restore to the phone"))
        t2.setStyleSheet("font-size:20px; font-weight:bold; color:%s; margin-top:12px;" % ACC2)
        lay.addWidget(t2)
        self._uitleg(lay, L(
            "Bestanden: alleen wat op de telefoon ONTBREEKT wordt teruggezet; wat er al staat blijft zoals het is. "
            "Contacten: het bestand komt in Download op je telefoon en de app Contacten gaat open. Kies daar "
            "Instellingen (of ⋮) → Importeren → .vcf-bestand. Let op: contacten die er al staan kunnen dan dubbel "
            "komen. Sms'jes kunnen niet terug (dat mag alleen de berichten-app), maar het overzicht blijft leesbaar.",
            "Files: only what is MISSING on the phone is restored. Contacts: the file goes to Download and the "
            "Contacts app opens; choose Import → .vcf file. Existing contacts may be doubled. Texts cannot be restored."))
        r3 = QHBoxLayout()
        r3.addWidget(self.g._btn("📱  " + L("Bestanden terugzetten", "Restore files"), self.terug_bestanden))
        r3.addWidget(self.g._btn("📇  " + L("Contacten terugzetten", "Restore contacts"), self.terug_contacten))
        lay.addLayout(r3)
        self._uitleg(lay, L(
            "De binnenkant van apps (zoals WhatsApp-gesprekken) laat Android door geen enkele app kopiëren; "
            "daarvoor heeft WhatsApp zijn eigen back-up.",
            "Android does not let any app copy the inside of other apps (like WhatsApp chats)."))
        lay.addStretch()
        return w

    def terug_bestanden(self):
        if self._bk_bezig:
            return
        basis = os.path.join(self.doel, "Back-up")
        keuzes = [(n, os.path.join(basis, n)) for n in ("Telefoon", "SD-kaart")
                  if os.path.isdir(os.path.join(basis, n))]
        if not keuzes:
            QMessageBox.information(self, "DraveGuard", L("Er is nog geen back-up met bestanden.",
                                                          "There is no file backup yet."))
            return
        naam, pc_map = keuzes[0]
        if len(keuzes) > 1:
            k = QMessageBox.question(self, "DraveGuard", L(
                "Welke back-up wil je terugzetten?\n\nJa = Telefoon (intern geheugen)\nNee = SD-kaart",
                "Which backup?\n\nYes = Phone (internal)\nNo = SD card"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
            if k == QMessageBox.StandardButton.Cancel:
                return
            naam, pc_map = keuzes[0] if k == QMessageBox.StandardButton.Yes else keuzes[1]
        if QMessageBox.question(self, "DraveGuard", L(
                "Bestanden uit ‘%s’ terugzetten naar je telefoon?\n\nAlleen wat op de telefoon ontbreekt wordt "
                "gekopieerd. Er wordt niets overschreven of verwijderd." % naam,
                "Restore files from ‘%s’ to your phone?\nOnly missing files are copied." % naam)) \
                != QMessageBox.StandardButton.Yes:
            return
        self._stop = False
        self._bk_bezig = True
        def werk(say):
            if naam == "SD-kaart":
                kaarten = self.adb.sd_kaarten()
                if not kaarten:
                    raise RuntimeError(L("Er zit geen SD-kaart in de telefoon.", "No SD card in the phone."))
                pad = kaarten[0]
            else:
                pad = "/storage/emulated/0"
            say("▶ " + L("Terugzetten naar ", "Restoring to ") + pad)
            a, b, c, fout = self.adb.terug_bestanden(pc_map, pad, say, lambda: self._stop)
            say(L("✔ Klaar: %d teruggezet (%s), %d stonden er al%s", "✔ Done: %d restored (%s), %d already there%s")
                % (a, TF.mooi(c), b, (L(", %d lukten niet", ", %d failed") % fout) if fout else ""))
        def klaar(r):
            self._bk_bezig = False
            self._fout(r)
        self.klus(werk, klaar)

    def terug_contacten(self):
        m = os.path.join(self.doel, "Back-up", "Contacten")
        vcfs = sorted([f for f in os.listdir(m) if f.lower().endswith(".vcf")]) if os.path.isdir(m) else []
        start = os.path.join(m, vcfs[-1]) if vcfs else self.doel
        pad, _ = QFileDialog.getOpenFileName(self, L("Kies het contactenbestand", "Choose the contacts file"),
                                             start, "Contacten (*.vcf)")
        if not pad:
            return
        if QMessageBox.question(self, "DraveGuard", L(
                "Dit contactenbestand op je telefoon zetten?\n\n%s\n\nDaarna gaat de app Contacten open. Kies daar "
                "Importeren → .vcf-bestand → %s.\nLet op: contacten die er al staan kunnen dubbel komen."
                % (os.path.basename(pad), os.path.basename(pad)),
                "Put this contacts file on your phone?\nThen choose Import → .vcf in Contacts.")) \
                != QMessageBox.StandardButton.Yes:
            return
        def werk(say):
            doel = self.adb.contacten_klaarzetten(pad)
            say(L("✔ Op je telefoon gezet: %s — kies nu in Contacten: Importeren → .vcf-bestand.",
                  "✔ Placed on your phone: %s — now choose Import → .vcf in Contacts.") % doel)
        self.klus(werk, lambda r: self._fout(r))

    def _kijk_verzoek(self):
        if self._bk_bezig or not self.adb.adres:
            return
        def werk(say):
            if not self.adb.verbonden():
                return False
            out = self.adb.sh("ls /sdcard/DraveCare/backup_verzoek.txt 2>/dev/null", timeout=15)
            if "backup_verzoek.txt" not in out or "No such" in out:
                return False
            self.adb.sh("rm -f /sdcard/DraveCare/backup_verzoek.txt", timeout=15)
            return True
        def klaar(r):
            if r is True and not self._bk_bezig:
                self.say("📱 " + L("DraveCare op je telefoon vraagt om een back-up — ik begin.",
                                   "DraveCare on your phone asks for a backup — starting."))
                self.sub.setCurrentIndex(2)
                self.backup()
        k = Klus(werk)
        k.klaar.connect(klaar)
        k.klaar.connect(lambda _r, k=k: self.klussen.remove(k) if k in self.klussen else None)
        self.klussen.append(k)
        k.start()

    def _toon_laatste(self):
        t = self.g.db.get_meta("tel_laatste_backup", "")
        self.lbl_laatste.setText(L("Laatste back-up: ", "Last backup: ") + (t or L("nog nooit", "never")))

    def backup(self):
        wat = {k for k, cb in self.b_vink.items() if cb.isChecked()}
        if not wat or self._bk_bezig:
            return
        self._stop = False
        basis = os.path.join(self.doel, "Back-up")
        if basis[:2].upper() == "C:":
            QMessageBox.information(self, "DraveGuard", L(
                "De back-up gaat liever niet op C:. Kies bij ‘2 · Bestanden naar pc’ een map op D:.",
                "Better not on C:. Choose a folder on D: under ‘2 · Files to PC’."))
            return
        def werk(say):
            dag = time.strftime("%Y-%m-%d")
            sam = []
            contacten = []
            if "contacten" in wat or "sms" in wat:
                say("▶ " + L("Contacten lezen…", "Reading contacts…"))
                contacten = self.adb.contacten()
            if "contacten" in wat:
                if contacten:
                    m = os.path.join(basis, "Contacten"); os.makedirs(m, exist_ok=True)
                    pad = os.path.join(m, "contacten_%s.vcf" % dag)
                    with open(pad, "w", encoding="utf-8", newline="") as f:
                        f.write(TF.maak_vcf(contacten))
                    n = sum(len(c["tel"]) for c in contacten)
                    say(L("  ✔ %d contacten, %d telefoonnummers → %s", "  ✔ %d contacts, %d numbers → %s")
                        % (len(contacten), n, pad))
                    sam.append(L("%d contacten", "%d contacts") % len(contacten))
                else:
                    say(L("  ⚠ Geen contacten gevonden.", "  ⚠ No contacts found."))
            if "sms" in wat and not self._stop:
                say("▶ " + L("Berichten lezen…", "Reading messages…"))
                b = self.adb.berichten()
                if b:
                    m = os.path.join(basis, "Berichten"); os.makedirs(m, exist_ok=True)
                    pad = TF.berichten_html(b, contacten, os.path.join(m, "berichten_%s.html" % dag))
                    say(L("  ✔ %d berichten → %s", "  ✔ %d messages → %s") % (len(b), pad))
                    sam.append(L("%d sms", "%d texts") % len(b))
                else:
                    say(L("  (geen sms'jes gevonden of geen toegang)", "  (no messages or no access)"))
            plekken = []
            if "intern" in wat:
                plekken.append(("/storage/emulated/0", os.path.join(basis, "Telefoon")))
            if "sd" in wat:
                kaarten = self.adb.sd_kaarten()
                if not kaarten:
                    say(L("  (geen SD-kaart in de telefoon)", "  (no SD card in the phone)"))
                for i, k in enumerate(kaarten, 1):
                    plekken.append((k, os.path.join(basis, "SD-kaart" + ("" if i == 1 else " %d" % i))))
            for pad, doel in plekken:
                if self._stop:
                    break
                say("▶ " + L("Bestanden op een rij zetten: ", "Listing files: ") + pad)
                lijst = self.adb.bestanden_alles(pad)
                say(L("  %d bestanden (%s). Alleen nieuwe worden gekopieerd…", "  %d files (%s). Copying new ones…")
                    % (len(lijst), TF.mooi(sum(g for _, g in lijst))))
                a, b2, c, fout = self.adb.ophalen_lijst(pad, lijst, doel, say, lambda: self._stop)
                say(L("  ✔ %d nieuw (%s), %d stonden er al%s", "  ✔ %d new (%s), %d already there%s")
                    % (a, TF.mooi(c), b2, (L(", %d lukten niet", ", %d failed") % fout) if fout else ""))
                sam.append(L("%d nieuwe bestanden", "%d new files") % a)
            if self._stop:
                say(L("Gestopt — wat al gekopieerd is, blijft staan.", "Stopped — copied files stay."))
                return None
            nu = time.strftime("%d-%m-%Y %H:%M")
            try:
                self.adb.zet_backup_merk(nu + " | " + ", ".join(sam))
            except Exception:
                pass
            say(L("✔ Back-up klaar: ", "✔ Backup done: ") + ", ".join(sam) + "  →  " + basis)
            return nu
        self._bk_bezig = True
        def klaar(r):
            self._bk_bezig = False
            if self._fout(r):
                return
            if r:
                self.g.db.set_meta("tel_laatste_backup", r)
                self._toon_laatste()
        self.klus(werk, klaar)

    # ------------------------------------------------ 4 opruimen
    def _p_opruimen(self):
        w = QWidget(); lay = QVBoxLayout(w)
        self._uitleg(lay, L(
            "Caches zijn tijdelijke bestanden die apps zelf weer aanmaken. Opruimen is veilig: je verliest geen "
            "foto's, berichten of instellingen. Apps kunnen de eerste keer daarna iets trager starten.",
            "Caches are temporary files apps recreate. Clearing is safe: no photos, messages or settings are lost."))
        self.lbl_opslag = QLabel("")
        self.lbl_opslag.setStyleSheet("font-size:19px;")
        lay.addWidget(self.lbl_opslag)
        r = QHBoxLayout()
        r.addWidget(self.g._btn("📊  " + L("Opslag bekijken", "Show storage"), self.opslag, ghost=True))
        r.addWidget(self.g._btn("🧹  " + L("Alle caches opruimen", "Clear all caches"), self.caches))
        r.addWidget(self.g._btn("🔎  " + L("Grote bestanden zoeken", "Find large files"), self.groot, ghost=True))
        lay.addLayout(r)
        self.tb_groot = _tabel([L("Bestand op telefoon", "File on phone"), L("Grootte", "Size")])
        self.tb_groot.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.tb_groot, 1)
        return w

    def opslag(self):
        def klaar(r):
            if self._fout(r):
                return
            tot, geb = r
            if tot:
                pct = 100 * geb / tot
                k = SLECHT if pct > 90 else LETOP if pct > 75 else GOED
                self.lbl_opslag.setText(L("Opslag: %d%% vol — %s gebruikt van %s, %s vrij",
                                          "Storage: %d%% full — %s of %s used, %s free") %
                                        (pct, TF.mooi(geb), TF.mooi(tot), TF.mooi(tot - geb)))
                self.lbl_opslag.setStyleSheet("font-size:19px; color:%s;" % k)
        self.klus(lambda say: self.adb.opslag(), klaar)

    def caches(self):
        if QMessageBox.question(self, "DraveGuard", L("Alle app-caches op de telefoon opruimen?",
                                                      "Clear all app caches on the phone?")) \
                != QMessageBox.StandardButton.Yes:
            return
        self.klus(lambda say: self.adb.caches_opruimen(say), lambda r: (self._fout(r), self.opslag()))

    def groot(self):
        self.say(L("Grote bestanden zoeken (groter dan 50 MB)…", "Searching large files (>50 MB)…"))
        def klaar(r):
            if self._fout(r):
                return
            self.tb_groot.setRowCount(0)
            for n, g in r:
                i = self.tb_groot.rowCount(); self.tb_groot.insertRow(i)
                self.tb_groot.setItem(i, 0, QTableWidgetItem(n))
                self.tb_groot.setItem(i, 1, QTableWidgetItem(TF.mooi(g)))
            self.say(L("%d grote bestanden gevonden. Ophalen kan bij ‘2 · Bestanden’.",
                       "%d large files found.") % len(r))
        self.klus(lambda say: self.adb.grote_bestanden(50), klaar)

    # ------------------------------------------------ 4 batterij
    def _p_batterij(self):
        w = QWidget(); lay = QVBoxLayout(w)
        self.lbl_bat = QLabel(L("Klik op ‘Batterij bekijken’.", "Click ‘Show battery’."))
        self.lbl_bat.setStyleSheet("font-size:20px;")
        self.lbl_bat.setWordWrap(True)
        lay.addWidget(self.lbl_bat)
        lay.addWidget(self.g._btn("🔋  " + L("Batterij bekijken", "Show battery"), self.batterij))
        self._uitleg(lay, L("Stroomverbruik per app sinds de laatste keer volledig opladen (in mAh):",
                            "Power use per app since last full charge (mAh):"))
        self.tb_stroom = _tabel([L("App", "App"), "mAh"])
        self.tb_stroom.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.tb_stroom, 1)
        return w

    def batterij(self):
        def werk(say):
            return self.adb.batterij(), self.adb.stroomvreters(15)
        def klaar(r):
            if self._fout(r):
                return
            b, s = r
            t = L("Batterij %s%% · gezondheid: %s", "Battery %s%% · health: %s") % (b["niveau"], b["gezondheid"])
            if b["temp"] is not None:
                t += " · %.1f °C" % b["temp"]
            t += L(" · aan de lader" if b["laadt"] else " · niet aan de lader",
                   " · charging" if b["laadt"] else " · not charging")
            self.lbl_bat.setText(t)
            self.lbl_bat.setStyleSheet("font-size:20px; color:%s;" % (GOED if b["gezondheid"] == "goed" else LETOP))
            self.tb_stroom.setRowCount(0)
            for n, m in s:
                i = self.tb_stroom.rowCount(); self.tb_stroom.insertRow(i)
                self.tb_stroom.setItem(i, 0, QTableWidgetItem(n))
                self.tb_stroom.setItem(i, 1, QTableWidgetItem("%.0f" % m))
        self.klus(werk, klaar)

    # ------------------------------------------------ 5 apps
    def _p_apps(self):
        w = QWidget(); lay = QVBoxLayout(w)
        self._uitleg(lay, L(
            "Jouw eigen geïnstalleerde apps. Vink aan wat weg mag en klik op ‘Verwijderen’. Er wordt eerst een "
            "reservekopie (apk) op de pc gemaakt. Je app-gegevens gaan wél verloren.",
            "Your own installed apps. Tick what may go and click ‘Remove’. A backup (apk) is made on the PC first."))
        r = QHBoxLayout()
        r.addWidget(self.g._btn("📋  " + L("Apps ophalen", "Load apps"), self.apps, ghost=True))
        r.addWidget(self.g._btn("🗑  " + L("Aangevinkte verwijderen", "Remove ticked"), self.verwijder))
        lay.addLayout(r)
        self.tb_apps = _tabel(["", L("App (pakket)", "App (package)"), L("Grootte", "Size"),
                               L("Laatst gebruikt", "Last used")])
        self.tb_apps.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.tb_apps, 1)
        return w

    def apps(self):
        self.say(L("Apps ophalen (even geduld)…", "Loading apps…"))
        def werk(say):
            return self.adb.gebruikers_apps(), self.adb.app_groottes(), self.adb.laatst_gebruikt()
        def klaar(r):
            if self._fout(r):
                return
            lijst, gr, lg = r
            nu = time.time()
            rijen = []
            for p in lijst:
                a, d, c = gr.get(p, (0, 0, 0))
                t = lg.get(p, 0)
                rijen.append((p, a + d + c, t))
            rijen.sort(key=lambda x: x[2])          # langst niet gebruikt bovenaan
            self.tb_apps.setRowCount(0)
            for p, g, t in rijen:
                i = self.tb_apps.rowCount(); self.tb_apps.insertRow(i)
                vk = QTableWidgetItem(); vk.setFlags(vk.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                vk.setCheckState(Qt.CheckState.Unchecked)
                self.tb_apps.setItem(i, 0, vk)
                self.tb_apps.setItem(i, 1, QTableWidgetItem(p))
                self.tb_apps.setItem(i, 2, QTableWidgetItem(TF.mooi(g) if g else "?"))
                if t:
                    dagen = int((nu - t) / 86400)
                    it = QTableWidgetItem(time.strftime("%d-%m-%Y", time.localtime(t)) +
                                          L("  (%d dagen)", "  (%d days)") % dagen)
                    if dagen > 90:
                        it.setForeground(QColor(LETOP))
                else:
                    it = QTableWidgetItem(L("onbekend", "unknown"))
                self.tb_apps.setItem(i, 3, it)
            self.tb_apps.resizeColumnToContents(0)
            self.say(L("%d apps. Bovenaan: het langst niet gebruikt.", "%d apps. Top: unused longest.") % len(rijen))
        self.klus(werk, klaar)

    def verwijder(self):
        weg = [self.tb_apps.item(i, 1).text() for i in range(self.tb_apps.rowCount())
               if self.tb_apps.item(i, 0).checkState() == Qt.CheckState.Checked]
        if not weg:
            return
        if QMessageBox.question(self, "DraveGuard", L("Deze %d app(s) verwijderen?\n\n%s",
                                                      "Remove these %d app(s)?\n\n%s") % (len(weg), "\n".join(weg))) \
                != QMessageBox.StandardButton.Yes:
            return
        bmap = os.path.join(self.doel, "App-reservekopie")
        def werk(say):
            for p in weg:
                self.adb.verwijder_app(p, bmap, say)
            say(L("✔ Klaar. Reservekopieën staan in ", "✔ Done. Backups in ") + bmap)
        self.klus(werk, lambda r: (self._fout(r), self.apps()))

    # ------------------------------------------------ 6 controle
    def _p_controle(self):
        w = QWidget(); lay = QVBoxLayout(w)
        self._uitleg(lay, L(
            "Eén knop: opslag, batterij, beveiligingsupdate, apps die zelf apps mogen installeren, apps met "
            "camera/microfoon/locatie, grote bestanden en stroomverbruik. Je krijgt een rapport op de pc.",
            "One button: storage, battery, security patch, permissions, large files and power use. You get a report."))
        r = QHBoxLayout()
        r.addWidget(self.g._btn("🩺  " + L("Volledige controle starten", "Start full check"), self.controle))
        self.btn_rap = self.g._btn(L("Rapport openen", "Open report"), self.open_rapport, ghost=True)
        self.btn_rap.setEnabled(False)
        r.addWidget(self.btn_rap)
        lay.addLayout(r)
        self.lbl_ctl = QLabel("")
        self.lbl_ctl.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_ctl.setWordWrap(True)
        self.lbl_ctl.setStyleSheet("font-size:19px;")
        lay.addWidget(self.lbl_ctl)
        lay.addStretch()
        self._rapport = ""
        return w

    def controle(self):
        doel = self.doel
        def werk(say):
            r = self.adb.controle(say)
            pad = os.path.join(doel, "Rapporten", "DraveCare_rapport_%s.html" % time.strftime("%Y-%m-%d_%H%M"))
            TF.rapport_html(r, pad)
            return r, pad
        def klaar(res):
            if self._fout(res):
                return
            r, pad = res
            self._rapport = pad
            self.btn_rap.setEnabled(True)
            self.lbl_ctl.setText("<br>".join('<span style="color:%s">● %s</span>' % (KL[k], t)
                                             for k, t in TF.oordeel(r)))
            self.say(L("Rapport opgeslagen: ", "Report saved: ") + pad)
        self.klus(werk, klaar)

    def open_rapport(self):
        if self._rapport:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._rapport))
