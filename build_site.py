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
    "TR_BTB":  {"slug": "tr", "label": "Türkiye (BTB)",         "flag": "🇹🇷", "color": "#E30A17"},
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


def us_source_url(number: str, collection: str) -> str:
    """ABD/CBP ruling için ÇALIŞAN dış kaynak linki (customsmobile aynası).

    CBP CROSS (rulings.cbp.gov) tek-karar deep-link'lerini Akamai ile dışarıdan
    engelliyor (403 Access Denied). customsmobile.com aynı CBP ruling'lerini
    GET ile erişilebilir gösterir:
        rulings/docview?doc_id=<KOLEKSİYON> <NUMARA>   (ör. "NY N358843")
    Koleksiyon yoksa yalnız numara denenir.
    """
    from urllib.parse import quote
    num = (number or "").strip()
    coll = (collection or "").strip()
    doc_id = f"{coll} {num}".strip() if coll else num
    return f"https://www.customsmobile.com/rulings/docview?doc_id={quote(doc_id)}"


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
            "url": us_source_url(rec.get("number", ""), rec.get("collection", "")),
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

    if slug == "tr":
        gtip = rec.get("gtip") or rec.get("hs", "")
        ref = rec.get("ref", "")
        return {
            "source": "tr", "source_label": meta["label"], "color": meta["color"],
            "flag": meta["flag"], "origin": "Türkiye",
            "hs": gtip, "hs4": hs4(gtip),
            "ref": ref,
            "date": iso_from_any(rec.get("date_issue", "")),
            "title": clip(rec.get("desc_tr", ""), 280),
            "gerekce": clip(rec.get("just_tr", ""), 220),
            # Resmî sitede tek-karar GET URL'si yok → kendi ürettiğimiz statik
            # detay sayfasına bağla (tam metin + resmî doğrulama linki).
            "url": f"tr/{tr_slug(ref)}.html",
        }

    return None


def tr_slug(ref: str) -> str:
    """BTB No'yu güvenli dosya adına çevirir (TR330000260021 → aynı)."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", (ref or "").strip()) or "btb"


def interleave_sources(decs):
    """Günün kararlarını kaynaklara göre round-robin harmanlar.
    Böylece site bulutları 60 ile sınırlasa bile her kaynaktan (AB/ABD/Kanada)
    adil sayıda bulut görünür; tek kaynak listeyi domine etmez."""
    buckets = defaultdict(list)
    for d in decs:
        buckets[d["source"]].append(d)
    # Kaynak sırası sabit: eu, us, ca, tr (sonra varsa diğerleri)
    order = [s for s in ("eu", "us", "ca", "tr") if s in buckets]
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


TR_OFFICIAL = "https://uygulama.gtb.gov.tr/BTBBasvuru/BtbWebArama"


def write_tr_detail_pages():
    """Her Türk BTB için statik detay sayfası (site/tr/<BTBNO>.html) üretir.
    Bulutlar bu sayfaya bağlanır; tıklayınca kararın tam metni açılır."""
    import html as _html

    out_dir = os.path.join(OUT_DIR, "tr")
    os.makedirs(out_dir, exist_ok=True)
    count = 0

    for f in glob.glob(f"{REPORTS_BASE}/TR_BTB/*/_report_data.json"):
        try:
            data = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        for rec in data.get("records", []):
            ref = (rec.get("ref") or "").strip()
            if not ref:
                continue
            gtip = (rec.get("gtip") or rec.get("hs", "")).strip()
            date_tr = fmt_date_tr(iso_from_any(rec.get("date_issue", "")))
            desc = _html.escape(rec.get("desc_tr", "") or "").replace("\n", "<br>")
            just = _html.escape(rec.get("just_tr", "") or "").replace("\n", "<br>")
            e_ref, e_gtip = _html.escape(ref), _html.escape(gtip)

            page = f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e_ref} · Türkiye BTB · GTİP {hs4(gtip)}</title>
<style>
 *{{box-sizing:border-box}}
 body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
   background:#eef3fb;color:#16202b;line-height:1.6}}
 .wrap{{max-width:760px;margin:0 auto;padding:32px 22px 64px}}
 a.back{{display:inline-flex;align-items:center;gap:7px;color:#5f7184;text-decoration:none;font-size:14px;font-weight:600}}
 a.back:hover{{color:#16202b}}
 .card{{background:#fff;border:1px solid #e6ebf2;border-radius:20px;padding:34px 32px;margin-top:18px;
   box-shadow:0 14px 40px rgba(40,90,160,.07)}}
 .tag{{display:inline-flex;align-items:center;gap:8px;font-size:13px;font-weight:700;color:#e30a17}}
 .tag i{{width:10px;height:10px;border-radius:50%;background:#e30a17;display:inline-block}}
 h1{{font-size:30px;letter-spacing:-1px;margin:14px 0 4px;font-family:'Space Grotesk',sans-serif}}
 .meta{{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px}}
 .chip{{background:#f4f7fc;border:1px solid #e6ebf2;border-radius:11px;padding:9px 14px;font-size:13px}}
 .chip b{{display:block;font-size:11px;color:#8693a6;font-weight:700;letter-spacing:.04em;text-transform:uppercase;margin-bottom:2px}}
 .chip .mono{{font-family:'JetBrains Mono',ui-monospace,monospace;font-weight:700}}
 .sec{{margin-top:26px}}
 .sec h2{{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#6f86ad;margin:0 0 7px}}
 .sec p{{margin:0;font-size:15.5px;color:#23303f}}
 .official{{display:inline-flex;align-items:center;gap:8px;margin-top:28px;background:#16202b;color:#fff;
   text-decoration:none;font-weight:700;font-size:14px;padding:13px 22px;border-radius:12px}}
 .note{{font-size:12.5px;color:#8693a6;margin-top:12px}}
</style></head>
<body><div class="wrap">
 <a class="back" href="../index.html">← GTİP Bulutları'na dön</a>
 <div class="card">
   <span class="tag"><i></i>Türkiye · Bağlayıcı Tarife Bilgisi (BTB)</span>
   <h1>GTİP {hs4(gtip)}</h1>
   <div class="meta">
     <div class="chip"><b>BTB No</b><span class="mono">{e_ref}</span></div>
     <div class="chip"><b>GTİP</b><span class="mono">{e_gtip}</span></div>
     <div class="chip"><b>Geçerlilik Başlama</b>{date_tr}</div>
   </div>
   <div class="sec"><h2>Eşyanın Tanımı</h2><p>{desc or '—'}</p></div>
   <div class="sec"><h2>Sınıflandırmanın Gerekçesi</h2><p>{just or '—'}</p></div>
   <a class="official" href="{TR_OFFICIAL}" target="_blank" rel="noopener">↗ Resmî kayıtta doğrula (Ticaret Bakanlığı)</a>
   <div class="note">Resmî BTB sorgulama sayfasında "BTB No" alanına <b>{e_ref}</b> yazıp arayarak bu kararı doğrulayabilirsiniz.</div>
 </div>
</div></body></html>"""

            with open(os.path.join(out_dir, f"{tr_slug(ref)}.html"), "w", encoding="utf-8") as fp:
                fp.write(page)
            count += 1

    return count


def main():
    tr_pages = write_tr_detail_pages()
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
    if tr_pages:
        print(f"  TR detay sayfaları: {tr_pages} → {os.path.join(OUT_DIR, 'tr')}/")
    if days:
        print(f"  En güncel gün: {days[0]['date_tr']} ({days[0]['count']} karar)")


if __name__ == "__main__":
    main()
