/**
 * BTI i18n — panel ve favoriler sayfaları için ortak dil katmanı.
 *
 * Dil tercihi index.html ile AYNI localStorage anahtarında ('bti_lang')
 * tutulur; böylece sayfalar arasında gezerken dil korunur.
 *
 * Kullanım:
 *   BTIi18n.dict({ tr:{...}, en:{...} });   // sayfaya özel metinler
 *   BTIi18n.mount(function(){ render(); }); // dil anahtarını çiz + değişimde yeniden çiz
 *   BTIi18n.t('key')  ·  BTIi18n.lang  ·  BTIi18n.srcName('eu')  ·  BTIi18n.fmtDate(iso)
 */
(function (g) {
  'use strict';

  var KEY = 'bti_lang';
  var lang = (function () {
    try { var v = localStorage.getItem(KEY); if (v === 'en' || v === 'tr') return v; } catch (e) {}
    return (navigator.language || 'tr').toLowerCase().indexOf('tr') === 0 ? 'tr' : 'en';
  })();

  var DICT = { tr: {}, en: {} };
  var onChange = null;

  var SRC_NAMES = {
    tr: { eu: 'Avrupa Birliği', us: 'Amerika', ca: 'Kanada', uk: 'İngiltere', tr: 'Türkiye' },
    en: { eu: 'European Union', us: 'United States', ca: 'Canada', uk: 'United Kingdom', tr: 'Türkiye' }
  };
  var SRC_SHORT = {
    tr: { eu: 'AB', us: 'ABD', ca: 'KAN', uk: 'İNG', tr: 'TR' },
    en: { eu: 'EU', us: 'US', ca: 'CA', uk: 'UK', tr: 'TR' }
  };
  var ORIGIN_EN = {
    'Kanada': 'Canada', 'İngiltere': 'United Kingdom', 'ABD': 'United States', 'Türkiye': 'Türkiye',
    'Fransa': 'France', 'Almanya': 'Germany', 'Hollanda': 'Netherlands', 'İtalya': 'Italy',
    'İspanya': 'Spain', 'Belçika': 'Belgium', 'Polonya': 'Poland', 'Avusturya': 'Austria',
    'Çekya': 'Czechia', 'İsveç': 'Sweden', 'Danimarka': 'Denmark', 'Finlandiya': 'Finland',
    'İrlanda': 'Ireland', 'Portekiz': 'Portugal', 'Macaristan': 'Hungary', 'Romanya': 'Romania',
    'Bulgaristan': 'Bulgaria', 'Yunanistan': 'Greece', 'Slovakya': 'Slovakia', 'Slovenya': 'Slovenia',
    'Hırvatistan': 'Croatia', 'Litvanya': 'Lithuania', 'Letonya': 'Latvia', 'Estonya': 'Estonia',
    'Lüksemburg': 'Luxembourg', 'Kıbrıs': 'Cyprus', 'Malta': 'Malta'
  };

  var MONTHS = {
    tr: ['Ocak','Şubat','Mart','Nisan','Mayıs','Haziran','Temmuz','Ağustos','Eylül','Ekim','Kasım','Aralık'],
    en: ['January','February','March','April','May','June','July','August','September','October','November','December']
  };

  // HS fasıl adları — İngilizce (TR karşılıkları sayfaların kendi sözlüğünde)
  var FASIL_EN = {
    '01':'Live animals','02':'Meat and edible offal','03':'Fish and crustaceans','04':'Dairy, eggs, honey',
    '05':'Other animal products','06':'Live trees and plants','07':'Edible vegetables','08':'Edible fruit and nuts',
    '09':'Coffee, tea, spices','10':'Cereals','11':'Milling products','12':'Oil seeds','13':'Vegetable saps and extracts',
    '14':'Vegetable plaiting materials','15':'Animal and vegetable fats','16':'Meat and fish preparations',
    '17':'Sugars and confectionery','18':'Cocoa and preparations','19':'Cereal, flour and pastry products',
    '20':'Vegetable and fruit preparations','21':'Miscellaneous edible preparations','22':'Beverages and spirits',
    '23':'Food industry residues, animal feed','24':'Tobacco','25':'Salt, sulphur, earths and stone',
    '26':'Ores, slag and ash','27':'Mineral fuels and oils','28':'Inorganic chemicals','29':'Organic chemicals',
    '30':'Pharmaceutical products','31':'Fertilisers','32':'Tanning, dyeing extracts, paints','33':'Perfumery and cosmetics',
    '34':'Soap and washing preparations','35':'Albuminoidal substances, glues','36':'Explosives','37':'Photographic goods',
    '38':'Miscellaneous chemical products','39':'Plastics and articles thereof','40':'Rubber and articles thereof',
    '41':'Raw hides and skins','42':'Leather goods','43':'Furskins','44':'Wood and articles of wood','45':'Cork',
    '46':'Basketware and wickerwork','47':'Pulp of wood','48':'Paper and paperboard','49':'Printed books and newspapers',
    '50':'Silk','51':'Wool and animal hair','52':'Cotton','53':'Other vegetable textile fibres',
    '54':'Man-made filaments','55':'Man-made staple fibres','56':'Wadding, felt, twine and ropes',
    '57':'Carpets and floor coverings','58':'Special woven fabrics','59':'Impregnated or coated textiles',
    '60':'Knitted or crocheted fabrics','61':'Knitted apparel','62':'Non-knitted apparel',
    '63':'Other made-up textiles, worn clothing','64':'Footwear','65':'Headgear','66':'Umbrellas and walking sticks',
    '67':'Feathers and artificial flowers','68':'Articles of stone, plaster, cement','69':'Ceramic products',
    '70':'Glass and glassware','71':'Precious stones and jewellery','72':'Iron and steel','73':'Articles of iron or steel',
    '74':'Copper and articles thereof','75':'Nickel and articles thereof','76':'Aluminium and articles thereof',
    '78':'Lead and articles thereof','79':'Zinc and articles thereof','80':'Tin and articles thereof',
    '81':'Other base metals','82':'Tools of base metal','83':'Miscellaneous articles of base metal',
    '84':'Machinery and mechanical appliances','85':'Electrical machinery and equipment','86':'Railway vehicles',
    '87':'Motor vehicles','88':'Aircraft','89':'Ships and boats','90':'Optical, measuring, medical instruments',
    '91':'Clocks and watches','92':'Musical instruments','93':'Arms and ammunition','94':'Furniture and lighting',
    '95':'Toys, games and sports equipment','96':'Miscellaneous manufactured articles','97':'Works of art and antiques'
  };

  function t(k) {
    var d = DICT[lang] || DICT.tr || {};
    if (d[k] !== undefined) return d[k];
    return (DICT.tr && DICT.tr[k] !== undefined) ? DICT.tr[k] : k;
  }

  /** Karar metni: EN modunda orijinal dil, TR modunda Türkçe çeviri */
  function title(d) { return (lang === 'en' && d && d.title_o) ? d.title_o : (d ? d.title : ''); }
  function reason(d) { return (lang === 'en' && d && d.gerekce_o) ? d.gerekce_o : (d ? d.gerekce : ''); }

  function fmtDate(iso) {
    if (!iso) return '';
    var p = String(iso).split('-');
    if (p.length !== 3) return iso;
    var m = MONTHS[lang] || MONTHS.tr;
    return (+p[2]) + ' ' + m[(+p[1]) - 1] + ' ' + p[0];
  }
  function monthName(i) { return (MONTHS[lang] || MONTHS.tr)[i]; }

  function srcName(s) { return (SRC_NAMES[lang] && SRC_NAMES[lang][s]) || s; }
  function srcShort(s) { return (SRC_SHORT[lang] && SRC_SHORT[lang][s]) || (s || '').toUpperCase(); }
  function originName(o) { return (lang === 'en' && ORIGIN_EN[o]) ? ORIGIN_EN[o] : o; }
  function fasilName(code, trDict) {
    if (lang === 'en') return FASIL_EN[code] || (trDict && trDict[code]) || '';
    return (trDict && trDict[code]) || FASIL_EN[code] || '';
  }

  /** Sağ üstteki TR/EN anahtarını sayfaya ekler; değişimde cb() çağrılır. */
  function mount(cb) {
    onChange = cb || null;
    if (!document.querySelector('.langsw')) {
      var st = document.createElement('style');
      st.textContent =
        '.langsw{position:fixed;top:14px;right:16px;z-index:200;display:inline-flex;background:rgba(255,255,255,.9);' +
        'backdrop-filter:blur(8px);border:1px solid #d7e0ea;border-radius:100px;padding:3px;gap:2px;' +
        'box-shadow:0 6px 20px rgba(40,90,160,.10)}' +
        '.langsw button{border:none;background:transparent;border-radius:100px;padding:6px 13px;font-size:13px;' +
        'font-weight:700;color:#8693a6;letter-spacing:.03em;cursor:pointer;font-family:inherit}' +
        '.langsw button[aria-pressed="true"]{background:#16202b;color:#fff}' +
        '@media(max-width:520px){.langsw{top:8px;right:8px}}';
      document.head.appendChild(st);

      var box = document.createElement('div');
      box.className = 'langsw';
      box.setAttribute('role', 'group');
      box.setAttribute('aria-label', 'Dil / Language');
      box.innerHTML = '<button data-l="tr">TR</button><button data-l="en">EN</button>';
      document.body.appendChild(box);
      box.querySelectorAll('button').forEach(function (b) {
        b.onclick = function () { setLang(b.getAttribute('data-l')); };
      });
    }
    paint();
    apply();
  }

  function paint() {
    document.querySelectorAll('.langsw button').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.getAttribute('data-l') === lang));
    });
  }

  /** data-i18n işaretli statik metinleri doldurur. */
  function apply() {
    document.documentElement.setAttribute('lang', lang);
    document.querySelectorAll('[data-i18n]').forEach(function (el) {
      var v = t(el.getAttribute('data-i18n'));
      if (v) el.textContent = v;
    });
    document.querySelectorAll('[data-i18n-ph]').forEach(function (el) {
      var v = t(el.getAttribute('data-i18n-ph'));
      if (v) el.setAttribute('placeholder', v);
    });
    var ti = document.querySelector('title[data-i18n-title]');
    if (ti) { var v = t(ti.getAttribute('data-i18n-title')); if (v) document.title = v; }
  }

  function setLang(l) {
    if (l !== 'tr' && l !== 'en') return;
    if (l === lang) return;
    lang = l;
    try { localStorage.setItem(KEY, lang); } catch (e) {}
    paint(); apply();
    if (onChange) onChange();
  }

  // Başka sekmede dil değişirse burada da uygula
  g.addEventListener('storage', function (e) {
    if (e.key === KEY && (e.newValue === 'tr' || e.newValue === 'en') && e.newValue !== lang) {
      lang = e.newValue; paint(); apply(); if (onChange) onChange();
    }
  });

  g.BTIi18n = {
    get lang() { return lang; },
    setLang: setLang,
    dict: function (d) { DICT = { tr: (d && d.tr) || {}, en: (d && d.en) || {} }; },
    t: t, mount: mount, apply: apply,
    title: title, reason: reason,
    fmtDate: fmtDate, monthName: monthName,
    srcName: srcName, srcShort: srcShort, originName: originName, fasilName: fasilName,
    FASIL_EN: FASIL_EN, KEY: KEY
  };
})(window);
