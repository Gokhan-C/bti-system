#!/usr/bin/env node
/**
 * BTI Birleşik Rapor Oluşturucu
 * Kullanım: node build_unified_docx.js unified_data.json output.docx
 *
 * JSON yapısı:
 * {
 *   "date": "2026-05-17",
 *   "countries": [{"name", "count", "color", "label_color"}, ...],
 *   "eu_ebti":  { report_date_tr, total, country_count, country_stats, gtip_top10, records },
 *   "us_cbp":   { stats, records, date_str },
 *   "ca_cbsa":  { records, date_str }
 * }
 */

'use strict';

const fs = require('fs');

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, BorderStyle, WidthType, ShadingType, VerticalAlign,
  PageNumber, Header, Footer, ExternalHyperlink, UnderlineType,
} = require('docx');

// ── Renkler ──────────────────────────────────────────────────────────────────

const BLUE_DARK  = '1F3864';
const BLUE_MID   = '2E75B6';
const BLUE_LIGHT = 'EBF3FB';
const RED_US     = '7B241C';
const RED_CA     = '922B21';
const NAVY_UK    = '012169';
const RED_BOLD   = 'C0392B';
const LINK_COLOR = '1155CC';
const WHITE      = 'FFFFFF';
const GRAY_LIGHT = 'F5F7FA';

// ── Kenarlık tanımları ───────────────────────────────────────────────────────

const brd       = { style: BorderStyle.SINGLE, size: 4, color: 'CCCCCC' };
const borders   = { top: brd, bottom: brd, left: brd, right: brd };
const noBorder  = { style: BorderStyle.NONE, size: 0, color: WHITE };
const noBorders = { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder };

// ── Genel yardımcılar ────────────────────────────────────────────────────────

function spacer() {
  return new Paragraph({ spacing: { before: 200, after: 200 }, children: [] });
}

function sectionTitle(text) {
  return new Paragraph({
    spacing: { before: 300, after: 120 },
    children: [new TextRun({ text, bold: true, size: 22, color: BLUE_DARK, font: 'Arial' })],
  });
}

function makeSectionBanner(title, bgColor) {
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    rows: [new TableRow({ children: [
      new TableCell({
        borders,
        width: { size: 9360, type: WidthType.DXA },
        shading: { fill: bgColor, type: ShadingType.CLEAR },
        margins: { top: 140, bottom: 140, left: 200, right: 200 },
        children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
          new TextRun({ text: title, bold: true, size: 28, color: WHITE, font: 'Arial' }),
        ]})],
      }),
    ]})]
  });
}

function makeDocTitle(title, subtitle) {
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 200, after: 80 },
      children: [new TextRun({ text: title, bold: true, size: 34, color: BLUE_DARK, font: 'Arial' })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 300 },
      children: [new TextRun({ text: subtitle, size: 20, color: '666666', font: 'Arial', italics: true })],
    }),
  ];
}

function makeInfoTable(rows) {
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [2500, 6860],
    rows: rows.map(([label, value]) =>
      new TableRow({ children: [
        new TableCell({
          borders,
          width: { size: 2500, type: WidthType.DXA },
          shading: { fill: BLUE_LIGHT, type: ShadingType.CLEAR },
          margins: { top: 80, bottom: 80, left: 120, right: 120 },
          children: [new Paragraph({ children: [
            new TextRun({ text: String(label || ''), bold: true, size: 20, color: '333333', font: 'Arial' }),
          ]})],
        }),
        new TableCell({
          borders,
          width: { size: 6860, type: WidthType.DXA },
          shading: { fill: WHITE, type: ShadingType.CLEAR },
          margins: { top: 80, bottom: 80, left: 120, right: 120 },
          children: [new Paragraph({ children: [
            new TextRun({ text: String(value || '-'), size: 20, color: '444444', font: 'Arial' }),
          ]})],
        }),
      ]})
    ),
  });
}

function makeRulingLink(url) {
  return new Paragraph({
    spacing: { before: 100, after: 60 },
    children: [
      new TextRun({ text: '📄 Tam metne erişmek için tıklayın: ', size: 20, color: '444444', font: 'Arial' }),
      new ExternalHyperlink({
        link: url,
        children: [new TextRun({
          text: url,
          style: 'Hyperlink',
          size: 20,
          color: LINK_COLOR,
          underline: { type: UnderlineType.SINGLE, color: LINK_COLOR },
          font: 'Arial',
        })],
      }),
    ],
  });
}

function makeRulingHeading(text, color) {
  return new Paragraph({
    spacing: { before: 100, after: 80 },
    children: [new TextRun({ text, bold: true, size: 28, color: color || BLUE_DARK, font: 'Arial' })],
  });
}

function makeSummarySection(summary) {
  const items = [
    ['1. Eşyanın Ticari Tanımı', summary.esya_tanimi  || '-'],
    ['2. GTİP Kararı',           summary.gtip_karar   || '-'],
    ['3. Teknik Gerekçe',        summary.teknik_gerekce || '-'],
  ];
  const result = [];
  items.forEach(([title, content]) => {
    result.push(new Paragraph({
      spacing: { before: 100, after: 40 },
      children: [new TextRun({ text: title, bold: true, size: 22, color: BLUE_MID, font: 'Arial' })],
    }));
    result.push(new Paragraph({
      spacing: { after: 80 },
      children: [new TextRun({ text: content, size: 20, color: '444444', font: 'Arial' })],
    }));
  });
  result.push(new Paragraph({
    spacing: { before: 100, after: 200 },
    children: [new TextRun({ text: '─'.repeat(80), size: 16, color: 'AAAAAA', font: 'Courier New' })],
  }));
  return result;
}

function makeNoResultsNotice() {
  return new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 300, after: 300 },
    children: [new TextRun({
      text: 'Bugün yeni HS sınıflandırma kararı bulunamadı.',
      size: 22, color: '888888', font: 'Arial', italics: true,
    })],
  });
}

// ── EU EBTI yardımcıları (build_docx.js ile birebir aynı) ───────────────────

function tc(text, shade, width, opts = {}) {
  const { bold = false, size = 15, color = '444444', center = false, mono = false } = opts;
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill: shade || WHITE, type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    verticalAlign: VerticalAlign.TOP,
    children: [new Paragraph({
      alignment: center ? AlignmentType.CENTER : AlignmentType.LEFT,
      children: [new TextRun({ text: String(text || ''), bold, size, color, font: mono ? 'Courier New' : 'Arial' })],
    })],
  });
}

function tcMulti(paragraphs, shade, width) {
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill: shade || WHITE, type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    verticalAlign: VerticalAlign.TOP,
    children: paragraphs,
  });
}

function barCell(count, maxCount, width) {
  const barLen = Math.max(1, Math.round((count / maxCount) * 22));
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill: GRAY_LIGHT, type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    verticalAlign: VerticalAlign.TOP,
    children: [new Paragraph({ children: [
      new TextRun({ text: '█'.repeat(barLen) + ' ' + count, size: 16, color: BLUE_MID, font: 'Courier New' }),
    ]})],
  });
}

function hdrRow(cols, widths, fill) {
  return new TableRow({ tableHeader: true, children: cols.map((c, i) =>
    new TableCell({
      borders,
      width: { size: widths[i], type: WidthType.DXA },
      shading: { fill: fill || BLUE_MID, type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      verticalAlign: VerticalAlign.CENTER,
      children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
        new TextRun({ text: c, bold: true, size: 16, color: WHITE, font: 'Arial' }),
      ]})],
    })
  )});
}

function encodeRef(ref) {
  return ref.replace(/\//g, '%2F');
}

function makeRefLink(ref) {
  const url = `https://ec.europa.eu/taxation_customs/dds2/ebti/ebti_consultation.jsp?Lang=en&reference=${encodeRef(ref)}&Expand=true&offset=1&allRecords=0&keywordmatchrule=OR`;
  return new ExternalHyperlink({
    link: url,
    children: [new TextRun({
      text: ref,
      style: 'Hyperlink',
      font: 'Courier New',
      size: 13,
      color: LINK_COLOR,
      underline: { type: UnderlineType.SINGLE, color: LINK_COLOR },
    })],
  });
}

function refCell(ref, shade, width) {
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill: shade || WHITE, type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    verticalAlign: VerticalAlign.TOP,
    children: [new Paragraph({ children: [makeRefLink(ref)] })],
  });
}

function descCell(descText, shade, width, hasImage) {
  const runs = [new TextRun({ text: descText || '', size: 15, color: '444444', font: 'Arial' })];
  if (hasImage) {
    runs.push(new TextRun({
      text: "📷 EBTI'de görsel mevcuttur",
      bold: true, size: 15, color: RED_BOLD, font: 'Arial', break: 1,
    }));
  }
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill: shade || WHITE, type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    verticalAlign: VerticalAlign.TOP,
    children: [new Paragraph({ children: runs })],
  });
}

function justCell(justText, casList, shade, width) {
  const children = [new Paragraph({ children: [
    new TextRun({ text: justText || '', size: 15, color: '555555', font: 'Arial' }),
  ]})];
  if (casList && casList.length > 0) {
    children.push(new Paragraph({ spacing: { before: 100 }, children: [
      new TextRun({ text: 'CAS No: ', bold: true, size: 16, color: RED_BOLD, font: 'Arial' }),
      new TextRun({ text: casList.join(', '), bold: true, size: 16, color: RED_BOLD, font: 'Courier New' }),
    ]}));
  }
  return tcMulti(children, shade, width);
}

function makeEuCountryTable(countryStats) {
  const maxCount = Math.max(...countryStats.map(s => s.count));
  const widths = [2800, 800, 1200, 4560];
  const rows = [hdrRow(['Ülke', 'Kod', 'BTI Sayısı', 'Dağılım'], widths, BLUE_DARK)];
  countryStats.forEach((s, i) => {
    const shade = i % 2 === 0 ? WHITE : GRAY_LIGHT;
    rows.push(new TableRow({ children: [
      tc(s.name,  shade, widths[0], { size: 15 }),
      tc(s.code,  shade, widths[1], { size: 15, mono: true, center: true }),
      tc(s.count, shade, widths[2], { size: 15, center: true, bold: true }),
      barCell(s.count, maxCount, widths[3]),
    ]}));
  });
  return new Table({ width: { size: 9360, type: WidthType.DXA }, columnWidths: widths, rows });
}

function makeGtipTop10(gtipTop10) {
  const maxCount = Math.max(...gtipTop10.map(g => g.count));
  const widths = [2000, 1200, 6160];
  const rows = [hdrRow(['GTİP (8 hane)', 'BTI Sayısı', 'Dağılım'], widths, BLUE_DARK)];
  gtipTop10.forEach((g, i) => {
    const shade = i % 2 === 0 ? WHITE : GRAY_LIGHT;
    rows.push(new TableRow({ children: [
      tc(g.hs,    shade, widths[0], { size: 15, mono: true }),
      tc(g.count, shade, widths[1], { size: 15, center: true, bold: true }),
      barCell(g.count, maxCount, widths[2]),
    ]}));
  });
  return new Table({ width: { size: 9360, type: WidthType.DXA }, columnWidths: widths, rows });
}

function makeEuCountrySection(countryCode, countryName, records) {
  const sorted = [...records].sort((a, b) => a.hs.localeCompare(b.hs));
  const widths = [950, 1600, 950, 3100, 3100];
  const detailRows = [
    hdrRow(['GTİP', 'BTI Ref. No', 'Tarih', 'Eşyanın Tanımı', 'Sınıflandırma Gerekçesi'], widths, BLUE_MID),
  ];
  sorted.forEach((r, i) => {
    const shade = i % 2 === 0 ? WHITE : GRAY_LIGHT;
    detailRows.push(new TableRow({ children: [
      tc(r.hs,         shade, widths[0], { size: 14, mono: true, color: BLUE_MID }),
      refCell(r.ref,   shade, widths[1]),
      tc(r.date_issue, shade, widths[2], { size: 13, center: true }),
      descCell(r.desc_tr, shade, widths[3], r.has_image),
      justCell(r.just_tr, r.cas, shade, widths[4]),
    ]}));
  });
  return [
    spacer(),
    new Paragraph({
      spacing: { before: 200, after: 100 },
      children: [
        new TextRun({ text: `${countryName} (${countryCode})`, bold: true, size: 22, color: BLUE_DARK, font: 'Arial' }),
        new TextRun({ text: `  —  ${records.length} BTI`, size: 18, color: '666666', font: 'Arial' }),
      ],
    }),
    new Table({ width: { size: 9700, type: WidthType.DXA }, columnWidths: widths, rows: detailRows }),
  ];
}

// ── Kapak sayfası ────────────────────────────────────────────────────────────

function makeCoverPage(data) {
  const content = [];

  content.push(new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 400, after: 120 },
    children: [new TextRun({ text: 'BAĞLAYICI TARİFE BİLGİLERİ', bold: true, size: 44, color: '1F3E6E', font: 'Arial' })],
  }));
  content.push(new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 500 },
    children: [new TextRun({ text: `Günlük Rapor  |  ${data.date}`, size: 24, color: '555555', font: 'Arial', italics: true })],
  }));

  const countries = data.countries;
  const colW = Math.floor(9360 / countries.length);
  const colWidths = countries.map(() => colW);

  content.push(new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: colWidths,
    rows: [
      new TableRow({ children: countries.map((c, i) =>
        new TableCell({
          borders: noBorders,
          width: { size: colWidths[i], type: WidthType.DXA },
          shading: { fill: c.color, type: ShadingType.CLEAR },
          margins: { top: 200, bottom: 160, left: 120, right: 120 },
          children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
            new TextRun({ text: String(c.count), bold: true, size: 56, color: WHITE, font: 'Arial' }),
          ]})],
        })
      )}),
      new TableRow({ children: countries.map((c, i) =>
        new TableCell({
          borders: noBorders,
          width: { size: colWidths[i], type: WidthType.DXA },
          shading: { fill: c.label_color, type: ShadingType.CLEAR },
          margins: { top: 100, bottom: 100, left: 120, right: 120 },
          children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
            new TextRun({ text: c.name, bold: true, size: 22, color: WHITE, font: 'Arial' }),
          ]})],
        })
      )}),
    ],
  }));

  return content;
}

// ── AB EBTI bölümü ───────────────────────────────────────────────────────────

function makeEuSection(euData) {
  if (!euData) return [makeNoResultsNotice()];
  const content = [];

  content.push(spacer());
  content.push(makeSectionBanner('AVRUPA BİRLİĞİ BTI', BLUE_DARK));
  content.push(spacer());

  // Başlık bloğu (build_docx.js makeTitleBlock ile aynı)
  content.push(new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 200, after: 80 },
    children: [new TextRun({ text: 'AVRUPA BAĞLAYICI TARİFE BİLGİSİ', bold: true, size: 36, color: BLUE_DARK, font: 'Arial' })],
  }));
  content.push(new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 80 },
    children: [new TextRun({ text: 'Günlük BTI Raporu', size: 24, color: BLUE_MID, font: 'Arial' })],
  }));
  content.push(new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 300 },
    children: [new TextRun({ text: euData.report_date_tr, size: 20, color: '666666', font: 'Arial' })],
  }));

  // Özet kartlar (build_docx.js makeSummaryCards ile aynı)
  content.push(new Table({
    width: { size: 6240, type: WidthType.DXA },
    columnWidths: [3120, 3120],
    alignment: AlignmentType.CENTER,
    rows: [new TableRow({ children: [
      new TableCell({
        borders: noBorders,
        width: { size: 3120, type: WidthType.DXA },
        shading: { fill: BLUE_DARK, type: ShadingType.CLEAR },
        margins: { top: 120, bottom: 120, left: 120, right: 120 },
        children: [
          new Paragraph({ alignment: AlignmentType.CENTER, children: [
            new TextRun({ text: String(euData.total), bold: true, size: 40, color: WHITE, font: 'Arial' }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, children: [
            new TextRun({ text: 'Toplam BTI', size: 18, color: 'BBCCDD', font: 'Arial' }),
          ]}),
        ],
      }),
      new TableCell({
        borders: noBorders,
        width: { size: 3120, type: WidthType.DXA },
        shading: { fill: BLUE_MID, type: ShadingType.CLEAR },
        margins: { top: 120, bottom: 120, left: 120, right: 120 },
        children: [
          new Paragraph({ alignment: AlignmentType.CENTER, children: [
            new TextRun({ text: String(euData.country_count), bold: true, size: 40, color: WHITE, font: 'Arial' }),
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, children: [
            new TextRun({ text: 'Ülke', size: 18, color: 'CCE0F5', font: 'Arial' }),
          ]}),
        ],
      }),
    ]})]
  }));
  content.push(spacer());

  // Ülke dağılım tablosu
  if (euData.country_stats && euData.country_stats.length > 0) {
    content.push(sectionTitle('Ülkelere Göre Dağılım'));
    content.push(makeEuCountryTable(euData.country_stats));
    content.push(spacer());
  }

  // GTİP Top 10
  if (euData.gtip_top10 && euData.gtip_top10.length > 0) {
    content.push(sectionTitle('En Çok BTI Verilen GTİP — Top 10'));
    content.push(makeGtipTop10(euData.gtip_top10));
  }

  // Ülke bazlı karar tabloları
  const byCountry = {};
  (euData.records || []).forEach(r => {
    (byCountry[r.country] = byCountry[r.country] || []).push(r);
  });
  (euData.country_stats || []).forEach(cs => {
    const recs = byCountry[cs.code] || [];
    if (recs.length > 0) content.push(...makeEuCountrySection(cs.code, cs.name, recs));
  });

  return content;
}

// ── ABD CBP bölümü ───────────────────────────────────────────────────────────

function makeUsCbpSection(cbpData) {
  const content = [];

  content.push(spacer());
  content.push(makeSectionBanner('AMERİKA BİRLEŞİK DEVLETLERİ CBP', RED_US));
  content.push(spacer());
  content.push(...makeDocTitle('ABD CBP Tarife Sınıflandırma Kararları', `CBP  |  ${cbpData.date_str}`));

  const stats = cbpData.stats || {};
  if (Object.keys(stats).length > 0) {
    content.push(new Paragraph({
      spacing: { before: 100, after: 60 },
      children: [new TextRun({ text: 'Günlük Karar İstatistikleri', bold: true, size: 24, color: '1F4E79', font: 'Arial' })],
    }));
    content.push(makeInfoTable([
      ['Tarih',                          cbpData.date_str],
      ['Toplam Çekilen Karar',           String(stats.total          || 0)],
      ['✓ Tarife Sınıflandırması',       String(stats.classification || 0)],
      ['✗ Menşei Kararı (raporda yok)', String(stats.origin         || 0)],
      ['– Diğer',                        String(stats.other          || 0)],
      ['Rapora Giren',                   String(stats.in_report      || 0)],
    ]));
    content.push(spacer());
  }

  const records = cbpData.records || [];
  if (records.length === 0) {
    content.push(makeNoResultsNotice());
  } else {
    records.forEach(rec => {
      content.push(makeRulingLink(rec.source_url));
      content.push(makeRulingHeading(`ABD CBP Kararı: ${rec.number}  |  ${rec.date_fmt}`, '1F4E79'));
      content.push(makeInfoTable([
        ['Karar Numarası', rec.number],
        ['Koleksiyon',     rec.collection],
        ['Karar Tarihi',   rec.date_fmt],
        ['HTS / GTİP',     rec.tariffs],
      ]));
      content.push(spacer());
      content.push(...makeSummarySection(rec.summary || {}));
    });
  }

  return content;
}

// ── Kanada CBSA bölümü ───────────────────────────────────────────────────────

function makeCaCbsaSection(cbsaData) {
  const content = [];

  content.push(spacer());
  content.push(makeSectionBanner('KANADA CBSA', RED_CA));
  content.push(spacer());
  content.push(...makeDocTitle('Kanada CBSA Tarife Sınıflandırma Kararları', `CBSA  |  ${cbsaData.date_str}`));

  const records = cbsaData.records || [];
  if (records.length === 0) {
    content.push(makeNoResultsNotice());
  } else {
    records.forEach(rec => {
      content.push(makeRulingLink(rec.source_url));
      content.push(makeRulingHeading(`Kanada CBSA Kararı: ${rec.ruling_id}  |  ${rec.date_fmt}`, '1F4E79'));
      content.push(makeInfoTable([
        ['Karar Numarası', rec.ruling_id],
        ['Karar Türü',     rec.ruling_type],
        ['Karar Tarihi',   rec.date_fmt],
        ['GTİP Kodu',      rec.hts],
        ['Başvurucu',      rec.applicant],
        ['Menşe Ülke',     rec.origin],
      ]));
      content.push(spacer());
      content.push(...makeSummarySection(rec.summary || {}));
    });
  }

  return content;
}

// ── İngiltere HMRC bölümü ────────────────────────────────────────────────────

function makeUkHmrcSection(ukData) {
  const content = [];

  content.push(spacer());
  content.push(makeSectionBanner('BİRLEŞİK KRALLIK HMRC', NAVY_UK));
  content.push(spacer());
  content.push(...makeDocTitle('İngiltere HMRC Tarife Sınıflandırma Kararları (ATaR)', `HMRC  |  ${ukData.date_str}`));

  const records = ukData.records || [];
  if (records.length === 0) {
    content.push(makeNoResultsNotice());
  } else {
    records.forEach(rec => {
      content.push(makeRulingLink(rec.source_url));
      content.push(makeRulingHeading(`İngiltere HMRC Kararı: ${rec.ruling_id}  |  ${rec.date_fmt}`, '1F4E79'));
      content.push(makeInfoTable([
        ['Karar Numarası',    rec.ruling_id],
        ['Karar Tarihi',      rec.date_fmt],
        ['Geçerlilik Bitişi', rec.expiry || '-'],
        ['GTİP Kodu',         rec.hts],
        ['Anahtar Kelimeler', rec.keywords || '-'],
      ]));
      content.push(spacer());
      content.push(...makeSummarySection(rec.summary || {}));
    });
  }

  return content;
}

// ── Ana fonksiyon ────────────────────────────────────────────────────────────

async function main() {
  const [,, jsonPath, docxPath] = process.argv;
  if (!jsonPath || !docxPath) {
    console.error('Kullanım: node build_unified_docx.js data.json output.docx');
    process.exit(1);
  }

  const data = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));
  const content = [];

  content.push(...makeCoverPage(data));

  if (data.eu_ebti)  content.push(...makeEuSection(data.eu_ebti));
  if (data.us_cbp)   content.push(...makeUsCbpSection(data.us_cbp));
  if (data.ca_cbsa)  content.push(...makeCaCbsaSection(data.ca_cbsa));
  if (data.uk_hmrc)  content.push(...makeUkHmrcSection(data.uk_hmrc));

  const doc = new Document({
    styles: { default: { document: { run: { font: 'Arial', size: 20 } } } },
    sections: [{
      properties: {
        page: {
          size: { width: 12240, height: 15840 },
          margin: { top: 900, right: 900, bottom: 900, left: 900 },
        },
      },
      headers: { default: new Header({ children: [
        new Paragraph({
          alignment: AlignmentType.RIGHT,
          border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: BLUE_MID, space: 1 } },
          children: [new TextRun({ text: `BTI Günlük Birleşik Rapor  |  ${data.date}`, size: 16, color: '888888', font: 'Arial' })],
        }),
      ]})},
      footers: { default: new Footer({ children: [
        new Paragraph({
          alignment: AlignmentType.CENTER,
          border: { top: { style: BorderStyle.SINGLE, size: 4, color: BLUE_MID, space: 1 } },
          children: [
            new TextRun({ text: 'Sayfa ', size: 16, color: '888888', font: 'Arial' }),
            new TextRun({ children: [PageNumber.CURRENT], size: 16, color: '888888', font: 'Arial' }),
            new TextRun({ text: '  |  Gökhan Ç.', size: 16, color: '888888', font: 'Arial' }),
          ],
        }),
      ]})},
      children: content,
    }],
  });

  const buf = await Packer.toBuffer(doc);
  fs.writeFileSync(docxPath, buf);
  console.log(`Birleşik rapor kaydedildi: ${docxPath}`);
}

main().catch(err => { console.error(err); process.exit(1); });
