/* Мяу-ритм: жми лапки в такт падающим нотам. */
'use strict';
(() => {
const {INK} = Mya;
const LC = ['#ff4fa3', '#ffd23f', '#22e0d0', '#ff9f1c'];
const KEYMAP = {KeyD: 0, ArrowLeft: 0, KeyF: 1, ArrowDown: 1, KeyJ: 2, ArrowUp: 2, KeyK: 3, ArrowRight: 3};
const SONGS = {
  polka: {bpm: 1, scale: [0, 2, 4, 5, 7, 9, 11, 12], base: 523.25},
  disco: {bpm: 1.12, scale: [0, 3, 5, 7, 10, 12, 15, 17], base: 440},
  night: {bpm: .9, scale: [0, 2, 3, 7, 8, 12, 14, 15], base: 392},
};
let ac = null;
function tone(freq, dur, type, vol) {
  if (Mya.muted()) return;
  try {
    ac = ac || new (window.AudioContext || window.webkitAudioContext)();
    const o = ac.createOscillator(), gn = ac.createGain(), t = ac.currentTime;
    o.type = type; o.frequency.setValueAtTime(freq, t);
    if (type === 'kick') { o.type = 'sine'; o.frequency.exponentialRampToValueAtTime(45, t + dur); }
    gn.gain.setValueAtTime(vol, t); gn.gain.exponentialRampToValueAtTime(.0001, t + dur);
    o.connect(gn).connect(ac.destination); o.start(t); o.stop(t + dur + .02);
  } catch (e) { /* без звука */ }
}

Mya.games.rhythm = {
  id: 'rhythm', title: 'Мяу-ритм',
  modes: [
    {id: 'polka', name: 'Мяу-полька', desc: 'Весёлая песенка. Жми лапку, когда нота долетит до линии.'},
    {id: 'disco', name: 'Принтер-диско', desc: 'Быстрее и с аккордами — иногда надо жать две лапки сразу.'},
    {id: 'night', name: 'Ночной клубок', desc: 'Медленная, но хитрая: много нот подряд в одну дорожку.'},
  ],
  controls: [],
  keys: 'Клавиши D F J K (или ← ↓ ↑ →) — четыре лапки · Esc пауза',
  hint: 'На телефоне нажимай прямо на дорожку. Идеально — 300 очков, хорошо — 100. Серия нот без промахов умножает очки.',
  recordText(mode) { const r = Mya.record('rhythm', mode || 'polka'); return r ? r.toLocaleString('ru-RU') : '—'; },
  subText() { return 'Диско: ' + this.recordText('disco'); },
  create(api) { return new Rhythm(api); },
};

class Rhythm {
  constructor(api) {
    this.api = api; this.cv = api.canvas; this.W = 0; this.H = 0; this.press = [0, 0, 0, 0];
    this.onDown = e => { if (!api.running) return; e.preventDefault(); const r = this.cv.getBoundingClientRect(); const l = Math.floor((e.clientX - r.left - this.ox) / this.lw); if (l >= 0 && l < 4) this.hit(l); };
    this.cv.addEventListener('pointerdown', this.onDown);
    this.reset('polka');
  }
  destroy() { this.cv.removeEventListener('pointerdown', this.onDown); }
  resize(W, H) { this.W = W; this.H = H; const tw = Math.min(W - 20, 460); this.lw = tw / 4; this.ox = (W - tw) / 2; this.hy = H - Math.max(70, this.lw * .9); }
  reset(mode) {
    this.mode = mode; this.diff = this.api.diff; const S = SONGS[mode];
    this.bpm = {kid: 92, player: 118, pro: 140}[this.diff] * S.bpm; this.beat = 60 / this.bpm;
    this.approach = {kid: 2.1, player: 1.6, pro: 1.2}[this.diff];
    const len = this.diff === 'kid' ? 40 : 60, rnd = Mya.rng(mode + this.diff);
    this.notes = []; let lane = 1;
    for (let b = 4; b * this.beat < len; b += .5) {
      const strong = b % 1 === 0, p = strong ? .75 : {kid: .05, player: .3, pro: .5}[this.diff];
      if (rnd() > p) continue;
      if (mode === 'night' && rnd() < .5) {} else lane = (lane + 1 + Math.floor(rnd() * 3)) % 4;
      const deg = Math.floor(rnd() * S.scale.length);
      this.notes.push({t: b * this.beat, lane, f: S.base * Math.pow(2, S.scale[deg] / 12), st: 0});
      if (mode === 'disco' && this.diff !== 'kid' && strong && rnd() < .25) this.notes.push({t: b * this.beat, lane: (lane + 2) % 4, f: S.base * Math.pow(2, S.scale[(deg + 2) % S.scale.length] / 12), st: 0});
    }
    this.end = this.notes[this.notes.length - 1].t + 2;
    this.t = -1.5; this.score = 0; this.combo = 0; this.maxCombo = 0; this.judged = 0; this.acc = 0; this.lastBeat = -1;
    this.fx = []; this.done = false;
    this.hud();
  }
  hud() { this.api.hud(`⭐ ${this.score.toLocaleString('ru-RU')}`, this.judged ? `${Math.round(this.acc / this.judged * 100)}%` : '—'); }
  key(code, down) { if (down && KEYMAP[code] != null) this.hit(KEYMAP[code]); }
  judge(n, kind) {
    n.st = kind === 'miss' ? 2 : 1; this.judged++;
    if (kind === 'miss') { this.combo = 0; this.fx.push({t: 'Мимо', lane: n.lane, a: .6, c: '#ffffff99'}); }
    else {
      this.combo++; this.maxCombo = Math.max(this.maxCombo, this.combo);
      const pts = {perfect: 300, good: 100, ok: 50}[kind], mult = 1 + Math.min(1, Math.floor(this.combo / 10) * .1);
      this.score += Math.round(pts * mult); this.acc += {perfect: 1, good: .7, ok: .4}[kind];
      this.fx.push({t: {perfect: 'ИДЕАЛЬНО!', good: 'Хорошо', ok: 'Норм'}[kind], lane: n.lane, a: .7, c: kind === 'perfect' ? '#ffd23f' : '#fff', ring: 1});
      tone(n.f, .25, 'triangle', .14);
    }
    this.hud();
  }
  hit(l) {
    if (this.done) return;
    this.press[l] = .15;
    let best = null, bd = 1;
    for (const n of this.notes) { if (n.lane !== l || n.st) continue; const d = Math.abs(n.t - this.t); if (d < bd) { bd = d; best = n; } if (n.t - this.t > .3) break; }
    if (!best || bd > .17) return;
    this.judge(best, bd < .06 ? 'perfect' : bd < .11 ? 'good' : 'ok');
  }
  update(dt) {
    if (this.done) return;
    this.t += dt;
    const bi = Math.floor(this.t / this.beat);
    if (bi > this.lastBeat && this.t >= 0 && this.t < this.end - 1.5) { this.lastBeat = bi; tone(110, .15, 'kick', .25); if (bi % 2) tone(1800, .03, 'square', .02); }
    for (const n of this.notes) if (!n.st && this.t - n.t > .17) this.judge(n, 'miss');
    this.press = this.press.map(p => Math.max(0, p - dt));
    this.fx.forEach(f => { f.a -= dt; }); this.fx = this.fx.filter(f => f.a > 0);
    if (this.t >= this.end) {
      this.done = true;
      const acc = this.judged ? this.acc / this.judged : 0, grade = acc > .95 ? 'S' : acc > .85 ? 'A' : acc > .7 ? 'B' : acc > .5 ? 'C' : 'D';
      this.api.challenge('combo', this.maxCombo);
      this.api.over({title: grade === 'S' ? 'МЯУ-ЗВЕЗДА!' : 'ПЕСНЯ ЗАКОНЧИЛАСЬ', big: `${grade} · ${this.score.toLocaleString('ru-RU')}`, score: this.score,
        text: `Точность ${Math.round(acc * 100)}% · Лучшая серия ${this.maxCombo}`});
    }
  }
  draw(g) {
    const {W, H, lw, ox, hy} = this; if (!W) return;
    g.clearRect(0, 0, W, H);
    const bg = g.createLinearGradient(0, 0, 0, H); bg.addColorStop(0, '#2b0a3d'); bg.addColorStop(1, '#6b1fb0');
    Mya.rrect(g, 0, 0, W, H, 22, bg);
    for (let i = 0; i < 4; i++) {
      g.fillStyle = LC[i] + (this.press[i] > 0 ? '33' : '14'); g.fillRect(ox + i * lw, 0, lw, H);
      g.fillStyle = '#ffffff22'; g.fillRect(ox + i * lw, 0, 2, H);
    }
    g.fillStyle = '#fff'; g.fillRect(ox - 6, hy - 3, lw * 4 + 12, 6);
    const pps = (hy + 20) / this.approach;
    for (const n of this.notes) {
      if (n.st) continue; const y = hy - (n.t - this.t) * pps; if (y < -40) break; if (y > H + 40) continue;
      Mya.rrect(g, ox + n.lane * lw + 6, y - 16, lw - 12, 32, 12, LC[n.lane], INK, 4);
      g.beginPath(); g.arc(ox + n.lane * lw + lw / 2, y, 6, 0, 7); g.fillStyle = '#ffffffbb'; g.fill();
    }
    // лапки
    for (let i = 0; i < 4; i++) {
      const cx = ox + i * lw + lw / 2, cy = hy + (H - hy) / 2 + 4, r = Math.min(lw * .38, (H - hy) * .42), pr = this.press[i] > 0;
      g.beginPath(); g.ellipse(cx, cy, r, r * .9, 0, 0, 7); g.fillStyle = pr ? '#fff' : LC[i]; g.fill(); g.lineWidth = 4; g.strokeStyle = INK; g.stroke();
      g.fillStyle = '#ff7ac6'; g.lineWidth = 2.5;
      [[0, r * .2, r * .38], [-r * .45, -r * .35, r * .18], [0, -r * .55, r * .18], [r * .45, -r * .35, r * .18]].forEach(([dx, dy, rr]) => { g.beginPath(); g.arc(cx + dx, cy + dy, rr, 0, 7); g.fill(); g.stroke(); });
    }
    for (const f of this.fx) {
      g.save(); g.globalAlpha = Math.min(1, f.a * 1.6);
      if (f.ring) { g.beginPath(); g.arc(ox + f.lane * lw + lw / 2, hy, lw * .45 * (1.4 - f.a), 0, 7); g.lineWidth = 4; g.strokeStyle = '#fff'; g.stroke(); }
      Mya.text(g, f.t, ox + f.lane * lw + lw / 2, hy - 60 - (1 - f.a) * 40, Math.min(18, lw / 5), f.c); g.restore();
    }
    if (this.combo >= 5) Mya.text(g, `КОМБО ${this.combo}`, W / 2, H * .3, Math.min(34, W / 12), '#fff');
    if (this.t < 0) Mya.text(g, this.t < -.8 ? 'Приготовься…' : 'Поехали!', W / 2, H * .4, Math.min(36, W / 11), '#ffd23f');
    // прогресс песни
    const pr = Math.max(0, Math.min(1, this.t / this.end));
    Mya.rrect(g, ox, 10, lw * 4, 8, 4, '#ffffff33'); Mya.rrect(g, ox, 10, lw * 4 * pr, 8, 4, '#ffd23f');
  }
}
})();
