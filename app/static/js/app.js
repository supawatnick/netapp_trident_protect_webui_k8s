// Trident Protect Web UI — shared utilities

function stateBadge(state) {
  const s = (state || 'Unknown').toLowerCase();
  if (s === 'protected') return '<span class="badge protected">PROTECTED</span>';
  if (s === 'partial') return '<span class="badge partial">PARTIAL</span>';
  if (s === 'none' || s === 'not protected' || s === 'unprotected') return '<span class="badge none">NONE</span>';
  if (s === 'completed' || s === 'success') return '<span class="badge success">COMPLETED</span>';
  if (s === 'failed' || s === 'error') return '<span class="badge error">FAILED</span>';
  if (s === 'running' || s === 'inprogress' || s === 'pending' || s === '') return '<span class="badge pending">RUNNING</span>';
  return `<span class="badge info">${state}</span>`;
}

function toast(message, kind) {
  const c = document.getElementById('toast-container');
  if (!c) return;
  const el = document.createElement('div');
  el.className = `toast ${kind || ''}`;
  el.textContent = message;
  c.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

function fmtBytes(b) {
  if (!b) return '—';
  const u = ['B','KB','MB','GB','TB'];
  let s = b;
  for (const x of u) { if (s < 1024) return s.toFixed(1)+' '+x; s /= 1024; }
  return s.toFixed(1)+' PB';
}

async function populateNsDropdown(id) {
  const sel = document.getElementById(id);
  try {
    const res = await fetch('/api/namespaces');
    const data = await res.json();
    const ns = (data.items || data.namespaces || []).map(i => typeof i === 'string' ? i : i.name);
    sel.innerHTML = ns.map(n => `<option value="${n}">${n}</option>`).join('');
  } catch (e) {
    sel.innerHTML = '<option value="">Failed to load</option>';
  }
}
