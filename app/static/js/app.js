/* ══════════════════════════════════════════════════════
   DeepGuard – Frontend JavaScript
   ══════════════════════════════════════════════════════ */

'use strict';

// ── Tab switching ────────────────────────────────────────
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(`panel-${tab.dataset.tab}`).classList.add('active');
    hideResults();
  });
});

// ── File upload helpers ──────────────────────────────────
function setupUploadZone(type, previewFn) {
  const zone  = document.getElementById(`drop-${type}`);
  const input = document.getElementById(`file-${type}`);

  zone.addEventListener('click',    () => input.click());
  zone.addEventListener('keydown',  e => { if (e.key === 'Enter' || e.key === ' ') input.click(); });
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave',() => zone.classList.remove('drag-over'));
  zone.addEventListener('drop',     e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) { input.files = e.dataTransfer.files; previewFn(file); }
  });
  input.addEventListener('change', () => {
    if (input.files[0]) previewFn(input.files[0]);
  });
}

function makeObjectURL(file) {
  return URL.createObjectURL(file);
}

function showPreview(type, file) {
  const zone    = document.getElementById(`drop-${type}`);
  const wrap    = document.getElementById(`preview-${type}-wrap`);
  const el      = document.getElementById(`preview-${type}`);
  zone.style.display = 'none';
  wrap.classList.remove('hidden');
  el.src = makeObjectURL(file);
}

setupUploadZone('image', f => showPreview('image', f));
setupUploadZone('video', f => showPreview('video', f));
setupUploadZone('audio', f => showPreview('audio', f));

// Clear buttons
document.querySelectorAll('.btn-clear').forEach(btn => {
  btn.addEventListener('click', () => {
    const type  = btn.dataset.target;
    const zone  = document.getElementById(`drop-${type}`);
    const wrap  = document.getElementById(`preview-${type}-wrap`);
    const input = document.getElementById(`file-${type}`);
    const el    = document.getElementById(`preview-${type}`);
    el.src = '';
    input.value = '';
    wrap.classList.add('hidden');
    zone.style.display = '';
    hideResults();
  });
});

// ── Text input ───────────────────────────────────────────
const textInput  = document.getElementById('text-input');
const charCount  = document.getElementById('char-count');
const btnClearTx = document.getElementById('btn-clear-text');

textInput.addEventListener('input', () => {
  const n = textInput.value.length;
  charCount.textContent = `${n.toLocaleString()} character${n !== 1 ? 's' : ''}`;
});
btnClearTx.addEventListener('click', () => {
  textInput.value = '';
  charCount.textContent = '0 characters';
  hideResults();
});

// ── Analyse buttons ──────────────────────────────────────
document.getElementById('btn-image').addEventListener('click', () => {
  const file = document.getElementById('file-image').files[0];
  if (!file) { showError('Please select an image first.'); return; }
  uploadFile('/api/detect/image', file);
});

document.getElementById('btn-video').addEventListener('click', () => {
  const file = document.getElementById('file-video').files[0];
  if (!file) { showError('Please select a video first.'); return; }
  uploadFile('/api/detect/video', file);
});

document.getElementById('btn-audio').addEventListener('click', () => {
  const file = document.getElementById('file-audio').files[0];
  if (!file) { showError('Please select an audio file first.'); return; }
  uploadFile('/api/detect/audio', file);
});

document.getElementById('btn-text').addEventListener('click', () => {
  const text = textInput.value.trim();
  if (!text) { showError('Please enter some text first.'); return; }
  sendText('/api/detect/text', text);
});

// ── API calls ────────────────────────────────────────────
async function uploadFile(endpoint, file) {
  showSpinner(true);
  hideResults();
  try {
    const form = new FormData();
    form.append('file', file);
    const resp = await fetch(endpoint, { method: 'POST', body: form });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    const data = await resp.json();
    renderResult(data);
  } catch (e) {
    showError(e.message);
  } finally {
    showSpinner(false);
  }
}

async function sendText(endpoint, text) {
  showSpinner(true);
  hideResults();
  try {
    const resp = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    const data = await resp.json();
    renderResult(data);
  } catch (e) {
    showError(e.message);
  } finally {
    showSpinner(false);
  }
}

// ── Render results ───────────────────────────────────────
function renderResult(data) {
  const area       = document.getElementById('results-area');
  const verdict    = document.getElementById('result-verdict');
  const confBar    = document.getElementById('conf-bar');
  const confPct    = document.getElementById('conf-pct');
  const flagsList  = document.getElementById('result-flags');
  const detailGrid = document.getElementById('result-details');

  const label = data.label || 'UNKNOWN';
  const conf  = parseFloat(data.confidence) || 0;

  // Verdict badge
  verdict.className = `verdict ${label}`;
  const icons = { FAKE: '⛔', SUSPICIOUS: '⚠️', REAL: '✅', ERROR: '❌', INSUFFICIENT_DATA: 'ℹ️' };
  verdict.textContent = `${icons[label] || '?'} ${label}`;

  // Confidence bar
  confBar.className = `conf-bar ${label}`;
  confPct.textContent = `${conf.toFixed(1)} %`;
  setTimeout(() => { confBar.style.width = `${Math.min(conf, 100)}%`; }, 50);

  // Flags
  flagsList.innerHTML = '';
  (data.flags || []).forEach(flag => {
    const el = document.createElement('span');
    el.className = 'flag-item';
    el.textContent = `⚠ ${flag}`;
    flagsList.appendChild(el);
  });

  // Detail cards
  detailGrid.innerHTML = '';
  const details = data.details || {};
  Object.entries(details).forEach(([key, value]) => {
    const card  = document.createElement('div');
    card.className = 'detail-card';
    const lbl   = document.createElement('div');
    lbl.className = 'detail-label';
    lbl.textContent = key.replace(/_/g, ' ');
    const val   = document.createElement('div');
    val.className = 'detail-value';
    val.textContent = typeof value === 'number' ? value.toFixed(4) : value;
    card.appendChild(lbl); card.appendChild(val);
    detailGrid.appendChild(card);
  });

  area.classList.remove('hidden');
  area.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ── UI helpers ───────────────────────────────────────────
function showSpinner(show) {
  document.getElementById('spinner').classList.toggle('hidden', !show);
}
function hideResults() {
  document.getElementById('results-area').classList.add('hidden');
}
function showError(msg) {
  renderResult({
    label: 'ERROR',
    confidence: 0,
    score: 0,
    flags: [msg],
    details: {}
  });
}
