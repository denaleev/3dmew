/* Летучий принтер: подлетай между колоннами из катушек. */
'use strict';
(() => {
const {COL, INK} = Mya;
const MEDALS = [[50, '🥇 золото'], [25, '🥈 серебро'], [10, '🥉 бронза']];
const medal = s => (MEDALS.find(m => s >= m[0]) || [0, ''])[1];

Mya.games.fly = {
  id: 'fly', title: 'Летучий принтер',
  modes: [
    {id: 'normal', name: 'Обычный', desc: 'Пролетай между колоннами из катушек. С 25 очков проходы сужаются, с 50 — катушки начинают двигаться.'},
    {id: 'wind', name: 'Ветер', desc: 'Порывы ветра то прижимают принтер вниз, то подбрасывают вверх. Следи за стрелками!'},
    {id: 'night', name: 'Ночь', desc: 'Темно! Видно только то, что освещает фонарик принтера.'},
  ],
  controls: [],
  keys: 'Пробел, ↑ или клик — подлететь · Esc пауза',
  hint: 'Тапай по экрану, чтобы принтер подлетал. Медали: 🥉 10, 🥈 25, 🥇 50.',
  recordText(mode) { const r = Mya.record('fly', mode || 'normal'); return r ? String(r) : '—'; },
  subText() { const r = Mya.record('fly', 'normal'); return medal(r) || 'без медали'; },
  create(api) { return new Fly(api); },
};

class Fly {
  constructor(api) {
    this.api = api; this.cv = api.canvas; this.W = 0; this.H = 0;
    this.onDown = e => { if (api.running) { e.preventDefault(); this.flap(); } };
    this.cv.addEventListener('pointerdown', this.onDown);
    this.reset('normal');
  }
  destroy() { this.cv.removeEventListener('pointerdown', this.onDown); }
  resize(W, H) { this.W = W; this.H = H; this.u = H / 600; }
  reset(mode) {
    this.mode = mode; this.diff = this.api.diff;
    this.y = 260; this.vy = 0; this.cols = []; this.score = 0; this.t = 0; this.started = false; this.dead = false;
    this.nextX = 0; this.wind = 0; this.windT = 3; this.trail = []; this.pops = []; this.lives = this.diff === 'kid' ? 3 : 1; this.inv = 0;
    this.stars = [];
    this.hud();
  }
  hud() { this.api.hud(`🏆 ${this.score}`, (medal(this.score) || '') + (this.diff === 'kid' ? ' ' + '❤'.repeat(this.lives) : '')); }
  key(code, down) { if (down && (code === 'Space' || code === 'ArrowUp' || code === 'KeyW')) this.flap(); }
  flap() { if (this.dead) return; this.started = true; this.vy = -330; this.api.beep('jump'); }
  gap() { const base = {kid: 230, player: 175, pro: 150}[this.diff]; return Math.max(base - 50, base - Math.max(0, this.score - 25) * 1.6); }
  speed() { return {kid: 120, player: 160, pro: 190}[this.diff] + Math.min(80, this.score * 1.2); }
  addCol(x) {
    const g = this.gap(), mid = 120 + g / 2 + Math.random() * (600 - 240 - g);
    const moving = this.score + this.cols.length >= 50 || this.diff === 'pro' && this.score >= 20;
    this.cols.push({x, mid, g, moving, ph: Math.random() * 6, amp: moving ? 50 + Math.random() * 40 : 0, passed: false});
    if (Math.random() < .45) this.stars.push({x: x + 35, y: mid, got: false});
  }
  update(dt) {
    if (this.dead) return;
    this.t += dt;
    const ww = this.W / this.u; // ширина мира в единицах
    if (!this.started) { this.y = 260 + Math.sin(this.t * 3) * 10; return; }
    if (this.mode === 'wind') { this.windT -= dt; if (this.windT <= 0) { this.wind = (Math.random() < .5 ? -1 : 1) * (220 + Math.random() * 260); if (Math.random() < .3) this.wind = 0; this.windT = 2.5 + Math.random() * 2; } }
    this.vy += (1050 + this.wind) * dt; this.vy = Math.min(this.vy, 600); this.y += this.vy * dt;
    const sp = this.speed() * dt;
    if (!this.cols.length) this.nextX = ww + 40;
    this.nextX -= sp;
    while (this.nextX < ww + 100) { this.addCol(this.nextX + 0); this.nextX += Math.max(210, 290 - this.score); }
    this.cols.forEach(c => { c.x -= sp; if (c.moving) c.off = Math.sin(this.t * 1.6 + c.ph) * c.amp; else c.off = 0; });
    this.stars.forEach(s => { s.x -= sp; });
    this.cols = this.cols.filter(c => c.x > -120); this.stars = this.stars.filter(s => s.x > -60 && !s.got);
    this.trail.push([this.y]); if (this.trail.length > 18) this.trail.shift();
    if (this.inv > 0) this.inv -= dt;
    this.pops.forEach(p => { p.a -= dt; }); this.pops = this.pops.filter(p => p.a > 0);
    // столкновения: принтер — круг r=24 в x=110
    const px = 110, r = 22;
    for (const c of this.cols) {
      if (!c.passed && c.x + 70 < px - r) { c.passed = true; this.score++; this.api.beep('eat'); this.hud(); if (this.score === 25 || this.score === 50) { this.pops.push({t: this.score === 25 ? 'Проходы сужаются!' : 'Катушки ожили!', a: 1.6}); } }
      const top = c.mid + c.off - c.g / 2, bot = c.mid + c.off + c.g / 2;
      if (px + r > c.x && px - r < c.x + 70 && (this.y - r < top || this.y + r > bot)) return this.hit();
    }
    for (const s of this.stars) if (!s.got && Math.hypot(s.x - px, s.y - this.y) < r + 14) { s.got = true; this.score += 2; this.api.beep('star'); this.pops.push({t: '+2 ⭐', a: .8}); this.hud(); }
    if (this.y < r) { this.y = r; this.vy = Math.max(this.vy, 40); } // потолок не опасен
    if (this.y > 600 - r) {
      if (this.diff === 'kid') { this.y = 600 - r; this.vy = -250; }
      else return this.hit();
    }
  }
  hit() {
    if (this.inv > 0) return;
    this.lives--; this.api.beep('hit');
    if (this.lives > 0) { this.inv = 1.5; this.cols = this.cols.filter(c => c.x < 60 || c.x > 200); this.vy = -250; this.hud(); return; }
    this.dead = true;
    const m = medal(this.score);
    this.api.challenge('score', this.score);
    this.api.over({title: 'БУМ!', big: String(this.score), score: this.score, text: m ? `Медаль: ${m}!` : `До бронзы осталось ${10 - this.score}.`});
  }
  draw(g) {
    const {W, H, u} = this; if (!W) return;
    const ww = W / u;
    g.save(); g.scale(u, u);
    const sky = g.createLinearGradient(0, 0, 0, 600);
    if (this.mode === 'night') { sky.addColorStop(0, '#120530'); sky.addColorStop(1, '#3a1060'); } else { sky.addColorStop(0, '#22c7ff'); sky.addColorStop(.65, '#9be8ff'); sky.addColorStop(1, '#ffc2e6'); }
    g.fillStyle = sky; g.fillRect(0, 0, ww, 600);
    // облака и город (медленный параллакс)
    const par = (this.t * 20) % (ww + 200);
    g.fillStyle = this.mode === 'night' ? '#ffffff22' : '#fff'; g.strokeStyle = INK; g.lineWidth = 3;
    for (let i = 0; i < 4; i++) { const x = ((i * 260 - par) % (ww + 200) + ww + 200) % (ww + 200) - 100, y = 90 + (i % 2) * 80; g.beginPath(); g.ellipse(x, y, 50, 18, 0, 0, 7); g.fill(); if (this.mode !== 'night') g.stroke(); }
    g.fillStyle = this.mode === 'night' ? '#2a0b4d' : '#d9a6ff';
    for (let i = 0; i < 12; i++) { const x = ((i * 90 - this.t * 40) % (ww + 180) + ww + 180) % (ww + 180) - 90, h = 60 + (i * 37) % 70; g.fillRect(x, 600 - h, 70, h); g.strokeRect(x, 600 - h, 70, h); }
    // колонны
    for (const c of this.cols) {
      const top = c.mid + c.off - c.g / 2, bot = c.mid + c.off + c.g / 2;
      for (let y = top - 46; y > -50; y -= 46) this.spool(g, c.x + 35, y + 23, (y / 46 | 0) % 2 ? COL.o : COL.p);
      for (let y = bot; y < 650; y += 46) this.spool(g, c.x + 35, y + 23, (y / 46 | 0) % 2 ? COL.y : COL.o);
    }
    for (const s of this.stars) star(g, s.x, s.y, 13);
    // шлейф филамента
    const px = 110;
    ['#ff4fa3', '#ffd23f', '#22e0d0'].forEach((c, k) => {
      g.beginPath(); this.trail.forEach(([y], i) => { const x = px - 30 - (this.trail.length - i) * 6; const yy = y + (k - 1) * 9; i ? g.lineTo(x, yy) : g.moveTo(x, yy); });
      g.lineWidth = 8; g.strokeStyle = c; g.lineCap = 'round'; g.stroke();
    });
    if (!(this.inv > 0 && Math.sin(this.t * 30) > 0)) this.printer(g, px, this.y, Math.max(-.5, Math.min(.7, this.vy / 700)));
    if (this.mode === 'night') {
      const grd = g.createRadialGradient(px + 60, this.y, 60, px + 60, this.y, 260);
      grd.addColorStop(0, 'rgba(10,0,30,0)'); grd.addColorStop(1, 'rgba(10,0,30,.93)');
      g.fillStyle = grd; g.fillRect(0, 0, ww, 600);
    }
    if (this.mode === 'wind' && this.wind) { const up = this.wind < 0; for (let i = 0; i < 5; i++) Mya.text(g, up ? '⇡' : '⇣', 60 + i * (ww - 120) / 4, 300 + Math.sin(this.t * 4 + i) * 120, 34, '#ffffffaa'); }
    g.restore();
    if (!this.started && !this.dead) Mya.text(g, 'Тапни, чтобы взлететь!', W / 2, H * .3, Math.min(30, W / 14), '#ffd23f');
    this.pops.forEach((p, i) => { g.save(); g.globalAlpha = Math.min(1, p.a); Mya.text(g, p.t, W / 2, H * .22 + i * 36, Math.min(30, W / 14), '#ffd23f'); g.restore(); });
    Mya.text(g, String(this.score), W / 2, H * .12, Math.min(64, H / 9), '#fff');
  }
  spool(g, x, y, c) { const im = Mya.spoolImg(c); if (im.complete) g.drawImage(im, x - 42, y - 42, 84, 84); }
  printer(g, x, y, rot) {
    g.save(); g.translate(x, y); g.rotate(rot);
    const flap = Math.sin(this.t * 22) * .5;
    g.save(); g.translate(-28, -8); g.rotate(-.3 + flap); g.beginPath(); g.ellipse(-18, 0, 24, 11, 0, 0, 7); g.fillStyle = '#fff'; g.fill(); g.lineWidth = 3.5; g.strokeStyle = INK; g.stroke(); g.restore();
    Mya.rrect(g, -30, -26, 60, 48, 11, '#b45cff', INK, 4);
    Mya.rrect(g, -18, -14, 36, 24, 6, '#fff', INK, 3);
    const cat = Mya.catImg(); if (cat.complete) g.drawImage(cat, -14, -15, 28, 28);
    Mya.rrect(g, -7, 22, 14, 10, 3, '#ffd23f', INK, 3);
    g.beginPath(); g.moveTo(-5, 32); g.lineTo(0, 41); g.lineTo(5, 32); g.closePath(); g.fillStyle = '#ff9f1c'; g.fill(); g.lineWidth = 3; g.stroke();
    g.restore();
  }
}
function star(g, x, y, r) {
  g.beginPath();
  for (let i = 0; i < 10; i++) { const a = -Math.PI / 2 + i * Math.PI / 5, rr = i % 2 ? r * .45 : r; g.lineTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr); }
  g.closePath(); g.fillStyle = '#ffd23f'; g.fill(); g.lineWidth = 2.5; g.strokeStyle = INK; g.stroke();
}
})();
