#!/usr/bin/env python3
"""Generate docs/plantilla-secretarios.pdf: how secretaries send their monthly update.

Usage: python3 docs/make_plantilla.py [--to boletin@...] [--out path.pdf]

Parish name, contact and deadlines come from config.yaml. --to is the newsletter
inbox address; without it the PDF leaves a blank line to fill in by hand.
Needs reportlab and pyyaml (both in the system Python on the Pi).
"""

import argparse
from pathlib import Path

import yaml
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether, PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table,
    TableStyle,
)

PROJECT_DIR = Path(__file__).resolve().parent.parent

GRANATE = colors.HexColor("#770024")
BURDEOS = colors.HexColor("#b30c3c")
DORADO = colors.HexColor("#a39b5c")
CREMA = colors.HexColor("#faf7f0")
TEXTO = colors.HexColor("#282828")
GRIS = colors.HexColor("#6b6b6b")

# Built-in PDF fonts: they cover Spanish and need no font files on the machine.
SANS, SANS_BOLD, MONO = "Helvetica", "Helvetica-Bold", "Courier"

S = {
    "h1": ParagraphStyle("h1", fontName=SANS_BOLD, fontSize=15, leading=19,
                         textColor=GRANATE, spaceBefore=4, spaceAfter=6),
    "h2": ParagraphStyle("h2", fontName=SANS_BOLD, fontSize=11.5, leading=15,
                         textColor=GRANATE, spaceBefore=10, spaceAfter=4),
    "body": ParagraphStyle("body", fontName=SANS, fontSize=9.5, leading=14, textColor=TEXTO),
    "small": ParagraphStyle("small", fontName=SANS, fontSize=8.5, leading=12, textColor=GRIS),
    "label": ParagraphStyle("label", fontName=SANS_BOLD, fontSize=9.5, leading=13,
                            textColor=GRANATE),
    "bullet": ParagraphStyle("bullet", fontName=SANS, fontSize=9.5, leading=14,
                             textColor=TEXTO, leftIndent=12, bulletIndent=2, spaceAfter=2),
    "mono": ParagraphStyle("mono", fontName=MONO, fontSize=9, leading=12.6, textColor=TEXTO),
    "center": ParagraphStyle("center", fontName=SANS, fontSize=8.5, leading=12,
                             textColor=GRIS, alignment=TA_CENTER),
}

TEMPLATE = """\
Asunto: Boletín de [mes] - [nombre del grupo]

1. LO QUE HEMOS HECHO ESTE MES
   (La parte más importante. Extiéndete todo lo que
   quieras.)
[Qué hicimos y cómo fue. Cuántos participamos y
quiénes. Qué vivimos, qué aprendimos, qué nos
llevamos. Alguna anécdota, una frase de alguien,
algo que nos sorprendió o nos emocionó. Quién nos
acompañó (sacerdote, ponente, otro grupo). Cuanto
más cuentes, más vivo quedará el boletín.]

2. PRÓXIMAS ACTIVIDADES
[Una línea por actividad: qué, cuándo, dónde y,
si hace falta, cómo apuntarse.]
- [Qué], [día y hora], [lugar]. [Inscripción]

3. AVISOS Y NECESIDADES
[Cambios de horario, voluntarios, material...
Si no hay nada, borra este apartado.]

4. CONTACTO DEL GRUPO (se publicará)
[Nombre, correo y/o teléfono.]"""

EXAMPLE = """\
Asunto: Boletín de noviembre - Jóvenes y Universitarios

1. LO QUE HEMOS HECHO ESTE MES
Después de los exámenes hemos vuelto a reunirnos los
viernes. Somos ya unos 20, y este mes se han sumado
tres chicas de primero de carrera que conocieron el
grupo en la misa de jóvenes.

El 13 de octubre vino el párroco a hablarnos de
vocación y sentido de la vida. Más que una charla fue
una conversación: estuvimos casi dos horas y nadie
tenía prisa por irse. Nos quedamos con una pregunta
suya: "¿Para quién eres tú?".

También preparamos la vigilia del Domund. Hicimos
los carteles, cantamos en la misa de 20:00 y
recaudamos 340 euros para las misiones. Gracias a
todos los que colaborasteis.

2. PRÓXIMAS ACTIVIDADES
- Cine-fórum "El Gran Silencio", viernes 14 de
  noviembre a las 20:00, salón parroquial.
- Convivencia de Adviento, 28-30 de noviembre,
  Monasterio de Veruela. Inscripción antes del 20
  en jovenes@example.com.

3. AVISOS Y NECESIDADES
Buscamos dos coches para el traslado a Veruela.

4. CONTACTO DEL GRUPO (se publicará)
Marta - jovenes@example.com"""


def header_footer(parish):
    def draw(canvas, doc):
        w, h = A4
        canvas.saveState()
        canvas.setFillColor(GRANATE)
        canvas.rect(0, h - 26 * mm, w, 26 * mm, stroke=0, fill=1)
        canvas.setFillColor(DORADO)
        canvas.rect(0, h - 27.2 * mm, w, 1.2 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont(SANS_BOLD, 16)
        canvas.drawString(18 * mm, h - 14 * mm, "Boletín parroquial")
        canvas.setFont(SANS, 9.5)
        canvas.setFillColor(colors.HexColor("#e9e2c4"))
        canvas.drawString(18 * mm, h - 20.5 * mm, "Guía y plantilla para los secretarios de los grupos")
        canvas.setFont(SANS, 8)
        canvas.setFillColor(GRIS)
        canvas.drawString(18 * mm, 12 * mm, parish.get("name", ""))
        canvas.drawRightString(w - 18 * mm, 12 * mm, f"Página {doc.page}")
        canvas.setStrokeColor(DORADO)
        canvas.setLineWidth(0.6)
        canvas.line(18 * mm, 16 * mm, w - 18 * mm, 16 * mm)
        canvas.restoreState()
    return draw


def boxed(flowables, background=CREMA, border=DORADO):
    t = Table([[flowables]], colWidths=[174 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), background),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, border),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def bullets(items):
    return [Paragraph(text, S["bullet"], bulletText="•") for text in items]


def build(out, to, config):
    parish = config.get("parish", {})
    sched = config.get("schedule", {})
    start = sched.get("collection_start_day", 10)
    remind = sched.get("reminder_day", 20)
    publish = sched.get("publish_day", 25)
    inbox = to or "_______________________________________"

    doc = SimpleDocTemplate(
        str(out), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=34 * mm, bottomMargin=22 * mm,
        title="Boletín parroquial: guía para secretarios", author=parish.get("name", ""),
    )
    story = []

    # ── Página 1: cómo enviar ───────────────────────────────────────
    story += [
        Paragraph("Cómo enviar la información de tu grupo", S["h1"]),
        Paragraph(
            "Cada mes, la parroquia publica un boletín con las noticias de todos los grupos. "
            "Tú solo tienes que enviar un correo con lo que ha hecho tu grupo y lo que viene. "
            "Con los correos de todos los grupos se redacta un único boletín, con un mismo tono y "
            "diseño; antes de enviarse a los feligreses, una persona de la parroquia lo revisa.",
            S["body"]),
        Spacer(1, 8),
    ]

    rows = [
        ("Para", f"<b>{inbox}</b>"),
        ("Desde", "La dirección de correo de tu grupo que tiene registrada la parroquia. "
                  "Los correos que lleguen desde otra dirección no se recogen."),
        ("Cuándo", f"Del día <b>{start}</b> al día <b>{publish}</b> de cada mes. "
                   f"El día {remind} se manda un recordatorio a los grupos que aún no han escrito."),
        ("Asunto", "Boletín de [mes] - [nombre del grupo]"),
        ("Respuesta", "Recibirás un acuse de recibo automático. Si no te llega, revisa la "
                      "carpeta de spam o escribe a la parroquia."),
    ]
    t = Table([[Paragraph(k, S["label"]), Paragraph(v, S["body"])] for k, v in rows],
              colWidths=[26 * mm, 148 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#e4dfcf")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("BACKGROUND", (0, 0), (-1, -1), CREMA),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story += [t, Spacer(1, 4)]

    story.append(Paragraph("Cómo escribirlo", S["h2"]))
    story += bullets([
        "<b>Escríbelo en el cuerpo del correo</b>, no en un documento adjunto. El boletín se "
        "redacta a partir del texto del correo. Los adjuntos (Word, PDF, carteles) se guardan, "
        "pero no se leen.",
        "<b>Usa la plantilla de la página siguiente.</b> Cópiala en el correo y rellena los "
        "apartados. Borra los que no necesites.",
        "<b>Lo más importante es contar lo que habéis vivido este mes.</b> Es lo que hace "
        "comunidad: qué hicisteis, cómo fue, quiénes participasteis, qué os llevasteis, alguna "
        "anécdota. Extiéndete todo lo que quieras; varios párrafos están muy bien.",
        "<b>Las próximas actividades, en breve:</b> una línea cada una con qué, cuándo (día, "
        "mes y hora; evita «el sábado que viene»), dónde y, si hace falta, cómo apuntarse.",
        "<b>No hace falta que quede bonito.</b> Con frases sencillas basta: la redacción final "
        "se armoniza con la del resto de grupos.",
        "<b>Solo información que se pueda publicar.</b> El boletín llega a toda la comunidad. "
        "No incluyas datos personales sin permiso, ni nombres o datos de menores. El contacto "
        "que pongas en el apartado 4 se publicará.",
        "<b>¿Se te olvidó algo?</b> Responde a tu propio correo o manda otro antes del día "
        f"{publish}. El último correo completa o corrige a los anteriores: indica qué cambia "
        "(<i>«la convivencia pasa al día 30»</i>).",
        "<b>Fotos:</b> por ahora el boletín no publica las fotos que se adjuntan.",
    ])

    contact = " · ".join(x for x in (parish.get("phone"), parish.get("email")) if x)
    if contact:
        story += [Spacer(1, 8),
                  boxed([Paragraph(f"<b>¿Dudas?</b> Escribe o llama a la parroquia: {contact}",
                                   S["body"])])]

    # ── Página 2: plantilla ─────────────────────────────────────────
    story += [
        PageBreak(),
        Paragraph("Plantilla para copiar en el correo", S["h1"]),
        Paragraph("La primera línea va en el <b>asunto</b> del correo. El resto, desde «1.», "
                  "cópialo en el cuerpo, sustituye lo que está entre corchetes y borra lo que "
                  "no necesites.", S["body"]),
        Spacer(1, 8),
        boxed([Preformatted(TEMPLATE, S["mono"])]),
    ]

    # ── Página 3: ejemplo ───────────────────────────────────────────
    story += [
        PageBreak(),
        Paragraph("Ejemplo rellenado", S["h1"]),
        Paragraph("Así podría ser el correo de un grupo. Es solo un ejemplo: cada grupo cuenta "
                  "lo suyo con sus propias palabras.", S["body"]),
        Spacer(1, 8),
        boxed([Preformatted(EXAMPLE, S["mono"])], background=colors.white),
        Spacer(1, 12),
        KeepTogether([
            Paragraph("Lo que pasa después", S["h2"]),
            *bullets([
                "Recibes el acuse de recibo y tu información queda guardada para el boletín del mes.",
                f"El día {publish} se redacta el boletín con los correos de todos los grupos.",
                "Una persona de la parroquia lo revisa, corrige si hace falta y lo envía a los "
                "suscriptores.",
            ]),
        ]),
    ]

    doc.build(story, onFirstPage=header_footer(parish), onLaterPages=header_footer(parish))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--to", default="", help="newsletter inbox address to print in the PDF")
    parser.add_argument("--out", default=str(PROJECT_DIR / "docs" / "plantilla-secretarios.pdf"))
    args = parser.parse_args()

    with (PROJECT_DIR / "config.yaml").open(encoding="utf-8") as f:
        config = yaml.safe_load(f)
    build(Path(args.out), args.to, config)
    print(f"Written {args.out}")


if __name__ == "__main__":
    main()
