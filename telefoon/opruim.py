# -*- coding: utf-8 -*-
# DraveCare - Dravenlock (Roger & Claudio). Vrije software onder de GNU GPL v3.0.
"""opruim.py - grote bestanden, dubbele foto's, oude downloads en de prullenbak (30 dagen terugzetten)."""
import hashlib
import json
import os
import shutil
import time

import droid

ROOT = droid.OPSLAG
BAK = os.path.join(ROOT, "DraveCare_prullenbak")
INDEX = os.path.join(BAK, "index.json")
DAGEN_BEWAREN = 30
OVERSLAAN = {os.path.join(ROOT, "Android", "data"), os.path.join(ROOT, "Android", "obb"), BAK}
MEDIA = (".jpg", ".jpeg", ".png", ".heic", ".webp", ".gif", ".mp4", ".mov", ".3gp", ".mkv")


def _loop(mappen, stop=lambda: False):
    for m in mappen:
        if not os.path.isdir(m):
            continue
        for d, sub, fs in os.walk(m):
            if stop():
                return
            sub[:] = [s for s in sub if os.path.join(d, s) not in OVERSLAAN and not s.startswith(".")]
            for f in fs:
                p = os.path.join(d, f)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                yield p, st.st_size, st.st_mtime


def grote(min_mb=50, stop=lambda: False):
    res = [(p, g, t) for p, g, t in _loop([ROOT], stop) if g >= min_mb * 2 ** 20]
    return sorted(res, key=lambda x: -x[1])


def oude_downloads(dagen=90, stop=lambda: False):
    grens = time.time() - dagen * 86400
    res = [(p, g, t) for p, g, t in _loop([os.path.join(ROOT, "Download")], stop) if t < grens]
    return sorted(res, key=lambda x: x[2])


def _hash(p, deel=None):
    h = hashlib.md5()
    with open(p, "rb") as f:
        if deel:
            h.update(f.read(deel))
        else:
            for blok in iter(lambda: f.read(1 << 20), b""):
                h.update(blok)
    return h.hexdigest()


def dubbel(stop=lambda: False, say=lambda t: None):
    """Dubbele foto's/video's: zelfde grootte én zelfde inhoud. Het OUDSTE exemplaar blijft (niet in de lijst)."""
    mappen = [os.path.join(ROOT, x) for x in ("DCIM", "Pictures", "Download", "Documents",
                                              os.path.join("Android", "media"), "Movies")]
    per = {}
    n = 0
    for p, g, t in _loop(mappen, stop):
        if p.lower().endswith(MEDIA) and g > 10 * 1024:
            per.setdefault(g, []).append((p, g, t))
            n += 1
            if n % 200 == 0:
                say("%d bestanden bekeken..." % n)
    res = []
    for g, lijst in per.items():
        if len(lijst) < 2 or stop():
            continue
        snel = {}
        for x in lijst:
            try:
                snel.setdefault(_hash(x[0], 65536), []).append(x)
            except OSError:
                pass
        for groep in snel.values():
            if len(groep) < 2:
                continue
            vol = {}
            for x in groep:
                try:
                    vol.setdefault(_hash(x[0]), []).append(x)
                except OSError:
                    pass
            for zelfde in vol.values():
                if len(zelfde) > 1:
                    zelfde.sort(key=lambda x: x[2])
                    res.extend(zelfde[1:])      # de oudste blijft staan
    return sorted(res, key=lambda x: -x[1])


# ------------------------------------------------------------------ prullenbak
def _lees():
    try:
        with open(INDEX, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _schrijf(ix):
    os.makedirs(BAK, exist_ok=True)
    tmp = INDEX + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(ix, f)
    os.replace(tmp, INDEX)


def naar_prullenbak(paden):
    """Verplaatst (niet wissen). Geeft (aantal, bytes)."""
    os.makedirs(BAK, exist_ok=True)
    ix = _lees()
    n = b = 0
    weg = []
    for p in paden:
        try:
            g = os.path.getsize(p)
            naam = "%d_%s" % (int(time.time() * 1000) % 10 ** 10, os.path.basename(p))
            doel = os.path.join(BAK, naam)
            shutil.move(p, doel)
            ix[naam] = {"van": p, "tijd": time.time(), "grootte": g}
            n += 1
            b += g
            weg += [p, doel]
        except Exception:
            pass
    _schrijf(ix)
    droid.scan_media(weg)
    return n, b


def inhoud():
    ix = _lees()
    res = []
    for naam, v in ix.items():
        p = os.path.join(BAK, naam)
        if os.path.exists(p):
            res.append((naam, v["van"], v.get("grootte", 0), v.get("tijd", 0)))
    return sorted(res, key=lambda x: -x[3])


def terugzetten(namen):
    ix = _lees()
    n = 0
    paden = []
    for naam in namen:
        v = ix.get(naam)
        if not v:
            continue
        try:
            doel = v["van"]
            if os.path.exists(doel):
                b, e = os.path.splitext(doel)
                doel = b + "_terug" + e
            os.makedirs(os.path.dirname(doel), exist_ok=True)
            shutil.move(os.path.join(BAK, naam), doel)
            ix.pop(naam, None)
            n += 1
            paden.append(doel)
        except Exception:
            pass
    _schrijf(ix)
    droid.scan_media(paden)
    return n


def definitief(namen):
    ix = _lees()
    n = b = 0
    for naam in namen:
        p = os.path.join(BAK, naam)
        try:
            if os.path.exists(p):
                b += os.path.getsize(p)
                os.remove(p)
            ix.pop(naam, None)
            n += 1
        except Exception:
            pass
    _schrijf(ix)
    return n, b


def oud_opruimen():
    """Wat langer dan 30 dagen in de prullenbak ligt, gaat echt weg."""
    grens = time.time() - DAGEN_BEWAREN * 86400
    oud = [naam for naam, van, g, t in inhoud() if t < grens]
    if oud:
        definitief(oud)
    return len(oud)


def mooi(b):
    if b is None or b < 0:
        return "?"
    for e in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024 or e == "TB":
            return ("%.0f %s" if e in ("B", "KB") else "%.1f %s") % (b, e)
        b /= 1024.0
