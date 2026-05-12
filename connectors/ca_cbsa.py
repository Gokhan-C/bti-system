"""
Kanada CBSA Connector

Veri çekme stratejisi: YENİ KARAR TESPİTİ
  - CBSA CARM API'den ruling listesi çekilir.
  - state/ca_cbsa_seen.json ile karşılaştırılır → sadece yeni rulingsId'ler işlenir.
  - Sadece HS tarife sınıflandırması kararları alınır.
  - Google Translate ile Türkçeye çevrilir.
  - python-docx ile Word raporu üretilir.
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from core.base_connector import BaseConnector
from core.report_builder import make_doc, add_ruling_to_doc, add_no_results_notice
from core.translator import translate_google


CBSA_LIST_URL = "https://ccp-pcc.cbsa-asfc.cloud-nuage.canada.ca/carmwebservices/v2/carm/publicrulings/list"
CBSA_DETAIL_URL = "https://ccp-pcc.cbsa-asfc.cloud-nuage.canada.ca/carmwebservices/v2/carm/publicrulings/rulingsdetails/{id}"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://ccp-pcc.cbsa-asfc.cloud-nuage.canada.ca/en/national-rulings",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}

HS_KEYWORDS = [
    "CATEGORY: CLASSIFICATION", "TARIFF CLASSIFICATION",
    "HTS ", "HTSUS ", "HARMONIZED TARIFF",
]


def _is_hs_classification(detail: dict) -> bool:
    if detail.get("tariffs"):
        return True
    text = (detail.get("text") or detail.get("analysisAndJustification") or "").upper()
    subject = (detail.get("subject") or detail.get("decision") or "").upper()
    return any(kw in text[:500] or kw in subject for kw in HS_KEYWORDS)


def _fetch_list(api_url: str, logger=None) -> list[dict]:
    try:
        r = requests.get(
            api_url,
            params={"lang": "en", "curr": "CAD"},
            headers=HEADERS,
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            return data
        return data.get("items", data.get("rulings", []))
    except Exception as e:
        if logger:
            logger.error(f"Kanada CBSA list API hatası: {e}")
        return []


def _fetch_detail(ruling_id: str, detail_url_tpl: str, logger=None) -> dict:
    url = detail_url_tpl.format(id=ruling_id) + "?lang=en&curr=CAD"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        if logger:
            logger.warning(f"Kanada CBSA detay hatası ({ruling_id}): {e}")
        return {}


class CaCbsaConnector(BaseConnector):

    @property
    def connector_id(self) -> str:
        return "ca_cbsa"

    @property
    def display_name(self) -> str:
        return self.config.get("display_name", "Kanada CBSA")

    def extract_id(self, record: dict[str, Any]) -> str:
        return str(
            record.get("rulingsId")
            or record.get("rulingId")
            or record.get("id")
            or record.get("caseNumber")
            or ""
        )

    def fetch(self, target_date: datetime) -> list[dict[str, Any]]:
        api_url = self.config.get("api_url", CBSA_LIST_URL)
        items = _fetch_list(api_url)
        # extract_id için her item'a normalize edilmiş id ekle
        for item in items:
            item["_normalized_id"] = self.extract_id(item)
        return items

    def build_report(
        self, records: list[dict[str, Any]], target_date: datetime
    ) -> list[Path]:
        date_str = target_date.strftime("%Y-%m-%d")
        date_dir = self.output_dir / date_str
        date_dir.mkdir(parents=True, exist_ok=True)

        detail_url_tpl = self.config.get("api_detail_url", CBSA_DETAIL_URL)
        doc = make_doc(
            "Kanada CBSA Tarife Sınıflandırma Kararları",
            f"CBSA  |  {date_str}",
        )
        count = 0

        for ruling in records:
            ruling_id = self.extract_id(ruling)
            date_fmt = (
                ruling.get("date") or ruling.get("dateOfDecision") or date_str
            )[:10]
            product = (
                ruling.get("product") or ruling.get("productName")
                or ruling.get("description") or "-"
            )
            hts = ruling.get("classificationNumber") or ruling.get("tariffCode") or "-"
            ruling_type = ruling.get("typeOfRuling") or ruling.get("rulingType") or "-"

            detail = _fetch_detail(ruling_id, detail_url_tpl)
            if not _is_hs_classification(detail):
                continue

            analysis = detail.get("analysisAndJustification") or detail.get("analysis") or ""
            decision = detail.get("decision") or "-"
            applicant = detail.get("applicantName") or detail.get("applicant") or "-"
            origin = detail.get("countryOfOrigin") or detail.get("origin") or "-"
            prod_desc = detail.get("productDescription") or detail.get("description") or product

            prod_desc_tr = translate_google(prod_desc)
            analysis_tr = translate_google(analysis)
            decision_tr = translate_google(decision)

            info_rows = [
                ("Karar Numarası", ruling_id),
                ("Karar Türü",     ruling_type),
                ("Karar Tarihi",   date_fmt),
                ("GTİP Kodu",      hts),
                ("Başvurucu",      applicant),
                ("Menşe Ülke",     origin),
                ("Kaynak",         f"https://ccp-pcc.cbsa-asfc.cloud-nuage.canada.ca/en/national-rulings/national-rulings-details/{ruling_id}"),
            ]
            sections = [
                ("Ürün Tanımı", prod_desc_tr),
                ("Karar Gerekçesi (Türkçe)", analysis_tr if analysis_tr else "Metin bulunamadı."),
                ("Karar", decision_tr),
            ]
            add_ruling_to_doc(
                doc,
                f"Kanada CBSA Kararı: {ruling_id}  |  {date_fmt}",
                info_rows,
                sections,
            )
            count += 1
            time.sleep(0.5)

        if count == 0:
            add_no_results_notice(doc)

        docx_path = date_dir / f"Kanada_CBSA_Kararlar_{date_str}.docx"
        doc.save(str(docx_path))
        return [docx_path]

    def get_processed_records(
        self, records: list[dict[str, Any]], target_date: datetime
    ) -> list[dict[str, Any]]:
        """
        Orchestrator'ın unified rapor için işlenmiş veriyi almasına izin verir.
        """
        date_str = target_date.strftime("%Y-%m-%d")
        detail_url_tpl = self.config.get("api_detail_url", CBSA_DETAIL_URL)
        processed = []

        for ruling in records:
            ruling_id = self.extract_id(ruling)
            date_fmt = (
                ruling.get("date") or ruling.get("dateOfDecision") or date_str
            )[:10]
            product = (
                ruling.get("product") or ruling.get("productName")
                or ruling.get("description") or "-"
            )
            hts = ruling.get("classificationNumber") or ruling.get("tariffCode") or "-"
            ruling_type = ruling.get("typeOfRuling") or ruling.get("rulingType") or "-"

            detail = _fetch_detail(ruling_id, detail_url_tpl)
            if not _is_hs_classification(detail):
                continue

            analysis = detail.get("analysisAndJustification") or detail.get("analysis") or ""
            decision = detail.get("decision") or "-"
            applicant = detail.get("applicantName") or detail.get("applicant") or "-"
            origin = detail.get("countryOfOrigin") or detail.get("origin") or "-"
            prod_desc = detail.get("productDescription") or detail.get("description") or product

            processed.append({
                "ruling_id":    ruling_id,
                "ruling_type":  ruling_type,
                "date_fmt":     date_fmt,
                "hts":          hts,
                "applicant":    applicant,
                "origin":       origin,
                "prod_desc_tr": translate_google(prod_desc),
                "analysis_tr":  translate_google(analysis),
                "decision_tr":  translate_google(decision),
                "source_url":   f"https://ccp-pcc.cbsa-asfc.cloud-nuage.canada.ca/en/national-rulings/national-rulings-details/{ruling_id}",
            })
            time.sleep(0.5)

        return processed
