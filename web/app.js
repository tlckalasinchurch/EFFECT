// ====================================================================
// กดจนหลอนTone — Neural Guitar Workstation (Chain UI)
// Vanilla JS, no build step. Talks to server.py over /api/*.
// ====================================================================
'use strict';

const $ = (id) => document.getElementById(id);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

function esc(v) {
  if (v === null || v === undefined) return '';
  return String(v)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function askText(message, fallback) {
  try {
    const v = window.prompt(message, fallback);
    if (v === null) return null;
    return String(v).trim() || fallback;
  } catch (err) {
    return fallback;
  }
}

// ── state ────────────────────────────────────────────────────────────
const state = {
  live: {},
  nam: null,
  namKey: 'none',
  namTitle: '',
  namFile: '',
  namArch: '2',
  namQuality: localStorage.getItem('tone.namQuality') || 'lite',
  showPitch: localStorage.getItem('tone.showPitch') === '1',
  block: 'amp',
  presets: [],
  t3kPresets: [],
  filter: 'all',
  query: '',
  selectedId: null,
  selectedType: null,
  selectedKey: null,
  dirty: false,
  isRunning: true,
  tunerActive: false,
  devices: { inputs: [], outputs: [] },
  selectedIn: null,
  selectedOut: null,
  knobControllers: { panel: [], face: [] },
  pending: new Map(),
  pollTimer: null,
  pollBusy: false,
  ctxBlock: null,
  pickerTarget: null,
  pickerMode: 'file',
  longPressTimer: null,
  favorites: new Set(JSON.parse(localStorage.getItem('tone.favorites') || '[]')),
  booted: false,
  t3kLoaded: null,
  lastServer: null,
};

// ── small API helper ─────────────────────────────────────────────────
async function api(path, { method = 'GET', body = null } = {}) {
  const options = { method, headers: {} };
  if (body !== null) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }
  const res = await fetch(path, options);
  let data = {};
  try { data = await res.json(); } catch (err) { /* empty body */ }
  if (!res.ok) {
    const detail = data.detail || data.error || data.message || `HTTP ${res.status}`;
    const error = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    error.status = res.status;
    throw error;
  }
  return data;
}

// ── toast ────────────────────────────────────────────────────────────
let toastTimer = null;
function showToast(message, isError = false) {
  const el = $('toast');
  if (!el) return;
  el.textContent = message;
  el.classList.toggle('error', !!isError);
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 3200);
}

// ── block definitions ────────────────────────────────────────────────
const ICONS = {
  input: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h7"/><path d="M8 7l5 5-5 5"/><path d="M19 5v14"/></svg>',
  gate: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12h3l2-6 3 12 3-12 2 6h7"/><path d="M2 5h20" stroke-dasharray="3 3"/></svg>',
  pitch: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v18"/><path d="M8 6l4-3 4 3"/><path d="M8 18l4 3 4-3"/></svg>',
  drive: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="6" width="16" height="12" rx="2"/><circle cx="9" cy="12" r="1.5"/><circle cx="15" cy="12" r="1.5"/><path d="M8 18v3M16 18v3"/></svg>',
  amp: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="8" cy="12" r="2"/><path d="M13 10h5M13 14h5"/></svg>',
  'amp-cab': '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="5" width="12" height="9" rx="1.5"/><circle cx="6" cy="9.5" r="1.5"/><rect x="15" y="8" width="7" height="11" rx="1.5"/><circle cx="18.5" cy="13.5" r="2"/></svg>',
  pedal: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3h12v18H6z"/><circle cx="9" cy="8" r="1.5"/><circle cx="15" cy="8" r="1.5"/><path d="M9 14h6"/></svg>',
  cab: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="1"/></svg>',
  reverb: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12c2-4 4-4 6 0s4 4 6 0 4-4 6 0"/><path d="M3 17c2-3 4-3 6 0s4 3 6 0 4-3 6 0"/></svg>',
  delay: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8"/><path d="M12 8v5l3 2"/><path d="M5 4 3 6M19 4l2 2"/></svg>',
  output: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12h11"/><path d="M11 7l5 5-5 5"/><path d="M20 5v14"/></svg>',
};

const K = (key, label, min, max, step, fmt, def, section, param, uiScale = 1) =>
  ({ key, label, min, max, step, fmt, def, section, param, uiScale });

const BLOCKS = [
  { id: 'input', en: 'INPUT', th: 'อินพุต', section: 'input', canBypass: false, icon: 'input' },
  { id: 'gate', en: 'GATE', th: 'นอยส์เกต', section: 'gate', canBypass: true, icon: 'gate' },
  { id: 'pitch', en: 'PITCH', th: 'ทรานสโพส', section: 'pitch', canBypass: true, icon: 'pitch', pluginHidden: true },
  { id: 'drive', en: 'DRIVE', th: 'โอเวอร์ไดรฟ์', section: 'screamer', canBypass: true, icon: 'pedal' },
  { id: 'amp', en: 'NAM AMP', th: 'แอมป์ / NAM', section: 'amp', canBypass: true, icon: 'amp' },
  { id: 'cab', en: 'IR CAB', th: 'ตู้ + IR', section: 'cab', canBypass: true, icon: 'cab' },
  { id: 'delay', en: 'DELAY', th: 'ดีเลย์', section: 'delay', canBypass: true, icon: 'delay' },
  { id: 'reverb', en: 'REVERB', th: 'รีเวิร์บ', section: 'reverb', canBypass: true, icon: 'reverb' },
  { id: 'output', en: 'OUTPUT', th: 'เอาต์พุต', section: 'master', canBypass: false, icon: 'output' },
];

const KNOB_SETS = {
  input: [
    K('trim', 'Trim', -24, 24, 0.5, 'db', 0, 'input', 'trim'),
  ],
  gate: [
    K('threshold', 'Threshold', -80, -20, 1, 'db', -55, 'gate', 'threshold'),
    K('release', 'Release', 10, 500, 1, 'ms', 50, 'gate', 'release'),
    K('hold', 'Hold', 0, 200, 1, 'ms', 50, 'gate', 'hold'),
    K('range', 'Range', -90, -20, 1, 'db', -60, 'gate', 'range'),
  ],
  pitch: [
    K('semitones', 'Pitch', -24, 24, 1, 'st', 0, 'pitch', 'semitones'),
    K('glide', 'Glide', 0, 100, 1, 'pct', 0, 'pitch', 'glide'),
    K('mix', 'Mix', 0, 100, 1, 'pct', 100, 'pitch', 'mix', 100),
  ],
  drive: [
    K('drive', 'Drive', 0, 100, 1, 'pct', 40, 'screamer', 'drive', 100),
    K('tone', 'Tone', 0, 100, 1, 'pct', 60, 'screamer', 'tone', 100),
    K('level', 'Level', 0, 100, 1, 'pct', 70, 'screamer', 'level', 100),
  ],
  amp_dsp: [
    K('gain', 'Gain', 0, 100, 1, 'pct', 65, 'amp', 'gain', 100),
    K('bass', 'Bass', 0, 100, 1, 'pct', 55, 'amp', 'bass', 100),
    K('mid', 'Middle', 0, 100, 1, 'pct', 50, 'amp', 'mid', 100),
    K('treble', 'Treble', 0, 100, 1, 'pct', 60, 'amp', 'treble', 100),
    K('presence', 'Presence', 0, 100, 1, 'pct', 60, 'amp', 'presence', 100),
    K('master', 'Volume', 0, 100, 1, 'pct', 70, 'amp', 'master', 100),
  ],
  amp_nam: [
    K('input_gain', 'In Gain', -24, 24, 0.5, 'db', 0, 'nam', 'input_gain'),
  ],
  cab: [
    K('lowcut', 'Low Cut', 20, 500, 1, 'hz', 20, 'cab', 'lowcut'),
    K('highcut', 'High Cut', 1000, 20000, 10, 'hz', 20000, 'cab', 'highcut'),
    K('mix', 'Mix', 0, 100, 1, 'pct', 100, 'cab', 'mix', 100),
    K('level', 'Level', 0, 200, 1, 'pct', 100, 'cab', 'level', 100),
  ],
  delay: [
    K('time', 'Time', 20, 2000, 1, 'ms', 360, 'delay', 'time'),
    K('feedback', 'Feedback', 0, 95, 1, 'pct', 35, 'delay', 'feedback', 100),
    K('mix', 'Mix', 0, 100, 1, 'pct', 25, 'delay', 'mix', 100),
  ],
  reverb: [
    K('decay', 'Decay', 0, 100, 1, 'pct', 50, 'reverb', 'decay', 100),
    K('mix', 'Mix', 0, 100, 1, 'pct', 20, 'reverb', 'mix', 100),
    K('tone', 'Tone', 0, 100, 1, 'pct', 50, 'reverb', 'tone', 100),
  ],
  output: [
    K('volume', 'Master', 0, 150, 1, 'pct', 100, 'master', 'volume', 100),
  ],
};

function blockById(id) {
  return BLOCKS.find((b) => b.id === id) || BLOCKS[0];
}

function blockEn(id) {
  if (id === 'amp' && !state.nam) return 'DSP AMP';
  return blockById(id).en;
}

function blockTh(id) {
  if (id === 'amp' && !state.nam) return 'แอมป์ / DSP';
  return blockById(id).th;
}

function visibleBlocks() {
  return BLOCKS.filter((b) => b.id !== 'pitch' || state.showPitch);
}

function knobsForBlock(id) {
  if (id === 'amp') return state.nam ? KNOB_SETS.amp_nam : KNOB_SETS.amp_dsp;
  return KNOB_SETS[id] || [];
}

function blockEnabled(id) {
  const c = state.live || {};
  if (id === 'input' || id === 'output') return true;
  if (id === 'gate') return c.gate ? !!c.gate.enabled : true;
  if (id === 'pitch') return c.pitch ? !!c.pitch.enabled : false;
  if (id === 'drive') return c.screamer ? !!c.screamer.enabled : false;
  if (id === 'amp') return state.nam ? !!state.nam.enabled : (c.amp ? !!c.amp.enabled : true);
  if (id === 'cab') return c.cab ? !!c.cab.enabled : true;
  if (id === 'delay') return c.delay ? !!c.delay.enabled : false;
  if (id === 'reverb') return c.reverb ? !!c.reverb.enabled : false;
  return true;
}

function namGearType() {
  if (!state.nam) return 'amp';
  const stages = state.nam.stages || [];
  if (stages.some((s) => s.gear_type === 'amp_cab')) return 'amp-cab';
  if (stages.length && stages.every((s) => s.gear_type === 'pedal')) return 'pedal';
  return 'amp';
}

function blockIcon(id) {
  if (id === 'amp' && state.nam) return ICONS[namGearType()] || ICONS.amp;
  const b = blockById(id);
  return ICONS[b.icon] || ICONS.amp;
}

function shortText(text, n = 18) {
  const s = String(text || '');
  return s.length > n ? s.slice(0, n - 1) + '…' : s;
}

function blockSubtitle(id) {
  const c = state.live || {};
  if (id === 'input') return Number(c.input?.trim_db || 0).toFixed(1) + ' dB trim';
  if (id === 'gate') return Number(c.gate?.threshold ?? -55).toFixed(0) + ' dB';
  if (id === 'pitch') {
    const st = Number(c.pitch?.target_semitones ?? c.pitch?.semitones ?? 0);
    return (st > 0 ? '+' : '') + st.toFixed(0) + ' st';
  }
  if (id === 'drive') return 'Drive ' + Math.round(Number(c.screamer?.drive || 0) * 100) + '%';
  if (id === 'amp') {
    if (state.nam) {
      const title = state.namTitle || (state.nam.stages || []).map((s) => s.title).filter(Boolean).join(' + ');
      return 'NAM · ' + shortText(title || 'capture', 15);
    }
    return 'DSP · ' + shortText(c.amp?.model || 'Amp', 12);
  }
  if (id === 'cab') return shortText(c.cab?.ir_name || 'IR', 16);
  if (id === 'delay') return Math.round(Number(c.delay?.time || 0.36) * 1000) + ' ms';
  if (id === 'reverb') {
    const type = String(c.reverb?.type || 'plate');
    return type.charAt(0).toUpperCase() + type.slice(1);
  }
  if (id === 'output') return Math.round(Number(c.master_volume ?? 1) * 100) + ' %';
  return '';
}

// ── knob helpers ─────────────────────────────────────────────────────
function toUi(kd, serverValue) {
  return Number(serverValue) * (kd.uiScale || 1);
}

function toServer(kd, uiValue) {
  const scaled = Number(uiValue) / (kd.uiScale || 1);
  return kd.section === 'delay' && kd.param === 'time' ? scaled / 1000 : scaled;
}

function readServer(kd) {
  const c = state.live || {};
  let v;
  if (kd.section === 'input') v = c.input?.trim_db;
  else if (kd.section === 'gate') {
    if (kd.param === 'range') v = c.gate?.range_db;
    else if (kd.param === 'hold') v = c.gate?.hold_ms;
    else if (kd.param === 'release') v = c.gate?.release_ms;
    else v = c.gate?.[kd.param];
  }
  else if (kd.section === 'pitch') {
    v = kd.param === 'semitones'
      ? (c.pitch?.target_semitones ?? c.pitch?.semitones)
      : c.pitch?.[kd.param];
  }
  else if (kd.section === 'screamer') v = c.screamer?.[kd.param];
  else if (kd.section === 'amp') v = c.amp?.[kd.param];
  else if (kd.section === 'cab') v = c.cab?.[kd.param];
  else if (kd.section === 'delay') {
    v = c.delay?.[kd.param];
    if (kd.param === 'time') v = Number(v || 0) * 1000;
  }
  else if (kd.section === 'reverb') v = c.reverb?.[kd.param];
  else if (kd.section === 'master') v = c.master_volume;
  else if (kd.section === 'nam') v = state.nam?.[kd.param];
  if (!Number.isFinite(Number(v))) v = (kd.def || 0) / (kd.uiScale || 1);
  return Number(v);
}

function fmtKnob(kd, v) {
  const n = Number(v);
  if (kd.fmt === 'db') return (n > 0 ? '+' : '') + n.toFixed(Math.abs(kd.step) < 1 ? 1 : 0) + ' dB';
  if (kd.fmt === 'pct') return Math.round(n) + ' %';
  if (kd.fmt === 'ms') return Math.round(n) + ' ms';
  if (kd.fmt === 'hz') return n >= 1000 ? (n / 1000).toFixed(n >= 10000 ? 1 : 2) + ' kHz' : Math.round(n) + ' Hz';
  if (kd.fmt === 'st') return (n > 0 ? '+' : '') + Math.round(n) + ' st';
  return String(Math.round(n));
}

function polar(cx, cy, r, deg) {
  const a = ((deg - 90) * Math.PI) / 180;
  return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
}

function arcPath(cx, cy, r, start, end) {
  const [x1, y1] = polar(cx, cy, r, start);
  const [x2, y2] = polar(cx, cy, r, end);
  const large = Math.abs(end - start) > 180 ? 1 : 0;
  const sweep = end >= start ? 1 : 0;
  return `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${r} ${r} 0 ${large} ${sweep} ${x2.toFixed(2)} ${y2.toFixed(2)}`;
}

function markDirty(on) {
  state.dirty = !!on;
  const dot = $('dirtyDot');
  const save = $('stSave');
  if (dot) dot.classList.toggle('on', state.dirty);
  if (save) {
    save.textContent = state.dirty ? 'ยังไม่บันทึก' : 'บันทึกแล้ว';
    save.classList.toggle('dirty', state.dirty);
  }
}

function queueParam(kd, uiValue) {
  if (kd.section === 'nam' && !state.nam) {
    showToast('ยังไม่มี NAM model ในบล็อกนี้', true);
    return;
  }
  markDirty(true);
  const key = kd.section + '.' + kd.param;
  let rec = state.pending.get(key);
  if (!rec) {
    rec = { timer: null, value: null };
    state.pending.set(key, rec);
  }
  rec.value = toServer(kd, uiValue);
  if (rec.timer) return;
  rec.timer = setTimeout(async () => {
    const value = rec.value;
    state.pending.delete(key);
    try {
      const data = await api('/api/parameter', {
        method: 'POST',
        body: { section: kd.section, param: kd.param, value },
      });
      if (data.state) applyServerState(data.state);
    } catch (err) {
      showToast('ปรับค่าไม่สำเร็จ: ' + err.message, true);
    }
  }, 32);
}

async function sendParamNow(section, param, value) {
  try {
    const data = await api('/api/parameter', {
      method: 'POST',
      body: { section, param, value },
    });
    if (data.state) applyServerState(data.state);
    return data;
  } catch (err) {
    showToast('ปรับค่าไม่สำเร็จ: ' + err.message, true);
    return null;
  }
}

function makeKnob(kd, initialUi, opts = {}) {
  const root = document.createElement('div');
  root.className = 'knob-unit';

  const knob = document.createElement('div');
  knob.className = 'knob';
  knob.tabIndex = 0;
  knob.setAttribute('role', 'slider');
  knob.setAttribute('aria-label', kd.label);
  knob.setAttribute('aria-valuemin', String(kd.min));
  knob.setAttribute('aria-valuemax', String(kd.max));

  const svgNS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('viewBox', '0 0 100 100');
  svg.setAttribute('aria-hidden', 'true');
  svg.innerHTML = `
    <path class="k-track" d="${arcPath(50, 50, 42, -135, 135)}"></path>
    <path class="k-arc" d=""></path>
    <circle class="k-face" cx="50" cy="50" r="30"></circle>
    <g class="k-pointer"><line x1="50" y1="50" x2="50" y2="22"></line></g>`;
  knob.appendChild(svg);

  const labelEl = document.createElement('div');
  labelEl.className = 'k-label';
  labelEl.textContent = kd.label;

  const valueEl = document.createElement('div');
  valueEl.className = 'k-value';

  root.appendChild(knob);
  root.appendChild(labelEl);
  root.appendChild(valueEl);

  const arc = svg.querySelector('.k-arc');
  const pointer = svg.querySelector('.k-pointer line');

  const ctrl = {
    kd,
    root,
    knob,
    value: initialUi,
    dragging: false,
    surface: opts.surface || 'panel',
    blockId: opts.blockId || null,
    setValue(v, silent = false) {
      let val = clamp(Number(v), kd.min, kd.max);
      if (kd.step) val = Math.round(val / kd.step) * kd.step;
      val = clamp(val, kd.min, kd.max);
      ctrl.value = val;
      const t = (val - kd.min) / (kd.max - kd.min || 1);
      const angle = -135 + 270 * t;
      arc.setAttribute('d', t <= 0.0005 ? '' : arcPath(50, 50, 42, -135, angle));
      const [px, py] = polar(50, 50, 27, angle);
      pointer.setAttribute('x2', px.toFixed(2));
      pointer.setAttribute('y2', py.toFixed(2));
      valueEl.textContent = fmtKnob(kd, val);
      knob.setAttribute('aria-valuenow', String(val));
      if (!silent) queueParam(kd, val);
    },
  };

  ctrl.setValue(initialUi, true);

  let startY = 0;
  let startVal = 0;

  knob.addEventListener('pointerdown', (e) => {
    ctrl.dragging = true;
    startY = e.clientY;
    startVal = ctrl.value;
    knob.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  knob.addEventListener('pointermove', (e) => {
    if (!ctrl.dragging) return;
    const fine = e.shiftKey ? 0.2 : 1;
    const span = kd.max - kd.min;
    const delta = ((startY - e.clientY) / 170) * span * fine;
    ctrl.setValue(startVal + delta);
  });
  const endDrag = (e) => {
    ctrl.dragging = false;
    try { knob.releasePointerCapture(e.pointerId); } catch (err) { /* ignore */ }
  };
  knob.addEventListener('pointerup', endDrag);
  knob.addEventListener('pointercancel', endDrag);
  knob.addEventListener('wheel', (e) => {
    e.preventDefault();
    const dir = e.deltaY < 0 ? 1 : -1;
    ctrl.setValue(ctrl.value + dir * (kd.step || 1) * 2);
  }, { passive: false });
  knob.addEventListener('dblclick', () => ctrl.setValue(kd.def));
  knob.addEventListener('keydown', (e) => {
    const step = kd.step || 1;
    if (e.key === 'ArrowUp' || e.key === 'ArrowRight') { e.preventDefault(); ctrl.setValue(ctrl.value + step); }
    else if (e.key === 'ArrowDown' || e.key === 'ArrowLeft') { e.preventDefault(); ctrl.setValue(ctrl.value - step); }
    else if (e.key === 'Home') { e.preventDefault(); ctrl.setValue(kd.min); }
    else if (e.key === 'End') { e.preventDefault(); ctrl.setValue(kd.max); }
  });

  return ctrl;
}

function syncKnobs() {
  ['panel', 'face'].forEach((surface) => {
    state.knobControllers[surface].forEach((ctrl) => {
      if (ctrl.dragging) return;
      const server = readServer(ctrl.kd);
      const ui = toUi(ctrl.kd, server);
      if (Math.abs(ui - ctrl.value) > 0.001) ctrl.setValue(ui, true);
    });
  });
}

// ── library / preset table ───────────────────────────────────────────
function mappedPresets() {
  const builtins = state.presets.map((p) => ({
    id: p.id,
    type: 'preset',
    name: p.name || 'Preset',
    category: p.category || 'Preset',
    author: p.author || 'กดจนหลอนTone',
    amp: p.settings?.amp?.model || 'DSP Amp',
    cab: p.settings?.cab?.ir_name || '',
    gain: Number(p.settings?.amp?.gain ?? 0.55),
    raw: p,
  }));
  const t3k = state.t3kPresets.map((p) => ({
    id: p.id,
    type: 't3k',
    name: p.name || p.id,
    category: p.category || 'TONE3000',
    author: p.author || 'TONE3000',
    amp: p.amp_name || p.amp_model || 'NAM Capture',
    cab: p.cab_name || p.cab_model || '',
    gain: Number(p.gain ?? 0.6),
    raw: p,
  }));
  return [...t3k, ...builtins];
}

function favKey(item) {
  return item.type + ':' + item.id;
}

function filteredPresets() {
  let list = mappedPresets();
  if (state.filter === 'mine') list = list.filter((p) => p.type === 'preset' && (p.author === 'User' || String(p.id).startsWith('user_')));
  else if (state.filter === 't3k') list = list.filter((p) => p.type === 't3k');
  else if (state.filter === 'fav') list = list.filter((p) => state.favorites.has(favKey(p)));
  const q = state.query.trim().toLowerCase();
  if (q) {
    list = list.filter((p) => [p.name, p.amp, p.cab, p.category, p.author].join(' ').toLowerCase().includes(q));
  }
  return list;
}

const LIB_DEFS = [
  { id: 'all', label: 'ทั้งหมด', icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>' },
  { id: 'mine', label: 'ของฉัน', icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 20v-1a6 6 0 0 1 12 0v1"/><circle cx="10" cy="8" r="4"/><path d="M17 11l1.5 3 3 .5-2.2 2.2.5 3-2.8-1.5-2.8 1.5.5-3L13 13.5l3-.5z"/></svg>' },
  { id: 't3k', label: 'จาก TONE3000', icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="8"/><path d="M4 12h16M12 4c3 3.5 3 12.5 0 16M12 4c-3 3.5-3 12.5 0 16"/></svg>' },
  { id: 'fav', label: 'ชื่นชอบ', icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3l2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3 6.4 20.2l1.1-6.2L3 9.6l6.2-.9z"/></svg>' },
];

function renderLib() {
  const el = $('libList');
  if (!el) return;
  const all = mappedPresets();
  const counts = {
    all: all.length,
    mine: all.filter((p) => p.type === 'preset' && (p.author === 'User' || String(p.id).startsWith('user_'))).length,
    t3k: all.filter((p) => p.type === 't3k').length,
    fav: all.filter((p) => state.favorites.has(favKey(p))).length,
  };
  el.innerHTML = LIB_DEFS.map((d) => `
    <button class="lib-item ${state.filter === d.id ? 'active' : ''}" data-filter="${d.id}">
      <span class="lib-ic">${d.icon}</span>
      <span>${d.label}</span>
      <span class="lib-count">${counts[d.id] ?? 0}</span>
    </button>`).join('');
  el.querySelectorAll('.lib-item').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.filter = btn.dataset.filter;
      renderLib();
      renderTable();
    });
  });
}

function starSVG() {
  return '<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1"><path d="M12 3l2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3 6.4 20.2l1.1-6.2L3 9.6l6.2-.9z"/></svg>';
}

function gainBarHTML(gain) {
  const n = 10;
  const lit = Math.round(clamp(Number(gain) || 0, 0, 1) * n);
  let html = '<span class="gaincell"><span class="gainbar">';
  for (let i = 0; i < n; i++) {
    const cls = i < lit ? (i >= 8 ? 'on hot' : 'on') : '';
    html += `<i class="${cls}"></i>`;
  }
  html += `</span><span class="gainval">${(Number(gain) * 10).toFixed(1)}</span></span>`;
  return html;
}

function renderTable() {
  const body = $('presetBody');
  if (!body) return;
  const list = filteredPresets();
  const count = $('rowCount');
  if (count) count.textContent = `${list.length} รายการ`;
  const cta = $('t3k-cta');
  if (cta) cta.classList.toggle('hidden', state.filter !== 't3k');

  if (!list.length) {
    body.innerHTML = `<tr class="empty-row"><td colspan="5">ไม่พบพรีเซ็ตที่ตรงเงื่อนไข — ลองเปลี่ยนหมวดหรือคำค้น</td></tr>`;
    return;
  }

  body.innerHTML = list.map((item) => {
    const key = favKey(item);
    const fav = state.favorites.has(key);
    const selected = key === state.selectedKey;
    return `
      <tr data-key="${esc(key)}" class="${selected ? 'selected' : ''}">
        <td>
          <div class="pname" title="${esc(item.name)}">${esc(item.name)}</div>
          <div class="psrc" title="${esc(item.author)}${item.type === 't3k' ? ' · TONE3000' : ''}">${esc(item.author)}${item.type === 't3k' ? ' · <span class="src-t3k">TONE3000</span>' : ''}</div>
        </td>
        <td class="camp" title="${esc(item.amp)}">${esc(item.amp)}</td>
        <td>${gainBarHTML(item.gain)}</td>
        <td class="cdate">${item.type === 't3k' ? 'NAM' : 'PRESET'}</td>
        <td><button class="star-btn ${fav ? 'fav' : ''}" data-fav="${esc(key)}" aria-label="ชื่นชอบ">${starSVG()}</button></td>
      </tr>`;
  }).join('');

  body.querySelectorAll('tr[data-key]').forEach((row) => {
    row.addEventListener('click', (e) => {
      if (e.target.closest('[data-fav]')) return;
      const item = list.find((p) => favKey(p) === row.dataset.key);
      if (item) loadPreset(item);
    });
  });

  body.querySelectorAll('[data-fav]').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const key = btn.dataset.fav;
      if (state.favorites.has(key)) state.favorites.delete(key);
      else state.favorites.add(key);
      localStorage.setItem('tone.favorites', JSON.stringify([...state.favorites]));
      renderLib();
      renderTable();
    });
  });
}

function findItemByKey(key) {
  return mappedPresets().find((p) => favKey(p) === key) || null;
}

function updateTopPreset(item) {
  if (!item) return;
  const name = item.name || 'Preset';
  const sub = [item.category, item.amp, item.type === 't3k' ? 'TONE3000' : ''].filter(Boolean).join(' • ');
  if ($('curName')) $('curName').textContent = name;
  if ($('curSub')) $('curSub').textContent = sub;
  if ($('stPreset')) $('stPreset').textContent = name;
}

function drow(k, v, mono = false) {
  return `<div class="d-row"><span class="k">${esc(k)}</span><span class="v ${mono ? 'mono' : ''}">${esc(v)}</span></div>`;
}

function renderDetails(item) {
  const el = $('details');
  if (!el) return;

  if (!item) {
    el.innerHTML = `
      <div class="d-label">WORKSTATION</div>
      <div class="d-name">เลือกพรีเซ็ตจากคลัง</div>
      <div class="d-tags">
        <span class="tag gold">NAM A2</span>
        <span class="tag">8-block chain</span>
      </div>
      <p class="d-comment">คลิกแถวในตารางเพื่อโหลดพรีเซ็ต หรือกดไทล์ใน Signal Chain เพื่อปรับค่าแต่ละบล็อก</p>
      <div class="d-sec">
        <h4>TONE3000 PLUGIN DNA</h4>
        ${drow('Gate', 'Threshold / Release / Hold / Range')}
        ${drow('IR CAB', 'Low Cut / High Cut / Mix')}
        ${drow('Pitch', 'Pitch / Glide / Mix')}
        ${drow('Local files', 'Load File / Load Folder')}
        ${drow('Library', 'Native TONE3000 search')}
      </div>
      <button class="d-t3k" data-action="open-t3k">ค้นหาเสียงจาก TONE3000</button>`;
    bindDetailActions();
    return;
  }

  const typeLabel = item.type === 't3k' ? 'TONE3000 PRESET' : (item.type === 't3k-live' ? 'TONE3000 LIVE LOAD' : 'PRESET');
  const tags = [
    `<span class="tag gold">${esc(item.category || 'Preset')}</span>`,
    `<span class="tag">${esc(item.author || 'กดจนหลอนTone')}</span>`,
  ].join('');

  let sections = '';
  if (item.type === 't3k-live' && state.t3kLoaded) {
    const l = state.t3kLoaded;
    sections = `
      <div class="d-sec">
        <h4>LOADED TONE</h4>
        ${drow('Gear', t3kGearLabel(l.gear))}
        ${drow('Creator', l.creator || 'TONE3000')}
        ${drow('Model', l.model || '—')}
        ${drow('Architecture', (l.fallback_a1 ? 'A1 (fallback)' : 'A' + (l.architecture || '2')) + ' · ' + (l.quality || 'lite'))}
      </div>
      <div class="d-sec">
        <h4>CHAIN</h4>
        ${(state.nam?.stages || []).map((s) => `<div class="d-row"><span class="k">${esc(s.gear_type || 'stage')}</span><span class="v">${esc(s.title || 'NAM')}</span></div>`).join('') || '<p class="d-comment">NAM capture</p>'}
      </div>`;
  } else if (item.type === 't3k') {
    const p = item.raw || {};
    sections = `
      <div class="d-sec">
        <h4>AMP / CAB</h4>
        ${drow('Amp', item.amp || '—')}
        ${drow('Cab', item.cab || '—')}
        ${drow('Gain', (Number(item.gain) * 10).toFixed(1) + ' / 10')}
        ${drow('IR mic', p.ir_mic || '—')}
      </div>
      <div class="d-sec">
        <h4>TONE3000 PACKAGE</h4>
        ${drow('Category', item.category || '—')}
        ${drow('Has NAM', p.has_nam ? 'yes' : 'no')}
        ${drow('IR duration', p.ir_duration_ms ? p.ir_duration_ms + ' ms' : '—')}
        ${drow('File size', p.file_size_kb ? p.file_size_kb + ' KB' : '—')}
      </div>`;
  } else {
    const s = item.raw?.settings || {};
    sections = `
      <div class="d-sec">
        <h4>AMP</h4>
        ${drow('Model', s.amp?.model || item.amp || 'DSP Amp')}
        ${drow('Gain', (Number(s.amp?.gain ?? item.gain) * 10).toFixed(1) + ' / 10')}
        ${drow('Bass / Mid / Treble', [s.amp?.bass, s.amp?.mid, s.amp?.treble].map((v) => v === undefined ? '—' : Math.round(Number(v) * 100) + '%').join(' / '))}
      </div>
      <div class="d-sec">
        <h4>CAB &amp; FX</h4>
        ${drow('Cabinet', s.cab?.ir_name || item.cab || '—')}
        ${drow('Low / High Cut', (s.cab?.lowcut ?? 20) + ' Hz / ' + (s.cab?.highcut ?? 20000) + ' Hz')}
        ${drow('Drive', s.screamer?.enabled ? 'ON · ' + Math.round(Number(s.screamer.drive || 0) * 100) + '%' : 'OFF')}
        ${drow('Reverb', s.reverb?.enabled ? Math.round(Number(s.reverb.mix || 0) * 100) + '% mix' : 'OFF')}
      </div>`;
  }

  el.innerHTML = `
    <div class="d-label">${typeLabel}</div>
    <div class="d-name">${esc(item.name)}</div>
    <div class="d-tags">${tags}</div>
    ${sections}
    <button class="d-t3k" data-action="open-t3k">ค้นหาเสียงจาก TONE3000</button>`;

  bindDetailActions();
}

function bindDetailActions() {
  const el = $('details');
  if (!el) return;
  el.querySelectorAll('[data-action="open-t3k"]').forEach((btn) => {
    btn.addEventListener('click', openT3K);
  });
}

// ── load / save presets ──────────────────────────────────────────────
async function loadPresetLibrary() {
  try {
    const [p, t] = await Promise.all([
      api('/api/presets'),
      api('/api/tone3000/presets'),
    ]);
    state.presets = p.presets || [];
    state.t3kPresets = t.presets || [];
    renderLib();
    renderTable();
    if (state.selectedKey) {
      const item = findItemByKey(state.selectedKey);
      if (item) {
        updateTopPreset(item);
        renderDetails(item);
      }
    }
  } catch (err) {
    showToast('โหลดคลังพรีเซ็ตไม่สำเร็จ: ' + err.message, true);
    renderLib();
    renderTable();
  }
}

async function loadPreset(item, opts = {}) {
  if (!item) return;
  try {
    let data;
    if (item.type === 't3k') {
      data = await api('/api/tone3000/load', {
        method: 'POST',
        body: { id: item.id },
      });
      state.t3kLoaded = null;
    } else {
      data = await api('/api/preset/load', {
        method: 'POST',
        body: { preset_id: item.id },
      });
      state.t3kLoaded = null;
    }

    if (data.state) applyServerState(data.state, { forceRender: true });
    if (!data.state?.nam) {
      state.namTitle = '';
      state.namFile = '';
    }

    state.selectedId = item.id;
    state.selectedType = item.type;
    state.selectedKey = favKey(item);
    localStorage.setItem('tone.lastPresetKey', state.selectedKey);
    markDirty(false);
    updateTopPreset(item);
    renderTable();
    renderDetails(item);
    renderChain();
    renderPanel();
    renderFaceStrip();
    if (!opts.silent) showToast('โหลด “' + item.name + '” แล้ว');
  } catch (err) {
    showToast('โหลดพรีเซ็ตไม่สำเร็จ: ' + err.message, true);
  }
}

async function savePreset(asNew) {
  const current = state.selectedKey ? findItemByKey(state.selectedKey) : null;
  const isNew = asNew || !current || current.type !== 'preset';
  let name;
  if (isNew) {
    name = askText('ชื่อพรีเซ็ตใหม่', current ? current.name + ' Copy' : 'พรีเซ็ตใหม่');
    if (!name) return;
  } else {
    name = askText('บันทึกทับพรีเซ็ต', current.name);
    if (!name) return;
  }
  const id = isNew ? 'user_' + Date.now() : current.id;
  const category = current?.category || 'User';
  try {
    await api('/api/preset/save', {
      method: 'POST',
      body: { id, name, category, author: 'User' },
    });
    markDirty(false);
    await loadPresetLibrary();
    const saved = mappedPresets().find((p) => p.type === 'preset' && p.id === id);
    if (saved) {
      state.selectedId = saved.id;
      state.selectedType = saved.type;
      state.selectedKey = favKey(saved);
      updateTopPreset(saved);
      renderTable();
      renderDetails(saved);
    }
    showToast('บันทึกพรีเซ็ต “' + name + '” แล้ว');
  } catch (err) {
    showToast('บันทึกไม่สำเร็จ: ' + err.message, true);
  }
}

// ── chain / panel ────────────────────────────────────────────────────
function renderChain() {
  const chain = $('chain');
  if (!chain) return;
  chain.innerHTML = '';

  visibleBlocks().forEach((b) => {
    const enabled = blockEnabled(b.id);
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'chain-block'
      + (state.block === b.id ? ' selected' : '')
      + (enabled ? '' : ' bypassed');
    btn.dataset.block = b.id;
    btn.title = blockEn(b.id) + ' · ' + blockTh(b.id);
    const power = b.canBypass
      ? `<span class="cb-power ${enabled ? '' : 'off'}" data-power="${b.id}" role="button" aria-label="เปิด/ปิด ${blockEn(b.id)}"><i></i></span>`
      : '';
    const t3kBadge = (b.id === 'amp' && state.t3kLoaded) ? '<span class="cb-t3k">T3K</span>' : '';
    const gearBadge = (b.id === 'amp' && state.nam) ? `<span class="cb-gear">${namGearType() === 'amp-cab' ? 'AMP+CAB' : 'NAM'}</span>` : '';
    btn.innerHTML = `${power}${t3kBadge}<span class="cb-icon">${blockIcon(b.id)}</span><span class="cb-en">${blockEn(b.id)}</span><span class="cb-sub">${esc(blockSubtitle(b.id))}</span>${gearBadge}`;
    chain.appendChild(btn);
  });

  const add = document.createElement('button');
  add.type = 'button';
  add.className = 'chain-empty';
  add.id = 'chain-add-tone';
  add.innerHTML = '<span class="plus">+</span><small>ค้นหาเสียง<br>TONE3000</small>';
  add.addEventListener('click', openT3K);
  chain.appendChild(add);

  const hint = $('pitch-hint');
  if (hint) {
    hint.textContent = state.showPitch ? '' : 'PITCH ถูกซ่อน · เปิดใน Settings';
    hint.style.cursor = state.showPitch ? 'default' : 'pointer';
    hint.onclick = state.showPitch ? null : openSettings;
  }
}

function updateChainLive() {
  document.querySelectorAll('#chain .chain-block').forEach((tile) => {
    const id = tile.dataset.block;
    const enabled = blockEnabled(id);
    tile.classList.toggle('bypassed', !enabled);
    const pw = tile.querySelector('.cb-power');
    if (pw) pw.classList.toggle('off', !enabled);
    const sub = tile.querySelector('.cb-sub');
    if (sub) sub.textContent = blockSubtitle(id);
  });
}

function selectBlock(id) {
  state.block = id;
  document.querySelectorAll('#chain .chain-block').forEach((tile) => {
    tile.classList.toggle('selected', tile.dataset.block === id);
  });
  renderPanel();
}

function renderPanel() {
  const b = blockById(state.block);
  if ($('pbEn')) $('pbEn').textContent = blockEn(b.id);
  if ($('pbTh')) $('pbTh').textContent = blockTh(b.id);
  const bypass = $('bypassToggle');
  if (bypass) {
    const can = b.canBypass;
    bypass.style.visibility = can ? 'visible' : 'hidden';
    const enabled = blockEnabled(b.id);
    bypass.setAttribute('aria-pressed', String(enabled));
    if ($('bypassLabel')) $('bypassLabel').textContent = enabled ? 'เปิดใช้งาน' : 'บายพาส';
  }

  const knobs = $('knobs');
  if (!knobs) return;
  knobs.innerHTML = '';
  state.knobControllers.panel = [];
  const defs = knobsForBlock(b.id);
  if (!defs.length) {
    knobs.innerHTML = '<div class="t3k-empty">บล็อกนี้ไม่มีพารามิเตอร์ให้ปรับ</div>';
  } else {
    defs.forEach((kd) => {
      const ctrl = makeKnob(kd, toUi(kd, readServer(kd)), { surface: 'panel', blockId: b.id });
      knobs.appendChild(ctrl.root);
      state.knobControllers.panel.push(ctrl);
    });
  }
  renderPanelSide();
}

function renderPanelSide() {
  const side = $('panelSide');
  if (!side) return;
  const b = blockById(state.block);

  if (b.id === 'input') {
    side.innerHTML = `
      <div class="ps-title">INPUT CALIBRATION</div>
      <div class="ps-note">Trim เป็นจุดเริ่มต้นของทั้งเชน ปรับให้ระดับกีตาร์พอดีกับออดิโออินเทอร์เฟซก่อนเข้า GATE และ NAM</div>
      ${drow('Tip', 'กด Trim แล้วลากขึ้น/ลง หรือดับเบิลคลิกเพื่อรีเซ็ต')}`;
    return;
  }
  if (b.id === 'gate') {
    side.innerHTML = `
      <div class="ps-title">NOISE GATE · 4 KNOBS</div>
      <div class="ps-note">Threshold, Release, Hold และ Range ทำงานครบเหมือนปลั๊กอิน TONE3000 — เกตปิดแน่นโดยไม่กินหางเสียงตอนเล่นเบา</div>
      ${drow('Threshold', 'จุดเริ่มเปิดเกต')}
      ${drow('Release', 'ความเร็วปิดหลังเสียงจบ')}
      ${drow('Hold', 'หน่วงก่อนเริ่มปิด')}
      ${drow('Range', 'ระดับเสียงต่ำสุดที่ถูกปิด')}`;
    return;
  }
  if (b.id === 'pitch') {
    side.innerHTML = `
      <div class="ps-title">PITCH SHIFT · ±24 ST</div>
      <div class="ps-note">Pitch เลื่อนเสียงได้ ±24 เซมิโทน, Glide ทำให้เปลี่ยนโน้ตแบบพอร์ตาเมนโต และ Mix ผสมเสียงdry/wet</div>
      ${drow('Glide', '0% = ทันที · 100% = นุ่มสุด')}
      ${drow('Setting', 'ซ่อนเป็นค่าเริ่มต้น — เปิด Show Pitch Shift')}
      <div class="ps-actions"><button class="mini-btn" data-action="open-settings">เปิดใน Settings</button></div>`;
    return;
  }
  if (b.id === 'drive') {
    side.innerHTML = `
      <div class="ps-title">DRIVE · PEDAL STAGE</div>
      <div class="ps-note">โอเวอร์ไดรฟ์อยู่หน้า NAM AMP จริง (ไม่ถูกข้าม) ใช้ผลักแอมป์ให้แตกมากขึ้นโดยไม่เปลี่ยนโมเดล</div>
      ${drow('Drive', 'ปริมาณเกน')}
      ${drow('Tone', 'ความสว่าง')}
      ${drow('Level', 'ระดับออกจากบล็อก')}`;
    return;
  }
  if (b.id === 'amp') {
    if (state.nam) {
      const stages = state.nam.stages || [];
      const title = state.namTitle || stages.map((s) => s.title).filter(Boolean).join(' → ') || 'NAM capture';
      const gear = namGearType();
      side.innerHTML = `
        <div class="ps-title">NAM CHAIN</div>
        <div class="ps-file">${esc(title)}</div>
        ${drow('Stages', String(stages.length || 1))}
        ${drow('Gear', gear === 'amp-cab' ? 'Amp + Cab capture' : gear === 'pedal' ? 'Pedal / outboard' : 'Amp head')}
        ${drow('Cab in capture', state.nam.includes_cab ? 'YES — ปิด IR CAB เพื่อไม่ตู้ซ้อน' : 'NO')}
        ${drow('Input gain', (state.nam.input_gain_db ?? 0).toFixed(1) + ' dB')}
        <div class="ps-actions">
          <button class="mini-btn" data-action="load-nam">Load NAM</button>
          <button class="mini-btn" data-action="open-t3k">TONE3000</button>
        </div>
        <div class="seg quality-seg">
          <button data-quality="lite" class="${state.namQuality === 'lite' ? 'active' : ''}">Lite</button>
          <button data-quality="full" class="${state.namQuality === 'full' ? 'active' : ''}">Full</button>
        </div>`;
    } else {
      side.innerHTML = `
        <div class="ps-title">DSP AMP</div>
        <div class="ps-file">${esc(state.live?.amp?.model || 'Amp')}</div>
        <div class="ps-note">ยังไม่มี NAM model — ใช้ DSP amp จำลองอยู่ โหลด .nam จากเครื่องหรือเลือกจาก TONE3000 เพื่อแทนที่</div>
        <div class="ps-actions">
          <button class="mini-btn" data-action="load-nam">Load NAM</button>
          <button class="mini-btn" data-action="open-t3k">TONE3000</button>
        </div>
        <div class="seg quality-seg">
          <button data-quality="lite" class="${state.namQuality === 'lite' ? 'active' : ''}">Lite</button>
          <button data-quality="full" class="${state.namQuality === 'full' ? 'active' : ''}">Full</button>
        </div>`;
    }
    return;
  }
  if (b.id === 'cab') {
    side.innerHTML = `
      <div class="ps-title">IR CAB · PER-BLOCK EQ</div>
      <div class="ps-file">${esc(state.live?.cab?.ir_name || 'Default IR')}</div>
      <div class="ps-note">Low Cut / High Cut เป็นparametric EQ ประจำบล็อก IR CAB ตามแนวคิดปลั๊กอิน TONE3000 ปรับได้โดยไม่กระทบเสียงรวม</div>
      ${drow('Low Cut', 'ตัดความถี่ต่ำ / rumble')}
      ${drow('High Cut', 'ตัดความถี่สูง / fizz')}
      ${drow('Mix', 'dry / wet ของ IR')}
      <div class="ps-actions">
        <button class="mini-btn" data-action="load-ir">Load IR</button>
        <button class="mini-btn" data-action="open-t3k">TONE3000</button>
      </div>`;
    return;
  }
  if (b.id === 'reverb') {
    side.innerHTML = `
      <div class="ps-title">REVERB · SPACE</div>
      <div class="ps-note">ปรับ decay, mix และ tone ของห้อง reverberation แบบเรียลไทม์</div>
      ${drow('Type', state.live?.reverb?.type || 'plate')}
      ${drow('Tip', 'ใช้ Mix ต่ำ ๆ สำหรับ rhythm')}`;
    return;
  }
  if (b.id === 'output') {
    side.innerHTML = `
      <div class="ps-title">OUTPUT · MASTER</div>
      <div class="ps-note">Master volume อยู่ท้ายเชนหลัง CAB และ REVERB ใช้คุมระดับออกโดยไม่เปลี่ยนเกนของแอมป์</div>
      ${drow('Tip', 'ถ้าเสียงแตกเกิน ให้ลดที่ AMP Volume ก่อน')}`;
    return;
  }
}

function renderFaceStrip() {
  const fs = $('faceStrip');
  if (!fs) return;
  fs.innerHTML = '';
  state.knobControllers.face = [];

  const groups = [];
  groups.push({ block: 'input', keys: ['trim'] });
  groups.push({ block: 'gate', keys: ['threshold'] });
  if (state.showPitch) groups.push({ block: 'pitch', keys: ['semitones', 'glide'] });
  if (state.nam) groups.push({ block: 'amp', keys: ['input_gain'] });
  else groups.push({ block: 'amp', keys: ['bass', 'mid', 'treble'] });
  groups.push({ block: 'cab', keys: ['lowcut', 'highcut'] });
  groups.push({ block: 'output', keys: ['volume'] });

  let first = true;
  groups.forEach((g) => {
    const b = blockById(g.block);
    const defs = knobsForBlock(g.block).filter((kd) => g.keys.includes(kd.key));
    if (!defs.length) return;
    if (!first) {
      const sep = document.createElement('div');
      sep.className = 'fs-sep';
      fs.appendChild(sep);
    }
    first = false;
    const grp = document.createElement('div');
    grp.className = 'fs-group';
    grp.dataset.block = g.block;

    defs.forEach((kd, index) => {
      const wrap = document.createElement('div');
      wrap.className = 'fs-knob';
      if (index === 0) {
        const name = document.createElement('div');
        name.className = 'fs-block-name';
        name.textContent = blockEn(g.block);
        wrap.appendChild(name);
      }
      const ctrl = makeKnob(kd, toUi(kd, readServer(kd)), { surface: 'face', blockId: g.block });
      wrap.appendChild(ctrl.root);
      grp.appendChild(wrap);
      state.knobControllers.face.push(ctrl);
    });

    grp.addEventListener('click', (e) => {
      if (e.target.closest('.knob')) return;
      selectBlock(g.block);
    });
    fs.appendChild(grp);
  });
}

// ── toggle block / status ────────────────────────────────────────────
async function toggleBlock(id) {
  const b = blockById(id);
  if (!b.canBypass) return;
  const enabled = !blockEnabled(id);
  let section = b.section;
  if (id === 'amp' && state.nam) section = 'nam';
  const data = await sendParamNow(section, 'enabled', enabled);
  if (data) {
    if (id === 'pitch' && !state.showPitch) state.showPitch = true;
    renderChain();
    renderPanel();
    renderFaceStrip();
  }
}

function updateMeter(el, pct) {
  if (!el) return;
  const leds = el.children;
  const n = leds.length;
  const lit = Math.round((clamp(Number(pct) || 0, 0, 100) / 100) * n);
  for (let i = 0; i < n; i++) {
    let cls = '';
    if (i < lit) cls = i >= n * 0.86 ? 'on-r' : (i >= n * 0.68 ? 'on-y' : 'on-g');
    leds[i].className = cls;
  }
}

function buildMeter(el, count = 16) {
  if (!el) return;
  el.innerHTML = Array.from({ length: count }, () => '<i></i>').join('');
}

function updateStatus(server) {
  state.lastServer = server;
  const sr = Number(server.sample_rate || 48000);
  const bs = Number(server.block_size || 128);
  const stats = server.audio_stats || {};
  const deadline = Number(stats.deadline_ms || (bs / sr * 1000));
  const hw = stats.stream_latency || {};
  const sys = server.system || {};
  const hwLabel = hw.reported_io_ms == null ? 'HW I/O —' : `HW I/O ${Number(hw.reported_io_ms).toFixed(2)} ms`;

  if ($('spec-sr')) $('spec-sr').textContent = (sr / 1000).toFixed(1) + ' kHz';
  if ($('spec-block')) $('spec-block').textContent = bs + ' smp';
  if ($('spec-lat')) $('spec-lat').textContent = hw.reported_io_ms == null ? deadline.toFixed(2) + ' ms' : Number(hw.reported_io_ms).toFixed(2) + ' ms';
  if ($('status-audio-perf')) {
    $('status-audio-perf').textContent = `SR ${sr.toLocaleString()} Hz · Buffer ${bs} (${deadline.toFixed(2)} ms) · ${hwLabel} · Max CB ${stats.callback_ms_max ?? 0} ms · XRuns ${Object.values(stats.xruns || {}).reduce((a, b) => a + Number(b || 0), 0)}`;
  }
  if ($('status-system-telemetry')) {
    $('status-system-telemetry').textContent = `CPU ${sys.cpu_percent ?? 0}% · RAM ${sys.ram_mb ?? 0} MB`;
  }
  if ($('status-engine-text')) {
    const devIn = server.input_device ?? 'default';
    const devOut = server.output_device ?? 'default';
    $('status-engine-text').textContent = `Audio Engine: ${server.is_running ? 'RUNNING' : 'STOPPED'} · ${devIn} → ${devOut}`;
  }
  if ($('side-engine-state')) {
    $('side-engine-state').textContent = server.is_running ? 'RUNNING' : 'STOPPED';
    $('side-engine-state').style.color = server.is_running ? 'var(--ok)' : 'var(--hot)';
  }
  const power = $('btn-power');
  if (power) power.classList.toggle('on', !!server.is_running);

  if ($('modal-sr-readout')) $('modal-sr-readout').textContent = sr.toLocaleString() + ' Hz';
  if ($('modal-buf-readout')) $('modal-buf-readout').textContent = bs + ' samples';

  updateMeter($('meterIn'), server.input_meter);
  updateMeter($('meterOut'), server.output_meter);
  updateTuner(server);

  const badge = $('engine-badge');
  if (badge) badge.textContent = state.nam ? ('NAM A' + (state.namArch || '2')) : 'DSP AMP';
}

function applyServerState(server, opts = {}) {
  if (!server) return;
  const prevNamKey = state.namKey;
  state.live = server.chain || {};
  state.nam = server.nam || null;
  state.namKey = state.nam
    ? ((state.nam.stages || []).map((s) => s.title || '').join('|') + '|' + (state.nam.enabled ? '1' : '0') + '|' + (state.nam.includes_cab ? 'cab' : ''))
    : 'none';
  state.isRunning = !!server.is_running;
  if (server.input_device !== undefined) state.selectedIn = server.input_device;
  if (server.output_device !== undefined) state.selectedOut = server.output_device;

  if (prevNamKey !== state.namKey || opts.forceRender) {
    renderChain();
    renderPanel();
    renderFaceStrip();
  } else {
    updateChainLive();
    syncKnobs();
  }
  updateStatus(server);
}

// ── tuner ────────────────────────────────────────────────────────────
function resetTuner() {
  if ($('tuner-note')) $('tuner-note').textContent = '--';
  if ($('tuner-freq')) $('tuner-freq').textContent = '0.0 Hz';
  if ($('tuner-needle')) $('tuner-needle').style.left = '50%';
  if ($('tuner-status')) {
    $('tuner-status').textContent = 'PLAY STRING';
    $('tuner-status').style.color = 'var(--muted)';
  }
}

function updateTuner(server) {
  const tuner = server.tuner;
  if (!tuner) {
    if (state.tunerActive) resetTuner();
    return;
  }
  state.tunerActive = true;
  $('tuner-display')?.classList.remove('hidden');
  const cents = Number(tuner.cents || 0);
  const hasNote = !!tuner.note && tuner.note !== '--';
  if ($('tuner-note')) $('tuner-note').textContent = hasNote ? tuner.note : '--';
  if ($('tuner-freq')) $('tuner-freq').textContent = Number(tuner.freq || 0).toFixed(1) + ' Hz';
  if ($('tuner-needle')) $('tuner-needle').style.left = clamp(50 + cents, 0, 100) + '%';
  if ($('tuner-status')) {
    const inTune = hasNote && Math.abs(cents) < 3;
    $('tuner-status').textContent = !hasNote ? 'PLAY STRING' : (inTune ? 'IN TUNE' : (cents > 0 ? 'SHARP' : 'FLAT'));
    $('tuner-status').style.color = !hasNote ? 'var(--muted)' : (inTune ? 'var(--ok)' : 'var(--gold)');
  }
}

async function toggleTuner() {
  const active = !state.tunerActive;
  try {
    const data = await api('/api/tuner/toggle', { method: 'POST', body: { active } });
    state.tunerActive = !!data.tuner_active;
    $('tuner-display')?.classList.toggle('hidden', !state.tunerActive);
    if (!state.tunerActive) resetTuner();
  } catch (err) {
    showToast('เปิดจูนเนอร์ไม่สำเร็จ: ' + err.message, true);
  }
}

// ── settings / devices ───────────────────────────────────────────────
function fillSettingsDevices() {
  const inSel = $('modal-select-in');
  const outSel = $('modal-select-out');
  if (!inSel || !outSel) return;
  const inputs = state.devices.inputs || [];
  const outputs = state.devices.outputs || [];
  inSel.innerHTML = inputs.map((d) => `<option value="${d.id}" ${d.id === state.selectedIn ? 'selected' : ''}>${esc(d.name)}</option>`).join('') || '<option value="">— none —</option>';
  outSel.innerHTML = outputs.map((d) => `<option value="${d.id}" ${d.id === state.selectedOut ? 'selected' : ''}>${esc(d.name)}</option>`).join('') || '<option value="">— none —</option>';
}

async function loadDevices() {
  try {
    const data = await api('/api/devices');
    const devices = data.devices || [];
    state.devices.inputs = devices.filter((d) => Number(d.inputs) > 0);
    state.devices.outputs = devices.filter((d) => Number(d.outputs) > 0);
    state.selectedIn = data.selected_in ?? null;
    state.selectedOut = data.selected_out ?? null;
    fillSettingsDevices();
  } catch (err) {
    showToast('โหลดรายการอุปกรณ์ไม่สำเร็จ: ' + err.message, true);
  }
}

function openSettings() {
  fillSettingsDevices();
  if ($('sw-show-pitch')) $('sw-show-pitch').checked = state.showPitch;
  const lite = $('btn-quality-lite');
  const full = $('btn-quality-full');
  if (lite) lite.classList.toggle('active', state.namQuality === 'lite');
  if (full) full.classList.toggle('active', state.namQuality === 'full');
  $('modal-settings')?.classList.remove('hidden');
}

function closeSettings() {
  $('modal-settings')?.classList.add('hidden');
}

async function applySettings() {
  const inId = $('modal-select-in')?.value;
  const outId = $('modal-select-out')?.value;
  try {
    const data = await api('/api/start', {
      method: 'POST',
      body: { input_id: inId === '' ? null : Number(inId), output_id: outId === '' ? null : Number(outId) },
    });
    if (data.state) applyServerState(data.state, { forceRender: true });
    closeSettings();
    showToast(data.success ? 'เริ่มเสียงเอ็นจินด้วยอุปกรณ์ใหม่แล้ว' : (data.message || 'เริ่มเอ็นจินไม่สำเร็จ'), !data.success);
  } catch (err) {
    showToast('Apply settings ไม่สำเร็จ: ' + err.message, true);
  }
}

async function setNamQuality(q) {
  state.namQuality = q;
  localStorage.setItem('tone.namQuality', q);
  await sendParamNow('nam', 'quality', q);
  const lite = $('btn-quality-lite');
  const full = $('btn-quality-full');
  if (lite) lite.classList.toggle('active', q === 'lite');
  if (full) full.classList.toggle('active', q === 'full');
  renderPanel();
  showToast('NAM quality = ' + q + ' (มีผลเมื่อโหลดโมเดลครั้งถัดไป)');
}

function setShowPitch(on) {
  state.showPitch = !!on;
  localStorage.setItem('tone.showPitch', state.showPitch ? '1' : '0');
  if (!state.showPitch) {
    if (state.block === 'pitch') state.block = 'amp';
    if (state.live?.pitch?.enabled) sendParamNow('pitch', 'enabled', false);
  }
  renderChain();
  renderPanel();
  renderFaceStrip();
}

// ── local files / context menu ───────────────────────────────────────
function openCtx(blockId, x, y) {
  const menu = $('ctx-menu');
  if (!menu) return;
  state.ctxBlock = blockId;
  const b = blockById(blockId);
  if ($('ctx-title')) $('ctx-title').textContent = blockEn(b.id) + ' · ' + blockTh(b.id);
  const fileBtn = $('ctx-load-file');
  const folderBtn = $('ctx-load-folder');
  const clearBtn = $('ctx-clear-file');
  const hasFile = blockId === 'amp' ? !!state.nam : blockId === 'cab';
  [fileBtn, folderBtn].forEach((btn) => btn?.classList.remove('disabled'));
  if (clearBtn) clearBtn.classList.toggle('disabled', !hasFile);
  menu.classList.add('open');
  const rect = menu.getBoundingClientRect();
  menu.style.left = Math.min(x, window.innerWidth - rect.width - 10) + 'px';
  menu.style.top = Math.min(y, window.innerHeight - rect.height - 10) + 'px';
}

function closeCtx() {
  $('ctx-menu')?.classList.remove('open');
  state.ctxBlock = null;
}

function pickFile(blockId, mode) {
  state.pickerTarget = blockId;
  state.pickerMode = mode;
  const input = mode === 'folder' ? $('folder-picker') : $('file-picker');
  if (!input) return;
  if (blockId === 'amp') input.accept = '.nam,.json';
  else if (blockId === 'cab') input.accept = '.wav';
  else input.accept = '.nam,.wav';
  input.value = '';
  input.click();
}

async function handlePickedFiles(fileList) {
  const files = Array.from(fileList || []);
  const target = state.pickerTarget || 'amp';
  if (!files.length) return;
  let file = null;
  if (target === 'amp') file = files.find((f) => /\.(nam|json)$/i.test(f.name));
  else if (target === 'cab') file = files.find((f) => /\.wav$/i.test(f.name));
  else file = files.find((f) => /\.(nam|json)$/i.test(f.name)) || files.find((f) => /\.wav$/i.test(f.name));

  if (!file) {
    showToast(target === 'cab' ? 'ไม่พบไฟล์ .wav ในโฟลเดอร์ที่เลือก' : 'ไม่พบไฟล์ .nam ในโฟลเดอร์ที่เลือก', true);
    return;
  }
  if (files.length > 1) showToast(`พบ ${files.length} ไฟล์ — ใช้ ${file.name}`);
  if (/\.wav$/i.test(file.name)) await uploadIR(file);
  else await uploadNAM(file);
}

async function uploadNAM(file) {
  try {
    const fd = new FormData();
    fd.append('nam_file', file, file.name);
    const res = await fetch('/api/nam/upload?quality=' + encodeURIComponent(state.namQuality), { method: 'POST', body: fd });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'อัปโหลด NAM ไม่สำเร็จ');
    state.namTitle = file.name;
    state.namFile = file.name;
    state.namArch = '2';
    state.t3kLoaded = null;
    state.block = 'amp';
    if (data.state) applyServerState(data.state, { forceRender: true });
    renderChain();
    renderPanel();
    renderFaceStrip();
    showToast('โหลด NAM “' + file.name + '” เข้า NAM AMP แล้ว');
  } catch (err) {
    showToast(err.message, true);
  }
}

async function uploadIR(file) {
  try {
    const fd = new FormData();
    fd.append('ir_file', file, file.name);
    const res = await fetch('/api/cab/load_ir', { method: 'POST', body: fd });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || 'อัปโหลด IR ไม่สำเร็จ');
    state.block = 'cab';
    if (data.state) applyServerState(data.state, { forceRender: true });
    renderChain();
    renderPanel();
    renderFaceStrip();
    showToast('โหลด IR “' + file.name + '” เข้า IR CAB แล้ว');
  } catch (err) {
    showToast(err.message, true);
  }
}

async function clearBlockFile(blockId) {
  try {
    if (blockId === 'amp') {
      const data = await api('/api/nam/clear', { method: 'POST' });
      state.namTitle = '';
      state.namFile = '';
      state.t3kLoaded = null;
      if (data.state) applyServerState(data.state, { forceRender: true });
      renderChain(); renderPanel(); renderFaceStrip();
      showToast('ล้าง NAM model แล้ว');
    } else if (blockId === 'cab') {
      const data = await sendParamNow('cab', 'ir_name', 'Celestion V30 4x12');
      if (data?.state) applyServerState(data.state, { forceRender: true });
      showToast('กลับไปใช้ IR เริ่มต้นแล้ว');
    } else {
      showToast('บล็อกนี้ไม่รองรับการล้างไฟล์', true);
    }
  } catch (err) {
    showToast(err.message, true);
  }
}

// ── boot / events ────────────────────────────────────────────────────
async function pollOnce() {
  if (state.pollBusy) return;
  state.pollBusy = true;
  try {
    const data = await api('/api/status');
    applyServerState(data);
  } catch (err) {
    /* transient */
  } finally {
    state.pollBusy = false;
  }
}

function startPolling() {
  if (state.pollTimer) return;
  state.pollTimer = setInterval(pollOnce, 180);
  pollOnce();
}

function bindEvents() {
  $('btn-power')?.addEventListener('click', async () => {
    try {
      if (state.isRunning) {
        await api('/api/stop', { method: 'POST' });
      } else {
        const d = await api('/api/start', { method: 'POST', body: {} });
        if (d.state) applyServerState(d.state);
      }
      await pollOnce();
    } catch (err) { showToast(err.message, true); }
  });

  $('btn-tuner-toggle')?.addEventListener('click', toggleTuner);
  $('btn-tuner-close')?.addEventListener('click', () => { if (state.tunerActive) toggleTuner(); });

  $('btn-settings-open')?.addEventListener('click', openSettings);
  $('btn-close-settings')?.addEventListener('click', closeSettings);
  $('btn-apply-settings')?.addEventListener('click', applySettings);
  $('modal-settings')?.addEventListener('click', (e) => { if (e.target.id === 'modal-settings') closeSettings(); });
  $('sw-show-pitch')?.addEventListener('change', (e) => setShowPitch(e.target.checked));
  $('btn-quality-lite')?.addEventListener('click', () => setNamQuality('lite'));
  $('btn-quality-full')?.addEventListener('click', () => setNamQuality('full'));

  $('btn-save-preset')?.addEventListener('click', () => savePreset(false));
  $('btn-save-as-preset')?.addEventListener('click', () => savePreset(true));
  $('prevPreset')?.addEventListener('click', stepPreset);
  $('nextPreset')?.addEventListener('click', stepPresetNext);
  $('btn-refresh-lib')?.addEventListener('click', async () => { await loadPresetLibrary(); showToast('รีเฟรชคลังแล้ว'); });

  let searchTimer = null;
  $('rig-search-input')?.addEventListener('input', (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.query = e.target.value || '';
      renderTable();
    }, 160);
  });

  $('btn-t3k-cta')?.addEventListener('click', openT3K);
  $('btn-t3k-open')?.addEventListener('click', openT3K);

  $('bypassToggle')?.addEventListener('click', () => toggleBlock(state.block));

  const chain = $('chain');
  if (chain) {
    chain.addEventListener('click', (e) => {
      const power = e.target.closest('.cb-power');
      if (power) {
        e.stopPropagation();
        toggleBlock(power.dataset.power);
        return;
      }
      const tile = e.target.closest('.chain-block');
      if (tile) selectBlock(tile.dataset.block);
    });
    chain.addEventListener('contextmenu', (e) => {
      const tile = e.target.closest('.chain-block');
      if (!tile) return;
      e.preventDefault();
      openCtx(tile.dataset.block, e.clientX, e.clientY);
    });
    chain.addEventListener('pointerdown', (e) => {
      const tile = e.target.closest('.chain-block');
      if (!tile) return;
      clearTimeout(state.longPressTimer);
      state.longPressTimer = setTimeout(() => {
        openCtx(tile.dataset.block, e.clientX, e.clientY);
      }, 520);
    });
    ['pointerup', 'pointercancel', 'pointermove'].forEach((evt) => {
      chain.addEventListener(evt, () => clearTimeout(state.longPressTimer));
    });
  }

  $('panelSide')?.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action], [data-quality]');
    if (!btn) return;
    if (btn.dataset.quality) { setNamQuality(btn.dataset.quality); return; }
    if (btn.dataset.action === 'load-nam') $('nam-file-input')?.click();
    else if (btn.dataset.action === 'load-ir') $('ir-file-input')?.click();
    else if (btn.dataset.action === 'open-t3k') openT3K();
    else if (btn.dataset.action === 'open-settings') openSettings();
  });

  $('ctx-load-file')?.addEventListener('click', () => { const b = state.ctxBlock; closeCtx(); if (b) pickFile(b, 'file'); });
  $('ctx-load-folder')?.addEventListener('click', () => { const b = state.ctxBlock; closeCtx(); if (b) pickFile(b, 'folder'); });
  $('ctx-clear-file')?.addEventListener('click', () => { const b = state.ctxBlock; closeCtx(); if (b) clearBlockFile(b); });

  $('file-picker')?.addEventListener('change', (e) => handlePickedFiles(e.target.files));
  $('folder-picker')?.addEventListener('change', (e) => handlePickedFiles(e.target.files));
  $('nam-file-input')?.addEventListener('change', async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (file) await uploadNAM(file);
  });
  $('ir-file-input')?.addEventListener('change', async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (file) await uploadIR(file);
  });

  document.addEventListener('click', (e) => {
    if (!e.target.closest('#ctx-menu')) closeCtx();
  });
  window.addEventListener('resize', closeCtx);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeCtx();
      closeSettings();
    }
  });
}

function stepPreset() {
  const list = filteredPresets();
  if (!list.length) return;
  const idx = list.findIndex((p) => favKey(p) === state.selectedKey);
  const next = idx <= 0 ? list.length - 1 : idx - 1;
  loadPreset(list[next]);
}

function stepPresetNext() {
  const list = filteredPresets();
  if (!list.length) return;
  const idx = list.findIndex((p) => favKey(p) === state.selectedKey);
  const next = idx < 0 || idx >= list.length - 1 ? 0 : idx + 1;
  loadPreset(list[next]);
}

async function boot() {
  buildMeter($('meterIn'));
  buildMeter($('meterOut'));
  bindEvents();
  initT3K();
  renderLib();
  renderTable();
  renderDetails(null);
  renderChain();
  renderPanel();
  renderFaceStrip();

  await loadDevices();
  await loadPresetLibrary();

  try {
    const server = await api('/api/status');
    applyServerState(server, { forceRender: true });
    if (server.is_running !== undefined) state.isRunning = !!server.is_running;
    if (server.tuner) {
      state.tunerActive = true;
      $('tuner-display')?.classList.remove('hidden');
    }
  } catch (err) {
    showToast('เชื่อมต่อ backend ไม่ได้: ' + err.message, true);
  }

  if (!state.selectedKey) {
    const lastKey = localStorage.getItem('tone.lastPresetKey');
    const last = lastKey ? mappedPresets().find((p) => favKey(p) === lastKey) : null;
    const first = last || filteredPresets()[0];
    if (first) await loadPreset(first, { silent: true });
    else renderDetails(null);
  }

  startPolling();
}

// ── TONE3000 SELECT FLOW ──────────────────────────────────────────
// ── 8. TONE3000 SELECT FLOW ──────────────────────────────────────────
// Mirrors the TONE3000 API contract:
//   POST /api/t3k/connect  -> authorize URL (browser tab picks a tone)
//   GET  /api/t3k/callback -> server exchanges code + installs the .nam
//   GET  /api/t3k/tones    -> in-app browser (trending/latest/favorites/...)
//   POST /api/t3k/load     -> install a model straight from the browser
const t3kState = {
  status: null,
  kind: 'trending',
  query: '',
  page: 1,
  gear: '',
  verified: false,
  tones: [],
  total: 0,
  totalPages: 1,
  searchTimer: null,
  pollTimer: null,
  toastTimer: null,
  lastSeq: 0,
  detail: null,
  models: []
};

const T3K_GEAR_LABELS = {
  'amp': 'Amp',
  'amp-cab': 'Amp + Cab',
  'amp_cab': 'Amp + Cab',
  'pedal': 'Pedal',
  'outboard': 'Outboard',
  'cab': 'Cab',
  'space': 'Space',
  'experimental': 'Experimental',
  'ir': 'Cabinet IR'
};

function t3kEl(id) { return document.getElementById(id); }

function t3kGearLabel(gear) {
  return T3K_GEAR_LABELS[gear] || (gear ? String(gear).replace(/[-_]/g, ' ') : 'Gear');
}

function t3kSafeUrl(url) {
  const value = String(url || '').trim();
  return /^https?:\/\//i.test(value) ? value : '';
}

function t3kNumber(value) {
  const n = Number(value || 0);
  if (n >= 1000000) return (n / 1000000).toFixed(1).replace(/\.0$/, '') + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k';
  return String(n);
}

function t3kToast(message, isError = false) {
  const el = t3kEl('t3k-toast');
  if (!el) return;
  el.textContent = message;
  el.classList.toggle('error', !!isError);
  el.classList.add('show');
  clearTimeout(t3kState.toastTimer);
  t3kState.toastTimer = setTimeout(() => el.classList.remove('show'), 3200);
}

async function t3kApi(path, { method = 'GET', body = null } = {}) {
  const options = { method, headers: {} };
  if (body !== null) {
    options.headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }
  const res = await fetch(path, options);
  let data = {};
  try { data = await res.json(); } catch (e) { /* empty body */ }
  if (!res.ok) {
    const detail = data.detail || data.error_description || data.error || `HTTP ${res.status}`;
    const error = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    error.status = res.status;
    throw error;
  }
  return data;
}

// ── modal lifecycle ──────────────────────────────────────────────────
async function openT3K() {
  const modal = t3kEl('modal-t3k');
  if (!modal) return;
  modal.classList.remove('hidden');
  try {
    await t3kRefreshStatus();
  } catch (err) {
    showT3KConnectView();
    t3kToast('เชื่อมต่อ backend ไม่ได้: ' + err.message, true);
  }
}

function closeT3K() {
  const modal = t3kEl('modal-t3k');
  if (modal) modal.classList.add('hidden');
  stopT3KWatch();
  if (t3kState.status && t3kState.status.logged_in) showT3KBrowseView();
  else showT3KConnectView();
}

async function t3kRefreshStatus() {
  const status = await t3kApi('/api/t3k/status');
  t3kState.status = status;
  renderT3KUser();

  // A tone may have been installed by the OAuth callback while the modal was
  // closed (or before a page reload); adopt it once per sequence number. Only
  // if the engine still has a NAM chain, so a manually uploaded model is not
  // mislabelled as the last TONE3000 tone.
  if (status.last_load && status.seq && status.seq !== t3kState.lastSeq) {
    t3kState.lastSeq = status.seq;
    if (status.engine_nam) { applyT3KLoad(status.last_load, false); pollOnce(); }
  }

  if (status.logged_in) {
    showT3KBrowseView();
    if (!t3kState.tones.length) await loadT3KBrowse(1);
  } else {
    showT3KConnectView();
  }
  return status;
}

function renderT3KUser() {
  const el = t3kEl('t3k-user');
  if (!el) return;
  const status = t3kState.status;
  const user = status && status.user;
  if (!status || !status.logged_in || !user) {
    el.innerHTML = (status && status.configured)
      ? '<span>ยังไม่เชื่อมต่อ</span>'
      : '';
    return;
  }
  const avatar = t3kSafeUrl(user.avatar_url);
  const name = user.display_name || user.username || 'TONE3000';
  el.innerHTML = `
    ${avatar ? `<img src="${esc(avatar)}" alt="" onerror="this.remove()">` : ''}
    <b>@${esc(user.username || name)}</b>`;
}

function showT3KConnectView() {
  t3kEl('t3k-connect').classList.remove('hidden');
  t3kEl('t3k-browse').classList.add('hidden');
  t3kEl('t3k-detail').classList.add('hidden');
  t3kEl('btn-t3k-back').classList.add('hidden');
  t3kEl('t3k-view-title').textContent = 'CONNECT';
  renderT3KConnectForm();
}

function showT3KBrowseView() {
  t3kEl('t3k-connect').classList.add('hidden');
  t3kEl('t3k-browse').classList.remove('hidden');
  t3kEl('t3k-detail').classList.add('hidden');
  t3kEl('btn-t3k-back').classList.add('hidden');
  t3kEl('t3k-view-title').textContent = 'SELECT TONE';
}

function showT3KDetailView() {
  t3kEl('t3k-connect').classList.add('hidden');
  t3kEl('t3k-browse').classList.add('hidden');
  t3kEl('t3k-detail').classList.remove('hidden');
  t3kEl('btn-t3k-back').classList.remove('hidden');
  t3kEl('t3k-view-title').textContent = 'TONE DETAILS';
}

function renderT3KConnectForm() {
  const status = t3kState.status || {};
  const keyInput = t3kEl('t3k-key-input');
  const redirectInput = t3kEl('t3k-redirect-input');
  const archSelect = t3kEl('t3k-arch-select');
  const connectBtn = t3kEl('btn-t3k-connect');
  const waiting = t3kEl('t3k-waiting');

  if (keyInput) keyInput.placeholder = status.client_id || 't3k_pub_...';
  if (redirectInput && !redirectInput.value) redirectInput.value = status.redirect_uri || '';
  if (archSelect && status.architecture) archSelect.value = status.architecture;
  if (connectBtn) {
    connectBtn.classList.toggle('hidden', !status.configured);
    connectBtn.disabled = false;
    connectBtn.textContent = 'เข้าสู่ระบบ TONE3000';
  }
  if (waiting && !t3kState.pollTimer) waiting.classList.add('hidden');
}

// ── configuration + OAuth ────────────────────────────────────────────
async function saveT3KConfig() {
  const btn = t3kEl('btn-t3k-save-key');
  const clientId = (t3kEl('t3k-key-input').value || '').trim();
  const redirectUri = (t3kEl('t3k-redirect-input').value || '').trim();
  const architecture = t3kEl('t3k-arch-select').value;

  if (!clientId && !(t3kState.status && t3kState.status.configured)) {
    t3kToast('ใส่ Publishable key ก่อนครับ', true);
    return;
  }
  btn.disabled = true;
  btn.textContent = 'กำลังบันทึก…';
  try {
    const status = await t3kApi('/api/t3k/config', { method: 'POST', body: {
      client_id: clientId || null,
      redirect_uri: redirectUri || null,
      architecture
    }});
    t3kState.status = status;
    t3kEl('t3k-key-input').value = '';
    renderT3KConnectForm();
    renderT3KUser();
    t3kToast('บันทึก key แล้ว — กด "เข้าสู่ระบบ TONE3000" ได้เลย');
  } catch (err) {
    t3kToast(err.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = 'บันทึก Key';
  }
}

async function startT3KFlow(prompt = 'select_tone', toneId = null) {
  const connectBtn = t3kEl('btn-t3k-connect');
  const browseAllBtn = t3kEl('btn-t3k-browse-all');
  const waiting = t3kEl('t3k-waiting');

  [connectBtn, browseAllBtn].forEach(b => { if (b) b.disabled = true; });
  if (connectBtn) connectBtn.textContent = 'กำลังเปิด TONE3000…';
  try {
    const data = await t3kApi('/api/t3k/connect', { method: 'POST', body: {
      prompt,
      tone_id: toneId
    }});

    // The backend opens the default browser; if that failed (webview/headless)
    // fall back to a normal tab from here.
    if (!data.opened) {
      const tab = window.open(data.authorize_url, '_blank');
      if (!tab) t3kToast('popup ถูกบล็อก — อนุญาต popup แล้วลองใหม่', true);
    }
    if (waiting) waiting.classList.remove('hidden');
    startT3KWatch();
  } catch (err) {
    t3kToast(err.message, true);
    if (connectBtn) {
      connectBtn.disabled = false;
      connectBtn.textContent = 'เข้าสู่ระบบ TONE3000';
    }
  } finally {
    if (browseAllBtn) browseAllBtn.disabled = false;
  }
}

function startT3KWatch() {
  stopT3KWatch();
  const before = (t3kState.status && t3kState.status.seq) || 0;
  const cancelBefore = (t3kState.status && t3kState.status.cancel_seq) || 0;
  const startedAt = Date.now();

  t3kState.pollTimer = setInterval(async () => {
    if (Date.now() - startedAt > 5 * 60 * 1000) {
      stopT3KWatch();
      const waiting = t3kEl('t3k-waiting');
      if (waiting) waiting.classList.add('hidden');
      const connectBtn = t3kEl('btn-t3k-connect');
      if (connectBtn) {
        connectBtn.disabled = false;
        connectBtn.textContent = 'เข้าสู่ระบบ TONE3000';
      }
      return;
    }
    try {
      const wasLoggedIn = !!(t3kState.status && t3kState.status.logged_in);
      const status = await t3kApi('/api/t3k/status');
      t3kState.status = status;
      renderT3KUser();

      const connectBtn = t3kEl('btn-t3k-connect');
      if (connectBtn) {
        connectBtn.disabled = false;
        connectBtn.textContent = 'เข้าสู่ระบบ TONE3000';
      }

      if ((status.cancel_seq || 0) !== cancelBefore) {
        stopT3KWatch();
        const waiting = t3kEl('t3k-waiting');
        if (waiting) waiting.classList.add('hidden');
        const connectBtn = t3kEl('btn-t3k-connect');
        if (connectBtn) {
          connectBtn.disabled = false;
          connectBtn.textContent = 'เข้าสู่ระบบ TONE3000';
        }
        if (status.logged_in) {
          showT3KBrowseView();
          await loadT3KBrowse(1);
        } else {
          showT3KConnectView();
        }
        t3kToast('ยกเลิกการเลือกเสียงแล้ว');
      } else if (status.seq !== before && status.last_load) {
        stopT3KWatch();
        const waiting = t3kEl('t3k-waiting');
        if (waiting) waiting.classList.add('hidden');
        t3kState.lastSeq = status.seq;
        applyT3KLoad(status.last_load, true);

        if (status.logged_in) {
          showT3KBrowseView();
          await loadT3KBrowse(1);
        } else {
          showT3KConnectView();
        }
        t3kToast(`โหลด "${status.last_load.title}" เข้า NAM AMP และบันทึกเป็นพรีเซ็ตแล้ว`);
        setTimeout(closeT3K, 1100);
      } else if (status.logged_in && !wasLoggedIn) {
        // Signed in, but the user closed the picker before choosing a tone:
        // switch to the in-app browser instead of waiting forever.
        stopT3KWatch();
        const waiting = t3kEl('t3k-waiting');
        if (waiting) waiting.classList.add('hidden');
        showT3KBrowseView();
        t3kState.lastSeq = status.seq || t3kState.lastSeq;
        t3kToast('เชื่อมต่อ TONE3000 แล้ว — เลือกเสียงได้เลย');
        await loadT3KBrowse(1);
      } else if (status.logged_in) {
        // Signed in but the tab is still open on the picker: refresh quietly.
        renderT3KConnectForm();
      }
    } catch (err) {
      // transient network hiccup while polling
    }
  }, 1500);
}

function stopT3KWatch() {
  if (t3kState.pollTimer) {
    clearInterval(t3kState.pollTimer);
    t3kState.pollTimer = null;
  }
}

// ── catalogue ────────────────────────────────────────────────────────
async function loadT3KBrowse(page = 1) {
  const grid = t3kEl('t3k-grid');
  const count = t3kEl('t3k-count');
  t3kState.page = page;
  t3kState.query = (t3kEl('t3k-search-input').value || '').trim();
  t3kState.gear = t3kEl('t3k-gear').value;

  if (grid) grid.innerHTML = '<div class="t3k-empty">กำลังโหลดเสียงจาก TONE3000…</div>';

  const params = new URLSearchParams();
  params.set('kind', t3kState.kind);
  params.set('page', String(page));
  if (t3kState.query) params.set('query', t3kState.query);
  if (t3kState.gear) params.set('gear', t3kState.gear);
  if (t3kState.verified) params.set('verified', 'true');

  try {
    const data = await t3kApi('/api/t3k/tones?' + params.toString());
    t3kState.tones = data.data || [];
    t3kState.total = data.total || t3kState.tones.length;
    t3kState.totalPages = Math.max(1, data.total_pages || 1);
    renderT3KGrid();
    renderT3KPager();
    if (count) {
      count.textContent = `${t3kNumber(t3kState.total)} เสียง · หน้า ${t3kState.page}/${t3kState.totalPages}`
        + (t3kState.query ? ` · "${t3kState.query}"` : '');
    }
  } catch (err) {
    if (err.status === 401) {
      if (t3kState.status) t3kState.status.logged_in = false;
      renderT3KUser();
      showT3KConnectView();
      t3kToast('เซสชัน TONE3000 หมดอายุ — เชื่อมต่อใหม่', true);
      return;
    }
    if (grid) {
      grid.innerHTML = `<div class="t3k-empty">โหลดคลังไม่สำเร็จ<br>${esc(err.message)}</div>`;
    }
    if (count) count.textContent = '';
  }
}

function renderT3KGrid() {
  const grid = t3kEl('t3k-grid');
  if (!grid) return;

  if (!t3kState.tones.length) {
    grid.innerHTML = '<div class="t3k-empty">ไม่พบเสียงที่ตรงเงื่อนไข<br>ลองล้างคำค้นหรือเปลี่ยนตัวกรอง</div>';
    return;
  }

  grid.innerHTML = t3kState.tones.map(tone => {
    const image = t3kSafeUrl((tone.images || [])[0]);
    const creator = (tone.user && (tone.user.display_name || tone.user.username)) || 'TONE3000';
    const downloads = Number(tone.downloads_count || 0);
    return `
      <article class="t3k-card" data-tone-id="${esc(tone.id)}" tabindex="0" role="button"
               aria-label="${esc(tone.title)}">
        <div class="t3k-thumb">
          ${image
            ? `<img src="${esc(image)}" alt="" loading="lazy" onerror="this.remove()">`
            : '<span class="t3k-thumb-fallback">T3K</span>'}
          <div class="t3k-badge-row">
            <span class="t3k-badge">${esc(String(tone.format || 'nam').toUpperCase())}</span>
            <span class="t3k-badge gear">${esc(t3kGearLabel(tone.gear))}</span>
          </div>
        </div>
        <div class="t3k-card-body">
          <div class="t3k-card-title">${esc(tone.title)}</div>
          <div class="t3k-card-meta">
            <span class="creator">by <b>@${esc(creator)}</b></span>
            <span class="t3k-star">${tone.is_favorite ? '★' : (downloads ? '↓ ' + t3kNumber(downloads) : '')}</span>
          </div>
        </div>
      </article>`;
  }).join('');

  grid.querySelectorAll('.t3k-card').forEach(card => {
    const open = () => openT3KDetail(card.dataset.toneId);
    card.addEventListener('click', open);
    card.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); }
    });
  });
}

function renderT3KPager() {
  const pager = t3kEl('t3k-pager');
  if (!pager) return;
  if (t3kState.totalPages <= 1) {
    pager.innerHTML = '';
    return;
  }

  const page = t3kState.page;
  const total = t3kState.totalPages;
  const first = Math.max(1, page - 2);
  const last = Math.min(total, first + 4);
  let html = `<button class="t3k-page-btn" data-page="${page - 1}" ${page <= 1 ? 'disabled' : ''}>‹</button>`;
  for (let p = first; p <= last; p++) {
    html += `<button class="t3k-page-btn ${p === page ? 'active' : ''}" data-page="${p}">${p}</button>`;
  }
  html += `<button class="t3k-page-btn" data-page="${page + 1}" ${page >= total ? 'disabled' : ''}>›</button>`;
  pager.innerHTML = html;

  pager.querySelectorAll('.t3k-page-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = Number(btn.dataset.page);
      if (target >= 1 && target <= total && target !== page) loadT3KBrowse(target);
    });
  });
}

// ── detail + install ─────────────────────────────────────────────────
async function openT3KDetail(toneId) {
  const detail = t3kEl('t3k-detail');
  if (!detail) return;
  showT3KDetailView();
  detail.innerHTML = '<div class="t3k-empty">กำลังโหลดรายละเอียด…</div>';

  try {
    const data = await t3kApi(`/api/t3k/tones/${encodeURIComponent(toneId)}`);
    t3kState.detail = data.tone || null;
    t3kState.models = data.models || [];
    renderT3KDetail();
  } catch (err) {
    if (err.status === 401) {
      if (t3kState.status) t3kState.status.logged_in = false;
      renderT3KUser();
      showT3KConnectView();
      t3kToast('เซสชัน TONE3000 หมดอายุ — เชื่อมต่อใหม่', true);
      return;
    }
    detail.innerHTML = `<div class="t3k-empty">โหลดรายละเอียดไม่สำเร็จ<br>${esc(err.message)}</div>`;
  }
}

function renderT3KDetail() {
  const detail = t3kEl('t3k-detail');
  const tone = t3kState.detail;
  if (!detail || !tone) return;

  const creator = (tone.user && (tone.user.display_name || tone.user.username)) || 'TONE3000';
  const image = t3kSafeUrl((tone.images || [])[0]);
  const models = t3kState.models;
  const currentArch = (t3kState.status && t3kState.status.architecture) || '2';

  const options = models.map((model, index) => {
    const arch = model.architecture_version ? ` • A${model.architecture_version}` : '';
    const size = model.size ? String(model.size) : '';
    return `<option value="${esc(model.id)}" ${index === 0 ? 'selected' : ''}>
      ${esc(model.name)}${esc(size ? ' • ' + size : '')}${esc(arch)}
    </option>`;
  }).join('');

  detail.innerHTML = `
    <div class="t3k-detail-grid">
      <div class="t3k-detail-art">
        ${image
          ? `<img src="${esc(image)}" alt="" onerror="this.remove()">`
          : '<span class="t3k-thumb-fallback">T3K</span>'}
      </div>
      <div>
        <h2>${esc(tone.title)}</h2>
        <div class="t3k-detail-meta">
          <span class="t3k-badge">${esc(String(tone.format || 'nam').toUpperCase())}</span>
          <span class="t3k-badge gear">${esc(t3kGearLabel(tone.gear))}</span>
          <span class="dot">•</span>
          <span>@${esc(creator)}</span>
          <span class="dot">•</span>
          <span>↓ ${t3kNumber(tone.downloads_count)}</span>
        </div>
        <p class="t3k-detail-desc">${esc(tone.description || 'ไม่มีคำอธิบายจากผู้สร้าง')}</p>

        <div class="t3k-model-row">
          <label>Model
            <select id="t3k-model-select" ${models.length ? '' : 'disabled'}>
              ${options || '<option>ยังไม่มีไฟล์ที่ดาวน์โหลดได้</option>'}
            </select>
          </label>
          <button id="btn-t3k-load" class="t3k-primary" ${models.length ? '' : 'disabled'}>
            ⚡ โหลดเข้า NAM AMP
          </button>
        </div>
        <div class="t3k-detail-note">
          จะติดตั้งเป็น NAM chain ในบล็อก NAM AMP — architecture ปัจจุบัน: A${esc(currentArch)}.
          ถ้าไฟล์โหลดไม่ติด ระบบจะลองใหม่ด้วย A1 ให้อัตโนมัติ
        </div>
      </div>
    </div>`;

  const loadBtn = t3kEl('btn-t3k-load');
  if (loadBtn && models.length) {
    loadBtn.addEventListener('click', loadT3KFromBrowser);
  }
}

async function loadT3KFromBrowser() {
  const tone = t3kState.detail;
  if (!tone) return;
  const btn = t3kEl('btn-t3k-load');
  const select = t3kEl('t3k-model-select');
  const modelId = select ? select.value : null;

  if (btn) { btn.disabled = true; btn.textContent = 'กำลังดาวน์โหลด…'; }
  try {
    const data = await t3kApi('/api/t3k/load', { method: 'POST', body: {
      tone_id: Number(tone.id),
      model_id: modelId ? Number(modelId) : null
    }});
    if (data.load) {
      t3kState.lastSeq = data.load.seq || ((t3kState.status && t3kState.status.seq) || t3kState.lastSeq);
      applyT3KLoad(data.load, true);
    }
    if (data.state) applyServerState(data.state, { forceRender: true });
    t3kToast(`โหลด "${data.load ? data.load.title : tone.title}" เข้า NAM AMP แล้ว`);
    setTimeout(closeT3K, 900);
  } catch (err) {
    t3kToast(err.message, true);
    if (btn) { btn.disabled = false; btn.textContent = '⚡ โหลดเข้า NAM AMP'; }
  }
}

// Reflect a loaded tone in the chain block, header and NAM status badge.
function applyT3KLoad(load, refreshState) {
  if (!load) return;
  state.t3kLoaded = load;
  state.namTitle = load.title || load.model || 'TONE3000 capture';
  state.namFile = load.model || '';
  state.namArch = load.fallback_a1 ? '1' : String(load.architecture || '2');
  state.namQuality = load.quality || state.namQuality;
  state.selectedKey = null;
  state.selectedId = null;
  state.selectedType = null;
  markDirty(false);

  const title = String(load.title || 'TONE3000 Tone');
  const archLabel = state.namArch === '1' ? 'A1 (fallback)' : 'A' + state.namArch;
  if ($('curName')) $('curName').textContent = title;
  if ($('curSub')) $('curSub').textContent = `${t3kGearLabel(load.gear)} • ${load.creator || 'TONE3000'} • ${archLabel}-${state.namQuality}`;
  if ($('stPreset')) $('stPreset').textContent = title;

  const item = {
    type: 't3k-live',
    id: 't3k-live',
    name: title,
    category: t3kGearLabel(load.gear),
    author: load.creator || 'TONE3000',
    amp: load.model || 'NAM',
    gain: 0.6,
  };
  renderTable();
  renderDetails(item);
  renderChain();
  renderPanel();
  renderFaceStrip();

  // Auto-saved on the server: refresh library so the new T3K preset appears
  // in "ทั้งหมด" / "จาก TONE3000" and mark it as saved (not dirty).
  loadPresetLibrary().catch(() => {});
  markDirty(false);

  if (refreshState) {
    fetch('/api/status')
      .then((res) => res.ok ? res.json() : null)
      .then((server) => { if (server) applyServerState(server, { forceRender: true }); })
      .catch(() => {});
  }
}

// ── wiring ───────────────────────────────────────────────────────────
function initT3K() {
  const closeBtn = t3kEl('btn-t3k-close');
  if (closeBtn) closeBtn.addEventListener('click', closeT3K);

  const settingsBtn = t3kEl('btn-t3k-settings');
  if (settingsBtn) settingsBtn.addEventListener('click', () => {
    showT3KConnectView();
    renderT3KConnectForm();
  });

  const backdrop = t3kEl('modal-t3k');
  if (backdrop) {
    backdrop.addEventListener('click', (e) => { if (e.target === backdrop) closeT3K(); });
  }

  const backBtn = t3kEl('btn-t3k-back');
  if (backBtn) backBtn.addEventListener('click', () => {
    showT3KBrowseView();
    renderT3KPager();
  });

  const saveKey = t3kEl('btn-t3k-save-key');
  if (saveKey) saveKey.addEventListener('click', saveT3KConfig);

  const connectBtn = t3kEl('btn-t3k-connect');
  if (connectBtn) connectBtn.addEventListener('click', () => startT3KFlow('select_tone'));

  const browseAll = t3kEl('btn-t3k-browse-all');
  if (browseAll) browseAll.addEventListener('click', () => startT3KFlow('select_tone'));

  const searchInput = t3kEl('t3k-search-input');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      clearTimeout(t3kState.searchTimer);
      t3kState.searchTimer = setTimeout(() => {
        t3kState.query = e.target.value.trim();
        loadT3KBrowse(1);
      }, 350);
    });
  }

  const verifiedBtn = t3kEl('btn-t3k-verified');
  if (verifiedBtn) {
    verifiedBtn.addEventListener('click', () => {
      t3kState.verified = !t3kState.verified;
      verifiedBtn.setAttribute('aria-pressed', String(t3kState.verified));
      loadT3KBrowse(1);
    });
  }

  const gearSelect = t3kEl('t3k-gear');
  if (gearSelect) gearSelect.addEventListener('change', () => loadT3KBrowse(1));

  document.querySelectorAll('#t3k-pills .t3k-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      document.querySelectorAll('#t3k-pills .t3k-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      t3kState.kind = pill.dataset.kind || 'trending';
      const input = t3kEl('t3k-search-input');
      if (input) input.value = '';
      t3kState.query = '';
      loadT3KBrowse(1);
    });
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && backdrop && !backdrop.classList.contains('hidden')) closeT3K();
  });
}


window.addEventListener('DOMContentLoaded', boot);
