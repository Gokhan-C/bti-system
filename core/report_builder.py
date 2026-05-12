"""
Ortak python-docx yardımcıları — CBP ve CBSA connector'ları tarafından kullanılır.
AB EBTI connector'ı Node.js build_docx.js'i kullanır, buraya bağımlı değil.
"""

from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


def make_doc(title: str, subtitle: str) -> Document:
    doc = Document()
    sec = doc.sections[0]
    sec.page_height = Cm(29.7)
    sec.page_width = Cm(21)
    for attr in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, attr, Cm(2.5))

    tp = doc.add_paragraph()
    tp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    tr = tp.add_run(title)
    tr.bold = True
    tr.font.size = Pt(17)
    tr.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)

    sp = doc.add_paragraph()
    sp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sr = sp.add_run(subtitle)
    sr.italic = True
    sr.font.size = Pt(11)
    sr.font.color.rgb = RGBColor(0x66, 0x66, 0x66)

    doc.add_paragraph()
    return doc


def set_cell_bg(cell, hex_color: str) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def add_info_table(doc: Document, rows: list[tuple[str, str]]) -> None:
    table = doc.add_table(rows=len(rows), cols=2)
    table.style = "Table Grid"
    for i, (label, value) in enumerate(rows):
        lc = table.rows[i].cells[0]
        vc = table.rows[i].cells[1]
        lc.width = Cm(5)
        vc.width = Cm(11)
        set_cell_bg(lc, "EBF3FB")
        lr = lc.paragraphs[0].add_run(label)
        lr.bold = True
        lr.font.size = Pt(10)
        vr = vc.paragraphs[0].add_run(str(value) if value else "-")
        vr.font.size = Pt(10)


def add_ruling_to_doc(
    doc: Document,
    heading: str,
    info_rows: list[tuple[str, str]],
    sections: list[tuple[str, str | list]],
) -> None:
    hp = doc.add_paragraph()
    hr = hp.add_run(heading)
    hr.bold = True
    hr.font.size = Pt(14)
    hr.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)

    add_info_table(doc, info_rows)
    doc.add_paragraph()

    for sec_title, content in sections:
        sp = doc.add_paragraph()
        sr = sp.add_run(sec_title)
        sr.bold = True
        sr.font.size = Pt(11)
        sr.font.color.rgb = RGBColor(0x2E, 0x75, 0xB6)

        if isinstance(content, str) and content:
            p = doc.add_paragraph()
            p.add_run(content).font.size = Pt(10)
        elif isinstance(content, list):
            for item in content:
                p = doc.add_paragraph(style="List Bullet")
                p.add_run(item).font.size = Pt(10)
        doc.add_paragraph()

    doc.add_paragraph("─" * 80)
    doc.add_paragraph()


def add_no_results_notice(doc: Document) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("Bugün yeni HS sınıflandırma kararı bulunamadı.")
    r.italic = True
    r.font.size = Pt(11)
    r.font.color.rgb = RGBColor(0x88, 0x88, 0x88)
