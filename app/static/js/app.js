// ── Textile ERP — Core UI Utilities ──────────────────────────────────────────

// ── Toast Notifications ─────────────────────────────────────────────────────
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');

    const styles = {
        success: { bg: 'bg-green-600', icon: '✓' },
        error:   { bg: 'bg-red-600',   icon: '✕' },
        warning: { bg: 'bg-amber-500',  icon: '⚠' },
        info:    { bg: 'bg-blue-600',   icon: 'ℹ' },
    };
    const s = styles[type] || styles.info;

    toast.className = `${s.bg} text-white pl-4 pr-3 py-3 rounded-lg shadow-lg flex items-center gap-3 min-w-[280px] max-w-sm transform transition-all duration-300 translate-x-[120%] opacity-0`;
    toast.innerHTML = `
        <span class="text-lg leading-none">${s.icon}</span>
        <span class="flex-1 text-sm">${message}</span>
        <button onclick="this.closest('.toast-item').remove()" class="text-white/70 hover:text-white ml-1">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
        </button>`;
    toast.classList.add('toast-item');
    container.appendChild(toast);

    requestAnimationFrame(() => {
        toast.classList.remove('translate-x-[120%]', 'opacity-0');
    });

    setTimeout(() => {
        toast.classList.add('translate-x-[120%]', 'opacity-0');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ── Confirm Dialog (replaces browser confirm()) ─────────────────────────────
function showConfirm(message, { title = 'Confirm', confirmText = 'Yes, proceed', cancelText = 'Cancel', danger = false } = {}) {
    return new Promise((resolve) => {
        const overlay = document.getElementById('confirm-overlay');
        document.getElementById('confirm-title').textContent = title;
        document.getElementById('confirm-message').textContent = message;
        const btn = document.getElementById('confirm-yes');
        btn.textContent = confirmText;
        btn.className = `px-4 py-2 text-sm font-medium text-white rounded-lg ${danger ? 'bg-red-600 hover:bg-red-700' : 'bg-blue-600 hover:bg-blue-700'}`;
        document.getElementById('confirm-cancel').textContent = cancelText;

        function cleanup(result) {
            overlay.classList.add('hidden');
            btn.removeEventListener('click', onYes);
            document.getElementById('confirm-cancel').removeEventListener('click', onNo);
            resolve(result);
        }
        function onYes() { cleanup(true); }
        function onNo()  { cleanup(false); }

        btn.addEventListener('click', onYes);
        document.getElementById('confirm-cancel').addEventListener('click', onNo);
        overlay.classList.remove('hidden');
    });
}

// ── Loading Overlay ─────────────────────────────────────────────────────────
function showLoading() {
    const el = document.getElementById('loading-overlay');
    el.classList.remove('hidden');
    el.classList.add('flex');
}
function hideLoading() {
    const el = document.getElementById('loading-overlay');
    el.classList.add('hidden');
    el.classList.remove('flex');
}

// ── Format Helpers ──────────────────────────────────────────────────────────
function formatCurrency(amount) {
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(amount);
}
function formatNumber(num) {
    return new Intl.NumberFormat('en-IN').format(num);
}
