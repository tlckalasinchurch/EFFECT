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
  knobControllers: { panel: [] },
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
  irPreview: null,
  lastServer: null,
  cortex: null,
  gigViewOpen: false,
  pendingScene: null,
  mooerPresets: [],
  cortexPresets: [],
  kemperRigs: [],
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
  input: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M7 12h7m-3-3 3 3-3 3"/><line x1="17" y1="8" x2="17" y2="16"/></svg>',
  gate: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 18h5l4-12h7"/><path d="M4 18V6h16" stroke-opacity="0.35" stroke-dasharray="2 2"/></svg>',
  pitch: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 19V5m-3 3 3-3 3 3"/><path d="M16 5v14m-3-3 3 3 3-3"/></svg>',
  drive: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="3" width="14" height="18" rx="2.5"/><circle cx="9.5" cy="8" r="1.3"/><circle cx="14.5" cy="8" r="1.3"/><line x1="8" y1="13" x2="16" y2="13"/><circle cx="12" cy="17" r="1.4"/></svg>',
  amp: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="2.5" y="5" width="19" height="14" rx="2"/><line x1="2.5" y1="14" x2="21.5" y2="14"/><circle cx="6.5" cy="16.5" r="0.9" fill="currentColor"/><circle cx="10" cy="16.5" r="0.9" fill="currentColor"/><circle cx="13.5" cy="16.5" r="0.9" fill="currentColor"/><circle cx="17.5" cy="16.5" r="0.9" fill="currentColor"/></svg>',
  'amp-cab': '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="3" width="16" height="6" rx="1.5"/><rect x="3" y="10" width="18" height="11" rx="2"/><circle cx="9" cy="15.5" r="2.5"/><circle cx="15" cy="15.5" r="2.5"/></svg>',
  pedal: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="3" width="14" height="18" rx="2.5"/><circle cx="9.5" cy="8" r="1.3"/><circle cx="14.5" cy="8" r="1.3"/><line x1="8" y1="13" x2="16" y2="13"/><circle cx="12" cy="17" r="1.4"/></svg>',
  cab: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="3" width="16" height="18" rx="2.5"/><circle cx="12" cy="12" r="5.5"/><circle cx="12" cy="12" r="2"/></svg>',
  reverb: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 4 7.5v9L12 21l8-4.5v-9L12 3Z"/><path d="M4 7.5 12 12l8-4.5"/><path d="M12 12v9"/></svg>',
  delay: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19V5l6 7-6 7Z"/><path d="M11 19V8l5 5.5-5 5.5Z" stroke-opacity="0.75"/><path d="M17 19v-8l4 4-4 4Z" stroke-opacity="0.5"/></svg>',
  eq: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="12" x2="21" y2="12" stroke-opacity="0.35"/><path d="M3 14c3-8 6 8 9 0s6-8 9-2"/></svg>',
  mod: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10c3-5 6 5 9 0s6-5 9 0"/><path d="M3 15c3-5 6 5 9 0s6-5 9 0" stroke-opacity="0.55"/></svg>',
  output: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2.5"/><line x1="7" y1="8" x2="7" y2="16"/><path d="M10 12h7m-3-3 3 3-3 3"/></svg>',
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
  { id: 'eq', en: 'STUDIO EQ', th: 'อีควอไลเซอร์', section: 'eq', canBypass: true, icon: 'eq' },
  { id: 'mod', en: 'MOD 19', th: 'มอดูเลชัน', section: 'mod', canBypass: true, icon: 'mod' },
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
    K('center', 'Axis Center', 0, 100, 1, 'pct', 50, 'cab', 'center'),
    K('distance', 'Distance', 0, 100, 1, 'pct', 20, 'cab', 'distance'),
    K('lowcut', 'Low Cut', 20, 500, 1, 'hz', 20, 'cab', 'lowcut'),
    K('highcut', 'High Cut', 1000, 20000, 10, 'hz', 20000, 'cab', 'highcut'),
    K('mix', 'Mix', 0, 100, 1, 'pct', 100, 'cab', 'mix', 100),
    K('level', 'Level', 0, 200, 1, 'pct', 100, 'cab', 'level', 100),
  ],
  eq: [
    K('band0', 'Band 1', -16, 16, 0.5, 'db', 0, 'eq', 'band0'),
    K('band1', 'Band 2', -16, 16, 0.5, 'db', 0, 'eq', 'band1'),
    K('band2', 'Band 3', -16, 16, 0.5, 'db', 0, 'eq', 'band2'),
    K('band3', 'Band 4', -16, 16, 0.5, 'db', 0, 'eq', 'band3'),
    K('band4', 'Band 5', -16, 16, 0.5, 'db', 0, 'eq', 'band4'),
    K('band5', 'Band 6', -16, 16, 0.5, 'db', 0, 'eq', 'band5'),
  ],
  // 5-Band Studio (eq model 5): cut bands are Hz (20 Hz / 20 kHz = off), the rest dB.
  eq_studio: [
    K('band0', 'Low Cut', 20, 500, 1, 'hz', 20, 'eq', 'band0'),
    K('band1', 'Low Shelf', -16, 16, 0.5, 'db', 0, 'eq', 'band1'),
    K('band2', 'Mid 1', -16, 16, 0.5, 'db', 0, 'eq', 'band2'),
    K('band3', 'Mid 2', -16, 16, 0.5, 'db', 0, 'eq', 'band3'),
    K('band4', 'High Shelf', -16, 16, 0.5, 'db', 0, 'eq', 'band4'),
    K('band5', 'High Cut', 2000, 20000, 50, 'hz', 20000, 'eq', 'band5'),
  ],
  mod: [
    K('rate', 'Rate', 0, 100, 1, 'pct', 50, 'mod', 'rate', 100),
    K('depth', 'Depth', 0, 100, 1, 'pct', 50, 'mod', 'depth', 100),
    K('tone', 'Tone', 0, 100, 1, 'pct', 50, 'mod', 'tone', 100),
    K('mix', 'Mix', 0, 100, 1, 'pct', 50, 'mod', 'mix', 100),
  ],
  delay: [
    K('time', 'Time', 20, 2000, 1, 'ms', 360, 'delay', 'time'),
    K('feedback', 'Feedback', 0, 95, 1, 'pct', 35, 'delay', 'feedback', 100),
    K('mix', 'Mix', 0, 100, 1, 'pct', 25, 'delay', 'mix', 100),
    K('duck_depth', 'Duck Depth', 0, 100, 1, 'pct', 60, 'delay', 'duck_depth', 100),
  ],
  reverb: [
    K('decay', 'Decay', 0, 100, 1, 'pct', 50, 'reverb', 'decay', 100),
    K('mix', 'Mix', 0, 100, 1, 'pct', 20, 'reverb', 'mix', 100),
    K('tone', 'Tone', 0, 100, 1, 'pct', 50, 'reverb', 'tone', 100),
    K('duck_depth', 'Duck Depth', 0, 100, 1, 'pct', 50, 'reverb', 'duck_depth', 100),
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
  const customOrder = state.chainOrder || state.lastServer?.chain_order || (state.lastServer?.chain?.device?.order);
  if (Array.isArray(customOrder) && customOrder.length) {
    const map = {};
    BLOCKS.forEach((b) => { map[b.id === 'drive' ? 'screamer' : b.id] = b; });
    const ordered = [];
    customOrder.forEach((key) => {
      const b = map[key];
      if (b && (b.id !== 'pitch' || state.showPitch)) {
        ordered.push(b);
      }
    });
    return [BLOCKS[0], ...ordered, BLOCKS[BLOCKS.length - 1]];
  }
  return BLOCKS.filter((b) => b.id !== 'pitch' || state.showPitch);
}

function knobsForBlock(id) {
  if (id === 'amp') return state.nam ? [...KNOB_SETS.amp_nam, ...KNOB_SETS.amp_dsp] : KNOB_SETS.amp_dsp;
  if (id === 'eq' && (state.live?.eq?.model_id ?? 5) === 5) return KNOB_SETS.eq_studio;
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
  if (id === 'eq') return c.eq ? !!c.eq.enabled : false;
  if (id === 'mod') return c.mod ? !!c.mod.enabled : false;
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
      return shortText(state.nam.includes_cab ? 'NAM · AMP+CAB' : 'NAM · ' + (title || 'capture'), 20);
    }
    return shortText(c.amp?.model || 'DSP Amp', 20);
  }
  if (id === 'cab') {
    if (state.nam?.includes_cab) return 'IN CAPTURE · BYPASSED';
    return shortText(c.cab?.ir_name || 'IR', 20);
  }
  if (id === 'delay') return Math.round(Number(c.delay?.time || 0.36) * 1000) + ' ms';
  if (id === 'mod') {
    const mid = Number(c.mod?.model_id || 12);
    const mnames = { 4: 'Flanger', 5: 'Jet-Flang', 6: 'Tremolo', 7: 'Stutter', 11: 'Rotary', 12: 'Ana-Chorus', 13: 'Tri-Chorus', 19: 'Lo-Fi Crush' };
    return (mnames[mid] || ('Mod #' + mid)) + ' · ' + Math.round(Number(c.mod?.mix ?? 0.5) * 100) + '%';
  }
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
  else if (kd.section === 'eq') {
    if (kd.param.startsWith('band')) {
      const idx = parseInt(kd.param.replace('band', ''), 10);
      v = (c.eq?.bands || [])[idx];
      if ((c.eq?.model_id ?? 5) === 5) {
        // Unset cut bands (0) mean "off": show the knob at its off end.
        if (idx === 0 && !(v >= 20)) v = 20;
        if (idx === 5 && !(v >= 2000)) v = 20000;
      }
    } else {
      v = c.eq?.[kd.param];
    }
  }
  else if (kd.section === 'delay') {
    v = c.delay?.[kd.param];
    if (kd.param === 'time') v = Number(v || 0) * 1000;
  }
  else if (kd.section === 'reverb') v = c.reverb?.[kd.param];
  else if (kd.section === 'mod') v = c.mod?.[kd.param];
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
  window._undoStack = window._undoStack || [];
  window._redoStack = window._redoStack || [];
  const prevSrv = readServer(kd);
  const nextSrv = toServer(kd, uiValue);
  const nowTs = Date.now();
  const topUndo = window._undoStack[window._undoStack.length - 1];
  if (topUndo && topUndo.section === kd.section && topUndo.param === kd.param && (nowTs - topUndo.ts) < 600) {
    topUndo.next = nextSrv;
    topUndo.ts = nowTs;
  } else if (Math.abs(Number(prevSrv) - Number(nextSrv)) > 0.0001) {
    window._undoStack.push({ section: kd.section, param: kd.param, prev: prevSrv, next: nextSrv, ts: nowTs });
    if (window._undoStack.length > 50) window._undoStack.shift();
    window._redoStack.length = 0;
    if ($('btn-undo')) $('btn-undo').disabled = false;
    if ($('btn-redo')) $('btn-redo').disabled = true;
  }
  const key = kd.section + '.' + kd.param;
  let rec = state.pending.get(key);
  if (!rec) {
    rec = { timer: null, value: null };
    state.pending.set(key, rec);
  }
  rec.value = toServer(kd, uiValue);
  if (typeof rec.value === 'number') {
    cppBridge.sendParamValue(kd.section, kd.param, rec.value);
  }
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
  if (typeof value === 'number') {
    cppBridge.sendParamValue(section, param, value);
  } else if (typeof value === 'boolean') {
    cppBridge.sendParamValue(section, param, value ? 1.0 : 0.0);
  }
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
    <circle class="k-collar" cx="50" cy="50" r="46" fill="none" stroke="#2c3646" stroke-width="3" stroke-dasharray="1.5 2.4"></circle><circle class="k-face" cx="50" cy="50" r="30"></circle><circle class="k-cap" cx="50" cy="50" r="24" fill="url(#knobCapGrad)" stroke="#384357" stroke-width="0.8"></circle><g class="k-ticks">${Array.from({ length: 19 }, (_, i) => { const a = -135 + (270 * i) / 18; const [tx, ty] = polar(50, 50, 46, a); return `<circle class="k-tick" data-idx="${i}" cx="${tx.toFixed(1)}" cy="${ty.toFixed(1)}" r="${i % 9 === 0 ? '1.6' : '1.1'}" fill="#2b3442"/>`; }).join('')}</g>
    <g class="k-pointer"><line x1="50" y1="36" x2="50" y2="22"></line><circle class="k-tip" cx="50" cy="24" r="2.1" fill="#f59e0b"></circle></g>`;
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
  const tip = svg.querySelector('.k-tip');
  const ticks = svg.querySelectorAll('.k-tick');

  const ctrl = {
    kd,
    root,
    knob,
    value: initialUi,
    dragging: false,
    blockId: opts.blockId || null,
    setValue(v, silent = false) {
      let val = clamp(Number(v), kd.min, kd.max);
      if (kd.step) val = Math.round(val / kd.step) * kd.step;
      val = clamp(val, kd.min, kd.max);
      ctrl.value = val;
      const t = (val - kd.min) / (kd.max - kd.min || 1);
      const angle = -135 + 270 * t;
      arc.setAttribute('d', t <= 0.0005 ? '' : arcPath(50, 50, 42, -135, angle));
      const [p1x, p1y] = polar(50, 50, 12, angle);
      const [px, py] = polar(50, 50, 27, angle);
      const [tx, ty] = polar(50, 50, 23.5, angle);
      pointer.setAttribute('x1', p1x.toFixed(2));
      pointer.setAttribute('y1', p1y.toFixed(2));
      if (tip) { tip.setAttribute('cx', tx.toFixed(2)); tip.setAttribute('cy', ty.toFixed(2)); }
      ticks.forEach((tk, idx) => tk.setAttribute('fill', (idx / 18) <= t + 0.01 ? 'var(--gold)' : '#2b3442'));
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
  valueEl.title = 'คลิกเพื่อพิมพ์ตัวเลขโดยตรง';
  valueEl.addEventListener('click', () => {
    if (valueEl.querySelector('input')) return;
    const inp = document.createElement('input');
    inp.type = 'number';
    inp.className = 'k-value-input';
    inp.min = String(kd.min);
    inp.max = String(kd.max);
    inp.step = String(kd.step || 1);
    inp.value = String(Number(ctrl.value.toFixed(2)));
    valueEl.textContent = '';
    valueEl.appendChild(inp);
    inp.focus();
    inp.select();
    const commit = () => {
      const parsed = parseFloat(inp.value);
      if (!Number.isNaN(parsed)) ctrl.setValue(parsed);
      else valueEl.textContent = fmtKnob(kd, ctrl.value);
    };
    inp.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') { ev.preventDefault(); inp.blur(); }
      else if (ev.key === 'Escape') { valueEl.textContent = fmtKnob(kd, ctrl.value); }
    });
    inp.addEventListener('blur', commit, { once: true });
  });
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
  state.knobControllers.panel.forEach((ctrl) => {
    if (ctrl.dragging) return;
    const server = readServer(ctrl.kd);
    const ui = toUi(ctrl.kd, server);
    if (Math.abs(ui - ctrl.value) > 0.001) ctrl.setValue(ui, true);
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
  const mooer = (state.mooerPresets || []).map((p, idx) => ({
    id: 'mooer_' + (p.name || idx),
    type: 'mooer',
    name: p.name || ('MOOER ' + idx),
    category: 'MOOER GE150',
    author: p.author || 'MOOER',
    amp: p.settings?.amp?.model || 'Mooer Amp',
    cab: p.settings?.cab?.ir_name || '',
    gain: Number(p.settings?.amp?.gain ?? 0.6),
    raw: p,
  }));
  const cortex = (state.cortexPresets || []).map((p) => ({
    id: p.id,
    type: 'cortex',
    name: p.name || p.id,
    category: 'Quad Cortex',
    author: p.author || 'Neural DSP',
    amp: p.base_settings?.amp?.model || 'Cortex Amp',
    cab: p.base_settings?.cab?.ir_name || '',
    gain: Number(p.base_settings?.amp?.gain ?? 0.65),
    raw: p,
  }));
  const kemper = (state.kemperRigs || []).map((r) => ({
    id: 'kemper_' + r.pack + '_' + r.id,
    type: 'kemper',
    name: r.name,
    category: r.category || 'KEMPER',
    author: r.author || 'KEMPER',
    amp: r.amp?.amp_name || 'Kemper Profile',
    cab: r.amp?.cab_name || '',
    gain: Number(r.params?.gain ?? 0.5),
    pack_path: r.pack_path,
    rig_id: r.id,
    raw: r,
  }));
  return [...t3k, ...mooer, ...cortex, ...kemper, ...builtins];
}

function favKey(item) {
  return item.type + ':' + item.id;
}

function filteredPresets() {
  let list = mappedPresets();
  if (state.filter === 'master') list = list.filter((p) => String(p.id).startsWith('master_'));
  else if (state.filter === 'mine') list = list.filter((p) => p.type === 'preset' && (p.author === 'User' || String(p.id).startsWith('user_')));
  else if (state.filter === 't3k') list = list.filter((p) => p.type === 't3k');
  else if (state.filter === 'kemper') list = list.filter((p) => p.type === 'kemper');
  else if (state.filter === 'cortex') list = list.filter((p) => p.type === 'cortex');
  else if (state.filter === 'mooer') list = list.filter((p) => p.type === 'mooer');
  else if (state.filter === 'fav') list = list.filter((p) => state.favorites.has(favKey(p)));
  if (state.toneFilter === 'clean') list = list.filter((p) => Number(p.gain ?? 0.5) <= 0.42);
  else if (state.toneFilter === 'crunch') list = list.filter((p) => Number(p.gain ?? 0.5) > 0.42 && Number(p.gain ?? 0.5) < 0.70);
  else if (state.toneFilter === 'highgain') list = list.filter((p) => Number(p.gain ?? 0.5) >= 0.70);
  const q = state.query.trim().toLowerCase();
  if (q) {
    list = list.filter((p) => [p.name, p.amp, p.cab, p.category, p.author].join(' ').toLowerCase().includes(q));
  }
  return list;
}

const LIB_DEFS = [
  { id: 'all', label: 'ทั้งหมด', icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>' },
  { id: 'master', label: '★ Master Clones', icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>' },
  { id: 'kemper', label: 'KEMPER Rigs', icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="3" width="20" height="14" rx="2"/><circle cx="7" cy="8" r="1.5"/><circle cx="12" cy="8" r="1.5"/><circle cx="17" cy="8" r="1.5"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>' },
  { id: 'cortex', label: 'Quad Cortex', icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="4" width="20" height="16" rx="2"/><circle cx="6" cy="8" r="1.5"/><circle cx="10" cy="8" r="1.5"/><circle cx="14" cy="8" r="1.5"/><circle cx="18" cy="8" r="1.5"/><circle cx="6" cy="14" r="1.5"/><circle cx="10" cy="14" r="1.5"/><circle cx="14" cy="14" r="1.5"/><circle cx="18" cy="14" r="1.5"/></svg>' },
  { id: 'mooer', label: 'MOOER GE150', icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="2" width="18" height="20" rx="3"/><circle cx="12" cy="7" r="2.5"/><rect x="7" y="13" width="10" height="6" rx="1"/></svg>' },
  { id: 't3k', label: 'จาก TONE3000', icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="8"/><path d="M4 12h16M12 4c3 3.5 3 12.5 0 16M12 4c-3 3.5-3 12.5 0 16"/></svg>' },
  { id: 'mine', label: 'ของฉัน', icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 20v-1a6 6 0 0 1 12 0v1"/><circle cx="10" cy="8" r="4"/><path d="M17 11l1.5 3 3 .5-2.2 2.2.5 3-2.8-1.5-2.8 1.5.5-3L13 13.5l3-.5z"/></svg>' },
  { id: 'fav', label: 'ชื่นชอบ', icon: '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3l2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3 6.4 20.2l1.1-6.2L3 9.6l6.2-.9z"/></svg>' },
];

function renderLib() {
  const el = $('libList');
  if (!el) return;
  const all = mappedPresets();
  const counts = {
    all: all.length,
    master: all.filter((p) => String(p.id).startsWith('master_')).length,
    mine: all.filter((p) => p.type === 'preset' && (p.author === 'User' || String(p.id).startsWith('user_'))).length,
    t3k: all.filter((p) => p.type === 't3k').length,
    kemper: all.filter((p) => p.type === 'kemper').length,
    cortex: all.filter((p) => p.type === 'cortex').length,
    mooer: all.filter((p) => p.type === 'mooer').length,
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
      toggleFavorite(list.find((item) => favKey(item) === btn.dataset.fav));
    });
  });
}

function toggleFavorite(item) {
  if (!item) return;
  const key = favKey(item);
  if (state.favorites.has(key)) state.favorites.delete(key);
  else state.favorites.add(key);
  localStorage.setItem('tone.favorites', JSON.stringify([...state.favorites]));
  renderLib();
  renderTable();
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

function gearBayHTML(item) {
  const p = item.raw || {};
  const live = item.type === 't3k-live' ? state.t3kLoaded : null;
  const image = live?.image || p.image || '';
  const amp = live?.model || p.amp_name || p.amp_model || item.amp || 'NAM capture';
  const cab = p.cab_name || p.cab_model || p.cab_fallback || item.cab || 'Cabinet not specified';
  const preview = state.irPreview;
  const irAvailable = item.type === 't3k-live'
    ? !!live?.includes_cab || !!preview?.available
    : item.type === 't3k' ? !!p.has_real_ir : !!preview?.available;
  const irName = item.type === 't3k-live'
    ? (live?.includes_cab ? 'Cabinet included in capture' : preview?.name || 'No embedded cabinet IR')
    : (item.type === 't3k' && p.has_real_ir ? cab : preview?.name || cab);
  const waveform = preview?.available && irAvailable
    ? `<svg class="gear-wave" viewBox="0 0 192 36" role="img" aria-label="IR waveform preview"><path d="${preview.waveform.map((v, i) => `M${i * 2} 18v${Math.max(1, v * 16)}`).join(' ')}"/></svg>`
    : '';
  const picture = image
    ? `<img class="gear-image" src="${esc(image)}" alt="${esc(item.name)} gear image" loading="lazy" referrerpolicy="no-referrer" onerror="this.hidden=true">`
    : `<div class="gear-no-image" aria-label="ไม่มีภาพจริงของอุปกรณ์" style="padding:0; overflow:hidden;"><svg viewBox="0 0 80 56" width="100%" height="100%" preserveAspectRatio="xMidYMid slice"><rect width="80" height="56" fill="#120f0d"/><rect x="4" y="6" width="72" height="26" rx="2" fill="#090b10" stroke="#334155"/><circle cx="22" cy="19" r="7" fill="url(#tubeGlowGrad)"/><circle cx="40" cy="19" r="7" fill="url(#tubeGlowGrad)"/><circle cx="58" cy="19" r="7" fill="url(#tubeGlowGrad)"/><rect x="4" y="36" width="72" height="14" rx="1.5" fill="#b45309"/><circle cx="14" cy="43" r="2.8" fill="#111"/><circle cx="26" cy="43" r="2.8" fill="#111"/><circle cx="38" cy="43" r="2.8" fill="#111"/><circle cx="50" cy="43" r="2.8" fill="#111"/><circle cx="68" cy="43" r="3" fill="#ef4444"/></svg></div>`;
  return `<div class="gear-bay" aria-label="แอมป์และตู้ลำโพง">
    <div class="gear-card">${picture}<div class="gear-info"><span class="gear-label">AMP / CAPTURE</span><strong>${esc(amp)}</strong><span>${esc(live?.gear ? t3kGearLabel(live.gear) : p.ir_mic ? 'Mic · ' + p.ir_mic : 'Gear name')}</span></div></div>
    <div class="gear-card gear-ir"><div class="gear-info"><span class="gear-label">CABINET / IR</span><strong>${esc(irName)}</strong><span>${irAvailable && preview?.sample_rate ? `${Number(preview.sample_rate).toLocaleString()} Hz · ${preview.duration_ms} ms` : irAvailable ? 'IR included' : 'Synthetic / unavailable'}</span>${waveform}</div></div>
  </div>`;
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

  sections = gearBayHTML(item) + sections;
  if (!state.irPreview) {
    api('/api/cab/ir-preview').then((preview) => {
      state.irPreview = preview;
      if (state.selectedKey === favKey(item) || item.type === 't3k-live') renderDetails(item);
    }).catch(() => {});
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
    const [p, t, m, c, k] = await Promise.all([
      api('/api/presets').catch(() => ({ presets: [] })),
      api('/api/tone3000/presets').catch(() => ({ presets: [] })),
      api('/api/mooer/presets').catch(() => ({ presets: [] })),
      api('/api/cortex/presets').catch(() => ({ presets: [] })),
      api('/api/kemper/search?limit=100&include_amp=true').catch(() => ({ results: [] })),
    ]);
    state.presets = p.presets || [];
    state.t3kPresets = t.presets || [];
    state.mooerPresets = m.presets || [];
    state.cortexPresets = c.presets || [];
    state.kemperRigs = k.results || [];
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
    } else if (item.type === 'mooer') {
      data = await api('/api/mooer/preset/load', {
        method: 'POST',
        body: { preset_name: item.name },
      });
      state.t3kLoaded = null;
    } else if (item.type === 'cortex') {
      data = await api('/api/cortex/preset/load', {
        method: 'POST',
        body: { id: item.id },
      });
      state.t3kLoaded = null;
      if (data.cortex) {
        state.cortex = data.cortex;
        renderCortexScenes(state.cortex);
        updateGigView(state.cortex);
      }
    } else if (item.type === 'kemper') {
      data = await api('/api/kemper/load', {
        method: 'POST',
        body: { name: item.name, author: item.author, pack_path: item.pack_path, rig_id: item.rig_id },
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
function chainGearVisual(id) {
  const image = id === 'amp' ? (state.t3kLoaded?.image || '') : '';
  if (image) return `<img class="cb-gear-image" src="${esc(image)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.hidden=true">`;
  if (id === 'cab' && state.nam?.includes_cab) {
    return '<span class="cb-gear-state included" title="Cabinet อยู่ใน NAM capture แล้ว">CAB<br>INCLUDED</span>';
  }
  if (id === 'amp') {
  if (id === 'amp') {
    return '';
  }
  }
  if (id === 'cab' && state.irPreview?.waveform?.length) {
    const bars = state.irPreview.waveform.map((v) => `<i style="height:${Math.max(3, Math.round(v * 24))}px"></i>`).join('');
    return `<span class="cb-ir-wave" title="Impulse Response waveform">${bars}</span>`;
  }
  if (false) return '';

  return '';
}

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
    const visual = chainGearVisual(b.id);
    const canNudge = b.id !== 'input' && b.id !== 'output';
    const nudge = canNudge
      ? `<span class="cb-nudge-left" data-nudge-left="${b.id}" title="เลื่อนบล็อกไปข้างหน้า">‹</span><span class="cb-nudge-right" data-nudge-right="${b.id}" title="เลื่อนบล็อกไปข้างหลัง">›</span>`
      : '';
    btn.classList.toggle('gear-block', !!visual);
    btn.classList.toggle('cab-included', b.id === 'cab' && !!state.nam?.includes_cab);
    btn.innerHTML = `${power}${t3kBadge}${nudge}<span class="cb-gear-visual">${visual}</span><span class="cb-icon">${blockIcon(b.id)}</span><span class="cb-en">${blockEn(b.id)}</span><span class="cb-sub">${esc(blockSubtitle(b.id))}</span>`;
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
      const ctrl = makeKnob(kd, toUi(kd, readServer(kd)), { blockId: b.id });
      knobs.appendChild(ctrl.root);
      state.knobControllers.panel.push(ctrl);
    });
  }
  renderAmpFaceplate(b.id);
  renderPanelSide();
}

function renderAmpFaceplate(blockId) {
  const tabsEl = $('panelBlockTabs');
  if (tabsEl) {
    tabsEl.innerHTML = visibleBlocks().map((vb) => {
      const en = blockEnabled(vb.id);
      const active = vb.id === blockId ? 'active' : '';
      const dot = vb.canBypass ? `<span class="pbt-dot ${en ? 'on' : 'off'}"></span>` : '';
      return `<button type="button" class="pbt-tab ${active} ${en ? '' : 'bypassed'}" data-tab-block="${vb.id}" title="คลิกเพื่อแก้ไข · ดับเบิลคลิกเพื่อเปิด/ปิด">${dot}${blockEn(vb.id)}</button>`;
    }).join('');
    tabsEl.querySelectorAll('[data-tab-block]').forEach((tb) => {
      tb.addEventListener('click', () => selectBlock(tb.dataset.tabBlock));
      tb.addEventListener('dblclick', (e) => { e.stopPropagation(); toggleBlock(tb.dataset.tabBlock); });
    });
  }
  const banner = $('ampFaceplateBanner');
  if (banner) { banner.style.display = 'none'; return; }
  if (!banner) return;
  const gain = Number(state.live?.amp?.gain ?? 0.65);
  const vMode = document.body.dataset.voicing || (gain < 0.36 ? 'clean' : (gain > 0.72 ? 'highgain' : 'vintage'));
  const jewelColor = vMode === 'clean' ? '#38bdf8' : (vMode === 'highgain' ? '#f43f5e' : '#f59e0b');
  const glowR = Math.round(9 + gain * 9);
  const tubesSvg = [265, 315, 365, 415, 505, 555, 605, 655].map((cx, idx) => {
    const isPower = idx >= 4;
    const tw = isPower ? 22 : 16;
    const th = isPower ? 40 : 32;
    const ty = isPower ? 10 : 18;
    return `<g><circle cx="${cx}" cy="${ty + th * 0.58}" r="${glowR + (isPower ? 3 : 0)}" fill="url(#tubeGlowGrad)"/><rect x="${cx - tw / 2}" y="${ty}" width="${tw}" height="${th}" rx="${tw / 2}" fill="rgba(15,23,42,0.45)" stroke="#94a3b8" stroke-width="1.2"/><rect x="${cx - tw * 0.28}" y="${ty + 6}" width="${tw * 0.56}" height="${th - 14}" rx="1" fill="#1e293b" stroke="#64748b" stroke-width="0.7"/><circle cx="${cx}" cy="${ty + th * 0.62}" r="${isPower ? 4.2 : 3.2}" fill="#fde047"/><rect x="${cx - tw / 2 - 1}" y="${ty + th - 4}" width="${tw + 2}" height="6" rx="1" fill="#b45309" stroke="#f59e0b" stroke-width="0.6"/></g>`;
  }).join('');
  banner.innerHTML = `<div class="faceplate-wrap"><svg viewBox="0 0 920 64" width="100%" height="64" preserveAspectRatio="none"><rect x="1" y="1" width="918" height="62" rx="5" fill="#0d1118" stroke="#2b3445" stroke-width="1.5"/><rect x="8" y="6" width="212" height="52" rx="3" fill="#141a24" stroke="#334155"/><circle cx="28" cy="32" r="9" fill="${jewelColor}" stroke="#f8fafc" stroke-width="1.5"/><circle cx="25" cy="29" r="3" fill="#ffffff" fill-opacity="0.7"/><text x="46" y="24" fill="#e2e8f0" font-family="monospace" font-size="10" font-weight="700">TUBE STAGE · ${blockId.toUpperCase()}</text><text x="46" y="39" fill="${jewelColor}" font-family="monospace" font-size="9" font-weight="600">BIAS: ${(38 + gain * 14).toFixed(1)}mA · ${vMode.toUpperCase()}</text><rect x="228" y="6" width="456" height="52" rx="3" fill="#070a0f" stroke="#f59e0b" stroke-width="0.9"/><line x1="228" y1="19" x2="684" y2="19" stroke="rgba(255,255,255,0.05)"/><line x1="228" y1="32" x2="684" y2="32" stroke="rgba(255,255,255,0.05)"/><line x1="228" y1="45" x2="684" y2="45" stroke="rgba(255,255,255,0.05)"/>${tubesSvg}<text x="456" y="54" text-anchor="middle" fill="#94a3b8" font-family="monospace" font-size="8" letter-spacing="1.5">4×12AX7 PREAMP  ·  4×EL34/6L6 CLASS A/B POWER STAGE</text><rect x="692" y="6" width="106" height="52" rx="3" fill="#090d14" stroke="#475569"/><path d="M 704 46 A 42 42 0 0 1 786 46" fill="none" stroke="#334155" stroke-width="2.5"/><path d="M 762 24 A 42 42 0 0 1 786 46" fill="none" stroke="#ef4444" stroke-width="2.5"/><line id="vuNeedleIn" x1="745" y1="48" x2="762" y2="18" stroke="#38bdf8" stroke-width="2" stroke-linecap="round"/><circle cx="745" cy="48" r="3" fill="#e2e8f0"/><text x="745" y="56" text-anchor="middle" fill="#94a3b8" font-family="monospace" font-size="8">INPUT VU</text><rect x="804" y="6" width="108" height="52" rx="3" fill="#090d14" stroke="#f59e0b" stroke-width="0.9"/><path d="M 816 46 A 42 42 0 0 1 898 46" fill="none" stroke="#334155" stroke-width="2.5"/><path d="M 874 24 A 42 42 0 0 1 898 46" fill="none" stroke="#ef4444" stroke-width="2.5"/><line id="vuNeedleOut" x1="857" y1="48" x2="878" y2="18" stroke="#f59e0b" stroke-width="2" stroke-linecap="round"/><circle cx="857" cy="48" r="3" fill="#e2e8f0"/><text x="857" y="56" text-anchor="middle" fill="#f59e0b" font-family="monospace" font-size="8">OUTPUT VU</text></svg><div class="voicing-quick-bar"><button type="button" class="mini-btn ${vMode==='clean'?'active':''}" data-voicing-pick="clean">❄️ CLEAN GLASS</button><button type="button" class="mini-btn ${vMode==='vintage'?'active':''}" data-voicing-pick="vintage">🔥 BRITISH PLEXI</button><button type="button" class="mini-btn ${vMode==='highgain'?'active':''}" data-voicing-pick="highgain">⚡ MODERN CHUG</button></div></div>`;
  banner.querySelectorAll('[data-voicing-pick]').forEach((vb) => {
    vb.addEventListener('click', () => {
      const m = vb.dataset.voicingPick;
      document.body.dataset.voicing = m;
      const g = m === 'clean' ? 0.28 : (m === 'highgain' ? 0.85 : 0.58);
      sendParamNow('amp', 'gain', g).then(() => renderPanel());
    });
  });

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
        <div class="ps-title">NAM A2 NEURAL AMP + IR LOADER</div>
        <div class="ps-file" style="color:var(--gold-2); font-weight:700;">${esc(title)}</div>
        ${drow('Architecture', 'NAM A2 (' + (state.namQuality === 'full' ? 'Full 8ch · 12,146w' : 'Lite 3ch · 1,871w') + ')')}
        ${drow('Active Cab IR', esc(state.live?.cab?.ir_name || 'Celestion V30 4x12') + (state.live?.cab?.enabled !== false ? ' (ON)' : ' (BYPASSED)'))}
        ${drow('Liquid Tone Stack', 'ACTIVE (Gain/EQ/Master ปรับได้จริง)')}
        ${drow('Input Gain', (state.nam.input_gain_db ?? 0).toFixed(1) + ' dB')}
        <div class="ps-actions" style="display:grid; grid-template-columns:1fr 1fr; gap:5px; margin-top:6px;">
          <button class="mini-btn" data-action="load-nam" style="border-color:var(--gold); color:var(--gold-2);">📂 เปิดไฟล์ NAM A2</button>
          <button class="mini-btn" data-action="load-ir" style="border-color:#38bdf8; color:#38bdf8;">📂 ใส่ไฟล์ IR (.wav)</button>
          <button class="mini-btn" data-action="activate-24bit-44k">⚡ 24-Bit / 44.1kHz</button>
          <button class="mini-btn" data-action="open-t3k">🌐 คลัง TONE3000</button>
        </div>
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
        <div class="ps-title">DSP TUBE AMP · 4 TOPOLOGIES</div>
        <label class="cab-select-label" style="margin-bottom:6px;">Amp Voicing Topology
          <select id="ampModelSelect" class="cab-select-input">
            <option value="Ozzy_Neural" ${(state.live?.amp?.model || '') === 'Ozzy_Neural' ? 'selected' : ''}>🔥 Ozzy × Neural Oversized 24-Bit (44.1kHz Touch Dynamic)</option>
            <option value="Clean" ${(state.live?.amp?.model || '') === 'Clean' ? 'selected' : ''}>Boutique Class-A Clean (High Headroom)</option>
            <option value="Twin" ${(state.live?.amp?.model || '') === 'Twin' ? 'selected' : ''}>1965 Fender Twin Reverb (6L6 Glass)</option>
            <option value="Plexi" ${(state.live?.amp?.model || '') === 'Plexi' ? 'selected' : ''}>1968 Marshall Super Lead Plexi (EL34 Bark)</option>
            <option value="5150" ${(state.live?.amp?.model || '5150') === '5150' ? 'selected' : ''}>Peavey 5150 / Dual Recto (Tight High-Gain)</option>
          </select>
        </label>
        <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:6px; background:#141a24; padding:6px 8px; border-radius:5px; border:1px solid #232d3d;">
          <span style="font-size:11px; font-weight:600; color:#cbd5e1;">Bright Cap Switch (เพิ่มหัวโน้ต)</span>
          <input type="checkbox" id="chkAmpBright" ${state.live?.amp?.bright ? 'checked' : ''} style="width:16px; height:16px; cursor:pointer;">
        </div>
        <label class="cab-select-label" style="margin-bottom:6px;">NAM A2 Neural Capture + IR Quick Loader
          <select id="quickNamA2Select" class="cab-select-input">
            <option value="">-- เลือกโมเดล NAM A2 ในเครื่อง หรือกดเปิดไฟล์ .nam/.namb --</option>
            <option value="t3k_bogner_fullstack">Bogner Ecstasy 101B (NAM A2 + Real 4x12 IR)</option>
            <option value="t3k_mesa_pitch_shift">Mesa Boogie Dual Rectifier (NAM A2 + Oversized IR)</option>
            <option value="t3k_marshall_bluesbreaker">1966 Marshall JTM45 Bluesbreaker (NAM A2)</option>
            <option value="t3k_dumble_spread">Dumble Overdrive Special (NAM A2 + 2x12 IR)</option>
            <option value="t3k_matchless_crunch">Matchless Brave 30 Class-A (NAM A2 + 2x12 IR)</option>
            <option value="t3k_stereo_crunch_verb">JHS Morning Glory + Boutique Amp (NAM A2)</option>
          </select>
        </label>
        <div class="ps-actions" style="display:grid; grid-template-columns:1fr 1fr; gap:5px; margin-bottom:6px;">
          <button class="mini-btn" data-action="load-nam" style="border-color:var(--gold); color:var(--gold-2);">📂 เปิดไฟล์ NAM A2</button>
          <button class="mini-btn" data-action="load-ir" style="border-color:#38bdf8; color:#38bdf8;">📂 ใส่ไฟล์ IR (.wav)</button>
          <button class="mini-btn" data-action="load-ozzy-neural" style="border-color:#f43f5e; color:#fda4af;">🔥 โทนโอไซด์ × นูลอ</button>
          <button class="mini-btn" data-action="activate-24bit-44k" style="border-color:#10b981; color:#6ee7b7;">⚡ 24-Bit / 44.1kHz</button>
        </div>
        <div class="ps-actions">
          <button class="mini-btn" data-action="load-nam">Load NAM</button>
          <button class="mini-btn" data-action="open-t3k">TONE3000</button>
        </div>
        <div class="seg quality-seg">
          <button data-quality="lite" class="${state.namQuality === 'lite' ? 'active' : ''}">Lite</button>
          <button data-quality="full" class="${state.namQuality === 'full' ? 'active' : ''}">Full</button>
        </div>`;
    if (true) {}
    $('ampModelSelect')?.addEventListener('change', (e) => {
        sendParamNow('amp', 'model', e.target.value).then(() => { renderChain(); renderPanel(); });
      });
      $('chkAmpBright')?.addEventListener('change', (e) => {
        sendParamNow('amp', 'bright', e.target.checked);
      });
      $('quickNamA2Select')?.addEventListener('change', (e) => {
        if (!e.target.value) return;
        api('/api/nam-a2/load-pair', { method: 'POST', body: { nam_id: e.target.value, quality: state.namQuality || 'lite' } }).then((res) => {
          if (res?.state) applyServerState(res.state, { forceRender: true });
          renderChain(); renderPanel();
          showToast('โหลดโมเดล NAM A2 + IR สำเร็จ');
        });
      });
      const _unused2 = ``;
      $('ampModelSelect')?.addEventListener('change', (e) => {
        sendParamNow('amp', 'model', e.target.value).then(() => { renderChain(); renderPanel(); });
      });
      $('chkAmpBright')?.addEventListener('change', (e) => {
        sendParamNow('amp', 'bright', e.target.checked);
      });
      $('quickNamA2Select')?.addEventListener('change', (e) => {
        if (!e.target.value) return;
        api('/api/nam-a2/load-pair', { method: 'POST', body: { nam_id: e.target.value, quality: state.namQuality || 'lite' } }).then((res) => {
          if (res?.state) applyServerState(res.state, { forceRender: true });
          renderChain(); renderPanel();
          showToast('โหลดโมเดล NAM A2 + IR สำเร็จ');
        });
      });
      const _unused = `
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
  if (false) {
    $('ampModelSelect')?.addEventListener('change', (e) => {
      sendParamNow('amp', 'model', e.target.value).then(() => { renderChain(); renderPanel(); });
    });
    $('chkAmpBright')?.addEventListener('change', (e) => {
      sendParamNow('amp', 'bright', e.target.checked);
    });
    return;
  }
  if (b.id === 'cab') {
    const cab = state.live?.cab || {};
    const center = Math.round(cab.center ?? 50);
    const dist = Math.round(cab.distance ?? 20);
    const tube = (cab.tube || 'OFF').toUpperCase();
    const mic = (cab.mic || 'SM57').toUpperCase();

    side.innerHTML = `
      <div class="ps-title">3D VIRTUAL MIC &amp; TUBE VOICING</div>
      <div class="ps-file">${esc(cab.ir_name || 'Default IR')}</div>
      <label class="cab-select-label" style="margin-bottom:6px;">24-Bit / 44.1kHz Studio IR &amp; Cab Selector
        <select id="cabIrQuickSelect" class="cab-select-input">
          <optgroup label="★ 24-Bit / 44.1kHz Studio Master IRs (Ozzy × Neural)">
            <option value="Ozzy British Oversized 4x12 (24-Bit 44.1kHz)" ${(cab.ir_name||'').includes('Ozzy British')?'selected':''}>Ozzy British Oversized 4x12 (24-Bit 44.1kHz)</option>
            <option value="Neural Archetype Oversized V30 (24-Bit 44.1kHz)" ${(cab.ir_name||'').includes('Neural Archetype')?'selected':''}>Neural Archetype Oversized V30 (24-Bit 44.1kHz)</option>
            <option value="1968 Marshall Basketweave Greenback (24-Bit 44.1kHz)" ${(cab.ir_name||'').includes('1968 Marshall')?'selected':''}>1968 Marshall Basketweave Greenback (24-Bit 44.1kHz)</option>
          </optgroup>
          <optgroup label="TONE3000 &amp; Studio Real IRs">
            <option value="t3k_recto_4x12_v30_sm57.wav" ${(cab.ir_name||'').includes('recto_4x12')?'selected':''}>Mesa Rectifier 4x12 V30 (SM57)</option>
            <option value="t3k_1960a_greenback_sm57_r121.wav" ${(cab.ir_name||'').includes('1960a_greenback')?'selected':''}>Marshall 1960A Greenback (SM57+R121)</option>
            <option value="t3k_bogner_uber_v30_t75.wav" ${(cab.ir_name||'').includes('bogner_uber')?'selected':''}>Bogner Uberkab V30+T75</option>
            <option value="t3k_friedman_4x12_v30.wav" ${(cab.ir_name||'').includes('friedman_4x12')?'selected':''}>Friedman 4x12 Vintage 30</option>
            <option value="t3k_evh_5150_4x12.wav" ${(cab.ir_name||'').includes('evh_5150')?'selected':''}>EVH 5150III 4x12 G12EVH</option>
            <option value="Celestion V30 4x12" ${cab.ir_name==='Celestion V30 4x12'?'selected':''}>Celestion V30 4x12 (Classic)</option>
            <option value="Greenback 4x12" ${cab.ir_name==='Greenback 4x12'?'selected':''}>Greenback 4x12 (Classic)</option>
          </optgroup>
        </select>
      </label>
      <div class="cab-3d-wrap">
        <div class="cab-speaker-stage" id="cabSpeakerStage">
          <svg viewBox="0 0 180 180" width="100%" height="100%" style="position:absolute; inset:0; pointer-events:none;"><circle cx="90" cy="90" r="84" fill="url(#speakerConeGrad)" stroke="#334155" stroke-width="3"/><circle cx="90" cy="90" r="76" fill="none" stroke="#1e293b" stroke-width="4"/><circle cx="90" cy="90" r="62" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="1" stroke-dasharray="4 3"/><circle cx="90" cy="90" r="44" fill="none" stroke="rgba(255,255,255,0.1)" stroke-width="1" stroke-dasharray="3 3"/><line x1="90" y1="6" x2="90" y2="174" stroke="rgba(56,189,248,0.18)" stroke-width="1" stroke-dasharray="3 3"/><line x1="6" y1="90" x2="174" y2="90" stroke="rgba(56,189,248,0.18)" stroke-width="1" stroke-dasharray="3 3"/><circle cx="90" cy="90" r="26" fill="#0f141d" stroke="#f59e0b" stroke-width="1.5"/><circle cx="90" cy="90" r="18" fill="url(#knobCapGrad)" stroke="#475569" stroke-width="1"/></svg>
          <div class="speaker-cone-circle" style="width: 90px; height: 90px;"></div>
          <div class="speaker-dust-cap"></div>
          <div class="draggable-mic" id="draggableMic" style="left: ${center}%; top: ${dist}%;">MIC</div>
        </div>
        <div class="cab-controls-grid">
          <label class="cab-select-label">Power Tube
            <select id="cabTubeSelect" class="cab-select-input">
              <option value="OFF" ${tube==='OFF'?'selected':''}>OFF (Pure IR)</option>
              <option value="6L6" ${tube==='6L6'?'selected':''}>6L6 (American Punch)</option>
              <option value="EL34" ${tube==='EL34'?'selected':''}>EL34 (British Mid)</option>
              <option value="EL84" ${tube==='EL84'?'selected':''}>EL84 (Vox Chime)</option>
              <option value="6V6" ${tube==='6V6'?'selected':''}>6V6 (Vintage Warm)</option>
              <option value="KT88" ${tube==='KT88'?'selected':''}>KT88 (Modern High-Headroom)</option>
            </select>
          </label>
          <label class="cab-select-label">Microphone
            <select id="cabMicSelect" class="cab-select-input">
              <option value="SM57" ${mic.includes('57')?'selected':''}>Shure SM57</option>
              <option value="MD421" ${mic.includes('421')?'selected':''}>Sennheiser MD421</option>
              <option value="U87" ${mic.includes('87')?'selected':''}>Neumann U87</option>
              <option value="R121" ${mic.includes('121')||mic.includes('RIBBON')?'selected':''}>Royer R-121 (Ribbon)</option>
            </select>
          </label>
        </div>
        <div class="ps-note">ลากจุดแดง MIC บนดอกลำโพง: แนวนอน = Center/Edge · แนวตั้ง = Distance</div>
      </div>
      <div class="ps-actions" style="margin-top:8px;">
        <button class="mini-btn" data-action="load-ir">Load IR</button>
        <button class="mini-btn" data-action="open-t3k">TONE3000</button>
      </div>`;

    attachCabMicDrag();
    $('cabIrQuickSelect')?.addEventListener('change', async (e) => {
      const irName = e.target.value;
      if (!irName) return;
      try {
        const res = await api('/api/nam-a2/load-pair', {
          method: 'POST',
          body: { ir_name: irName, enable_cab: true }
        });
        if (res?.state) applyServerState(res.state, { forceRender: true });
        await loadIrPreview();
        renderChain(); renderPanel();
        showToast('โหลด IR "' + irName + '" คู่กับแอมป์/NAM A2 แล้ว');
      } catch (err) { showToast(err.message, true); }
    });
    return;
    return;
  }
  if (b.id === 'eq') {
    const eq = state.live?.eq || {};
    const modelId = eq.model_id ?? 5;
    side.innerHTML = `
      <div class="ps-title">STUDIO PARAMETRIC EQ CURVE</div>
      <div class="eq-curve-wrap">
        <svg class="eq-curve-svg" id="eqCurveSvg" viewBox="0 0 300 120" preserveAspectRatio="none">
          <line x1="0" y1="30" x2="300" y2="30" stroke="#1e293b" stroke-width="0.7" stroke-dasharray="3,3"/><line x1="0" y1="60" x2="300" y2="60" stroke="#475569" stroke-width="1" stroke-dasharray="4,2"/><line x1="0" y1="90" x2="300" y2="90" stroke="#1e293b" stroke-width="0.7" stroke-dasharray="3,3"/><line x1="60" y1="0" x2="60" y2="120" stroke="#1e293b" stroke-width="0.7"/><line x1="120" y1="0" x2="120" y2="120" stroke="#1e293b" stroke-width="0.7"/><line x1="180" y1="0" x2="180" y2="120" stroke="#1e293b" stroke-width="0.7"/><line x1="240" y1="0" x2="240" y2="120" stroke="#1e293b" stroke-width="0.7"/>
          <line x1="100" y1="0" x2="100" y2="120" stroke="#1e293b" stroke-width="0.5"/>
          <line x1="200" y1="0" x2="200" y2="120" stroke="#1e293b" stroke-width="0.5"/>
          <path id="eqCurvePath" d="M 0 60 L 300 60" fill="url(#eqAreaGrad)" stroke="#38bdf8" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <div style="display:flex; justify-content:space-between; font-size:9px; color:#64748b; font-family:monospace;">
          <span>20 Hz</span><span>1 kHz</span><span>20 kHz</span>
        </div>
        <div style="display:flex; gap:4px; margin-top:6px;" id="eqModelBtns">
          <button class="mini-btn ${modelId===5?'active':''}" data-model="5">5-Band Studio</button>
          <button class="mini-btn ${modelId===1?'active':''}" data-model="1">Mooer G</button>
          <button class="mini-btn ${modelId===2?'active':''}" data-model="2">Mooer HM</button>
        </div>
      </div>
      <div class="ps-note">EQ กราฟิกจำลองจาก Quad Cortex globalEQ ตอบสนองความถี่แม่นยำระดับสตูดิโอ</div>`;

    drawEqCurve(eq.curve);
    attachEqEvents();
    return;
  }
  if (b.id === 'mod') {
    const mod = state.live?.mod || {};
    const mid = Number(mod.model_id ?? 12);
    const models = [
      [12, '12 · Ana-Chorus (Analog Warm)'],
      [13, '13 · Tri-Chorus (Lush 3-Phase)'],
      [4, '04 · Classic Flanger'],
      [5, '05 · Jet-Flanger (Sweep)'],
      [6, '06 · Optical Tremolo'],
      [7, '07 · Stutter Chopper'],
      [11, '11 · Rotary Speaker'],
      [19, '19 · Lo-Fi Bitcrusher & Decimator'],
    ];
    side.innerHTML = `
      <div class="ps-title">MOOER GE150 · 19-MODEL MODULATION</div>
      <label class="cab-select-label">Modulation Algorithm
        <select id="modModelSelect" class="cab-select-input">
          ${models.map(([id, name]) => `<option value="${id}" ${mid === id ? 'selected' : ''}>${name}</option>`).join('')}
        </select>
      </label>
      <div class="ps-note" style="margin-top:8px;">คัดสำเนาอัลกอริทึม Modulation จาก MOOER GE150 ครบทั้ง Chorus, Flanger, Tremolo และ Lo-Fi Bitcrusher</div>`;
    $('modModelSelect')?.addEventListener('change', (e) => {
      sendParamNow('mod', 'model_id', parseInt(e.target.value, 10)).then(() => renderChain());
    });
    return;
  }
  if (b.id === 'delay') {
    const ducking = !!state.live?.delay?.ducking;
    side.innerHTML = `
      <div class="ps-title">DYNAMIC DUCKING DELAY</div>
      <div class="ps-note">เมื่อเปิด Ducking หาง Delay จะหลบลงอัตโนมัติขณะดีดโน้ตเร็วๆ ทำให้ยินหัวโน้ตชัดเป๊ะ และพวยพุ่งขึ้นมาเมื่อหยุดดีด</div>
      <div style="display:flex; align-items:center; justify-content:space-between; margin-top:8px; background:#141a24; padding:8px; border-radius:6px; border:1px solid #232d3d;">
        <span style="font-size:11px; font-weight:600; color:#cbd5e1;">เปิด Ducking (หลบเสียงดีด)</span>
        <input type="checkbox" id="chkDelayDuck" ${ducking?'checked':''} style="width:18px; height:18px; cursor:pointer;">
      </div>`;
    $('chkDelayDuck')?.addEventListener('change', (e) => {
      api('/api/parameter', { method: 'POST', body: { section: 'delay', param: 'ducking', value: e.target.checked } });
    });
    return;
  }
  if (b.id === 'reverb') {
    const ducking = !!state.live?.reverb?.ducking;
    const rtype = String(state.live?.reverb?.type || 'plate').toLowerCase();
    const rtypeOpts = ['room', 'hall', 'plate', 'cathedral', 'spring']
      .map((t) => `<option value="${t}" ${rtype === t ? 'selected' : ''}>${t.charAt(0).toUpperCase() + t.slice(1)}</option>`)
      .join('');
    side.innerHTML = `
      <div class="ps-title">DYNAMIC DUCKING REVERB</div>
      <label class="cab-select-label">Type
        <select id="reverbTypeSelect" class="cab-select-input">${rtypeOpts}</select>
      </label>
      <div class="ps-note">เมื่อเปิด Ducking มวล Reverb จะลดระดับลงชั่วขณะในระหว่างดีดริฟฟ์เร็วๆ ไม่ทำให้เสียงตีกันเละ (Muddy)</div>
      <div style="display:flex; align-items:center; justify-content:space-between; margin-top:8px; background:#141a24; padding:8px; border-radius:6px; border:1px solid #232d3d;">
        <span style="font-size:11px; font-weight:600; color:#cbd5e1;">เปิด Ducking (หลบเสียงดีด)</span>
        <input type="checkbox" id="chkReverbDuck" ${ducking?'checked':''} style="width:18px; height:18px; cursor:pointer;">
      </div>`;
    $('reverbTypeSelect')?.addEventListener('change', (e) => {
      api('/api/parameter', { method: 'POST', body: { section: 'reverb', param: 'type', value: e.target.value } });
    });
    $('chkReverbDuck')?.addEventListener('change', (e) => {
      api('/api/parameter', { method: 'POST', body: { section: 'reverb', param: 'ducking', value: e.target.checked } });
    });
    return;
  }
  if (b.id === 'output') {
    const hd = state.lastServer?.hd_audio || { enabled: false, auto_level: false, output_trim_db: 0, pure_cab: 0.65, stereo_width: 0.60, anti_squash: 0.70, telemetry: { rms_dbfs: -15.0, crest_db: 12.5, stereo_width_pct: 55, makeup_db: 0.0 } };
    const tel = hd.telemetry || {};
    side.innerHTML = `
      <div class="ps-title">WORLD-CLASS MASTERING & ANTI-SQUASH</div>
      <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:6px; background:#141a24; padding:5px 8px; border-radius:5px; border:1px solid #232d3d;" title="ใช้ CPU ประมาณ 2 เท่า — แนะนำ buffer 256 ขึ้นไป">
        <span style="font-size:11px; font-weight:600; color:#cbd5e1;">HD Stereo Engine (CPU ~2x · buffer 256+)</span>
        <input type="checkbox" id="chkHdEnabled" ${hd.enabled ? 'checked' : ''} style="width:16px; height:16px; cursor:pointer;">
      </div>
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:4px; margin-bottom:6px; font-family:var(--mono); font-size:10.5px;">
        <div style="background:#11161f; padding:4px 6px; border-radius:4px; border:1px solid #222a38;">RMS: <strong style="color:var(--gold-2)">${tel.rms_dbfs ?? -15.0} dBFS</strong></div>
        <div style="background:#11161f; padding:4px 6px; border-radius:4px; border:1px solid #222a38;">CREST: <strong style="color:#10b981">${tel.crest_db ?? 12.0} dB</strong></div>
        <div style="background:#11161f; padding:4px 6px; border-radius:4px; border:1px solid #222a38;">3D WIDTH: <strong style="color:#38bdf8">${tel.stereo_width_pct ?? 50}%</strong></div>
        <div style="background:#11161f; padding:4px 6px; border-radius:4px; border:1px solid #222a38;">AUTO-GAIN: <strong style="color:#c084fc">${(tel.makeup_db >= 0 ? '+' : '') + (tel.makeup_db ?? 0.0)} dB</strong></div>
      </div>
      <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:6px; background:#141a24; padding:5px 8px; border-radius:5px; border:1px solid #232d3d;">
        <span style="font-size:11px; font-weight:600; color:#cbd5e1;">Auto-Leveler (คุมความดังคงที่)</span>
        <input type="checkbox" id="chkHdAutoLevel" ${hd.auto_level === true ? 'checked' : ''} style="width:16px; height:16px; cursor:pointer;">
      </div>
      <label class="cab-select-label" style="font-size:10.5px;">HD Output Trim (${(hd.output_trim_db ?? 0) >= 0 ? '+' : ''}${Number(hd.output_trim_db ?? 0).toFixed(1)} dB)
        <input type="range" id="rngHdTrim" min="-24" max="12" step="0.5" value="${Number(hd.output_trim_db ?? 0)}" style="width:100%; accent-color:#cbd5e1;">
      </label>
      <label class="cab-select-label" style="font-size:10.5px;">Anti-Squash & Dynamic Sag (${Math.round((hd.anti_squash ?? 0.7) * 100)}%)
        <input type="range" id="rngHdAntiSquash" min="0" max="100" value="${Math.round((hd.anti_squash ?? 0.7) * 100)}" style="width:100%; accent-color:var(--gold);">
      </label>
      <label class="cab-select-label" style="font-size:10.5px; margin-top:4px;">Pure Cabinet & Speaker Thump (${Math.round((hd.pure_cab ?? 0.65) * 100)}%)
        <input type="range" id="rngHdPureCab" min="0" max="100" value="${Math.round((hd.pure_cab ?? 0.65) * 100)}" style="width:100%; accent-color:#38bdf8;">
      </label>
      <label class="cab-select-label" style="font-size:10.5px; margin-top:4px;">3D Stereo Space & Doubler (${Math.round((hd.stereo_width ?? 0.6) * 100)}%)
        <input type="range" id="rngHdStereo" min="0" max="100" value="${Math.round((hd.stereo_width ?? 0.6) * 100)}" style="width:100%; accent-color:#10b981;">
      </label>
      <label class="cab-select-label" style="font-size:10.5px; margin-top:4px;">Natural Touch Dynamics · ตอบสนองน้ำหนักมือ (${Math.round((hd.touch_sensitivity ?? 0.85) * 100)}%)
        <input type="range" id="rngHdTouch" min="0" max="100" value="${Math.round((hd.touch_sensitivity ?? 0.85) * 100)}" style="width:100%; accent-color:#f97316;">
      </label>
      <div style="display:flex; align-items:center; justify-content:space-between; margin-top:6px; background:#141a24; padding:5px 8px; border-radius:5px; border:1px solid #232d3d;">
        <span style="font-size:11px; font-weight:600; color:#f97316;">Ozzy × Neural Stereo Doubler (±9ct)</span>
        <input type="checkbox" id="chkHdOzzyDoubler" ${hd.ozzy_doubler ? 'checked' : ''} style="width:16px; height:16px; cursor:pointer;">
      </div>`;
    $('rngHdTouch')?.addEventListener('change', (e) => {
      api('/api/hd-audio/update', { method: 'POST', body: { touch_sensitivity: Number(e.target.value) / 100 } }).then(() => renderPanelSide());
    });
    $('chkHdOzzyDoubler')?.addEventListener('change', (e) => {
      api('/api/hd-audio/update', { method: 'POST', body: { ozzy_doubler: e.target.checked } }).then(() => renderPanelSide());
    });
    $('chkHdEnabled')?.addEventListener('change', (e) => {
      api('/api/hd-audio/update', { method: 'POST', body: { enabled: e.target.checked } }).then(() => renderPanelSide());
    });
    $('rngHdTrim')?.addEventListener('change', (e) => {
      api('/api/hd-audio/update', { method: 'POST', body: { output_trim_db: Number(e.target.value) } }).then(() => renderPanelSide());
    });
    $('chkHdAutoLevel')?.addEventListener('change', (e) => {
      api('/api/hd-audio/update', { method: 'POST', body: { auto_level: e.target.checked } }).then(() => renderPanelSide());
    });
    $('rngHdAntiSquash')?.addEventListener('change', (e) => {
      api('/api/hd-audio/update', { method: 'POST', body: { anti_squash: Number(e.target.value) / 100 } }).then(() => renderPanelSide());
    });
    $('rngHdPureCab')?.addEventListener('change', (e) => {
      api('/api/hd-audio/update', { method: 'POST', body: { pure_cab: Number(e.target.value) / 100 } }).then(() => renderPanelSide());
    });
    $('rngHdStereo')?.addEventListener('change', (e) => {
      api('/api/hd-audio/update', { method: 'POST', body: { stereo_width: Number(e.target.value) / 100 } }).then(() => renderPanelSide());
    });
    return;
  }
  if (false) {
    side.innerHTML = `
      <div class="ps-title">OUTPUT · MASTER</div>
      <div class="ps-note">Master volume อยู่ท้ายเชนหลัง CAB และ REVERB ใช้คุมระดับออกโดยไม่เปลี่ยนเกนของแอมป์</div>
      ${drow('Tip', 'ถ้าเสียงแตกเกิน ให้ลดที่ AMP Volume ก่อน')}`;
    return;
  }
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

// ── audio path helpers ───────────────────────────────────────────────
// The engine reports the driver's real round-trip latency.  The block
// deadline (block/sample rate) is only ~2.7 ms and is NOT what the player
// feels -- showing it alone made a 106 ms fallback path look fast.
function shortHostApi(name) {
  if (!name) return '—';
  if (/wasapi/i.test(name)) return 'WASAPI';
  if (/asio/i.test(name)) return 'ASIO';
  if (/wdm-ks/i.test(name)) return 'WDM-KS';
  if (/directsound/i.test(name)) return 'DSOUND';
  if (/mme/i.test(name)) return 'MME';
  return String(name);
}

function shortenDevice(name, max = 26) {
  if (!name) return 'system default';
  const clean = String(name).replace(/\s*\(Line 6[^)]*\)/i, '').trim();
  return clean.length > max ? clean.slice(0, max - 1) + '…' : clean;
}

function audioLatencyLevel(ms) {
  if (ms == null) return '';
  if (ms <= 15) return 'lat-good';
  if (ms <= 60) return 'lat-ok';
  return 'lat-bad';
}

function audioPathWarning(path) {
  if (!path || !path.warning) return '';
  if (path.warning === 'fallback') {
    const err = path.error ? ' — UX1 เปิดไม่สำเร็จ' : '';
    return `กำลังใช้การ์ดเสียงเริ่มต้นแทน UX1${err} (หน่วง ${Number(path.reported_io_ms ?? 0).toFixed(0)} ms) เปิด Settings เพื่อเลือกอุปกรณ์`;
  }
  if (path.warning === 'dsp_over_budget') {
    const dsp = Number(path.dsp_avg_ms ?? 0).toFixed(1);
    return `DSP ใช้ ${dsp} ms/block เกินงบ ${Number(path.buffer_ms ?? 0).toFixed(1)} ms — เสี่ยงเสียงแตก ลองเพิ่ม buffer เป็น 256`;
  }
  if (path.warning === 'high_latency') {
    return `ความหน่วงสูง ${Number(path.reported_io_ms ?? 0).toFixed(0)} ms — ตรวจอุปกรณ์/buffer ใน Settings`;
  }

  return '';
}

function updateStatus(server) {
  state.lastServer = server;
  const sr = Number(server.sample_rate || 48000);
  const bs = Number(server.block_size || 128);
  const stats = server.audio_stats || {};
  const deadline = Number(stats.deadline_ms || (bs / sr * 1000));
  const hw = stats.stream_latency || {};
  const path = server.audio_path || {};
  const sys = server.system || {};
  const ioMs = path.reported_io_ms ?? hw.reported_io_ms;
  const hwLabel = ioMs == null ? 'HW I/O —' : `HW I/O ${Number(ioMs).toFixed(1)} ms`;
  const apiShort = shortHostApi(path.output?.hostapi || path.input?.hostapi);

  if ($('spec-path')) {
    const pathEl = $('spec-path');
    pathEl.textContent = !server.is_running ? '—' : (path.using_fallback ? 'FALLBACK' : apiShort);
    pathEl.className = path.using_fallback ? 'lat-bad' : '';
  }
  const warnText = audioPathWarning(path);
  if ($('se-audio-warn')) {
    $('se-audio-warn').textContent = warnText;
    $('se-audio-warn').classList.toggle('hidden', !warnText);
  }
  if ($('status-audio-warn')) {
    $('status-audio-warn').textContent = warnText || '';
    $('status-audio-warn').classList.toggle('hidden', !warnText);
  }
  if (warnText && server.is_running && state.lastAudioWarning !== warnText) {
    state.lastAudioWarning = warnText;
    showToast(warnText, true);
  }
  if (!warnText) state.lastAudioWarning = '';

  if ($('status-audio-perf')) {
    // Short enough to stay on one line at 1280; the full breakdown (device
    // names, block deadline, max callback) lives in the tooltip.
    const cbTxt = stats.callback_ms_avg == null
      ? ''
      : ` · DSP ${Number(stats.callback_ms_avg).toFixed(2)} ms`;
    const xruns = Object.values(stats.xruns || {}).reduce((a, b) => a + Number(b || 0), 0);
    const perf = $('status-audio-perf');
    perf.textContent = `${hwLabel}${cbTxt} · XRUN ${xruns}`;
    perf.title = [
      `SR ${sr.toLocaleString()} Hz`,
      `block ${bs} smp (${deadline.toFixed(2)} ms)`,
      path.output?.name ? `${shortenDevice(path.input?.name, 40)} -> ${shortenDevice(path.output?.name, 40)}` : '',
      stats.callback_ms_max != null ? `max callback ${Number(stats.callback_ms_max).toFixed(2)} ms` : '',
    ].filter(Boolean).join(' · ');
  }
  if ($('status-system-telemetry')) {
    $('status-system-telemetry').textContent = `CPU ${sys.cpu_percent ?? 0}% · RAM ${sys.ram_mb ?? 0} MB`;
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
  if (server.chain) {
    const previousIrName = state.irPreview?.name;
    if (!state.irPreview || previousIrName !== server.chain.cab?.ir_name) {
      api('/api/cab/ir-preview').then((preview) => {
        state.irPreview = preview;
        renderChain();
      }).catch(() => {});
    }
  }

  // Gig View meter & tuner mirrors
  if ($('gigMeterIn')) $('gigMeterIn').style.width = Math.min(100, Math.max(0, server.input_meter || 0)) + '%';
  if ($('gigMeterOut')) $('gigMeterOut').style.width = Math.min(100, Math.max(0, server.output_meter || 0)) + '%';
  updateGigTuner(server);

  const badge = $('engine-badge');
  if (badge) {
    const bitDepth = server.hd_audio?.bit_depth || 24;
    const srKhz = (sr / 1000).toFixed(1);
    const modeLabel = state.nam ? ('NAM A' + (state.namArch || '2') + '+IR') : (server.chain?.amp?.topology === 'Ozzy_Neural' ? 'OZZY×NEURAL' : 'DSP AMP');
    badge.textContent = `${bitDepth}-BIT · ${srKhz}kHz · ${modeLabel}`;
  }
}

function applyServerState(server, opts = {}) {
  if (!server) return;
  const prevNamKey = state.namKey;
  state.live = server.chain || {};
  state.nam = server.nam || null;
  state.namKey = state.nam
    ? ((state.nam.stages || []).map((s) => s.title || '').join('|') + '|' + (state.nam.enabled ? '1' : '0') + '|' + (state.nam.includes_cab ? 'cab' : ''))
    : 'none';
  if (server.t3k_last_load) state.t3kLoaded = server.t3k_last_load;
  state.isRunning = !!server.is_running;
  if (server.sample_rate !== undefined) state.sampleRate = Number(server.sample_rate);
  if (server.block_size !== undefined) state.bufferSize = Number(server.block_size);
  if (server.input_device !== undefined) state.selectedIn = server.input_device;
  if (server.output_device !== undefined) state.selectedOut = server.output_device;

  if (server.cortex) {
    // While a scene click is in flight, keep the optimistic selection so a poll
    // that raced the request cannot flip the LED back.
    state.cortex = state.pendingScene == null
      ? server.cortex
      : { ...server.cortex, active_scene_index: state.pendingScene };
    renderCortexScenes(state.cortex);
    updateGigView(state.cortex, server);
  }

  const orderCandidate = server.chain_order || server.chain?.device?.order;
  if (orderCandidate && Array.isArray(orderCandidate)) {
    const newOrder = orderCandidate;
    const oldOrderStr = (state.chainOrder || []).join(',');
    const newOrderStr = newOrder.join(',');
    if (oldOrderStr !== newOrderStr) {
      state.chainOrder = newOrder;
      opts.forceRender = true;
    }
  }

  if (prevNamKey !== state.namKey || opts.forceRender) {
    renderChain();
    renderPanel();
  } else {
    updateChainLive();
    syncKnobs();
  }
  if (server.morph && $('morphSlider') && !$('morphSlider').matches(':active')) {
    const m = server.morph;
    $('morphSlider').value = Math.round((m.morph_pos || 0) * 100);
    if ($('morphReadout')) $('morphReadout').textContent = `${Math.round((m.morph_pos || 0) * 100)}% (${(m.morph_pos || 0) < 0.5 ? 'A' : 'B'})`;
  }
  if (server.chain?.parallel) {
    const p = server.chain.parallel;
    $('btn-parallel-toggle')?.classList.toggle('active', !!p.enabled);
    if ($('parallelBlendSlider') && !$('parallelBlendSlider').matches(':active')) {
      $('parallelBlendSlider').value = Math.round((p.blend || 0.3) * 100);
      if ($('parallelBlendReadout')) $('parallelBlendReadout').textContent = `${Math.round((p.blend || 0.3) * 100)}%`;
    }
  }
  if (state.block === 'eq' && server.chain?.eq?.curve) {
    drawEqCurve(server.chain.eq.curve);
  }
  updateDynamicVoicingAccent();
  syncSliderProgressCss($('morphSlider'));
  syncSliderProgressCss($('parallelBlendSlider'));
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
function deviceOptionLabel(d) {
  const api = shortHostApi(d.hostapi_name);
  const ch = Number(d.inputs) > 0 ? `${d.inputs} in` : `${d.outputs} out`;
  const star = /UX1|Line 6/i.test(d.name || '') ? '★ ' : '';
  return `${star}${d.name} · ${api} · ${ch}`;
}

function fillSettingsDevices() {
  const inSel = $('modal-select-in');
  const outSel = $('modal-select-out');
  if (!inSel || !outSel) return;
  const inputs = state.devices.inputs || [];
  const outputs = state.devices.outputs || [];
  inSel.innerHTML = inputs.map((d) => `<option value="${d.id}" ${d.id === state.selectedIn ? 'selected' : ''}>${esc(deviceOptionLabel(d))}</option>`).join('') || '<option value="">— none —</option>';
  outSel.innerHTML = outputs.map((d) => `<option value="${d.id}" ${d.id === state.selectedOut ? 'selected' : ''}>${esc(deviceOptionLabel(d))}</option>`).join('') || '<option value="">— none —</option>';
  updateSettingsAudioNote();
}

function updateSettingsAudioNote() {
  const el = $('modal-audio-path-note');
  if (!el) return;
  const path = state.lastServer?.audio_path || {};
  const io = path.reported_io_ms;
  const api = shortHostApi(path.output?.hostapi || path.input?.hostapi);
  const rows = [];
  if (path.using_fallback) {
    rows.push('<b class="lat-bad">FALLBACK</b> — กำลังใช้การ์ดเสียงเริ่มต้น ไม่ใช่ UX1');
  } else if (io != null) {
    rows.push(`สตรีมปัจจุบัน: <b>${esc(api)}</b> · <b class="${audioLatencyLevel(io)}">${Number(io).toFixed(1)} ms</b> round trip`);
  } else {
    rows.push('สตรีมยังไม่เปิด — เลือกอุปกรณ์แล้วกด Apply');
  }
  if (path.buffer_ms != null) rows.push(`block ${esc(String(state.lastServer?.block_size ?? ''))} smp = ${Number(path.buffer_ms).toFixed(2)} ms`);
  if (state.asioDrivers && state.asioDrivers.length > 0) {
    const asioList = state.asioDrivers.map(d => `<span style="color:${d.is_ux1 ? '#38bdf8' : '#94a3b8'}">${esc(d.name)}</span>`).join(', ');
    rows.push(`<div style="margin-top:6px; font-size:11px; opacity:0.9;"><b>ASIO Windows Drivers:</b> ${asioList}</div>`);
  }
  el.innerHTML = rows.join('<br>');
}

async function loadDevices() {
  try {
    const data = await api('/api/devices');
    const devices = data.devices || [];
    state.devices.inputs = devices.filter((d) => Number(d.inputs) > 0);
    state.devices.outputs = devices.filter((d) => Number(d.outputs) > 0);
    state.selectedIn = data.selected_in ?? null;
    state.selectedOut = data.selected_out ?? null;
    state.asioDrivers = data.asio_drivers || [];
    fillSettingsDevices();
  } catch (err) {
    showToast('โหลดรายการอุปกรณ์ไม่สำเร็จ: ' + err.message, true);
  }
}

function openSettings() {
  fillSettingsDevices();
  if ($('sw-show-pitch')) $('sw-show-pitch').checked = state.showPitch;

  // Set sample rate & buffer size from live engine state
  const curSr = state.sampleRate || Number(state.lastServer?.sample_rate) || 48000;
  if ($('modal-select-sr')) $('modal-select-sr').value = String(curSr);

  const curBuf = state.bufferSize || Number(state.lastServer?.block_size) || 128;
  if ($('modal-select-buf')) $('modal-select-buf').value = String(curBuf);

  // Set Input Trim
  const curTrim = state.live?.chain?.input?.trim_db ?? 0.0;
  if ($('modal-input-trim')) $('modal-input-trim').value = curTrim;
  if ($('modal-trim-readout')) $('modal-trim-readout').textContent = (curTrim >= 0 ? '+' : '') + Number(curTrim).toFixed(1) + ' dB';

  // Set Master Volume
  const curVol = Math.round((state.live?.chain?.master_volume ?? 1.0) * 100);
  if ($('modal-master-vol')) $('modal-master-vol').value = curVol;
  if ($('modal-vol-readout')) $('modal-vol-readout').textContent = curVol + '%';

  const lite = $('btn-quality-lite');
  const full = $('btn-quality-full');
  if (lite) lite.classList.toggle('active', state.namQuality === 'lite');
  if (full) full.classList.toggle('active', state.namQuality === 'full');
  updateSettingsAudioNote();
  $('modal-settings')?.classList.remove('hidden');
}

function closeSettings() {
  $('modal-settings')?.classList.add('hidden');
}

async function applySettings() {
  const inId = $('modal-select-in')?.value;
  const outId = $('modal-select-out')?.value;
  const sr = Number($('modal-select-sr')?.value || state.sampleRate || 48000);
  const buf = Number($('modal-select-buf')?.value || state.bufferSize || 256);

  try {
    const data = await api('/api/settings', {
      method: 'POST',
      body: {
        input_id: inId === '' ? null : Number(inId),
        output_id: outId === '' ? null : Number(outId),
        sample_rate: sr,
        buffer_size: buf,
      },
    });
    state.sampleRate = sr;
    state.bufferSize = buf;
    localStorage.setItem('tone.sampleRate', sr);
    localStorage.setItem('tone.bufferSize', buf);
    if (data.state) applyServerState(data.state, { forceRender: true });
    closeSettings();
    const realMs = data.state?.audio_path?.reported_io_ms;
    const latTxt = realMs == null
      ? `${(buf / sr * 1000).toFixed(1)} ms (buffer)`
      : `${Number(realMs).toFixed(1)} ms round trip`;
    showToast(data.success ? `บันทึกแล้ว: ${sr.toLocaleString()} Hz · ${buf} samples · ${latTxt}` : (data.message || 'บันทึกไม่สำเร็จ'), !data.success);
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
  if (blockId === 'amp') input.accept = '.nam,.namb,.t3kpreset,.json';
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
  if (target === 'amp') file = files.find((f) => /\.(nam|namb|t3kpreset|json)$/i.test(f.name));
  else if (target === 'cab') file = files.find((f) => /\.wav$/i.test(f.name));
  else file = files.find((f) => /\.(nam|namb|t3kpreset|json)$/i.test(f.name)) || files.find((f) => /\.wav$/i.test(f.name));

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
    await loadIrPreview();
    renderChain();
    renderPanel();
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
      renderChain(); renderPanel();
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

async function loadIrPreview() {
  try {
    const preview = await api('/api/cab/ir-preview');
    if (preview) {
      state.irPreview = preview;
      if (state.block === 'cab') renderPanel();
    }
  } catch (err) {
    /* ignore preview failures */
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
  state.pollTimer = setInterval(pollOnce, 250);
  pollOnce();
}

async function reorderBlock(blockId, delta) {
  try {
    const res = await api('/api/chain/reorder', {
      method: 'POST',
      body: { block: blockId, direction: delta > 0 ? 'right' : 'left' }
    });
    if (res?.order) {
      state.chainOrder = res.order;
      if (res.state) applyServerState(res.state, { forceRender: true });
      renderChain();
      selectBlock(blockId);
      showToast(`ย้ายบล็อก ${blockEn(blockId)} สำเร็จ`);
    }
  } catch (err) {
    showToast('ย้ายบล็อกไม่สำเร็จ: ' + err.message, true);
  }
}

async function applyQuickScene(name) {
  try {
    const res = await api('/api/scenes/quick', { method: 'POST', body: { scene: name } });
    if (res?.state) {
      applyServerState(res.state, { forceRender: true });
      renderChain();
      renderPanel();
    }
    updateSceneUi(name);
    showToast(`เปิดซีน: ${name.toUpperCase()} สำเร็จ`);
  } catch (err) {
    showToast('เปลี่ยนซีนไม่สำเร็จ: ' + err.message, true);
  }
}

function updateSceneUi(activeName) {
  ['clean', 'rhythm', 'lead'].forEach((s) => {
    const btn = $(`btn-scene-${s}`);
    if (btn) btn.classList.toggle('active', s === activeName);
  });
}

async function handleAbClick(e) {
  if (e.shiftKey) {
    try {
      const res = await api('/api/ab/store', { method: 'POST', body: { slot: 'A' } });
      updateAbUi(res);
      showToast('บันทึกค่า Rig ปัจจุบันลงใน Snapshot A แล้ว');
    } catch (err) {
      showToast(err.message, true);
    }
    return;
  }
  try {
    const res = await api('/api/ab/toggle', { method: 'POST' });
    if (res?.state) {
      applyServerState(res.state, { forceRender: true });
      renderChain();
      renderPanel();
    }
    updateAbUi(res);
    showToast(`สลับ Rig เป็น: ${res?.active_slot === 'A' ? 'Snapshot [A]' : 'Live Rig [B]'}`);
  } catch (err) {
    showToast(err.message, true);
  }
}

function updateAbUi(abState) {
  const btn = $('btn-ab-toggle');
  if (!btn) return;
  if (!abState || !abState.has_a) {
    btn.textContent = 'A/B: LIVE';
    btn.classList.remove('active-a', 'active-b');
  } else {
    btn.textContent = `A/B: ${abState.active_slot}`;
    btn.classList.toggle('active-a', abState.active_slot === 'A');
    btn.classList.toggle('active-b', abState.active_slot === 'B');
  }
}

let midiPollTimer = null;

async function openMidiModal() {
  const modal = $('modal-midi');
  if (!modal) return;
  modal.classList.remove('hidden');
  await refreshMidiModal();
  if (!midiPollTimer) {
    midiPollTimer = setInterval(refreshMidiModal, 1500);
  }
}

function closeMidiModal() {
  const modal = $('modal-midi');
  if (modal) modal.classList.add('hidden');
  if (midiPollTimer) {
    clearInterval(midiPollTimer);
    midiPollTimer = null;
  }
  api('/api/midi/learn', { method: 'POST', body: { action: null } }).catch(() => {});
}

const ACTION_LABELS = {
  scene_clean: 'Quick Scene: Clean',
  scene_rhythm: 'Quick Scene: Rhythm',
  scene_lead: 'Quick Scene: Lead',
  ab_toggle: 'Rig A/B Toggle',
  ab_store: 'Rig A/B Store Snapshot A',
  bypass_gate: 'Bypass: Noise Gate',
  bypass_comp: 'Bypass: Compressor',
  bypass_drive: 'Bypass: Overdrive',
  bypass_amp: 'Bypass: NAM Amp',
  bypass_cab: 'Bypass: Cabinet IR',
  bypass_chorus: 'Bypass: Chorus',
  bypass_delay: 'Bypass: Delay',
  bypass_reverb: 'Bypass: Reverb',
  preset_prev: 'Preset: Previous',
  preset_next: 'Preset: Next',
  tuner_toggle: 'Tuner: Toggle',
};

async function refreshMidiModal() {
  try {
    const data = await api('/api/midi/status');
    const banner = $('midiDeviceCount');
    if (banner) {
      if (data.available_ports && data.available_ports.length > 0) {
        banner.textContent = `MIDI พร้อมใช้งาน: ${data.active_port || data.available_ports.join(', ')}`;
      } else {
        banner.textContent = 'ยังไม่พบอุปกรณ์ MIDI Controller เชื่อมต่ออยู่';
      }
    }
    const tbody = $('midiMappingsBody');
    if (!tbody) return;
    const mappings = data.mappings || {};
    const learning = data.learning_target;

    const actionToTrigger = {};
    for (const [k, v] of Object.entries(mappings)) {
      actionToTrigger[v] = k;
    }

    const rows = Object.entries(ACTION_LABELS).map(([action, label]) => {
      const trig = actionToTrigger[action];
      const isLearning = learning === action;
      return `<tr>
        <td><strong>${esc(label)}</strong></td>
        <td><span class="midi-binding-badge ${trig ? 'bound' : ''}">${trig ? esc(trig.toUpperCase()) : '— ไม่ได้ผูก —'}</span></td>
        <td>
          <button class="btn btn-sm ${isLearning ? 'btn-learning' : 'btn-ghost'}" data-learn-action="${action}">
            ${isLearning ? '● กำลังจับคู่...' : 'LEARN'}
          </button>
          ${trig ? `<button class="btn btn-sm btn-ghost btn-clear" data-clear-action="${action}" title="ล้างการจับคู่">✕</button>` : ''}
        </td>
      </tr>`;
    });
    tbody.innerHTML = rows.join('');
  } catch (err) {
    console.warn('refreshMidiModal error:', err);
  }
}

async function handleMidiBodyClick(e) {
  const learnBtn = e.target.closest('[data-learn-action]');
  if (learnBtn) {
    const act = learnBtn.dataset.learnAction;
    try {
      await api('/api/midi/learn', { method: 'POST', body: { action: act } });
      await refreshMidiModal();
      showToast(`โหมด MIDI Learn: กดปุ่มหรือเหยียบฟุตสวิตช์สำหรับ ${ACTION_LABELS[act] || act}`);
    } catch (err) {
      showToast(err.message, true);
    }
    return;
  }
  const clearBtn = e.target.closest('[data-clear-action]');
  if (clearBtn) {
    const act = clearBtn.dataset.clearAction;
    try {
      await api('/api/midi/clear', { method: 'POST', body: { action: act } });
      await refreshMidiModal();
      showToast(`ล้างการผูก MIDI ของ ${ACTION_LABELS[act] || act} แล้ว`);
    } catch (err) {
      showToast(err.message, true);
    }
  }
}

function bindEvents() {
  $('btn-power')?.addEventListener('click', async () => {
    try {
      if (state.isRunning) {
        await api('/api/stop', { method: 'POST' });
      } else {
        const savedSr = state.sampleRate || Number(localStorage.getItem('tone.sampleRate')) || 48000;
        const savedBuf = state.bufferSize || Number(localStorage.getItem('tone.bufferSize')) || 256;
        const d = await api('/api/start', {
          method: 'POST',
          body: {
            sample_rate: savedSr,
            buffer_size: savedBuf,
            input_id: state.selectedIn,
            output_id: state.selectedOut
          }
        });
        if (d.state) applyServerState(d.state);
      }
      await pollOnce();
    } catch (err) { showToast(err.message, true); }
  });

  $('btn-tuner-toggle')?.addEventListener('click', toggleTuner);
  $('btn-tuner-close')?.addEventListener('click', () => { if (state.tunerActive) toggleTuner(); });

  $('btn-settings-open')?.addEventListener('click', openSettings);
  $('engine-badge')?.addEventListener('click', () => {
    const currentSr = state.sampleRate || Number(state.lastServer?.sample_rate) || 48000;
    api('/api/audio/24bit-44k', { method: 'POST', body: { sample_rate: currentSr, bit_depth: 24, touch_sensitivity: 0.88 } })
      .then((res) => {
        localStorage.setItem('tone.sampleRate', String(currentSr));
        if (res?.state) applyServerState(res.state, { forceRender: true });
        showToast(`เปิดใช้งาน 24-Bit / ${currentSr.toLocaleString()} Hz Studio Natural Dynamics แล้ว`);
      })
      .catch((err) => showToast(err.message, true));
  });
  $('btn-refresh-devices')?.addEventListener('click', async () => {
    await loadDevices();
    showToast('รีเฟรชรายการอุปกรณ์เสียงแล้ว');
  });
  $('btn-close-settings')?.addEventListener('click', closeSettings);
  $('btn-apply-settings')?.addEventListener('click', applySettings);
  $('modal-settings')?.addEventListener('click', (e) => { if (e.target.id === 'modal-settings') closeSettings(); });
  $('sw-show-pitch')?.addEventListener('change', (e) => setShowPitch(e.target.checked));
  $('btn-quality-lite')?.addEventListener('click', () => setNamQuality('lite'));
  $('btn-quality-full')?.addEventListener('click', () => setNamQuality('full'));

  $('modal-input-trim')?.addEventListener('input', (e) => {
    const v = Number(e.target.value);
    if ($('modal-trim-readout')) $('modal-trim-readout').textContent = (v >= 0 ? '+' : '') + v.toFixed(1) + ' dB';
    sendParamNow('input', 'trim', v);
  });

  $('modal-master-vol')?.addEventListener('input', (e) => {
    const v = Number(e.target.value);
    if ($('modal-vol-readout')) $('modal-vol-readout').textContent = v + '%';
    sendParamNow('master', 'volume', v / 100.0);
  });

  $('btn-save-preset')?.addEventListener('click', () => savePreset(false));
  $('btn-save-as-preset')?.addEventListener('click', () => savePreset(true));
  $('btn-import-preset')?.addEventListener('click', () => $('universal-file-input')?.click());
  $('universal-file-input')?.addEventListener('change', async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    try {
      showToast(`กำลังนำเข้า ${file.name}...`);
      const res = await fetch('/api/preset/import', { method: 'POST', body: fd });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data.detail || 'นำเข้าไม่สำเร็จ');
      showToast(`นำเข้าสำเร็จ: ${data.name || file.name}`);
      await loadPresetLibrary();
      const server = await api('/api/status');
      applyServerState(server, { forceRender: true });
    } catch (err) {
      showToast('นำเข้าไม่สำเร็จ: ' + err.message, true);
    }
  });
  $('prevPreset')?.addEventListener('click', stepPreset);
  $('nextPreset')?.addEventListener('click', stepPresetNext);
  $('btn-refresh-lib')?.addEventListener('click', async () => {
    await loadPresetLibrary();
    if (t3kMain.liveMode) {
      await searchT3KLive(t3kMain.query);
    } else {
      renderTable();
    }
    showToast('รีเฟรชคลังเสียง TONE3000 แล้ว');
  });

  $('rig-search-input')?.addEventListener('input', (e) => {
    clearTimeout(t3kMain.timer);
    const val = (e.target.value || '').trim();
    state.query = val;
    t3kMain.timer = setTimeout(() => {
      if (t3kMain.liveMode) {
        searchT3KLive(val);
      } else {
        renderTable();
      }
    }, 220);
  });

  $('btn-t3k-cta')?.addEventListener('click', openT3K);
  $('btn-t3k-open')?.addEventListener('click', openT3K);

  $('bypassToggle')?.addEventListener('click', () => toggleBlock(state.block));

  $('btn-scene-clean')?.addEventListener('click', () => applyQuickScene('clean'));
  $('btn-scene-rhythm')?.addEventListener('click', () => applyQuickScene('rhythm'));
  $('btn-scene-lead')?.addEventListener('click', () => applyQuickScene('lead'));

  $('btn-ab-toggle')?.addEventListener('click', handleAbClick);

  $('btn-midi-modal')?.addEventListener('click', openMidiModal);
  $('btn-midi-open')?.addEventListener('click', openMidiModal);
  $('btn-close-midi')?.addEventListener('click', closeMidiModal);
  $('btn-close-midi-btn')?.addEventListener('click', closeMidiModal);
  $('modal-midi')?.addEventListener('click', (e) => {
    if (e.target.id === 'modal-midi') closeMidiModal();
  });
  $('midiMappingsBody')?.addEventListener('click', handleMidiBodyClick);

  const toggleExplorer = () => {
    const main = document.querySelector('.app > .main');
    const btn = $('btn-toggle-explorer');
    if (!main) return;
    const isVis = main.classList.toggle('explorer-visible');
    if (btn) btn.classList.toggle('active', isVis);
    if (isVis && t3kMain.liveMode) {
      searchT3KLive(t3kMain.query);
    }
  };
  $('btn-toggle-explorer')?.addEventListener('click', toggleExplorer);
  $('btn-close-explorer')?.addEventListener('click', toggleExplorer);
  $('curPresetBox')?.addEventListener('click', toggleExplorer);
  $('btn-import-preset-banner')?.addEventListener('click', () => {
    $('universal-file-input')?.click();
  });
  $('btn-toggle-routing')?.addEventListener('click', () => {
    const r = $('routingContainer');
    const b = $('btn-toggle-routing');
    if (!r) return;
    const exp = r.classList.toggle('expanded');
    r.classList.toggle('collapsed', !exp);
    if (b) b.textContent = exp ? '🎛️ Routing & Morph ▴' : '🎛️ Routing & Morph ▾';
  });

  const chain = $('chain');
  if (chain) {
    chain.addEventListener('click', (e) => {
      const nudgeLeft = e.target.closest('.cb-nudge-left');
      if (nudgeLeft) {
        e.stopPropagation();
        reorderBlock(nudgeLeft.dataset.nudgeLeft, -1);
        return;
      }
      const nudgeRight = e.target.closest('.cb-nudge-right');
      if (nudgeRight) {
        e.stopPropagation();
        reorderBlock(nudgeRight.dataset.nudgeRight, 1);
        return;
      }
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
    else if (btn.dataset.action === 'activate-24bit-44k') {
      api('/api/audio/24bit-44k', { method: 'POST', body: { sample_rate: 44100, bit_depth: 24, touch_sensitivity: 0.88 } })
        .then((res) => {
          localStorage.setItem('tone.sampleRate', '44100');
          if (res?.state) applyServerState(res.state, { forceRender: true });
          showToast('เปิดใช้งาน 24-Bit / 44.1 kHz Studio Natural Dynamics แล้ว');
        })
        .catch((err) => showToast(err.message, true));
    }
    else if (btn.dataset.action === 'load-ozzy-neural') {
      Promise.all([
        api('/api/ai-tone/match', { method: 'POST', body: { query: 'ozzy_neural_24bit' } }),
        api('/api/audio/24bit-44k', { method: 'POST', body: { sample_rate: 44100, bit_depth: 24, touch_sensitivity: 0.92, ozzy_doubler: true } }),
      ]).then(([matchRes, srRes]) => {
        localStorage.setItem('tone.sampleRate', '44100');
        const st = srRes?.state || matchRes?.state;
        if (st) applyServerState(st, { forceRender: true });
        renderChain(); renderPanel();
        showToast('โหลดโทน โอไซด์ × นูลอ 24-Bit / 44.1 kHz + NAM A2 + Studio IR แล้ว!');
      }).catch((err) => showToast(err.message, true));
    }
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
      closeMidiModal();
      const main = document.querySelector('.app > .main');
      if (main && main.classList.contains('explorer-visible')) {
        main.classList.remove('explorer-visible');
        $('btn-toggle-explorer')?.classList.remove('active');
      }
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
  initCortex();
  initMorphAndParallel();
  renderLib();
  renderTable();
  renderDetails(null);
  renderChain();
  renderPanel();

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
    try {
      const ab = await api('/api/ab/state');
      updateAbUi(ab);
    } catch (_) {}
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

  // Real-time TONE3000 main catalog initialization
  searchT3KLive('');

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

// =========================================================================
// Real-time TONE3000 Main Search & Live Preset Controller
// =========================================================================
const t3kMain = {
  liveMode: true,
  kind: 'trending',
  gear: '',
  query: '',
  timer: null,
  tones: [],
};

async function searchT3KLive(query = '') {
  t3kMain.query = (query || '').trim();
  const grid = $('t3kMainGrid');
  const localTable = $('localPresetsTable');
  const count = $('rowCount');

  if (!t3kMain.liveMode) {
    if (grid) grid.style.display = 'none';
    if (localTable) localTable.classList.remove('hidden');
    renderTable();
    return;
  }

  if (localTable) localTable.classList.add('hidden');
  if (grid) {
    grid.style.display = 'grid';
    grid.innerHTML = '<div class="t3k-empty" style="grid-column: 1 / -1; padding: 22px; text-align: center; color: var(--muted);"><span class="t3k-spinner"></span> กำลังค้นหาคลังเสียง TONE3000 แบบเรียลไทม์…</div>';
  }

  const params = new URLSearchParams();
  if (t3kMain.query) {
    params.set('kind', 'search');
    params.set('query', t3kMain.query);
  } else {
    params.set('kind', t3kMain.kind || 'trending');
  }
  if (t3kMain.gear) params.set('gear', t3kMain.gear);
  params.set('page', '1');

  try {
    const data = await t3kApi('/api/t3k/tones?' + params.toString());
    t3kMain.tones = data.data || [];
    renderT3KMainGrid(t3kMain.tones);
    if (count) {
      count.innerHTML = `<span class="t3k-live-search-status"><span class="t3k-live-dot"></span> TONE3000 (${data.total || t3kMain.tones.length} เสียง)</span>`;
    }
  } catch (err) {
    if (grid) {
      grid.innerHTML = `<div class="t3k-empty" style="grid-column: 1 / -1; padding: 20px; text-align: center; color: var(--hot-ink);">ค้นหา TONE3000 ไม่สำเร็จ: ${esc(err.message)}</div>`;
    }
  }
}

function renderT3KMainGrid(tones) {
  const grid = $('t3kMainGrid');
  if (!grid) return;

  if (!tones || !tones.length) {
    grid.innerHTML = '<div class="t3k-empty" style="grid-column: 1 / -1; padding: 28px; text-align: center; color: var(--muted);">ไม่พบเสียงที่ตรงกับคำค้นหาใน TONE3000<br><small style="color:var(--faint);">ลองเปลี่ยนคำค้น เช่น Marshall, Clean, Mesa, Overdrive</small></div>';
    return;
  }

  grid.innerHTML = tones.map((tone) => {
    const image = t3kSafeUrl((tone.images || [])[0]);
    const creator = (tone.user && (tone.user.display_name || tone.user.username)) || 'TONE3000';
    const gear = tone.gear || 'amp';
    const isA2 = String(tone.architecture || tone.architecture_version || '').includes('2') || true;
    return `
      <div class="t3k-grid-item" data-tone-id="${esc(tone.id)}">
        <div class="t3k-gi-thumb">
          ${image
            ? `<img src="${esc(image)}" alt="" loading="lazy" onerror="this.remove()">`
            : '<span class="t3k-gi-thumb-fallback">T3K</span>'}
        </div>
        <div class="t3k-gi-info">
          <div class="t3k-gi-title" title="${esc(tone.title)}">${esc(tone.title)}</div>
          <div class="t3k-gi-author">by @${esc(creator)}</div>
          <div class="t3k-gi-badges">
            <span class="t3k-gi-badge t3k-a2">${isA2 ? 'NAM A2' : 'NAM A1'}</span>
            <span class="t3k-gi-badge t3k-gear">${esc(t3kGearLabel(gear))}</span>
            ${tone.downloads_count ? `<span class="t3k-gi-badge">↓ ${t3kNumber(tone.downloads_count)}</span>` : ''}
          </div>
        </div>
        <div class="t3k-gi-action">
          <button type="button" class="t3k-gi-load-btn" data-load-tone="${esc(tone.id)}" title="ดาวน์โหลดและโหลดเข้า NAM AMP ทันที">
            ⚡ โหลด
          </button>
        </div>
      </div>
    `;
  }).join('');

  grid.querySelectorAll('[data-load-tone]').forEach((btn) => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const toneId = Number(btn.dataset.loadTone);
      const tone = tones.find((t) => t.id === toneId);
      btn.classList.add('loading');
      btn.textContent = 'กำลังโหลด…';
      try {
        const data = await t3kApi('/api/t3k/load', {
          method: 'POST',
          body: { tone_id: toneId },
        });
        btn.classList.remove('loading');
        btn.classList.add('loaded');
        btn.textContent = '✓ โหลดแล้ว';
        if (data.load) applyT3KLoad(data.load, true);
        if (data.state) applyServerState(data.state, { forceRender: true });
        showToast(`⚡ โหลด "${tone ? tone.title : 'TONE3000'}" เข้า NAM AMP สำเร็จ!`);
        setTimeout(() => {
          btn.classList.remove('loaded');
          btn.textContent = '⚡ โหลด';
        }, 2500);
      } catch (err) {
        btn.classList.remove('loading');
        btn.textContent = '⚡ โหลด';
        showToast(`โหลดเสียงไม่สำเร็จ: ${err.message}`, true);
      }
    });
  });

  grid.querySelectorAll('.t3k-grid-item').forEach((item) => {
    item.addEventListener('click', () => {
      grid.querySelectorAll('.t3k-grid-item').forEach((i) => i.classList.remove('active'));
      item.classList.add('active');
      const toneId = item.dataset.toneId;
      openT3KDetail(toneId);
    });
  });
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
  let html = `<button class="t3k-page-btn" data-page="${page - 1}" ${page <= 1 ? 'disabled' : ''}><svg width=\"12\" height=\"12\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M15 5l-7 7 7 7\"/></svg></button>`;
  for (let p = first; p <= last; p++) {
    html += `<button class="t3k-page-btn ${p === page ? 'active' : ''}" data-page="${p}">${p}</button>`;
  }
  html += `<button class="t3k-page-btn" data-page="${page + 1}" ${page >= total ? 'disabled' : ''}><svg width=\"12\" height=\"12\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M9 5l7 7-7 7\"/></svg></button>`;
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
            โหลดเข้า NAM AMP
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
    if (btn) { btn.disabled = false; btn.textContent = 'โหลดเข้า NAM AMP'; }
  }
}

// Reflect a loaded tone in the chain block, header and NAM status badge.
function applyT3KLoad(load, refreshState) {
  if (!load) return;
  state.t3kLoaded = load;
  state.irPreview = null;
  api('/api/cab/ir-preview').then((preview) => {
    state.irPreview = preview;
    if (state.selectedType === 't3k-live' || state.selectedType === 't3k') {
      const current = state.selectedKey ? findItemByKey(state.selectedKey) : {
        type: 't3k-live', id: 't3k-live', name: load.title || 'TONE3000 Tone',
        category: t3kGearLabel(load.gear), author: load.creator || 'TONE3000', raw: load,
      };
      if (current) renderDetails(current);
    }
  }).catch(() => {});
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


// ===================================================================
// NEURAL DSP QUAD CORTEX — SCENE ARCHITECTURE & GIG VIEW
// ===================================================================

let cortexPresetsList = [];

async function initCortex() {
  try {
    const res = await api('/api/cortex/presets');
    if (res && res.presets) {
      cortexPresetsList = res.presets;
      populateCortexPresetSelect(res.presets);
    }
  } catch (err) {
    console.warn('Failed loading Cortex presets:', err);
  }

  $('cortexPresetSelect')?.addEventListener('change', async (e) => {
    const presetId = e.target.value;
    if (!presetId) return;
    try {
      const data = await api('/api/cortex/preset/load', {
        method: 'POST',
        body: { id: presetId }
      });
      if (data.state) applyServerState(data.state, { forceRender: true });
      showToast(`Loaded Cortex preset: ${data.cortex?.preset_name || presetId}`);
    } catch (err) {
      showToast('Error loading Cortex preset: ' + err.message, true);
    }
  });

  $('btn-gig-view')?.addEventListener('click', openGigView);
  $('btn-gig-close')?.addEventListener('click', closeGigView);
  $('btn-gig-tuner')?.addEventListener('click', toggleGigTuner);
  $('btn-gig-tuner-off')?.addEventListener('click', toggleGigTuner);

  // Global Keyboard shortcuts: keys 1-8 or A-H to switch scenes, Esc to close Gig View
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    // In Gig View reserve 1–8/A–H for scenes. The editor uses arrows to
    // navigate presets and F to toggle the selected preset's favourite.
    if (state.gigViewOpen) {
      if (e.key === 'Escape') {
        closeGigView();
        return;
      }
    } else {
      if (e.key === 'ArrowLeft') { e.preventDefault(); stepPreset(); return; }
      if (e.key === 'ArrowRight') { e.preventDefault(); stepPresetNext(); return; }
      if (e.key.toLowerCase() === 'f') {
        const item = state.selectedKey ? findItemByKey(state.selectedKey) : null;
        if (item) { e.preventDefault(); toggleFavorite(item); }
        return;
      }
      return;
    }
    // Number keys 1-8
    const num = parseInt(e.key, 10);
    if (!isNaN(num) && num >= 1 && num <= 8) {
      selectCortexScene(num - 1);
      return;
    }
    // Letters a-h or A-H
    const keyLower = e.key.toLowerCase();
    if (keyLower >= 'a' && keyLower <= 'h' && keyLower.length === 1) {
      const idx = keyLower.charCodeAt(0) - 97;
      selectCortexScene(idx);
    }
  });
}

function populateCortexPresetSelect(presets) {
  const sel = $('cortexPresetSelect');
  if (!sel) return;
  sel.innerHTML = '<option value="">-- Cortex Presets --</option>' +
    presets.map(p => `<option value="${esc(p.id)}">${esc(p.name)} (${esc(p.category || 'Multi-Scene')})</option>`).join('');
}

// Scene buttons are rebuilt only when labels/colours change; a selection change
// just moves the .active class, so a click is never swallowed by a re-render.
const sceneStructSig = (c) =>
  JSON.stringify([c.preset_name, (c.scenes || []).map((s) => [s.index, s.label])]);

function syncActiveClass(container, selector, attr, activeIdx) {
  container.querySelectorAll(selector).forEach((el) => {
    el.classList.toggle('active', parseInt(el.dataset[attr], 10) === activeIdx);
  });
}

function renderCortexScenes(cortex) {
  if (!cortex || !cortex.scenes) return;
  const container = $('cortexScenesContainer');
  const nameEl = $('cortexPresetName');
  if (nameEl) nameEl.textContent = cortex.preset_name || 'Cortex Multi-Scene';

  if (!container) return;
  const activeIdx = cortex.active_scene_index ?? 0;
  const sig = sceneStructSig(cortex);

  if (container.dataset.sig !== sig) {
    container.dataset.sig = sig;
    container.innerHTML = cortex.scenes.map(sc => `
      <button class="csb-btn"
              data-scene-idx="${sc.index}"
              title="Switch to Scene ${sc.badge}: ${esc(sc.label)}">
        <span class="csb-led"></span>
        <span class="csb-badge">${sc.badge}</span>
        <span class="csb-label">${esc(sc.label)}</span>
      </button>`).join('');
  }
  if (!container.dataset.bound) {
    container.dataset.bound = '1';
    container.addEventListener('click', (e) => {
      const btn = e.target.closest('.csb-btn');
      if (btn) selectCortexScene(parseInt(btn.dataset.sceneIdx, 10));
    });
  }
  syncActiveClass(container, '.csb-btn', 'sceneIdx', activeIdx);
}

async function selectCortexScene(idx) {
  const prev = state.cortex;
  state.pendingScene = idx;
  if (prev && prev.scenes) {
    state.cortex = { ...prev, active_scene_index: idx };
    renderCortexScenes(state.cortex);
    updateGigView(state.cortex);
  }
  try {
    const data = await api('/api/cortex/scene/select', {
      method: 'POST',
      body: { index: idx }
    });
    if (data.state) {
      applyServerState({ ...data.state, cortex: data.cortex }, { forceRender: true });
    }
    const sc = data.active_scene;
    showToast(`Scene ${sc.badge} activated: ${sc.label}`);
  } catch (err) {
    if (state.pendingScene === idx && prev && prev.scenes) {
      state.cortex = prev;
      renderCortexScenes(prev);
      updateGigView(prev);
    }
    showToast('Failed switching scene: ' + err.message, true);
  } finally {
    if (state.pendingScene === idx) state.pendingScene = null;
  }
}

function openGigView() {
  state.gigViewOpen = true;
  const modal = $('modal-gig-view');
  if (modal) modal.classList.remove('hidden');
  renderGigFootswitches();
  updateGigTuner(state.lastServer);
}

function closeGigView() {
  state.gigViewOpen = false;
  const modal = $('modal-gig-view');
  if (modal) modal.classList.add('hidden');
}

function renderGigFootswitches() {
  const container = $('gigFootswitches');
  if (!container || !state.cortex || !state.cortex.scenes) return;

  const scenes = state.cortex.scenes;
  const activeIdx = state.cortex.active_scene_index ?? 0;

  if ($('gigPresetTitle')) $('gigPresetTitle').textContent = state.cortex.preset_name || 'Cortex Preset';
  const activeSc = scenes[activeIdx];
  if ($('gigActiveSceneBadge') && activeSc) {
    $('gigActiveSceneBadge').textContent = `SCENE ${activeSc.badge} · ${activeSc.label}`;
  }

  const sig = sceneStructSig(state.cortex);
  if (container.dataset.sig !== sig) {
    container.dataset.sig = sig;
    container.innerHTML = scenes.map(sc => `
      <div class="gig-fs"
           data-fs-idx="${sc.index}">
        <div class="gig-fs-top">
          <span class="gig-fs-badge">${sc.badge}</span>
          <div class="gig-fs-ring"></div>
        </div>
        <div class="gig-fs-label">${esc(sc.label)}</div>
      </div>`).join('');
  }
  if (!container.dataset.bound) {
    container.dataset.bound = '1';
    container.addEventListener('click', (e) => {
      const el = e.target.closest('.gig-fs');
      if (el) selectCortexScene(parseInt(el.dataset.fsIdx, 10));
    });
  }
  syncActiveClass(container, '.gig-fs', 'fsIdx', activeIdx);
}

function updateGigView(cortex, server) {
  if (!state.gigViewOpen) return;
  renderGigFootswitches();
}

// Gig View tuner: big centre read-out shown while the engine tuner is active.
function updateGigTuner(server) {
  const tuner = server ? server.tuner : null;
  const on = !!tuner;
  const cents = Number(tuner?.cents || 0);
  const hasNote = on && !!tuner.note && tuner.note !== '--';
  const inTune = hasNote && Math.abs(cents) <= 5;
  const set = (id, text) => { const el = $(id); if (el) el.textContent = text; };

  $('gigTunerPanel')?.classList.toggle('hidden', !on);
  $('btn-gig-tuner')?.classList.toggle('active', on);
  set('gigTunerNote', hasNote ? tuner.note : '--');
  set('gigTunerStatus', !on ? 'TUNER OFF' : (hasNote ? `${cents > 0 ? '+' : ''}${cents}c` : 'PLAY STRING'));
  set('gigTunerBigNote', hasNote ? tuner.note : '--');
  set('gigTunerBigFreq', on ? Number(tuner.freq || 0).toFixed(1) + ' Hz' : '0.0 Hz');
  set('gigTunerBigStatus', !hasNote ? 'PLAY STRING' : (inTune ? 'IN TUNE' : (cents > 0 ? 'SHARP' : 'FLAT')));
  const needle = $('gigTunerNeedle');
  if (needle) needle.style.left = clamp(50 + cents, 0, 100) + '%';
  $('gigTunerPanel')?.classList.toggle('in-tune', inTune);
}

async function toggleGigTuner() {
  await toggleTuner();
  updateGigTuner(state.tunerActive ? { tuner: { note: '--', cents: 0, freq: 0 } } : null);
}

// ===================================================================
// 3D CAB, STUDIO EQ, MORPHING & PARALLEL ROUTING HELPERS
// ===================================================================

// Trailing-edge throttle: fires at most once per `ms`, and always delivers the
// last value so a drag ends on the exact position the user released at.
function throttle(fn, ms) {
  let last = 0;
  let timer = null;
  let pending = null;
  return (...args) => {
    pending = args;
    const wait = ms - (Date.now() - last);
    if (wait <= 0) {
      if (timer) { clearTimeout(timer); timer = null; }
      last = Date.now();
      fn(...args);
    } else if (!timer) {
      timer = setTimeout(() => {
        timer = null;
        last = Date.now();
        fn(...pending);
      }, wait);
    }
  };
}

function postParam(section, param, value) {
  return api('/api/parameter', { method: 'POST', body: { section, param, value } }).catch(() => null);
}

function attachCabMicDrag() {
  const stage = $('cabSpeakerStage');
  const mic = $('draggableMic');
  if (!stage || !mic) return;

  const sendMic = throttle((center, dist) => {
    postParam('cab', 'center', center);
    postParam('cab', 'distance', dist);
  }, 40);

  function updatePos(e) {
    const rect = stage.getBoundingClientRect();
    const x = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
    const y = Math.max(0, Math.min(rect.height, e.clientY - rect.top));
    const center = Math.round((x / rect.width) * 100);
    const dist = Math.round((y / rect.height) * 100);
    mic.style.left = center + '%';
    mic.style.top = dist + '%';
    sendMic(center, dist);
  }

  let dragging = false;
  stage.addEventListener('pointerdown', (e) => {
    dragging = true;
    stage.setPointerCapture(e.pointerId);
    updatePos(e);
  });
  stage.addEventListener('pointermove', (e) => {
    if (dragging) updatePos(e);
  });
  stage.addEventListener('pointerup', () => { dragging = false; });
  stage.addEventListener('pointercancel', () => { dragging = false; });

  $('cabTubeSelect')?.addEventListener('change', (e) => postParam('cab', 'tube', e.target.value));
  $('cabMicSelect')?.addEventListener('change', (e) => postParam('cab', 'mic', e.target.value));
}

function drawEqCurve(curve) {
  const path = $('eqCurvePath');
  if (!path || !curve || !curve.length) return;
  const w = 300;
  const h = 120;
  const midY = 60;
  const maxDb = 16.0;

  let d = `M 0 ${midY} `;
  curve.forEach((pt, i) => {
    const x = (i / (curve.length - 1)) * w;
    const y = midY - (pt.db / maxDb) * (midY - 10);
    const clampedY = Math.max(5, Math.min(h - 5, y));
    d += `L ${x.toFixed(1)} ${clampedY.toFixed(1)} `;
  });
  d += `L ${w} ${midY} Z`;
  path.setAttribute('d', d);
  const svg = $('eqCurveSvg');
  if (svg) {
    svg.querySelectorAll('.eq-node-g').forEach((n) => n.remove());
    const bands = state.live?.eq?.bands || [20, 0, 0, 0, 0, 20000];
    const nodeColors = ['#f59e0b', '#38bdf8', '#10b981', '#a855f7'];
    const nodeXs = [65, 130, 195, 255];
    nodeXs.forEach((nx, idx) => {
      const bandIdx = idx + 1;
      const dbVal = clamp(Number(bands[bandIdx] || 0), -16, 16);
      const ny = clamp(midY - (dbVal / maxDb) * (midY - 10), 8, h - 8);
      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.setAttribute('class', 'eq-node-g');
      g.style.cursor = 'ns-resize';
      g.innerHTML = `<circle cx="${nx}" cy="${ny.toFixed(1)}" r="8" fill="${nodeColors[idx]}" fill-opacity="0.25"/><circle cx="${nx}" cy="${ny.toFixed(1)}" r="4.5" fill="${nodeColors[idx]}" stroke="#ffffff" stroke-width="1.2"/>`;
      svg.appendChild(g);
    });
  }
}

function attachEqEvents() {
  document.querySelectorAll('#eqModelBtns button').forEach(btn => {
    btn.addEventListener('click', () => {
      const model = parseInt(btn.dataset.model, 10);
      api('/api/parameter', { method: 'POST', body: { section: 'eq', param: 'model_id', value: model } })
        .then(res => { if (res && res.state) applyServerState(res.state, { forceRender: true }); })
        .catch((err) => showToast('เปลี่ยนโมเดล EQ ไม่สำเร็จ: ' + err.message, true));
    });
  });
}

function initMorphAndParallel() {
  const slider = $('morphSlider');
  const readout = $('morphReadout');
  function updateMorphUI(morph) {
    if (!morph) return;
    if (slider && Number.isFinite(Number(morph.morph_pos))) {
      slider.value = String(Math.round(Number(morph.morph_pos) * 100));
    }
    if (readout) {
      const percent = slider ? slider.value : Math.round(Number(morph.morph_pos) * 100);
      const pos = Number(percent) / 100;
      readout.textContent = `${percent}% (${pos < 0.5 ? 'A' : 'B'})`;
      if (slider) slider.setAttribute('aria-valuetext', `${percent} percent, Slot ${pos < 0.5 ? 'A' : 'B'}`);
    }
    ['A', 'B'].forEach((slot) => {
      const badge = $(`morphSlot${slot}Btn`);
      const values = morph[`slot_${slot.toLowerCase()}`];
      const isCaptured = morph.captured?.[slot] === true;
      if (badge && values) {
        badge.classList.toggle('captured', isCaptured);
        badge.setAttribute('aria-label', isCaptured
          ? `Replace saved Morph Slot ${slot}`
          : `Capture current rig into Morph Slot ${slot}`);
        badge.title = isCaptured
          ? `Saved · Gain ${Number(values.amp_gain).toFixed(2)} · Master ${Number(values.amp_master).toFixed(2)}`
          : `Empty · click to capture current rig into Slot ${slot}`;
        badge.textContent = isCaptured ? `SAVED ${slot}` : `SAVE ${slot}`;
      }
    });
  };
  let morphReady = false;
  const morphReadyPromise = api('/api/morph').then((morph) => {
    updateMorphUI(morph);
    morphReady = true;
    return morph;
  }).catch((err) => {
    showToast('โหลดสถานะ Morph ไม่สำเร็จ: ' + err.message, true);
    return null;
  });
  if (slider) {
    let requestSequence = 0;
    let pendingPosition = null;
    let sending = false;
    const flushMorph = async () => {
      if (sending || pendingPosition === null) return;
      if (!morphReady) {
        await morphReadyPromise;
        if (!morphReady) return;
      }
      sending = true;
      const position = pendingPosition;
      pendingPosition = null;
      const sequence = ++requestSequence;
      try {
        const res = await api('/api/morph/set', { method: 'POST', body: { pos: position } });
        if (sequence === requestSequence && pendingPosition === null) updateMorphUI(res.morph);
      } catch (err) {
        if (sequence === requestSequence) showToast('Morph failed: ' + err.message, true);
      } finally {
        sending = false;
        if (pendingPosition !== null) flushMorph();
      }
    };
    slider.addEventListener('input', (e) => {
      const val = Number(e.target.value) / 100.0;
      if (readout) readout.textContent = `${e.target.value}% (${val < 0.5 ? 'A' : 'B'})`;
      slider.setAttribute('aria-valuetext', `${e.target.value} percent, Slot ${val < 0.5 ? 'A' : 'B'}`);
      pendingPosition = val;
      flushMorph();
    });
  }

  ['A', 'B'].forEach((slot) => {
    $(`morphSlot${slot}Btn`)?.addEventListener('click', async () => {
      try {
        const morph = await morphReadyPromise;
        if (!morphReady) throw new Error('Morph state is unavailable');
        if (morph.captured?.[slot] && !window.confirm(`Replace saved Morph Slot ${slot}?`)) return;
        const res = await api('/api/morph/capture', { method: 'POST', body: { slot } });
        updateMorphUI(res.morph);
        showToast(`💾 Saved current rig into Morph Slot ${slot} (${slot === 'A' ? 'Heel' : 'Toe'})`);
      } catch (err) {
        showToast(`Could not capture Morph Slot ${slot}: ${err.message}`, true);
      }
    });
    $(`morphSlot${slot}Clear`)?.addEventListener('click', async () => {
      try {
        const morph = await morphReadyPromise;
        if (!morphReady) throw new Error('Morph state is unavailable');
        if (!morph.captured?.[slot]) return;
        if (!window.confirm(`Clear saved Morph Slot ${slot}? This will not change the live sound.`)) return;
        const res = await api(`/api/morph/${slot}`, { method: 'DELETE' });
        updateMorphUI(res.morph);
        showToast(`Cleared Morph Slot ${slot}`);
      } catch (err) {
        showToast(`Could not clear Morph Slot ${slot}: ${err.message}`, true);
      }
    });
  });

  const pBtn = $('btn-parallel-toggle');
  if (pBtn) {
    pBtn.addEventListener('click', () => {
      const active = !pBtn.classList.contains('active');
      pBtn.classList.toggle('active', active);
      postParam('parallel', 'enabled', active);
      showToast(`Parallel Dual Path: ${active ? 'ENABLED' : 'DISABLED'}`);
    });
  }

  const pSlider = $('parallelBlendSlider');
  const pReadout = $('parallelBlendReadout');
  if (pSlider) {
    const sendBlend = throttle((val) => postParam('parallel', 'blend', val), 40);
    pSlider.addEventListener('input', (e) => {
      const val = Number(e.target.value) / 100.0;
      if (pReadout) pReadout.textContent = `${e.target.value}%`;
      sendBlend(val);
    });
  }
}


window.addEventListener('DOMContentLoaded', boot);


// ===================================================================
// PREMIUM DARK UI VOICING, SLIDER SYNC & HYBRID C++ WEBSOCKET BRIDGE
// ===================================================================

function syncSliderProgressCss(slider) {
  if (!slider) return;
  slider.style.setProperty('--attr-min', slider.min || '0');
  slider.style.setProperty('--attr-max', slider.max || '100');
  slider.style.setProperty('--control-value', slider.value || '0');
}

function updateDynamicVoicingAccent() {
  const ampGain = Number(state.live?.amp?.gain ?? 0.65);
  const ampModel = String(state.live?.amp?.model || '').toLowerCase();
  const driveOn = !!state.live?.screamer?.enabled;
  let voicing = 'vintage';
  if (ampGain < 0.35 && !driveOn) {
    voicing = 'clean';
  } else if (ampGain >= 0.72 || /5150|rect|metal|uberschall/i.test(ampModel)) {
    voicing = 'highgain';
  }
  if (document.body && document.body.dataset.voicing !== voicing) {
    document.body.dataset.voicing = voicing;
  }
}

const cppBridge = {
  ws: null,
  connected: false,
  reqSeq: 1,
  connect() {
    const urlParams = new URLSearchParams(window.location.search);
    const tokenFromUrl = urlParams.get('cpp_token');
    const portFromUrl = urlParams.get('cpp_port');
    if (tokenFromUrl) localStorage.setItem('tone.cppToken', tokenFromUrl);
    if (portFromUrl) localStorage.setItem('tone.cppPort', portFromUrl);
    const token = tokenFromUrl || localStorage.getItem('tone.cppToken') || '';
    const port = portFromUrl || localStorage.getItem('tone.cppPort') || '8765';
    if (!token) return;
    try {
      const ws = new WebSocket(`ws://127.0.0.1:${port}/ws?token=${encodeURIComponent(token)}`);
      ws.addEventListener('open', () => {
        cppBridge.ws = ws;
        cppBridge.connected = true;
        showToast('⚡ Native C++ ASIO Engine เชื่อมต่อสำเร็จ (17.5 ms UX1)', false);
        ws.send(JSON.stringify({ type: 'get_state', req_id: String(cppBridge.reqSeq++) }));
      });
      ws.addEventListener('close', () => {
        cppBridge.ws = null;
        cppBridge.connected = false;
      });
      ws.addEventListener('error', () => {
        cppBridge.ws = null;
        cppBridge.connected = false;
      });
    } catch (e) {
      cppBridge.connected = false;
    }
  },
  sendParamNormalized(block, param, normalized) {
    if (!cppBridge.connected || !cppBridge.ws) return;
    try {
      cppBridge.ws.send(JSON.stringify({
        type: 'set_param',
        req_id: String(cppBridge.reqSeq++),
        block,
        param,
        normalized: Math.max(0, Math.min(1, Number(normalized)))
      }));
    } catch (e) { /* ignore */ }
  },
  sendParamValue(block, param, value) {
    if (!cppBridge.connected || !cppBridge.ws) return;
    try {
      cppBridge.ws.send(JSON.stringify({
        type: 'set_param',
        req_id: String(cppBridge.reqSeq++),
        block,
        param,
        value: Number(value)
      }));
    } catch (e) { /* ignore */ }
  }
};

window.addEventListener('DOMContentLoaded', () => {
  ['morphSlider', 'parallelBlendSlider'].forEach((id) => {
    const el = $(id);
    if (el) {
      syncSliderProgressCss(el);
      el.addEventListener('input', () => syncSliderProgressCss(el));
    }
  });
  updateDynamicVoicingAccent();
  cppBridge.connect();

  // MOOER GE150 / Quad Cortex Tap Tempo BPM Sync
  const tapTimes = [];
  const tapBtn = $('btn-tap-tempo');
  if (tapBtn) {
    tapBtn.addEventListener('click', async () => {
      const now = performance.now();
      if (tapTimes.length && now - tapTimes[tapTimes.length - 1] > 2200) tapTimes.length = 0;
      tapTimes.push(now);
      if (tapTimes.length > 5) tapTimes.shift();
      if (tapTimes.length >= 2) {
        let sum = 0;
        for (let i = 1; i < tapTimes.length; i++) sum += (tapTimes[i] - tapTimes[i - 1]);
        const avgMs = sum / (tapTimes.length - 1);
        const bpm = Math.max(40, Math.min(260, Math.round(60000 / avgMs)));
        tapBtn.textContent = `TAP ${bpm} BPM`;
        try {
          const res = await api('/api/tempo/sync', { method: 'POST', body: { bpm, subdivision: '1/4' } });
          if (res.state) applyServerState(res.state);
          showToast(`⏱ Tap Tempo: ${bpm} BPM (Delay = ${Math.round(res.delay_time_sec * 1000)} ms)`);
        } catch (err) { /* ignore */ }
      } else {
        showToast('เคาะปุ่ม TAP อีกครั้งเพื่อคำนวณจังหวะ BPM');
      }
    });
  }

  // Kemper Auto-Morph A<->B Generator
  const autoMorphBtn = $('btn-auto-morph');
  if (autoMorphBtn) {
    autoMorphBtn.addEventListener('click', async () => {
      try {
        const res = await api('/api/morph/auto', { method: 'POST', body: {} });
        if (res.morph) {
          const slider = $('morphSlider');
          if (slider) { slider.value = '0'; syncSliderProgressCss(slider); }
          if ($('morphReadout')) $('morphReadout').textContent = '0% (A)';
          if ($('morphSlotABtn')) { $('morphSlotABtn').classList.add('captured'); $('morphSlotABtn').textContent = 'SAVED A'; }
          if ($('morphSlotBBtn')) { $('morphSlotBBtn').classList.add('captured'); $('morphSlotBBtn').textContent = 'SAVED B'; }
        }
        showToast('⚡ สร้างคู่ Kemper Morph A (Rhythm) ↔ B (Solo Lead) อัตโนมัติแล้ว!');
      } catch (err) {
        showToast('Auto-Morph ไม่สำเร็จ: ' + err.message, true);
      }
    });
  }

  // Artist preset search (keyword lookup, see engine/ai_tone_matcher.py)
  let liveBpm = 120;
  async function runAiToneMatch(queryText) {
    if (!queryText) return;
    try {
      const res = await api('/api/ai-tone/match', { method: 'POST', body: { query: queryText } });
      if (res.state) applyServerState(res.state, { forceRender: true });
      const prof = res.matched_profile;
      if (prof) {
        liveBpm = prof.bpm || 120;
        if ($('btn-tap-tempo')) $('btn-tap-tempo').textContent = `TAP ${liveBpm} BPM`;
        if ($('curName')) $('curName').textContent = prof.title;
        if ($('curSub')) $('curSub').textContent = prof.brand_dna;
        showToast(`🎸 Artist Preset: ${prof.title} (${prof.summary})`);
      }
    } catch (err) {
      showToast('โหลด Artist Preset ไม่สำเร็จ: ' + err.message, true);
    }
  }
  $('aiToneMatchBtn')?.addEventListener('click', () => runAiToneMatch($('aiToneInput')?.value || 'polyphia'));
  $('aiToneInput')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') runAiToneMatch(e.target.value); });
  document.querySelectorAll('#aiQuickPills [data-ai]').forEach((btn) => {
    btn.addEventListener('click', () => {
      if ($('aiToneInput')) $('aiToneInput').value = btn.textContent;
      runAiToneMatch(btn.dataset.ai);
    });
  });

  // Web Audio API Smart Drum Groove & Metronome Synthesizer
  let audioCtx = null;
  let drumTimer = null;
  let drumStep = 0;
  function triggerDrumStep(style, step) {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const now = audioCtx.currentTime;
    const isKick = style === 'metal' ? (step % 2 === 0 || step === 3 || step === 7) : (step === 0 || step === 4);
    const isSnare = (step === 2 || step === 6);
    if (style === 'metro') {
      const osc = audioCtx.createOscillator();
      const g = audioCtx.createGain();
      osc.frequency.value = step % 4 === 0 ? 1200 : 800;
      g.gain.setValueAtTime(0.15, now);
      g.gain.exponentialRampToValueAtTime(0.001, now + 0.04);
      osc.connect(g); g.connect(audioCtx.destination);
      osc.start(now); osc.stop(now + 0.045);
      return;
    }
    if (isKick) {
      const osc = audioCtx.createOscillator();
      const g = audioCtx.createGain();
      osc.frequency.setValueAtTime(135, now);
      osc.frequency.exponentialRampToValueAtTime(38, now + 0.11);
      g.gain.setValueAtTime(0.35, now);
      g.gain.exponentialRampToValueAtTime(0.001, now + 0.14);
      osc.connect(g); g.connect(audioCtx.destination);
      osc.start(now); osc.stop(now + 0.15);
    }
    if (isSnare) {
      const osc = audioCtx.createOscillator();
      const g = audioCtx.createGain();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(210, now);
      osc.frequency.exponentialRampToValueAtTime(95, now + 0.09);
      g.gain.setValueAtTime(0.22, now);
      g.gain.exponentialRampToValueAtTime(0.001, now + 0.11);
      osc.connect(g); g.connect(audioCtx.destination);
      osc.start(now); osc.stop(now + 0.12);
    }
    // Hi-Hat
    const hatOsc = audioCtx.createOscillator();
    const hatG = audioCtx.createGain();
    hatOsc.type = 'square';
    hatOsc.frequency.setValueAtTime(6400, now);
    hatG.gain.setValueAtTime(0.04, now);
    hatG.gain.exponentialRampToValueAtTime(0.001, now + 0.03);
    hatOsc.connect(hatG); hatG.connect(audioCtx.destination);
    hatOsc.start(now); hatOsc.stop(now + 0.035);
  }

  const drumBtn = $('drumToggleBtn');
  if (drumBtn) {
    drumBtn.addEventListener('click', () => {
      if (drumTimer) {
        clearInterval(drumTimer);
        drumTimer = null;
        drumBtn.classList.remove('active');
        drumBtn.innerHTML = '<span class="p-led"></span>DRUMS OFF';
      } else {
        drumStep = 0;
        drumBtn.classList.add('active');
        drumBtn.innerHTML = '<span class="p-led"></span>DRUMS ON';
        const stepMs = () => Math.max(80, Math.round((60000 / (liveBpm || 120)) / 2));
        const loop = () => {
          const style = $('drumStyleSelect')?.value || 'rock';
          triggerDrumStep(style, drumStep % 8);
          drumStep++;
          drumTimer = setTimeout(loop, stepMs());
        };
        loop();
      }
    });
  }

  // Output spectrum (server FFT of the last 2048 output samples, 24 log bands, -72..0 dBFS)
  // and VU needles driven by the real input/output RMS meters.
  const rta = $('rtaCanvas');
  if (rta) {
    const ctx = rta.getContext('2d');
    const shown = new Array(24).fill(-72);
    let needleIn = -60, needleOut = -60;
    const meterDb = (m) => 20 * Math.log10(Math.max(1e-3, Number(m || 0) / 100));
    const swingFor = (db) => Math.max(-14, Math.min(14, (db + 30) * (14 / 30)));
    function drawRta() {
      const w = rta.width, h = rta.height;
      ctx.clearRect(0, 0, w, h);
      const srv = state.lastServer || {};
      const spec = Array.isArray(srv.spectrum) ? srv.spectrum : null;
      const bw = w / shown.length;
      for (let i = 0; i < shown.length; i++) {
        const target = spec ? Math.max(-72, Number(spec[i] ?? -72)) : -72;
        shown[i] += (target - shown[i]) * (target > shown[i] ? 0.6 : 0.15);  // fast attack, slow fall
        const barH = Math.max(2, ((shown[i] + 72) / 72) * (h - 2));
        ctx.fillStyle = shown[i] > -6 ? '#f43f5e' : (shown[i] > -24 ? '#f59e0b' : '#38bdf8');
        ctx.fillRect(i * bw + 1, h - barH, bw - 1.5, barH);
      }
      needleIn += (meterDb(srv.input_meter) - needleIn) * 0.3;
      needleOut += (meterDb(srv.output_meter) - needleOut) * 0.3;
      const sIn = swingFor(needleIn), sOut = swingFor(needleOut);
      const nIn = $('vuNeedleIn'), nOut = $('vuNeedleOut');
      if (nIn) { nIn.setAttribute('x2', (745 + sIn * 0.9).toFixed(1)); nIn.setAttribute('y2', (20 - Math.abs(sIn) * 0.12).toFixed(1)); }
      if (nOut) { nOut.setAttribute('x2', (857 + sOut * 1.15).toFixed(1)); nOut.setAttribute('y2', (18 - Math.abs(sOut) * 0.12).toFixed(1)); }
      requestAnimationFrame(drawRta);
    }
    requestAnimationFrame(drawRta);
  }

  // PLAY MODE + Tone Filter Chips + Studio Macros + Undo/Redo
  const appRoot = document.querySelector('.app');
  if ($('btn-lib-drawer') && appRoot) {
    $('btn-lib-drawer').addEventListener('click', () => {
      const isPlay = appRoot.classList.toggle('play-mode');
      $('btn-lib-drawer').classList.toggle('active-drawer-btn', isPlay);
    });
  }
  document.querySelectorAll('#presetFilterChips button').forEach((chip) => {
    chip.addEventListener('click', () => {
      document.querySelectorAll('#presetFilterChips button').forEach((c) => c.classList.remove('active'));
      chip.classList.add('active');
      const kind = chip.dataset.t3kKind;
      const gear = chip.dataset.t3kGear;
      if (kind === 'local') {
        t3kMain.liveMode = false;
        searchT3KLive();
      } else {
        t3kMain.liveMode = true;
        if (kind) {
          t3kMain.kind = kind;
          t3kMain.gear = '';
        } else if (gear) {
          t3kMain.gear = gear;
        }
        searchT3KLive(t3kMain.query);
      }
    });
  });
  document.querySelectorAll('#macroStrip [data-macro]').forEach((mbtn) => {
    mbtn.addEventListener('click', async () => {
      const m = mbtn.dataset.macro;
      mbtn.classList.toggle('active');
      if (m === 'tight') {
        await sendParamNow('gate', 'enabled', true);
        await sendParamNow('gate', 'threshold', -48);
        await sendParamNow('screamer', 'enabled', true);
        await sendParamNow('screamer', 'drive', 0.22);
        await sendParamNow('screamer', 'level', 0.78);
        await sendParamNow('amp', 'bass', 0.38);
        showToast('Macro: Tight — เปิด Gate + Boost Screamer + ลด Bass');
      } else if (m === 'bright') {
        await sendParamNow('amp', 'treble', 0.74);
        await sendParamNow('amp', 'presence', 0.76);
        showToast('Macro: Bright — เพิ่ม Treble & Presence');
      } else if (m === 'space') {
        await sendParamNow('delay', 'enabled', true);
        await sendParamNow('delay', 'mix', 0.32);
        await sendParamNow('reverb', 'enabled', true);
        await sendParamNow('reverb', 'mix', 0.34);
        await sendParamNow('reverb', 'decay', 0.68);
        showToast('Macro: Space — เปิด Stereo Delay + Plate Reverb');
      } else if (m === 'lead') {
        const curGain = Number(state.live?.amp?.gain ?? 0.6);
        await sendParamNow('amp', 'gain', Math.min(1.0, curGain + 0.16));
        await sendParamNow('screamer', 'enabled', true);
        await sendParamNow('delay', 'enabled', true);
        showToast('Macro: Lead Boost — เพิ่ม Gain + เปิด Drive & Delay');
      }
      renderChain();
      renderPanel();
    });
  });
  async function performUndo() {
    const stack = window._undoStack || [];
    if (!stack.length) return;
    const item = stack.pop();
    window._redoStack = window._redoStack || [];
    window._redoStack.push(item);
    if ($('btn-undo')) $('btn-undo').disabled = stack.length === 0;
    if ($('btn-redo')) $('btn-redo').disabled = false;
    await sendParamNow(item.section, item.param, item.prev);
    renderChain();
    renderPanel();
    showToast('Undo: ' + item.section + '.' + item.param);
  }
  async function performRedo() {
    const rstack = window._redoStack || [];
    if (!rstack.length) return;
    const item = rstack.pop();
    window._undoStack = window._undoStack || [];
    window._undoStack.push(item);
    if ($('btn-undo')) $('btn-undo').disabled = false;
    if ($('btn-redo')) $('btn-redo').disabled = rstack.length === 0;
    await sendParamNow(item.section, item.param, item.next);
    renderChain();
    renderPanel();
    showToast('Redo: ' + item.section + '.' + item.param);
  }
  $('btn-undo')?.addEventListener('click', performUndo);
  $('btn-redo')?.addEventListener('click', performRedo);
  window.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === 'z') {
      if (document.activeElement && ['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;
      e.preventDefault();
      performUndo();
    } else if ((e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === 'y' || (e.shiftKey && e.key.toLowerCase() === 'z'))) {
      if (document.activeElement && ['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;
      e.preventDefault();
      performRedo();
    }
  });
  const libDrawerBtn = $('btn-lib-drawer');
  const mainLib = document.querySelector('.app > .main');
  if (false && libDrawerBtn && mainLib) {
    libDrawerBtn.addEventListener('click', () => {
      const hidden = mainLib.classList.toggle('collapsed-drawer');
      libDrawerBtn.classList.toggle('active-drawer-btn', !hidden);
      if (!hidden) {
        mainLib.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  }
  const riffBtn = $('riffToggleBtn');
  let riffTimer = null, riffIdx = 0;
  const riffNotes = [82.41, 82.41, 98.0, 110.0, 82.41, 123.47, 110.0, 98.0];
  if (riffBtn) {
    riffBtn.addEventListener('click', () => {
      if (riffTimer) {
        clearTimeout(riffTimer);
        riffTimer = null;
        riffBtn.classList.remove('active');
        riffBtn.innerHTML = '<span class="p-led"></span>🎸 RIFF OFF';
      } else {
        if (!drumCtx) drumCtx = new (window.AudioContext || window.webkitAudioContext)();
        riffBtn.classList.add('active');
        riffBtn.innerHTML = '<span class="p-led"></span>🎸 RIFF ON';
        const playNote = () => {
          const now = drumCtx.currentTime;
          const freq = riffNotes[riffIdx % riffNotes.length];
          riffIdx++;
          const osc = drumCtx.createOscillator(), flt = drumCtx.createBiquadFilter(), g = drumCtx.createGain();
          osc.type = 'sawtooth'; osc.frequency.setValueAtTime(freq, now);
          flt.type = 'bandpass'; flt.frequency.setValueAtTime(950 + Number(state.live?.amp?.gain ?? 0.6) * 1400, now); flt.Q.setValueAtTime(2.4, now);
          g.gain.setValueAtTime(0.14, now); g.gain.exponentialRampToValueAtTime(0.001, now + 0.19);
          osc.connect(flt); flt.connect(g); g.connect(drumCtx.destination);
          osc.start(now); osc.stop(now + 0.21);
          riffTimer = setTimeout(playNote, Math.max(110, Math.round((60000 / (liveBpm || 120)) / 2)));
        };
        playNote();
      }
    });
  }
  if (false) {
    [].forEach(() => {
      if (false) {
      }
    });
  }

  if (false && riffBtn) {
    riffBtn.addEventListener('click', () => {
      if (riffTimer) {
        clearTimeout(riffTimer);
        riffTimer = null;
        riffBtn.classList.remove('active');
        riffBtn.innerHTML = '<span class="p-led"></span>🎸 RIFF OFF';
      } else {
        if (!drumCtx) drumCtx = new (window.AudioContext || window.webkitAudioContext)();
        riffBtn.classList.add('active');
        riffBtn.innerHTML = '<span class="p-led"></span>🎸 RIFF ON';
        const playNote = () => {
          const now = drumCtx.currentTime;
          const freq = riffNotes[riffIdx % riffNotes.length];
          riffIdx++;
          const osc = drumCtx.createOscillator();
          const flt = drumCtx.createBiquadFilter();
          const g = drumCtx.createGain();
          osc.type = 'sawtooth';
          osc.frequency.setValueAtTime(freq, now);
          flt.type = 'bandpass';
          flt.frequency.setValueAtTime(950 + Number(state.live?.amp?.gain ?? 0.6) * 1400, now);
          flt.Q.setValueAtTime(2.4, now);
          g.gain.setValueAtTime(0.14, now);
          g.gain.exponentialRampToValueAtTime(0.001, now + 0.19);
          osc.connect(flt);
          flt.connect(g);
          g.connect(drumCtx.destination);
          osc.start(now);
          osc.stop(now + 0.21);
          riffTimer = setTimeout(playNote, Math.max(110, Math.round((60000 / (liveBpm || 120)) / 2)));
        };
        playNote();
      }
    });
  }
});
