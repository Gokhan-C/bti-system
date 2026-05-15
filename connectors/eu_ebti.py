"""
AB EBTI Connector

Veri çekme stratejisi: TARIH BAZLI
  - Her çalışmada bir önceki günün kararları EBTI sitesinden çekilir.
  - Playwright ile Chromium üzerinden scraping yapılır.
  - ZIP indirilir → CSV zenginleştirilir → Claude CLI ile Türkçeye çevrilir
  - Node.js build_docx.js ile Word raporu üretilir.
"""

import asyncio
import csv
import json
import re
import subprocess
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from core.base_connector import BaseConnector
from core.translator import translate_all_claude


COUNTRY_NAMES = {
    'AT': 'Avusturya', 'BE': 'Belçika', 'BG': 'Bulgaristan',
    'CY': 'Kıbrıs', 'CZ': 'Çek Cumhuriyeti', 'DE': 'Almanya',
    'DK': 'Danimarka', 'EE': 'Estonya', 'ES': 'İspanya',
    'FI': 'Finlandiya', 'FR': 'Fransa', 'GB': 'Birleşik Krallık',
    'GR': 'Yunanistan', 'HR': 'Hırvatistan', 'HU': 'Macaristan',
    'IE': 'İrlanda', 'IT': 'İtalya', 'LT': 'Litvanya',
    'LU': 'Lüksemburg', 'LV': 'Letonya', 'MT': 'Malta',
    'NL': 'Hollanda', 'PL': 'Polonya', 'PT': 'Portekiz',
    'RO': 'Romanya', 'SE': 'İsveç', 'SI': 'Slovenya',
    'SK': 'Slovakya', 'XI': 'Kuzey İrlanda',
}

TR_MONTHS = {
    1: 'Ocak', 2: 'Şubat', 3: 'Mart', 4: 'Nisan', 5: 'Mayıs', 6: 'Haziran',
    7: 'Temmuz', 8: 'Ağustos', 9: 'Eylül', 10: 'Ekim', 11: 'Kasım', 12: 'Aralık',
}

CAS_RE = re.compile(r'\b(\d{2,7}-\d{2}-\d)\b')


def _format_date_tr(date_str: str) -> str:
    s = (date_str or '').strip()[:10]
    try:
        if '/' in s:
            d, m, y = s.split('/')
        elif '-' in s:
            y, m, d = s.split('-')
        else:
            return date_str
        return f"{int(d)} {TR_MONTHS[int(m)]} {y}"
    except Exception:
        return date_str


def _hs8(code: str) -> str:
    return code[:8].replace('*', '').strip()


def _detect_cas(desc: str, just: str, hs: str) -> list[str]:
    if hs[:2] not in ('28', '29'):
        return []
    return list(set(CAS_RE.findall((desc or '') + ' ' + (just or ''))))


def _build_search_url(date_hyphen: str, date_slash_encoded: str, offset: int = 1) -> str:
    base = "https://ec.europa.eu/taxation_customs/dds2/ebti/ebti_consultation.jsp"
    params = (
        f"?Lang=en&Lang=en&refcountry=&reference="
        f"&valstartdate1={date_hyphen}&valstartdate={date_slash_encoded}"
        f"&valstartdateto1={date_hyphen}&valstartdateto={date_slash_encoded}"
        f"&valenddate1=&valenddate=&valenddateto1=&valenddateto="
        f"&suppldate1=&suppldate=&nomenc=&nomencto="
        f"&keywordsearch1=&keywordsearch=&specialkeyword="
        f"&keywordmatchrule=OR&excludekeywordsearch1=&excludekeywordsearch="
        f"&excludespecialkeyword=&descript=&orderby=4"
        f"&Expand=true&offset={offset}&viewVal=&isVisitedRef=true&allRecords=0&showProgressBar=true"
    )
    return base + params


async def _scrape_page_images(page) -> tuple[dict, bool]:
    table = await page.query_selector("table.table-result")
    if not table:
        return {}, True

    rows = await table.query_selector_all("tbody tr")
    result: dict[str, int] = {}
    found_zero = False

    for row in rows:
        cells = await row.query_selector_all("td")
        if len(cells) < 6:
            continue
        bti_ref = (await cells[0].inner_text()).strip()
        try:
            num_images = int((await cells[5].inner_text()).strip())
        except ValueError:
            num_images = 0
        result[bti_ref] = num_images
        if num_images == 0:
            found_zero = True

    return result, found_zero


async def _scrape_and_download(
    target_date: datetime, output_dir: Path, logger=None
) -> tuple[Path | None, dict]:
    from playwright.async_api import async_playwright

    date_hyphen = target_date.strftime("%d-%m-%Y")
    date_slash_encoded = quote(target_date.strftime("%d/%m/%Y"), safe="")

    if logger:
        logger.info(f"AB EBTI: {date_hyphen} tarihli BTI'lar aranıyor...")

    bti_image_map: dict[str, int] = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        search_url = _build_search_url(date_hyphen, date_slash_encoded)
        await page.goto(search_url, wait_until="load", timeout=120000)

        body_text = await page.inner_text("body")
        if "0 results match" in body_text or "results match your search" not in body_text:
            if logger:
                logger.warning(f"AB EBTI: {date_hyphen} için sonuç bulunamadı.")
            await browser.close()
            return None, {}

        page_num = 1
        while True:
            page_data, found_zero = await _scrape_page_images(page)
            bti_image_map.update(page_data)
            if found_zero:
                break
            next_link = await page.query_selector("a:has-text('Next')")
            if not next_link:
                break
            await next_link.click()
            await page.wait_for_load_state("networkidle")
            page_num += 1

        if logger:
            images_with = sum(1 for v in bti_image_map.values() if v > 0)
            logger.info(f"AB EBTI: {len(bti_image_map)} BTI tarandı, {images_with} resim içeriyor.")

        output_dir.mkdir(parents=True, exist_ok=True)
        zip_path = output_dir / f"BTI_{target_date.strftime('%Y%m%d')}.zip"

        async with page.expect_download(timeout=120000) as dl_info:
            clicked = await page.evaluate("""() => {
                const btn = Array.from(document.querySelectorAll('button, a'))
                    .find(el => el.textContent.trim().includes('Download Search result'));
                if (btn) { btn.click(); return true; }
                return false;
            }""")
            if not clicked:
                raise RuntimeError("'Download Search result' butonu bulunamadı!")

        download = await dl_info.value
        await download.save_as(zip_path)
        await browser.close()

    return zip_path, bti_image_map


def _extract_and_enrich_csv(
    zip_path: Path, bti_image_map: dict, output_dir: Path, target_date: datetime
) -> Path:
    csv_out_path = output_dir / f"BTI_{target_date.strftime('%Y%m%d')}.csv"

    with zipfile.ZipFile(zip_path, "r") as z:
        csv_files = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not csv_files:
            raise ValueError(f"ZIP içinde CSV bulunamadı: {zip_path}")
        raw_bytes = z.open(csv_files[0]).read()

    content = raw_bytes.decode("utf-8-sig", errors="replace")
    lines = content.splitlines()
    reader = csv.DictReader(lines)
    fieldnames = list(reader.fieldnames or [])

    has_image_col = any("image" in f.lower() for f in fieldnames)
    extra_fields = [] if has_image_col else ["Resim_Sayisi", "Resim_Var"]

    rows_out = []
    for row in reader:
        bti_ref = (
            row.get("BTI_REFERENCE") or row.get("BTI Reference")
            or row.get("Reference") or row.get("BTI_Reference") or ""
        ).strip()
        if not has_image_col:
            num_images = bti_image_map.get(bti_ref, 0)
            row["Resim_Sayisi"] = str(num_images)
            row["Resim_Var"] = "EVET" if num_images > 0 else "HAYIR"
        rows_out.append(row)

    with open(csv_out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames + extra_fields)
        writer.writeheader()
        writer.writerows(rows_out)

    return csv_out_path


class EuEbtiConnector(BaseConnector):

    @property
    def connector_id(self) -> str:
        return "eu_ebti"

    @property
    def display_name(self) -> str:
        return self.config.get("display_name", "Avrupa Birliği EBTI")

    def extract_id(self, record: dict[str, Any]) -> str:
        return (
            record.get("BTI_REFERENCE")
            or record.get("BTI Reference")
            or record.get("Reference")
            or record.get("BTI_Reference")
            or ""
        ).strip()

    def deduplicate(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        AB EBTI override: tarih bazlı çekim yapıldığı için, her gün o günün TÜM BTI'leri
        rapora girer (gerek olmayan dedup kaldırıldı).
        Yine de state dosyasını güncelliyoruz (geçmiş takip için).
        """
        for r in records:
            rid = self.extract_id(r)
            if rid:
                self._seen_ids.add(rid)
        if records:
            self._save_seen_ids()
        return records  # TÜMÜNÜ döndür, dedup yok

    def fetch(self, target_date: datetime) -> list[dict[str, Any]]:
        date_dir = self.output_dir / target_date.strftime("%Y-%m-%d")
        date_dir.mkdir(parents=True, exist_ok=True)

        zip_path, bti_image_map = asyncio.run(
            _scrape_and_download(target_date, date_dir, logger=None)
        )

        if zip_path is None:
            return []

        csv_path = _extract_and_enrich_csv(zip_path, bti_image_map, date_dir, target_date)

        with open(csv_path, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))

        return rows

    def build_report(
        self, records: list[dict[str, Any]], target_date: datetime
    ) -> list[Path]:
        date_dir = self.output_dir / target_date.strftime("%Y-%m-%d")
        date_dir.mkdir(parents=True, exist_ok=True)

        batch_size = self.config.get("claude_batch_size", 8)
        translated = translate_all_claude(records, batch_size=batch_size)

        dates = [
            r.get("DATE_OF _ISSUE", "").strip()[:10]
            for r in translated
            if r.get("DATE_OF _ISSUE", "").strip()
        ]
        report_date_raw = Counter(dates).most_common(1)[0][0] if dates else target_date.strftime("%Y-%m-%d")
        report_date_tr = _format_date_tr(report_date_raw)

        report_records = []
        for row in translated:
            hs = _hs8(row.get("NOMENCLATURE_CODE", ""))
            desc_orig = (row.get("DESCRIPTION_OF_GOODS") or "").strip()
            just_orig = (row.get("CLASSIFICATION_JUSTIFICATION") or "").strip()
            cas_list = _detect_cas(desc_orig, just_orig, hs)

            report_records.append({
                "ref":        (row.get("BTI_REFERENCE") or row.get("BTI Reference") or "").strip(),
                "country":    row.get("ISSUING_COUNTRY", "").strip(),
                "hs":         hs,
                "date_issue": (row.get("DATE_OF _ISSUE") or "").strip(),
                "desc_tr":    row.get("desc_tr", desc_orig),
                "just_tr":    row.get("just_tr", just_orig),
                "has_image":  row.get("Resim_Var", "HAYIR") == "EVET",
                "num_images": int(row.get("Resim_Sayisi") or 0),
                "cas":        cas_list,
            })

        country_counter = Counter(r["country"] for r in report_records)
        gtip_counter = Counter(r["hs"] for r in report_records)

        data = {
            "report_date_raw": report_date_raw,
            "report_date_tr":  report_date_tr,
            "total":           len(report_records),
            "country_count":   len(country_counter),
            "country_stats":   [
                {"code": c, "name": COUNTRY_NAMES.get(c, c), "count": n}
                for c, n in country_counter.most_common()
            ],
            "gtip_top10": [
                {"hs": h, "count": n} for h, n in gtip_counter.most_common(10)
            ],
            "records": report_records,
        }

        # Birleşik rapor için veriyi sakla
        self._report_data = data
        # JSON'a kalıcı kaydet — records_new=0 olduğunda orchestrator buradan okur
        (date_dir / "_report_data.json").write_text(
            json.dumps(self._report_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        json_path = date_dir / "_eu_report_tmp.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        date_compact = report_date_tr.replace(" ", "")
        docx_path = date_dir / f"AB_EBTI_Rapor_{date_compact}.docx"

        docx_script = Path(
            self.config.get("docx_script", "~/Desktop/claude/code/bti_system/assets/build_docx.js")
        ).expanduser()

        result = subprocess.run(
            ["node", str(docx_script), str(json_path), str(docx_path)],
            capture_output=True, text=True,
        )
        json_path.unlink(missing_ok=True)

        if result.returncode != 0:
            raise RuntimeError(f"Node.js hatası:\n{result.stderr[:600]}")

        return [docx_path]

    def get_report_data(
        self, records: list[dict[str, Any]], target_date: datetime
    ) -> dict | None:
        """
        Orchestrator'ın unified rapor için veriyi almasına izin verir.
        build_report() ile aynı veriyi döndürür ama .docx üretmez.
        """
        if not records:
            return None

        batch_size = self.config.get("claude_batch_size", 8)
        translated = translate_all_claude(records, batch_size=batch_size)

        dates = [
            r.get("DATE_OF _ISSUE", "").strip()[:10]
            for r in translated
            if r.get("DATE_OF _ISSUE", "").strip()
        ]
        report_date_raw = Counter(dates).most_common(1)[0][0] if dates else target_date.strftime("%Y-%m-%d")
        report_date_tr = _format_date_tr(report_date_raw)

        report_records = []
        for row in translated:
            hs = _hs8(row.get("NOMENCLATURE_CODE", ""))
            desc_orig = (row.get("DESCRIPTION_OF_GOODS") or "").strip()
            just_orig = (row.get("CLASSIFICATION_JUSTIFICATION") or "").strip()
            cas_list = _detect_cas(desc_orig, just_orig, hs)
            report_records.append({
                "ref":        (row.get("BTI_REFERENCE") or row.get("BTI Reference") or "").strip(),
                "country":    row.get("ISSUING_COUNTRY", "").strip(),
                "hs":         hs,
                "date_issue": (row.get("DATE_OF _ISSUE") or "").strip(),
                "desc_tr":    row.get("desc_tr", desc_orig),
                "just_tr":    row.get("just_tr", just_orig),
                "has_image":  row.get("Resim_Var", "HAYIR") == "EVET",
                "num_images": int(row.get("Resim_Sayisi") or 0),
                "cas":        cas_list,
            })

        country_counter = Counter(r["country"] for r in report_records)
        gtip_counter = Counter(r["hs"] for r in report_records)

        return {
            "report_date_raw": report_date_raw,
            "report_date_tr":  report_date_tr,
            "total":           len(report_records),
            "country_count":   len(country_counter),
            "country_stats":   [
                {"code": c, "name": COUNTRY_NAMES.get(c, c), "count": n}
                for c, n in country_counter.most_common()
            ],
            "gtip_top10": [
                {"hs": h, "count": n} for h, n in gtip_counter.most_common(10)
            ],
            "records": report_records,
        }
