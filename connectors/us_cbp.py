"""
ABD CBP Connector — v2

Veri çekme stratejisi: YENİ KARAR TESPİTİ
  - CBP API'den en son yayınlanan kararlar çekilir.
  - state/us_cbp_seen.json ile karşılaştırılır → sadece yeni ruling numaraları işlenir.
  - Kararlar üç kategoriye ayrılır: 'classification', 'origin', 'other'
  - Rapora SADECE 'classification' kararları girer.
  - Her karar Claude ile 3 maddeye özetlenir (eşya tanımı, GTİP, teknik gerekçe).
  - Raporun başında istatistik tablosu yer alır (sınıflandırma/menşei/diğer sayıları).
  - Her kararın başında tam metne erişim linki verilir.
"""

import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from core.base_connector import BaseConnector
from core.report_builder import make_doc, add_ruling_to_doc, add_no_results_notice, add_info_table
from core.translator import summarize_cbp_ruling_claude

from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


CBP_API_RECENT = "https://rulings.cbp.gov/api/stat/recentRulings"
CBP_API_DETAIL = "https://rulings.cbp.gov/api/ruling/{number}"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://rulings.cbp.gov/home",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}

# ── Kategori tespiti ──────────────────────────────────────────────────────────

ORIGIN_KEYWORDS = [
    "COUNTRY OF ORIGIN", "COUNTRY-OF-ORIGIN",
    "NAFTA", "USMCA", "CAFTA", "FREE TRADE AGREEMENT",
    "RULES OF ORIGIN", "SUBSTANTIAL TRANSFORMATION",
    "MARKING", "CATEGORY: ORIGIN", "CATEGORY:  ORIGIN",
]

CLASSIFICATION_KEYWORDS = [
    "TARIFF CLASSIFICATION", "HTS ", "HTSUS ", "HARMONIZED TARIFF",
    "CATEGORY: CLASSIFICATION", "CATEGORY:  CLASSIFICATION",
]


def _categorize_ruling(detail: dict) -> str:
    """
    Kararı üç kategoriden birine atar:
      'classification' — tarife sınıflandırması
      'origin'         — menşei/ülke tespiti
      'other'          — diğer (değerleme, işaretleme vb.)
    """
    subject   = (detail.get("subject") or "").upper()
    text_head = (detail.get("text") or "")[:600].upper()
    has_tariffs = bool(detail.get("tariffs"))

    is_origin = any(kw in subject or kw in text_head for kw in ORIGIN_KEYWORDS)
    is_classification = has_tariffs or any(
        kw in subject or kw in text_head for kw in CLASSIFICATION_KEYWORDS
    )

    if is_origin and not is_classification:
        return "origin"
    if is_classification:
        return "classification"
    return "other"


# ── API yardımcıları ──────────────────────────────────────────────────────────

def _fetch_recent_rulings(recent_days: int, logger=None) -> list[dict]:
    try:
        r = requests.get(
            CBP_API_RECENT,
            params={"format": "json", "collection": ""},
            headers=HEADERS,
            timeout=20,
        )
        r.raise_for_status()
        cutoff = (datetime.now() - timedelta(days=recent_days)).strftime("%Y-%m-%d")
        recent = []
        for ruling in r.json():
            date_modified = ruling.get("dateModified", "")
            try:
                dt = datetime.strptime(date_modified, "%m/%d/%Y")
                if dt.strftime("%Y-%m-%d") >= cutoff:
                    recent.append(ruling)
            except Exception:
                pass
        return recent
    except Exception as e:
        if logger:
            logger.error(f"ABD CBP API hatası: {e}")
        return []


def _fetch_detail(ruling_number: str, logger=None) -> dict:
    try:
        r = requests.get(
            CBP_API_DETAIL.format(number=ruling_number),
            headers=HEADERS,
            timeout=20,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        if logger:
            logger.warning(f"ABD CBP detay hatası ({ruling_number}): {e}")
        return {}


# ── Rapor yardımcıları ────────────────────────────────────────────────────────

def _add_stats_table(doc, stats: dict, date_str: str) -> None:
    """Raporun başına istatistik özet tablosu ekler."""
    p = doc.add_paragraph()
    r = p.add_run("Günlük Karar İstatistikleri")
    r.bold = True
    r.font.size = Pt(12)
    r.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)

    rows = [
        ("Tarih",                   date_str),
        ("Toplam Çekilen Karar",    str(stats["total"])),
        ("✓ Tarife Sınıflandırması", str(stats["classification"])),
        ("✗ Menşei Kararı (raporda yok)", str(stats["origin"])),
        ("– Diğer (değerleme vb.)", str(stats["other"])),
        ("Rapora Giren",            str(stats["in_report"])),
    ]
    add_info_table(doc, rows)
    doc.add_paragraph()


def _add_ruling_link(doc, url: str) -> None:
    """Her kararın başına tam metne erişim linki ekler."""
    from docx.oxml.ns import qn as _qn
    from docx.oxml import OxmlElement as _OE

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # Sabit metin
    run_label = p.add_run("📄 Tam metne erişmek için: ")
    run_label.font.size = Pt(10)
    run_label.font.color.rgb = RGBColor(0x44, 0x44, 0x44)

    # Hyperlink
    rel_id = doc.part.relate_to(
        url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )
    hyperlink = _OE("w:hyperlink")
    hyperlink.set(_qn("r:id"), rel_id)

    run_link = _OE("w:r")
    rPr = _OE("w:rPr")
    style = _OE("w:rStyle")
    style.set(_qn("w:val"), "Hyperlink")
    rPr.append(style)
    sz = _OE("w:sz")
    sz.set(_qn("w:val"), "20")   # 10pt
    rPr.append(sz)
    run_link.append(rPr)

    t = _OE("w:t")
    t.text = url
    run_link.append(t)
    hyperlink.append(run_link)
    p._p.append(hyperlink)


def _add_summary_section(doc, summary: dict) -> None:
    """3 maddelik Claude özetini rapora yazar."""
    items = [
        ("1. Eşyanın Ticari Tanımı",    summary.get("esya_tanimi", "-")),
        ("2. GTİP Kararı",              summary.get("gtip_karar", "-")),
        ("3. Teknik Gerekçe",           summary.get("teknik_gerekce", "-")),
    ]
    for title, content in items:
        tp = doc.add_paragraph()
        tr = tp.add_run(title)
        tr.bold = True
        tr.font.size = Pt(11)
        tr.font.color.rgb = RGBColor(0x2E, 0x75, 0xB6)

        cp = doc.add_paragraph()
        cp.add_run(content).font.size = Pt(10)
        doc.add_paragraph()


# ── Connector ─────────────────────────────────────────────────────────────────

class UsCbpConnector(BaseConnector):

    @property
    def connector_id(self) -> str:
        return "us_cbp"

    @property
    def display_name(self) -> str:
        return self.config.get("display_name", "ABD CBP")

    def extract_id(self, record: dict[str, Any]) -> str:
        return str(record.get("rulingNumber") or record.get("id") or "")

    def fetch(self, target_date: datetime) -> list[dict[str, Any]]:
        recent_days = self.config.get("recent_days", 14)
        rulings = _fetch_recent_rulings(recent_days)
        for ruling in rulings:
            ruling["id"] = ruling.get("rulingNumber", "")
        return rulings

    def build_report(
        self, records: list[dict[str, Any]], target_date: datetime
    ) -> list[Path]:
        date_str = target_date.strftime("%Y-%m-%d")
        date_dir = self.output_dir / date_str
        date_dir.mkdir(parents=True, exist_ok=True)

        doc = make_doc(
            "ABD CBP Tarife Sınıflandırma Kararları",
            f"CBP  |  {date_str}",
        )

        # ── İstatistik sayaçları ──
        stats = {"total": 0, "classification": 0, "origin": 0, "other": 0, "in_report": 0}
        classification_records = []

        for ruling in records:
            number = ruling.get("rulingNumber", "UNKNOWN")
            detail = _fetch_detail(number)
            if not detail:
                continue

            stats["total"] += 1
            category = _categorize_ruling(detail)
            stats[category] += 1

            if category == "classification":
                date_raw = ruling.get("dateModified", date_str)
                try:
                    date_fmt = datetime.strptime(date_raw, "%m/%d/%Y").strftime("%Y-%m-%d")
                except Exception:
                    date_fmt = date_str

                classification_records.append({
                    "number":     number,
                    "date_fmt":   date_fmt,
                    "collection": (detail.get("collection") or ruling.get("collection") or "").upper(),
                    "tariffs":    ", ".join(detail.get("tariffs") or []) or "-",
                    "subject":    detail.get("subject") or "-",
                    "text":       detail.get("text") or "",
                    "source_url": f"https://rulings.cbp.gov/ruling/{number}",
                })
            time.sleep(0.5)

        stats["in_report"] = len(classification_records)

        # ── İstatistik tablosunu ekle ──
        _add_stats_table(doc, stats, date_str)

        # ── Her sınıflandırma kararını rapora ekle ──
        for rec in classification_records:
            # Tam metin linki
            _add_ruling_link(doc, rec["source_url"])

            # Bilgi tablosu
            info_rows = [
                ("Karar Numarası", rec["number"]),
                ("Koleksiyon",     rec["collection"]),
                ("Karar Tarihi",   rec["date_fmt"]),
                ("HTS / GTİP",     rec["tariffs"]),
            ]

            # Heading ekle (add_ruling_to_doc'un heading bölümünü elle yapıyoruz)
            hp = doc.add_paragraph()
            hr = hp.add_run(f"ABD CBP Kararı: {rec['number']}  |  {rec['date_fmt']}")
            hr.bold = True
            hr.font.size = Pt(14)
            hr.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)

            add_info_table(doc, info_rows)
            doc.add_paragraph()

            # Claude 3 madde özet
            summary = summarize_cbp_ruling_claude(
                subject=rec["subject"],
                text=rec["text"],
                tariffs=rec["tariffs"],
                ruling_number=rec["number"],
            )
            _add_summary_section(doc, summary)

            doc.add_paragraph("─" * 80)
            doc.add_paragraph()

        if stats["in_report"] == 0:
            add_no_results_notice(doc)

        docx_path = date_dir / f"ABD_CBP_Kararlar_{date_str}.docx"
        doc.save(str(docx_path))
        return [docx_path]
