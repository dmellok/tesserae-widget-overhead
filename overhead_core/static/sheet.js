/* The specimen sheet, built in the render browser or in a worker: each specimen's picture is
   cut out (cut.js), the cut-outs are packed onto one page (pack.js), and the page comes back as
   one JPEG with each specimen's box, caption anchor and caption lines as fractions of the page.
   A specimen with no picture yet is packed as an empty mount of about the size it will take. */
import { IN_WORKER, canvas, cutout, faceOf, fromAlpha, inkOf, loadImage, maskCanvas, mount, perchKept, toJpeg, vignette, whole } from './cut.js';
import { packSheet } from './pack.js';
export { captionPlan, wrapLabel } from './pack.js';

const PAPERS = { cream: [243, 234, 214], white: [255, 255, 255], aged: [233, 220, 192] };
const sheetSize = (ratio, size) => (ratio >= 1 ? [size, Math.round(size / ratio)] : [Math.round(size * ratio), size]);

function drawMount(ctx, x, y, w, h, ink, W) {
  ctx.save();
  ctx.strokeStyle = ink;
  ctx.globalAlpha = 0.45;
  ctx.lineWidth = Math.max(1, Math.round(W / 700));
  ctx.setLineDash([ctx.lineWidth * 3, ctx.lineWidth * 3]);
  ctx.beginPath();
  ctx.ellipse(x + w / 2, y + h / 2, w * 0.48, h * 0.48, 0, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();
}

/* Each specimen's spot on a W x H page: packed, or a cell each for the grid layout. ``zoom``
   under 1 packs into the middle that share of the page. */
function spots(items, W, H, label, { layout, facing, fast, zoom }) {
  if (layout === 'grid') return gridSpots(items, W, H, label);
  const k = Math.max(0.3, Math.min(1, Number(zoom) || 1));
  const w = W * k, h = H * k;
  const got = packSheet(items, w, h, label / k, { facing, fast });
  if (k === 1) return got;
  const dx = (W - w) / 2, dy = (H - h) / 2;
  return got.map((s) => s && { ...s, x: s.x + dx, y: s.y + dy, cap: [s.cap[0] + dx, s.cap[1] + dy] });
}

function gridSpots(items, W, H, label) {
  const n = items.length;
  const cols = Math.max(1, Math.min(n, Math.round(Math.sqrt((n * W) / H)) || 1));
  const rows = Math.ceil(n / cols);
  const cw = W / cols, ch = H / rows, cap = label * H * 1.3;
  return items.map((it, i) => {
    const lines = it.lines && it.lines.length ? [String(it.lines[0])] : [];
    const aw = cw * 0.84, ah = ch - cap * (lines.length + 0.6);
    const scale = Math.max(0.001, Math.min(aw / it.mask.w, ah / it.mask.h));
    const w = it.mask.w * scale, h = it.mask.h * scale;
    const x = (i % cols) * cw + (cw - w) / 2, y = Math.floor(i / cols) * ch + (ah - h) / 2 + cap * 0.3;
    return { x, y, w, h, flip: false, cap: [x + w / 2, y + h + cap * 0.1], lines };
  });
}

function draw(items, placed, W, H, paper, ink) {
  const bg = PAPERS[paper] || PAPERS.cream;
  const sheet = canvas(W, H);
  const ctx = sheet.getContext('2d');
  ctx.fillStyle = `rgb(${bg.join(',')})`;
  ctx.fillRect(0, 0, W, H);
  const shown = [], slots = [];
  items.forEach((b, i) => {
    const s = placed[i];
    if (!s) return;
    const w = Math.max(1, Math.round(s.w)), h = Math.max(1, Math.round(s.h)), x = s.x, y = s.y;
    if (b.blend === 'mount') drawMount(ctx, x, y, w, h, ink, W);
    else {
      ctx.save();
      ctx.globalCompositeOperation = b.blend;
      if (s.flip) { ctx.translate(x + w, y); ctx.scale(-1, 1); ctx.drawImage(b.cut, 0, 0, w, h); } else ctx.drawImage(b.cut, x, y, w, h);
      ctx.restore();
    }
    slots[b.idx] = { x, y, w, h, on_paper: !!b.on_paper };
    shown.push({ name: b.name, sci: b.sci, mount: b.blend === 'mount', flip: !!s.flip, box: [x / W, y / H, w / W, h / H], at: [s.cap[0] / W, s.cap[1] / H], lines: s.lines });
  });
  return { sheet, shown, slots, paper: `rgb(${bg.join(',')})` };
}

/* The placeholder page, laid out at once from each specimen's aspect and factor as empty
   mounts, synchronous, so the page shows while the real sheet is built; ``slots`` gives each
   specimen's box by its index in ``specimens`` for drawIntoMount. */
export function quickSheet({ specimens, ratio, size, label, paper = 'cream', ink = '#2a2116', layout = 'cluster', facing = 'inward', zoom = 1 }) {
  const items = specimens.map((b, idx) => { const m = mount(Number(b.aspect) > 0 ? Number(b.aspect) : 0.8); return { ...b, ...m, idx, flippable: false, face: null }; });
  if (!items.length) return null;
  const [W, H] = sheetSize(ratio, size);
  const placed = spots(items, W, H, label, { layout, facing, fast: true, zoom });
  const d = draw(items, placed, W, H, paper, ink);
  if (!d.shown.length) return null;
  return { canvas: d.sheet, slots: d.slots, paper: d.paper, items: d.shown, ratio, label, w: W, h: H, quick: true };
}

/* A cut-out drawn into its placeholder mount, the dashed oval painted over with paper first. */
export function drawIntoMount(quick, i, pic, blend) {
  const slot = quick.slots[i];
  if (!slot || !quick.canvas) return;
  const ctx = quick.canvas.getContext('2d');
  const pw = pic.width || pic.naturalWidth, ph = pic.height || pic.naturalHeight;
  if (!pw || !ph) return;
  const k = Math.min(slot.w / pw, slot.h / ph);
  const w = pw * k, h = ph * k, x = slot.x + (slot.w - w) / 2, y = slot.y + (slot.h - h) / 2;
  ctx.save();
  ctx.fillStyle = quick.paper;
  ctx.fillRect(slot.x - 2, slot.y - 2, slot.w + 4, slot.h + 4);
  ctx.globalCompositeOperation = blend === 'multiply' ? 'multiply' : 'source-over';
  ctx.drawImage(pic, x, y, w, h);
  ctx.restore();
}

/* The page. ``specimens``: [{ name, sci, src, cut, on_paper, classic, whole, paper, neutral,
   factor, aspect, lines }]; ``src`` the picture (null for a mount), ``cut`` a PNG with alpha when
   one arrived. Returns null when nothing could be placed. */
export async function buildSheet({ specimens, ratio, size, label, paper = 'cream', ink = '#2a2116', layout = 'cluster', facing = 'inward', zoom = 1, onCut = null }) {
  const loaded = await Promise.all(specimens.map(async (b, idx) => {
    try {
      let got = null, byEdges = false, model = null;
      if (b.whole && b.src) got = whole(await loadImage(b.src));
      else if (b.cut) {
        const cutImg = await loadImage(b.cut);
        got = fromAlpha(cutImg, b.neutral && b.on_paper ? b.paper : null);
        // a cut-out with next to nothing opaque in it (a mask that missed the subject) is no
        // cut-out: the picture is cut by its edges or shown as a soft oval instead
        if (got && inkOf(got) < 0.01 * got.mask.w * got.mask.h) got = null;
        if (got && !b.on_paper && !b.classic) got.blend = 'source-over';
        if (got && !b.classic) model = cutImg;
      }
      if (!b.whole && b.src && b.on_paper) {
        // a plate or painting on plain paper is cut by its edges when that keeps the perch
        const edge = cutout(await loadImage(b.src), model);
        if (perchKept(edge)) { got = edge; byEdges = true; }
      }
      if (!got && b.src) got = vignette(await loadImage(b.src));
      if (!got) got = mount(0.8);
      if (onCut && got.blend !== 'mount') { try { await onCut(idx, got.cut, got.blend); } catch { /* the page may have moved on */ } }
      // a plate cut by its edges may carry lettering, so it is never mirrored
      const flippable = !b.no_flip && got.blend !== 'mount' && !byEdges && !b.whole && (!!b.cut || !b.on_paper);  // an aircraft carries lettering: never mirrored
      return { ...b, ...got, idx, flippable, face: flippable ? faceOf(got.mask) : null };
    } catch { return { ...b, ...mount(0.8), idx, flippable: false, face: null }; }
  }));
  if (!loaded.length) return null;
  const [W, H] = sheetSize(ratio, size);
  const placed = spots(loaded, W, H, label, { layout, facing, fast: false, zoom });
  const d = draw(loaded, placed, W, H, paper, ink);
  if (!d.shown.length) return null;
  void maskCanvas;
  return { src: await toJpeg(d.sheet), items: d.shown, paper: d.paper, ratio, label, w: W, h: H };
}

/* As a worker: one message in with buildSheet's argument, one out with the result or the error. */
if (IN_WORKER) {
  self.onmessage = async (e) => {
    const onCut = async (i, cut, blend) => {
      const bitmap = await createImageBitmap(cut);
      self.postMessage({ kind: 'cut', i, bitmap, blend }, [bitmap]);
    };
    try { self.postMessage({ ok: true, sheet: await buildSheet({ ...e.data, onCut }) }); }
    catch (err) { self.postMessage({ ok: false, error: String(err && err.message || err) }); }
  };
}
