#!/usr/bin/env node
/**
 * BTI Word Rapor Oluşturucu
 * Kullanım: node build_docx.js report_data.json output.docx
 */

'use strict';

const fs   = require('fs');
const path = require('path');

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, BorderStyle, WidthType, ShadingType, VerticalAlign,
  PageNumber, Header, Footer, ExternalHyperlink, UnderlineType,
} = require('docx');

// ── Sabitler ────────────────────────────────────────────────────────────────

const BLUE_DARK  = '1F3864';
const BLUE_MID   = '2E75B6';
const LINK_COLOR = '1155CC';
const WHITE      = 'FFFFFF';
const GRAY_LIGHT = 'F5F7FA';
const RED        = 'C0392B';

const brd      = { style: BorderStyle.SINGLE, size: 4, color: 'CCCCCC' };
const borders  = { top: brd, bottom: brd, left: brd, right: brd };
const noBorder = { style: BorderStyle.NONE,   size: 0, color: WHITE };
const noBorders= { top: noBorder, bottom: noBorder, left: noBorder, right: noBorder };

// ── Yardımcılar ────────────────────────────────────────────────────────────

function tc(text, shade, width, opts = {}) {
  const { bold=false, size=15, color='444444', center=false, mono=false } = opts;
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill: shade || WHITE, type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    verticalAlign: VerticalAlign.TOP,
    children: [new Paragraph({
      alignment: center ? AlignmentType.CENTER : AlignmentType.LEFT,
      children: [new TextRun({ text: String(text || ''), bold, size, color, font: mono ? 'Courier New' : 'Arial' })]
    })]
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
      new TextRun({ text: '█'.repeat(barLen) + ' ' + count, size: 16, color: BLUE_MID, font: 'Courier New' })
    ]})]
  });
}

function hdrRow(cols, widths, fill = BLUE_MID) {
  return new TableRow({ tableHeader: true, children: cols.map((c, i) =>
    new TableCell({
      borders,
      width: { size: widths[i], type: WidthType.DXA },
      shading: { fill, type: ShadingType.CLEAR },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      verticalAlign: VerticalAlign.CENTER,
      children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
        new TextRun({ text: c, bold: true, size: 16, color: WHITE, font: 'Arial' })
      ]})]
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
    })]
  });
}

function refCell(ref, shade, width) {
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill: shade || WHITE, type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    verticalAlign: VerticalAlign.TOP,
    children: [new Paragraph({ children: [makeRefLink(ref)] })]
  });
}

function descCell(descText, shade, width, hasImage) {
  const runs = [new TextRun({ text: descText || '', size: 15, color: '444444', font: 'Arial' })];
  if (hasImage) {
    runs.push(new TextRun({
      text: '📷 EBTI\'de görsel mevcuttur',
      bold: true, size: 15, color: RED, font: 'Arial', break: 1,
    }));
  }
  return new TableCell({
    borders,
    width: { size: width, type: WidthType.DXA },
    shading: { fill: shade || WHITE, type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    verticalAlign: VerticalAlign.TOP,
    children: [new Paragraph({ children: runs })]
  });
}

function justCell(justText, casList, shade, width) {
  const children = [new Paragraph({ children: [
    new TextRun({ text: justText || '', size: 15, color: '555555', font: 'Arial' })
  ]})];
  if (casList && casList.length > 0) {
    children.push(new Paragraph({ spacing: { before: 100 }, children: [
      new TextRun({ text: 'CAS No: ', bold: true, size: 16, color: RED, font: 'Arial' }),
      new TextRun({ text: casList.join(', '), bold: true, size: 16, color: RED, font: 'Courier New' }),
    ]}));
  }
  return tcMulti(children, shade, width);
}

function spacer() {
  return new Paragraph({ spacing: { before: 200, after: 200 }, children: [] });
}

function sectionTitle(text) {
  return new Paragraph({
    spacing: { before: 300, after: 120 },
    children: [new TextRun({ text, bold: true, size: 22, color: BLUE_DARK, font: 'Arial' })]
  });
}

// ── Rapor Bölümleri ─────────────────────────────────────────────────────────

function makeTitleBlock(data) {
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 200, after: 80 },
      children: [new TextRun({ text: 'AVRUPA BAĞLAYICI TARİFE BİLGİSİ', bold: true, size: 36, color: BLUE_DARK, font: 'Arial' })]
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 80 },
      children: [new TextRun({ text: 'Günlük BTI Raporu', size: 24, color: BLUE_MID, font: 'Arial' })]
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 300 },
      children: [new TextRun({ text: data.report_date_tr, size: 20, color: '666666', font: 'Arial' })]
    }),
  ];
}

function makeSummaryCards(data) {
  return new Table({
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
            new TextRun({ text: String(data.total), bold: true, size: 40, color: WHITE, font: 'Arial' })
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, children: [
            new TextRun({ text: 'Toplam BTI', size: 18, color: 'BBCCDD', font: 'Arial' })
          ]})
        ]
      }),
      new TableCell({
        borders: noBorders,
        width: { size: 3120, type: WidthType.DXA },
        shading: { fill: BLUE_MID, type: ShadingType.CLEAR },
        margins: { top: 120, bottom: 120, left: 120, right: 120 },
        children: [
          new Paragraph({ alignment: AlignmentType.CENTER, children: [
            new TextRun({ text: String(data.country_count), bold: true, size: 40, color: WHITE, font: 'Arial' })
          ]}),
          new Paragraph({ alignment: AlignmentType.CENTER, children: [
            new TextRun({ text: 'Ülke', size: 18, color: 'CCE0F5', font: 'Arial' })
          ]})
        ]
      }),
    ]})]
  });
}

function makeCountryTable(countryStats) {
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

function makeCountrySection(countryCode, countryName, records) {
  const sorted = [...records].sort((a, b) => a.hs.localeCompare(b.hs));
  const widths = [950, 1600, 950, 3100, 3100];
  const detailRows = [
    hdrRow(['GTİP', 'BTI Ref. No', 'Tarih', 'Eşyanın Tanımı', 'Sınıflandırma Gerekçesi'], widths, BLUE_MID)
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
      ]
    }),
    new Table({ width: { size: 9700, type: WidthType.DXA }, columnWidths: widths, rows: detailRows }),
  ];
}

// ── Ana Fonksiyon ───────────────────────────────────────────────────────────

async function main() {
  const [,, jsonPath, docxPath] = process.argv;
  if (!jsonPath || !docxPath) {
    console.error('Kullanım: node build_docx.js data.json output.docx');
    process.exit(1);
  }

  const data = JSON.parse(fs.readFileSync(jsonPath, 'utf8'));

  // Ülkelere göre kayıtları grupla
  const byCountry = {};
  data.records.forEach(r => {
    (byCountry[r.country] = byCountry[r.country] || []).push(r);
  });

  // Doküman içeriğini oluştur
  const content = [];

  // Başlık
  content.push(...makeTitleBlock(data));

  // Özet kartlar (2'li)
  content.push(makeSummaryCards(data));
  content.push(spacer());

  // Ülke dağılım tablosu
  content.push(sectionTitle('Ülkelere Göre Dağılım'));
  content.push(makeCountryTable(data.country_stats));
  content.push(spacer());

  // GTİP Top 10
  content.push(sectionTitle('En Çok BTI Verilen GTİP — Top 10'));
  content.push(makeGtipTop10(data.gtip_top10));

  // Ülke detay bölümleri (country_stats sırasına göre)
  data.country_stats.forEach(cs => {
    const recs = byCountry[cs.code] || [];
    if (recs.length === 0) return;
    content.push(...makeCountrySection(cs.code, cs.name, recs));
  });

  // Belge oluştur
  const doc = new Document({
    styles: { default: { document: { run: { font: 'Arial', size: 20 } } } },
    sections: [{
      properties: {
        page: {
          size: { width: 12240, height: 15840 },
          margin: { top: 900, right: 900, bottom: 900, left: 900 },
        }
      },
      headers: { default: new Header({ children: [
        new Paragraph({
          alignment: AlignmentType.RIGHT,
          border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: BLUE_MID, space: 1 } },
          children: [new TextRun({ text: `EBTI Günlük BTI Raporu  |  ${data.report_date_tr}`, size: 16, color: '888888', font: 'Arial' })]
        })
      ]})},
      footers: { default: new Footer({ children: [
        new Paragraph({
          alignment: AlignmentType.CENTER,
          border: { top: { style: BorderStyle.SINGLE, size: 4, color: BLUE_MID, space: 1 } },
          children: [
            new TextRun({ text: 'Sayfa ', size: 16, color: '888888', font: 'Arial' }),
            new TextRun({ children: [PageNumber.CURRENT], size: 16, color: '888888', font: 'Arial' }),
            new TextRun({ text: '  |  Gökhan Ç.', size: 16, color: '888888', font: 'Arial' }),
          ]
        })
      ]})},
      children: content,
    }]
  });

  const buf = await Packer.toBuffer(doc);
  fs.writeFileSync(docxPath, buf);
  console.log(`Rapor kaydedildi: ${docxPath}`);
}

main().catch(err => { console.error(err); process.exit(1); });
