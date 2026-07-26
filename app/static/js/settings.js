// Settings page logic

let currentProfiles = {};
let currentActive = '';
let editingProfile = null;
let loggingInProfile = null;
let fullToken = null;
let detectedPlatform = 'unknown';

async function loadSettings() {
  try {
    const [settingsRes, platformRes] = await Promise.all([
      fetch('/api/settings'),
      fetch('/api/platform'),
    ]);
    const data = await settingsRes.json();
    const platformData = await platformRes.json();
    currentProfiles = data.profiles || {};
    currentActive = data.active || '';
    detectedPlatform = platformData.platform || 'unknown';

    // Populate whoami info
    document.getElementById('whoami-user').textContent = data.whoami?.user || '—';
    document.getElementById('whoami-server').textContent = data.whoami?.server || '—';
    document.getElementById('active-profile').textContent = currentActive || '(none)';

    // Display detected platform
    const platformEl = document.getElementById('detected-platform');
    const platformLabel = platformEl ? platformEl.parentElement : null;
    const cliName = platformData.cli || '';
    if (platformEl) {
      const badge = detectedPlatform === 'ocp' ? 'OCP' :
                     detectedPlatform === 'k8s' ? 'Kubernetes' :
                     'Unknown';
      const color = detectedPlatform === 'ocp' ? '#0066cc' :
                    detectedPlatform === 'k8s' ? '#7c3aed' :
                    '#999';
      platformEl.innerHTML = `<span style="color:${color};font-weight:600">${badge}</span>` +
        (cliName ? ` <span style="color:#999;font-size:12px">(${cliName})</span>` : '');
    }

    // Update cluster label based on platform
    const clusterLabel = document.getElementById('cluster-label');
    if (clusterLabel) {
      clusterLabel.textContent = detectedPlatform === 'ocp' ? 'OCP Cluster' :
                                  detectedPlatform === 'k8s' ? 'K8s Context' : 'Cluster';
    }

    // Show/hide OCP-specific help sections
    document.querySelectorAll('[id^="help-"]').forEach(el => {
      if (el.id === 'help-ocp') el.style.display = (detectedPlatform === 'ocp') ? '' : 'none';
      if (el.id === 'help-k8s') el.style.display = (detectedPlatform === 'k8s') ? '' : 'none';
    });

    // Show/hide password section in login form (OCP only)
    const passwordSection = document.getElementById('login-password-section');
    if (passwordSection) {
      passwordSection.style.display = (detectedPlatform === 'ocp') ? '' : 'none';
    }

    renderProfiles();
    loadClusterInfo();
  } catch (e) {
    toast('Failed to load settings: ' + e.message, 'error');
  }
}

async function loadClusterInfo() {
  try {
    const res = await fetch('/api/ocp-cluster');
    const info = await res.json();
    const el = document.getElementById('ocp-cluster-name');
    if (!info || !info.name) {
      el.textContent = '—';
      return;
    }
    let txt = info.name;
    if (info.platform) txt += ` <span style="color:#999;font-size:12px">(${info.platform})</span>`;
    if (info.version) txt += ` <span style="color:#999;font-size:12px">· v${info.version}</span>`;
    el.innerHTML = txt;
  } catch (e) {
    document.getElementById('ocp-cluster-name').textContent = '—';
  }
}

function renderProfiles() {
  const tbody = document.getElementById('profiles-tbody');
  const names = Object.keys(currentProfiles).sort();
  if (names.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty">No profiles. Click "+ Add Profile".</td></tr>';
    return;
  }
  tbody.innerHTML = names.map(name => {
    const p = currentProfiles[name];
    const isActive = name === currentActive;
    const platform = p.platform || '';
    const isK8s = platform === 'k8s';

    // Actions:
    // - k8s profiles: show Switch button (when not active) + Connected badge. No login needed.
    // - OCP profiles: show Login & Switch button.
    let actions;
    if (isK8s) {
      actions = (isActive
        ? `<span class="badge success">Connected (kubeconfig)</span>`
        : `<button class="btn small" onclick="switchToProfile('${escapeHtml(name)}')">Switch</button>
           <span class="badge success">Connected</span>`)
        + `<button class="btn small secondary" onclick="editProfile('${escapeHtml(name)}')">Edit</button>
           <button class="btn small danger" onclick="deleteProfile('${escapeHtml(name)}')"${isActive ? ' disabled' : ''}>Del</button>`;
    } else {
      actions = (isActive
        ? ''
        : `<button class="btn small" onclick="showLoginForm('${escapeHtml(name)}')">Login &amp; Switch</button>`)
        + `<button class="btn small secondary" onclick="editProfile('${escapeHtml(name)}')">Edit</button>
           <button class="btn small danger" onclick="deleteProfile('${escapeHtml(name)}')"${isActive ? ' disabled' : ''}>Del</button>`;
    }

    const platformBadge = platform
      ? ` <span class="badge" style="background:${platform === 'k8s' ? '#7c3aed' : '#0066cc'};color:#fff">${platform.toUpperCase()}</span>`
      : '';

    return `
      <tr${isActive ? ' style="background:#fffbea"' : ''}>
        <td><b>${escapeHtml(name)}</b>${isActive ? ' <span class="badge protected">ACTIVE</span>' : ''}${platformBadge}</td>
        <td class="text-mono">${escapeHtml(p.api_url || '')}</td>
        <td>${escapeHtml(p.appvault || 'ontap-s3-appvault')}/${escapeHtml(p.appvault_namespace || 'trident-protect')}</td>
        <td class="text-muted">${escapeHtml(p.description || '—')}</td>
        <td>${isActive ? '<span class="badge success">In use</span>' : '<span class="badge pending">Standby</span>'}</td>
        <td>${actions}</td>
      </tr>
    `;
  }).join('');
}

async function testConnection() {
  try {
    const res = await fetch('/api/settings/test', {method:'POST'});
    const r = await res.json();
    toast(r.ok ? 'Connection OK: ' + r.message : 'Failed: ' + r.message, r.ok ? 'success' : 'error');
  } catch (e) {
    toast('Test failed: ' + e.message, 'error');
  }
}

async function showFullToken() {
  if (fullToken) {
    prompt('Bearer Token (copy this):', fullToken);
    return;
  }
  try {
    const res = await fetch('/api/settings/token');
    const r = await res.json();
    if (r.ok) {
      fullToken = r.full;
      prompt('Bearer Token (copy this):', fullToken);
    } else {
      toast(r.message, 'error');
    }
  } catch (e) {
    toast('Failed: ' + e.message, 'error');
  }
}

function showAddForm() {
  editingProfile = null;
  document.getElementById('profile-form-title').textContent = 'Add Profile';
  document.getElementById('pf-name').value = '';
  document.getElementById('pf-name').disabled = false;
  document.getElementById('pf-description').value = '';
  document.getElementById('pf-api-url').value = 'https://';
  document.getElementById('pf-insecure').value = 'true';
  document.getElementById('pf-platform').value = '';
  document.getElementById('profile-form').style.display = 'block';
}

function editProfile(name) {
  const p = currentProfiles[name];
  if (!p) return;
  editingProfile = name;
  document.getElementById('profile-form-title').textContent = 'Edit Profile: ' + name;
  document.getElementById('pf-name').value = name;
  document.getElementById('pf-name').disabled = true;
  document.getElementById('pf-description').value = p.description || '';
  document.getElementById('pf-api-url').value = p.api_url || '';
  document.getElementById('pf-insecure').value = p.insecure_skip_tls ? 'true' : 'false';
  document.getElementById('pf-platform').value = p.platform || '';
  document.getElementById('profile-form').style.display = 'block';
}

function hideProfileForm() {
  document.getElementById('profile-form').style.display = 'none';
  editingProfile = null;
}

async function saveProfile() {
  const body = {
    name: document.getElementById('pf-name').value.trim(),
    description: document.getElementById('pf-description').value.trim(),
    api_url: document.getElementById('pf-api-url').value.trim(),
    insecure_skip_tls: document.getElementById('pf-insecure').value === 'true',
    platform: document.getElementById('pf-platform').value || '',
  };
  if (!body.name || !body.api_url) {
    toast('Name and API URL are required', 'error');
    return;
  }
  try {
    const res = await fetch('/api/settings/profile', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(body),
    });
    const r = await res.json();
    toast(r.message, r.ok ? 'success' : 'error');
    if (r.ok) {
      hideProfileForm();
      await loadSettings();
    }
  } catch (e) {
    toast('Save failed: ' + e.message, 'error');
  }
}

async function deleteProfile(name) {
  if (!confirm(`Delete profile "${name}"?`)) return;
  try {
    const res = await fetch(`/api/settings/profile/${encodeURIComponent(name)}`, {method:'DELETE'});
    const r = await res.json();
    toast(r.message, r.ok ? 'success' : 'error');
    if (r.ok) await loadSettings();
  } catch (e) {
    toast('Delete failed: ' + e.message, 'error');
  }
}

function showLoginForm(name) {
  loggingInProfile = name;
  document.getElementById('login-profile-name').textContent = name;
  document.getElementById('login-token').value = '';
  document.getElementById('login-username').value = '';
  document.getElementById('login-password').value = '';
  document.getElementById('login-form').style.display = 'block';
}

function hideLoginForm() {
  document.getElementById('login-form').style.display = 'none';
  loggingInProfile = null;
}

async function switchToProfile(name) {
  try {
    const res = await fetch('/api/settings/switch', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name}),
    });
    const r = await res.json();
    toast(r.message, r.ok ? 'success' : 'error');
    if (r.ok) {
      await loadSettings();
      await testConnection();
    }
  } catch (e) {
    toast('Switch failed: ' + e.message, 'error');
  }
}

async function loginWithToken() {
  const token = document.getElementById('login-token').value.trim();
  if (!token) {
    toast('Token required', 'error');
    return;
  }
  await doLogin({name: loggingInProfile, token});
}

async function loginWithPassword() {
  const username = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password').value;
  if (!username || !password) {
    toast('Username and password required', 'error');
    return;
  }
  await doLogin({name: loggingInProfile, username, password});
}

async function doLogin(body) {
  try {
    const res = await fetch('/api/settings/login', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(body),
    });
    const r = await res.json();
    toast(r.message, r.ok ? 'success' : 'error');
    if (r.ok) {
      hideLoginForm();
      await loadSettings();
      await testConnection();
    }
  } catch (e) {
    toast('Login failed: ' + e.message, 'error');
  }
}

function escapeHtml(s) {
  if (s === null || s === undefined) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function toggleHelp() {
  const content = document.getElementById('help-content');
  const toggle = document.getElementById('help-toggle');
  if (content.style.display === 'none') {
    content.style.display = 'block';
    toggle.textContent = '▲';
  } else {
    content.style.display = 'none';
    toggle.textContent = '▼';
  }
}

function toggleKubeconfig() {
  const content = document.getElementById('kubeconfig-content');
  const toggle = document.getElementById('kubeconfig-toggle');
  if (content.style.display === 'none') {
    content.style.display = 'block';
    toggle.textContent = '▲';
  } else {
    content.style.display = 'none';
    toggle.textContent = '▼';
  }
}

function loadKubeconfigFile() {
  const fileInput = document.getElementById('kubeconfig-file');
  const file = fileInput.files[0];
  if (!file) {
    showKubeconfigMsg('Choose a kubeconfig file first', 'error');
    return;
  }
  const reader = new FileReader();
  reader.onload = (e) => {
    document.getElementById('kubeconfig-text').value = e.target.result;
    showKubeconfigMsg(`Loaded ${file.name} (${file.size} bytes)`, 'success');
  };
  reader.onerror = () => {
    showKubeconfigMsg('Failed to read file', 'error');
  };
  reader.readAsText(file);
}

function showKubeconfigMsg(text, kind) {
  const el = document.getElementById('kubeconfig-msg');
  el.textContent = text;
  el.style.color = kind === 'error' ? 'var(--color-error)' :
                   kind === 'success' ? 'var(--color-success)' :
                   'var(--color-text-muted, #666)';
  el.style.fontSize = '13px';
}

function showKubeconfigPreview(preview) {
  const el = document.getElementById('kubeconfig-preview');
  const lines = [
    `<b>Server:</b> <code>${escapeHtml(preview.server)}</code>`,
    `<b>User:</b> <code>${escapeHtml(preview.user)}</code>`,
    `<b>Context:</b> <code>${escapeHtml(preview.context)}</code>`,
    `<b>Profile created:</b> <code>${escapeHtml(preview.profile)}</code>`,
    `<b>TLS skip:</b> ${preview.insecure_skip_tls ? 'yes' : 'no'}`,
  ];
  el.innerHTML = lines.join('<br/>');
  el.style.display = 'block';
}

async function importKubeconfig() {
  const yaml = document.getElementById('kubeconfig-text').value.trim();
  if (!yaml) {
    showKubeconfigMsg('Paste or load a kubeconfig first', 'error');
    return;
  }

  const btn = event.target;
  btn.disabled = true;
  btn.textContent = 'Applying...';
  showKubeconfigMsg('Validating and writing kubeconfig...', 'info');

  try {
    const res = await fetch('/api/settings/kubeconfig', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({kubeconfig: yaml}),
    });
    const r = await res.json();
    if (r.ok) {
      showKubeconfigMsg(r.message, 'success');
      if (r.preview) showKubeconfigPreview(r.preview);
      loadSettings();
    } else {
      showKubeconfigMsg(r.message, 'error');
      document.getElementById('kubeconfig-preview').style.display = 'none';
    }
  } catch (e) {
    showKubeconfigMsg('Request failed: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Apply Kubeconfig';
  }
}

loadSettings();
