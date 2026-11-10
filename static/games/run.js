/* Мяу-ран: бег по трём дорожкам мимо катушек и барьеров. */
'use strict';
(() => {
const {COL, INK} = Mya;
const KEYMAP = {ArrowLeft: 'L', KeyA: 'L', ArrowRight: 'R', KeyD: 'R', ArrowUp: 'U', KeyW: 'U', Space: 'U', ArrowDown: 'D', KeyS: 'D'};
const ZMAX = 75, F = 15, PZ = 1.2;
const fmt = n => Math.floor(n).toLocaleString('ru-RU');

function missions() {
  const r = Mya.rng('run' + Mya.today()), pick = (a, b, step) => a + Math.floor(r() * ((b - a) / step + 1)) * step;
  const all = [
    {k: 'stars', n: pick(60, 200, 20), t: n => `Собери ${n} ⭐ за забег`},
    {k: 'meters', n: pick(800, 2400, 200), t: n => `Пробеги ${fmt(n)} м`},
    {k: 'jumps', n: pick(15, 40, 5), t: n => `Прыгни ${n} раз`},
    {k: 'slides', n: pick(8, 24, 4), t: n => `Проскользни под барьером ${n} раз`},
  ];
  for (let i = all.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [all[i], all[j]] = [all[j], all[i]]; }
  const done = Mya.store.get('run.m.' + Mya.today(), []);
  return all.slice(0, 3).map((m, i) => ({...m, i, done: done.includes(i), text: m.t(m.n)}));
}

Mya.games.run = {
  id: 'run', title: 'Мяу-ран',
  modes: [{id: 'run', name: 'Забег', desc: 'Беги как можно дальше: перепрыгивай катушки, проскальзывай под барьерами, обегай ящики. Скорость растёт!'}],
  controls: [{k: 'L', l: '←'}, {k: 'U', l: '↑'}, {k: 'D', l: '↓'}, {k: 'R', l: '→'}],
  keys: '← → сменить дорожку · ↑ или Пробел прыжок · ↓ подкат · Esc пауза',
  hint: 'Свайп влево-вправо — сменить дорожку, вверх — прыжок, вниз — подкат. 🧲 притягивает звёзды, 🛡 спасает от одного удара.',
  recordText() { const r = Mya.record('run', 'run'); return r ? fmt(r) + ' м' : '—'; },
  subText() { const m = missions(); return `🎯 ${m.filter(x => x.done).length}/3 задания`; },
  extra() { return `<p style="text-align:left"><b>Задания дня:</b><br>${missions().map(m => (m.done ? '✅ ' : '▫️ ') + m.text).join('<br>')}</p>`; },
  create(api) { return new Run(api); },
};

class Run {
  constructor(api) {
    this.api = api; this.cv = api.canvas; this.W = 0; this.H = 0;
    Mya.swipes(this.cv, d => { if (!api.running) return; const m = {left: 'L', right: 'R', up: 'U', down: 'D', tap: 'U'}[d]; if (m) this.act(m); });
    this.reset();
  }
  resize(W, H) { this.W = W; this.H = H; }
  reset() {
    this.diff = this.api.diff;
    this.v = {kid: 9, player: 12, pro: 15}[this.diff]; this.vmax = {kid: 16, player: 26, pro: 32}[this.diff];
    this.hearts = this.diff === 'kid' ? 3 : 1;
    this.lane = 0; this.x = 0; this.y = 0; this.vy = 0; this.slide = 0; this.inv = 0; this.shield = false; this.magnet = 0;
    this.dist = 0; this.stars = 0; this.jumps = 0; this.slides = 0; this.objs = []; this.nextZ = 45; this.t = 0; this.pops = []; this.dead = false;
    this.ms = missions();
    this.hud();
  }
  hud() { this.api.hud(`⭐ ${this.stars}`, `${fmt(this.dist)} м` + (this.hearts > 1 || this.diff === 'kid' ? ' ' + '❤'.repeat(Math.max(0, this.hearts)) : '')); }
  key(code, down) { if (down) { const k = KEYMAP[code] || code; this.act(k); } }
  act(k) {
    if (this.dead) return;
    if (k === 'L' && this.lane > -1) { this.lane--; this.api.beep('move'); }
    if (k === 'R' && this.lane < 1) { this.lane++; this.api.beep('move'); }
    if (k === 'U' && this.y <= 0.01) { this.vy = 7.4; this.slide = 0; this.jumps++; this.api.beep('jump'); }
    if (k === 'D') { if (this.y > 0.01) this.vy = -12; this.slide = .65; this.api.beep('rot'); }
  }
  spawnRow(z) {
    const r = Math.random, kid = this.diff === 'kid';
    const lanes = [-1, 0, 1].sort(() => r() - .5);
    const nObs = kid ? 1 : (r() < .35 + Math.min(.3, this.dist / 6000) ? 2 : 1);
    const types = kid ? ['spool'] : ['spool', 'spool', 'bar', 'box'];
    for (let i = 0; i < nObs; i++) {
      const type = types[Math.floor(r() * types.length)];
      this.objs.push({type, lane: lanes[i], z, c: [COL.p, COL.o, COL.c][Math.floor(r() * 3)]});
      if (type === 'spool' && r() < .5) for (let j = 0; j < 5; j++) this.objs.push({type: 'star', lane: lanes[i], z: z - 2 + j, h: 1.6 * Math.sin(Math.PI * (j + .5) / 5) + .2});
    }
    const free = lanes[nObs];
    if (free != null && r() < .7) for (let j = 0; j < 5; j++) this.objs.push({type: 'star', lane: free, z: z + j * 1.6, h: .4});
    if (free != null && r() < .06) this.objs.push({type: r() < .55 ? 'magnet' : 'shield', lane: free, z: z + 9, h: .5});
  }
  update(dt) {
    if (this.dead) return;
    this.t += dt;
    this.v = Math.min(this.vmax, this.v + dt * (this.diff === 'kid' ? .08 : .2));
    const dz = this.v * dt; this.dist += dz;
    this.objs.forEach(o => { o.z -= dz; });
    this.nextZ -= dz;
    if (this.nextZ <= ZMAX) { this.spawnRow(this.nextZ); this.nextZ += Math.max(11, 26 - this.v * .45) + Math.random() * 6; }
    this.x += (this.lane - this.x) * Math.min(1, dt * 14);
    if (this.y > 0 || this.vy > 0) { this.vy -= 24 * dt; this.y = Math.max(0, this.y + this.vy * dt); if (this.y === 0) this.vy = 0; }
    if (this.slide > 0) this.slide -= dt;
    if (this.inv > 0) this.inv -= dt;
    if (this.magnet > 0) this.magnet -= dt;
    // столкновения
    for (const o of this.objs) {
      if (o.gone || Math.abs(o.z - PZ) > .7) continue;
      const same = Math.abs(this.x - o.lane) < .45;
      if (o.type === 'star') {
        if ((same && Math.abs(this.y + .4 - o.h) < 1) || (this.magnet > 0 && o.z < 2)) { o.gone = true; this.stars++; this.api.beep('star'); }
      } else if (o.type === 'magnet' || o.type === 'shield') {
        if (same) { o.gone = true; this.api.beep('win'); if (o.type === 'magnet') { this.magnet = 8; this.pops.push({t: '🧲 Магнит!', a: 1.2}); } else { this.shield = true; this.pops.push({t: '🛡 Щит!', a: 1.2}); } }
      } else if (same && this.inv <= 0) {
        const hit = o.type === 'box' || (o.type === 'spool' && this.y < .55) || (o.type === 'bar' && this.slide <= 0);
        if (o.type === 'bar' && this.slide > 0 && !o.passed) { o.passed = true; this.slides++; }
        if (hit) this.hit(o);
      }
    }
    if (this.magnet > 0) this.objs.forEach(o => { if (o.type === 'star' && !o.gone && o.z < 9) o.lane += (this.x - o.lane) * Math.min(1, dt * 8); });
    this.objs = this.objs.filter(o => o.z > -3 && !o.gone);
    this.pops.forEach(p => { p.a -= dt; }); this.pops = this.pops.filter(p => p.a > 0);
    this.checkMissions();
    this.api.challenge('meters', this.dist);
    this.hud();
  }
  hit(o) {
    o.gone = true;
    if (this.shield) { this.shield = false; this.inv = 1; this.api.beep('drop'); this.pops.push({t: 'Щит спас!', a: 1}); return; }
    this.hearts--; this.api.beep('hit');
    if (this.hearts > 0) { this.inv = 1.5; this.pops.push({t: 'Ой! Осторожнее 🧡', a: 1}); return; }
    this.dead = true;
    const md = this.ms.filter(m => m.done).length;
    this.api.over({title: 'БУМ!', big: fmt(this.dist) + ' м', score: Math.floor(this.dist),
      text: `Звёзд: ${this.stars} · Прыжков: ${this.jumps}<br>Задания дня: ${md}/3${md === 3 ? ' — все выполнены! 🎉' : ''}`});
  }
  checkMissions() {
    const val = {stars: this.stars, meters: this.dist, jumps: this.jumps, slides: this.slides};
    for (const m of this.ms) if (!m.done && val[m.k] >= m.n) {
      m.done = true; const key = 'run.m.' + Mya.today(); const d = Mya.store.get(key, []); d.push(m.i); Mya.store.set(key, d);
      this.pops.push({t: '🎯 ' + m.text + ' ✔', a: 2}); this.api.beep('win');
    }
  }
  proj(lane, z, h) {
    const {W, H} = this, hy = H * .3, sc = F / (F + Math.max(-2, z - PZ + 1.2));
    const rw = Math.min(W * .46, H * .42), lw = rw * 2 / 3;
    return {x: W / 2 + lane * lw * sc, y: hy + (H * .98 - hy) * sc - (h || 0) * lw * .55 * sc, s: sc, lw: lw * sc};
  }
  draw(g) {
    const {W, H} = this; if (!W) return;
    const hy = H * .3, cx = W / 2;
    const sky = g.createLinearGradient(0, 0, 0, hy); sky.addColorStop(0, '#ff7ac6'); sky.addColorStop(1, '#ffb35c');
    g.fillStyle = sky; g.fillRect(0, 0, W, H);
    // полки по бокам
    g.fillStyle = '#ffc98a'; g.fillRect(0, hy, W, H - hy);
    const off = (this.dist % 6) / 6;
    for (let i = 0; i < 10; i++) {
      const z = (i - off) * 6 + 1, a = this.proj(-2.2, z), b = this.proj(2.2, z), a2 = this.proj(-2.2, z + 6), b2 = this.proj(2.2, z + 6);
      if (z < -1) continue;
      g.strokeStyle = INK; g.lineWidth = Math.max(1, 3 * a.s);
      g.fillStyle = '#8b2fd6'; g.beginPath(); g.moveTo(0, a.y - a.lw * 1.8); g.lineTo(a.x, a.y - a.lw * 1.8); g.lineTo(a2.x, a2.y - a2.lw * 1.8); g.lineTo(0, a2.y - a2.lw * 1.8); g.closePath(); g.fill();
      g.beginPath(); g.moveTo(W, b.y - b.lw * 1.8); g.lineTo(b.x, b.y - b.lw * 1.8); g.lineTo(b2.x, b2.y - b2.lw * 1.8); g.lineTo(W, b2.y - b2.lw * 1.8); g.closePath(); g.fill();
      const cc = [COL.c, COL.y, COL.l, COL.b][i % 4];
      Mya.rrect(g, a.x - a.lw * .9, a.y - a.lw * 2.5, a.lw * .45, a.lw * .7, 4 * a.s, cc, INK, Math.max(1, 2 * a.s));
      Mya.rrect(g, b.x + b.lw * .45, b.y - b.lw * 2.5, b.lw * .45, b.lw * .7, 4 * b.s, [COL.y, COL.p, COL.c, COL.l][i % 4], INK, Math.max(1, 2 * b.s));
    }
    // принтер-ворота на горизонте
    const gw = W * .2, gh = hy * .45;
    Mya.rrect(g, cx - gw / 2, hy - gh, gw, gh + 4, 12, '#b45cff', INK, 4);
    g.fillStyle = '#3a0f5c'; g.fillRect(cx - gw * .35, hy - gh * .7, gw * .7, gh * .7 + 2);
    Mya.rrect(g, cx - gw * .12, hy - gh * .85, gw * .24, gh * .25, 5, '#fff', INK, 3);
    // дорога
    const L = this.proj(-1.5, ZMAX), R = this.proj(1.5, ZMAX), BL = this.proj(-1.5, -2), BR = this.proj(1.5, -2);
    g.beginPath(); g.moveTo(L.x, hy); g.lineTo(R.x, hy); g.lineTo(BR.x, H); g.lineTo(BL.x, H); g.closePath();
    g.fillStyle = '#c58cff'; g.fill(); g.lineWidth = 4; g.strokeStyle = INK; g.stroke();
    for (const ln of [-.5, .5]) { const a = this.proj(ln, ZMAX), b = this.proj(ln, -2); g.beginPath(); g.moveTo(a.x, hy); g.lineTo(b.x, H); g.lineWidth = 5; g.strokeStyle = '#ffd23f'; g.stroke(); }
    for (let i = 0; i < 14; i++) { const z = (i - (this.dist % 5) / 5) * 5; if (z < -1) continue; const a = this.proj(0, z), b = this.proj(0, z + 1.5); g.beginPath(); g.moveTo(a.x - a.lw * 1.45, a.y); g.lineTo(a.x - a.lw * 1.45, a.y); g.moveTo(cx, a.y); g.lineTo(cx, b.y); g.lineWidth = 3 * a.s; g.strokeStyle = '#ffffff55'; g.stroke(); }
    // объекты: дальние первыми
    const objs = this.objs.slice().sort((a, b) => b.z - a.z);
    const drawPlayer = () => {
      const p = this.proj(this.x, PZ, 0), sz = p.lw * .95;
      g.save(); g.globalAlpha = .25; g.beginPath(); g.ellipse(p.x, p.y, sz * .45, sz * .12, 0, 0, 7); g.fillStyle = INK; g.fill(); g.restore();
      if (this.inv > 0 && Math.sin(this.t * 30) > 0) return;
      const im = Mya.catImg(true), jy = this.y * p.lw * .55, sh = this.slide > 0 ? .62 : 1;
      if (this.shield || this.magnet > 0) { g.beginPath(); g.arc(p.x, p.y - jy - sz * .45, sz * .62, 0, 7); g.fillStyle = this.shield ? '#22e0d055' : '#ff4fa344'; g.fill(); }
      if (im.complete) g.drawImage(im, p.x - sz / 2, p.y - jy - sz * sh, sz, sz * sh);
    };
    let drawn = false;
    for (const o of objs) {
      if (!drawn && o.z < PZ) { drawPlayer(); drawn = true; }
      const p = this.proj(o.lane, o.z, o.h || 0); if (p.s <= 0 || o.z > ZMAX) continue;
      const lw = p.lw;
      if (o.type === 'spool') { const im = Mya.spoolImg(o.c); if (im.complete) g.drawImage(im, p.x - lw * .45, p.y - lw * .78, lw * .9, lw * .9); }
      else if (o.type === 'box') { for (let k = 0; k < 3; k++) Mya.rrect(g, p.x - lw * .4, p.y - lw * .55 * (k + 1), lw * .8, lw * .55, 6 * p.s, ['#ffb35c', '#ff9f1c', '#ffd23f'][k], INK, Math.max(1.5, 3 * p.s)); Mya.text(g, '🐾', p.x, p.y - lw * 1.4, lw * .3); }
      else if (o.type === 'bar') { g.fillStyle = INK; g.fillRect(p.x - lw * .4, p.y - lw * .9, lw * .07, lw * .9); g.fillRect(p.x + lw * .33, p.y - lw * .9, lw * .07, lw * .9); Mya.rrect(g, p.x - lw * .48, p.y - lw * 1.05, lw * .96, lw * .2, 6 * p.s, '#ffd23f', INK, Math.max(1.5, 3 * p.s)); }
      else if (o.type === 'star') { star(g, p.x, p.y - lw * .2, lw * .2); }
      else { g.beginPath(); g.arc(p.x, p.y - lw * .3, lw * .26, 0, 7); g.fillStyle = o.type === 'magnet' ? '#22e0d0' : '#ffd23f'; g.fill(); g.lineWidth = 3 * p.s; g.strokeStyle = INK; g.stroke(); Mya.text(g, o.type === 'magnet' ? '🧲' : '🛡', p.x, p.y - lw * .3, lw * .3); }
    }
    if (!drawn) drawPlayer();
    this.pops.forEach((p, i) => { g.save(); g.globalAlpha = Math.min(1, p.a); Mya.text(g, p.t, cx, H * .4 + i * 34, Math.min(30, W / 14), '#ffd23f'); g.restore(); });
    if (this.magnet > 0) Mya.text(g, `🧲 ${Math.ceil(this.magnet)}с`, 14, hy * .2 + 10, 18, '#fff', 'left');
  }
}
function star(g, x, y, r) {
  g.beginPath();
  for (let i = 0; i < 10; i++) { const a = -Math.PI / 2 + i * Math.PI / 5, rr = i % 2 ? r * .45 : r; g.lineTo(x + Math.cos(a) * rr, y + Math.sin(a) * rr); }
  g.closePath(); g.fillStyle = '#ffd23f'; g.fill(); g.lineWidth = Math.max(1.5, r * .18); g.strokeStyle = INK; g.stroke();
}
})();
