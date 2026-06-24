"""
Türkiye BTB Connector (Bağlayıcı Tarife Bilgisi)

Veri kaynağı: Ticaret Bakanlığı halka açık BTB sorgulama sistemi
    https://uygulama.gtb.gov.tr/BTBBasvuru/BtbWebArama
(ASP.NET WebForms + AJAX UpdatePanel — Playwright ile sürülür.)

Strateji: KÜMÜLATİF (yıl bazlı)
  - Yıl seçilip "BUL" ile o yılın tüm BTB'leri sayfalı GridView'den listelenir
    (BTB No, GTİP, kısa eşya tanımı, geçerlilik başlama tarihi).
  - State dosyasıyla karşılaştırılır; yalnızca YENİ BTB'ler için BTB No ile tekil
    arama yapılıp DETAY panelinden TAM eşya tanımı + sınıflandırma gerekçesi çekilir.
  - Veri zaten Türkçe olduğu için çeviri adımı YOKTUR.
  - Tek-karar için kalıcı kaynak URL'si olmadığından (detay postback ile açılıyor)
    site bulutları resmî sorgu sayfasına yönlendirir.
"""

import asyncio
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from core.base_connector import BaseConnector

URL = "https://uygulama.gtb.gov.tr/BTBBasvuru/BtbWebArama"
PFX = "ctl00_ContentPlaceHolder1_"
SEARCH_PAGE = URL

TR_MONTHS = {
    1: 'Ocak', 2: 'Şubat', 3: 'Mart', 4: 'Nisan', 5: 'Mayıs', 6: 'Haziran',
    7: 'Temmuz', 8: 'Ağustos', 9: 'Eylül', 10: 'Ekim', 11: 'Kasım', 12: 'Aralık',
}

# GridView satırlarını oku (sadece veri satırları: ilk hücrede 'TR..' linki olanlar)
_JS_ROWS = """() => {
  const t = document.getElementById('ctl00_ContentPlaceHolder1_GridView1');
  if (!t) return [];
  const out = [];
  for (const r of t.rows) {
    const c = r.cells; if (!c || c.length < 4) continue;
    const a = c[0].querySelector('a'); if (!a) continue;
    const ref = a.innerText.trim();
    if (!/^TR/.test(ref)) continue;
    out.push({ ref, gtip: c[1].innerText.trim(),
               desc_short: c[2].innerText.trim(), date: c[3].innerText.trim() });
  }
  return out;
}"""

# Sayfalama: mevcut sayfa (span) + tıklanabilir sayfa linkleri (sayı veya '...')
_JS_PAGER = """() => {
  const t = document.getElementById('ctl00_ContentPlaceHolder1_GridView1');
  const links = new Set(); let current = null;
  if (t) {
    t.querySelectorAll('a').forEach(a => { const x = a.innerText.trim();
      if (/^\\d+$/.test(x) || x === '...') links.add(x); });
    t.querySelectorAll('span').forEach(s => { const x = s.innerText.trim();
      if (/^\\d+$/.test(x)) current = x; });
  }
  return { links: [...links], current };
}"""

# Detay panelindeki label'lar
_JS_DETAIL = """() => {
  const g = id => { const e = document.getElementById('ctl00_ContentPlaceHolder1_' + id);
                    return e ? e.innerText.trim() : ''; };
  return { ref: g('lblBtbNo'), gtip: g('lblGtip'), date: g('lblGbastar'),
           gerekce: g('lblSinger'), esya: g('lblEstanim') };
}"""


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _format_date_tr(date_str: str) -> str:
    s = (date_str or "").strip()[:10]
    try:
        if "/" in s:
            d, m, y = s.split("/")
        elif "-" in s:
            y, m, d = s.split("-")
        else:
            return date_str
        return f"{int(d)} {TR_MONTHS[int(m)]} {y}"
    except Exception:
        return date_str


async def _collect_all_rows(page) -> dict[str, dict]:
    """Sayfalı GridView'in tüm sayfalarını gezerek ref->satır sözlüğü döndürür."""
    rows_by_ref: dict[str, dict] = {}
    stuck = 0
    for _ in range(80):  # güvenlik üst sınırı
        await page.wait_for_selector(f"#{PFX}GridView1", timeout=30000)
        before = len(rows_by_ref)
        for r in await page.evaluate(_JS_ROWS):
            rows_by_ref[r["ref"]] = r

        info = await page.evaluate(_JS_PAGER)
        cur = int(info["current"]) if (info["current"] or "").isdigit() else len(rows_by_ref) // 16 + 1
        nxt = str(cur + 1)
        links = info["links"]

        clicked = False
        try:
            if nxt in links:
                await page.click(f"#{PFX}GridView1 a:text-is('{nxt}')")
                clicked = True
            elif "..." in links:
                # İleri yönlü "..." daima sonuncudur (geri "..." varsa ilk sıradadır)
                await page.locator(f"#{PFX}GridView1 a", has_text="...").last.click()
                clicked = True
        except Exception:
            clicked = False

        if not clicked:
            break

        try:
            await page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        await page.wait_for_timeout(700)

        # ilerleme yoksa (yeni ref gelmedi) iki turda dur
        stuck = stuck + 1 if len(rows_by_ref) == before else 0
        if stuck >= 2:
            break

    return rows_by_ref


async def _fetch_detail(page, ref: str) -> dict:
    """BTB No ile tekil arama yapıp DETAY panelinden tam alanları döndürür."""
    await page.goto(URL, wait_until="load", timeout=60000)
    await page.fill(f"#{PFX}txtBtbno", ref)
    await page.click(f"#{PFX}btnBul")
    try:
        await page.wait_for_selector(f"#{PFX}GridView1 a", timeout=20000)
    except Exception:
        return {}
    try:
        await page.locator(f"#{PFX}GridView1 a", has_text=ref).first.click()
    except Exception:
        try:
            await page.click(f"#{PFX}GridView1 tr:nth-child(2) a")
        except Exception:
            return {}
    try:
        await page.wait_for_selector(f"#{PFX}lblEstanim", timeout=20000)
    except Exception:
        return {}
    await page.wait_for_timeout(300)
    return await page.evaluate(_JS_DETAIL)


class TrBtbConnector(BaseConnector):

    @property
    def connector_id(self) -> str:
        return "tr_btb"

    @property
    def display_name(self) -> str:
        return self.config.get("display_name", "Türkiye BTB")

    def extract_id(self, record: dict[str, Any]) -> str:
        return (record.get("ref") or "").strip()

    # ── Veri çekme ─────────────────────────────────────────────────────────
    def fetch(self, target_date: datetime) -> list[dict[str, Any]]:
        return asyncio.run(self._afetch(target_date))

    async def _afetch(self, target_date: datetime) -> list[dict[str, Any]]:
        from playwright.async_api import async_playwright

        year = target_date.year
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await (await browser.new_context()).new_page()
            await page.goto(URL, wait_until="load", timeout=60000)

            # Yıl seç + BUL
            try:
                await page.select_option(f"#{PFX}DropDownList5", label=str(year))
            except Exception:
                await page.select_option(f"#{PFX}DropDownList5", value=str(year))
            await page.click(f"#{PFX}btnBul")
            await page.wait_for_selector(f"#{PFX}GridView1", timeout=30000)

            rows_by_ref = await _collect_all_rows(page)
            rows = list(rows_by_ref.values())

            # Yalnız YENİ BTB'ler için detay çek (tam tanım + gerekçe)
            new_refs = [r for r in rows if r["ref"] not in self._seen_ids]
            for r in new_refs:
                detail = await _fetch_detail(page, r["ref"])
                if detail:
                    r["esya_tanimi"] = detail.get("esya") or r.get("desc_short", "")
                    r["gerekce"] = detail.get("gerekce", "")
                    if detail.get("gtip"):
                        r["gtip"] = detail["gtip"]
                    if detail.get("date"):
                        r["date"] = detail["date"]

            await browser.close()

        return rows

    # ── Rapor verisi üretimi (site _report_data.json) ───────────────────────
    def _build_data(self, records: list[dict[str, Any]], target_date: datetime) -> dict:
        report_records = []
        for r in records:
            gtip = (r.get("gtip") or "").strip()
            report_records.append({
                "ref":        (r.get("ref") or "").strip(),
                "gtip":       gtip,
                "hs":         _digits(gtip)[:8],
                "date_issue": (r.get("date") or "").strip(),
                "desc_tr":    r.get("esya_tanimi") or r.get("desc_short", ""),
                "just_tr":    r.get("gerekce", ""),
            })

        dates = [_digits_date(r["date_issue"]) for r in report_records if r["date_issue"]]
        report_date_raw = Counter(dates).most_common(1)[0][0] if dates else target_date.strftime("%d/%m/%Y")
        gtip_counter = Counter(r["hs"] for r in report_records if r["hs"])

        return {
            "report_date_raw": report_date_raw,
            "report_date_tr":  _format_date_tr(report_date_raw),
            "total":           len(report_records),
            "country_count":   1,
            "country_stats":   [{"code": "TR", "name": "Türkiye", "count": len(report_records)}],
            "gtip_top10":      [{"hs": h, "count": n} for h, n in gtip_counter.most_common(10)],
            "records":         report_records,
        }

    def build_report(self, records: list[dict[str, Any]], target_date: datetime) -> list[Path]:
        date_dir = self.output_dir / target_date.strftime("%Y-%m-%d")
        date_dir.mkdir(parents=True, exist_ok=True)

        data = self._build_data(records, target_date)
        self._report_data = data
        (date_dir / "_report_data.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # TR için ayrı .docx şablonu yok; site/birleşik rapor JSON'dan okur.
        return []

    def get_report_data(self, records: list[dict[str, Any]], target_date: datetime) -> dict | None:
        if not records:
            return None
        return self._build_data(records, target_date)


def _digits_date(s: str) -> str:
    """'12/06/2026' biçimini olduğu gibi döndürür (sayaç için anahtar)."""
    return (s or "").strip()[:10]
