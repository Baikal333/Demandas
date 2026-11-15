/*
 * Lectura y reescritura de formatos de documento, íntegramente en el navegador.
 * Formatos: DOCX, XLSX, PPTX, ODT, ODS, ODP, PDF (texto → DOCX) y texto plano
 * (TXT, CSV, TSV, MD, JSON, XML, HTML, SRT, LOG…).
 */
(function (global) {
  'use strict';
  const { readZip, writeZip } = global.MiniZip;
  const A = global.Anonimizador;

  const FAKE_AUTHOR = 'Autor Ficticio';
  const FAKE_INITIALS = 'AF';
  const FAKE_ORG = 'Entidad Ficticia';

  const enc = new TextEncoder();
  const dec = new TextDecoder('utf-8');

  // ------------------------------------------------------------- texto plano
  const TEXT_EXT = ['txt', 'csv', 'tsv', 'md', 'markdown', 'json', 'xml', 'html', 'htm', 'srt', 'vtt', 'log', 'yaml', 'yml', 'ini', 'tex', 'eml'];

  function decodeText(buf) {
    const u8 = new Uint8Array(buf);
    const bom = u8[0] === 0xef && u8[1] === 0xbb && u8[2] === 0xbf;
    try {
      return { text: new TextDecoder('utf-8', { fatal: true }).decode(u8), bom, encoding: 'UTF-8' };
    } catch {
      return { text: new TextDecoder('windows-1252').decode(u8), bom: false, encoding: 'Windows-1252 (convertido a UTF-8)' };
    }
  }

  async function loadText(file, ext) {
    const { text, bom, encoding } = decodeText(await file.arrayBuffer());
    return {
      kind: 'texto', label: `Texto (${ext.toUpperCase()}, ${encoding})`, name: file.name, text, warnings: [],
      async build(entities) {
        const out = A.replaceText(text, entities);
        return { blob: new Blob([bom ? '﻿' : '', out], { type: file.type || 'text/plain;charset=utf-8' }), ext };
      },
    };
  }

  // ------------------------------------------------------------ formatos XML
  const PROFILES = {
    docx: {
      label: 'Documento de Word (DOCX)',
      parts: /^word\/(document|header\d*|footer\d*|footnotes|endnotes|comments)\.xml$/,
      para: new Set(['w:p']),
      textTags: ['w:t', 'w:delText', 'w:instrText'],
      preserveSpace: true,
      media: /^word\/media\//,
    },
    xlsx: {
      label: 'Hoja de cálculo de Excel (XLSX)',
      parts: /^xl\/(sharedStrings|worksheets\/sheet\d+|comments\d*|threadedComments\/threadedComment\d*)\.xml$/,
      para: new Set(['si', 'is', 'text', 'tc:text']),
      textTags: ['t', 'tc:text'],
      preserveSpace: true,
      numericCells: /^xl\/worksheets\/sheet\d+\.xml$/,
      media: /^xl\/media\//,
    },
    pptx: {
      label: 'Presentación de PowerPoint (PPTX)',
      parts: /^ppt\/(slides\/slide\d+|notesSlides\/notesSlide\d+|comments\/comment\d*|comments\/modernComment[^/]*|diagrams\/data\d+)\.xml$/,
      para: new Set(['a:p', 'p:text', 'p188:txBody']),
      textTags: ['a:t', 'p:text'],
      media: /^ppt\/media\//,
    },
    odt: {
      label: 'Documento OpenDocument (ODT/ODS/ODP)',
      parts: /^(content|styles)\.xml$/,
      para: new Set(['text:p', 'text:h']),
      textNodes: true,
      media: /^Pictures\//,
    },
  };
  PROFILES.ods = PROFILES.odt;
  PROFILES.odp = PROFILES.odt;

  function parseXml(bytes) {
    const src = dec.decode(bytes);
    const decl = (src.match(/^\s*<\?xml[^>]*\?>/) || [''])[0];
    const doc = new DOMParser().parseFromString(src, 'application/xml');
    if (doc.getElementsByTagName('parsererror').length) throw new Error('XML no válido');
    return { doc, decl };
  }
  function serializeXml({ doc, decl }) {
    let s = new XMLSerializer().serializeToString(doc);
    if (decl && !s.startsWith('<?xml')) s = decl + (decl.endsWith('\n') ? '' : '\r\n') + s;
    return enc.encode(s);
  }

  /** Agrupa los nodos de texto de un documento XML por párrafo. Devuelve [[{get,set}]] */
  function collectUnits(doc, profile, partName) {
    const groups = new Map();
    const order = [];
    const nearestPara = (node) => {
      for (let n = node.parentNode; n && n.nodeType === 1; n = n.parentNode) if (profile.para.has(n.nodeName)) return n;
      return null;
    };
    const push = (para, accessor) => {
      const key = para || accessor;
      if (!groups.has(key)) { groups.set(key, []); order.push(key); }
      groups.get(key).push(accessor);
    };
    if (profile.textNodes) {
      const walker = doc.createTreeWalker(doc.documentElement, 4 /* SHOW_TEXT */);
      for (let t = walker.nextNode(); t; t = walker.nextNode()) {
        const para = nearestPara(t);
        if (!para) continue;
        const node = t;
        push(para, { get: () => node.nodeValue, set: (v) => { node.nodeValue = v; } });
      }
    } else {
      const els = [];
      for (const tag of profile.textTags) els.push(...doc.getElementsByTagName(tag));
      // Orden de documento
      els.sort((a, b) => (a.compareDocumentPosition(b) & 4 ? -1 : 1));
      for (const el of els) {
        const isInstr = el.nodeName === 'w:instrText';
        const para = isInstr ? null : nearestPara(el);
        const node = el;
        push(para, {
          get: () => node.textContent,
          set: (v) => {
            node.textContent = v;
            if (profile.preserveSpace && /^\s|\s$/.test(v)) node.setAttribute('xml:space', 'preserve');
          },
        });
      }
    }
    const units = order.map((k) => groups.get(k));
    // Celdas numéricas de Excel (teléfonos, NSS… guardados como número).
    if (profile.numericCells && profile.numericCells.test(partName)) {
      for (const c of doc.getElementsByTagName('c')) {
        const t = c.getAttribute('t');
        if (t && t !== 'n') continue;
        const v = c.getElementsByTagName('v')[0];
        if (!v || c.getElementsByTagName('f').length) continue;
        units.push([{
          numeric: true,
          get: () => v.textContent,
          set: (val) => {
            if (/^-?\d+(\.\d+)?(E[+-]?\d+)?$/i.test(val)) { v.textContent = val; return; }
            // Convertir a texto en línea
            const ns = c.namespaceURI;
            c.removeChild(v);
            c.setAttribute('t', 'inlineStr');
            const is = doc.createElementNS(ns, 'is');
            const tt = doc.createElementNS(ns, 't');
            tt.textContent = val;
            is.appendChild(tt);
            c.appendChild(is);
          },
        }]);
      }
    }
    return units;
  }

  const NUMERIC_TYPES = new Set(['telefono', 'nss', 'tarjeta', 'iban', 'dni', 'custom', 'manual']);

  /** Aplica las sustituciones a un párrafo cuyo texto puede estar repartido en varios nodos. */
  function applyUnit(unit, entities) {
    const texts = unit.map((n) => n.get() || '');
    const full = texts.join('');
    if (!full) return 0;
    const ents = unit[0].numeric ? entities.filter((e) => NUMERIC_TYPES.has(e.type)) : entities;
    const ms = A.findMatches(full, ents);
    if (!ms.length) return 0;
    const owner = new Array(full.length);
    let k = 0;
    texts.forEach((t, i) => { for (let j = 0; j < t.length; j++) owner[k++] = i; });
    const out = texts.map(() => '');
    let pos = 0;
    for (const m of ms) {
      for (; pos < m.start; pos++) out[owner[pos]] += full[pos];
      out[owner[m.start]] += A.adaptCase(m.match, m.entity.replacement);
      pos = m.end;
    }
    for (; pos < full.length; pos++) out[owner[pos]] += full[pos];
    unit.forEach((n, i) => { if (out[i] !== texts[i]) n.set(out[i]); });
    return ms.length;
  }

  // Metadatos: autores, empresa, revisores…
  function scrubMetadata(doc, entities) {
    let n = 0;
    const setText = (tag, val) => {
      for (const el of [...doc.getElementsByTagName(tag)]) { if (el.textContent.trim()) { el.textContent = val; n++; } }
    };
    ['dc:creator', 'cp:lastModifiedBy', 'meta:initial-creator', 'Manager', 'author', 'meta:printed-by'].forEach((t) => setText(t, FAKE_AUTHOR));
    ['Company'].forEach((t) => setText(t, FAKE_ORG));
    for (const t of ['dc:title', 'dc:subject', 'dc:description', 'cp:keywords', 'meta:keyword', 'vt:lpwstr', 'cp:category']) {
      for (const el of [...doc.getElementsByTagName(t)]) {
        const v = el.textContent;
        const r = A.replaceText(v, entities);
        if (r !== v) { el.textContent = r; n++; }
      }
    }
    // Atributos de autoría (control de cambios, comentarios, personas)
    const all = doc.getElementsByTagName('*');
    for (const el of all) {
      const tag = el.nodeName.replace(/^[^:]+:/, '');
      for (const attr of [...el.attributes]) {
        const name = attr.name.replace(/^[^:]+:/, '');
        let val = null;
        if (name === 'author') val = FAKE_AUTHOR;
        else if (name === 'initials') val = FAKE_INITIALS;
        else if ((name === 'name' || name === 'displayName') && /^(cmAuthor|author|person)$/.test(tag)) val = FAKE_AUTHOR;
        else if (name === 'userId' && attr.value) val = FAKE_AUTHOR;
        else if (name === 'providerId' && attr.value) val = 'None';
        if (val !== null && attr.value !== val) { el.setAttribute(attr.name, val); n++; }
      }
    }
    return n;
  }

  async function blankImage(ext) {
    const mime = /jpe?g$/i.test(ext) ? 'image/jpeg' : /png$/i.test(ext) ? 'image/png' : /gif$/i.test(ext) ? 'image/gif' : /webp$/i.test(ext) ? 'image/webp' : null;
    if (!mime) return null;
    const c = document.createElement('canvas');
    c.width = 4; c.height = 4;
    const g = c.getContext('2d');
    g.fillStyle = '#ffffff'; g.fillRect(0, 0, 4, 4);
    const outMime = mime === 'image/gif' ? 'image/png' : mime;
    const blob = await new Promise((r) => c.toBlob(r, outMime, 0.9));
    return blob ? new Uint8Array(await blob.arrayBuffer()) : null;
  }

  async function loadZipDoc(file, ext) {
    const profile = PROFILES[ext];
    const buf = await file.arrayBuffer();
    const entries = await readZip(buf);
    const segments = [];
    const warnings = [];
    let images = 0;
    for (const e of entries) {
      if (profile.parts.test(e.name)) {
        const x = parseXml(e.data);
        for (const u of collectUnits(x.doc, profile, e.name)) {
          const t = u.map((n) => n.get() || '').join('');
          if (t.trim()) segments.push(t);
        }
      }
      if (profile.media.test(e.name) && /\.(png|jpe?g|gif|bmp|tiff?|webp|emf|wmf|svg)$/i.test(e.name)) images++;
    }
    if (images) warnings.push(`El documento contiene ${images} imagen(es). Su contenido no se analiza: si alguna muestra datos personales (p. ej. una copia del DNI), active «Sustituir imágenes por recuadros en blanco».`);
    if (entries.some((e) => /vbaProject\.bin$/i.test(e.name))) warnings.push('El documento contiene macros; se conservan sin analizar.');
    return {
      kind: 'zip', label: profile.label, name: file.name, text: segments.join('\n'), warnings, images,
      async build(entities, opts = {}) {
        const fresh = await readZip(buf);
        const stats = { replaced: 0, meta: 0, images: 0 };
        for (const e of fresh) {
          const isPart = profile.parts.test(e.name);
          const isMeta = /^(docProps\/(core|app|custom)\.xml|meta\.xml|word\/people\.xml|ppt\/commentAuthors\.xml|ppt\/authors\.xml|xl\/persons\/person\.xml)$/.test(e.name);
          const isComments = /comment|people|person|authors/i.test(e.name) || isPart;
          const isRels = /\.rels$/.test(e.name);
          if (isPart || (opts.metadata !== false && (isMeta || isComments)) || isRels) {
            let x;
            try { x = parseXml(e.data); } catch { continue; }
            if (isPart) for (const u of collectUnits(x.doc, profile, e.name)) stats.replaced += applyUnit(u, entities);
            if (opts.metadata !== false && (isMeta || isComments || e.name === 'content.xml' || e.name === 'styles.xml')) stats.meta += scrubMetadata(x.doc, entities);
            if (isRels) {
              // Hipervínculos (mailto:, URLs con datos personales)
              for (const r of x.doc.getElementsByTagName('Relationship')) {
                const tgt = r.getAttribute('Target') || '';
                if (r.getAttribute('TargetMode') === 'External') {
                  const nt = A.replaceText(decodeURIComponentSafe(tgt), entities);
                  if (nt !== decodeURIComponentSafe(tgt)) r.setAttribute('Target', nt);
                }
              }
            }
            if (e.name === 'content.xml' || e.name === 'styles.xml') {
              for (const a of x.doc.getElementsByTagName('text:a')) {
                const h = a.getAttribute('xlink:href');
                if (h) { const nh = A.replaceText(decodeURIComponentSafe(h), entities); if (nh !== decodeURIComponentSafe(h)) a.setAttribute('xlink:href', nh); }
              }
            }
            e.data = serializeXml(x);
          }
          // Miniaturas de la primera página (muestran el contenido original).
          if (opts.metadata !== false && /^(docProps\/thumbnail\.(jpe?g|png)|Thumbnails\/thumbnail\.png)$/i.test(e.name)) {
            const b = await blankImage(e.name);
            if (b) { e.data = b; stats.meta++; }
          }
          if (opts.images && profile.media.test(e.name)) {
            const b = await blankImage(e.name);
            if (b) { e.data = b; stats.images++; }
          }
        }
        return { blob: await writeZip(fresh), ext, stats };
      },
    };
  }

  function decodeURIComponentSafe(s) { try { return decodeURIComponent(s); } catch { return s; } }

  // ------------------------------------------------------------------- PDF
  async function loadPdf(file) {
    const pdfjs = global.pdfjsLib;
    if (!pdfjs) throw new Error('El lector de PDF no está disponible en esta copia de la aplicación.');
    const data = new Uint8Array(await file.arrayBuffer());
    let pdf;
    try {
      pdf = await pdfjs.getDocument({ data, isEvalSupported: false, disableFontFace: true, useSystemFonts: false, stopAtErrors: false }).promise;
    } catch (err) {
      if (err && err.name === 'PasswordException') throw new Error('El PDF está protegido con contraseña. Quite la protección antes de anonimizarlo.');
      throw err;
    }
    const pages = [];
    for (let i = 1; i <= pdf.numPages; i++) {
      const page = await pdf.getPage(i);
      const tc = await page.getTextContent();
      let line = '', lines = [], lastY = null;
      for (const it of tc.items) {
        if (!('str' in it)) continue;
        const y = it.transform ? Math.round(it.transform[5]) : null;
        if (lastY !== null && y !== null && Math.abs(y - lastY) > 2 && line) { lines.push(line); line = ''; }
        line += it.str;
        if (it.hasEOL) { lines.push(line); line = ''; }
        lastY = y;
      }
      if (line) lines.push(line);
      pages.push(lines.map((l) => l.replace(/\s+$/, '')));
    }
    const text = pages.map((p) => p.join('\n')).join('\n\n');
    const warnings = ['Los PDF no se pueden reescribir conservando el diseño: se genera un documento Word (DOCX) con el texto anonimizado, página a página. Revise el resultado.'];
    if (!text.replace(/\s/g, '').length) throw new Error('El PDF no contiene texto seleccionable (probablemente es un escaneo). Pase antes un OCR al documento.');
    const meta = await pdf.getMetadata().catch(() => null);
    if (meta?.info?.Author) warnings.push('Los metadatos del PDF original (autor, etc.) no se trasladan al documento generado.');
    return {
      kind: 'pdf', label: `PDF (${pdf.numPages} pág.) → se exporta como DOCX`, name: file.name, text, warnings,
      async build(entities) {
        const paras = [];
        pages.forEach((p, i) => {
          if (i) paras.push({ pageBreak: true });
          for (const l of p) paras.push({ text: A.replaceText(l, entities) });
        });
        return { blob: await makeDocx(paras), ext: 'docx' };
      },
    };
  }

  function xmlEsc(s) { return s.replace(/[<>&"]/g, (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;' }[c])); }

  async function makeDocx(paras) {
    const body = paras.map((p) => p.pageBreak
      ? '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'
      : `<w:p><w:r><w:t xml:space="preserve">${xmlEsc(p.text)}</w:t></w:r></w:p>`).join('');
    const files = {
      '[Content_Types].xml': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>',
      '_rels/.rels': '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>',
      'docProps/core.xml': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator>${FAKE_AUTHOR}</dc:creator><cp:lastModifiedBy>${FAKE_AUTHOR}</cp:lastModifiedBy><dc:title>Documento anonimizado</dc:title></cp:coreProperties>`,
      'word/document.xml': `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>${body}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1417" w:right="1701" w:bottom="1417" w:left="1701" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>`,
    };
    return writeZip(Object.entries(files).map(([name, s]) => ({ name, method: 8, data: enc.encode(s) })));
  }

  // ------------------------------------------------------------- despacho
  const SUPPORTED = ['docx', 'xlsx', 'pptx', 'odt', 'ods', 'odp', 'pdf', ...TEXT_EXT];

  async function loadDocument(file) {
    const ext = (file.name.match(/\.([^.]+)$/) || [, ''])[1].toLowerCase();
    if (PROFILES[ext]) return loadZipDoc(file, ext);
    if (ext === 'pdf') return loadPdf(file);
    if (TEXT_EXT.includes(ext) || (!ext && file.type.startsWith('text/'))) return loadText(file, ext || 'txt');
    if (['doc', 'xls', 'ppt', 'rtf', 'pages', 'wpd'].includes(ext)) {
      throw new Error(`El formato .${ext} no está soportado directamente. Ábralo y guárdelo como .docx (o .xlsx / .pptx) y vuelva a intentarlo.`);
    }
    throw new Error(`Formato no soportado (.${ext || '?'}). Formatos admitidos: ${SUPPORTED.join(', ')}.`);
  }

  function textDocument(text) {
    return {
      kind: 'texto', label: 'Texto pegado', name: 'texto.txt', text, warnings: [],
      async build(entities) { return { blob: new Blob([A.replaceText(text, entities)], { type: 'text/plain;charset=utf-8' }), ext: 'txt' }; },
    };
  }

  global.Formatos = { loadDocument, textDocument, SUPPORTED, makeDocx };
})(typeof window !== 'undefined' ? window : globalThis);
