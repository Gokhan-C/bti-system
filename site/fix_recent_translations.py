#!/usr/bin/env python3
"""Son N günün (varsayılan 14) çevrilmemiş (yabancı dilde kalmış) kayıtlarını
DOĞRUDAN site verisinde (data.js + data/days + feed'ler) Claude ile yeniden çevirir.

build_site.py'a / ~/BTI_Reports'a dokunmaz → 73 günlük arşiv olduğu gibi korunur.

Kullanım:
    python3 site/fix_recent_translations.py [gün_sayısı]
"""
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.translator import translate_batch_claude          # noqa: E402
from migrate_data import load_data_js                        # noqa: E402
from build_site import write_data_js, write_split_data, write_feeds, OUT_DIR  # noqa: E402

BATCH = 8

# Türkçede standalone (kelime sınırlı) geçmeyen güçlü yabancı belirteçler.
# fix_untranslated.is_foreign, Türkçe işareti olarak ö/ü'yü saydığı için Almanca
# (umlaut'lu) metinleri kaçırıyordu; bu liste dilden bağımsız çalışır ve apostrof/
# "en" gibi Türkçeyle çakışan kısa belirteçleri içermez.
_FW = ("und|der|die|das|den|dem|für|mit|eines|einer|einem|von|oder|nicht|aus|bei|"
       "auch|sowie|zur|zum|the|and|with|which|from|are|been|these|goods|een|het|"
       "voor|met|zijn|wordt|aan|dat|les|une|avec|dans|pour|sous|est|aux|qui|ainsi|"
       "della|delle|con|per|uso|sono|che|och|på|av|med|för|enligt|som|van")
_FOREIGN = re.compile(r"\b(?:" + _FW + r")\b", re.I)


def looks_foreign(s):
    s = (s or "").strip()
    return len(s) >= 25 and bool(_FOREIGN.search(s))


def is_foreign(rec_or_text):
    """Kayıt (title+gerekce) ya da düz metin yabancı dilde mi?"""
    if isinstance(rec_or_text, dict):
        return looks_foreign(rec_or_text.get("title", "")) or looks_foreign(rec_or_text.get("gerekce", ""))
    return looks_foreign(rec_or_text)


def main():
    days_n = int(sys.argv[1]) if len(sys.argv) > 1 else 14
    payload = load_data_js(os.path.join(OUT_DIR, "data.js"))
    window = payload["days"][:days_n]
    print(f"Son {days_n} gün: {window[0]['date']} → {window[-1]['date']}")

    # çevrilmemiş kayıtları topla (nesne referanslarıyla)
    todo = []
    for day in window:
        for rec in day["decisions"]:
            if is_foreign(rec.get("title", "")) or is_foreign(rec.get("gerekce", "")):
                todo.append(rec)
    print(f"Çevrilecek kayıt: {len(todo)}")
    if not todo:
        print("Çevrilmemiş kayıt yok, çıkılıyor.")
        return

    fixed = 0
    for start in range(0, len(todo), BATCH):
        chunk = todo[start:start + BATCH]
        batch = [{
            "LANGUAGE": "auto",
            "DESCRIPTION_OF_GOODS": r.get("title", ""),
            "CLASSIFICATION_JUSTIFICATION": r.get("gerekce", ""),
        } for r in chunk]
        print(f"  Batch {start + 1}-{start + len(chunk)}/{len(todo)} çevriliyor...", flush=True)
        try:
            out = translate_batch_claude(batch)
        except Exception as e:
            print(f"    ! batch hatası: {e}")
            continue
        for rec, res in zip(chunk, out):
            nd = (res.get("desc_tr") or "").strip()
            nj = (res.get("just_tr") or "").strip()
            if nd and not is_foreign(nd):
                rec["title"] = nd
                if nj:
                    rec["gerekce"] = nj
                fixed += 1
            else:
                print(f"    ! {rec.get('ref')} hâlâ yabancı, atlandı")

    print(f"\n{fixed}/{len(todo)} kayıt çevrildi. Dosyalar yazılıyor...")

    # aynı payload nesneleri güncellendi → üç çıktıyı da yeniden yaz
    write_data_js(payload, OUT_DIR)
    write_split_data(payload, OUT_DIR)
    write_feeds(payload["days"], OUT_DIR)
    print("✓ data.js + data/ + feed'ler güncellendi.")


if __name__ == "__main__":
    main()
