// ====================================================================
// ⚡ กดจนหลอนTone - Guitar Rig & Amp Workstation Engine Frontend
// ====================================================================

let isEngineRunning = false;
let isTunerActive = false;
let pollingInterval = null;
let currentLoadedRigId = null;
let allPresetsCache = [];
let allKemperPacksCache = [];

// Rig names, authors and amp metadata come from .rigpack SQLite files that
// anyone can ship. Everything interpolated into innerHTML must go through this.
function esc(v) {
  if (v === null || v === undefined) return '';
  return String(v)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// Every pack numbers its own rigs from 1, so bare r.id collides across the 35
// packs. Selection identity must include the pack.
function rigKey(r) {
  if (!r) return '';
  const scope = r.pack_path || r.pack || (r.__packPath) || '';
  return scope ? `${scope}::${r.id}` : String(r.id);
}
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
    const defaultVal = parseFloat(knob.dataset.default || knob.dataset.val || '0.5');

    updateKnobAngle(knob, startVal, min, max);

    // Mouse drag (vertical)
    knob.addEventListener('mousedown', (e) => {
      isDragging = true;
      startY = e.clientY;
      startVal = parseFloat(knob.dataset.val);
      document.body.style.cursor = 'ns-resize';
      knob.classList.add('knob-active');
      e.preventDefault();
    });

    window.addEventListener('mousemove', (e) => {
      if (!isDragging) return;
      const deltaY = startY - e.clientY;
      const range = max - min;
      const step = range / 270; // Smoother: 270 degrees for full range
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
        knob.classList.remove('knob-active');
      }
    });

    // Scroll wheel support
    knob.addEventListener('wheel', (e) => {
      e.preventDefault();
      const currentVal = parseFloat(knob.dataset.val);
      const range = max - min;
      const step = range / 50; // Smoother scroll
      const delta = e.deltaY > 0 ? -step : step;
      let newVal = currentVal + delta;
      newVal = Math.max(min, Math.min(max, newVal));

      knob.dataset.val = newVal;
      updateKnobAngle(knob, newVal, min, max);
      updateKnobLabel(knob, section, param, newVal);
      sendParamUpdate(section, param, newVal);
    }, { passive: false });

    // Double-click reset to default
    knob.addEventListener('dblclick', () => {
      knob.dataset.val = defaultVal;
      updateKnobAngle(knob, defaultVal, min, max);
      updateKnobLabel(knob, section, param, defaultVal);
      sendParamUpdate(section, param, defaultVal);
      
      // Visual feedback - flash
      knob.classList.add('knob-flash');
      setTimeout(() => knob.classList.remove('knob-flash'), 200);
    });

    // Right-click context menu for presets
    knob.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      showKnobContext(knob, section, param, min, max);
    });
  });
}

function showKnobContext(knob, section, param, min, max) {
  // Simple preset values: 0%, 25%, 50%, 75%, 100%
  const presets = [0, 0.25, 0.5, 0.75, 1.0];
  
  // Create context menu
  const menu = document.createElement('div');
  menu.className = 'knob-context-menu';
  menu.innerHTML = presets.map((val, i) => 
    `<div class="context-item" data-val="${val}">${Math.round(val * 100)}%</div>`
  ).join('');
  
  // Position menu
  const rect = knob.getBoundingClientRect();
  menu.style.left = rect.left + 'px';
  menu.style.top = (rect.bottom + 5) + 'px';
  
  document.body.appendChild(menu);
  
  // Handle clicks
  menu.querySelectorAll('.context-item').forEach(item => {
    item.addEventListener('click', () => {
      const val = parseFloat(item.dataset.val);
      const newVal = min + val * (max - min);
      knob.dataset.val = newVal;
      updateKnobAngle(knob, newVal, min, max);
      updateKnobLabel(knob, section, param, newVal);
      sendParamUpdate(section, param, newVal);
      document.body.removeChild(menu);
    });
  });
  
  // Close on click outside
  setTimeout(() => {
    document.addEventListener('click', function closeMenu(e) {
      if (!menu.contains(e.target)) {
        document.body.removeChild(menu);
        document.removeEventListener('click', closeMenu);
      }
    });
  }, 0);
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
        if (e.target.closest('.mod-power-btn') || e.target.closest('.drag-handle')) return; // handled by other buttons
        selectModulePanel(m.id);
      });
      
      // Drag and drop reordering
      initDragAndDrop(modElem);
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
      if (e.target.value === 'custom_upload') {
        document.getElementById('ir-file-input').click();
        e.target.value = cabSelect.dataset.lastValue || 'Celestion V30 4x12';
      } else {
        cabSelect.dataset.lastValue = e.target.value;
        sendParamUpdate('cab', 'ir_name', e.target.value);
        document.getElementById('insp-cab-ir').innerText = e.target.value;
      }
    });
  }
  
  // Custom IR file input
  const irFileInput = document.getElementById('ir-file-input');
  if (irFileInput) {
    irFileInput.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (file && file.name.endsWith('.wav')) {
        await uploadCustomIR(file);
      }
    });
  }
  
  // Custom IR drag-and-drop zone
  const cabDropZone = document.getElementById('cab-drop-zone');
  if (cabDropZone) {
    cabDropZone.addEventListener('click', () => {
      document.getElementById('ir-file-input').click();
    });
    
    cabDropZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      cabDropZone.classList.add('drag-over');
    });
    
    cabDropZone.addEventListener('dragleave', () => {
      cabDropZone.classList.remove('drag-over');
    });
    
    cabDropZone.addEventListener('drop', async (e) => {
      e.preventDefault();
      cabDropZone.classList.remove('drag-over');
      
      const file = e.dataTransfer.files[0];
      if (file && file.name.endsWith('.wav')) {
        await uploadCustomIR(file);
      }
    });
  }
}

async function uploadCustomIR(file) {
  const cabDropZone = document.getElementById('cab-drop-zone');
  const dropText = cabDropZone ? cabDropZone.querySelector('.drop-text') : null;
  const setDropText = (msg) => { if (dropText) dropText.innerText = msg; };

  const formData = new FormData();
  // Field name MUST match the FastAPI parameter name in server.py.
  formData.append('ir_file', file);

  if (dropText) setDropText('Uploading...');
  try {
    const response = await fetch('/api/cab/load_ir', {
      method: 'POST',
      body: formData
    });

    // Surface the server's validation detail instead of throwing on !ok.
    let data = null;
    try { data = await response.json(); } catch (_) { /* non-JSON error body */ }

    if (!response.ok || !data || !data.success) {
      const detail = (data && (data.detail || data.message)) || `HTTP ${response.status}`;
      throw new Error(detail);
    }

    // Add to dropdown
    const cabSelect = document.getElementById('select-cab-ir');
    if (cabSelect) {
      // Replace any stale entry for the same name, then select it.
      const existing = Array.from(cabSelect.options).find(o => o.value === data.ir_name);
      if (existing) existing.remove();
      const option = document.createElement('option');
      option.value = data.ir_name;
      option.innerText = `🎵 ${data.ir_name}`;
      cabSelect.insertBefore(option, cabSelect.firstChild);
      cabSelect.value = data.ir_name;
      cabSelect.dataset.lastValue = data.ir_name;
    }

    // The IR buffer is already installed server-side; only the label needs syncing.
    sendParamUpdate('cab', 'ir_name', data.ir_name);
    const insp = document.getElementById('insp-cab-ir');
    if (insp) insp.innerText = data.ir_name;

    const trimmed = data.truncated ? ` (trimmed to ${data.samples} smp)` : '';
    setDropText(`Loaded: ${data.ir_name}${trimmed}`);
    setTimeout(() => setDropText('Drag & Drop .wav IR file here'), 2500);
  } catch (error) {
    console.error('Failed to upload IR:', error);
    setDropText(`Upload failed: ${error.message}`);
    setTimeout(() => setDropText('Drag & Drop .wav IR file here'), 3500);
  }
}

// Shared across every chain module. This MUST live outside the per-element
// handler: when each module owned its own `draggedElement`, only the module
// that received `dragstart` had it set, so the drop target's closure always
// saw null and the reorder silently did nothing.
let chainDragSource = null;

function initDragAndDrop(draggableElement) {
  draggableElement.addEventListener('dragstart', (e) => {
    chainDragSource = draggableElement;
    draggableElement.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', draggableElement.id);
  });

  draggableElement.addEventListener('dragend', () => {
    draggableElement.classList.remove('dragging');
    document.querySelectorAll('.chain-module').forEach(el => {
      el.classList.remove('drag-over');
    });
    chainDragSource = null;
  });

  draggableElement.addEventListener('dragover', (e) => {
    e.preventDefault();
    if (chainDragSource && chainDragSource !== draggableElement) {
      e.dataTransfer.dropEffect = 'move';
      draggableElement.classList.add('drag-over');
    }
  });

  draggableElement.addEventListener('dragleave', () => {
    draggableElement.classList.remove('drag-over');
  });

  draggableElement.addEventListener('drop', (e) => {
    e.preventDefault();
    e.stopPropagation();
    draggableElement.classList.remove('drag-over');

    if (!chainDragSource || chainDragSource === draggableElement) return;

    const signalChain = document.getElementById('signal-chain');
    const allModules = Array.from(signalChain.querySelectorAll('.chain-module.draggable'));
    const draggedIndex = allModules.indexOf(chainDragSource);
    const targetIndex = allModules.indexOf(draggableElement);

    if (draggedIndex < 0 || targetIndex < 0) return;

    if (draggedIndex < targetIndex) {
      // Move down: place after the target.
      signalChain.insertBefore(chainDragSource, draggableElement.nextSibling);
    } else {
      // Move up: place before the target.
      signalChain.insertBefore(chainDragSource, draggableElement);
    }

    saveSignalChainOrder();
    selectModulePanel(chainDragSource.dataset.module);
  });
}

function saveSignalChainOrder() {
  const signalChain = document.getElementById('signal-chain');
  const allModules = Array.from(signalChain.querySelectorAll('.chain-module.draggable'));
  const order = allModules.map(m => m.dataset.module);
  
  localStorage.setItem('signalChainOrder', JSON.stringify(order));
  console.log('Signal chain order saved:', order);
}

function loadSignalChainOrder() {
  let order;
  try {
    const savedOrder = localStorage.getItem('signalChainOrder');
    if (!savedOrder) return;
    order = JSON.parse(savedOrder);
  } catch (_) {
    return; // Corrupt storage must not break startup.
  }
  if (!Array.isArray(order) || !order.length) return;

  const signalChain = document.getElementById('signal-chain');
  if (!signalChain) return;

  // The chain interleaves modules with `.chain-arrow` separators. A previous
  // implementation used appendChild, which moved every module past the arrows
  // and destroyed the layout. Instead, permute the modules among the existing
  // module slots so the separators stay put.
  const slots = Array.from(signalChain.querySelectorAll('.chain-module.draggable'));
  const byId = new Map(slots.map(el => [el.dataset.module, el]));
  const defaultOrder = slots.map(el => el.dataset.module);

  // Start from defaults, then apply the saved order for ids that still exist.
  const resolved = defaultOrder.slice();
  const seen = new Set();
  order.forEach(id => {
    const at = resolved.indexOf(id);
    if (at !== -1 && !seen.has(id)) {
      resolved.splice(at, 1);
      seen.add(id);
    }
  });
  // Append any saved ids that were not in the original default list.
  order.forEach(id => {
    if (byId.has(id) && !resolved.includes(id)) resolved.push(id);
  });

  // Write each resolved module into its corresponding slot position.
  resolved.forEach((id, i) => {
    const el = byId.get(id);
    const slot = slots[i];
    if (el && slot && el !== slot) signalChain.insertBefore(el, slot);
  });
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
    // Main slot click
    slot.addEventListener('click', (e) => {
      if (e.target.classList.contains('slot-edit-btn')) return; // Let edit button handle it
      
      slots.forEach(s => s.classList.remove('active'));
      slot.classList.add('active');
      const presetId = slot.dataset.preset;
      loadPresetById(presetId);
    });
    
    // Edit button click
    const editBtn = slot.querySelector('.slot-edit-btn');
    if (editBtn) {
      editBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        editPerformanceSlot(slot);
      });
    }
  });
}

function editPerformanceSlot(slot) {
  const slotNum = slot.dataset.slot;
  const currentName = slot.querySelector('.slot-name').innerText;
  const currentPreset = slot.dataset.preset;
  
  // Simple prompt for now (could be improved with modal)
  const newName = prompt(`Edit Performance Slot ${slotNum} Name:`, currentName);
  if (newName && newName !== currentName) {
    slot.querySelector('.slot-name').innerText = newName;
    // Save to localStorage or backend
    savePerformanceSlotConfig(slotNum, { name: newName, preset: currentPreset });
  }
}

function savePerformanceSlotConfig(slotNum, config) {
  // Save performance slot configuration
  const perfConfig = JSON.parse(localStorage.getItem('performanceConfig') || '{}');
  perfConfig[slotNum] = config;
  localStorage.setItem('performanceConfig', JSON.stringify(perfConfig));
}

function loadPerformanceSlotConfig() {
  const perfConfig = JSON.parse(localStorage.getItem('performanceConfig') || '{}');
  const slots = document.querySelectorAll('.perf-slot');
  
  slots.forEach(slot => {
    const slotNum = slot.dataset.slot;
    if (perfConfig[slotNum]) {
      slot.dataset.preset = perfConfig[slotNum].preset;
      slot.querySelector('.slot-name').innerText = perfConfig[slotNum].name;
    }
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

  // Category filter chips, built from the server's aggregate counts.
  renderCategoryChips();

  // Show every pack. The previous slice(0,15) hid 20 of the 35 installed
  // packs with no way to reach them.
  packs.forEach((p) => {
    const item = document.createElement('div');
    item.className = 'tree-sub-item';
    item.title = esc(`${p.pack_name} — ${p.rig_count} rigs`);
    item.innerHTML =
      `<span>${esc(p.pack_name)}</span>` +
      `<span style="opacity:0.5;">${esc(p.rig_count ?? 0)}</span>`;
    if (p.error) {
      item.style.opacity = '0.45';
      item.title = `Unreadable pack: ${p.error}`;
    }
    item.addEventListener('click', () => {
      document.querySelectorAll('.tree-item, .tree-sub-item').forEach(el => el.classList.remove('active'));
      item.classList.add('active');
      loadKemperPackRigs(p.path, p.pack_name);
    });
    container.appendChild(item);
  });
}

let kemperCategoryFilter = null;

function renderCategoryChips() {
  const host = document.getElementById('kemper-categories');
  if (!host) return;

  fetch('/api/kemper/categories')
    .then(r => r.json())
    .then(d => {
      const cats = d.categories || [];
      host.innerHTML = '';

      const all = document.createElement('button');
      all.className = 'cat-chip active';
      all.textContent = 'All';
      all.addEventListener('click', () => setCategoryFilter(null, all));
      host.appendChild(all);

      cats.forEach(c => {
        const b = document.createElement('button');
        b.className = 'cat-chip';
        b.textContent = `${c.category} (${c.count})`;
        b.addEventListener('click', () => setCategoryFilter(c.category, b));
        host.appendChild(b);
      });
    })
    .catch(() => { /* chips are optional; grid still works */ });
}

function setCategoryFilter(category, activeBtn) {
  kemperCategoryFilter = category;
  document.querySelectorAll('#kemper-categories .cat-chip').forEach(c => c.classList.remove('active'));
  if (activeBtn) activeBtn.classList.add('active');

  // Re-run whatever the user is currently looking at.
  if (librarySearchTerm) {
    runLibrarySearch();
  } else if (currentKemperPack) {
    loadKemperPackRigs(currentKemperPack.path, currentKemperPack.pack_name);
  }
}

let currentKemperPack = null;

async function loadKemperPackRigs(packPath, packName) {
  currentKemperPack = allKemperPacksCache.find(p => p.path === packPath) || null;
  const title = document.getElementById('grid-current-folder');
  title.innerText = `Kemper Pack: ${packName}` + (kemperCategoryFilter ? ` · ${kemperCategoryFilter}` : '');
  tableBody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:20px;">Loading Kemper Rigs…</td></tr>';

  const url = new URL('/api/kemper/rigs', window.location.origin);
  url.searchParams.set('pack_path', packPath);
  url.searchParams.set('limit', '5000');
  url.searchParams.set('decode', 'true');

  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    let rigs = data.rigs || [];
    if (kemperCategoryFilter) {
      rigs = rigs.filter(r => (r.category || '') === kemperCategoryFilter);
    }
    title.innerText = `Kemper Pack: ${packName} — ${rigs.length} rigs`;
    renderRigTable(rigs, true);
  } catch (err) {
    console.error('Failed to load pack rigs:', err);
    tableBody.innerHTML =
      `<tr><td colspan="7" style="text-align:center; padding:20px; color:#e0555f;">Failed to load pack: ${esc(err.message)}</td></tr>`;
  }
}

function renderRigTable(rigs, isKemper = false) {
  tableBody.innerHTML = '';
  if (!rigs || !rigs.length) {
    tableBody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:20px; color:#7a8290;">No rigs matched.</td></tr>';
    return;
  }

  rigs.forEach((r) => {
    const tr = document.createElement('tr');
    tr.dataset.id = r.id;
    tr.dataset.rigKey = rigKey(r);
    if (rigKey(r) === currentLoadedRigId) tr.classList.add('active-row');

    // Stepped gain meter (1 to 9 bars)
    const gainVal = r.settings ? (r.settings.amp.gain || 0.6) : (r.name.toLowerCase().includes('clean') ? 0.2 : 0.7);
    const gainBarsCount = Math.min(9, Math.max(1, Math.round(gainVal * 9)));
    let gainMeterHtml = '<div class="gain-tier-meter">';
    for (let b = 1; b <= 9; b++) {
      gainMeterHtml += `<div class="gain-bar ${b <= gainBarsCount ? 'on' : ''}"></div>`;
    }
    gainMeterHtml += '</div>';

    // Prefer values actually decoded from the rig; fall back only when absent.
    const amp = r.amp || {};
    const ampName = r.settings
      ? (r.settings.amp.model || '5150')
      : (amp.amp_name || amp.model || (r.name.toLowerCase().includes('plexi') ? 'Plexi' : '5150'));
    const cabName = r.settings
      ? (r.settings.cab.ir_name || 'Celestion V30')
      : (amp.cab_name || 'Celestion V30 4x12');

    // Keep the real values on the row so the click handler does not have to
    // re-derive them from the display name.
    tr.dataset.rigName = r.name;
    tr.dataset.rigAuthor = r.author || '';
    tr.dataset.packName = r.pack || '';

    tr.innerHTML = `
      <td style="text-align: center;">⭐</td>
      <td><strong>${esc(r.name)}</strong></td>
      <td>${esc(r.author || 'กดจนหลอนTone')}</td>
      <td>${gainMeterHtml}</td>
      <td>${esc(ampName)}</td>
      <td>${esc(cabName)}</td>
      <td><span class="badge" style="background:#202530; color:#4ef58d; padding:2px 6px; border-radius:3px;">${esc(r.category || (isKemper ? 'Kemper Rig' : 'Factory'))}</span></td>
    `;

    tr.addEventListener('click', () => {
      document.querySelectorAll('.rig-table tbody tr').forEach(row => row.classList.remove('active-row'));
      tr.classList.add('active-row');
      currentLoadedRigId = rigKey(r);
      updateInspector(r);

      if (isKemper) {
        loadKemperRig(r.name, r.author);
      } else if (r.isTone3000 || (r.id && String(r.id).startsWith('t3k_'))) {
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
      <td><strong>${esc(r.name)}</strong></td>
      <td>${esc(r.author || 'TONE3000')}</td>
      <td>${gainMeterHtml}</td>
      <td>${esc(r.amp_model)}</td>
      <td>${esc(r.cab_model)}</td>
      <td><span class="badge" style="background:#2a1b3d; color:#ce93d8; border:1px solid #7b1fa2; padding:2px 6px; border-radius:3px;">TONE3000 NAM</span></td>
    `;

    tr.addEventListener('click', () => {
      document.querySelectorAll('.rig-table tbody tr').forEach(row => row.classList.remove('active-row'));
      tr.classList.add('active-row');
      currentLoadedRigId = rigKey(r);
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

// ── Library search ───────────────────────────────────────────────────
// The previous filter only ever scanned the handful of local presets and
// TONE3000 entries, so the placeholder "Search Rigs, Amps, Artists..." could
// not reach any of the 1821 installed KEMPER rigs. Searching now goes through
// /api/kemper/search, which covers rig name, author, and (opt-in) the amp,
// brand, model and cabinet decoded from each rig's SysEx payload.

let librarySearchTerm = '';
let librarySearchTimer = null;
let librarySearchToken = 0;

function searchLocalOnly(term) {
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
  if (!term) {
    renderRigTable(allPresetsCache);
    return;
  }
  renderRigTable(allList.filter(r =>
    String(r.name || '').toLowerCase().includes(term) ||
    String(r.author || '').toLowerCase().includes(term) ||
    String(r.category || '').toLowerCase().includes(term)
  ));
}

async function runLibrarySearch() {
  const term = librarySearchTerm;
  const token = ++librarySearchToken;

  // Fewer than 2 characters: fall back to the local, instant list.
  if (term.length < 2) {
    searchLocalOnly(term);
    return;
  }

  const url = new URL('/api/kemper/search', window.location.origin);
  url.searchParams.set('q', term);
  url.searchParams.set('limit', '400');
  url.searchParams.set('include_amp', 'true');
  if (kemperCategoryFilter) url.searchParams.set('category', kemperCategoryFilter);

  const title = document.getElementById('grid-current-folder');
  title.innerText = `Searching "${term}"…`;
  tableBody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:20px;">Searching 1821 KEMPER rigs…</td></tr>';

  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    // Drop stale responses so a slow earlier query cannot overwrite a newer one.
    if (token !== librarySearchToken) return;

    title.innerText = `"${term}" — ${data.count} KEMPER rigs`;
    renderRigTable(data.results || [], true);
  } catch (err) {
    if (token !== librarySearchToken) return;
    console.error('Library search failed:', err);
    title.innerText = `Search failed: ${err.message}`;
    tableBody.innerHTML =
      `<tr><td colspan="7" style="text-align:center; padding:20px; color:#e0555f;">Search failed: ${esc(err.message)}</td></tr>`;
  }
}

searchInput.addEventListener('input', (e) => {
  librarySearchTerm = e.target.value.toLowerCase().trim();
  clearTimeout(librarySearchTimer);
  // Debounce: include_amp decodes one blob per rig server-side.
  librarySearchTimer = setTimeout(runLibrarySearch, 260);
});

// Escape restores the full local list without re-querying the server.
searchInput.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    e.target.value = '';
    librarySearchTerm = '';
    clearTimeout(librarySearchTimer);
    librarySearchToken++;
    searchLocalOnly('');
  }
});

// ── 8. INITIAL BOOTSTRAP ─────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  initKnobs();
  initSignalChain();
  loadSignalChainOrder(); // Load saved signal chain order
  initPerformanceBar();
  loadPerformanceSlotConfig(); // Load saved slot configurations
  loadLibrary();
  selectModulePanel('amp');
});
