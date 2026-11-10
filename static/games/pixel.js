/* Пиксель-мяу: раскраска по номерам. Картинки строятся из рисунков и эмодзи прямо в браузере. */
'use strict';
(() => {
const {INK} = Mya;
const PAL = ['#f6e2ff', '#ffffff', '#ffd457', '#ffab2e', '#ff7a8a', '#ff4fa3', '#a64dff', '#4a1838', '#22e0d0', '#4da6ff', '#9dff4a', '#3fae4a', '#8b5a2b', '#ff3b30', '#9aa0a6', '#2b2b2b'];
const PICS = [
  {id: 'cat', name: 'Котик', svg: () => Mya.catSVG(256)},
  {id: 'catb', name: 'Котик спиной', svg: () => Mya.catSVG(256, true)},
  {id: 'spool', name: 'Катушка', svg: () => Mya.spoolSVG('#ff4fa3')},
  {id: 'dino', name: 'Динозаврик', emoji: '🦖'}, {id: 'rocket', name: 'Ракета', emoji: '🚀'}, {id: 'donut', name: 'Пончик', emoji: '🍩'},
  {id: 'uni', name: 'Единорог', emoji: '🦄'}, {id: 'octo', name: 'Осьминог', emoji: '🐙'}, {id: 'straw', name: 'Клубника', emoji: '🍓'},
  {id: 'whale', name: 'Кит', emoji: '🐳'}, {id: 'rainbow', name: 'Радуга', emoji: '🌈'}, {id: 'fox', name: 'Лисёнок', emoji: '🦊'},
];
const SIZES = {s16: 16, s24: 24, s32: 32};
const doneSet = () => Mya.store.get('pixel.done', []);
const hex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
const PALRGB = PAL.map(hex);

Mya.games.pixel = {
  id: 'pixel', title: 'Пиксель-мяу',
  modes: [
    {id: 's16', name: '16×16', desc: 'Выбери цвет внизу и закрашивай клетки с его номером. Можно водить пальцем.'},
    {id: 's24', name: '24×24', desc: 'Картинка побольше и подробнее.'},
    {id: 's32', name: '32×32', desc: 'Для настоящих художников: много мелких клеток.'},
  ],
  controls: [{k: 'SAVE', l: '💾 Сохранить', wide: true}, {k: 'NEXT', l: '🖼 Другая', wide: true}],
  touchOnly: false,
  keys: 'Мышкой: выбери цвет и закрашивай · можно зажать и вести',
  hint: 'Прогресс каждой картинки сохраняется. Готовую можно скачать на устройство.',
  recordText() { const n = doneSet().length; return n ? `${n} картин` : '—'; },
  subText() { return `${PICS.length * 3} картинок`; },
  extra() {
    const cur = Mya.store.get('pixel.pic', 'cat'), done = doneSet();
    return `<div class="modes">${PICS.map(p => `<button class="chip ${p.id === cur ? 'on' : ''}" onclick="Mya.store.set('pixel.pic','${p.id}');this.parentNode.querySelectorAll('.chip').forEach(b=>b.classList.remove('on'));this.classList.add('on')">${p.emoji || '🐱'} ${p.name}${done.some(d => d.startsWith(p.id + '.')) ? ' ✔' : ''}</button>`).join('')}</div>`;
  },
  create(api) { return new Pixel(api); },
};

function build(pic, n, cb) {
  const c = document.createElement('canvas'); c.width = c.height = n; const g = c.getContext('2d');
  const finish = () => {
    const d = g.getImageData(0, 0, n, n).data, idx = [];
    for (let i = 0; i < n * n; i++) {
      if (d[i * 4 + 3] < 110) { idx.push(0); continue; }
      let best = 1, bd = 1e9; for (let k = 1; k < PAL.length; k++) { const [r, gg, b] = PALRGB[k], dd = (r - d[i * 4]) ** 2 * .3 + (gg - d[i * 4 + 1]) ** 2 * .59 + (b - d[i * 4 + 2]) ** 2 * .11; if (dd < bd) { bd = dd; best = k; } }
      idx.push(best);
    }
    const used = [0, ...[...new Set(idx)].filter(k => k).sort((a, b) => a - b)];
    cb({target: idx.map(k => used.indexOf(k)), colors: used.map(k => PAL[k])});
  };
  if (pic.emoji) {
    g.textAlign = 'center'; g.textBaseline = 'middle'; g.font = `${n * .9}px "Apple Color Emoji","Segoe UI Emoji","Noto Color Emoji",sans-serif`;
    g.fillText(pic.emoji, n / 2, n / 2 + n * .05); finish();
  } else {
    const im = new Image(); im.onload = () => { g.imageSmoothingEnabled = true; g.drawImage(im, n * .04, n * .04, n * .92, n * .92); finish(); };
    im.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(pic.svg());
  }
}

class Pixel {
  constructor(api) {
    this.api = api; this.cv = api.canvas; this.W = 0; this.H = 0; this.painting = false;
    this.onDown = e => { if (!api.running || !this.pic) return; const p = this.pt(e); if (this.palAt(p)) return; this.painting = true; this.paint(p); };
    this.onMove = e => { if (this.painting) this.paint(this.pt(e)); };
    this.onUp = () => { if (this.painting) { this.painting = false; this.save(); } };
    this.cv.addEventListener('pointerdown', this.onDown); this.cv.addEventListener('pointermove', this.onMove);
    window.addEventListener('pointerup', this.onUp);
    this.reset('s16');
  }
  destroy() { this.cv.removeEventListener('pointerdown', this.onDown); this.cv.removeEventListener('pointermove', this.onMove); window.removeEventListener('pointerup', this.onUp); }
  pt(e) { const r = this.cv.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; }
  resize(W, H) {
    this.W = W; this.H = H; if (!this.pic) return;
    const n = this.n, k = this.pic.colors.length - 1, perRow = Math.min(k, Math.max(5, Math.floor((W - 20) / 52)));
    this.palRows = Math.ceil(k / perRow); this.perRow = perRow;
    this.pr = Math.min(24, (W - 20) / perRow / 2 - 3);
    const palH = this.palRows * (this.pr * 2 + 10) + 16;
    this.cs = Math.floor(Math.min((W - 16) / n, (H - palH - 40) / n));
    this.gx = (W - this.cs * n) / 2; this.gy = 30 + (H - palH - 30 - this.cs * n) / 2;
    this.py = H - palH + 8;
  }
  reset(mode) {
    this.mode = mode; this.n = SIZES[mode]; this.picDef = PICS.find(p => p.id === Mya.store.get('pixel.pic', 'cat')) || PICS[0];
    this.key_ = `${this.picDef.id}.${this.n}`; this.pic = null; this.won = false; this.t = 0;
    build(this.picDef, this.n, pic => {
      this.pic = pic;
      const saved = Mya.store.get('pixel.p.' + this.key_, null);
      this.fill = saved && saved.length === this.n * this.n ? saved : pic.target.map(t => (t === 0 ? 0 : -1));
      this.sel = 1; this.pickNext(); this.resize(this.W, this.H); this.hud();
      if (!this.api.running) this.draw(this.cv.getContext('2d'));
    });
  }
  left(c) { let s = 0; for (let i = 0; i < this.fill.length; i++) if (this.pic.target[i] === c && this.fill[i] !== c) s++; return s; }
  pickNext() { const k = this.pic.colors.length; for (let j = 0; j < k - 1; j++) { const c = (this.sel - 1 + j) % (k - 1) + 1; if (this.left(c)) { this.sel = c; return; } } }
  hud() {
    if (!this.pic) return this.api.hud('…', '');
    const total = this.pic.target.filter(t => t).length, ok = this.fill.filter((f, i) => f > 0 && f === this.pic.target[i]).length;
    this.api.hud(`🎨 ${this.picDef.name}`, `${Math.floor(ok / total * 100)}%`);
  }
  key(code, down) {
    if (!down) return;
    if (code === 'SAVE') this.download();
    if (code === 'NEXT') { const i = PICS.indexOf(this.picDef); Mya.store.set('pixel.pic', PICS[(i + 1) % PICS.length].id); this.reset(this.mode); }
    const d = parseInt((code || '').replace('Digit', ''), 10); if (code && code.startsWith('Digit') && this.pic && d >= 1 && d < this.pic.colors.length) this.sel = d;
  }
  palAt([x, y]) {
    if (y < this.py - 6) return false;
    const k = this.pic.colors.length - 1;
    for (let c = 1; c <= k; c++) { const [cx, cy] = this.palPos(c); if (Math.hypot(x - cx, y - cy) < this.pr + 6) { this.sel = c; this.api.beep('rot'); return true; } }
    return true;
  }
  palPos(c) { const i = c - 1, r = Math.floor(i / this.perRow), inRow = Math.min(this.perRow, this.pic.colors.length - 1 - r * this.perRow), col = i - r * this.perRow, sp = (this.W - 20) / inRow; return [10 + sp * (col + .5), this.py + this.pr + r * (this.pr * 2 + 10)]; }
  paint([x, y]) {
    const cx = Math.floor((x - this.gx) / this.cs), cy = Math.floor((y - this.gy) / this.cs);
    if (cx < 0 || cy < 0 || cx >= this.n || cy >= this.n || this.won) return;
    const i = cy * this.n + cx; if (this.pic.target[i] === 0 || this.fill[i] === this.sel) return;
    if (this.fill[i] === this.pic.target[i]) return; // правильную клетку не перекрашиваем
    this.fill[i] = this.sel;
    if (this.sel === this.pic.target[i]) { this.api.beep('move'); if (!this.left(this.sel)) { this.api.beep('star'); this.pickNext(); } }
    this.hud();
    if (this.fill.every((f, k) => f === this.pic.target[k] || this.pic.target[k] === 0 && f <= 0)) this.win();
  }
  save() { if (this.pic) Mya.store.set('pixel.p.' + this.key_, this.fill); }
  win() {
    this.won = true; this.save(); this.api.beep('win');
    const d = doneSet(); if (!d.includes(this.key_)) { d.push(this.key_); Mya.store.set('pixel.done', d); }
    this.api.challenge('pictures', d.length);
    setTimeout(() => this.api.over({title: 'КАРТИНА ГОТОВА!', big: '🖼', score: d.length, text: `«${this.picDef.name}» раскрашена. Нажми «💾 Сохранить», чтобы скачать её.`, next: () => { const i = PICS.indexOf(this.picDef); Mya.store.set('pixel.pic', PICS[(i + 1) % PICS.length].id); }, again: 'Ещё раз эту'}), 500);
    if (this.won) Mya.store.set('pixel.p.' + this.key_, null);
  }
  download() {
    if (!this.pic) return;
    const s = 24, c = document.createElement('canvas'); c.width = c.height = this.n * s; const g = c.getContext('2d');
    g.fillStyle = '#fff'; g.fillRect(0, 0, c.width, c.height);
    this.fill.forEach((f, i) => { if (f > 0) { g.fillStyle = this.pic.colors[f]; g.fillRect((i % this.n) * s, Math.floor(i / this.n) * s, s, s); } });
    const a = document.createElement('a'); a.download = `3dmyau-${this.picDef.id}.png`; a.href = c.toDataURL('image/png'); a.click();
  }
  update(dt) { this.t += dt; }
  draw(g) {
    const {W, H} = this; if (!W) return;
    g.clearRect(0, 0, W, H); Mya.rrect(g, 0, 0, W, H, 22, '#fff');
    if (!this.pic) { Mya.text(g, 'Готовим картинку…', W / 2, H / 2, 20, '#ff4fa3'); return; }
    const {n, cs, gx, gy} = this, showNum = cs >= 13;
    g.font = `800 ${Math.floor(cs * .55)}px Rubik, sans-serif`; g.textAlign = 'center'; g.textBaseline = 'middle';
    for (let i = 0; i < n * n; i++) {
      const x = gx + (i % n) * cs, y = gy + Math.floor(i / n) * cs, t = this.pic.target[i], f = this.fill[i];
      if (t === 0) { g.fillStyle = (i + Math.floor(i / n)) % 2 ? '#faf5ff' : '#f3ebfb'; g.fillRect(x, y, cs, cs); continue; }
      if (f === t) { g.fillStyle = this.pic.colors[t]; g.fillRect(x, y, cs, cs); continue; }
      g.fillStyle = t === this.sel ? '#d9d2e6' : '#f4f4f8'; g.fillRect(x, y, cs, cs);
      if (f > 0) { g.fillStyle = this.pic.colors[f]; g.globalAlpha = .45; g.fillRect(x, y, cs, cs); g.globalAlpha = 1; g.strokeStyle = '#ff3b30'; g.lineWidth = 1.5; g.strokeRect(x + 1.5, y + 1.5, cs - 3, cs - 3); }
      g.strokeStyle = '#e2dcea'; g.lineWidth = 1; g.strokeRect(x + .5, y + .5, cs - 1, cs - 1);
      if (showNum) { g.fillStyle = t === this.sel ? '#2b0a3d' : '#9a90a8'; g.fillText(String(t), x + cs / 2, y + cs / 2 + 1); }
    }
    Mya.rrect(g, gx - 3, gy - 3, cs * n + 6, cs * n + 6, 6, null, INK, 4);
    const total = this.pic.target.filter(t => t).length, ok = this.fill.filter((f, i) => f > 0 && f === this.pic.target[i]).length;
    Mya.text(g, `${this.picDef.name} · ${Math.floor(ok / total * 100)}%`, W / 2, 16, 16, '#ff2e88');
    for (let c = 1; c < this.pic.colors.length; c++) {
      const [x, y] = this.palPos(c), left = this.left(c), r = this.pr;
      g.beginPath(); g.arc(x, y, r, 0, 7); g.fillStyle = this.pic.colors[c]; g.fill(); g.lineWidth = c === this.sel ? 6 : 3; g.strokeStyle = INK; g.stroke();
      const light = ['#ffffff', '#f6e2ff', '#ffd457', '#9dff4a', '#22e0d0', '#ffab2e'].includes(this.pic.colors[c]);
      if (left) Mya.text(g, String(c), x, y + 1, r * .9, light ? '#2b0a3d' : '#fff'); else Mya.text(g, '✔', x, y + 1, r * .9, '#fff');
    }
  }
}
})();
