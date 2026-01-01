// Utility functions for the Textile ERP application

// Show loading overlay
function showLoading() {
    document.getElementById('loading-overlay').classList.remove('hidden');
    document.getElementById('loading-overlay').classList.add('flex');
}

// Hide loading overlay
function hideLoading() {
    document.getElementById('loading-overlay').classList.add('hidden');
    document.getElementById('loading-overlay').classList.remove('flex');
}

// Show toast notification
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    
    const bgColor = {
        'success': 'bg-green-500',
        'error': 'bg-red-500',
        'warning': 'bg-yellow-500',
        'info': 'bg-blue-500'
    }[type] || 'bg-blue-500';
    
    toast.className = `${bgColor} text-white px-6 py-3 rounded-lg shadow-lg transform transition-all duration-300 translate-x-full`;
    toast.innerHTML = `
        <div class="flex items-center justify-between">
            <span>${message}</span>
            <button onclick="this.parentElement.parentElement.remove()" class="ml-4 text-white hover:text-gray-200">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                </svg>
            </button>
        </div>
    `;
    
    container.appendChild(toast);
    
    // Animate in
    setTimeout(() => {
        toast.classList.remove('translate-x-full');
    }, 100);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        toast.classList.add('translate-x-full');
        setTimeout(() => {
            if (toast.parentElement) {
                toast.remove();
            }
        }, 300);
    }, 5000);
}

// Format currency
function formatCurrency(amount) {
    return new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency: 'INR'
    }).format(amount);
}

// Format number with commas
function formatNumber(num) {
    return new Intl.NumberFormat('en-IN').format(num);
}

// Auto-calculate totals in forms
function calculateTotals() {
    const rows = document.querySelectorAll('.item-row');
    let grandTotal = 0;
    
    rows.forEach(row => {
        const boxes = parseFloat(row.querySelector('.boxes')?.value || 0);
        const metersPerBox = parseFloat(row.querySelector('.meters-per-box')?.value || 0);
        const rate = parseFloat(row.querySelector('.rate')?.value || 0);
        
        const totalMeters = boxes * metersPerBox;
        const amount = totalMeters * rate;
        
        const totalMetersField = row.querySelector('.total-meters');
        const amountField = row.querySelector('.amount');
        
        if (totalMetersField) totalMetersField.value = totalMeters.toFixed(2);
        if (amountField) amountField.value = amount.toFixed(2);
        
        grandTotal += amount;
    });
    
    const grandTotalField = document.getElementById('grand-total');
    if (grandTotalField) {
        grandTotalField.textContent = formatCurrency(grandTotal);
    }
}

// Add new row to item table
function addItemRow() {
    const tbody = document.querySelector('#items-table tbody');
    const rowCount = tbody.children.length;
    
    const newRow = document.createElement('tr');
    newRow.className = 'item-row';
    newRow.innerHTML = `
        <td class="px-4 py-2">
            <input type="text" name="items[${rowCount}][quality]" class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="Quality/Type">
        </td>
        <td class="px-4 py-2">
            <input type="number" name="items[${rowCount}][boxes]" class="boxes w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="0" onchange="calculateTotals()">
        </td>
        <td class="px-4 py-2">
            <input type="number" step="0.01" name="items[${rowCount}][meters_per_box]" class="meters-per-box w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="0.00" onchange="calculateTotals()">
        </td>
        <td class="px-4 py-2">
            <input type="number" step="0.01" name="items[${rowCount}][total_meters]" class="total-meters w-full px-3 py-2 border border-gray-300 rounded-md bg-gray-50" readonly>
        </td>
        <td class="px-4 py-2">
            <input type="number" step="0.01" name="items[${rowCount}][rate_per_meter]" class="rate w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" placeholder="0.00" onchange="calculateTotals()">
        </td>
        <td class="px-4 py-2">
            <input type="number" step="0.01" name="items[${rowCount}][amount]" class="amount w-full px-3 py-2 border border-gray-300 rounded-md bg-gray-50" readonly>
        </td>
        <td class="px-4 py-2">
            <button type="button" onclick="this.closest('tr').remove(); calculateTotals();" class="text-red-600 hover:text-red-800">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                </svg>
            </button>
        </td>
    `;
    
    tbody.appendChild(newRow);
}

// Initialize date pickers
document.addEventListener('DOMContentLoaded', function() {
    // Initialize Flatpickr for date inputs
    flatpickr('.date-picker', {
        dateFormat: 'Y-m-d',
        defaultDate: 'today'
    });
    
    // Initialize auto-calculation for existing rows
    calculateTotals();
});

// Party search functionality
function initPartySearch(inputId, resultsId) {
    const input = document.getElementById(inputId);
    const results = document.getElementById(resultsId);
    
    if (!input || !results) return;
    
    let timeout;
    
    input.addEventListener('input', function() {
        clearTimeout(timeout);
        const query = this.value.trim();
        
        if (query.length < 2) {
            results.classList.add('hidden');
            return;
        }
        
        timeout = setTimeout(async () => {
            try {
                const response = await fetch(`/api/parties/search?q=${encodeURIComponent(query)}`);
                const parties = await response.json();
                
                results.innerHTML = '';
                
                if (parties.length === 0) {
                    results.innerHTML = '<div class="px-4 py-2 text-gray-500">No parties found</div>';
                } else {
                    parties.forEach(party => {
                        const div = document.createElement('div');
                        div.className = 'px-4 py-2 hover:bg-gray-100 cursor-pointer';
                        div.innerHTML = `
                            <div class="font-medium">${party.name}</div>
                            <div class="text-sm text-gray-500">${party.party_type} • ${party.contact.phone}</div>
                        `;
                        div.addEventListener('click', () => {
                            input.value = party.name;
                            input.dataset.partyId = party.id;
                            results.classList.add('hidden');
                        });
                        results.appendChild(div);
                    });
                }
                
                results.classList.remove('hidden');
            } catch (error) {
                console.error('Error searching parties:', error);
            }
        }, 300);
    });
    
    // Hide results when clicking outside
    document.addEventListener('click', function(e) {
        if (!input.contains(e.target) && !results.contains(e.target)) {
            results.classList.add('hidden');
        }
    });
}