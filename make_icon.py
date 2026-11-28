# -*- coding: utf-8 -*-
"""Bouwt assets/icon.ico voor DraveGuard uit het Dravenlock-draaklogo.

Zoekt het logo eerst in DraveGuard\\assets, dan in de gedeelde ..\\assets-map.
Valt terug op een simpel getekend schild-icoon als er geen logo is.
Gebruikt Pillow (geldige ICO met meerdere maten) - NIET pygame.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
os.makedirs(ASSETS, exist_ok=True)


def _find_logo():
    cands = [
        os.path.join(ASSETS, "logo.png"),
        os.path.join(ASSETS, "logo_t.png"),
        os.path.join(HERE, "..", "assets", "logo.png"),
        os.path.join(HERE, "..", "assets", "logo_t.png"),
    ]
    for c in cands:
        if os.path.isfile(c):
            return os.path.abspath(c)
    return None


def main():
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("Pillow ontbreekt: pip install pillow")
        return

    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    logo = _find_logo()
    if logo:
        img = Image.open(logo).convert("RGBA")
        # vierkant canvas met de logo netjes gecentreerd
        s = max(img.size)
        canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        canvas.paste(img, ((s - img.width) // 2, (s - img.height) // 2), img)
        base = canvas
    else:
        # getekend schild als terugval
        base = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        d = ImageDraw.Draw(base)
        d.polygon([(128, 20), (226, 60), (226, 140), (128, 236), (30, 140), (30, 60)],
                  fill=(127, 119, 221, 255), outline=(181, 156, 255, 255))
        d.line([(90, 128), (118, 158), (172, 96)], fill=(255, 255, 255, 255), width=14)

    ico = os.path.join(ASSETS, "icon.ico")
    base.save(ico, format="ICO", sizes=sizes)
    # ook een png voor de homepagina
    base.resize((256, 256)).save(os.path.join(ASSETS, "icon-256.png"))
    print("icoon geschreven:", ico)


if __name__ == "__main__":
    main()
