/* ── Time formatting ──────────────────────────────────────── */
function timeAgo(dateStr) {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now - date;
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);

  if (diffSec < 60) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  if (diffDay < 7) return `${diffDay}d ago`;
  return date.toLocaleDateString();
}

/* ── API helpers ────────────────────────────────────────────── */
async function apiGet(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return res.json();
}

async function apiPost(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`);
  return res.json();
}

/* ── Loading state helper ───────────────────────────────────── */
async function withLoading(loadingRef, fn) {
  if (loadingRef !== undefined) loadingRef.value = true;
  try {
    return await fn();
  } finally {
    if (loadingRef !== undefined) loadingRef.value = false;
  }
}

/* ── Toast notification system ──────────────────────────────── */
function showToast(message, type = 'success', duration = 4000) {
  const existing = document.getElementById('toast-container');
  let container = existing;
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'fixed top-4 right-4 z-[100] flex flex-col gap-2 max-w-sm';
    document.body.appendChild(container);
  }

  const colors = {
    success: 'bg-green-900/80 border-green-700 text-green-200',
    error: 'bg-red-900/80 border-red-700 text-red-200',
    warning: 'bg-yellow-900/80 border-yellow-700 text-yellow-200',
    info: 'bg-blue-900/80 border-blue-700 text-blue-200',
  };
  const icons = {
    success: '✅',
    error: '❌',
    warning: '⚠️',
    info: 'ℹ️',
  };

  const toast = document.createElement('div');
  toast.className = `toast flex items-start gap-3 px-4 py-3 rounded-lg border backdrop-blur-sm shadow-lg ${colors[type] || colors.info}`;
  toast.innerHTML = `
    <span class="text-base flex-shrink-0 mt-0.5">${icons[type] || 'ℹ️'}</span>
    <span class="text-sm flex-1">${message}</span>
    <button onclick="this.closest('.toast').classList.add('toast-exit'); setTimeout(() => this.closest('.toast').remove(), 300)" class="text-sm opacity-60 hover:opacity-100 flex-shrink-0">✕</button>
  `;

  container.appendChild(toast);

  // Auto-dismiss
  setTimeout(() => {
    if (toast.isConnected) {
      toast.classList.add('toast-exit');
      setTimeout(() => toast.remove(), 300);
    }
  }, duration);
}

/* ── Animated number counter ───────────────────────────────── */
function animateValue(el, start, end, duration = 800) {
  if (!el) return;
  const startTime = performance.now();
  const isFloat = end % 1 !== 0;

  function update(currentTime) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);
    // Ease-out cubic
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = start + (end - start) * eased;

    if (isFloat) {
      el.textContent = current.toFixed(1);
    } else {
      el.textContent = Math.round(current);
    }

    if (progress < 1) {
      requestAnimationFrame(update);
    }
  }

  requestAnimationFrame(update);
}

/* ── Confirmation dialog ────────────────────────────────────── */
function confirmAction(message, confirmText = 'Confirm', cancelText = 'Cancel') {
  return new Promise((resolve) => {
    const existing = document.getElementById('confirm-dialog');
    if (existing) existing.remove();

    const backdrop = document.createElement('div');
    backdrop.id = 'confirm-dialog';
    backdrop.className = 'fixed inset-0 z-[90] flex items-center justify-center p-4';
    backdrop.innerHTML = `
      <div class="absolute inset-0 bg-black/60" onclick="document.getElementById('confirm-dialog').remove()"></div>
      <div class="relative bg-slate-800 rounded-xl border border-slate-700 p-6 max-w-sm w-full shadow-2xl">
        <p class="text-sm text-slate-200 mb-4">${message}</p>
        <div class="flex gap-3 justify-end">
          <button class="confirm-cancel px-4 py-2 text-sm text-slate-400 hover:text-slate-200 bg-slate-700/50 hover:bg-slate-700 rounded-lg transition-colors">${cancelText}</button>
          <button class="confirm-ok px-4 py-2 text-sm text-white bg-cyan-600 hover:bg-cyan-500 rounded-lg transition-colors">${confirmText}</button>
        </div>
      </div>
    `;

    document.body.appendChild(backdrop);

    backdrop.querySelector('.confirm-ok').addEventListener('click', () => {
      backdrop.remove();
      resolve(true);
    });
    backdrop.querySelector('.confirm-cancel').addEventListener('click', () => {
      backdrop.remove();
      resolve(false);
    });
  });
}
