# BTI System — Uygulama İlerleme

Context kesilirse: bu dosyayı oku → kaldığın adımdan devam et.
Tamamlanan adımlar: mevcut dosyaları silme/yeniden yazma, sadece eksik adımları tamamla.

## Adımlar

[x] STEP-01: core/logger.py
[x] STEP-02: core/translator.py
[x] STEP-03: core/report_builder.py
[x] STEP-04: core/base_connector.py
[x] STEP-05: config.yaml
[x] STEP-06: assets/ kopyası (build_docx.js + package.json)
[x] STEP-07: connectors/eu_ebti.py
[x] STEP-08: connectors/us_cbp.py
[x] STEP-09: connectors/ca_cbsa.py + state migrasyonu (1195 ID taşındı)
[x] STEP-10: core/orchestrator.py
[x] STEP-11: main.py
[x] STEP-12: setup.sh + LaunchAgent plist

## TÜM ADIMLAR TAMAMLANDI

setup.sh çalıştırılmadı — pip/npm/LaunchAgent kurulumu için kullanıcı onayı gerekli.

## Kaynak Dosyalar

- ebti_agent/ebti_download.py — AB EBTI Playwright scraper
- ebti_agent/generate_report.py — AB EBTI rapor üretici (Claude çevirisi + Node.js)
- ebti_agent/build_docx.js — Node.js Word oluşturucu (assets/'a kopyalanacak)
- Gumruk_Kararlar/karar_takip.py — ABD CBP + Kanada CBSA (make_doc, add_info_table, add_ruling_to_doc, set_cell_bg, translate_to_turkish buradan alınır)
- Gumruk_Kararlar/cbsa_seen_ids.json — state/ca_cbsa_seen.json'a taşınacak

## Mimari Notlar

- AB EBTI: tarih bazlı (dün), Playwright scraping, Claude çevirisi, Node.js .docx
- ABD CBP: en son yayınlananlar → us_cbp_seen.json karşılaştırması → sadece yeniler
- Kanada CBSA: CARM API listesi → ca_cbsa_seen.json karşılaştırması → sadece yeniler
- Her connector BaseConnector'dan türer, run() tek giriş noktası
- Orchestrator birleşik BTI_Unified_YYYY-MM-DD.docx üretir
- LaunchAgent 06:00'da çalışır
