/* Interfaz del anonimizador. Todo ocurre en el navegador. */
(function () {
  'use strict';
  const A = window.Anonimizador;
  const F = window.Formatos;
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => [...document.querySelectorAll(s)];
  const esc = (s) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  if (window.pdfjsLib) window.pdfjsLib.GlobalWorkerOptions.workerSrc = 'about:blank';

  const state = {
    doc: null,
    entities: [],
    overrides: new Map(), // clave -> {enabled, replacement}
    manual: [], // [{text, type}]
    view: 'orig',
  };
  const keyOf = (e) => e.type + '|' + e.text.toLowerCase();

  // ------------------------------------------------------------ opciones
  const catsEl = $('#cats');
  for (const c of A.CATEGORIES) {
    if (c.id === 'manual' || c.id === 'custom') continue;
    catsEl.insertAdjacentHTML('beforeend', `<label class="check"><input type="checkbox" data-cat="${c.id}" ${c.on ? 'checked' : ''}> ${esc(c.label)}</label>`);
  }
  function options() {
    const categories = {};
    $$('[data-cat]').forEach((i) => { categories[i.dataset.cat] = i.checked; });
    const custom = $('#custom').value.split('\n').map((l) => l.trim()).filter(Boolean).map((l) => {
      const [text, replacement] = l.split('=>').map((s) => s.trim());
      return { text, replacement: replacement || '' };
    });
    return {
      categories,
      style: $('input[name="style"]:checked').value,
      custom,
      extraEntities: state.manual,
    };
  }
  // Re-analizar al cambiar opciones
  $('#settings').addEventListener('change', (ev) => {
    if (ev.target.id === 'opt-meta' || ev.target.id === 'opt-images') return;
    if (state.doc) analyze();
  });
  let customTimer;
  $('#custom').addEventListener('input', () => { clearTimeout(customTimer); customTimer = setTimeout(() => state.doc && analyze(), 600); });

  // ------------------------------------------------------------ pestañas
  $$('.tab').forEach((t) => t.addEventListener('click', () => {
    $$('.tab').forEach((x) => x.classList.toggle('active', x === t));
    $$('.tabpane').forEach((p) => { p.hidden = p.dataset.pane !== t.dataset.tab; });
  }));

  // ------------------------------------------------------------ carga
  const drop = $('#drop');
  const input = $('#file');
  drop.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } });
  ['dragenter', 'dragover'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add('over'); }));
  ['dragleave', 'drop'].forEach((ev) => drop.addEventListener(ev, () => drop.classList.remove('over')));
  drop.addEventListener('drop', (e) => { e.preventDefault(); if (e.dataTransfer.files[0]) load(e.dataTransfer.files[0]); });
  // Evita que soltar un archivo fuera de la zona lo abra en el navegador
  window.addEventListener('dragover', (e) => e.preventDefault());
  window.addEventListener('drop', (e) => e.preventDefault());
  input.addEventListener('change', () => { if (input.files[0]) load(input.files[0]); input.value = ''; });
  $('#btn-paste').addEventListener('click', () => {
    const t = $('#paste').value;
    if (!t.trim()) return showError('Pegue algún texto primero.');
    start(F.textDocument(t));
  });

  function showError(msg) { const el = $('#error'); el.textContent = msg; el.hidden = !msg; }
  function busy(on, text) { $('#busy').hidden = !on; if (text) $('#busy-text').textContent = text; }

  async function load(file) {
    showError('');
    busy(true, `Leyendo «${file.name}»…`);
    try {
      const doc = await F.loadDocument(file);
      start(doc);
    } catch (err) {
      console.error(err);
      showError(err.message || String(err));
      $('#step-review').hidden = true;
    } finally { busy(false); }
  }

  function start(doc) {
    state.doc = doc;
    state.overrides.clear();
    state.manual = [];
    showError('');
    $('#file-info').textContent = `${doc.name} · ${doc.label}`;
    $('#warnings').innerHTML = doc.warnings.map((w) => `<div class="alert warn">${esc(w)}</div>`).join('');
    $('#step-review').hidden = false;
    analyze();
    $('#step-review').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function analyze() {
    const list = A.analyze(state.doc.text, options());
    for (const e of list) {
      const o = state.overrides.get(keyOf(e));
      if (o) { if (o.enabled !== undefined) e.enabled = o.enabled; if (o.replacement !== undefined) e.replacement = o.replacement; }
    }
    state.entities = list;
    renderPreview();
    renderList();
  }

  // ------------------------------------------------------------ lista
  function renderList() {
    const q = $('#filter').value.trim().toLowerCase();
    const box = $('#entities');
    const groups = new Map();
    for (const e of state.entities) {
      if (q && !e.text.toLowerCase().includes(q) && !e.replacement.toLowerCase().includes(q)) continue;
      // Partes de nombres que solo aparecen dentro del nombre completo: no aportan nada en la lista.
      if (e.meta && e.meta.part && !e.count) continue;
      if (!groups.has(e.type)) groups.set(e.type, []);
      groups.get(e.type).push(e);
    }
    if (!groups.size) {
      box.innerHTML = `<div class="empty">${state.entities.length ? 'Ningún dato coincide con el filtro.' : 'No se han detectado datos personales. Puede añadirlos manualmente seleccionando texto en la vista previa.'}</div>`;
      return;
    }
    let html = '';
    const order = A.CATEGORIES.map((c) => c.id);
    for (const type of [...groups.keys()].sort((a, b) => order.indexOf(a) - order.indexOf(b))) {
      const items = groups.get(type);
      html += `<div class="group-h"><span>${esc(A.CAT_LABEL[type] || type)}</span><span>${items.length}</span></div>`;
      for (const e of items) {
        html += `<div class="ent ${e.enabled ? '' : 'off'}" data-id="${e.id}">
          <input type="checkbox" ${e.enabled ? 'checked' : ''} aria-label="Sustituir ${esc(e.text)}">
          <div class="orig" title="Ver en el documento">${esc(e.text)}<span class="cnt">×${e.count || 0}</span></div>
          <input class="rep" value="${esc(e.replacement)}" aria-label="Sustituto de ${esc(e.text)}">
          ${e.type === 'manual' ? '<button class="del" type="button">quitar</button>' : ''}
        </div>`;
      }
    }
    box.innerHTML = html;
  }
  $('#filter').addEventListener('input', renderList);
  const entById = (id) => state.entities.find((e) => e.id === id);
  $('#entities').addEventListener('change', (ev) => {
    const row = ev.target.closest('.ent');
    if (!row) return;
    const e = entById(row.dataset.id);
    if (ev.target.type === 'checkbox') {
      e.enabled = ev.target.checked;
      row.classList.toggle('off', !e.enabled);
      setOverride(e, { enabled: e.enabled });
      renderPreview();
    }
  });
  $('#entities').addEventListener('input', (ev) => {
    if (!ev.target.classList.contains('rep')) return;
    const e = entById(ev.target.closest('.ent').dataset.id);
    e.replacement = ev.target.value;
    setOverride(e, { replacement: e.replacement });
    if (state.view === 'anon') schedulePreview();
  });
  $('#entities').addEventListener('click', (ev) => {
    const row = ev.target.closest('.ent');
    if (!row) return;
    if (ev.target.classList.contains('del')) {
      const e = entById(row.dataset.id);
      state.manual = state.manual.filter((m) => m.text !== e.text);
      analyze();
      return;
    }
    if (ev.target.closest('.orig')) {
      const m = $(`#preview mark[data-id="${row.dataset.id}"]`);
      if (m) { m.scrollIntoView({ block: 'center', behavior: 'smooth' }); m.animate([{ outline: '3px solid var(--accent)' }, { outline: '3px solid transparent' }], { duration: 1400 }); }
    }
  });
  function setOverride(e, patch) { state.overrides.set(keyOf(e), Object.assign(state.overrides.get(keyOf(e)) || {}, patch)); }
  $('#btn-all').addEventListener('click', () => bulk(true));
  $('#btn-none').addEventListener('click', () => bulk(false));
  function bulk(on) {
    const q = $('#filter').value.trim().toLowerCase();
    for (const e of state.entities) {
      if (q && !e.text.toLowerCase().includes(q) && !e.replacement.toLowerCase().includes(q)) continue;
      e.enabled = on; setOverride(e, { enabled: on });
    }
    renderList(); renderPreview();
  }
  $('#add-form').addEventListener('submit', (ev) => {
    ev.preventDefault();
    const t = $('#add-text').value.trim();
    if (t) { addManual(t); $('#add-text').value = ''; }
  });
  function addManual(text) {
    text = text.trim().replace(/\s+/g, ' ');
    if (!text || text.length < 2) return;
    if (!state.manual.some((m) => m.text === text)) state.manual.push({ text, type: 'manual' });
    analyze();
    const e = state.entities.find((x) => x.type === 'manual' && x.text === text);
    if (e) {
      const row = $(`.ent[data-id="${e.id}"]`);
      if (row) { row.scrollIntoView({ block: 'nearest' }); row.classList.add('flash'); row.querySelector('.rep').focus(); row.querySelector('.rep').select(); }
    }
  }

  // ------------------------------------------------------------ vista previa
  $$('.seg-btn').forEach((b) => b.addEventListener('click', () => {
    state.view = b.dataset.view;
    $$('.seg-btn').forEach((x) => x.classList.toggle('active', x === b));
    renderPreview();
  }));
  let pvTimer;
  function schedulePreview() { clearTimeout(pvTimer); pvTimer = setTimeout(renderPreview, 250); }

  function renderPreview() {
    const text = state.doc.text;
    const all = state.entities.map((e) => ({ ...e, enabled: true, _real: e }));
    const ms = A.findMatches(text, all);
    const anon = state.view === 'anon';
    let html = '', last = 0, n = 0;
    const counts = new Map();
    for (const m of ms) {
      const e = m.entity._real;
      counts.set(e.id, (counts.get(e.id) || 0) + 1);
      html += esc(text.slice(last, m.start));
      const shown = anon && e.enabled ? A.adaptCase(m.match, e.replacement) : m.match;
      const title = e.enabled ? `${A.CAT_LABEL[e.type] || e.type}: ${m.match} → ${A.adaptCase(m.match, e.replacement)}` : `${m.match} (no se sustituirá)`;
      html += `<mark data-id="${e.id}" class="${e.enabled ? '' : 'off'}" title="${esc(title)}">${esc(shown)}</mark>`;
      last = m.end;
      if (e.enabled) n++;
    }
    html += esc(text.slice(last));
    const pv = $('#preview');
    pv.classList.toggle('anon', anon);
    pv.innerHTML = html || '<span class="muted">(El documento no contiene texto.)</span>';
    for (const e of state.entities) e.count = counts.get(e.id) || 0;
    $$('.ent').forEach((row) => { const e = entById(row.dataset.id); const c = row.querySelector('.cnt'); if (e && c) c.textContent = '×' + e.count; });
    $('#stats').textContent = `${n} sustitucion${n === 1 ? '' : 'es'} · ${state.entities.filter((e) => e.enabled).length} datos distintos`;
  }

  $('#preview').addEventListener('click', (ev) => {
    const m = ev.target.closest('mark');
    if (!m || String(getSelection()).trim()) return;
    const row = $(`.ent[data-id="${m.dataset.id}"]`);
    if (!row) { $('#filter').value = ''; renderList(); }
    const r = $(`.ent[data-id="${m.dataset.id}"]`);
    if (r) { r.scrollIntoView({ block: 'center', behavior: 'smooth' }); r.classList.remove('flash'); void r.offsetWidth; r.classList.add('flash'); }
  });

  // Añadir selección
  const selBtn = $('#sel-add');
  let selText = '';
  document.addEventListener('selectionchange', () => {
    const sel = getSelection();
    const t = String(sel).trim();
    if (!t || t.length < 2 || t.length > 120 || !sel.rangeCount || !$('#preview').contains(sel.anchorNode)) { selBtn.hidden = true; return; }
    selText = t;
    const r = sel.getRangeAt(0).getBoundingClientRect();
    selBtn.querySelector('span').textContent = t.length > 40 ? t.slice(0, 40) + '…' : t;
    selBtn.hidden = false;
    selBtn.style.top = Math.max(8, r.top - 38) + 'px';
    selBtn.style.left = Math.min(window.innerWidth - selBtn.offsetWidth - 8, Math.max(8, r.left)) + 'px';
  });
  selBtn.addEventListener('mousedown', (e) => e.preventDefault());
  selBtn.addEventListener('click', () => { selBtn.hidden = true; getSelection().removeAllRanges(); addManual(selText); });
  window.addEventListener('scroll', () => { selBtn.hidden = true; }, { passive: true });
  $('#preview').addEventListener('scroll', () => { selBtn.hidden = true; }, { passive: true });

  // ------------------------------------------------------------ descargas
  function save(blob, name) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  }
  const baseName = () => state.doc.name.replace(/\.[^.]+$/, '');

  $('#btn-download').addEventListener('click', async () => {
    const btn = $('#btn-download');
    btn.disabled = true;
    busy(true, 'Generando el documento anonimizado…');
    try {
      const active = state.entities.filter((e) => e.enabled && e.replacement !== e.text);
      const { blob, ext } = await state.doc.build(active, { metadata: $('#opt-meta').checked, images: $('#opt-images').checked });
      save(blob, `${baseName()}_ANONIMIZADO.${ext}`);
    } catch (err) {
      console.error(err);
      showError('No se pudo generar el documento: ' + (err.message || err));
    } finally { btn.disabled = false; busy(false); }
  });

  $('#btn-map').addEventListener('click', () => {
    const q = (s) => '"' + String(s).replace(/"/g, '""') + '"';
    const rows = [['Tipo', 'Dato original', 'Sustituto ficticio', 'Apariciones', 'Sustituido']];
    for (const e of state.entities) rows.push([A.CAT_LABEL[e.type] || e.type, e.text, e.replacement, e.count || 0, e.enabled ? 'Sí' : 'No']);
    const csv = '﻿' + rows.map((r) => r.map(q).join(';')).join('\r\n');
    save(new Blob([csv], { type: 'text/csv;charset=utf-8' }), `${baseName()}_CORRESPONDENCIAS_CONFIDENCIAL.csv`);
  });

  $('#btn-reset').addEventListener('click', () => {
    state.doc = null; state.entities = [];
    $('#step-review').hidden = true;
    $('#preview').innerHTML = ''; $('#entities').innerHTML = '';
    $('#paste').value = '';
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
})();
