/* Мяу-печать: роняй слои точно друг на друга и печатай башню. */
'use strict';
(() => {
const {COL, INK} = Mya;
const LH = 24, WW = 360, BASE = 200;
const COLORS = [COL.y, COL.o, COL.p, COL.o, COL.y, COL.c, COL.v, COL.c];

Mya.games.stack = {
  id: 'stack', title: 'Мяу-печать',
  modes: [
    {id: 'classic', name: 'Классика', desc: 'Слой ездит туда-сюда. Тапни, чтобы уронить его на башню. Что не попало — отрежется, и следующий слой станет уже.'},
    {id: 'turbo', name: 'Турбо', desc: 'Скорость растёт в два раза быстрее. Только для профи печати!'},
  ],
  controls: [],
  keys: 'Пробел, ↓ или клик — уронить слой · Esc пауза',
  hint: 'Попадёшь идеально 3 раза подряд — слой снова станет шире!',
  recordText(mode) { const r = Mya.record('stack', mode || 'classic'); return r ? r + ' слоёв' : '—'; },
  subText() { return 'Турбо: ' + this.recordText('turbo'); },
  create(api) { return new Stack(api); },
};

class Stack {
  constructor(api) {
    this.api = api; this.cv = api.canvas; this.W = 0; this.H = 0;
    this.onDown = e => { if (api.running) { e.preventDefault(); this.drop(); } };
    this.cv.addEventListener('pointerdown', this.onDown);
    this.reset('classic');
  }
  destroy() { this.cv.removeEventListener('pointerdown', this.onDown); }
  resize(W, H) { this.W = W; this.H = H; this.k = Math.min(W / WW, H / 560); this.ox = (W - WW * this.k) / 2; }
  reset(mode) {
    this.mode = mode; this.diff = this.api.diff;
    this.layers = [{x: (WW - BASE) / 2, w: BASE, c: '#a64dff'}];
    this.debris = []; this.pops = []; this.combo = 0; this.score = 0; this.dead = false; this.cam = 0; this.t = 0;
    this.spawn();
    this.hud();
  }
  speed() {
    const base = {kid: 95, player: 140, pro: 185}[this.diff], k = this.mode === 'turbo' ? 9 : 4;
    return Math.min(base + this.score * k, 520);
  }
  spawn() {
    const top = this.layers[this.layers.length - 1], fromLeft = this.layers.length % 2 === 0;
    this.cur = {x: fromLeft ? -top.w : WW, w: top.w, dir: fromLeft ? 1 : -1, c: COLORS[this.layers.length % COLORS.length]};
  }
  hud() { this.api.hud(`🧱 ${this.score}`, this.combo >= 2 ? `Идеально ×${this.combo}` : ''); }
  key(code, down) { if (down && ['Space', 'ArrowDown', 'Enter', 'KeyS'].includes(code)) this.drop(); }
  drop() {
    if (this.dead || !this.cur) return;
    const top = this.layers[this.layers.length - 1], c = this.cur;
    const tol = this.diff === 'kid' ? 9 : this.diff === 'pro' ? 4 : 6;
    if (Math.abs(c.x - top.x) <= tol) {
      c.x = top.x; this.combo++;
      if (this.combo >= 3) { const grow = Math.min(12, BASE - c.w); if (grow > 0) { c.w += grow; c.x -= grow / 2; this.pops.push({t: 'Слой шире! +' + Math.round(grow), a: 1}); } }
      this.pops.push({t: this.combo > 1 ? `ИДЕАЛЬНО! ×${this.combo}` : 'ИДЕАЛЬНО!', a: 1.1});
      this.api.beep('line');
    } else {
      const l = Math.max(c.x, top.x), r = Math.min(c.x + c.w, top.x + top.w);
      if (r - l <= 0) { this.debris.push({x: c.x, y: this.layers.length, w: c.w, c: c.c, vy: 0, vx: c.dir * 40, rot: 0}); this.cur = null; return this.end(); }
      if (c.x < l) this.debris.push({x: c.x, y: this.layers.length, w: l - c.x, c: c.c, vy: 0, vx: -60, rot: 0});
      if (c.x + c.w > r) this.debris.push({x: r, y: this.layers.length, w: c.x + c.w - r, c: c.c, vy: 0, vx: 60, rot: 0});
      c.x = l; c.w = r - l; this.combo = 0; this.api.beep('drop');
    }
    this.layers.push({x: c.x, w: c.w, c: c.c});
    this.score++;
    if (this.score % 10 === 0) { this.pops.push({t: `${this.score} слоёв! Мур!`, a: 1.5}); this.api.beep('win'); }
    this.api.challenge('layers', this.score);
    this.hud(); this.spawn();
  }
  end() {
    this.dead = true; this.api.beep('hit');
    setTimeout(() => this.api.over({title: 'ПЕЧАТЬ ОКОНЧЕНА', big: `${this.score} слоёв`, score: this.score,
      text: this.score >= 30 ? 'Огромная башня! Котик гордится тобой.' : 'Совет: жми, когда края слоёв совпадают.'}), 700);
  }
  update(dt) {
    this.t += dt;
    if (this.cur && !this.dead) {
      const c = this.cur; c.x += c.dir * this.speed() * dt;
      const lim = 70;
      if (c.x > WW - c.w + lim) { c.x = WW - c.w + lim; c.dir = -1; }
      if (c.x < -lim) { c.x = -lim; c.dir = 1; }
    }
    this.debris.forEach(d => { d.vy += 900 * dt; d.yy = (d.yy || 0) + d.vy * dt; d.x += d.vx * dt; d.rot += d.vx * .004 * dt * 10; });
    this.debris = this.debris.filter(d => d.yy < 1200);
    this.pops.forEach(p => { p.a -= dt; }); this.pops = this.pops.filter(p => p.a > 0);
    const want = Math.max(0, this.layers.length * LH - 560 * .45);
    this.cam += (want - this.cam) * Math.min(1, dt * 6);
  }
  draw(g) {
    const {W, H, k, ox} = this; if (!W) return;
    g.clearRect(0, 0, W, H);
    const bg = g.createLinearGradient(0, 0, 0, H); bg.addColorStop(0, '#3a0f5c'); bg.addColorStop(1, '#6b1fb0');
    Mya.rrect(g, 0, 0, W, H, 22, bg);
    g.save(); g.translate(ox, 0); g.scale(k, k);
    const VH = H / k, yOf = i => VH - 40 - (i + 1) * LH + this.cam;
    // стол принтера
    Mya.rrect(g, 30, yOf(-1), 300, 14, 6, '#9dff4a', INK, 3);
    this.layers.forEach((l, i) => { const y = yOf(i); if (y > -LH && y < VH) this.layer(g, l.x, y, l.w, l.c); });
    for (const d of this.debris) { const y = yOf(d.y) + d.yy; g.save(); g.translate(d.x + d.w / 2, y + LH / 2); g.rotate(d.rot); this.layer(g, -d.w / 2, -LH / 2, d.w, d.c); g.restore(); }
    if (this.cur) {
      const y = yOf(this.layers.length), c = this.cur;
      this.layer(g, c.x, y, c.w, c.c);
      // сопло над слоем
      const nx = c.x + c.w / 2;
      g.fillStyle = '#ffd23f'; g.fillRect(-200, y - 64, WW + 400, 10); g.strokeStyle = INK; g.lineWidth = 3; g.strokeRect(-200, y - 64, WW + 400, 10);
      Mya.rrect(g, nx - 18, y - 60, 36, 28, 6, '#fff', INK, 3);
      g.beginPath(); g.moveTo(nx - 6, y - 32); g.lineTo(nx, y - 22); g.lineTo(nx + 6, y - 32); g.closePath(); g.fillStyle = '#ff9f1c'; g.fill(); g.stroke();
      const cat = Mya.catImg(); if (cat.complete) g.drawImage(cat, nx - 12, y - 58, 24, 24);
    } else if (this.dead) {
      const top = this.layers[this.layers.length - 1], cat = Mya.catImg(), s = Math.min(90, top.w + 20);
      if (cat.complete) g.drawImage(cat, top.x + top.w / 2 - s / 2, yOf(this.layers.length - 1) - s * .86, s, s);
    }
    g.restore();
    this.pops.forEach((p, i) => { g.save(); g.globalAlpha = Math.min(1, p.a); Mya.text(g, p.t, W / 2, H * .2 + i * 38, Math.min(32, W / 13), '#ffd23f'); g.restore(); });
    Mya.text(g, String(this.score), W / 2, H * .09, Math.min(60, H / 10), '#fff');
  }
  layer(g, x, y, w, c) {
    Mya.rrect(g, x, y, w, LH - 2, 6, c, INK, 3);
    g.globalAlpha = .4; Mya.rrect(g, x + 5, y + 4, Math.max(0, w - 10), 5, 3, '#fff'); g.globalAlpha = 1;
  }
}
})();
