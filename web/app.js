// ====================================================================
// ⚡ กดจนหลอนTone - Guitar Rig & Amp Workstation Engine Frontend
// ====================================================================

let isEngineRunning = false;
let isTunerActive = false;
let pollingInterval = null;
let currentLoadedRigId = null;
let allPresetsCache = [];
let allKemperPacksCache = [];
let allTone3000PresetsCache = [];

// DOM Elements
const btnPower = document.getElementById('btn-power');
const btnTuner = document.getElementById('btn-tuner-toggle');
const tunerDisplay = document.getElementById('tuner-display');
const meterIn = document.getElementById('meter-in');
const meterOut = document.getElementById('meter-out');
const tableBody = document.getElementById('rig-table-body');
const searchInput = document.getElementById('rig-search-input');

// ── 1. ROTARY KNOB CONTROLS ──────────────────────────────────────────
function initKnobs() {
  const knobs = document.querySelectorAll('.knob');
  knobs.forEach(knob => {
    let isDragging = false;
    let startY = 0;
    let startVal = parseFloat(knob.dataset.val || '0.5');
    const min = parseFloat(knob.dataset.min || '0');
    const max = parseFloat(knob.dataset.max || '1');
    const section = knob.dataset.section;
    const param = knob.dataset.param;

    updateKnobAngle(knob, startVal, min, max);

    knob.addEventListener('mousedown', (e) => {
      isDragging = true;
      startY = e.clientY;
      startVal = parseFloat(knob.dataset.val);
      document.body.style.cursor = 'ns-resize';
      e.preventDefault();
    });

    window.addEventListener('mousemove', (e) => {
      if (!isDragging) return;
      const deltaY = startY - e.clientY;
      const range = max - min;
      const step = range / 180;
      let newVal = startVal + deltaY * step;
      newVal = Math.max(min, Math.min(max, newVal));

      knob.dataset.val = newVal;
      updateKnobAngle(knob, newVal, min, max);
      updateKnobLabel(knob, section, param, newVal);
      sendParamUpdate(section, param, newVal);
    });

    window.addEventListener('mouseup', () => {
      if (isDragging) {
        isDragging = false;
        document.body.style.cursor = 'default';
      }
    });
  });
}

function updateKnobAngle(knob, val, min, max) {
  const norm = (val - min) / (max - min);
  const angle = -135 + norm * 270;
  const pointer = knob.querySelector('.knob-pointer');
  if (pointer) {
    pointer.style.transform = `rotate(${angle}deg)`;
  }
}

function updateKnobLabel(knob, section, param, val) {
  let displayVal = val;
  if (param === 'threshold') {
    displayVal = Math.round(val) + ' dB';
  } else if (param === 'time') {
    displayVal = Math.round(val * 1000) + ' ms';
  } else if (param === 'feedback' || param === 'mix' || param === 'decay') {
    displayVal = Math.round(val * 100) + '%';
  } else {
    displayVal = (val * 10).toFixed(1);
  }

  const group = knob.closest('.knob-group');
  if (group) {
    const valSpan = group.querySelector('.knob-val');
    if (valSpan) valSpan.innerText = displayVal;
  }
}

function setKnob(id, val) {
  const k = document.getElementById(id);
  if (k) {
    k.dataset.val = val;
    const min = parseFloat(k.dataset.min);
    const max = parseFloat(k.dataset.max);
    updateKnobAngle(k, val, min, max);
    updateKnobLabel(k, k.dataset.section, k.dataset.param, val);
  }
}

// ── 2. MODULAR SIGNAL CHAIN SWITCHING ────────────────────────────────
function initSignalChain() {
  const modules = [
    { id: 'gate', section: 'gate' },
    { id: 'screamer', section: 'screamer' },
    { id: 'amp', section: 'amp' },
    { id: 'cab', section: 'cab' },
    { id: 'delay', section: 'delay' },
    { id: 'reverb', section: 'reverb' }
  ];

  modules.forEach(m => {
    const modElem = document.getElementById(`cmod-${m.id}`);
    const powBtn = document.getElementById(`cpow-${m.id}`);
    const bigPowBtn = document.getElementById(`btn-module-power-${m.id}`);

    // Click module card to select and switch parameter strip
    if (modElem) {
      modElem.addEventListener('click', (e) => {
        if (e.target.closest('.mod-power-btn')) return; // handled by powBtn
        selectModulePanel(m.id);
      });
    }

    // Module power button on chain
    if (powBtn) {
      powBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        toggleModuleState(m.id, m.section);
      });
    }

    // Big master power button in parameter strip
    if (bigPowBtn) {
      bigPowBtn.addEventListener('click', () => {
        toggleModuleState(m.id, m.section);
      });
    }
  });

  // Cabinet IR dropdown
  const cabSelect = document.getElementById('select-cab-ir');
  if (cabSelect) {
    cabSelect.addEventListener('change', (e) => {
      sendParamUpdate('cab', 'ir_name', e.target.value);
      document.getElementById('insp-cab-ir').innerText = e.target.value;
    });
  }
}

function selectModulePanel(modId) {
  // Highlight active module in chain
  document.querySelectorAll('.chain-module').forEach(el => el.classList.remove('active-edit'));
  const activeMod = document.getElementById(`cmod-${modId}`);
  if (activeMod) activeMod.classList.add('active-edit');

  // Show active parameter panel
  document.querySelectorAll('.param-panel').forEach(p => p.classList.remove('active'));
  const panel = document.getElementById(`panel-${modId}`);
  if (panel) panel.classList.add('active');
}

async function toggleModuleState(modId, section) {
  const modElem = document.getElementById(`cmod-${modId}`);
  const led = document.getElementById(`cled-${modId}`);
  const bigBtn = document.getElementById(`btn-module-power-${modId}`);

  const isBypassed = modElem.classList.contains('bypassed');
  const newState = isBypassed; // if bypassed, turn ON

  setModuleVisualState(modId, newState);
  sendParamUpdate(section, 'enabled', newState);
}

function setModuleVisualState(modId, enabled) {
  const modElem = document.getElementById(`cmod-${modId}`);
  const led = document.getElementById(`cled-${modId}`);
  const bigBtn = document.getElementById(`btn-module-power-${modId}`);

  if (modElem) {
    if (enabled) {
      modElem.classList.remove('bypassed');
    } else {
      modElem.classList.add('bypassed');
    }
  }

  if (led) {
    if (enabled) {
      led.classList.remove('off');
      led.classList.add('on');
    } else {
      led.classList.remove('on');
      led.classList.add('off');
    }
  }

  if (bigBtn) {
    if (enabled) {
      bigBtn.classList.remove('off');
      bigBtn.classList.add('on');
    } else {
      bigBtn.classList.remove('on');
      bigBtn.classList.add('off');
    }
  }
}

// ── 3. PERFORMANCE SLOTS (1-5) ────────────────────────────────────────
function initPerformanceBar() {
  const slots = document.querySelectorAll('.perf-slot');
  slots.forEach(slot => {
    slot.addEventListener('click', () => {
      slots.forEach(s => s.classList.remove('active'));
      slot.classList.add('active');
      const presetId = slot.dataset.preset;
      loadPresetById(presetId);
    });
  });
}

// ── 4. PRESET & KEMPER PACK LOADING ──────────────────────────────────
async function loadLibrary() {
  // Load local presets
  const res = await fetch('/api/presets');
  const data = await res.json();
  allPresetsCache = data.presets || [];

  document.getElementById('count-factory').innerText = allPresetsCache.filter(p => p.author !== 'User').length;
  document.getElementById('count-user').innerText = allPresetsCache.filter(p => p.author === 'User').length;

  // Load Kemper packs
  try {
    const kRes = await fetch('/api/kemper/packs');
    const kData = await kRes.json();
    allKemperPacksCache = kData.packs || [];
    document.getElementById('count-kemper').innerText = allKemperPacksCache.length;
    renderKemperSubPacks(allKemperPacksCache);
  } catch (e) {}

  // Load TONE3000 Factory Neural Presets
  try {
    const t3kRes = await fetch('/api/tone3000/presets');
    const t3kData = await t3kRes.json();
    allTone3000PresetsCache = t3kData.presets || [];
    const tCount = document.getElementById('count-tone3000');
    if (tCount) tCount.innerText = allTone3000PresetsCache.length;
  } catch (e) {}

  document.getElementById('count-all').innerText = allPresetsCache.length + allTone3000PresetsCache.length + allKemperPacksCache.reduce((a, b) => a + (b.rig_count || 0), 0);

  // Render presets in table
  renderRigTable(allPresetsCache);

  // Load initial preset
  if (allPresetsCache.length > 0) {
    loadPresetById(allPresetsCache[0].id);
  }
}

function renderKemperSubPacks(packs) {
  const container = document.getElementById('kemper-sub-packs');
  container.innerHTML = '';
  packs.slice(0, 15).forEach(p => {
    const item = document.createElement('div');
    item.className = 'tree-sub-item';
    item.innerHTML = `<span>${p.pack_name}</span><span style="opacity:0.5;">${p.rig_count}</span>`;
    item.addEventListener('click', () => {
      document.querySelectorAll('.tree-item, .tree-sub-item').forEach(el => el.classList.remove('active'));
      item.classList.add('active');
      loadKemperPackRigs(p.path, p.pack_name);
    });
    container.appendChild(item);
  });
}

async function loadKemperPackRigs(packPath, packName) {
  document.getElementById('grid-current-folder').innerText = `Kemper Pack: ${packName}`;
  tableBody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding: 20px;">Loading Kemper Rigs...</td></tr>';
  const res = await fetch(`/api/kemper/rigs?pack_path=${encodeURIComponent(packPath)}`);
  const data = await res.json();
  renderRigTable(data.rigs, true);
}

function renderRigTable(rigs, isKemper = false) {
  tableBody.innerHTML = '';
  rigs.forEach((r, idx) => {
    const tr = document.createElement('tr');
    tr.dataset.id = r.id;
    if (r.id === currentLoadedRigId) tr.classList.add('active-row');

    // Stepped gain meter (1 to 9 bars)
    const gainVal = r.settings ? (r.settings.amp.gain || 0.6) : (r.name.toLowerCase().includes('clean') ? 0.2 : 0.7);
    const gainBarsCount = Math.min(9, Math.max(1, Math.round(gainVal * 9)));
    let gainMeterHtml = '<div class="gain-tier-meter">';
    for (let b = 1; b <= 9; b++) {
      gainMeterHtml += `<div class="gain-bar ${b <= gainBarsCount ? 'on' : ''}"></div>`;
    }
    gainMeterHtml += '</div>';

    const ampName = r.settings ? (r.settings.amp.model || '5150') : (r.name.toLowerCase().includes('plexi') ? 'Plexi' : '5150');
    const cabName = r.settings ? (r.settings.cab.ir_name || 'Celestion V30') : 'Celestion V30 4x12';

    tr.innerHTML = `
      <td style="text-align: center;">⭐</td>
      <td><strong>${r.name}</strong></td>
      <td>${r.author || 'กดจนหลอนTone'}</td>
      <td>${gainMeterHtml}</td>
      <td>${ampName}</td>
      <td>${cabName}</td>
      <td><span class="badge" style="background:#202530; color:#4ef58d; padding:2px 6px; border-radius:3px;">${r.category || (isKemper ? 'Kemper Rig' : 'Factory')}</span></td>
    `;

    tr.addEventListener('click', () => {
      document.querySelectorAll('.rig-table tbody tr').forEach(row => row.classList.remove('active-row'));
      tr.classList.add('active-row');
      currentLoadedRigId = r.id;
      updateInspector(r);

      if (isKemper) {
        loadKemperRig(r.name, r.author);
      } else if (r.isTone3000 || (r.id && r.id.startsWith('t3k_'))) {
        loadTone3000Preset(r.id);
      } else {
        loadPresetById(r.id);
      }
    });

    tableBody.appendChild(tr);
  });
}

function updateInspector(r) {
  document.getElementById('insp-name').innerText = r.name;
  document.getElementById('insp-author').innerText = r.author || 'กดจนหลอนTone Studio';
  document.getElementById('insp-category').innerText = r.category || 'Lead / High Gain';
  if (r.settings && r.settings.amp) {
    document.getElementById('insp-amp-model').innerText = r.settings.amp.model || '5150 High Gain';
    document.getElementById('insp-cab-ir').innerText = r.settings.cab.ir_name || 'Celestion V30 4x12';
  }
}

async function loadPresetById(pid) {
  try {
    const res = await fetch('/api/preset/load', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ preset_id: pid })
    });
    const data = await res.json();
    if (data.success) {
      currentLoadedRigId = pid;
      updateInspector(data.loaded_preset);
      syncGuiToState(data.state);
    }
  } catch (e) {}
}

async function loadKemperRig(name, author) {
  try {
    const res = await fetch('/api/kemper/load', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, author })
    });
    const d = await res.json();
    if (d.success) {
      syncGuiToState(d.state);
      document.getElementById('insp-category').innerText = `Kemper: ${d.category}`;
    }
  } catch (e) {}
}

function renderTone3000Table(presets) {
  tableBody.innerHTML = '';
  presets.forEach((r) => {
    const tr = document.createElement('tr');
    tr.dataset.id = r.id;
    if (r.id === currentLoadedRigId) tr.classList.add('active-row');

    const gainBarsCount = Math.min(9, Math.max(1, Math.round((r.gain || 0.6) * 9)));
    let gainMeterHtml = '<div class="gain-tier-meter">';
    for (let b = 1; b <= 9; b++) {
      gainMeterHtml += `<div class="gain-bar ${b <= gainBarsCount ? 'on' : ''}"></div>`;
    }
    gainMeterHtml += '</div>';

    tr.innerHTML = `
      <td style="text-align: center;">🔥</td>
      <td><strong>${r.name}</strong></td>
      <td>${r.author || 'TONE3000'}</td>
      <td>${gainMeterHtml}</td>
      <td>${r.amp_model}</td>
      <td>${r.cab_model}</td>
      <td><span class="badge" style="background:#2a1b3d; color:#ce93d8; border:1px solid #7b1fa2; padding:2px 6px; border-radius:3px;">TONE3000 NAM</span></td>
    `;

    tr.addEventListener('click', () => {
      document.querySelectorAll('.rig-table tbody tr').forEach(row => row.classList.remove('active-row'));
      tr.classList.add('active-row');
      currentLoadedRigId = r.id;
      document.getElementById('insp-name').innerText = r.name;
      document.getElementById('insp-author').innerText = r.author;
      document.getElementById('insp-category').innerText = `Neural: ${r.category}`;
      document.getElementById('insp-amp-model').innerText = r.amp_model;
      document.getElementById('insp-cab-ir').innerText = r.cab_model;
      loadTone3000Preset(r.id);
    });

    tableBody.appendChild(tr);
  });
}

async function loadTone3000Preset(id) {
  try {
    const res = await fetch('/api/tone3000/load', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id })
    });
    const d = await res.json();
    if (d.success) {
      syncGuiToState(d.state);
    }
  } catch (e) {}
}

// ── 5. SYNC GUI CONTROLS TO STATE ────────────────────────────────────
function syncGuiToState(state) {
  const c = state.chain;

  // Sync Knobs
  setKnob('knob-amp-gain', c.amp.gain);
  setKnob('knob-amp-bass', c.amp.bass);
  setKnob('knob-amp-mid', c.amp.mid);
  setKnob('knob-amp-treble', c.amp.treble);
  setKnob('knob-amp-presence', c.amp.presence);
  setKnob('knob-amp-master', c.amp.master);

  setKnob('knob-ts-drive', c.screamer.drive);
  setKnob('knob-ts-tone', c.screamer.tone);
  setKnob('knob-ts-level', c.screamer.level);

  setKnob('knob-gate-thresh', c.gate.threshold);

  setKnob('knob-delay-time', c.delay.time);
  setKnob('knob-delay-fb', c.delay.feedback);
  setKnob('knob-delay-mix', c.delay.mix);

  setKnob('knob-rev-decay', c.reverb.decay);
  setKnob('knob-rev-mix', c.reverb.mix);

  // Sync Modules On/Off
  setModuleVisualState('gate', c.gate.enabled);
  setModuleVisualState('screamer', c.screamer.enabled);
  setModuleVisualState('amp', c.amp.enabled);
  setModuleVisualState('cab', c.cab.enabled);
  setModuleVisualState('delay', c.delay.enabled);
  setModuleVisualState('reverb', c.reverb.enabled);

  // Amp badge
  const badge = document.getElementById('badge-amp-model');
  const chainTitle = document.getElementById('cmod-amp-title');
  if (badge) badge.innerText = c.amp.model.toUpperCase();
  if (chainTitle) chainTitle.innerText = `AMP (${c.amp.model.toUpperCase()})`;

  // Cab dropdown
  if (document.getElementById('select-cab-ir')) {
    document.getElementById('select-cab-ir').value = c.cab.ir_name;
  }
}

// ── 6. AUDIO ENGINE CONTROLS & VU METERS ─────────────────────────────
btnPower.addEventListener('click', async () => {
  if (!isEngineRunning) {
    const res = await fetch('/api/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
    const data = await res.json();
    if (data.success) {
      isEngineRunning = true;
      btnPower.innerText = 'ON';
      btnPower.classList.remove('off');
      btnPower.classList.add('on');
      startPolling();
    } else {
      alert('Error starting Line 6 UX1 Audio Engine: ' + data.message);
    }
  } else {
    await fetch('/api/stop', { method: 'POST' });
    isEngineRunning = false;
    btnPower.innerText = 'POWER';
    btnPower.classList.remove('on');
    btnPower.classList.add('off');
    stopPolling();
  }
});

btnTuner.addEventListener('click', async () => {
  isTunerActive = !isTunerActive;
  if (isTunerActive) {
    btnTuner.style.borderColor = '#00e5ff';
    btnTuner.style.color = '#00e5ff';
    tunerDisplay.classList.remove('hidden');
  } else {
    btnTuner.style.borderColor = '';
    btnTuner.style.color = '';
    tunerDisplay.classList.add('hidden');
  }
  await fetch('/api/tuner/toggle', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ active: isTunerActive })
  });
});

function startPolling() {
  if (pollingInterval) clearInterval(pollingInterval);
  pollingInterval = setInterval(async () => {
    try {
      const res = await fetch('/api/status');
      const state = await res.json();

      // Update VU meters (Logarithmic dB scale: -60 dB to 0 dB)
      function rmsToPercent(rms) {
        if (rms < 0.0001) return 0;
        const db = 20 * Math.log10(rms);
        return Math.max(0, Math.min(100, (db + 60) / 60 * 100));
      }
      if (meterIn) meterIn.style.width = rmsToPercent(state.input_meter / 100) + '%';
      if (meterOut) meterOut.style.width = rmsToPercent(state.output_meter / 100) + '%';

      // Update Tuner
      if (state.tuner && isTunerActive) {
        const noteElem = document.getElementById('tuner-note');
        const needle = document.getElementById('tuner-needle');
        const statusElem = document.getElementById('tuner-status');

        if (state.tuner.note !== '--') {
          noteElem.innerText = state.tuner.note + state.tuner.octave;
          const cents = Math.max(-50, Math.min(50, state.tuner.cents));
          const pct = 50 + (cents / 50.0) * 45;
          needle.style.left = `${pct}%`;

          if (Math.abs(cents) <= 4) {
            statusElem.innerText = 'IN TUNE';
            statusElem.className = 'tuner-tune-status in-tune';
          } else if (cents < 0) {
            statusElem.innerText = `FLAT (${cents})`;
            statusElem.className = 'tuner-tune-status';
          } else {
            statusElem.innerText = `SHARP (+${cents})`;
            statusElem.className = 'tuner-tune-status';
          }
        } else {
          noteElem.innerText = '--';
          needle.style.left = '50%';
          statusElem.innerText = 'PLAY STRING';
          statusElem.className = 'tuner-tune-status';
        }
      }
    } catch (e) {}
  }, 75);
}

function stopPolling() {
  if (pollingInterval) {
    clearInterval(pollingInterval);
    pollingInterval = null;
  }
  if (meterIn) meterIn.style.width = '0%';
  if (meterOut) meterOut.style.width = '0%';
}

async function sendParamUpdate(section, param, value) {
  try {
    await fetch('/api/parameter', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ section, param, value })
    });
  } catch (e) {}
}

// ── 7. PRESET SAVE & LOCATIONS NAVIGATION ────────────────────────────
document.getElementById('btn-save-preset').addEventListener('click', async () => {
  const name = prompt('ตั้งชื่อพรีเซ็ตเสียงของคุณ (Preset Name):', 'กดจนหลอน Custom Lead');
  if (!name || !name.trim()) return;
  const category = prompt('หมวดหมู่เสียง (Category e.g. Metal, Blues, Clean):', 'User Custom') || 'User Custom';
  const pid = 'user-' + Date.now();
  try {
    const res = await fetch('/api/preset/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: pid, name: name.trim(), category: category.trim(), author: 'User' })
    });
    const d = await res.json();
    if (d.success) {
      alert(`บันทึกพรีเซ็ต "${name}" เรียบร้อยแล้ว!`);
      await loadLibrary();
    }
  } catch (e) {
    alert('Error saving preset: ' + e);
  }
});

// Sidebar folder navigation
document.querySelectorAll('.tree-item').forEach(item => {
  item.addEventListener('click', () => {
    const folder = item.dataset.folder;
    document.querySelectorAll('.tree-item, .tree-sub-item').forEach(el => el.classList.remove('active'));
    item.classList.add('active');

    if (folder === 'all') {
      document.getElementById('grid-current-folder').innerText = 'All Rigs (Loaded)';
      renderRigTable(allPresetsCache);
    } else if (folder === 'factory') {
      document.getElementById('grid-current-folder').innerText = 'Factory NAM Tones';
      renderRigTable(allPresetsCache.filter(p => p.author !== 'User'));
    } else if (folder === 'tone3000') {
      document.getElementById('grid-current-folder').innerText = 'TONE3000 Neural Rigs (NAM Models)';
      renderTone3000Table(allTone3000PresetsCache);
    } else if (folder === 'user') {
      document.getElementById('grid-current-folder').innerText = 'User Custom Library';
      renderRigTable(allPresetsCache.filter(p => p.author === 'User'));
    } else if (folder === 'kemper-root') {
      const sub = document.getElementById('kemper-sub-packs');
      sub.classList.toggle('open');
    }
  });
});

// Search filter
searchInput.addEventListener('input', (e) => {
  const q = e.target.value.toLowerCase().trim();
  const allList = [
    ...allPresetsCache,
    ...allTone3000PresetsCache.map(t => ({
      id: t.id,
      name: t.name,
      author: t.author,
      category: `Neural: ${t.category}`,
      settings: {
        amp: { model: t.amp_model, gain: t.gain },
        cab: { ir_name: t.cab_model }
      },
      isTone3000: true
    }))
  ];
  if (!q) {
    renderRigTable(allPresetsCache);
    return;
  }
  const filtered = allList.filter(r =>
    r.name.toLowerCase().includes(q) ||
    (r.author && r.author.toLowerCase().includes(q)) ||
    (r.category && r.category.toLowerCase().includes(q))
  );
  renderRigTable(filtered);
});

// ── 8. INITIAL BOOTSTRAP ─────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  initKnobs();
  initSignalChain();
  initPerformanceBar();
  loadLibrary();
  selectModulePanel('amp');
});
