# GTİP Bulutları — Site

AB (EBTI), ABD (CBP) ve Kanada (CBSA) günlük gümrük sınıflandırma kararlarını
"havada uçuşan bulutlar" olarak gösteren statik web sitesi. Her bulutun üzerinde
kararın GTİP pozisyonunun ilk 4 hanesi yazar; buluta tıklayınca kararın orijinal
kaynak sayfası yeni sekmede açılır.

## Dosyalar
- `index.html` — site arayüzü. **Claude Design (DC) bileşeni**: `<x-dc>` şablonu +
  `{{ }}` değişkenleri + alttaki `class Component extends DCLogic` mantığı. Çizim
  (bulutlar, tooltip) imperatif olarak `renderField()` ile yapılır.
- `support.js` — DC runtime (React'i unpkg'den yükleyip `index.html`'i çalıştırır).
  Otomatik üretilir, elle düzenlenmez.
- `data.js`    — `window.BTI_DATA` olarak gömülü karar verisi (otomatik üretilir).
- `build_site.py` — `~/Desktop/BTI_Reports` altındaki `_report_data.json`'ları
  tarayıp `data.js`'i yeniden üretir. **Tasarım değişse de bu hiç değişmez**;
  `index.html` aynı `window.BTI_DATA` şemasını okur.
- `index_legacy.html` — eski tek-dosya (saf HTML/CSS/JS) tasarımın yedeği.

## Günlük otomasyon (kurulu)
Sistem her gün **06:00**'da otomatik çalışır. Tek giriş noktası kök dizindeki
`daily_update.sh`:

1. `main.py` → tüm connector'ları çalıştırır (dünün kararlarını çeker, rapor üretir)
2. `site/build_site.py` → siteyi (`data.js`) tazeler

Bunu tetikleyen macOS LaunchAgent: `~/Library/LaunchAgents/com.user.bti-system-daily.plist`
(Python 3.12 + `claude` CLI ile çalışır). Loglar: `~/Desktop/BTI_Reports/logs/daily_update.log`.

```bash
# Elle çalıştırmak (bugün hemen güncellemek):
bash daily_update.sh

# LaunchAgent'ı hemen tetiklemek:
launchctl start com.user.bti-system-daily

# Durumu görmek (0 = son çalışma başarılı):
launchctl list | grep bti

# Sadece siteyi yeniden üretmek (veri çekmeden):
python3 site/build_site.py
```

`index.html` her zaman **bugünün tarihini** üst kısımda gösterir; o gün için henüz
karar yoksa "henüz yayımlanmadı" notuyla en son yayımlanan günü gösterir. Oklarla
geçmiş günlere bakılabilir.

### Bulut renkleri (kaynak ayrımı)
Her bulutun **gövde tonu** kararı veren idareyi gösterir (ince fark):
- **Avrupa Birliği** → beyaz (`#ffffff`)
- **Amerika (CBP)** → kırık beyaz / sıcak (`#f7f1e8`)
- **Kanada (CBSA)** → bir tık grimsi (`#e7ebf0`)

Renkler `index.html` içinde `CLOUD_BG` sabitinde tanımlı. Bir günde çok karar
varsa bulutlar 60 ile sınırlıdır; `build_site.py` kararları kaynaklara göre
**round-robin harmanladığı** için her idare (AB/ABD/Kanada) bu 60 içinde adil
temsil edilir (tek kaynak listeyi domine etmez).

### Buluta gelince çıkan kutu (tooltip)
Türkçe iki bölüm gösterir: **Ürün Tanımı** (`desc_tr`) ve **Sınıflandırma
Gerekçesi** (`just_tr` / `teknik_gerekce`). Tıklayınca kararın orijinal kaynağı açılır.

### Çeviri eksiklerini düzeltme
Bazı EBTI kayıtları batch çevirisinde atlanıp yabancı dilde kalabilir. `core/translator.py`
artık ikinci geçişte bunları tek tek yeniden çevirir. Önceden kaydedilmiş günleri
düzeltmek için:
```bash
python3 fix_untranslated.py 2026-06-19   # tek gün
python3 fix_untranslated.py              # tüm EU günleri
python3 site/build_site.py               # ardından siteyi tazele
```

## Yerelde görüntüleme
```bash
cd site && python3 -m http.server 8780
# tarayıcıda: http://localhost:8780
```

## İnternette yayınlama (ücretsiz seçenekler)
`site/` klasörü tamamen statiktir; herhangi bir statik host'a yüklenebilir:

- **GitHub Pages**: `site/` içeriğini bir repoya koyup Pages'i aç.
- **Netlify / Cloudflare Pages / Vercel**: klasörü sürükle-bırak veya repo bağla.
  Build komutu gerekmez; publish dizini = `site`.

Günlük otomasyon için: sunucuda cron ile orchestrator + `build_site.py` çalıştırıp
`data.js`'i host'a (git push veya rsync) gönder.
