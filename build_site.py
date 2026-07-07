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

# GitHub Pages tabanı (deep-link ve göreli TR URL'lerini mutlaklaştırmak için)
PAGES_BASE = "https://gokhan-c.github.io/bti-system/"

# RSS başlıklarında kaynak kısaltmaları
SRC_SHORT = {"eu": "AB", "us": "ABD", "ca": "CAN", "tr": "TR"}

# Fasıl (GTİP ilk 2 hane) → Türkçe ad. index.html'deki FASIL ile aynı.
FASIL_TR = {
    "01": "Canlı hayvanlar", "02": "Etler ve yenilen sakatat", "03": "Balıklar ve su ürünleri",
    "04": "Süt ürünleri, yumurta, bal", "05": "Diğer hayvansal ürünler",
    "06": "Canlı bitkiler ve çiçekler", "07": "Sebzeler", "08": "Meyveler ve kabuklu yemişler",
    "09": "Kahve, çay, baharat", "10": "Hububat", "11": "Değirmencilik ürünleri",
    "12": "Yağlı tohumlar", "13": "Bitkisel özsu ve hülasalar",
    "14": "Örülmeye elverişli bitkisel ürünler", "15": "Hayvansal ve bitkisel yağlar",
    "16": "Et ve balık müstahzarları", "17": "Şeker ve şeker mamulleri",
    "18": "Kakao ve müstahzarları", "19": "Unlu mamuller", "20": "Sebze ve meyve müstahzarları",
    "21": "Yenilen çeşitli gıda müstahzarları", "22": "İçecekler ve alkollü içkiler",
    "23": "Gıda sanayii kalıntıları, hayvan yemleri", "24": "Tütün",
    "25": "Tuz, kükürt, toprak ve taşlar", "26": "Metal cevherleri",
    "27": "Mineral yakıtlar ve yağlar", "28": "Anorganik kimyasallar", "29": "Organik kimyasallar",
    "30": "Eczacılık ürünleri", "31": "Gübreler", "32": "Boyalar, vernikler, mürekkepler",
    "33": "Parfümeri ve kozmetik", "34": "Sabunlar, yıkama müstahzarları",
    "35": "Albüminoid maddeler, tutkallar", "36": "Barut ve patlayıcılar",
    "37": "Fotoğrafçılık ürünleri", "38": "Muhtelif kimyasal ürünler",
    "39": "Plastikler ve mamulleri", "40": "Kauçuk ve mamulleri",
    "41": "Ham postlar ve deriler", "42": "Deri eşya ve saraciye", "43": "Kürkler",
    "44": "Ağaç ve ahşap eşya", "45": "Mantar", "46": "Hasırcılık ve sepetçilik eşyası",
    "47": "Odun hamuru", "48": "Kâğıt ve karton", "49": "Basılı kitaplar, gazeteler",
    "50": "İpek", "51": "Yapağı ve yün", "52": "Pamuk", "53": "Diğer bitkisel lifler",
    "54": "Sentetik ve suni filamentler", "55": "Sentetik ve suni devamsız lifler",
    "56": "Vatka, keçe, ipler ve halatlar", "57": "Halılar ve yer kaplamaları",
    "58": "Özel dokunmuş mensucat", "59": "Emdirilmiş, kaplanmış mensucat", "60": "Örme eşya",
    "61": "Örme giyim eşyası", "62": "Örülmemiş giyim eşyası",
    "63": "Diğer hazır eşya, kullanılmış giysiler", "64": "Ayakkabılar", "65": "Başlıklar",
    "66": "Şemsiyeler ve bastonlar", "67": "Kuş tüyü ve yapma çiçekler",
    "68": "Taş, alçı, çimentodan eşya", "69": "Seramik mamulleri", "70": "Cam ve cam eşya",
    "71": "Kıymetli taşlar ve mücevherat", "72": "Demir ve çelik", "73": "Demir veya çelikten eşya",
    "74": "Bakır ve mamulleri", "75": "Nikel ve mamulleri", "76": "Alüminyum ve mamulleri",
    "78": "Kurşun ve mamulleri", "79": "Çinko ve mamulleri", "80": "Kalay ve mamulleri",
    "81": "Diğer adi metaller", "82": "Adi metallerden aletler",
    "83": "Adi metallerden çeşitli eşya", "84": "Makineler ve mekanik cihazlar",
    "85": "Elektrikli makine ve cihazlar", "86": "Demiryolu taşıtları",
    "87": "Motorlu kara taşıtları", "88": "Hava taşıtları", "89": "Gemiler ve suda yüzen taşıtlar",
    "90": "Optik, ölçü ve tıbbi cihazlar", "91": "Saatler", "92": "Müzik aletleri",
    "93": "Silahlar ve mühimmat", "94": "Mobilyalar ve aydınlatma cihazları",
    "95": "Oyuncaklar ve spor malzemeleri", "96": "Çeşitli mamul eşya",
    "97": "Sanat eserleri ve antikalar",
}


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
    """ABD/CBP ruling için resmi CBP CROSS deep-link'i.

    Not (2026-07): customsmobile.com aynası bu ruling'leri artık tutmuyor
    ("document is not found" hatası). CBP kendi sitesindeki Akamai bloğunu da
    kaldırdı; tek-karar deep-link'i (rulings.cbp.gov/ruling/<NUMARA>) yeniden
    doğrudan erişilebilir. Bu URL connector'ın ürettiği source_url ile aynıdır.
    """
    num = (number or "").strip()
    return f"https://rulings.cbp.gov/ruling/{num}"


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


def compute_extras(days):
    """Tüm arşivden kaynak sayıları ve arşivde geçen fasıl (2 haneli) kodları."""
    source_counts = {"eu": 0, "us": 0, "ca": 0, "tr": 0}
    chapters = set()
    for day in days:
        for d in day.get("decisions", []):
            s = d.get("source")
            if s in source_counts:
                source_counts[s] += 1
            ch = str(d.get("hs4", "") or "")[:2]
            if ch:
                chapters.add(ch)
    return source_counts, sorted(chapters)


def write_split_data(payload, out_dir):
    """Yeni mimari: özet index.json + gün başına ayrı JSON.

    - data/index.json  → kararlar OLMADAN özet (her ziyaretçi bunu indirir)
    - data/days/<date>.json → o günün tam karar listesi (talep üzerine indirilir)

    Ziyaretçi açılışta yalnızca index.json + en son günü indirir; arşivin tamamı
    (~1.5 MB) yalnız arama/filtre yapılınca yüklenir.
    """
    data_dir = os.path.join(out_dir, "data")
    days_dir = os.path.join(data_dir, "days")
    os.makedirs(days_dir, exist_ok=True)

    index = {
        "generated_at": payload["generated_at"],
        "today": payload["today"],
        "today_tr": payload["today_tr"],
        "latest_date": payload["latest_date"],
        "latest_is_today": payload["latest_is_today"],
        "total_decisions": payload["total_decisions"],
        "total_days": payload["total_days"],
        "source_counts": payload["source_counts"],
        "chapters": payload["chapters"],
        "days": [
            {"date": d["date"], "date_tr": d["date_tr"],
             "count": d["count"], "sources": d["sources"]}
            for d in payload["days"]
        ],
    }
    with open(os.path.join(data_dir, "index.json"), "w", encoding="utf-8") as fp:
        json.dump(index, fp, ensure_ascii=False, separators=(",", ":"))

    current = set()
    for day in payload["days"]:
        current.add(day["date"])
        with open(os.path.join(days_dir, f"{day['date']}.json"), "w", encoding="utf-8") as fp:
            json.dump(day, fp, ensure_ascii=False, separators=(",", ":"))

    # Arşivden düşmüş eski gün dosyalarını temizle (index.json onları listelemez).
    for stale in glob.glob(os.path.join(days_dir, "*.json")):
        name = os.path.splitext(os.path.basename(stale))[0]
        if name not in current:
            try:
                os.remove(stale)
            except OSError:
                pass

    return data_dir


def build_payload(days):
    """days listesinden tam BTI_DATA yükünü (özet alanlar dahil) kurar."""
    total = sum(d["count"] for d in days)
    today_iso = datetime.now().strftime("%Y-%m-%d")
    latest_iso = days[0]["date"] if days else None
    source_counts, chapters = compute_extras(days)
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "today": today_iso,
        "today_tr": fmt_date_tr(today_iso),
        "latest_date": latest_iso,
        "latest_is_today": (latest_iso == today_iso),
        "total_decisions": total,
        "total_days": len(days),
        "source_counts": source_counts,
        "chapters": chapters,
        "days": days,
    }


def write_data_js(payload, out_dir):
    """GERİYE UYUMLULUK: dashboard.html hâlâ window.BTI_DATA'yı kullanıyor;
    index.html ise fetch başarısız olursa (file://) buna fallback yapar."""
    out = os.path.join(out_dir, "data.js")
    with open(out, "w", encoding="utf-8") as fp:
        fp.write("window.BTI_DATA = ")
        json.dump(payload, fp, ensure_ascii=False, indent=1)
        fp.write(";\n")
    return out


FASIL_FEEDS = ["28", "29", "39", "84", "85"]  # kimya + makine fasılları
FEED_DAYS = 14        # ana feed: son kaç gün
FASIL_FEED_ITEMS = 60  # fasıl feed'i: en yeni kaç karar


def _rfc822(iso):
    """'2026-07-02' → RFC-822 tarih (RSS pubDate için)."""
    from email.utils import formatdate
    import time
    try:
        dt = datetime.strptime(iso, "%Y-%m-%d")
        return formatdate(time.mktime(dt.timetuple()))
    except Exception:
        return formatdate()


def _abs_url(u):
    """Göreli TR URL'sini (tr/xxx.html) GitHub Pages tabanıyla mutlaklaştırır."""
    u = (u or "").strip()
    if not u:
        return PAGES_BASE
    if u.startswith("http://") or u.startswith("https://"):
        return u
    return PAGES_BASE + u.lstrip("/")


def _rss_channel(title, link, self_url, description, items):
    """Bir RSS 2.0 belgesi (string) kurar. items: hazır <item> stringleri listesi."""
    from xml.sax.saxutils import escape
    from email.utils import formatdate
    head = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        '<channel>\n'
        '<title>' + escape(title) + '</title>\n'
        '<link>' + escape(link) + '</link>\n'
        '<atom:link href="' + escape(self_url) + '" rel="self" type="application/rss+xml"/>\n'
        '<description>' + escape(description) + '</description>\n'
        '<language>tr</language>\n'
        '<lastBuildDate>' + formatdate() + '</lastBuildDate>\n'
    )
    return head + "".join(items) + '</channel>\n</rss>\n'


def _item(title, link, guid, pubdate, description):
    from xml.sax.saxutils import escape
    return (
        '<item>\n'
        '<title>' + escape(title) + '</title>\n'
        '<link>' + escape(link) + '</link>\n'
        '<guid isPermaLink="false">' + escape(guid) + '</guid>\n'
        '<pubDate>' + escape(pubdate) + '</pubDate>\n'
        '<description>' + escape(description) + '</description>\n'
        '</item>\n'
    )


def write_feeds(days, out_dir):
    """RSS çıktıları: ana feed (son 14 gün, gün başına item) + fasıl feed'leri."""
    written = []

    # --- ana feed: son 14 günün her günü bir item ---
    items = []
    for day in days[:FEED_DAYS]:
        decs = day.get("decisions", [])
        # kaynak dağılımı: "AB 98 · TR 5"
        src_ct = {}
        ch_ct = defaultdict(int)
        for d in decs:
            src_ct[d["source"]] = src_ct.get(d["source"], 0) + 1
            ch = str(d.get("hs4", "") or "")[:2]
            if ch:
                ch_ct[ch] += 1
        parts = [f"{SRC_SHORT[s]} {src_ct[s]}" for s in ("eu", "us", "ca", "tr") if src_ct.get(s)]
        src_str = (" (" + " · ".join(parts) + ")") if parts else ""
        title = f"{day['date_tr']} — {day['count']} yeni tarife kararı{src_str}"
        # açıklama: en çok karar çıkan 5 fasıl
        top = sorted(ch_ct.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        top_str = " · ".join(
            f"{ch} {FASIL_TR.get(ch, '')} ({n})".strip() for ch, n in top
        )
        desc = ("En çok karar çıkan fasıllar: " + top_str) if top_str else "Bu gün karar çıkmadı."
        link = PAGES_BASE + "#g=" + day["date"]
        items.append(_item(title, link, link, _rfc822(day["date"]), desc))

    doc = _rss_channel(
        "GTİP Bulutları — günlük tarife kararları",
        PAGES_BASE, PAGES_BASE + "feed.xml",
        "AB, ABD, Kanada ve Türkiye bağlayıcı tarife kararlarının günlük özeti.",
        items,
    )
    path = os.path.join(out_dir, "feed.xml")
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(doc)
    written.append(path)

    # --- fasıl feed'leri: karar başına item, en yeni FASIL_FEED_ITEMS karar ---
    for ch in FASIL_FEEDS:
        rows = []
        for day in days:  # days zaten tarih azalan sırada
            for d in day.get("decisions", []):
                if str(d.get("hs4", "") or "")[:2] == ch:
                    rows.append((day, d))
        rows = rows[:FASIL_FEED_ITEMS]
        items = []
        for day, d in rows:
            hs = d.get("hs") or d.get("hs4") or ""
            desc_txt = d.get("title") or d.get("gerekce") or ""
            title = (f"{hs} — {desc_txt}").strip(" —")[:110] or hs
            src = SRC_SHORT.get(d["source"], d["source"])
            link = _abs_url(d.get("url"))
            guid = (d.get("ref") or link) + "|" + ch
            body = f"[{src}] {d.get('source_label','')} · {day['date_tr']}"
            if d.get("gerekce"):
                body += " — " + d["gerekce"]
            items.append(_item(title, link, guid, _rfc822(d.get("date") or day["date"]), body))

        fname = f"feed-fasil-{ch}.xml"
        doc = _rss_channel(
            f"GTİP Bulutları — Fasıl {ch} {FASIL_TR.get(ch, '')}".strip(),
            PAGES_BASE + "#f=" + ch, PAGES_BASE + fname,
            f"Fasıl {ch} ({FASIL_TR.get(ch, '')}) altındaki yeni tarife kararları.",
            items,
        )
        path = os.path.join(out_dir, fname)
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(doc)
        written.append(path)

    return written


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

    payload = build_payload(days)

    # Yeni mimari: özet + gün başına JSON
    data_dir = write_split_data(payload, OUT_DIR)
    # Geriye uyumluluk: dashboard.html ve file:// fallback için tam data.js
    out = write_data_js(payload, OUT_DIR)
    # RSS çıktıları (ana feed + fasıl feed'leri)
    feeds = write_feeds(days, OUT_DIR)

    total = payload["total_decisions"]
    print(f"✓ {total} karar, {len(days)} gün → {out}")
    print(f"  Bölünmüş veri: {data_dir}/index.json + {len(days)} gün dosyası")
    print(f"  RSS: {len(feeds)} feed ({', '.join(os.path.basename(f) for f in feeds)})")
    if tr_pages:
        print(f"  TR detay sayfaları: {tr_pages} → {os.path.join(OUT_DIR, 'tr')}/")
    if days:
        print(f"  En güncel gün: {days[0]['date_tr']} ({days[0]['count']} karar)")


if __name__ == "__main__":
    main()
