/* Overhead: the shared page for the four widgets. Each widget's client.js imports this and
   names its page. The server hands over the aircraft with their pictures as data URIs, so
   nothing is fetched here; the page is markup and CSS alone. */

import { buildSheet } from './sheet.js';

const PAPER = { cream: '#f3ead6', white: '#ffffff', aged: '#e9dcc0', blueprint: '#1d3f73', sky: 'linear-gradient(180deg,#dfe9f0 0%,#f2efe6 70%,#efe6d4 100%)' };
const INK = { cream: '#2a2116', white: '#111111', aged: '#2a2116', blueprint: '#eaf0f8', sky: '#22303a' };
const SIL = {
  jet: 'M100 6 C107 6 109 22 109 44 L109 152 C109 172 106 186 100 194 C94 186 91 172 91 152 L91 44 C91 22 93 6 100 6 Z M109 78 L194 130 L194 141 L109 112 Z M91 78 L6 130 L6 141 L91 112 Z M106 166 L142 186 L142 192 L106 182 Z M94 166 L58 186 L58 192 L94 182 Z',
  wide: 'M100 4 C109 4 112 22 112 46 L112 154 C112 174 108 188 100 196 C92 188 88 174 88 154 L88 46 C88 22 91 4 100 4 Z M112 70 L198 136 L198 150 L112 112 Z M88 70 L2 136 L2 150 L88 112 Z M108 164 L150 188 L150 195 L108 184 Z M92 164 L50 188 L50 195 L92 184 Z',
  prop: 'M100 10 C106 10 108 24 108 44 L108 150 C108 168 105 182 100 190 C95 182 92 168 92 150 L92 44 C92 24 94 10 100 10 Z M108 82 L196 84 L196 96 L108 100 Z M92 82 L4 84 L4 96 L92 100 Z M106 168 L144 170 L144 178 L106 180 Z M94 168 L56 170 L56 178 L94 180 Z',
  light: 'M100 28 C106 28 108 40 108 56 L108 140 C108 158 104 170 100 176 C96 170 92 158 92 140 L92 56 C92 40 94 28 100 28 Z M108 66 L194 66 L194 78 L108 80 Z M92 66 L6 66 L6 78 L92 80 Z M104 158 L136 160 L136 167 L104 168 Z M96 158 L64 160 L64 167 L96 168 Z',
  biz: 'M100 10 C105 10 107 24 107 44 L107 154 C107 172 104 186 100 192 C96 186 93 172 93 154 L93 44 C93 24 95 10 100 10 Z M107 86 L186 126 L186 135 L107 110 Z M93 86 L14 126 L14 135 L93 110 Z M104 170 L134 184 L134 190 L104 184 Z M96 170 L66 184 L66 190 L96 184 Z',
  ufo: 'M100 60 a34 18 0 1 0 0.1 0 Z M20 112 a80 22 0 1 0 160 0 a80 22 0 1 0 -160 0 Z M52 140 h14 v6 h-14 Z M93 146 h14 v6 h-14 Z M134 140 h14 v6 h-14 Z',
  heli: 'M84 96 a16 38 0 1 0 32 0 a16 38 0 1 0 -32 0 Z M97 128 h6 v58 h-6 Z M86 180 h28 v4 h-28 Z M98 18 h4 v74 h-4 Z M100 90 h72 v4 h-72 Z M28 90 h72 v4 h-72 Z M98 92 h4 v74 h-4 Z',
};

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

async function predecode(src) {
  if (!src || typeof Image === 'undefined') return;
  try { const img = new Image(); img.src = src; await Promise.race([img.decode(), new Promise((r) => setTimeout(r, 6000))]); } catch { /* shown as it is */ }
}

function sil(cls) {
  return `<svg class="oh-sil" viewBox="0 0 200 200" fill="currentColor" aria-hidden="true"><path d="${SIL[cls] || SIL.jet}"/></svg>`;
}

function logo(a, cls = '') {
  if (a.logo) return `<img class="oh-logo ${cls}" src="${a.logo}" alt="${esc(a.air)}" decoding="sync">`;
  return a.air && a.air !== 'private' ? `<span class="oh-airname ${cls}">${esc(a.air)}</span>` : '';
}

function head(d, where = 'top') {
  if (d.header === 'hidden' || (d.header === 'bottom') !== (where === 'bottom')) return '';
  const bits = [d.title, d.area, d.period].filter(Boolean).map(esc).join(' · ');
  const line = `<div class="ph"><span class="ph-k">${bits}</span><b class="ph-d">${esc(d.time)} · ${esc(d.date)}</b></div>`;
  return where === 'bottom' ? `<div class="ph-rule"></div>${line}` : `${line}<div class="ph-rule"></div>`;
}

function foot(d, extra = []) {
  const mode = d.footer || 'show';
  if (mode === 'hide') return '';
  const bits = [...(mode === 'credits' ? [] : [...(d.notices || []), ...(d.status || []), ...extra]), ...(d.credits || []), d.attribution].filter(Boolean);
  return bits.length ? `<div class="credit">${bits.map(esc).join(' · ')}</div>` : '';
}

function message(d, title, body, hint) {
  // an empty sky may carry the unidentified contact alone: the one thing on the page, over the words
  const contact = d.ufo && d.ufo.pic ? `<figure class="ufo ufo-alone"><img src="${d.ufo.pic.src}" alt="" decoding="sync"><figcaption>${esc(d.ufo.typ)}${(d.ufo.lines || []).slice(1, 3).map((l) => ` · ${esc(l)}`).join('')}</figcaption></figure>` : '';
  return `${head(d)}<div class="msg${contact ? ' msg-contact' : ''}">${contact}<div class="msg-t">${esc(title)}</div><div class="msg-b">${esc(body)}</div>${hint ? `<div class="msg-h">${esc(hint)}</div>` : ''}</div>${foot(d)}`;
}

function lines(a) {
  return (a.lines || []).map((t, i) => `<span class="ln${i === 0 ? ' ln-first' : ''}">${esc(t)}</span>`).join('');
}

const SIL_URL = (cls) => 'data:image/svg+xml;utf8,' + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="400" height="400" fill="#7a7a7a"><path d="${SIL[cls] || SIL.jet}"/></svg>`);

function picture(a, cls = '') {
  if (a.pic && a.pic.src) return `<img class="oh-pic ${cls}${a.pic.whole ? ' whole' : ' cut'}" src="${a.pic.src}" alt="${esc(a.typ)}" decoding="sync">`;
  return `<span class="oh-pic oh-nopic ${cls}">${sil(a.cls)}</span>`;
}

/* The full-bleed photograph: the nearest aircraft fills the page, the rest along a strip. */
function photoPage(d) {
  const hero = d.aircraft[0];
  const rest = d.aircraft.slice(1);
  const bg = hero.pic && hero.pic.src ? `<div class="fb-bg" style="background-image:url('${hero.pic.src}');background-size:${d.photo_fit || 'cover'}"></div>` : `<div class="fb-bg fb-none">${sil(hero.cls)}</div>`;
  const strip = rest.length ? `<ul class="fb-strip">${rest.map((a) => `<li>${a.pic && a.pic.src ? `<span class="fb-th" style="background-image:url('${a.pic.src}')"></span>` : `<span class="fb-th fb-th-none">${sil(a.cls)}</span>`}<span class="fb-th-t"><b>${esc(a.cs)}</b><span>${esc(a.typ)}</span><span>${esc(a.alt_text)} · ${esc(a.where)}</span></span></li>`).join('')}</ul>` : '';
  const top = d.header === 'hidden' ? '' : `<div class="fb-top"><span>${esc(d.title)} · ${esc(d.area)}</span><span>${esc(d.time)} · ${esc(d.date)}</span></div>`;
  return `${bg}<div class="fb-shade"></div>${top}<div class="fb-main">${logo(hero, 'fb-logo')}<div class="fb-cs">${esc(hero.cs)}</div><div class="fb-typ">${esc(hero.typ)}${hero.reg ? ` <span>· ${esc(hero.reg)}</span>` : ''}</div><div class="fb-r">${lines(hero).replace(/<\/span><span/g, '</span> · <span')}</div></div>${strip}${foot(d).replace('class="credit"', 'class="credit fb-credit"')}`;
}

/* The modern looks for one aircraft: boarding pass, tiles, poster and split, in the airline's colours. */
const DIRS = { N: 'north', NE: 'north-east', E: 'east', SE: 'south-east', S: 'south', SW: 'south-west', W: 'west', NW: 'north-west' };

function palette(d, a) {
  const b = d.colours === 'airline' && a.brand && a.brand.primary ? a.brand : null;
  if (b) return { p: b.primary, s: b.secondary, t: b.tint, sh: b.shade, th: b.third || b.secondary, ink: b.ink, ink2: b.ink2 || '#fff' };
  return { p: '#24333b', s: '#55666f', t: '#e9ecee', sh: '#101a1f', th: '#8a9aa3', ink: '#fff', ink2: '#fff' };
}

function statRows(a) {
  return [
    ['Height', a.ground ? '0 ft' : `${a.alt.toLocaleString()} ft`, a.ground ? 'on the ground' : `${a.trend}${a.rate ? `, ${Math.abs(a.rate).toLocaleString()} ft/min` : ''}`],
    ['Speed', a.gs ? `${a.gs} kt` : '', 'over the ground'],
    ['Distance', `${a.km} km`, `to the ${DIRS[a.compass] || a.compass || ''}`],
    ['Heading', `${String(a.trk).padStart(3, '0')}°`, a.ground ? 'on the ground' : a.trend],
  ].filter((r) => r[1]);
}

function stat([label, value, sub], cls = '') {
  return `<div class="md-st ${cls}"><small>${esc(label)}</small><b>${esc(value)}</b>${sub ? `<em>${esc(sub)}</em>` : ''}</div>`;
}

function routeBlock(a) {
  const ro = a.route || {};
  if (ro.origin && ro.dest) return `<div class="md-rt"><b>${esc(ro.origin)}<small>${esc(ro.origin_city || '')}</small></b><i></i><b>${esc(ro.dest)}<small>${esc(ro.dest_city || '')}</small></b></div>`;
  return `<div class="md-rt md-rt-text"><b>${esc(a.route_text)}</b></div>`;
}

function modPic(a, cls = '') {
  if (!a.pic || !a.pic.src) return `<div class="md-pic md-none ${cls}">${sil(a.cls)}</div>`;
  return `<div class="md-pic ${cls}${a.pic.whole ? ' whole' : ' cut'}" style="background-image:url('${a.pic.src}')"></div>`;
}

function modernPage(d) {
  const a = d.aircraft[0];
  const c = palette(d, a);
  const portrait = (d.cell_h || 1) > (d.cell_w || 1);
  const vars = `--p:${c.p};--s:${c.s};--t:${c.t};--sh:${c.sh};--th:${c.th};--pink:${c.ink};--sink:${c.ink2}`;
  const top = d.header === 'hidden' ? '' : `${esc(d.title)} · ${esc(d.time)}`;
  const when = `${esc(d.time)} · ${esc(d.date)}`;
  const credit = `${esc(a.typ)}${a.reg ? ` · ${esc(a.reg)}` : ''}${a.pic && a.pic.credit && d.footer !== 'hide' ? ` · ${esc(a.pic.credit)}` : ''}`;
  const typ = `${esc(a.typ)}${a.reg ? ` · <span class="nb">${esc(a.reg)}</span>` : ''}${a.air && a.air !== 'private' ? ` · ${esc(a.air)}` : ''}`;
  const st = statRows(a);
  const contact = d.ufo && d.ufo.pic ? `<figure class="ufo md-ufo"><img src="${d.ufo.pic.src}" alt="" decoding="sync"><figcaption>${esc(d.ufo.typ)} · ${esc(d.ufo.lines[1])}</figcaption></figure>` : '';
  const notes = d.footer === 'hide' ? [] : [...(d.notices || []), ...(d.status || [])];
  const note = notes.length ? `<div class="md-note">${notes.map(esc).join(' · ')}</div>` : '';
  let body;
  if (d.look === 'pass') {
    body = `<div class="md-ph">${modPic(a)}${top ? `<div class="md-top">${top}</div>` : ''}<div class="md-cap">${credit}</div>${contact}</div>
      <div class="md-side">${logo(a)}<div class="md-cs">${esc(a.cs)}</div><div class="md-typ">${esc(a.typ)}${a.reg ? ` · <span class="nb">${esc(a.reg)}</span>` : ''}</div>${routeBlock(a)}<div class="md-chips">${st.map((r, i) => stat(r, i === 0 ? 'on-s' : 'on-t')).join('')}</div></div>`;
  } else if (d.look === 'tiles') {
    const tone = ['on-p', 'on-s', 'on-th', 'on-sh'];
    body = `<div class="md-bar">${logo(a)}<div class="md-bar-t"><div class="md-cs">${esc(a.cs)}</div><div class="md-typ">${typ}</div></div><div class="md-when">${top ? `${esc(d.title)}<br>` : ''}${when}</div></div>
      <div class="md-grid">${modPic(a, 'md-card')}<div class="md-tiles">${routeBlock(a)}${st.map((r, i) => stat(r, tone[i])).join('')}</div>${contact}</div>${note}`;
  } else if (d.look === 'poster') {
    body = `${modPic(a, 'md-bg')}<div class="md-shade"></div><div class="md-top md-top-row"><span>${top || when}</span>${logo(a)}</div>${contact}
      <div class="md-main"><div class="md-cs">${esc(a.cs)}</div><div class="md-typ">${typ}</div><div class="md-row">${routeBlock(a)}<div class="md-stats">${st.slice(0, 3).map((r) => stat(r, 'glass')).join('')}</div></div></div>${note}`;
  } else {
    body = `<div class="md-frame-wrap">${modPic(a, 'md-frame')}<span class="md-pill">${esc(a.ground ? 'on the ground' : a.trend)}</span>${contact}</div>
      <div class="md-r"><div class="md-hd"><span>${top || when}</span>${logo(a)}</div><div class="md-cs">${esc(a.cs)}</div><div class="md-typ">${typ}</div>${routeBlock(a)}<div class="md-stats4">${st.map((r, i) => stat(r, i === 0 ? 'on-s' : i === 1 ? 'on-th' : 'dim')).join('')}</div>${note}</div>`;
  }
  return `<div class="md md-${esc(d.look)}${portrait ? ' portrait' : ''}" style="${vars}">${body}</div>`;
}

/* The plate: one aircraft, large, in a ruled frame, with its particulars beside it. */
function platePage(d) {
  const a = d.aircraft[0];
  const ro = a.route || {};
  const brand = d.colours === 'airline' && a.brand && a.brand.primary ? a.brand : null;
  const rows = [
    ['Route', a.route_text],
    ['Height', a.ground ? 'on the ground' : `${a.alt.toLocaleString()} ft, ${a.trend}${a.rate ? ` at ${Math.abs(a.rate).toLocaleString()} ft/min` : ''}`],
    ['Where', `${a.where}, heading ${String(a.trk).padStart(3, '0')}°`],
    ['Speed', a.gs ? `${a.gs} kt over the ground` : ''],
  ].filter((r) => r[1]);
  const portrait = (d.cell_h || 1) > (d.cell_w || 1);
  const contact = d.ufo && d.ufo.pic ? `<figure class="ufo"><img src="${d.ufo.pic.src}" alt="" decoding="sync"><figcaption>${esc(d.ufo.typ)} · ${esc(d.ufo.lines[1])} · ${esc(d.ufo.lines[2])}</figcaption></figure>` : '';
  return `${head(d)}<div class="pl${portrait ? ' portrait' : ''}${brand ? ' brand' : ''}"${brand ? ` style="--brand:${brand.primary};--brand2:${brand.secondary};--on-brand:${brand.ink}"` : ''}><div class="pl-plate"><div class="pl-frame"><i class="tl"></i><i class="tr"></i><i class="bl"></i><i class="br"></i></div>${contact}${picture(a, 'pl-pic')}<div class="pl-fig">Fig. 1. ${esc(a.typ)}${a.reg ? `, ${esc(a.reg)}` : ''}${a.pic && a.pic.credit ? `, ${esc(a.pic.credit)}` : ''}</div></div><div class="pl-note">${logo(a, brand ? 'pl-logo chip' : 'pl-logo mono')}<div class="pl-cs">${esc(a.cs)}</div><div class="pl-typ">${esc(a.typ)}${a.reg ? ` <i>· ${esc(a.reg)}</i>` : ''}</div><dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join('')}</dl><p class="pl-about">${esc(a.about)}</p></div></div>${head(d, 'bottom')}${foot(d)}`;
}

/* The cluster: every aircraft painted and cut out, sized by its wingspan, in rows; or, with
   photographs, a spotter's log of cards. */
function clusterPage(d) {
  const n = d.aircraft.length;
  if (d.pictures === 'photos') {
    const cols = n <= 2 ? n : n <= 4 ? 2 : n <= 6 ? 3 : 4;
    return `${head(d)}<div class="lg-grid" style="--cols:${cols}">${d.aircraft.map((a) => `<article class="lg-card">${a.pic && a.pic.src ? `<div class="lg-pic" style="background-image:url('${a.pic.src}')"></div>` : `<div class="lg-pic lg-none">${sil(a.cls)}</div>`}<div class="lg-row">${logo(a, 'lg-logo')}<b>${esc(a.cs)}</b></div><div class="lg-lines">${lines(a)}</div></article>`).join('')}</div>${head(d, 'bottom')}${foot(d)}`;
  }
  const W0 = d.cell_w || 800, H0 = d.cell_h || 480;
  return `${head(d)}<div class="sh" data-packed></div>${head(d, 'bottom')}${foot(d)}`;
}

/* ---- building the sheet without holding the page ----
   The packer runs in one module worker (OffscreenCanvas) so the page, and an editor showing it,
   stay responsive while the sheet is built; the page builds the sheet itself where workers are
   missing or one fails. A sheet is kept by a key of everything that decides it, so a page drawn
   again from the same data (an editor's refresh while paintings are on the way) is not packed
   again. */
const WORKER_PATH = './sheet.js';
let WORKER = null;
let CHAIN = Promise.resolve();
function packOffThread(args) {
  if (typeof Worker === 'undefined' || typeof OffscreenCanvas === 'undefined') return buildSheet(args);
  const run = () => new Promise((resolve) => {
    try { if (!WORKER) WORKER = new Worker(new URL(WORKER_PATH, import.meta.url), { type: 'module' }); } catch { resolve(buildSheet(args)); return; }
    const w = WORKER;
    let done = false;
    const finish = (sheet) => { if (done) return; done = true; clearTimeout(timer); w.onmessage = null; w.onerror = null; resolve(sheet); };
    const drop = () => { if (WORKER === w) WORKER = null; try { w.terminate(); } catch { /* gone */ } };
    const timer = setTimeout(() => { drop(); finish(buildSheet(args)); }, 60000);
    w.onmessage = (e) => { if (e.data && e.data.kind === 'cut') return; finish(e.data && e.data.ok ? e.data.sheet : buildSheet(args)); };
    w.onerror = () => { drop(); finish(buildSheet(args)); };
    w.postMessage(args);
  });
  CHAIN = CHAIN.then(run, run);
  return CHAIN;
}
const fnv = (s) => { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0).toString(36); };
function keyOf(a) {
  const parts = a.specimens.map((x) => `${x.name}|${x.sci}|${x.src ? x.src.length : 0}|${x.whole ? 1 : 0}|${x.factor}|${x.aspect}|${x.cap || 0}|${(x.lines || []).join('/')}`);
  return `oh1:${a.ratio.toFixed(4)}:${a.size}:${a.label.toFixed(4)}:${a.paper}:${a.packer}:${a.zoom}:${a.budget}:${fnv(parts.join(';'))}`;
}
const SHEETS = new Map();
const SHEETS_MAX = 8;

/* A silhouette as a PNG, drawn once per kind: a worker cannot decode the SVG itself. */
const SIL_PNG = new Map();
async function silPng(cls) {
  const k = SIL[cls] ? cls : 'jet';
  if (SIL_PNG.has(k)) return SIL_PNG.get(k);
  let out = SIL_URL(k);
  try {
    const img = new Image();
    img.src = SIL_URL(k);
    await img.decode();
    const cv = document.createElement('canvas');
    cv.width = 400; cv.height = 400;
    cv.getContext('2d').drawImage(img, 0, 0, 400, 400);
    out = cv.toDataURL('image/png');
  } catch { /* the SVG as it is */ }
  SIL_PNG.set(k, out);
  return out;
}

/* The cluster packed: every cut-out's footprint laid on a lattice from the middle out, each as
   large as the page allows (the Specimen Sheet's packer). Returns the sheet, or null. */
async function packCluster(d) {
  const w = d.cell_w || 800, h = d.cell_h || 480;
  const specimens = await Promise.all(d.aircraft.map(async (a) => {
    const pic = a.pic || {};
    const src = pic.src || await silPng(a.cls);
    const whole = !!pic.src && !!pic.whole;
    return {
      name: a.cs, sci: a.reg || a.cs, src, cut: whole ? null : src, on_paper: false, classic: false, whole, neutral: false, no_flip: true,
      factor: Math.pow((a.span || 20) / 35, 0.45), aspect: pic.aspect > 0 ? pic.aspect : 3, paper: null,
      cap: a.ufo ? 1.5 : 0,  // the contact stays small beside the aircraft, however much paper is free
      lines: [a.cs, ...(a.lines || [])],
    };
  }));
  const label = Math.max(0.017, 13 / h) * ((Number(d.text_size) || 100) / 100);
  const zoom = Math.max(0.4, Math.min(1, (Number(d.scale) || 100) / 100));
  const packer = ['spiral', 'voids'].includes(d.packing) ? d.packing : 'balanced';
  // while pictures are still on the way the page is drawn again soon: a quicker arrangement
  const budget = Number(d.live_refresh_s) > 0 ? 1500 : 4000;
  const args = { specimens, ratio: w / h, size: 1400, label, paper: d.paper === 'white' ? 'white' : d.paper === 'aged' ? 'aged' : 'cream', ink: INK[d.paper] || INK.cream, layout: 'cluster', packer, facing: 'inward', zoom, budget };
  const key = keyOf(args);
  if (SHEETS.has(key)) return SHEETS.get(key);
  try {
    const made = await packOffThread(args);
    if (made && made.src) {
      SHEETS.set(key, made);
      while (SHEETS.size > SHEETS_MAX) SHEETS.delete(SHEETS.keys().next().value);
    }
    return made;
  } catch (e) { console.warn('overhead: packing failed', e); return null; }
}

/* A caption line as the packer wrapped it: its breaks kept, so the line is as wide as was measured. */
const br = (t) => esc(t).replace(/\n/g, '<br>');

function packedPage(d, made) {
  const byName = Object.fromEntries(d.aircraft.map((a) => [a.cs, a]));
  const tags = made.items.map((m) => {
    const lines = m.lines || [];
    if (!lines.length) return '';
    const a = byName[m.name] || {};
    const first = `${a.logo ? `<img class="sh-logo" src="${a.logo}" alt="">` : ''}${br(lines[0])}`;
    return `<span class="sh-l" style="left:${(m.at[0] * 100).toFixed(2)}%;top:${(m.at[1] * 100).toFixed(2)}%"><span class="sh-ln sh-name">${first}</span>${lines.slice(1).map((t) => `<span class="sh-ln sh-sm">${br(t)}</span>`).join('')}</span>`;
  }).join('');
  const page = `<div class="sh-page" style="--r:${made.ratio};--lf:${made.label}"><img src="${made.src}" alt="" decoding="sync">${tags}</div>`;
  return `${head(d)}<div class="sh">${page}</div>${head(d, 'bottom')}${foot(d)}`;
}

/* Where the scene's captions sit, as shares of the page: the top line, the particulars, the credit. */
const SC_BOXES = { top: [0, 0, 1, 0.1], main: [0.4, 0.5, 1, 0.94], credit: [0, 0.92, 0.5, 1] };

/* Which of the scene's captions sit on a dark part of the painting: the picture drawn small as the
   page draws it (cover, or contain on the paper), then the light of each caption's box. */
async function darkBehind(src, fit, ratio, paper) {
  if (!src || typeof document === 'undefined' || typeof Image === 'undefined') return null;
  try {
    const img = new Image();
    img.src = src;
    await img.decode();
    const W = 160, H = Math.max(1, Math.round(W / (ratio || 1.5)));
    const cv = document.createElement('canvas');
    cv.width = W; cv.height = H;
    const g = cv.getContext('2d', { willReadFrequently: true });
    g.fillStyle = paper; g.fillRect(0, 0, W, H);
    const k = (fit === 'contain' ? Math.min : Math.max)(W / img.naturalWidth, H / img.naturalHeight);
    const dw = img.naturalWidth * k, dh = img.naturalHeight * k;
    g.drawImage(img, (W - dw) / 2, (H - dh) / 2, dw, dh);
    const out = {};
    for (const [name, [x0, y0, x1, y1]] of Object.entries(SC_BOXES)) {
      const x = Math.floor(x0 * W), y = Math.floor(y0 * H);
      const px = g.getImageData(x, y, Math.max(1, Math.ceil(x1 * W) - x), Math.max(1, Math.ceil(y1 * H) - y)).data;
      let sum = 0;
      for (let i = 0; i < px.length; i += 4) sum += 0.2126 * px[i] + 0.7152 * px[i + 1] + 0.0722 * px[i + 2];
      out[name] = sum / (px.length / 4) < 118;
    }
    return out;
  } catch { return null; }
}

/* The scene: one whole painting across the page, the particulars set over its paper; a caption on a
   dark part of the painting (a night, a storm) is light on a dark halo. */
function scenePage(d) {
  const a = d.aircraft[0];
  const dk = d.sc_dark || {};
  const on = (k) => (dk[k] ? ' on-dark' : '');
  const art = a.pic && a.pic.src ? `<div class="sc-bg" style="background-image:url('${a.pic.src}');background-size:${a.pic.whole ? 'cover' : 'contain'}"></div>` : `<div class="sc-bg sc-none">${sil(a.cls)}</div>`;
  const top = d.header === 'hidden' ? '' : `<div class="sc-top${on('top')}"><span>${esc(d.title)} · ${esc(d.area)}</span><span>${esc(d.time)} · ${esc(d.date)}</span></div>`;
  const contact = d.ufo && d.ufo.pic ? `<figure class="ufo sc-ufo"><img src="${d.ufo.pic.src}" alt="" decoding="sync"><figcaption>${esc(d.ufo.typ)} · ${esc(d.ufo.lines[1])}</figcaption></figure>` : '';
  return `${art}${contact}${top}<div class="sc-main${on('main')}">${logo(a, 'sc-logo')}<div class="sc-cs">${esc(a.cs)}</div><div class="sc-typ">${esc(a.typ)}${a.reg ? ` <span>· ${esc(a.reg)}</span>` : ''}</div><div class="sc-r">${lines(a).replace(/<\/span><span/g, '</span> · <span')}</div></div>${foot(d).replace('class="credit"', `class="credit sc-credit${on('credit')}"`)}`;
}

export async function render(shadow, ctx, widget) {
  const d = ctx.data || {};
  const size = ctx.cell?.size || 'md';
  d.cell_w = ctx.cell?.w; d.cell_h = ctx.cell?.h;
  let body;
  if (!d.widget && !d.error) body = `<div class="msg"><div class="msg-t">Overhead</div><div class="msg-b">No data from the server yet.</div></div>`;
  else if (d.state === 'error' || d.error) body = message(d, d.title || 'Overhead', d.error || 'Something went wrong.', d.hint);
  else if (d.state === 'empty') body = message(d, d.title || 'Overhead', 'Nothing in the air within reach.', d.hint);
  else if (d.state === 'painting') body = message(d, d.title || 'Overhead', 'Nothing painted yet.', d.hint);
  else {
    for (const a of d.aircraft) if (a.pic && a.pic.src) await predecode(a.pic.src);
    if (widget === 'scene' && d.aircraft[0]?.pic?.src) {
      const pic = d.aircraft[0].pic;
      const solid = String(PAPER[d.paper] || PAPER.cream);
      d.sc_dark = await darkBehind(pic.src, pic.whole ? 'cover' : 'contain', (d.cell_w || 3) / (d.cell_h || 2), solid.startsWith('#') ? solid : '#f2efe6');
    }
    if (widget === 'cluster' && d.pictures === 'paintings' && typeof document !== 'undefined') {
      const made = await packCluster(d);
      if (made && made.src) { await predecode(made.src); body = packedPage(d, made); }
      else body = clusterPage(d);
    } else body = widget === 'photo' ? photoPage(d) : widget === 'plate' ? (['pass', 'tiles', 'poster', 'split'].includes(d.look) ? modernPage(d) : platePage(d)) : widget === 'scene' ? scenePage(d) : clusterPage(d);
  }
  const paper = PAPER[d.paper] || PAPER.cream;
  const ink = INK[d.paper] || INK.cream;
  const fonts = {
    fell: "--serif: 'IM Fell English', Georgia, serif; --sc: 'IM Fell English SC', Georgia, serif; --sans: 'Archivo Narrow', Arial, sans-serif;",
    archivo: "--serif: 'Archivo Narrow', Arial, sans-serif; --sc: 'Archivo Narrow', Arial, sans-serif; --sans: 'Archivo Narrow', Arial, sans-serif;",
    georgia: "--serif: Georgia, 'Times New Roman', serif; --sc: Georgia, 'Times New Roman', serif; --sans: Georgia, 'Times New Roman', serif;",
    page: "--serif: inherit; --sc: inherit; --sans: inherit;",
  }[d.font] || '';
  const dark = widget === 'photo' && d.state === 'ok';
  shadow.innerHTML = `
    <style>${d.font_css || ''}</style>
    <div class="oh ${esc(widget)} font-${esc(d.font || 'fell')} paper-${esc(d.paper || 'cream')} size-${esc(size)} lv-${esc(d.panel || 'colour')}${dark ? ' dark' : ''}" style="--paper:${paper};--ink:${ink};--ts:${(Number(d.text_size) || 100) / 100};${fonts}">${body}</div>
    <style>
      :host { display: block; height: 100%; }
      .oh { container-type: size; height: 100%; width: 100%; overflow: hidden; position: relative; display: flex; flex-direction: column; background: var(--paper); color: var(--ink);
        font-family: var(--serif); font-variant-numeric: tabular-nums; }
      .oh.font-page { font-family: inherit; }
      .oh.font-archivo .ph-k, .oh.font-archivo .pl-cs, .oh.font-archivo .pl-note dt, .oh.font-archivo .sh-name, .oh.font-archivo .oh-airname, .oh.font-georgia .ph-k, .oh.font-page .ph-k { text-transform: uppercase; letter-spacing: .1em; }
      /* the unidentified contact on a single page */
      .ufo { position: absolute; right: 7%; top: 9%; width: 8%; margin: 0; display: flex; flex-direction: column; align-items: center; gap: .3cqmin; z-index: 1; }
      .ufo img { width: 100%; mix-blend-mode: multiply; } .sc-ufo img { mix-blend-mode: normal; }
      .ufo figcaption { font-family: var(--sc); font-size: calc(var(--ts) * 1.7cqmin); letter-spacing: .08em; text-align: center; white-space: nowrap; }
      .ufo-alone { position: static; width: 26%; max-height: 46cqh; margin: 0 auto .6cqmin; } .ufo-alone img { max-height: 40cqh; object-fit: contain; } .ufo-alone figcaption { white-space: normal; font-size: calc(var(--ts) * 2.2cqmin); }
      .msg-contact { justify-content: center; gap: .9cqmin; }
      .sc-ufo { right: 6%; top: 12%; width: 7%; } .sc-ufo figcaption { font-family: var(--sans); text-transform: uppercase; color: #fff; text-shadow: 0 1px 3px rgba(0,0,0,.7); }
      /* the packed cluster */
      .sh { flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center; padding: 0 .6cqmin; }
      .sh-page { position: relative; aspect-ratio: var(--r); max-width: 100%; max-height: 100%; width: min(100%, calc((100cqh - 9cqmin) * var(--r))); container-type: size; }
      .sh-page > img { display: block; width: 100%; height: 100%; }
      .sh-l { position: absolute; transform: translate(-50%, 12%); white-space: nowrap; text-align: center; line-height: 1.15; font-family: var(--sc); font-size: calc(var(--lf) * 100cqh); letter-spacing: .04em; color: var(--ink); }
      .sh-ln { display: block; }
      .sh-sm { font-family: var(--serif); font-style: italic; letter-spacing: 0; font-size: .88em; opacity: .85; }
      .sh-logo { height: 1em; vertical-align: -.15em; margin-right: .3em; filter: grayscale(1) contrast(2.2) brightness(.75); mix-blend-mode: multiply; }
      /* a halo in the paper's colour behind every caption that can sit over a picture */
      .sh-l, .cl-sp figcaption, .pl-fig { --halo: var(--paper); text-shadow: .06em 0 0 var(--halo), -.06em 0 0 var(--halo), 0 .06em 0 var(--halo), 0 -.06em 0 var(--halo), .045em .045em 0 var(--halo), -.045em .045em 0 var(--halo), .045em -.045em 0 var(--halo), -.045em -.045em 0 var(--halo), .09em 0 0 var(--halo), -.09em 0 0 var(--halo); }
      .sc-main, .sc-top, .sc-credit { --halo: rgba(255,255,255,.92); text-shadow: .06em 0 0 var(--halo), -.06em 0 0 var(--halo), 0 .06em 0 var(--halo), 0 -.06em 0 var(--halo), .045em .045em 0 var(--halo), -.045em .045em 0 var(--halo), .045em -.045em 0 var(--halo), -.045em -.045em 0 var(--halo); }
      .oh.paper-blueprint .sh-l, .oh.paper-blueprint .cl-sp figcaption { --halo: #1d3f73; }
      .lv-mono .sh-l { -webkit-text-stroke: .3px currentColor; }
      .oh.dark { background: #000; color: #fff; }
      .lv-mono { --ink: #000; }
      .oh.lv-mono .oh-pic.cut, .oh.lv-gray4 .oh-pic.cut { filter: contrast(1.15); }
      .ph { display: flex; justify-content: space-between; align-items: baseline; gap: 2cqmin; padding: 1.2cqmin 2.4cqmin .3cqmin; flex: 0 0 auto; font-size: calc(var(--ts) * 1em); }
      .ph-k { font-family: var(--sc); font-size: 2.4cqmin; letter-spacing: .13em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .ph-d { font-weight: 400; font-size: 3cqmin; letter-spacing: .04em; white-space: nowrap; }
      .ph-rule { border-top: 1px solid var(--ink); position: relative; margin: 0 2.4cqmin .2cqmin; flex: 0 0 auto; }
      .ph-rule::after { content: ""; position: absolute; left: 0; right: 0; top: 2px; border-top: 1px solid var(--ink); }
      .credit { flex: 0 0 auto; font-size: 1.7cqmin; opacity: .7; padding: .3cqmin 2.4cqmin .7cqmin; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-style: italic; }
      .msg { flex: 1; display: flex; flex-direction: column; justify-content: center; gap: 1.4cqmin; padding: 4cqmin 6cqmin; text-align: center; }
      .msg-t { font-family: var(--sc); font-size: 5cqmin; letter-spacing: .06em; } .msg-b { font-size: 3.4cqmin; } .msg-h { font-size: 2.6cqmin; font-style: italic; opacity: .75; }
      .oh-nopic { position: relative; display: block; overflow: hidden; }
      .oh-sil { position: absolute; inset: 0; width: 100%; height: 100%; opacity: .3; }
      .oh-logo { display: block; object-fit: contain; }
      .oh-logo.mono { filter: grayscale(1) contrast(2.2) brightness(.75); mix-blend-mode: multiply; }
      .oh.dark .oh-logo { filter: drop-shadow(0 1px 2px rgba(0,0,0,.6)); }
      .oh-airname { font-family: var(--sc); letter-spacing: .1em; font-size: .8em; }
      .ln { display: block; }
      /* the photograph */
      .fb-bg { position: absolute; inset: 0; background-position: center; background-repeat: no-repeat; background-color: #000; }
      .fb-none { color: #fff; } .fb-none .oh-sil { inset: 15cqmin; width: auto; height: auto; }
      .fb-shade { position: absolute; inset: 0; background: linear-gradient(180deg, rgba(0,0,0,.45) 0, rgba(0,0,0,0) 22%, rgba(0,0,0,0) 48%, rgba(0,0,0,.8) 100%); }
      .fb-top, .fb-main, .fb-strip, .fb-credit { position: absolute; font-family: var(--sans); text-shadow: 0 1px 3px rgba(0,0,0,.6); }
      .fb-top { top: 2.6cqmin; left: 2.6cqmin; right: 2.6cqmin; display: flex; justify-content: space-between; font-size: 2.6cqmin; letter-spacing: .1em; text-transform: uppercase; }
      .fb-main { left: 2.6cqmin; bottom: 3cqmin; max-width: 58%; }
      img.fb-logo { height: 6cqmin; max-width: 30cqmin; margin-bottom: 1cqmin; }
      .fb-cs { font-size: calc(var(--ts) * 12cqmin); font-weight: 700; line-height: .95; }
      .fb-typ { font-size: calc(var(--ts) * 3.8cqmin); font-weight: 600; margin-top: .8cqmin; } .fb-typ span { font-weight: 400; opacity: .85; }
      .fb-r { font-size: calc(var(--ts) * 3cqmin); margin-top: .4cqmin; } .fb-r .ln { display: inline; }
      .fb-strip { right: 2.4cqmin; bottom: 3cqmin; width: 36%; list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 1cqmin; }
      .fb-strip li { display: flex; gap: 1.2cqmin; align-items: center; background: rgba(0,0,0,.42); padding: .7cqmin; border-radius: .5cqmin; }
      .fb-th { width: 10cqmin; height: 6.5cqmin; background-size: cover; background-position: center; border-radius: .3cqmin; flex: none; } .fb-th-none { position: relative; color: #fff; }
      .fb-th-t { display: flex; flex-direction: column; line-height: 1.15; font-size: 2cqmin; min-width: 0; } .fb-th-t b { font-size: 2.6cqmin; } .fb-th-t span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .fb-credit { right: 2.6cqmin; top: 6cqmin; left: auto; max-width: 70%; padding: 0; opacity: .85; font-size: 1.8cqmin; background: none; }
      .oh.photo .size-sm .fb-strip, .oh.photo.size-sm .fb-strip, .oh.photo.size-xs .fb-strip { display: none; }
      /* the plate */
      .pl { flex: 1; min-height: 0; display: grid; grid-template-columns: 62fr 38fr; gap: 2cqmin; padding: 1.5cqmin 2.4cqmin; }
      .pl.portrait { grid-template-columns: 1fr; grid-template-rows: 60fr 40fr; }
      .pl-plate { position: relative; display: flex; align-items: center; justify-content: center; min-height: 0; padding: 4cqmin; }
      .pl-frame { position: absolute; inset: 1cqmin; border: 1.5px solid var(--ink); outline: 1px solid var(--ink); outline-offset: 4px; }
      .pl-frame i { position: absolute; width: 4cqmin; height: 4cqmin; border: 1.5px solid var(--ink); }
      .pl-frame i.tl { left: -1.3cqmin; top: -1.3cqmin; border-right: 0; border-bottom: 0; } .pl-frame i.tr { right: -1.3cqmin; top: -1.3cqmin; border-left: 0; border-bottom: 0; }
      .pl-frame i.bl { left: -1.3cqmin; bottom: -1.3cqmin; border-right: 0; border-top: 0; } .pl-frame i.br { right: -1.3cqmin; bottom: -1.3cqmin; border-left: 0; border-top: 0; }
      .pl-pic { max-width: 92%; max-height: 82%; object-fit: contain; mix-blend-mode: multiply; } .pl-pic.whole { mix-blend-mode: normal; max-height: 90%; }
      .oh-nopic.pl-pic { width: 60%; aspect-ratio: 1; }
      .pl-fig { position: absolute; left: 0; right: 0; bottom: 2.2cqmin; text-align: center; font-size: calc(var(--ts) * 1.9cqmin); font-style: italic; padding: 0 3cqmin; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .pl-note { display: flex; flex-direction: column; gap: .8cqmin; min-width: 0; padding-top: 1cqmin; }
      img.pl-logo { height: 4.5cqmin; max-width: 22cqmin; }
      .pl-note .oh-airname { font-size: calc(var(--ts) * 2.6cqmin); letter-spacing: .12em; line-height: 1.2; }
      .pl-cs { font-family: var(--sc); font-size: calc(var(--ts) * 6cqmin); letter-spacing: .04em; line-height: 1; }
      .pl-typ { font-size: calc(var(--ts) * 3cqmin); } .pl-typ i { opacity: .8; }
      .pl-note dl { margin: .6cqmin 0 0; display: grid; grid-template-columns: auto 1fr; gap: .5cqmin 1.6cqmin; font-size: calc(var(--ts) * 2.5cqmin); }
      .pl-note dt { font-family: var(--sc); letter-spacing: .08em; font-size: .8em; opacity: .8; padding-top: .3em; } .pl-note dd { margin: 0; }
      .pl-about { font-size: calc(var(--ts) * 2.4cqmin); line-height: 1.3; margin: .6cqmin 0 0; font-style: italic; opacity: .9; }
      /* the modern looks: a plain sans throughout, the colours as variables */
      .md { flex: 1; min-height: 0; position: relative; display: grid; font-family: var(--sans); color: #111; overflow: hidden; }
      .oh.font-fell .md, .oh.font-georgia .md { --sans: 'Archivo Narrow', Arial, sans-serif; }
      .md .oh-logo { height: 7cqmin; max-width: 26cqmin; background: #fff; padding: 1cqmin 1.8cqmin; border-radius: 1.4cqmin; object-fit: contain; box-sizing: border-box; filter: none; mix-blend-mode: normal; }
      .md .oh-airname { font-family: var(--sans); font-size: 2.8cqmin; letter-spacing: .12em; text-transform: uppercase; }
      .md-cs { font-weight: 700; line-height: .95; letter-spacing: -.01em; font-size: calc(var(--ts) * 12cqmin); }
      .md-typ { font-size: calc(var(--ts) * 3.9cqmin); opacity: .9; }
      .md .nb { white-space: nowrap; }
      .md-pic { background-position: center; background-repeat: no-repeat; background-size: cover; } .md-pic.cut { background-size: contain; background-color: var(--t); }
      .md-none { position: relative; background: var(--t); } .md-none .oh-sil { inset: 12%; width: auto; height: auto; }
      .md-rt { display: flex; align-items: center; gap: 2.5cqmin; } .md-rt b { font-size: calc(var(--ts) * 8.3cqmin); font-weight: 700; line-height: 1; } .md-rt small { display: block; font-size: calc(var(--ts) * 2.7cqmin); opacity: .85; font-weight: 400; margin-top: .4cqmin; }
      .md-rt i { flex: 1; border-top: .45cqmin dashed currentColor; opacity: .7; position: relative; } .md-rt i::after { content: "\\2708"; position: absolute; left: 45%; top: -2.9cqmin; font-style: normal; font-size: 3.8cqmin; opacity: 1; }
      .md-rt-text b { font-size: calc(var(--ts) * 5cqmin); }
      .md-st { border-radius: 1.9cqmin; padding: 1.6cqmin 2.1cqmin; display: flex; flex-direction: column; justify-content: flex-end; min-width: 0; } .md-st small { font-size: calc(var(--ts) * 2.3cqmin); letter-spacing: .12em; text-transform: uppercase; opacity: .8; } .md-st b { font-size: calc(var(--ts) * 4.4cqmin); line-height: 1.1; white-space: nowrap; } .md-st em { font-style: normal; font-size: calc(var(--ts) * 2.4cqmin); opacity: .85; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .md-st.on-p { background: var(--p); color: var(--pink); } .md-st.on-s { background: var(--s); color: var(--sink); } .md-st.on-th { background: var(--th); color: #fff; } .md-st.on-sh { background: var(--sh); color: #fff; } .md-st.on-t { background: var(--t); color: #111; } .md-st.on-t small { color: var(--sh); opacity: 1; }
      .md-st.dim { background: rgba(255,255,255,.1); color: #fff; } .md-st.glass { background: rgba(255,255,255,.16); color: #fff; border-top: .8cqmin solid var(--s); }
      .md-top { font-size: calc(var(--ts) * 2.8cqmin); letter-spacing: .14em; text-transform: uppercase; }
      .md-note { position: absolute; right: 2.4cqmin; bottom: 1.2cqmin; font-size: 2.2cqmin; opacity: .8; font-style: italic; color: inherit; }
      .md-ufo { right: 4%; top: 10%; width: 7%; } .md-ufo figcaption { font-family: var(--sans); font-size: 2cqmin; text-transform: uppercase; letter-spacing: .08em; color: #fff; text-shadow: 0 1px 3px rgba(0,0,0,.7); }
      /* A: the boarding pass */
      .md-pass { grid-template-columns: 62fr 38fr; background: var(--t); } .md-pass.portrait { grid-template-columns: 1fr; grid-template-rows: 52fr 48fr; }
      .md-ph { position: relative; min-height: 0; overflow: hidden; } .md-ph .md-pic { position: absolute; inset: 0; } .md-ph::after { content: ""; position: absolute; inset: 0; background: linear-gradient(180deg, transparent 55%, color-mix(in srgb, var(--p) 92%, transparent) 100%); pointer-events: none; }
      .md-ph .md-top { position: absolute; left: 4.6cqmin; top: 3.3cqmin; color: #fff; text-shadow: 0 1px 3px rgba(0,0,0,.5); z-index: 1; } .md-cap { position: absolute; left: 4.6cqmin; right: 4.6cqmin; bottom: 3.6cqmin; color: #fff; font-size: calc(var(--ts) * 3cqmin); opacity: .92; z-index: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .md-side { background: var(--p); color: var(--pink); padding: 4.6cqmin 5cqmin; display: flex; flex-direction: column; gap: 2cqmin; border-left: 1.7cqmin solid var(--s); min-height: 0; } .md-pass.portrait .md-side { border-left: 0; border-top: 1.7cqmin solid var(--s); }
      .md-side .oh-logo { align-self: flex-start; } .md-side .md-rt { margin-top: 1.6cqmin; }
      .md-chips { display: grid; grid-template-columns: 1fr 1fr; gap: 1.7cqmin; margin-top: auto; } .md-chips .md-st em { display: none; }
      /* B: the tiles */
      .md-tiles-page, .md-tiles { } .md.md-tiles { background: var(--t); padding: 3.3cqmin 3.7cqmin; grid-template-rows: auto 1fr; gap: 2.5cqmin; }
      .md-bar { display: flex; align-items: center; gap: 3cqmin; background: var(--p); color: var(--pink); border-radius: 2.9cqmin; padding: 2cqmin 3.3cqmin; min-width: 0; } .md-bar .md-cs { font-size: calc(var(--ts) * 7cqmin); } .md-bar .md-typ { font-size: calc(var(--ts) * 3.3cqmin); } .md-bar-t { min-width: 0; } .md-bar-t > div { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .md-when { margin-left: auto; text-align: right; font-size: calc(var(--ts) * 2.7cqmin); letter-spacing: .08em; text-transform: uppercase; opacity: .9; white-space: nowrap; }
      .md-grid { display: grid; grid-template-columns: 1.25fr 1fr; gap: 2.5cqmin; min-height: 0; position: relative; } .md-tiles.portrait .md-grid { grid-template-columns: 1fr; grid-template-rows: 1fr 1fr; }
      .md-card { border-radius: 2.9cqmin; overflow: hidden; min-height: 0; }
      .md-tiles .md-tiles { display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: auto 1fr 1fr; gap: 2cqmin; min-height: 0; }
      .md-tiles .md-rt { grid-column: 1 / -1; background: #fff; color: #111; border-radius: 2.5cqmin; padding: 2cqmin 2.9cqmin; border-left: 1.25cqmin solid var(--s); } .md-tiles .md-rt b { font-size: calc(var(--ts) * 6.2cqmin); } .md-tiles .md-rt small { color: var(--sh); } .md-tiles .md-rt i { border: 0; height: .8cqmin; background: linear-gradient(90deg, var(--p), var(--th)); border-radius: .4cqmin; opacity: 1; } .md-tiles .md-rt i::after { content: none; }
      .md-tiles .md-st b { font-size: calc(var(--ts) * 6.2cqmin); }
      /* C: the poster */
      .md-poster { color: #fff; background: var(--sh); } .md-bg { position: absolute; inset: 0; } .md-bg.cut { background-size: 70%; background-position: center 30%; background-color: transparent; }
      .md-shade { position: absolute; inset: 0; background: linear-gradient(180deg, color-mix(in srgb, var(--sh) 60%, transparent) 0%, transparent 35%, transparent 45%, color-mix(in srgb, var(--p) 95%, transparent) 100%); }
      .md-top-row { position: absolute; left: 5cqmin; right: 5cqmin; top: 3.7cqmin; display: flex; justify-content: space-between; align-items: center; }
      .md-main { position: absolute; left: 5cqmin; right: 5cqmin; bottom: 4.6cqmin; } .md-poster .md-cs { font-size: calc(var(--ts) * 15.4cqmin); letter-spacing: -.02em; line-height: .9; } .md-poster .md-typ { font-size: calc(var(--ts) * 4.2cqmin); margin: 1.2cqmin 0 2.5cqmin; }
      .md-row { display: flex; align-items: flex-end; gap: 5cqmin; } .md-poster .md-rt b { font-size: calc(var(--ts) * 9cqmin); } .md-poster .md-rt i { flex: 0 0 14cqmin; border: 0; border-top: .6cqmin solid var(--s); opacity: 1; } .md-poster .md-rt i::after { content: none; }
      .md-stats { display: flex; gap: 2cqmin; margin-left: auto; } .md-stats .md-st em { display: none; } .md-stats .md-st:nth-child(2) { border-color: var(--th); } .md-stats .md-st:nth-child(3) { border-color: var(--t); }
      .md-poster.portrait .md-row { flex-direction: column; align-items: flex-start; gap: 2.5cqmin; } .md-poster.portrait .md-stats { margin-left: 0; }
      /* D: the split, dark */
      .md-split { background: var(--sh); color: #fff; grid-template-columns: 1fr 1fr; padding: 4.2cqmin; gap: 4.2cqmin; } .md-split.portrait { grid-template-columns: 1fr; grid-template-rows: 50fr 50fr; }
      .md-frame-wrap { position: relative; min-height: 0; } .md-frame { position: absolute; inset: 0; border-radius: 3.7cqmin; border: .6cqmin solid var(--p); overflow: hidden; }
      .md-pill { position: absolute; left: 2.9cqmin; top: 2.5cqmin; background: var(--p); color: var(--pink); font-size: calc(var(--ts) * 2.5cqmin); padding: .8cqmin 1.9cqmin; border-radius: 99cqmin; letter-spacing: .1em; text-transform: uppercase; }
      .md-r { display: flex; flex-direction: column; gap: 1.6cqmin; min-height: 0; min-width: 0; } .md-hd { display: flex; align-items: center; justify-content: space-between; gap: 2cqmin; } .md-hd span { font-size: calc(var(--ts) * 2.7cqmin); letter-spacing: .14em; text-transform: uppercase; opacity: .8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .md-split .md-cs { font-size: calc(var(--ts) * 13cqmin); } .md-split .md-typ { opacity: .85; }
      .md-split .md-rt { margin: 2cqmin 0; background: var(--p); color: var(--pink); border-radius: 2.9cqmin; padding: 2.5cqmin 3.3cqmin; }
      .md-stats4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1.7cqmin; margin-top: auto; } .md-stats4 .md-st em { display: none; } .md-stats4 .md-st b { font-size: calc(var(--ts) * 4.2cqmin); }
      .md-split.portrait .md-stats4 { grid-template-columns: 1fr 1fr; }
      /* the plate in the airline's colours: the particulars on a panel of its main colour with a stripe of the second, the frame and the caption in it */
      .pl.brand .pl-note { background: var(--brand); color: var(--on-brand); padding: 2.2cqmin 2.6cqmin 2cqmin; border-top: 1.2cqmin solid var(--brand2); }
      .pl.brand .pl-note dt { opacity: .78; } .pl.brand .pl-about { opacity: .92; }
      .pl.brand .pl-frame, .pl.brand .pl-frame i { border-color: var(--brand); } .pl.brand .pl-frame { outline-color: var(--brand2); }
      .pl.brand .pl-fig { color: var(--brand); }
      .pl.brand img.pl-logo.chip { background: #fff; padding: .8cqmin 1.2cqmin; border-radius: .6cqmin; height: 8cqmin; max-width: 30cqmin; box-sizing: border-box; filter: none; mix-blend-mode: normal; align-self: flex-start; }
      .pl.brand .oh-airname { color: var(--on-brand); }
      /* the cluster */
      .cl { flex: 1; min-height: 0; display: flex; flex-direction: column; justify-content: space-evenly; padding: 1cqmin 2cqmin; }
      .cl-row { display: flex; justify-content: space-evenly; align-items: flex-end; }
      .cl-sp { margin: 0; display: flex; flex-direction: column; align-items: center; } .cl-sp.lift { transform: translateY(-1.2cqmin); }
      .cl-pic { width: 100%; display: block; mix-blend-mode: multiply; } .cl-pic.whole { aspect-ratio: 3 / 1; object-fit: cover; mix-blend-mode: normal; } .oh-nopic.cl-pic { aspect-ratio: 3 / 1; } .oh-nopic.cl-pic .oh-sil { transform: scale(.8); }
      .cl-sp figcaption { text-align: center; line-height: 1.12; margin-top: .4cqmin; white-space: nowrap; font-size: calc(var(--ts) * 2.1cqmin); }
      .cl-sp figcaption b { display: block; font-family: var(--sc); letter-spacing: .07em; } .cl-sp figcaption .ln { font-size: .92em; } .cl-sp figcaption .ln:not(.ln-first) { font-style: italic; opacity: .85; font-size: .85em; }
      img.cl-logo { height: 2.4cqmin; max-width: 14cqmin; margin: 0 auto .3cqmin; }
      /* the spotter's log */
      .lg-grid { flex: 1; min-height: 0; display: grid; grid-template-columns: repeat(var(--cols), 1fr); grid-auto-rows: 1fr; gap: 1.2cqmin; padding: 1cqmin 2cqmin; font-family: var(--sans); }
      .lg-card { display: flex; flex-direction: column; min-height: 0; background: rgba(255,255,255,.55); border: 1px solid rgba(0,0,0,.18); overflow: hidden; }
      .lg-pic { flex: 1 1 55%; min-height: 0; background-size: cover; background-position: center; } .lg-none { position: relative; } .lg-none .oh-sil { inset: 2cqmin; width: auto; height: auto; }
      .lg-row { display: flex; justify-content: space-between; align-items: center; gap: 1cqmin; padding: .7cqmin 1cqmin 0; min-width: 0; } .lg-row b { font-size: calc(var(--ts) * 2.8cqmin); flex: none; white-space: nowrap; }
      img.lg-logo { height: 3cqmin; max-width: 12cqmin; min-width: 0; }
      .lg-row .oh-airname { flex: 1 1 auto; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: calc(var(--ts) * 1.9cqmin); letter-spacing: .06em; }
      .lg-lines { padding: .3cqmin 1cqmin .8cqmin; font-size: calc(var(--ts) * 2cqmin); line-height: 1.2; } .lg-lines .ln { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; } .lg-lines .ln-first { font-weight: 600; }
      /* the scene */
      .sc-bg { position: absolute; inset: 0; background-position: center; background-repeat: no-repeat; } .sc-none .oh-sil { inset: 15cqmin; width: auto; height: auto; }
      .sc-top, .sc-main, .sc-credit { position: absolute; font-family: var(--sans); }
      .sc-top { top: 2.6cqmin; left: 2.6cqmin; right: 2.6cqmin; display: flex; justify-content: space-between; font-size: 2.6cqmin; letter-spacing: .1em; text-transform: uppercase; }
      .sc-main { right: 3cqmin; bottom: 7cqmin; text-align: right; max-width: 60%; }
      img.sc-logo { height: 6cqmin; max-width: 30cqmin; margin: 0 0 1cqmin auto; } span.sc-logo { display: block; margin-bottom: .6cqmin; }
      .sc-main.on-dark, .sc-top.on-dark, .sc-credit.on-dark { color: #fff; --halo: rgba(8,12,30,.82); }
      .sc-cs { font-size: calc(var(--ts) * 11cqmin); font-weight: 700; line-height: .95; }
      .sc-typ { font-size: calc(var(--ts) * 3.6cqmin); font-weight: 600; margin-top: .8cqmin; } .sc-typ span { font-weight: 400; opacity: .75; }
      .sc-r { font-size: calc(var(--ts) * 2.8cqmin); margin-top: .4cqmin; } .sc-r .ln { display: inline; }
      .sc-credit { left: 2.6cqmin; right: auto; bottom: 2cqmin; max-width: 50%; padding: 0; }
    </style>`;
}
