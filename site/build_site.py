#!/usr/bin/env python3
"""
BTI Sky — site veri üreteci.

~/BTI_Reports altındaki tüm connector çıktılarını (_report_data.json)
tarar, her sınıflandırma kararını normalize eder ve site/data.js dosyasına
`window.BTI_DATA = {...}` olarak yazar.

Böylece index.html dosyası hiçbir sunucuya ihtiyaç duymadan (file:// ile bile)
açıldığında günün kararlarını "bulutlar" halinde gösterebilir.

Kullanım:
    python3 site/build_site.py
"""

import json
import glob
import os
import re
from datetime import datetime
from collections import defaultdict

REPORTS_BASE = os.path.expanduser("~/BTI_Reports")
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

SOURCES = {
    "EU_EBTI": {"slug": "eu", "label": "Avrupa Birliği (EBTI)", "flag": "🇪🇺", "color": "#2E6BE6"},
    "US_CBP":  {"slug": "us", "label": "Amerika (CBP)",         "flag": "🇺🇸", "color": "#C0392B"},
    "CA_CBSA": {"slug": "ca", "label": "Kanada (CBSA)",          "flag": "🇨🇦", "color": "#D34040"},
}

# AB üye ülke kodları → bayrak/isim (kısa, gerekenler)
EU_COUNTRY = {
    "FR": ("Fransa", "🇫🇷"), "DE": ("Almanya", "🇩🇪"), "NL": ("Hollanda", "🇳🇱"),
    "IT": ("İtalya", "🇮🇹"), "ES": ("İspanya", "🇪🇸"), "BE": ("Belçika", "🇧🇪"),
    "PL": ("Polonya", "🇵🇱"), "AT": ("Avusturya", "🇦🇹"), "CZ": ("Çekya", "🇨🇿"),
    "SE": ("İsveç", "🇸🇪"), "DK": ("Danimarka", "🇩🇰"), "FI": ("Finlandiya", "🇫🇮"),
    "IE": ("İrlanda", "🇮🇪"), "PT": ("Portekiz", "🇵🇹"), "HU": ("Macaristan", "🇭🇺"),
    "RO": ("Romanya", "🇷🇴"), "BG": ("Bulgaristan", "🇧🇬"), "GR": ("Yunanistan", "🇬🇷"),
    "SK": ("Slovakya", "🇸🇰"), "SI": ("Slovenya", "🇸🇮"), "HR": ("Hırvatistan", "🇭🇷"),
    "LT": ("Litvanya", "🇱🇹"), "LV": ("Letonya", "🇱🇻"), "EE": ("Estonya", "🇪🇪"),
    "LU": ("Lüksemburg", "🇱🇺"), "CY": ("Kıbrıs", "🇨🇾"), "MT": ("Malta", "🇲🇹"),
}

TR_MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
             "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def hs4(code: str) -> str:
    """GTİP kodundan ilk 4 hane (sadece rakamlar)."""
    digits = re.sub(r"\D", "", code or "")
    return digits[:4]


def fmt_date_tr(iso: str) -> str:
    try:
        d = datetime.strptime(iso, "%Y-%m-%d")
        return f"{d.day} {TR_MONTHS[d.month - 1]} {d.year}"
    except Exception:
        return iso


def iso_from_any(s: str) -> str:
    """'24/05/2026' veya '2026-05-22' → '2026-05-22'."""
    s = (s or "").strip()
    if re.match(r"\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return s


def eu_source_url(ref: str, country: str, date_iso: str) -> str:
    """
    EBTI tek-karar detay sayfası — doğrudan deep link.

    EBTI public consultation oturum-bağımlı, POST ile çalışan bir aramadır ve
    dışarıdan link'le tek bir karara gidilemez (eksik parametre verilince yalnızca
    boş form / "More information can be found here" gösterir). Ancak EBTI'nin
    kendi JS'inin kullandığı detay uç noktası GET ile çalışır:

        ebti_details.jsp?showHeader=false&Lang=en&reference=<HAM_BTI_REFERANS>

    'reference' değeri CSV'deki HAM BTI_REFERENCE'tır (ülke ön ekiyle birlikte,
    ör. 'FRBTIFR-BTI-2026-02399'); URL-encode edilir. FR/DE/BE/CZ (nokta ve eğik
    çizgi içeren referanslar dahil) HTTP 200 ile kararın tam içeriğini döndürür.
    Not: showHeader=true bu uçta 500 verir; mutlaka showHeader=false kullanılır.
    """
    from urllib.parse import quote
    r = quote((ref or "").strip(), safe="")
    base = "https://ec.europa.eu/taxation_customs/dds2/ebti/ebti_details.jsp"
    return f"{base}?showHeader=false&Lang=en&reference={r}"


def clip(text: str, n: int = 220) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    return text[:n] + ("…" if len(text) > n else "")


def collect():
    by_date = defaultdict(list)  # iso_date -> [decision,...]

    for src_dir, meta in SOURCES.items():
        for f in glob.glob(f"{REPORTS_BASE}/{src_dir}/*/_report_data.json"):
            try:
                data = json.load(open(f, encoding="utf-8"))
            except Exception:
                continue
            for rec in data.get("records", []):
                dec = normalize(src_dir, meta, rec, data)
                if dec and dec["hs4"]:
                    by_date[dec["date"]].append(dec)

    return by_date


def normalize(src_dir, meta, rec, data):
    slug = meta["slug"]

    if slug == "eu":
        hs = rec.get("hs", "")
        date_iso = iso_from_any(rec.get("date_issue", ""))
        country = rec.get("country", "")
        cname, cflag = EU_COUNTRY.get(country, (country, "🇪🇺"))
        return {
            "source": "eu", "source_label": meta["label"], "color": meta["color"],
            "flag": cflag, "origin": cname,
            "hs": hs, "hs4": hs4(hs),
            "ref": rec.get("ref", ""),
            "date": date_iso,
            "title": clip(rec.get("desc_tr", ""), 280),
            "gerekce": clip(rec.get("just_tr", ""), 220),
            "url": eu_source_url(rec.get("ref", ""), country, date_iso),
        }

    if slug == "us":
        tariffs = rec.get("tariffs", "")
        first = tariffs.split(",")[0].strip() if tariffs else ""
        summ = rec.get("summary") or {}
        title = summ.get("esya_tanimi") or summ.get("summary_tr") or ""
        return {
            "source": "us", "source_label": meta["label"], "color": meta["color"],
            "flag": meta["flag"], "origin": "ABD",
            "hs": tariffs, "hs4": hs4(first),
            "ref": rec.get("number", ""),
            "date": iso_from_any(rec.get("date_fmt", "")),
            "title": clip(title, 280),
            "gerekce": clip(summ.get("teknik_gerekce", ""), 220),
            "url": rec.get("source_url", ""),
        }

    if slug == "ca":
        hts = rec.get("hts", "")
        summ = rec.get("summary") or {}
        title = summ.get("esya_tanimi") or ""
        return {
            "source": "ca", "source_label": meta["label"], "color": meta["color"],
            "flag": meta["flag"], "origin": "Kanada",
            "hs": hts, "hs4": hs4(hts),
            "ref": rec.get("ruling_id", ""),
            "date": iso_from_any(rec.get("date_fmt", "")),
            "title": clip(title, 280),
            "gerekce": clip(summ.get("teknik_gerekce", ""), 220),
            "url": rec.get("source_url", ""),
        }

    return None


def interleave_sources(decs):
    """Günün kararlarını kaynaklara göre round-robin harmanlar.
    Böylece site bulutları 60 ile sınırlasa bile her kaynaktan (AB/ABD/Kanada)
    adil sayıda bulut görünür; tek kaynak listeyi domine etmez."""
    buckets = defaultdict(list)
    for d in decs:
        buckets[d["source"]].append(d)
    # Kaynak sırası sabit: eu, us, ca (sonra varsa diğerleri)
    order = [s for s in ("eu", "us", "ca") if s in buckets]
    order += [s for s in buckets if s not in order]
    out = []
    i = 0
    while True:
        added = False
        for s in order:
            if i < len(buckets[s]):
                out.append(buckets[s][i])
                added = True
        if not added:
            break
        i += 1
    return out


def main():
    by_date = collect()

    days = []
    for iso in sorted(by_date.keys(), reverse=True):
        decs = interleave_sources(by_date[iso])
        days.append({
            "date": iso,
            "date_tr": fmt_date_tr(iso),
            "count": len(decs),
            "sources": sorted({d["source"] for d in decs}),
            "decisions": decs,
        })

    total = sum(d["count"] for d in days)
    today_iso = datetime.now().strftime("%Y-%m-%d")
    latest_iso = days[0]["date"] if days else None
    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "today": today_iso,
        "today_tr": fmt_date_tr(today_iso),
        "latest_date": latest_iso,
        "latest_is_today": (latest_iso == today_iso),
        "total_decisions": total,
        "total_days": len(days),
        "days": days,
    }

    out = os.path.join(OUT_DIR, "data.js")
    with open(out, "w", encoding="utf-8") as fp:
        fp.write("window.BTI_DATA = ")
        json.dump(payload, fp, ensure_ascii=False, indent=1)
        fp.write(";\n")

    print(f"✓ {total} karar, {len(days)} gün → {out}")
    if days:
        print(f"  En güncel gün: {days[0]['date_tr']} ({days[0]['count']} karar)")


if __name__ == "__main__":
    main()
