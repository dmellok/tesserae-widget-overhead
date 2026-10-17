/* Pictures into cut-outs, in the page or in a worker: a plate or painting on plain paper is
   cut by spreading in from the edges (cutout), a picture that arrived with alpha by its alpha
   (fromAlpha), a photo as a soft vignette (vignette), a picture still to come as an empty mount
   (mount), and a whole-object painting kept entire (whole). Each returns { cut, mask, blend }:
   the drawable cut-out, its outline as a 0/1 mask, and how it prints on paper. */

/* The packer runs the same in the page and in a worker (client.js starts
   one when it can, so the page stays responsive while the sheet is built);
   in a worker a picture is an ImageBitmap and a canvas an OffscreenCanvas. */
export const IN_WORKER = typeof WorkerGlobalScope !== 'undefined' && typeof self !== 'undefined' && self instanceof WorkerGlobalScope;

export function loadImage(src) {
  if (IN_WORKER) {
    return fetch(src).then((r) => { if (!r.ok) throw new Error('picture would not load'); return r.blob(); }).then((b) => createImageBitmap(b)).then((bm) => {
      bm.naturalWidth = bm.width; bm.naturalHeight = bm.height; return bm;
    });
  }
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('picture would not decode'));
    img.src = src;
  });
}

export function canvas(w, h) {
  const cw = Math.max(1, Math.round(w)), ch = Math.max(1, Math.round(h));
  if (IN_WORKER) return new OffscreenCanvas(cw, ch);
  const c = document.createElement('canvas');
  c.width = cw;
  c.height = ch;
  return c;
}

/* The finished sheet as a JPEG data URL, from either kind of canvas. */
export async function toJpeg(c) {
  if (!IN_WORKER) return c.toDataURL('image/jpeg', 0.9);
  const blob = await c.convertToBlob({ type: 'image/jpeg', quality: 0.9 });
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let s = '';
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return `data:image/jpeg;base64,${btoa(s)}`;
}

function median(values) {
  const a = Float64Array.from(values).sort();
  return a.length ? a[a.length >> 1] : 0;
}

/* A box blur of radius r on a float grid, run twice to come near a Gaussian. */
function boxBlur(src, w, h, r, passes = 1) {
  let a = Float32Array.from(src);
  const b = new Float32Array(w * h);
  for (let p = 0; p < passes; p++) {
    for (let y = 0; y < h; y++) {
      let sum = 0, n = 0;
      for (let x = -r; x <= r; x++) { const xx = Math.min(w - 1, Math.max(0, x)); sum += a[y * w + xx]; n++; }
      for (let x = 0; x < w; x++) {
        b[y * w + x] = sum / n;
        const out = x - r, inn = x + r + 1;
        sum += a[y * w + Math.min(w - 1, inn)] - a[y * w + Math.max(0, out)];
      }
    }
    for (let x = 0; x < w; x++) {
      let sum = 0, n = 0;
      for (let y = -r; y <= r; y++) { const yy = Math.min(h - 1, Math.max(0, y)); sum += b[yy * w + x]; n++; }
      for (let y = 0; y < h; y++) {
        a[y * w + x] = sum / n;
        const out = y - r, inn = y + r + 1;
        sum += b[Math.min(h - 1, inn) * w + x] - b[Math.max(0, out) * w + x];
      }
    }
  }
  return a;
}

export function dilate(m, w, h, r) {
  const out = new Uint8Array(w * h);
  const row = new Uint8Array(w * h);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    let v = 0;
    for (let k = -r; k <= r && !v; k++) { const xx = x + k; if (xx >= 0 && xx < w && m[y * w + xx]) v = 1; }
    row[y * w + x] = v;
  }
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    let v = 0;
    for (let k = -r; k <= r && !v; k++) { const yy = y + k; if (yy >= 0 && yy < h && row[yy * w + x]) v = 1; }
    out[y * w + x] = v;
  }
  return out;
}
function erode(m, w, h, r) {
  const inv = new Uint8Array(w * h);
  for (let i = 0; i < inv.length; i++) inv[i] = m[i] ? 0 : 1;
  const d = dilate(inv, w, h, r);
  const out = new Uint8Array(w * h);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const edge = x < r || y < r || x >= w - r || y >= h - r;
    out[y * w + x] = d[y * w + x] || edge ? 0 : 1;
  }
  return out;
}

/* The paper, found by spreading in from the edges over anything that looks
   like paper; what the spread cannot reach is the specimen. */
function paperMask(data, sw, sh, paper) {
  const n = sw * sh;
  const L = new Float32Array(n), diff = new Uint8Array(n), sat = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    const r = data[i * 4], g = data[i * 4 + 1], b = data[i * 4 + 2];
    L[i] = 0.299 * r + 0.587 * g + 0.114 * b;
    diff[i] = Math.max(Math.abs(r - paper[0]), Math.abs(g - paper[1]), Math.abs(b - paper[2]));
    sat[i] = Math.max(r, g, b) - Math.min(r, g, b);
  }
  const blur = boxBlur(L, sw, sh, 2, 2);
  const hp = new Float32Array(n);
  for (let i = 0; i < n; i++) hp[i] = Math.min(255, Math.abs(L[i] - blur[i]) * 8);
  const texture = boxBlur(hp, sw, sh, 2, 1);
  const paperL = 0.299 * paper[0] + 0.587 * paper[1] + 0.114 * paper[2];
  const paperlike = new Uint8Array(n), washlike = new Uint8Array(n), cand = new Uint8Array(n), edge = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    paperlike[i] = diff[i] < 24 ? 1 : 0;
    washlike[i] = texture[i] < 24 && sat[i] < 26 && L[i] > paperL - 95 ? 1 : 0;
    cand[i] = paperlike[i] | washlike[i];
    edge[i] = sat[i] < 26 && L[i] > paperL - 95 ? 1 : 0;
  }
  const bg = new Uint8Array(n);
  const stack = [];
  const seed = (i) => { if (cand[i] && !bg[i]) { bg[i] = 1; stack.push(i); } };
  for (let x = 0; x < sw; x++) { seed(x); seed((sh - 1) * sw + x); }
  for (let y = 0; y < sh; y++) { seed(y * sw); seed(y * sw + sw - 1); }
  while (stack.length) {
    const i = stack.pop();
    const x = i % sw, y = (i - x) / sw;
    if (x > 0) seed(i - 1);
    if (x < sw - 1) seed(i + 1);
    if (y > 0) seed(i - sw);
    if (y < sh - 1) seed(i + sw);
  }
  let reach = new Uint8Array(n);
  for (let i = 0; i < n; i++) reach[i] = bg[i] && washlike[i] && !paperlike[i] ? 1 : 0;
  for (let k = 0; k < 8; k++) {
    const grown = dilate(reach, sw, sh, 1);
    for (let i = 0; i < n; i++) grown[i] = grown[i] && (edge[i] || bg[i]) ? 1 : 0;
    reach = grown;
  }
  let obj = new Uint8Array(n);
  for (let i = 0; i < n; i++) obj[i] = bg[i] || reach[i] ? 0 : 1;
  obj = dilate(erode(obj, sw, sh, 1), sw, sh, 2);
  return obj;
}

export function bbox(m, w, h) {
  let x0 = w, y0 = h, x1 = -1, y1 = -1;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (m[y * w + x]) {
    if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
  }
  return x1 < 0 ? null : [x0, y0, x1 + 1, y1 + 1];
}

/* A picture on plain paper, cut out: the specimen cropped with the paper
   turned white; its hard mask; the paper colour. Printed by multiply. */
export function cutout(img, model = null) {
  const k0 = Math.min(1, 1000 / Math.max(img.naturalWidth, img.naturalHeight));
  const cw = Math.max(1, Math.round(img.naturalWidth * k0)), ch = Math.max(1, Math.round(img.naturalHeight * k0));
  const full = canvas(cw, ch);
  const fctx = full.getContext('2d', { willReadFrequently: true });
  fctx.drawImage(img, 0, 0, cw, ch);
  const px = fctx.getImageData(0, 0, cw, ch).data;
  const b = Math.max(2, Math.floor(Math.min(cw, ch) / 40));
  const samples = [[], [], []];
  const step = Math.max(1, Math.floor((cw * b * 2) / 4000));
  for (let y = 0; y < ch; y++) {
    if (y >= b && y < ch - b) continue;
    for (let x = 0; x < cw; x += step) { const i = (y * cw + x) * 4; samples[0].push(px[i]); samples[1].push(px[i + 1]); samples[2].push(px[i + 2]); }
  }
  const paper = samples.map((s) => Math.round(median(s)));
  const k = Math.min(1, 320 / Math.max(cw, ch));
  const sw = Math.max(1, Math.round(cw * k)), sh = Math.max(1, Math.round(ch * k));
  const small = canvas(sw, sh);
  const sctx = small.getContext('2d', { willReadFrequently: true });
  sctx.drawImage(full, 0, 0, sw, sh);
  const sd = sctx.getImageData(0, 0, sw, sh).data;
  const sm = paperMask(sd, sw, sh, paper);
  // A white bird on white paper is what the spread takes for paper, so a model's mask that
  // passed its check is added: what it kept is never given up, and the edges still add the
  // perch and the foliage it left out.
  if (model) {
    const mc = canvas(sw, sh);
    const mctx = mc.getContext('2d', { willReadFrequently: true });
    mctx.drawImage(model, 0, 0, sw, sh);
    const md = mctx.getImageData(0, 0, sw, sh).data;
    const kept = new Uint8Array(sw * sh);
    for (let i = 0; i < sw * sh; i++) kept[i] = md[i * 4 + 3] > 127 ? 1 : 0;
    const grown = dilate(kept, sw, sh, 1);
    for (let i = 0; i < sw * sh; i++) if (grown[i]) sm[i] = 1;
  }
  dropShadows(sm, sd, sw, sh, paper);
  let box = bbox(erode(sm, sw, sh, 3), sw, sh) || bbox(sm, sw, sh);
  if (!box) return null;
  const pad = Math.max(cw, ch) / 60;
  box = [Math.max(0, Math.floor(box[0] / k - pad)), Math.max(0, Math.floor(box[1] / k - pad)), Math.min(cw, Math.ceil(box[2] / k + pad)), Math.min(ch, Math.ceil(box[3] / k + pad))];
  const bw = box[2] - box[0], bh = box[3] - box[1];
  if (bw < 2 || bh < 2) return null;
  const hard = new Uint8Array(bw * bh);
  for (let y = 0; y < bh; y++) for (let x = 0; x < bw; x++) {
    const sx = Math.min(sw - 1, Math.floor((box[0] + x) * k)), sy = Math.min(sh - 1, Math.floor((box[1] + y) * k));
    hard[y * bw + x] = sm[sy * sw + sx];
  }
  const soft = boxBlur(Float32Array.from(hard), bw, bh, 2, 2);
  const cut = canvas(bw, bh);
  const cctx = cut.getContext('2d');
  const out = cctx.createImageData(bw, bh);
  const lut = paper.map((c) => { const t = new Uint8Array(256); for (let i = 0; i < 256; i++) t[i] = Math.min(255, Math.round(i * 255 / Math.max(1, c))); return t; });
  for (let y = 0; y < bh; y++) for (let x = 0; x < bw; x++) {
    const i = ((box[1] + y) * cw + box[0] + x) * 4, o = (y * bw + x) * 4;
    const m = Math.min(1, Math.max(0, soft[y * bw + x]));
    out.data[o] = Math.round(lut[0][px[i]] * m + 255 * (1 - m));
    out.data[o + 1] = Math.round(lut[1][px[i + 1]] * m + 255 * (1 - m));
    out.data[o + 2] = Math.round(lut[2][px[i + 2]] * m + 255 * (1 - m));
    out.data[o + 3] = 255;
  }
  cctx.putImageData(out, 0, 0);
  return { cut, mask: { w: bw, h: bh, data: hard }, paper, blend: 'multiply', box, frame: [cw, ch] };
}

/* The soft shadow a painting leaves under its subject: smooth, a neutral darkening of
   the paper (it is not drawn, only cast), and open to the paper at its outer edge. The
   paper spread takes it for part of the specimen, and printed by multiply it shows as a
   grey smudge, so what it reaches is dropped from the mask, a model's included. The
   spread stops at the drawing's own outline (never smooth), so a pale patch the outline
   encloses, a white bird's breast, is kept. */
function dropShadows(sm, sd, sw, sh, paper) {
  const n = sw * sh;
  const L = new Float32Array(n);
  for (let i = 0; i < n; i++) L[i] = 0.299 * sd[i * 4] + 0.587 * sd[i * 4 + 1] + 0.114 * sd[i * 4 + 2];
  const blur = boxBlur(L, sw, sh, 2, 2);
  const hp = new Float32Array(n);
  for (let i = 0; i < n; i++) hp[i] = Math.min(255, Math.abs(L[i] - blur[i]) * 8);
  const texture = boxBlur(hp, sw, sh, 2, 1);
  const cand = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    if (!sm[i]) continue;
    const rc = [sd[i * 4] / paper[0], sd[i * 4 + 1] / paper[1], sd[i * 4 + 2] / paper[2]];
    const mean = (rc[0] + rc[1] + rc[2]) / 3;
    const spread = Math.max(...rc) - Math.min(...rc);
    if (mean > 0.7 && mean < 0.985 && spread < 0.07 && texture[i] < 18) cand[i] = mean < 0.93 ? 2 : 1;
  }
  const drop = new Uint8Array(n);
  const stack = [];
  const open = (i) => {
    const x = i % sw, y = (i - x) / sw;
    return x === 0 || y === 0 || x === sw - 1 || y === sh - 1 || !sm[i - 1] || !sm[i + 1] || !sm[i - sw] || !sm[i + sw];
  };
  // the shadow proper (clearly darker than paper) is followed from the open edge; its faint
  // fringe (barely darker, which a white bird's own plumage also is) only a few steps out
  for (let i = 0; i < n; i++) if (cand[i] === 2 && open(i)) { drop[i] = 1; stack.push(i); }
  while (stack.length) {
    const i = stack.pop();
    const x = i % sw, y = (i - x) / sw;
    const go = (j) => { if (cand[j] === 2 && !drop[j]) { drop[j] = 1; stack.push(j); } };
    if (x > 0) go(i - 1);
    if (x < sw - 1) go(i + 1);
    if (y > 0) go(i - sw);
    if (y < sh - 1) go(i + sw);
  }
  for (let step = 0; step < 5; step++) {
    const next = dilate(drop, sw, sh, 1);
    for (let i = 0; i < n; i++) if (next[i] && !drop[i] && cand[i]) drop[i] = 1;
  }
  for (let i = 0; i < n; i++) if (drop[i]) sm[i] = 0;
}

/* How much of a cut-out is drawing, in pixels of its mask. */
export function inkOf(got) { let n = 0; const d = got.mask.data; for (let i = 0; i < d.length; i++) n += d[i]; return n; }

/* Whether a picture on plain paper is to be cut by its edges rather than by
   the model's mask. The model keeps the bird and drops the branch it sits
   on, the foliage round it, the log a fungus grows from, all of which are
   the drawing; the edge cut keeps everything drawn on the paper. So a plate
   or painting is cut by its edges whenever the paper was plain enough to
   find: the cut is well under the whole frame, not just specks, and does
   not fill its own box the way a painted background wash does (a bird on a
   branch fills well under three quarters of its box; a plate with a sky
   behind the bird fills nearly all of it). An aged, textured or vignetted
   plate fails this and keeps the model's mask. */
export function perchKept(edge) {
  if (!edge) return false;
  const [fw, fh] = edge.frame;
  const edgeInk = inkOf(edge);
  if (edgeInk >= 0.8 * fw * fh || edgeInk <= 0.01 * fw * fh) return false;
  // the mask closed (blurred and thresholded) so a speckled wash reads as the
  // solid block it is, then its share of the cut's own box
  const { w, h, data } = edge.mask;
  const r = Math.max(2, Math.round(Math.max(w, h) / 80));
  const soft = boxBlur(Float32Array.from(data), w, h, r, 2);
  let filled = 0;
  for (let i = 0; i < soft.length; i++) if (soft[i] > 0.2) filled++;
  return filled < 0.72 * w * h;
}

/* A picture that arrived already cut out (a PNG with alpha): its alpha is
   the mask and nothing is guessed; the alpha travels with the cut, so a
   plate prints by multiply and a photo over the paper. */
export function fromAlpha(img, paper = null) {
  const k0 = Math.min(1, 1000 / Math.max(img.naturalWidth, img.naturalHeight));
  const cw = Math.max(1, Math.round(img.naturalWidth * k0)), ch = Math.max(1, Math.round(img.naturalHeight * k0));
  const full = canvas(cw, ch);
  const fctx = full.getContext('2d', { willReadFrequently: true });
  fctx.drawImage(img, 0, 0, cw, ch);
  const px = fctx.getImageData(0, 0, cw, ch).data;
  const hardFull = new Uint8Array(cw * ch);
  for (let i = 0; i < cw * ch; i++) hardFull[i] = px[i * 4 + 3] > 127 ? 1 : 0;
  let box = bbox(hardFull, cw, ch);
  if (!box) return null;
  const pad = Math.max(cw, ch) / 60;
  box = [Math.max(0, Math.floor(box[0] - pad)), Math.max(0, Math.floor(box[1] - pad)), Math.min(cw, Math.ceil(box[2] + pad)), Math.min(ch, Math.ceil(box[3] + pad))];
  const bw = box[2] - box[0], bh = box[3] - box[1];
  if (bw < 2 || bh < 2) return null;
  const hard = new Uint8Array(bw * bh);
  const cut = canvas(bw, bh);
  const cctx = cut.getContext('2d');
  const out = cctx.createImageData(bw, bh);
  // the picture's own paper scaled to white, so a cream wash under a bird does not tint the sheet
  const lut = paper ? paper.map((c) => { const t = new Uint8Array(256); for (let i = 0; i < 256; i++) t[i] = Math.min(255, Math.round(i * 255 / Math.max(1, c))); return t; }) : null;
  for (let y = 0; y < bh; y++) for (let x = 0; x < bw; x++) {
    const i = ((box[1] + y) * cw + box[0] + x) * 4, o = (y * bw + x) * 4;
    const a = px[i + 3] / 255;
    hard[y * bw + x] = a > 0.5 ? 1 : 0;
    out.data[o] = lut ? lut[0][px[i]] : px[i];
    out.data[o + 1] = lut ? lut[1][px[i + 1]] : px[i + 1];
    out.data[o + 2] = lut ? lut[2][px[i + 2]] : px[i + 2];
    out.data[o + 3] = px[i + 3];
  }
  cctx.putImageData(out, 0, 0);
  return { cut, mask: { w: bw, h: bh, data: hard }, paper: [255, 255, 255], blend: 'multiply', box, frame: [cw, ch] };
}

/* A photo as a soft oval vignette: an ellipse inscribed in the picture,
   feathered at the edge, so it reads as a mounted print rather than a
   pasted rectangle. Printed as it is, with its alpha. */
export function vignette(img) {
  const k0 = Math.min(1, 900 / Math.max(img.naturalWidth, img.naturalHeight));
  const w = Math.max(2, Math.round(img.naturalWidth * k0)), h = Math.max(2, Math.round(img.naturalHeight * k0));
  const cut = canvas(w, h);
  const ctx = cut.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(img, 0, 0, w, h);
  const id = ctx.getImageData(0, 0, w, h);
  const hard = new Uint8Array(w * h);
  const cx = w / 2, cy = h / 2, rx = w * 0.47, ry = h * 0.47;
  const feather = Math.max(4, Math.min(w, h) * 0.07);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const dx = (x + 0.5 - cx) / rx, dy = (y + 0.5 - cy) / ry;
    const d = Math.sqrt(dx * dx + dy * dy); // 1 at the ellipse's edge
    // distance to the edge in pixels, roughly, along the shorter radius
    const px = (1 - d) * Math.min(rx, ry);
    const a = Math.min(1, Math.max(0, px / feather));
    id.data[(y * w + x) * 4 + 3] = Math.round(255 * a);
    hard[y * w + x] = a > 0.5 ? 1 : 0;
  }
  ctx.putImageData(id, 0, 0);
  return { cut, mask: { w, h, data: hard }, paper: [255, 255, 255], blend: 'source-over' };
}

/* An empty mount for a specimen with no picture yet: an oval of the size
   it will take, drawn as a dotted outline. */
export function mount(aspect = 0.8) {
  const w = Math.round(400 * aspect), h = 400;
  const hard = new Uint8Array(w * h);
  const cx = w / 2, cy = h / 2, rx = w * 0.48, ry = h * 0.48;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const dx = (x + 0.5 - cx) / rx, dy = (y + 0.5 - cy) / ry;
    hard[y * w + x] = dx * dx + dy * dy <= 1 ? 1 : 0;
  }
  return { cut: null, mask: { w, h, data: hard }, paper: [255, 255, 255], blend: 'mount' };
}

/* A mask as a canvas (white on black), for scaling. */
export function maskCanvas(mask) {
  const c = canvas(mask.w, mask.h);
  const ctx = c.getContext('2d');
  const id = ctx.createImageData(mask.w, mask.h);
  for (let i = 0; i < mask.data.length; i++) { const v = mask.data[i] ? 255 : 0; id.data[i * 4] = v; id.data[i * 4 + 1] = v; id.data[i * 4 + 2] = v; id.data[i * 4 + 3] = 255; }
  ctx.putImageData(id, 0, 0);
  return c;
}

/* Place cut-outs on a W x H page in an oval, biggest first, each with room
   under it for its label, then nudged inward until the group is tight.
   (x, y, scale) per specimen; scale 0 when one does not fit at all. */
/* ---------------- the packer ---------------- */

/* Which way a specimen faces, read from its mask: the head of a bird or an
   animal in profile sits in the top rows, off to one side of the body's
   centre. 'left', 'right', or null when the mask has no say (a plant, a
   fungus, a bird seen head-on). */
export function faceOf(mask) {
  const { w, h, data } = mask;
  let sx = 0, n = 0, hx = 0, hn = 0;
  const headRows = Math.max(1, Math.floor(h * 0.3));
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (data[y * w + x]) {
    sx += x; n++;
    if (y < headRows) { hx += x; hn++; }
  }
  if (!n || !hn) return null;
  const d = hx / hn - sx / n;
  if (Math.abs(d) < w * 0.03) return null;
  return d > 0 ? 'right' : 'left';
}


export function whole(img) {
  const k0 = Math.min(1, 1000 / Math.max(img.naturalWidth, img.naturalHeight));
  const w = Math.max(1, Math.round(img.naturalWidth * k0)), h = Math.max(1, Math.round(img.naturalHeight * k0));
  const c = canvas(w, h);
  c.getContext('2d').drawImage(img, 0, 0, w, h);
  return { cut: c, mask: { w, h, data: new Uint8Array(w * h).fill(1) }, paper: [255, 255, 255], blend: 'source-over', box: [0, 0, w, h], frame: [w, h] };
}
