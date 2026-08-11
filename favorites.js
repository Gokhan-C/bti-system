/**
 * BTIFav — "Favorilerim" deposu.
 *
 * Site tamamen statik (sunucu/veritabanı yok), bu yüzden kullanıcının
 * kaydettiği kararlar tarayıcının localStorage'ında tutulur. Aynı tarayıcıda
 * siteye tekrar gelindiğinde favoriler yerinde durur.
 *
 * Kayıt biçimi (localStorage anahtarı: BTI_FAV_KEY):
 *   { "<id>": { id, source, ref, hs, hs4, date, title, gerekce, url,
 *               origin, note, savedAt } }
 *
 * Her değişiklikte window'a 'bti-fav-change' event'i yayılır; sayfalar
 * buna abone olup kendini tazeler.
 */
(function (global) {
  'use strict';

  var KEY = 'bti_favorites_v1';

  function read() {
    try {
      var raw = localStorage.getItem(KEY);
      var obj = raw ? JSON.parse(raw) : {};
      return (obj && typeof obj === 'object') ? obj : {};
    } catch (e) {
      return {};
    }
  }

  function write(obj) {
    try {
      localStorage.setItem(KEY, JSON.stringify(obj));
    } catch (e) {
      // kota dolu / gizli mod — sessiz geç, UI yine de çalışsın
      console.warn('Favori kaydedilemedi:', e);
    }
    try {
      global.dispatchEvent(new CustomEvent('bti-fav-change'));
    } catch (e) {}
  }

  /** Bir kararın benzersiz kimliği. Ref yoksa GTİP+tarih ile türetilir. */
  function idOf(dec) {
    if (!dec) return '';
    var src = dec.source || '?';
    var ref = (dec.ref || '').trim();
    if (ref) return src + ':' + ref;
    return src + ':' + (dec.hs || dec.hs4 || '') + ':' + (dec.date || '');
  }

  function has(idOrDec) {
    var id = typeof idOrDec === 'string' ? idOrDec : idOf(idOrDec);
    return Object.prototype.hasOwnProperty.call(read(), id);
  }

  function add(dec, note) {
    if (!dec) return null;
    var id = idOf(dec);
    if (!id) return null;
    var db = read();
    var prev = db[id] || {};
    db[id] = {
      id: id,
      source: dec.source || '',
      ref: dec.ref || '',
      hs: dec.hs || '',
      hs4: dec.hs4 || '',
      date: dec.date || '',
      title: dec.title || '',
      gerekce: dec.gerekce || '',
      url: dec.url || '',
      origin: dec.origin || '',
      note: (note !== undefined && note !== null) ? note : (prev.note || ''),
      savedAt: prev.savedAt || new Date().toISOString()
    };
    write(db);
    return db[id];
  }

  function remove(idOrDec) {
    var id = typeof idOrDec === 'string' ? idOrDec : idOf(idOrDec);
    var db = read();
    if (db[id]) {
      delete db[id];
      write(db);
      return true;
    }
    return false;
  }

  /** Favorideyse çıkarır, değilse ekler. Sonuç: true = artık favoride. */
  function toggle(dec, note) {
    var id = idOf(dec);
    if (has(id)) { remove(id); return false; }
    add(dec, note);
    return true;
  }

  function setNote(idOrDec, note) {
    var id = typeof idOrDec === 'string' ? idOrDec : idOf(idOrDec);
    var db = read();
    if (!db[id]) return false;
    db[id].note = note || '';
    write(db);
    return true;
  }

  /** Tüm favoriler — varsayılan sıralama: en son kaydedilen önce. */
  function all() {
    var db = read();
    return Object.keys(db).map(function (k) { return db[k]; })
      .sort(function (a, b) {
        return (b.savedAt || '').localeCompare(a.savedAt || '');
      });
  }

  function count() { return Object.keys(read()).length; }

  /** Serbest metin araması: GTİP, ref, ürün, gerekçe, not, ülke, tarih. */
  function search(query) {
    var q = (query || '').trim().toLowerCase();
    var list = all();
    if (!q) return list;
    var terms = q.split(/\s+/);
    return list.filter(function (f) {
      var hay = [f.hs, f.hs4, f.ref, f.title, f.gerekce, f.note, f.origin,
                 f.date, f.source].join(' ').toLowerCase();
      return terms.every(function (t) { return hay.indexOf(t) !== -1; });
    });
  }

  function exportJSON() {
    return JSON.stringify(all(), null, 2);
  }

  function exportCSV() {
    var rows = [['GTIP', 'GTIP_TAM', 'REF', 'KAYNAK', 'ULKE', 'TARIH', 'URUN', 'GEREKCE', 'NOT', 'LINK']];
    all().forEach(function (f) {
      rows.push([f.hs4, f.hs, f.ref, f.source, f.origin, f.date,
                 f.title, f.gerekce, f.note, f.url]);
    });
    return rows.map(function (r) {
      return r.map(function (c) {
        c = (c === null || c === undefined) ? '' : String(c);
        return '"' + c.replace(/"/g, '""').replace(/\r?\n/g, ' ') + '"';
      }).join(',');
    }).join('\r\n');
  }

  /** Dosya indirtir (dışa aktarma butonları için). */
  function download(filename, content, mime) {
    var blob = new Blob([content], { type: (mime || 'text/plain') + ';charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 0);
  }

  global.BTIFav = {
    idOf: idOf, has: has, add: add, remove: remove, toggle: toggle,
    setNote: setNote, all: all, count: count, search: search,
    exportJSON: exportJSON, exportCSV: exportCSV, download: download,
    KEY: KEY
  };
})(window);
