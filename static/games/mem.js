/* Мяу-память: найди пары одинаковых фигурок. */
'use strict';
(() => {
const {INK} = Mya;
const ICONS = ['🐱', '🧸', '🦖', '🚀', '🐙', '🏰', '🎲', '🦄', '🐉', '🌵', '⚽', '🎁', '🐢', '🦊', '🐼', '🍩', '🎈', '🪐', '🐳', '🍓'];
const SIZES = {s: [4, 4], m: [4, 5], l: [6, 6]};
const fmt = ms => { const s = Math.floor(ms / 1000); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };

Mya.games.mem = {
  id: 'mem', title: 'Мяу-память',
  modes: [
    {id: 's', name: '4×4', desc: '8 пар фигурок. Открывай по две карточки и запоминай, где какая.'},
    {id: 'm', name: '4×5', desc: '10 пар. Чем меньше ошибок, тем лучше время.'},
    {id: 'l', name: '6×6 Профи', desc: '18 пар! На сложности «Профи» после 3 ошибок подряд закрытые карты перемешиваются.'},
  ],
  controls: [],
  keys: 'Клик мышкой по карточке · Esc пауза',
  hint: 'Рекорд — самое быстрое время. За каждую ошибку +2 секунды.',
  recordText(mode) { const r = Mya.record('mem', mode || 's'); return r ? fmt(r) : '—'; },
  subText() { return '6×6: ' + this.recordText('l'); },
  create(api) { return new Mem(api); },
};

class Mem {
  constructor(api) {
    this.api = api; this.cv = api.canvas; this.W = 0; this.H = 0;
    this.onDown = e => { if (!api.running) return; const r = this.cv.getBoundingClientRect(); this.tap(e.clientX - r.left, e.clientY - r.top); };
    this.cv.addEventListener('pointerdown', this.onDown);
    this.reset('s');
  }
  destroy() { this.cv.removeEventListener('pointerdown', this.onDown); }
  resize(W, H) {
    this.W = W; this.H = H; if (!this.cols) return;
    let [c, r] = [this.cols, this.rows]; if (W > H * 1.2 && c < r) [c, r] = [r, c];
    this.gc = c; this.gr = r;
    const gap = 8, cw = Math.min((W - 20 - gap * (c - 1)) / c, ((H - 20 - gap * (r - 1)) / r) * .82);
    this.cw = cw; this.ch = cw / .82; this.gap = gap;
    this.ox = (W - (c * cw + (c - 1) * gap)) / 2; this.oy = (H - (r * this.ch + (r - 1) * gap)) / 2;
  }
  reset(mode) {
    this.mode = mode; this.diff = this.api.diff;
    [this.cols, this.rows] = SIZES[mode];
    const pairs = this.cols * this.rows / 2, icons = ICONS.slice().sort(() => Math.random() - .5).slice(0, pairs);
    const deck = icons.concat(icons).sort(() => Math.random() - .5);
    this.cards = deck.map(ic => ({ic, open: false, done: false, flip: 0}));
    this.picked = []; this.time = 0; this.miss = 0; this.streakMiss = 0; this.found = 0; this.lock = 0; this.won = false; this.pops = [];
    if (this.W) this.resize(this.W, this.H);
    this.hud();
  }
  hud() { this.api.hud(`⏱ ${fmt(this.time + this.miss * 2000)}`, `Пары ${this.found}/${this.cards.length / 2}`); }
  key() {}
  cellAt(x, y) {
    const c = Math.floor((x - this.ox) / (this.cw + this.gap)), r = Math.floor((y - this.oy) / (this.ch + this.gap));
    if (c < 0 || r < 0 || c >= this.gc || r >= this.gr) return -1;
    return r * this.gc + c;
  }
  tap(x, y) {
    if (this.won) return;
    const i = this.cellAt(x, y), card = this.cards[i];
    if (!card || card.open || card.done) return;
    if (this.picked.length === 2) this.closePicked();
    card.open = true; this.picked.push(i); this.api.beep('rot');
    if (this.picked.length === 2) {
      const [a, b] = this.picked.map(k => this.cards[k]);
      if (a.ic === b.ic) {
        a.done = b.done = true; this.picked = []; this.found++; this.streakMiss = 0; this.api.beep('eat');
        if (this.found === this.cards.length / 2) this.win();
      } else {
        this.miss++; this.streakMiss++; this.lock = .8; this.api.beep('hit');
        if (this.diff === 'pro' && this.mode === 'l' && this.streakMiss >= 3) { this.lock = 1.1; this.shuffleSoon = true; this.streakMiss = 0; }
      }
      this.hud();
    }
  }
  closePicked() {
    this.picked.forEach(k => { this.cards[k].open = false; }); this.picked = [];
    if (this.shuffleSoon) {
      this.shuffleSoon = false;
      const idx = this.cards.map((c, i) => (!c.done ? i : -1)).filter(i => i >= 0), ics = idx.map(i => this.cards[i].ic).sort(() => Math.random() - .5);
      idx.forEach((i, k) => { this.cards[i].ic = ics[k]; this.cards[i].flip = 0; });
      this.pops.push({t: 'Карты перемешались! 🌀', a: 1.6});
    }
  }
  win() {
    this.won = true; this.api.beep('win');
    const total = this.time + this.miss * 2000;
    this.api.challenge('pairs', this.found);
    setTimeout(() => this.api.over({title: 'ВСЕ ПАРЫ НАЙДЕНЫ!', big: fmt(total), score: Math.round(total), lowerBetter: true, text: `Ошибок: ${this.miss} (каждая +2 с).`}), 600);
  }
  update(dt) {
    if (!this.won) this.time += dt * 1000;
    if (this.lock > 0) { this.lock -= dt; if (this.lock <= 0 && this.picked.length === 2) this.closePicked(); }
    this.cards.forEach(c => { const want = c.open || c.done ? 1 : 0; c.flip += (want - c.flip) * Math.min(1, dt * 14); });
    this.pops.forEach(p => { p.a -= dt; }); this.pops = this.pops.filter(p => p.a > 0);
    this.hud();
  }
  draw(g) {
    const {W, H, cw, ch, gap, ox, oy} = this; if (!W || !cw) return;
    g.clearRect(0, 0, W, H);
    const bg = g.createLinearGradient(0, 0, 0, H); bg.addColorStop(0, '#3a0f5c'); bg.addColorStop(1, '#5b1a96');
    Mya.rrect(g, 0, 0, W, H, 22, bg);
    this.cards.forEach((c, i) => {
      const col = i % this.gc, row = Math.floor(i / this.gc), x = ox + col * (cw + gap), y = oy + row * (ch + gap);
      const f = c.flip, sx = Math.abs(Math.cos(f * Math.PI)), face = f > .5;
      g.save(); g.translate(x + cw / 2, y + ch / 2); g.scale(Math.max(.02, sx), 1);
      if (face) {
        Mya.rrect(g, -cw / 2, -ch / 2, cw, ch, cw * .16, c.done ? '#eaffd6' : '#fff', c.done ? '#5fcf3a' : INK, 3.5);
        g.font = `${cw * .55}px system-ui, "Apple Color Emoji", "Segoe UI Emoji", sans-serif`; g.textAlign = 'center'; g.textBaseline = 'middle'; g.fillText(c.ic, 0, 2);
      } else {
        const gr = g.createLinearGradient(-cw / 2, -ch / 2, cw / 2, ch / 2); gr.addColorStop(0, '#ff7ac6'); gr.addColorStop(1, '#a64dff');
        Mya.rrect(g, -cw / 2, -ch / 2, cw, ch, cw * .16, gr, INK, 3.5);
        const cat = Mya.catImg(); if (cat.complete) { g.globalAlpha = .9; g.drawImage(cat, -cw * .3, -cw * .32, cw * .6, cw * .6); g.globalAlpha = 1; }
      }
      g.restore();
    });
    this.pops.forEach(p => { g.save(); g.globalAlpha = Math.min(1, p.a); Mya.text(g, p.t, W / 2, H / 2, Math.min(30, W / 14), '#ffd23f'); g.restore(); });
  }
}
})();
