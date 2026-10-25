#!/usr/bin/env python3
"""Filigrane renforcé pour PDF (dossiers de location, copies de pièces d'identité...).

Par rapport à la v1 :
  - filigrane répété en mosaïque sur toute la page (impossible à recadrer),
  - option --flatten : chaque page est convertie en image, ce qui supprime le
    texte et le calque vectoriel (le filigrane ne peut plus être retiré comme un objet),
  - option --add-date pour dater la copie,
  - métadonnées du PDF effacées.

Dépendances :
    pip install pypdf reportlab pypdfium2 pillow

Exemple :
    python watermark_pdf_secure.py dossier.pdf "Copie réservée à Agence Dupont - location" \
        dossier_filigrane.pdf --flatten --add-date
"""

import argparse
import io
import math
import sys
from datetime import date
from pathlib import Path

import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.lib.colors import HexColor
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

FONT = "Helvetica-Bold"


def make_overlay(width, height, text, opacity, color, font_size, angle):
    """Page transparente contenant le texte répété en mosaïque, inclinée."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(width, height))

    diagonal = math.hypot(width, height)
    text_width = stringWidth(text, FONT, font_size)
    step_x = text_width + font_size * 2
    step_y = font_size * 3.5
    cols = int(diagonal / step_x) + 2
    rows = int(diagonal / step_y) + 2

    c.saveState()
    c.setFillColor(color)
    c.setFillAlpha(opacity)
    c.setFont(FONT, font_size)
    c.translate(width / 2, height / 2)
    c.rotate(angle)
    for r in range(-rows, rows + 1):
        offset = step_x / 2 if r % 2 else 0  # lignes décalées une sur deux
        for k in range(-cols, cols + 1):
            c.drawCentredString(k * step_x + offset, r * step_y, text)
    c.restoreState()

    c.save()
    buffer.seek(0)
    return PdfReader(buffer).pages[0]


def add_watermark(reader, text, opacity, color, font_ratio, angle):
    """Retourne un PdfWriter avec le filigrane fusionné sur chaque page."""
    writer = PdfWriter()
    for page in reader.pages:
        box = page.mediabox
        width, height = float(box.width), float(box.height)
        font_size = width * font_ratio
        overlay = make_overlay(width, height, text, opacity, color, font_size, angle)
        page.merge_transformed_page(
            overlay, Transformation().translate(float(box.left), float(box.bottom))
        )
        writer.add_page(page)
    writer.add_metadata({"/Producer": "", "/Creator": ""})
    return writer


def flatten_pdf(pdf_bytes, dpi, jpeg_quality):
    """Convertit chaque page en image : plus de texte ni d'objets séparés."""
    src = pdfium.PdfDocument(pdf_bytes)
    images = []
    for page in src:
        # scale = dpi / 72 (un point PDF = 1/72 de pouce)
        images.append(page.render(scale=dpi / 72).to_pil().convert("RGB"))
    src.close()

    out = io.BytesIO()
    # Chaque image devient une page ; la taille en points est conservée
    # grâce à la résolution indiquée. Aucun texte ni objet vectoriel n'est conservé.
    images[0].save(
        out,
        format="PDF",
        save_all=True,
        append_images=images[1:],
        resolution=dpi,
        quality=jpeg_quality,
    )
    return out.getvalue()


def parse_args():
    p = argparse.ArgumentParser(description="Filigrane renforcé en mosaïque pour PDF.")
    p.add_argument("input", type=Path, help="PDF à modifier")
    p.add_argument("text", help="Texte du filigrane")
    p.add_argument("output", type=Path, help="PDF de sortie")
    p.add_argument("--opacity", type=float, default=0.4, help="Opacité 0-1 (défaut 0.4)")
    p.add_argument("--color", default="#808080", help="Couleur hex (défaut #808080)")
    p.add_argument("--angle", type=float, default=30, help="Angle en degrés (défaut 30)")
    p.add_argument(
        "--font-ratio",
        type=float,
        default=0.04,
        help="Taille de police en proportion de la largeur de page (défaut 0.04)",
    )
    p.add_argument("--add-date", action="store_true", help="Ajoute la date du jour au texte")
    p.add_argument(
        "--flatten",
        action="store_true",
        help="Convertit les pages en images (recommandé : plus difficile à retirer)",
    )
    p.add_argument("--dpi", type=int, default=150, help="Résolution si --flatten (défaut 150)")
    p.add_argument("--jpeg-quality", type=int, default=85, help="Qualité JPEG si --flatten")
    return p.parse_args()


def main():
    args = parse_args()

    if not args.input.is_file():
        sys.exit(f"Erreur : fichier introuvable : {args.input}")
    if args.input.resolve() == args.output.resolve():
        sys.exit("Erreur : le fichier de sortie doit être différent de l'entrée.")
    if not args.text.strip():
        sys.exit("Erreur : le texte du filigrane est vide.")
    if not 0 <= args.opacity <= 1:
        sys.exit("Erreur : l'opacité doit être comprise entre 0 et 1.")
    try:
        color = HexColor(args.color)
    except ValueError:
        sys.exit(f"Erreur : couleur invalide : {args.color}")

    text = args.text.strip()
    if args.add_date:
        text += f" - {date.today():%d/%m/%Y}"

    try:
        reader = PdfReader(args.input)
        if reader.is_encrypted:
            sys.exit("Erreur : le PDF est protégé par un mot de passe (non géré).")
        writer = add_watermark(
            reader, text, args.opacity, color, args.font_ratio, args.angle
        )
        buf = io.BytesIO()
        writer.write(buf)
        data = buf.getvalue()
        if args.flatten:
            data = flatten_pdf(data, args.dpi, args.jpeg_quality)
        args.output.write_bytes(data)
    except SystemExit:
        raise
    except Exception as e:
        sys.exit(f"Erreur : {e}")

    print(f"Filigrane ajouté sur {len(reader.pages)} page(s) -> {args.output}")


if __name__ == "__main__":
    main()