"""
ABD CBP Connector

Veri çekme stratejisi: YENİ KARAR TESPİTİ
  - CBP API'den en son yayınlanan kararlar çekilir.
  - state/us_cbp_seen.json ile karşılaştırılır → sadece yeni ruling numaraları işlenir.
  - Sadece HS tarife sınıflandırması kararları alınır.
  - Google Translate ile Türkçeye çevrilir.
  - python-docx ile Word raporu üretilir.
"""

import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from core.base_connector import BaseConnector
from core.report_builder import make_doc, add_ruling_to_doc, add_no_results_notice
from core.translator import translate_google


CBP_API_RECENT = "https://rulings.cbp.gov/api/stat/recentRulings"
CBP_API_DETAIL = "https://rulings.cbp.gov/api/ruling/{number}"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://rulings.cbp.gov/home",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}

HS_KEYWORDS = [
    "CATEGORY: CLASSIFICATION", "CATEGORY:  CLASSIFICATION",
    "TARIFF CLASSIFICATION", "HTS ", "HTSUS ", "HARMONIZED TARIFF",
]


def _is_hs_classification(detail: dict) -> bool:
    if detail.get("tariffs"):
        return True
    text = (detail.get("text") or "").upper()
    subject = (detail.get("subject") or "").upper()
    return any(kw in text[:500] or kw in subject for kw in HS_KEYWORDS)


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
        recent_days = self.config.get("recent_days", 2)
        rulings = _fetch_recent_rulings(recent_days)
        result = []
        for ruling in rulings:
            number = ruling.get("rulingNumber", "")
            if not number:
                continue
            # Deduplication'dan önce ID ataması (extract_id için)
            ruling["id"] = number
            ruling["rulingNumber"] = number
            result.append(ruling)
        return result

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
        count = 0

        for ruling in records:
            number = ruling.get("rulingNumber", "UNKNOWN")
            date_raw = ruling.get("dateModified", date_str)
            try:
                date_fmt = datetime.strptime(date_raw, "%m/%d/%Y").strftime("%Y-%m-%d")
            except Exception:
                date_fmt = date_str

            detail = _fetch_detail(number)
            if not _is_hs_classification(detail):
                continue

            subject = detail.get("subject") or "-"
            tariffs = ", ".join(detail.get("tariffs") or []) or "-"
            text = detail.get("text") or ""
            ruling_date = (detail.get("rulingDate") or "")[:10] or date_fmt
            collection = (detail.get("collection") or ruling.get("collection") or "").upper()

            subject_tr = translate_google(subject)
            text_tr = translate_google(text)

            info_rows = [
                ("Karar Numarası", number),
                ("Koleksiyon",     collection),
                ("Karar Tarihi",   ruling_date),
                ("HTS / GTİP",     tariffs),
                ("Kaynak",         f"https://rulings.cbp.gov/ruling/{number}"),
            ]
            sections = [
                ("Konu", subject_tr),
                ("Karar Tam Metni (Türkçe)", text_tr if text_tr else "Metin bulunamadı."),
            ]
            add_ruling_to_doc(doc, f"ABD CBP Kararı: {number}  |  {ruling_date}", info_rows, sections)
            count += 1
            time.sleep(0.5)  # API'ye nazik ol

        if count == 0:
            add_no_results_notice(doc)

        docx_path = date_dir / f"ABD_CBP_Kararlar_{date_str}.docx"
        doc.save(str(docx_path))
        return [docx_path]

    def get_processed_records(
        self, records: list[dict[str, Any]], target_date: datetime
    ) -> list[dict[str, Any]]:
        """
        Orchestrator'ın unified rapor için işlenmiş veriyi almasına izin verir.
        Her karar için detay çeker, HTS filtresi uygular, Türkçe çeviri ekler.
        """
        date_str = target_date.strftime("%Y-%m-%d")
        processed = []
        for ruling in records:
            number = ruling.get("rulingNumber", "UNKNOWN")
            date_raw = ruling.get("dateModified", date_str)
            try:
                date_fmt = datetime.strptime(date_raw, "%m/%d/%Y").strftime("%Y-%m-%d")
            except Exception:
                date_fmt = date_str

            detail = _fetch_detail(number)
            if not _is_hs_classification(detail):
                continue

            subject = detail.get("subject") or "-"
            tariffs = ", ".join(detail.get("tariffs") or []) or "-"
            text = detail.get("text") or ""
            ruling_date = (detail.get("rulingDate") or "")[:10] or date_fmt
            collection = (detail.get("collection") or ruling.get("collection") or "").upper()

            processed.append({
                "number":      number,
                "collection":  collection,
                "ruling_date": ruling_date,
                "tariffs":     tariffs,
                "subject_tr":  translate_google(subject),
                "text_tr":     translate_google(text),
                "source_url":  f"https://rulings.cbp.gov/ruling/{number}",
            })
            time.sleep(0.5)

        return processed
