/* The packer: cut-outs onto one page, each as large as the page allows.

   Every specimen's outline is rastered onto a grid of CELL-pixel cells in three layers: the
   body, the body with a little air round it, and the strip its caption needs. A body never
   touches another's air or caption; air may overlap air; a caption may sit in a neighbour's
   air but not on a body or another caption. So the footprints interlock, and a long name no
   longer holds a strip of paper open beside its specimen.

   Placement is greedy from the middle out: the largest first, each on the nearest free lattice
   point to the page's centre (turned to face the middle when its outline says which way it
   faces), the group pulled inward after each one lands. The common scale is found by bisection, the largest at which everything fits. Then
   each specimen grows in turn where it stands, or moves to the nearest gap that takes it, and
   the whole is pulled inward, until nothing can grow; last, the arrangement is scaled as one to
   the page's margins. Captions are measured with the canvas, and a page too small to carry
   them loses the count line first, then the captions. */

export const CELL = 5;
const MARGIN = 0.02;
const AIR = 1;            // cells of air round a body: bodies sit two apart, their air may overlap
const GROW = 1.05;        // growth per round
const RELATIVE_CAP = 3;   // no specimen grows past this times its given size
const TOP = 0.8;          // nor past this share of the page's short side
const WRAP_AT = 20;
const SETTLE_PASSES = 20;  // inward pulls after each placement

/* A caption longer than about twenty characters is broken at its spaces; a line only a little
   over is left whole, since two short lines cost more height than they save. */
export function wrapLabel(text, max = WRAP_AT) {
  const t = String(text);
  if (t.length <= max + 2) return t;
  const out = [];
  let cur = '';
  for (const w of t.split(' ')) {
    if (cur && (cur + ' ' + w).length > max) { out.push(cur); cur = w; } else cur = cur ? cur + ' ' + w : w;
  }
  if (cur) out.push(cur);
  return out.join('\n');
}

/* What of a specimen's caption lines a page of ``n`` specimens can carry. By the page's height
   in caption heights: everything, wrapped, on a tall page; the first line alone on a middling
   one; nothing on a small cell, where a caption would be wider than its specimen. And by how
   much caption the page would hold stacked: all of it up to nine tenths of the page's height,
   the first lines alone up to one and two fifths, else none. The lesser of the two. */
export function captionPlan(lines, label, n = 1) {
  if (!lines || !lines.length) return [];
  const tall = 1 / Math.max(1e-6, label);
  const byHeight = tall < 16 ? 0 : tall < 30 ? 1 : 2;
  const stacked = n * 1.2 * label;
  const byCount = stacked * lines.length <= 0.9 ? 2 : stacked <= 1.4 ? 1 : 0;
  const level = Math.min(byHeight, byCount);
  if (level === 0) return [];
  if (level === 1) return [String(lines[0])];
  return lines.map((t) => wrapLabel(t));
}

let MEASURE = null;
/* Text widths in pixels at ``px``, from a canvas; the page's small capitals with their letter
   spacing run a little wider than the serif measured here, hence the allowance. */
export function measurer(px) {
  if (MEASURE === null) {
    try {
      const c = typeof OffscreenCanvas !== 'undefined' ? new OffscreenCanvas(8, 8) : typeof document !== 'undefined' ? document.createElement('canvas') : null;
      MEASURE = c ? c.getContext('2d') : false;
    } catch { MEASURE = false; }
  }
  return (text) => {
    if (!MEASURE) return text.length * 0.62 * px;
    MEASURE.font = `${px}px Georgia, "Times New Roman", serif`;
    return MEASURE.measureText(text).width * 1.1 + text.length * px * 0.04;
  };
}

/* A mask halved by taking the maximum, again and again, so a cell asks the level whose pixels
   are no bigger than itself and a leg one pixel wide still sets its cell. */
const PYRAMIDS = new WeakMap();
function pyramidOf(mask) {
  let levels = PYRAMIDS.get(mask.data);
  if (levels) return levels;
  levels = [{ w: mask.w, h: mask.h, data: mask.data }];
  for (;;) {
    const a = levels[levels.length - 1];
    if (a.w <= 1 && a.h <= 1) break;
    const w = Math.ceil(a.w / 2), h = Math.ceil(a.h / 2), data = new Uint8Array(w * h);
    for (let y = 0; y < a.h; y++) for (let x = 0; x < a.w; x++) if (a.data[y * a.w + x]) data[(y >> 1) * w + (x >> 1)] = 1;
    levels.push({ w, h, data });
  }
  PYRAMIDS.set(mask.data, levels);
  return levels;
}

function dilate(m, w, h, r) {
  const out = new Uint8Array(w * h);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    if (!m[y * w + x]) continue;
    for (let dy = -r; dy <= r; dy++) for (let dx = -r; dx <= r; dx++) {
      const xx = x + dx, yy = y + dy;
      if (xx >= 0 && yy >= 0 && xx < w && yy < h && dx * dx + dy * dy <= r * r + r) out[yy * w + xx] = 1;
    }
  }
  return out;
}

/* A specimen's footprint at ``scale``, mirrored when ``flip``: the body (fb), the body with
   its air (fa) and its caption strip (fs), all on one fw x fh grid. ``off``/``top`` say where
   the drawn picture sits inside; ``lt`` is the caption's first row. */
function footprint(item, scale, flip, cap, air) {
  const key = `${Math.round(scale * item.mask.w * 4)}|${flip ? 1 : 0}`;
  let memo = item._fp;
  if (!memo) memo = item._fp = new Map();
  const had = memo.get(key);
  if (had) return had;
  const tw = Math.max(1, Math.ceil((item.mask.w * scale) / CELL - 1e-6)), th = Math.max(1, Math.ceil((item.mask.h * scale) / CELL - 1e-6));
  const c = CELL / scale;
  const levels = pyramidOf(item.mask);
  const L = Math.min(levels.length - 1, Math.max(0, Math.floor(Math.log2(Math.max(1, c)))));
  const lv = levels[L], q = 2 ** L;
  const raw = new Uint8Array(tw * th);
  let mass = 0;
  for (let y = 0; y < th; y++) {
    const y0 = Math.max(0, Math.floor((y * c) / q)), y1 = Math.min(lv.h, Math.max(y0 + 1, Math.ceil(((y + 1) * c) / q)));
    for (let x = 0; x < tw; x++) {
      let a = x * c, e = (x + 1) * c;
      if (flip) { const t = item.mask.w - e; e = item.mask.w - a; a = t; }
      const x0 = Math.max(0, Math.floor(a / q)), x1 = Math.min(lv.w, Math.max(x0 + 1, Math.ceil(e / q)));
      let hit = 0;
      for (let yy = y0; yy < y1 && !hit; yy++) for (let xx = x0; xx < x1; xx++) if (lv.data[yy * lv.w + xx]) { hit = 1; break; }
      if (hit) { raw[y * tw + x] = 1; mass++; }
    }
  }
  const pad = Math.min(tw, th) > 4 ? air : 0;
  const bw = tw + 2 * pad, bh = th + 2 * pad;
  let grown = new Uint8Array(bw * bh);
  for (let y = 0; y < th; y++) for (let x = 0; x < tw; x++) grown[(y + pad) * bw + x + pad] = raw[y * tw + x];
  if (pad) grown = dilate(grown, bw, bh, pad);
  // the caption: its lines measured, stacked under the lowest ink in its own columns
  const segs = cap.lines.flatMap((t) => String(t).split('\n'));
  const rowH = Math.max(1, Math.ceil((cap.px * 1.2) / CELL));
  const rows = segs.length * rowH;
  const cw = segs.length ? Math.ceil(Math.max(...segs.map((s) => cap.measure(s))) / CELL) + 1 : 0;
  const fw = Math.max(bw, cw);
  const off = Math.floor((fw - bw) / 2), cx = Math.floor((fw - cw) / 2);
  let lt = bh;
  if (rows) {
    let low = -1;
    for (let y = bh - 1; y >= 0 && low < 0; y--) for (let x = Math.max(0, cx - off); x < Math.min(bw, cx - off + cw); x++) if (grown[y * bw + x]) { low = y; break; }
    lt = Math.max(Math.floor(bh * 0.6), Math.min(bh, low + 1));
  }
  const fh = Math.max(bh, lt + rows);
  const fb = new Uint8Array(fw * fh), fa = new Uint8Array(fw * fh), fs = new Uint8Array(fw * fh);
  for (let y = 0; y < bh; y++) for (let x = 0; x < bw; x++) if (grown[y * bw + x]) fa[y * fw + off + x] = 1;
  for (let y = 0; y < th; y++) for (let x = 0; x < tw; x++) if (raw[y * tw + x]) fb[(y + pad) * fw + off + pad + x] = 1;
  if (rows) for (let y = lt; y < lt + rows; y++) for (let x = cx; x < cx + cw; x++) fs[y * fw + x] = 1;
  const f = { fw, fh, fb, fa, fs, off: off + pad, top: pad, tw, th, mass, flip, lt, cw, cx, rows };
  memo.set(key, f);
  return f;
}

class Page {
  constructor(W, H, air, px, top) {
    this.gw = Math.floor(W / CELL); this.gh = Math.floor(H / CELL);
    this.mx = Math.max(1, Math.round(this.gw * MARGIN)); this.my = Math.max(1, Math.round(this.gh * MARGIN));
    this.cx = this.gw / 2; this.cy = this.gh / 2;
    this.air = air; this.top = top;
    this.cap = { px, measure: measurer(px) };
    // lattice points, nearest the middle first, the distance in page units so a cluster follows the page's shape
    const pts = [];
    for (let y = this.my; y < this.gh - this.my; y += 2) for (let x = this.mx; x < this.gw - this.mx; x += 2) pts.push([x, y, ((x - this.cx) / this.gw) ** 2 + ((y - this.cy) / this.gh) ** 2]);
    pts.sort((a, b) => a[2] - b[2]);
    this.lattice = pts;
  }
  grid() { const n = this.gw * this.gh; return { b: new Uint16Array(n), a: new Uint16Array(n), s: new Uint16Array(n) }; }
  within(x, y, f) { return x >= this.mx && y >= this.my && x + f.fw <= this.gw - this.mx && y + f.fh <= this.gh - this.my; }
  overlaps(occ, x, y, f) {
    const gw = this.gw;
    for (let yy = 0; yy < f.fh; yy++) for (let xx = 0; xx < f.fw; xx++) {
      const k = yy * f.fw + xx, g = (y + yy) * gw + x + xx;
      if (f.fb[k] && (occ.a[g] || occ.s[g])) return true;
      if (f.fa[k] && occ.b[g]) return true;
      if (f.fs[k] && (occ.b[g] || occ.s[g])) return true;
    }
    return false;
  }
  free(occ, x, y, f) { return this.within(x, y, f) && !this.overlaps(occ, x, y, f); }
  stamp(occ, x, y, f, on) {
    const d = on ? 1 : -1, gw = this.gw;
    for (let yy = 0; yy < f.fh; yy++) for (let xx = 0; xx < f.fw; xx++) {
      const k = yy * f.fw + xx, g = (y + yy) * gw + x + xx;
      if (f.fb[k]) occ.b[g] += d;
      if (f.fa[k]) occ.a[g] += d;
      if (f.fs[k]) occ.s[g] += d;
    }
  }
  foot(item, scale, flip) { return footprint(item, scale, flip, { lines: item.lines, px: this.cap.px, measure: this.cap.measure }, this.air); }
  /* the anchor that puts a footprint's body centre on a lattice point */
  at(p, f) { return [Math.round(p[0] - f.off - f.tw / 2), Math.round(p[1] - f.top - f.th / 2)]; }
  /* the first lattice point, from the middle out, that takes a footprint; or null */
  spot(occ, f, from = 0) {
    const L = this.lattice;
    for (let i = from; i < L.length; i++) { const [x, y] = this.at(L[i], f); if (this.free(occ, x, y, f)) return [x, y]; }
    return null;
  }
}

/* Which way a specimen should turn on one side of the page: toward the middle. */
function flipFor(item, side, facing) {
  if (facing === 'painted' || !item.flippable || !item.face) return false;
  return side < 0 ? item.face === 'left' : item.face === 'right';
}

/* Everything placed at a common ``unit``, the largest first, nearest the middle; null when one
   of them finds no room. */
function place(page, items, unit, facing) {
  const occ = page.grid();
  const placed = [];
  for (const it of items) {
    const scale = Math.min(unit * it.factor, page.top / Math.max(it.mask.w, it.mask.h));
    let done = null;
    const L = page.lattice;
    for (let i = 0; i < L.length && !done; i++) {
      const p = L[i];
      const first = flipFor(it, p[0] < page.cx ? -1 : 1, facing);
      for (const flip of it.flippable && facing !== 'painted' ? [first, !first] : [false]) {
        const f = page.foot(it, scale, flip);
        const [x, y] = page.at(p, f);
        if (page.free(occ, x, y, f)) { page.stamp(occ, x, y, f, 1); done = { it, x, y, f, scale, base: scale }; break; }
      }
    }
    if (!done) return null;
    placed.push(done);
    // the group closes up before the next one lands, so each newcomer finds a cluster already
    // tight; on the bench this packs a seventh more paper than settling only at the end
    settle(page, occ, placed, SETTLE_PASSES);
  }
  return { occ, placed };
}

/* The largest common scale at which everything fits, by bracketing then bisection. */
function largest(page, items, u0, facing, steps) {
  let lo = 0, hi = 0, best = null;
  let got = place(page, items, u0, facing);
  if (got) {
    lo = u0; best = got;
    for (let u = u0 * 1.3, i = 0; i < 8 && !hi; u *= 1.3, i++) { const t = place(page, items, u, facing); if (t) { lo = u; best = t; } else hi = u; }
    if (!hi) return best;
  } else {
    hi = u0;
    for (let u = u0 * 0.8, i = 0; i < 16 && !lo; u *= 0.8, i++) { const t = place(page, items, u, facing); if (t) { lo = u; best = t; } else hi = u; }
    if (!best) return null;
  }
  for (let i = 0; i < steps; i++) { const mid = (lo + hi) / 2; const t = place(page, items, mid, facing); if (t) { lo = mid; best = t; } else hi = mid; }
  return best;
}

/* Pull everything a cell toward the middle where it can go: the neighbour cell that brings it
   nearest, a few passes. */
function settle(page, occ, placed, passes = 3) {
  const steps = [[0, 1], [0, -1], [1, 0], [-1, 0], [1, 1], [-1, 1], [1, -1], [-1, -1]];
  for (let pass = 0; pass < passes; pass++) {
    let moved = false;
    for (const p of placed) {
      const bx = p.x + p.f.off + p.f.tw / 2, by = p.y + p.f.top + p.f.th / 2;
      const d0 = ((bx - page.cx) / page.gw) ** 2 + ((by - page.cy) / page.gh) ** 2;
      page.stamp(occ, p.x, p.y, p.f, 0);
      let best = null, bd = d0 - 1e-9;
      for (const [dx, dy] of steps) {
        const d = ((bx + dx - page.cx) / page.gw) ** 2 + ((by + dy - page.cy) / page.gh) ** 2;
        if (d < bd && page.free(occ, p.x + dx, p.y + dy, p.f)) { bd = d; best = [dx, dy]; }
      }
      if (best) { p.x += best[0]; p.y += best[1]; moved = true; }
      page.stamp(occ, p.x, p.y, p.f, 1);
    }
    if (!moved) break;
  }
}

/* Each specimen a little larger where it stands, nudged, or on the nearest gap that takes it,
   the smallest drawn first; then a pull inward; again until nothing grows or the time is up. */
function inflate(page, occ, placed, deadline) {
  for (let round = 0; round < 80; round++) {
    if (performance.now() > deadline) break;
    let grew = false;
    for (const p of [...placed].sort((a, b) => a.scale * Math.max(a.it.mask.w, a.it.mask.h) - b.scale * Math.max(b.it.mask.w, b.it.mask.h))) {
      if (p.stuck && round - p.stuck < 3) continue;
      const ns = p.scale * GROW;
      if (ns > p.base * RELATIVE_CAP || ns * Math.max(p.it.mask.w, p.it.mask.h) > page.top) continue;
      const nf = page.foot(p.it, ns, p.f.flip);
      const bx = p.x + p.f.off + p.f.tw / 2, by = p.y + p.f.top + p.f.th / 2;
      const nx = Math.round(bx - nf.off - nf.tw / 2), ny = Math.round(by - nf.top - nf.th / 2);
      page.stamp(occ, p.x, p.y, p.f, 0);
      let spot = null;
      for (const [dx, dy] of [[0, 0], [0, 1], [0, -1], [1, 0], [-1, 0], [1, 1], [-1, 1], [1, -1], [-1, -1]]) {
        if (page.free(occ, nx + dx, ny + dy, nf)) { spot = [nx + dx, ny + dy]; break; }
      }
      if (!spot) spot = page.spot(occ, nf);
      if (spot) { p.x = spot[0]; p.y = spot[1]; p.f = nf; p.scale = ns; grew = true; p.stuck = 0; } else p.stuck = round || 1;
      page.stamp(occ, p.x, p.y, p.f, 1);
    }
    settle(page, occ, placed);
    if (!grew) break;
  }
}

/* The arrangement scaled as one about the page's centre until it meets the margins. The
   captions keep their size, so their strips only get roomier. */
function fill(page, placed) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const p of placed) { x0 = Math.min(x0, p.x); y0 = Math.min(y0, p.y); x1 = Math.max(x1, p.x + p.f.fw); y1 = Math.max(y1, p.y + p.f.fh); }
  const ux0 = page.mx, ux1 = page.gw - page.mx, uy0 = page.my, uy1 = page.gh - page.my;
  let s = Math.min((ux1 - ux0) / Math.max(1, x1 - x0), (uy1 - uy0) / Math.max(1, y1 - y0), 1.5);
  for (const p of placed) s = Math.min(s, page.top / Math.max(1, p.scale * Math.max(p.it.mask.w, p.it.mask.h)));
  if (s <= 1.01) return;
  const bcx = (x0 + x1) / 2, bcy = (y0 + y1) / 2, ucx = (ux0 + ux1) / 2, ucy = (uy0 + uy1) / 2;
  for (const p of placed) {
    // the body's centre moves with the group; the picture is re-anchored about it at the new scale
    const bx = p.x + p.f.off + p.f.tw / 2, by = p.y + p.f.top + p.f.th / 2;
    p.cx = ucx + (bx - bcx) * s; p.cy = ucy + (by - bcy) * s; p.scale *= s;
    p.capDy = (p.f.lt - p.f.top - p.f.th / 2) * s;
  }
}

/* Pack ``items`` ([{ mask, factor, lines, flippable, face }]) onto a W x H page. ``label`` is the
   caption height as a share of the page's height, ``facing`` 'inward' or 'painted', ``fast``
   a quick first guess for a placeholder page, ``budget`` milliseconds for the growing. Returns,
   per item in the order given, { x, y, w, h, flip, cap: [cx, cy], lines } in pixels, or null for
   one that found no room; captions are the lines actually reserved for. */
export function packSheet(items, W, H, label, { facing = 'inward', fast = false, budget = 4000, air = AIR, packer = 'balanced' } = {}) {
  if (packer === 'spiral' || packer === 'voids') return packFugleramme(items, W, H, label, packer, facing);
  const t0 = performance.now();
  const px = label * H;
  const plan = items.map((it) => captionPlan(it.lines, label, items.length));
  const page = new Page(W, H, air, px, TOP * Math.min(W, H));
  const order = items.map((it, i) => ({ it: { ...it, _fp: null, lines: plan[i] }, i })).sort((a, b) => b.it.factor ** 2 * b.it.mask.w * b.it.mask.h - a.it.factor ** 2 * a.it.mask.w * a.it.mask.h);
  const room = (page.gw - 2 * page.mx) * (page.gh - 2 * page.my) * CELL * CELL;
  const area = order.reduce((s, o) => s + o.it.mask.w * o.it.mask.h * o.it.factor ** 2, 0);
  const u0 = Math.sqrt((0.5 * room) / Math.max(1, area));
  const its = order.map((o) => o.it);
  let got = largest(page, its, u0, facing, fast ? 3 : 6);
  if (!got) {
    // not even small: without captions, then without air
    for (const it of its) { it.lines = []; it._fp = null; }
    got = largest(page, its, u0 * 0.5, facing, 3);
    if (!got) return items.map(() => null);
  }
  if (!fast) inflate(page, got.occ, got.placed, t0 + budget);
  for (const p of got.placed) { p.cx = p.x + p.f.off + p.f.tw / 2; p.cy = p.y + p.f.top + p.f.th / 2; p.capDy = p.f.lt - p.f.top - p.f.th / 2; }
  fill(page, got.placed);
  const out = items.map(() => null);
  got.placed.forEach((p, k) => {
    const w = p.it.mask.w * p.scale, h = p.it.mask.h * p.scale;
    const x = p.cx * CELL - w / 2, y = p.cy * CELL - h / 2;
    out[order[k].i] = { x, y, w, h, flip: p.f.flip, cap: [x + w / 2, p.cy * CELL + p.capDy * CELL], lines: p.it.lines };
  });
  return out;
}

/* Spiral and voids: the two layouts of Fugleramme's packer (render/packing.py and the size
   search in render/collage.py), adapted to the footprints above.

   Copyright (c) 2026 Arne Giacomo Munthe-Kaas, https://github.com/arnegiacomo/fugleramme
   MIT License: permission is hereby granted, free of charge, to any person obtaining a copy of
   this software and associated documentation files (the "Software"), to deal in the Software
   without restriction, including without limitation the rights to use, copy, modify, merge,
   publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to
   whom the Software is furnished to do so, subject to the following conditions: the above
   copyright notice and this permission notice shall be included in all copies or substantial
   portions of the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.

   A specimen and its caption are one footprint with no air round it, so specimens nestle and a
   caption never lands on a neighbour. Spiral takes the first free spot on an outward walk from
   the middle, the largest first, which makes a round cluster with bare corners. Voids scores
   every legal spot at once, by how empty the paper round it is and how much of it the
   specimen would touch, so the large ones spread over the sheet and the small ones fill the
   rest, corners included. The size overshoots and shrinks by a tenth until everything fits,
   then bisects back toward the size that failed; the cluster is centred last. */

const F_STEP = 1;          // spiral: cells between candidate spots
const F_SHRINK = 0.9;
const F_ATTEMPTS = 20;
const F_REFINE = { spiral: 3, voids: 3 };
const F_SIGMA = 8;         // voids: cells the emptiness is measured over
const F_CLING = 0.8;
const F_PULL = 0.02;

/* Mirrored or not by the name alone, so a specimen does not turn when another arrives. */
function nameFlip(it) {
  let h = 2166136261;
  for (const ch of String(it.sci || it.name || '')) { h ^= ch.codePointAt(0); h = Math.imul(h, 16777619) >>> 0; }
  return (h & 255) < 128;
}

/* One mask of the body and its caption strip, and the rows to probe first: the densest row in
   each third, since most spots on a filling page collide and a row is cheap to test. */
function solid(f) {
  if (f.u) return f;
  const u = new Uint8Array(f.fw * f.fh);
  const cells = [];
  for (let k = 0; k < u.length; k++) if (f.fb[k] || f.fs[k]) { u[k] = 1; cells.push(k); }
  const rows = [];
  for (let b = 0; b < 3; b++) {
    const y0 = Math.floor((b * f.fh) / 3), y1 = Math.floor(((b + 1) * f.fh) / 3);
    let best = -1, bn = 0;
    for (let y = y0; y < y1; y++) { let n = 0; for (let x = 0; x < f.fw; x++) n += u[y * f.fw + x]; if (n > bn) { bn = n; best = y; } }
    if (best >= 0) rows.push(best);
  }
  f.u = u; f.cells = cells; f.probes = rows; f.area = cells.length;
  return f;
}

function hits(occ, gw, x, y, f) {
  for (const r of f.probes) { const g = (y + r) * gw + x, k = r * f.fw; for (let xx = 0; xx < f.fw; xx++) if (f.u[k + xx] && occ[g + xx]) return true; }
  for (const k of f.cells) { const yy = (k / f.fw) | 0, xx = k - yy * f.fw; if (occ[(y + yy) * gw + x + xx]) return true; }
  return false;
}

function take(occ, gw, x, y, f) {
  for (const k of f.cells) { const yy = (k / f.fw) | 0, xx = k - yy * f.fw; occ[(y + yy) * gw + x + xx] = 1; }
}

/* The first spot on an outward walk from the middle where ``f`` fits inside the margins. */
function firstFree(page, occ, f) {
  const { gw, gh, mx, my } = page;
  const cx = gw / 2, cy = gh / 2, maxR = Math.hypot(gw, gh);
  const fits = (px, py) => {
    const x = Math.round(px - f.fw / 2), y = Math.round(py - f.fh / 2);
    if (x < mx || y < my || x + f.fw > gw - mx || y + f.fh > gh - my) return null;
    return hits(occ, gw, x, y, f) ? null : [x, y];
  };
  let got = fits(cx, cy);
  if (got) return got;
  for (let r = F_STEP; r <= maxR; r += F_STEP) {
    const count = Math.max(8, Math.floor((2 * Math.PI * r) / F_STEP));
    for (let i = 0; i < count; i++) {
      const a = (2 * Math.PI * i) / count;
      if ((got = fits(cx + r * Math.cos(a), cy + r * Math.sin(a)))) return got;
    }
  }
  return null;
}

/* An in-place radix-2 FFT over ``n`` complex values at ``re``/``im`` with stride ``s``; the
   bit reversal and the twiddles are kept per length. */
const FFT_TABLES = new Map();
function tables(n) {
  let t = FFT_TABLES.get(n);
  if (t) return t;
  const rev = new Uint32Array(n);
  for (let i = 1, j = 0; i < n; i++) { let bit = n >> 1; for (; j & bit; bit >>= 1) j ^= bit; j ^= bit; rev[i] = j; }
  const cos = new Float64Array(n / 2), sin = new Float64Array(n / 2);
  for (let k = 0; k < n / 2; k++) { cos[k] = Math.cos((2 * Math.PI * k) / n); sin[k] = Math.sin((2 * Math.PI * k) / n); }
  FFT_TABLES.set(n, (t = { rev, cos, sin }));
  return t;
}
function fft1(re, im, off, n, s, inv) {
  const { rev, cos, sin } = tables(n);
  for (let i = 1; i < n; i++) {
    const j = rev[i];
    if (i < j) {
      const a = off + i * s, b = off + j * s;
      let t = re[a]; re[a] = re[b]; re[b] = t;
      t = im[a]; im[a] = im[b]; im[b] = t;
    }
  }
  const sg = inv ? 1 : -1;
  for (let len = 2; len <= n; len <<= 1) {
    const half = len >> 1, step = n / len;
    for (let i = 0; i < n; i += len) {
      for (let k = 0; k < half; k++) {
        const cr = cos[k * step], ci = sg * sin[k * step];
        const a = off + (i + k) * s, b = a + half * s;
        const xr = re[b] * cr - im[b] * ci, xi = re[b] * ci + im[b] * cr;
        re[b] = re[a] - xr; im[b] = im[a] - xi; re[a] += xr; im[a] += xi;
      }
    }
  }
}

function fft2(re, im, w, h, inv) {
  for (let y = 0; y < h; y++) fft1(re, im, y * w, w, 1, inv);
  for (let x = 0; x < w; x++) fft1(re, im, x, h, w, inv);
  if (inv) { const k = 1 / (w * h); for (let i = 0; i < re.length; i++) { re[i] *= k; im[i] *= k; } }
}

const pow2 = (n) => { let p = 1; while (p < n) p <<= 1; return p; };

/* The page as a grid of cells, and the fields a voids cost scores against. Correlations run
   on a power-of-two grid; a spot whose footprint would wrap is outside the page anyway. */
class Board {
  constructor(page) {
    this.page = page;
    this.gw = page.gw; this.gh = page.gh;
    this.pw = pow2(this.gw); this.ph = pow2(this.gh);
    this.occ = new Uint8Array(this.gw * this.gh);
    // the outside of the margins is solid, as Fugleramme's page edge is
    for (let y = 0; y < this.gh; y++) for (let x = 0; x < this.gw; x++) if (x < page.mx || y < page.my || x >= this.gw - page.mx || y >= this.gh - page.my) this.occ[y * this.gw + x] = 1;
    // a gaussian as three box blurs, each this many cells either side
    this.r = Math.max(1, Math.round((Math.sqrt((12 * F_SIGMA * F_SIGMA) / 3 + 1) - 1) / 2));
    this.share = this.blur((x, y) => (this.inside(x, y) ? 1 : 0));
  }
  inside(x, y) { const p = this.page; return x >= p.mx && y >= p.my && x < this.gw - p.mx && y < this.gh - p.my; }
  /* ``at`` over the grid blurred to about a gaussian of F_SIGMA cells, outside the grid counted
     as solid. */
  blur(at) {
    const { gw, gh, r } = this;
    let a = new Float64Array(gw * gh), b = new Float64Array(gw * gh);
    for (let y = 0; y < gh; y++) for (let x = 0; x < gw; x++) a[y * gw + x] = at(x, y);
    const k = 1 / (2 * r + 1);
    for (let pass = 0; pass < 3; pass++) {
      for (let y = 0; y < gh; y++) {
        const o = y * gw;
        let s = 0;
        for (let x = 0; x <= Math.min(r, gw - 1); x++) s += a[o + x];
        for (let x = 0; x < gw; x++) {
          b[o + x] = s * k;
          if (x + r + 1 < gw) s += a[o + x + r + 1];
          if (x - r >= 0) s -= a[o + x - r];
        }
      }
      for (let x = 0; x < gw; x++) {
        let s = 0;
        for (let y = 0; y <= Math.min(r, gh - 1); y++) s += b[y * gw + x];
        for (let y = 0; y < gh; y++) {
          a[y * gw + x] = s * k;
          if (y + r + 1 < gh) s += b[(y + r + 1) * gw + x];
          if (y - r >= 0) s -= b[(y - r) * gw + x];
        }
      }
    }
    return a;
  }
  /* How empty the paper is round each cell, as a share of the page within reach. */
  emptiness() {
    const free = this.blur((x, y) => (this.occ[y * this.gw + x] ? 0 : 1));
    for (let i = 0; i < free.length; i++) free[i] /= Math.max(this.share[i], 1e-6);
    return free;
  }
  /* The free cells touching something solid; the margins count, so a corner scores like a neighbour. */
  halo() {
    const { gw, gh, occ } = this;
    const out = new Float64Array(gw * gh);
    for (let y = 0; y < gh; y++) for (let x = 0; x < gw; x++) {
      if (occ[y * gw + x]) continue;
      const s = (xx, yy) => xx < 0 || yy < 0 || xx >= gw || yy >= gh || occ[yy * gw + xx];
      if (s(x - 1, y) || s(x + 1, y) || s(x, y - 1) || s(x, y + 1)) out[y * gw + x] = 1;
    }
    return out;
  }
  /* The sums over the footprint of two fields at every offset at once, by one transform: the
     fields go in as the real and imaginary parts, and since the footprint is real the two
     correlations come back apart in the same two parts. */
  correlate(fa, fb, f) {
    const { gw, gh, pw, ph } = this;
    if (!this.buf) this.buf = Array.from({ length: 4 }, () => new Float64Array(pw * ph));
    const [mr, mi, re, im] = this.buf;
    mr.fill(0); mi.fill(0); re.fill(0); im.fill(0);
    for (const k of f.cells) { const y = (k / f.fw) | 0, x = k - y * f.fw; mr[y * pw + x] = 1; }
    fft2(mr, mi, pw, ph, false);
    for (let y = 0; y < gh; y++) for (let x = 0; x < gw; x++) { re[y * pw + x] = fa[y * gw + x]; im[y * pw + x] = fb[y * gw + x]; }
    fft2(re, im, pw, ph, false);
    for (let i = 0; i < re.length; i++) { const a = re[i], b = im[i]; re[i] = a * mr[i] + b * mi[i]; im[i] = b * mr[i] - a * mi[i]; }
    fft2(re, im, pw, ph, true);
    return [re, im];
  }
  /* The cheapest legal spot for ``f``, or null when there is none. */
  best(f) {
    const { gw, gh, pw } = this;
    if (f.fw > gw || f.fh > gh) return null;
    const empty = this.emptiness(), halo = this.halo();
    const area = Math.max(1, f.area);
    const field = new Float64Array(gw * gh);
    for (let i = 0; i < field.length; i++) field[i] = -empty[i] / area - (F_CLING * halo[i]) / Math.sqrt(area);
    const [clash, cost] = this.correlate(this.occ, field, f);
    let bx = -1, by = -1, bc = Infinity;
    for (let y = 0; y + f.fh <= gh; y++) for (let x = 0; x + f.fw <= gw; x++) {
      if (clash[y * pw + x] >= 0.5) continue;
      const c = cost[y * pw + x] + F_PULL * Math.hypot(y + f.fh / 2 - gh / 2, x + f.fw / 2 - gw / 2);
      if (c < bc) { bc = c; bx = x; by = y; }
    }
    return bx < 0 ? null : [bx, by];
  }
}

function placeFugleramme(page, items, unit, packer, facing) {
  const placed = [];
  if (packer === 'voids') {
    const board = new Board(page);
    for (const it of items) {
      const scale = Math.min(unit * it.factor, page.top / Math.max(it.mask.w, it.mask.h));
      const f = solid(page.foot(it, scale, it._flip));
      const spot = board.best(f);
      if (!spot) return null;
      take(board.occ, board.gw, spot[0], spot[1], f);
      placed.push({ it, x: spot[0], y: spot[1], f, scale });
    }
    return centred(page, placed);
  }
  const occ = new Uint8Array(page.gw * page.gh);
  for (const it of items) {
    const scale = Math.min(unit * it.factor, page.top / Math.max(it.mask.w, it.mask.h));
    const f = solid(page.foot(it, scale, it._flip));
    const spot = firstFree(page, occ, f);
    if (!spot) return null;
    take(occ, page.gw, spot[0], spot[1], f);
    placed.push({ it, x: spot[0], y: spot[1], f, scale });
  }
  return centred(page, placed);
}

/* The cluster's bounding box centred on the page. */
function centred(page, placed) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const p of placed) { x0 = Math.min(x0, p.x); y0 = Math.min(y0, p.y); x1 = Math.max(x1, p.x + p.f.fw); y1 = Math.max(y1, p.y + p.f.fh); }
  const dx = Math.round((page.gw - (x1 - x0)) / 2 - x0), dy = Math.round((page.gh - (y1 - y0)) / 2 - y0);
  for (const p of placed) { p.x += dx; p.y += dy; }
  return placed;
}

/* Shrink from an overshoot until everything fits, then bisect toward the size that failed. */
function sizeFugleramme(page, items, u0, packer, facing) {
  let fit = null, unit = u0, failed = null;
  for (let step = 0; step < F_ATTEMPTS; step++) {
    unit = u0 * F_SHRINK ** step;
    fit = placeFugleramme(page, items, unit, packer, facing);
    if (fit) break;
    failed = unit;
  }
  if (!fit || failed === null) return fit;
  let small = unit, large = failed;
  for (let i = 0; i < F_REFINE[packer]; i++) {
    const mid = (small + large) / 2;
    const got = placeFugleramme(page, items, mid, packer, facing);
    if (got) { fit = got; small = mid; } else large = mid;
  }
  return fit;
}

/* Voids packs on a page whose grid fits a 256-cell transform, and the result is scaled back. */
const VOIDS_CELLS = 256;

function packFugleramme(items, W, H, label, packer, facing) {
  const k = packer === 'voids' ? Math.min(1, ((VOIDS_CELLS - 1) * CELL) / Math.max(W, H)) : 1;
  if (k < 1) {
    const got = packFugleramme(items, W * k, H * k, label, packer === 'voids' ? 'voids-scaled' : packer, facing);
    return got.map((p) => p && { ...p, x: p.x / k, y: p.y / k, w: p.w / k, h: p.h / k, cap: [p.cap[0] / k, p.cap[1] / k] });
  }
  if (packer === 'voids-scaled') packer = 'voids';
  const px = label * H;
  const plan = items.map((it) => captionPlan(it.lines, label, items.length));
  const page = new Page(W, H, 0, px, TOP * Math.min(W, H));
  const order = items
    .map((it, i) => ({ it: { ...it, _fp: null, lines: plan[i], _flip: it.flippable && facing !== 'painted' ? nameFlip(it) : false }, i }))
    .sort((a, b) => b.it.factor ** 2 * b.it.mask.w * b.it.mask.h - a.it.factor ** 2 * a.it.mask.w * a.it.mask.h);
  const its = order.map((o) => o.it);
  const room = (page.gw - 2 * page.mx) * (page.gh - 2 * page.my) * CELL * CELL;
  const area = its.reduce((s, it) => s + it.mask.w * it.mask.h * it.factor ** 2, 0);
  // Fugleramme's overshoot: the specimens' boxes at half again the page, to shrink from
  const u0 = Math.sqrt((1.5 * room) / Math.max(1, area));
  let got = sizeFugleramme(page, its, u0, packer, facing);
  if (!got) {
    // specimens beat blank paper: without captions
    for (const it of its) { it.lines = []; it._fp = null; }
    got = sizeFugleramme(page, its, u0, packer, facing);
    if (!got) return items.map(() => null);
  }
  const out = items.map(() => null);
  for (const p of got) {
    const k = its.indexOf(p.it);
    const w = p.it.mask.w * p.scale, h = p.it.mask.h * p.scale;
    const bx = (p.x + p.f.off + p.f.tw / 2) * CELL, by = (p.y + p.f.top + p.f.th / 2) * CELL;
    const x = bx - w / 2, y = by - h / 2;
    out[order[k].i] = { x, y, w, h, flip: p.f.flip, cap: [x + w / 2, (p.y + p.f.lt) * CELL], lines: p.it.lines };
  }
  return out;
}
