#!/usr/bin/env python3
"""
Tek seferlik migrasyon: mevcut site/data.js arşivini yeni bölünmüş formata çevirir.

Okur:  site/data.js  (window.BTI_DATA = {...};)
Yazar: site/data/index.json           (özet, kararlar olmadan)
       site/data/days/YYYY-MM-DD.json  (her günün tam karar listesi)

build_site.py içindeki yazma mantığını yeniden kullanır; böylece migrasyon çıktısı
üreticinin bundan sonra üreteceğiyle birebir aynı olur.

Kullanım:
    python3 site/migrate_data.py
"""

import json
import os
import re

from build_site import write_split_data, compute_extras, write_data_js

OUT_DIR = os.path.dirname(os.path.abspath(__file__))


def load_data_js(path):
    """window.BTI_DATA = {...}; içindeki JSON'u ayrıştırır."""
    with open(path, encoding="utf-8") as fp:
        text = fp.read()
    m = re.search(r"window\.BTI_DATA\s*=\s*", text)
    if not m:
        raise SystemExit("HATA: data.js içinde 'window.BTI_DATA =' bulunamadı.")
    body = text[m.end():].strip()
    if body.endswith(";"):
        body = body[:-1].strip()
    return json.loads(body)


def main():
    src = os.path.join(OUT_DIR, "data.js")
    payload = load_data_js(src)

    # Eski data.js'te source_counts / chapters yoksa arşivden hesapla.
    if "source_counts" not in payload or "chapters" not in payload:
        sc, ch = compute_extras(payload["days"])
        payload.setdefault("source_counts", sc)
        payload.setdefault("chapters", ch)

    data_dir = write_split_data(payload, OUT_DIR)
    # data.js'i de source_counts/chapters ile zenginleştirip yeniden yaz
    # (dashboard.html ve file:// fallback aynı alanları görsün).
    write_data_js(payload, OUT_DIR)

    days = payload["days"]
    print(f"✓ Migrasyon tamam: {payload['total_decisions']} karar, {len(days)} gün")
    print(f"  → {data_dir}/index.json")
    print(f"  → {data_dir}/days/ ({len(days)} dosya)")
    print(f"  → data.js source_counts/chapters ile güncellendi")


if __name__ == "__main__":
    main()
