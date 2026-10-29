# -*- coding: utf-8 -*-
# DraveCare - Copyright (C) 2026 Dravenlock (Roger & Claudio).
"""maak_stem_care.py - Leon spreekt de vaste zinnetjes in voor DraveCare op de telefoon. Draai: py -3.10 maak_stem_care.py"""
import os
import sys
import wave

import numpy as np

HIER = os.path.dirname(os.path.abspath(__file__))
ZINNEN = {
    "c_welkom": "Welkom bij DraveCare. Ik kijk je telefoon na.",
    "c_alles_goed": "Je telefoon is in orde.",
    "c_opslag_goed": "Je opslag heeft nog genoeg ruimte.",
    "c_opslag_letop": "Let op: je opslag raakt vol.",
    "c_opslag_vol": "Je opslag is bijna vol. Ruim wat op.",
    "c_bat_goed": "Je batterij is gezond.",
    "c_bat_warm": "Je batterij is warm. Leg de telefoon even weg.",
    "c_bat_slecht": "Je batterij heeft een probleem of is versleten.",
    "c_bat_laag": "Je batterij is bijna leeg. Leg hem aan de lader.",
    "c_slot_uit": "Er staat geen schermslot aan. Dat is niet veilig.",
    "c_patch_oud": "Je beveiligingsupdate is oud.",
    "c_patch_goed": "Je beveiligingsupdate is recent.",
    "c_installeer": "Er zijn apps die zelf andere apps mogen installeren.",
    "c_ongebruikt": "Er staan apps op die je al lang niet gebruikt.",
    "c_dubbel": "Ik heb dubbele foto's gevonden.",
    "c_geen_dubbel": "Ik heb geen dubbele foto's gevonden.",
    "c_prullenbak": "Klaar. De bestanden staan in de prullenbak. Je kunt ze dertig dagen terugzetten.",
    "c_terug": "Klaar. De bestanden staan weer op hun plek.",
    "c_toegang": "DraveCare heeft toegang nodig. Tik op de knop en zet de schakelaar aan.",
    "c_klaar": "Klaar met nakijken.",
}


def uitspraak_fn():
    """Pa's eigen uitspraaklijst (DraveLeon), als die er is."""
    for p in (os.path.join(HIER, "..", "..", "Tools en kantoor", "DraveLeon"), HIER):
        if os.path.exists(os.path.join(p, "uitspraak.py")):
            sys.path.insert(0, os.path.abspath(p))
            try:
                import uitspraak
                return uitspraak.uitspraak
            except Exception:
                pass
    return lambda t: t


def main():
    from neuvoice import TTS
    uit = os.path.join(HIER, "stem_care")
    os.makedirs(uit, exist_ok=True)
    tts = TTS(auto_download=True)
    namen = list(getattr(tts, "voice_style_names", []) or [])
    stijl = tts.get_voice_style("Leon" if "Leon" in namen else namen[0])
    sr = int(getattr(tts, "sample_rate", 44100) or 44100)
    u = uitspraak_fn()
    for sleutel, tekst in ZINNEN.items():
        wav, _ = tts.synthesize(u(tekst), voice_style=stijl, total_steps=10, speed=0.9, lang="nl")
        x = np.asarray(wav, dtype=np.float32).flatten()
        drempel = 0.01 * (np.max(np.abs(x)) or 1)
        waar = np.where(np.abs(x) > drempel)[0]
        if len(waar):
            x = x[max(0, waar[0] - int(sr * 0.015)): waar[-1] + int(sr * 0.04)]
        x = np.concatenate([np.zeros(int(sr * 0.03), np.float32), x, np.zeros(int(sr * 0.03), np.float32)])
        n = int(len(x) * 22050 / sr)
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)
        x = x / (np.max(np.abs(x)) or 1) * 0.9
        with wave.open(os.path.join(uit, sleutel + ".wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(22050)
            w.writeframes((x * 32767).astype("<i2").tobytes())
    print("KLAAR", len(ZINNEN))


if __name__ == "__main__":
    main()
