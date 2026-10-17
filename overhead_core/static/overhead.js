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
  return `${head(d)}<div class="msg"><div class="msg-t">${esc(title)}</div><div class="msg-b">${esc(body)}</div>${hint ? `<div class="msg-h">${esc(hint)}</div>` : ''}</div>${foot(d)}`;
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

/* The plate: one aircraft, large, in a ruled frame, with its particulars beside it. */
function platePage(d) {
  const a = d.aircraft[0];
  const ro = a.route || {};
  const rows = [
    ['Route', a.route_text],
    ['Height', a.ground ? 'on the ground' : `${a.alt.toLocaleString()} ft, ${a.trend}${a.rate ? ` at ${Math.abs(a.rate).toLocaleString()} ft/min` : ''}`],
    ['Where', `${a.where}, heading ${String(a.trk).padStart(3, '0')}°`],
    ['Speed', a.gs ? `${a.gs} kt over the ground` : ''],
  ].filter((r) => r[1]);
  const portrait = (d.cell_h || 1) > (d.cell_w || 1);
  return `${head(d)}<div class="pl${portrait ? ' portrait' : ''}"><div class="pl-plate"><div class="pl-frame"><i class="tl"></i><i class="tr"></i><i class="bl"></i><i class="br"></i></div>${picture(a, 'pl-pic')}<div class="pl-fig">Fig. 1. ${esc(a.typ)}${a.reg ? `, ${esc(a.reg)}` : ''}${a.pic && a.pic.credit ? `, ${esc(a.pic.credit)}` : ''}</div></div><div class="pl-note">${logo(a, 'pl-logo mono')}<div class="pl-cs">${esc(a.cs)}</div><div class="pl-typ">${esc(a.typ)}${a.reg ? ` <i>· ${esc(a.reg)}</i>` : ''}${a.air && a.air !== 'private' && !a.logo ? `<i> · ${esc(a.air)}</i>` : ''}</div><dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join('')}</dl><p class="pl-about">${esc(a.about)}</p></div></div>${head(d, 'bottom')}${foot(d)}`;
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

/* The cluster packed: every cut-out's footprint laid on a lattice from the middle out, each as
   large as the page allows (the Specimen Sheet's packer). Returns the sheet, or null. */
async function packCluster(d) {
  const w = d.cell_w || 800, h = d.cell_h || 480;
  const specimens = d.aircraft.map((a) => {
    const pic = a.pic || {};
    const src = pic.src || SIL_URL(a.cls);
    const whole = !!pic.src && !!pic.whole;
    return {
      name: a.cs, sci: a.reg || a.cs, src, cut: whole ? null : src, on_paper: false, classic: false, whole, neutral: false, no_flip: true,
      factor: Math.pow((a.span || 20) / 35, 0.45), aspect: pic.aspect > 0 ? pic.aspect : 3, paper: null,
      lines: [a.cs, ...(a.lines || [])],
    };
  });
  const label = Math.max(0.017, 13 / h) * ((Number(d.text_size) || 100) / 100);
  const zoom = Math.max(0.4, Math.min(1, (Number(d.scale) || 100) / 100));
  try {
    return await buildSheet({ specimens, ratio: w / h, size: 1400, label, paper: d.paper === 'white' ? 'white' : d.paper === 'aged' ? 'aged' : 'cream', ink: INK[d.paper] || INK.cream, layout: 'cluster', facing: 'inward', zoom });
  } catch (e) { console.warn('overhead: packing failed', e); return null; }
}

function packedPage(d, made) {
  const byName = Object.fromEntries(d.aircraft.map((a) => [a.cs, a]));
  const tags = made.items.map((m) => {
    const lines = m.lines || [];
    if (!lines.length) return '';
    const a = byName[m.name] || {};
    const first = `${a.logo ? `<img class="sh-logo" src="${a.logo}" alt="">` : ''}${esc(lines[0])}`;
    return `<span class="sh-l" style="left:${(m.at[0] * 100).toFixed(2)}%;top:${(m.at[1] * 100).toFixed(2)}%"><span class="sh-ln sh-name">${first}</span>${lines.slice(1).map((t) => `<span class="sh-ln sh-sm">${esc(t)}</span>`).join('')}</span>`;
  }).join('');
  const page = `<div class="sh-page" style="--r:${made.ratio};--lf:${made.label}"><img src="${made.src}" alt="" decoding="sync">${tags}</div>`;
  return `${head(d)}<div class="sh">${page}</div>${head(d, 'bottom')}${foot(d)}`;
}

/* The scene: one whole painting across the page, the particulars set over its paper. */
function scenePage(d) {
  const a = d.aircraft[0];
  const art = a.pic && a.pic.src ? `<div class="sc-bg" style="background-image:url('${a.pic.src}');background-size:${a.pic.whole ? 'cover' : 'contain'}"></div>` : `<div class="sc-bg sc-none">${sil(a.cls)}</div>`;
  const top = d.header === 'hidden' ? '' : `<div class="sc-top"><span>${esc(d.title)} · ${esc(d.area)}</span><span>${esc(d.time)} · ${esc(d.date)}</span></div>`;
  return `${art}${top}<div class="sc-main">${logo(a, 'sc-logo')}<div class="sc-cs">${esc(a.cs)}</div><div class="sc-typ">${esc(a.typ)}${a.reg ? ` <span>· ${esc(a.reg)}</span>` : ''}</div><div class="sc-r">${lines(a).replace(/<\/span><span/g, '</span> · <span')}</div></div>${foot(d).replace('class="credit"', 'class="credit sc-credit"')}`;
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
    if (widget === 'cluster' && d.pictures === 'paintings' && typeof document !== 'undefined') {
      const made = await packCluster(d);
      if (made && made.src) { await predecode(made.src); body = packedPage(d, made); }
      else body = clusterPage(d);
    } else body = widget === 'photo' ? photoPage(d) : widget === 'plate' ? platePage(d) : widget === 'scene' ? scenePage(d) : clusterPage(d);
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
      .fb-logo { height: 6cqmin; max-width: 30cqmin; margin-bottom: 1cqmin; }
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
      .pl-logo { height: 4.5cqmin; max-width: 22cqmin; }
      .pl-cs { font-family: var(--sc); font-size: calc(var(--ts) * 6cqmin); letter-spacing: .04em; line-height: 1; }
      .pl-typ { font-size: calc(var(--ts) * 3cqmin); } .pl-typ i { opacity: .8; }
      .pl-note dl { margin: .6cqmin 0 0; display: grid; grid-template-columns: auto 1fr; gap: .5cqmin 1.6cqmin; font-size: calc(var(--ts) * 2.5cqmin); }
      .pl-note dt { font-family: var(--sc); letter-spacing: .08em; font-size: .8em; opacity: .8; padding-top: .3em; } .pl-note dd { margin: 0; }
      .pl-about { font-size: calc(var(--ts) * 2.4cqmin); line-height: 1.3; margin: .6cqmin 0 0; font-style: italic; opacity: .9; }
      /* the cluster */
      .cl { flex: 1; min-height: 0; display: flex; flex-direction: column; justify-content: space-evenly; padding: 1cqmin 2cqmin; }
      .cl-row { display: flex; justify-content: space-evenly; align-items: flex-end; }
      .cl-sp { margin: 0; display: flex; flex-direction: column; align-items: center; } .cl-sp.lift { transform: translateY(-1.2cqmin); }
      .cl-pic { width: 100%; display: block; mix-blend-mode: multiply; } .cl-pic.whole { aspect-ratio: 3 / 1; object-fit: cover; mix-blend-mode: normal; } .oh-nopic.cl-pic { aspect-ratio: 3 / 1; } .oh-nopic.cl-pic .oh-sil { transform: scale(.8); }
      .cl-sp figcaption { text-align: center; line-height: 1.12; margin-top: .4cqmin; white-space: nowrap; font-size: calc(var(--ts) * 2.1cqmin); }
      .cl-sp figcaption b { display: block; font-family: var(--sc); letter-spacing: .07em; } .cl-sp figcaption .ln { font-size: .92em; } .cl-sp figcaption .ln:not(.ln-first) { font-style: italic; opacity: .85; font-size: .85em; }
      .cl-logo { height: 2.4cqmin; max-width: 14cqmin; margin: 0 auto .3cqmin; }
      /* the spotter's log */
      .lg-grid { flex: 1; min-height: 0; display: grid; grid-template-columns: repeat(var(--cols), 1fr); grid-auto-rows: 1fr; gap: 1.2cqmin; padding: 1cqmin 2cqmin; font-family: var(--sans); }
      .lg-card { display: flex; flex-direction: column; min-height: 0; background: rgba(255,255,255,.55); border: 1px solid rgba(0,0,0,.18); overflow: hidden; }
      .lg-pic { flex: 1 1 55%; min-height: 0; background-size: cover; background-position: center; } .lg-none { position: relative; } .lg-none .oh-sil { inset: 2cqmin; width: auto; height: auto; }
      .lg-row { display: flex; justify-content: space-between; align-items: center; padding: .7cqmin 1cqmin 0; } .lg-row b { font-size: calc(var(--ts) * 2.8cqmin); }
      .lg-logo { height: 3cqmin; max-width: 12cqmin; }
      .lg-lines { padding: .3cqmin 1cqmin .8cqmin; font-size: calc(var(--ts) * 2cqmin); line-height: 1.2; } .lg-lines .ln { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; } .lg-lines .ln-first { font-weight: 600; }
      /* the scene */
      .sc-bg { position: absolute; inset: 0; background-position: center; background-repeat: no-repeat; } .sc-none .oh-sil { inset: 15cqmin; width: auto; height: auto; }
      .sc-top, .sc-main, .sc-credit { position: absolute; font-family: var(--sans); }
      .sc-top { top: 2.6cqmin; left: 2.6cqmin; right: 2.6cqmin; display: flex; justify-content: space-between; font-size: 2.6cqmin; letter-spacing: .1em; text-transform: uppercase; }
      .sc-main { right: 3cqmin; bottom: 7cqmin; text-align: right; max-width: 60%; }
      .sc-logo { height: 6cqmin; max-width: 30cqmin; margin: 0 0 1cqmin auto; }
      .sc-cs { font-size: calc(var(--ts) * 11cqmin); font-weight: 700; line-height: .95; }
      .sc-typ { font-size: calc(var(--ts) * 3.6cqmin); font-weight: 600; margin-top: .8cqmin; } .sc-typ span { font-weight: 400; opacity: .75; }
      .sc-r { font-size: calc(var(--ts) * 2.8cqmin); margin-top: .4cqmin; } .sc-r .ln { display: inline; }
      .sc-credit { left: 2.6cqmin; right: auto; bottom: 2cqmin; max-width: 50%; padding: 0; }
    </style>`;
}
