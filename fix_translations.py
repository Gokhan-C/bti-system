#!/usr/bin/env python3
"""
Çeviri tamiri — tüm kaynaklardaki çevrilmemiş kayıtları Türkçeye çevirir.

Neden gerekli: claude CLI oturumu geçersizken (OAuth süresi dolduğunda) çeviri
çağrıları başarısız oluyor ve connector'lar ham (yabancı dil) metni kaydediyordu.
Oturum yenilendikten sonra bu araç birikmiş kayıtları toplu olarak düzeltir.

Kapsam (~/BTI_Reports altındaki _report_data.json dosyaları):
    EU_EBTI   → records[].desc_tr / just_tr
    US_CBP    → records[].summary.esya_tanimi / teknik_gerekce
    CA_CBSA   → records[].summary.esya_tanimi / teknik_gerekce
    UK_HMRC   → records[].summary.esya_tanimi / teknik_gerekce

Kullanım:
    python3 fix_translations.py --dry-run          # ne değişecek, sadece göster
    python3 fix_translations.py                    # hepsini çevir
    python3 fix_translations.py --source EU_EBTI   # tek kaynak
    python3 fix_translations.py --limit 50         # en fazla 50 kayıt

Sonrasında siteyi tazele:  python3 site/build_site.py
"""

import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.translator import call_claude, ClaudeAuthError  # noqa: E402

REPORTS = os.path.expanduser("~/BTI_Reports")

# Kaynak → çevrilecek alanların yolu. ("düz" = record[alan], "özet" = record.summary[alan])
SOURCES = {
    "EU_EBTI": ("duz",  ["desc_tr", "just_tr"]),
    "US_CBP":  ("ozet", ["esya_tanimi", "teknik_gerekce"]),
    "CA_CBSA": ("ozet", ["esya_tanimi", "teknik_gerekce"]),
    "UK_HMRC": ("ozet", ["esya_tanimi", "teknik_gerekce"]),
}

# Çeviri denemeye değmeyen yer tutucular
PLACEHOLDERS = {"", "-", "—", "(bilgi yok)", "(özet üretilemedi)", "(çeviri yok)"}

# Yabancı dil sezgisi: yaygın EN/FR/DE/ES/IT işlev kelimeleri vs. Türkçe ekler
FOREIGN = re.compile(
    r'\b(the|and|with|which|for|from|are|this|that|has|been|used|other'
    r'|des|les|une|pour|est|dans|avec|sur|par'
    r'|und|der|die|das|mit|von|den|ist|für'
    r'|para|con|del|los|las|por|como'
    r'|che|di|il|della|per|una)\b', re.I)
TURKISH = re.compile(
    r'\b(ve|bir|için|olan|ile|bu|adet|marka|model|ürün|madde|içeren|yapılmış'
    r'|kullanılan|olarak|göre|tarife|sınıflandırma|eşya|cihaz|malzeme|üzere'
    r'|bulunan|edilen|şeklinde|kısmı|parça)\b', re.I)


def is_untranslated(text: str) -> bool:
    """Metin Türkçe değil mi? (kısa/yer tutucu metinlerde False)"""
    t = (text or "").strip()
    if t.lower() in PLACEHOLDERS or len(t) < 25:
        return False
    return len(FOREIGN.findall(t)) > len(TURKISH.findall(t))


def translate_batch(texts: list[str]) -> list[str]:
    """Metin listesini tek Claude çağrısıyla Türkçeye çevirir.

    Sıra ve sayı korunmalı; bozuk yanıtta orijinaller döndürülür (veri kaybı olmaz).
    """
    parts = []
    for i, t in enumerate(texts, 1):
        parts.append(f"### METIN_{i}\n{t.strip()}")

    prompt = (
        "Aşağıdaki gümrük tarife kararı metinlerini Türkçeye çevir.\n"
        "Kurallar: teknik terimleri koru, marka/model/kod/sayıları aynen bırak, "
        "yorum ekleme, kısaltma yapma.\n"
        "Yanıtı SADECE şu biçimde ver (başka hiçbir şey yazma):\n"
        "### CEVIRI_1\n<çeviri>\n### CEVIRI_2\n<çeviri>\n\n"
        + "\n\n".join(parts)
    )

    resp = call_claude(prompt, timeout=300)

    out = []
    for i in range(1, len(texts) + 1):
        m = re.search(
            rf"###\s*CEVIRI_{i}\s*\n(.*?)(?=\n###\s*CEVIRI_{i + 1}\s*\n|\Z)",
            resp, re.S)
        val = (m.group(1).strip() if m else "")
        out.append(val if val else texts[i - 1])   # eşleşmezse orijinali koru
    return out


def collect_jobs(only_source=None):
    """Çevrilecek işleri topla: (dosya, kayıt_index, alan_yolu, metin)"""
    jobs = []
    for src, (kind, fields) in SOURCES.items():
        if only_source and src != only_source:
            continue
        for path in sorted(glob.glob(f"{REPORTS}/{src}/*/_report_data.json")):
            try:
                data = json.load(open(path, encoding="utf-8"))
            except Exception:
                continue
            for idx, rec in enumerate(data.get("records", [])):
                holder = rec if kind == "duz" else (rec.get("summary") or {})
                if not isinstance(holder, dict):
                    continue
                for f in fields:
                    if is_untranslated(holder.get(f, "")):
                        jobs.append({"path": path, "src": src, "idx": idx,
                                     "kind": kind, "field": f,
                                     "text": holder[f]})
    return jobs


def apply_updates(updates):
    """updates: {path: {(idx, kind, field): yeni_metin}} → dosyalara yaz."""
    for path, changes in updates.items():
        data = json.load(open(path, encoding="utf-8"))
        for (idx, kind, field), new in changes.items():
            rec = data["records"][idx]
            holder = rec if kind == "duz" else rec.setdefault("summary", {})
            holder[field] = new
        json.dump(data, open(path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="değişiklik yazma, sadece göster")
    ap.add_argument("--source", help="tek kaynak (EU_EBTI / US_CBP / CA_CBSA / UK_HMRC)")
    ap.add_argument("--limit", type=int, help="en fazla kaç kayıt çevrilsin")
    ap.add_argument("--batch", type=int, default=6, help="tek çağrıda kaç metin (varsayılan 6)")
    args = ap.parse_args()

    jobs = collect_jobs(args.source)
    if args.limit:
        jobs = jobs[:args.limit]

    if not jobs:
        print("✓ Çevrilmemiş kayıt bulunamadı.")
        return

    from collections import Counter
    print(f"Çevrilecek alan sayısı: {len(jobs)}")
    print("  kaynak dağılımı:", dict(Counter(j["src"] for j in jobs)))

    if args.dry_run:
        for j in jobs[:10]:
            print(f"\n— {j['src']} [{j['field']}] {os.path.basename(os.path.dirname(j['path']))}")
            print("   ", j["text"][:140].replace("\n", " "))
        print(f"\n(dry-run — hiçbir şey yazılmadı)")
        return

    updates, done, failed = {}, 0, 0
    for start in range(0, len(jobs), args.batch):
        chunk = jobs[start:start + args.batch]
        try:
            results = translate_batch([j["text"] for j in chunk])
        except ClaudeAuthError as e:
            print(f"\n✗ DURDURULDU — {e}")
            break
        except Exception as e:
            failed += len(chunk)
            print(f"  ! parti {start // args.batch + 1} hatası: {str(e)[:90]}")
            continue

        for j, new in zip(chunk, results):
            if new and new != j["text"]:
                updates.setdefault(j["path"], {})[(j["idx"], j["kind"], j["field"])] = new
                done += 1

        # Her partide diske yaz — uzun sürede kesilirse ilerleme kaybolmasın
        if updates:
            apply_updates(updates)
            updates = {}
        print(f"  {min(start + args.batch, len(jobs))}/{len(jobs)} işlendi (çevrilen: {done})")

    print(f"\n✓ Çevrilen alan: {done}" + (f" · başarısız: {failed}" if failed else ""))
    print("Şimdi siteyi tazele:  python3 site/build_site.py")


if __name__ == "__main__":
    main()
