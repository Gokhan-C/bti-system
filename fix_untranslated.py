#!/usr/bin/env python3
"""Kaydedilmiş _report_data.json içinde çevrilmeden kalmış (yabancı dilde) EBTI
kayıtlarını bulup Claude ile yeniden Türkçeye çevirir, dosyaya geri yazar.

Kullanım:
    python3 fix_untranslated.py 2026-06-19            # tek gün
    python3 fix_untranslated.py                       # tüm EU günleri
"""
import sys, json, glob, os, re
sys.path.insert(0, "/Users/gokhancankaya/bti_system")
from core.translator import translate_batch_claude

BASE = os.path.expanduser("~/BTI_Reports/EU_EBTI")

TR_CHARS = set("ğşıİĞŞÇÖÜçöü")
# Türkçe metinde çok sık geçen kelimeler
TR_WORDS = re.compile(r"\b(ve|ile|olarak|için|göre|edilmiş|ürün|sınıflandır|pozisyon|fasıl|kural)\b", re.I)
# Tipik yabancı (en/de/nl/fr) belirteçler
FOREIGN = re.compile(r"\b(the|and|with|which|een|voor|met|het|zachte|der|und|für|les|une|avec|dans)\b", re.I)


def is_foreign(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 25:
        return False
    has_tr = any(c in TR_CHARS for c in t) or bool(TR_WORDS.search(t))
    has_foreign = bool(FOREIGN.search(t))
    # Türkçe işareti yok ve yabancı belirteç varsa → çevrilmemiş
    return has_foreign and not has_tr


# country → kaynak dil kodu (Claude'a ipucu)
LANG = {
    "NL": "nl", "DE": "de", "AT": "de", "FR": "fr", "BE": "fr", "LU": "fr",
    "ES": "es", "IT": "it", "PT": "pt", "PL": "pl", "SE": "sv", "DK": "da",
    "FI": "fi", "CZ": "cs", "SK": "sk", "HU": "hu", "RO": "ro", "BG": "bg",
    "EL": "el", "GR": "el", "HR": "hr", "SI": "sl", "LT": "lt", "LV": "lv",
    "EE": "et", "IE": "en", "MT": "en", "CY": "el",
}


def fix_file(path: str) -> int:
    data = json.load(open(path, encoding="utf-8"))
    recs = data.get("records", [])
    fixed = 0
    for r in recs:
        desc = r.get("desc_tr", "")
        just = r.get("just_tr", "")
        if not (is_foreign(desc) or is_foreign(just)):
            continue
        lang = LANG.get(r.get("country", ""), "en")
        payload = [{
            "LANGUAGE": lang,
            "DESCRIPTION_OF_GOODS": desc,
            "CLASSIFICATION_JUSTIFICATION": just,
        }]
        try:
            out = translate_batch_claude(payload)[0]
        except Exception as e:
            print(f"  ! {r.get('ref')} çeviri hatası: {e}")
            continue
        new_desc = out.get("desc_tr", "").strip()
        new_just = out.get("just_tr", "").strip()
        if new_desc and not is_foreign(new_desc):
            r["desc_tr"] = new_desc
            r["just_tr"] = new_just or just
            fixed += 1
            print(f"  ✓ {r.get('ref')} ({lang}) çevrildi")
        else:
            print(f"  ! {r.get('ref')} hâlâ yabancı, atlandı")
    if fixed:
        json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return fixed


def main():
    if len(sys.argv) > 1:
        dirs = [os.path.join(BASE, sys.argv[1])]
    else:
        dirs = sorted(glob.glob(os.path.join(BASE, "2026-*")))
    grand = 0
    for d in dirs:
        path = os.path.join(d, "_report_data.json")
        if not os.path.exists(path):
            continue
        day = os.path.basename(d)
        print(f"[{day}]")
        n = fix_file(path)
        print(f"  → {n} kayıt düzeltildi")
        grand += n
    print(f"\nToplam {grand} kayıt yeniden çevrildi.")


if __name__ == "__main__":
    main()
