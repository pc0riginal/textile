/**
 * GST Verification Module
 * Handles captcha fetching and GSTIN verification
 */

class GSTVerification {
    constructor() {
        this.captchaImage = null;
        this.captchaCookie = null;
    }

    /**
     * Fetch captcha from GST portal
     */
    async fetchCaptcha() {
        try {
            const response = await fetch('/gst/api/captcha', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            const result = await response.json();

            if (result.success) {
                this.captchaImage = result.captcha_image;
                this.captchaCookie = result.captcha_cookie;
                return result;
            } else {
                throw new Error(result.error || 'Failed to fetch captcha');
            }
        } catch (error) {
            console.error('Error fetching captcha:', error);
            throw error;
        }
    }

    /**
     * Verify GSTIN with captcha
     */
    async verifyGSTIN(gstin, captcha) {
        if (!this.captchaCookie) {
            throw new Error('Please fetch captcha first');
        }

        try {
            const formData = new FormData();
            formData.append('gstin', gstin);
            formData.append('captcha', captcha);
            formData.append('captcha_cookie', this.captchaCookie);

            const response = await fetch('/gst/api/verify', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();
            return result;
        } catch (error) {
            console.error('Error verifying GSTIN:', error);
            throw error;
        }
    }

    /**
     * Validate GSTIN format (client-side)
     */
    async validateFormat(gstin) {
        try {
            const formData = new FormData();
            formData.append('gstin', gstin);

            const response = await fetch('/gst/api/validate-format', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();
            return result;
        } catch (error) {
            console.error('Error validating GSTIN format:', error);
            throw error;
        }
    }

    /**
     * Show GST verification modal
     */
    showVerificationModal(gstin, onSuccess) {
        // Create modal HTML
        const modalHTML = `
            <div id="gstVerificationModal" class="fixed inset-0 overflow-y-auto h-full w-full z-50 flex items-center justify-center p-4" style="backdrop-filter: blur(4px); -webkit-backdrop-filter: blur(4px);">
                <div class="relative mx-auto p-6 border w-full max-w-md shadow-2xl rounded-lg bg-white">
                    <div class="space-y-4">
                        <!-- Header -->
                        <div class="flex items-center justify-between border-b pb-3">
                            <h3 class="text-xl font-semibold text-gray-900">Verify GST Number</h3>
                            <button id="closeModalBtn" class="text-gray-400 hover:text-gray-600 transition-colors">
                                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                                </svg>
                            </button>
                        </div>
                        
                        <!-- GSTIN Display -->
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">GSTIN</label>
                            <input type="text" id="gstinInput" value="${gstin}" readonly
                                class="w-full px-4 py-2.5 border border-gray-300 rounded-lg bg-gray-50 text-gray-700 font-mono text-sm">
                        </div>

                        <!-- Captcha Section -->
                        <div>
                            <div class="flex items-center justify-between mb-2">
                                <label class="block text-sm font-medium text-gray-700">Captcha Code</label>
                                <button id="refreshCaptchaBtn" class="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1 transition-colors">
                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path>
                                    </svg>
                                    Refresh
                                </button>
                            </div>
                            
                            <!-- Captcha Image Container -->
                            <div id="captchaContainer" class="mb-3 flex justify-center items-center bg-white border-2 border-gray-300 rounded-lg p-6 min-h-[120px]">
                                <div class="flex items-center gap-2 text-gray-500">
                                    <svg class="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
                                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                    </svg>
                                    <span>Loading captcha...</span>
                                </div>
                            </div>
                            
                            <!-- Captcha Input -->
                            <input type="text" id="captchaInput" placeholder="Enter 6-digit captcha code" maxlength="6"
                                class="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-center text-lg font-mono tracking-widest">
                            <p class="mt-1 text-xs text-gray-500">Enter the 6-digit code shown in the image above</p>
                        </div>

                        <!-- Messages -->
                        <div id="errorMessage" class="hidden p-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg flex items-start gap-2">
                            <svg class="w-5 h-5 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
                            </svg>
                            <span id="errorText"></span>
                        </div>
                        
                        <div id="successMessage" class="hidden p-3 bg-green-50 border border-green-200 text-green-700 text-sm rounded-lg flex items-start gap-2">
                            <svg class="w-5 h-5 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
                            </svg>
                            <span id="successText"></span>
                        </div>

                        <!-- Action Buttons -->
                        <div class="flex gap-3 pt-2">
                            <button id="verifyBtn" class="flex-1 bg-blue-600 text-white px-6 py-2.5 rounded-lg hover:bg-blue-700 focus:ring-4 focus:ring-blue-300 font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
                                Verify GST
                            </button>
                            <button id="cancelBtn" class="px-6 py-2.5 border border-gray-300 rounded-lg hover:bg-gray-50 font-medium transition-colors">
                                Cancel
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Add modal to body
        document.body.insertAdjacentHTML('beforeend', modalHTML);

        // Get elements
        const modal = document.getElementById('gstVerificationModal');
        const captchaContainer = document.getElementById('captchaContainer');
        const captchaInput = document.getElementById('captchaInput');
        const verifyBtn = document.getElementById('verifyBtn');
        const refreshBtn = document.getElementById('refreshCaptchaBtn');
        const closeBtn = document.getElementById('closeModalBtn');
        const cancelBtn = document.getElementById('cancelBtn');
        const errorMsg = document.getElementById('errorMessage');
        const errorText = document.getElementById('errorText');
        const successMsg = document.getElementById('successMessage');
        const successText = document.getElementById('successText');

        // Load captcha
        const loadCaptcha = async () => {
            try {
                captchaContainer.innerHTML = `
                    <div class="flex items-center gap-2 text-gray-500">
                        <svg class="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        <span>Loading...</span>
                    </div>
                `;
                
                const result = await this.fetchCaptcha();
                
                captchaContainer.innerHTML = `
                    <img src="${result.captcha_image}" 
                         alt="Captcha" 
                         class="border-2 border-gray-300 rounded-lg shadow-sm mx-auto"
                         style="width: 280px; height: auto; image-rendering: crisp-edges;">
                `;
                
                captchaInput.value = '';
                captchaInput.focus();
                errorMsg.classList.add('hidden');
            } catch (error) {
                console.error('Captcha load error:', error);
                captchaContainer.innerHTML = `
                    <div class="text-red-500 text-center">
                        <svg class="w-12 h-12 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                        </svg>
                        <p class="text-sm">Failed to load captcha</p>
                        <button class="mt-2 text-blue-600 hover:text-blue-800 text-sm underline" onclick="this.closest('#gstVerificationModal').remove()">Close and try again</button>
                    </div>
                `;
                errorText.textContent = error.message || 'Failed to load captcha. Please try again.';
                errorMsg.classList.remove('hidden');
            }
        };

        // Verify GSTIN
        const verify = async () => {
            const captcha = captchaInput.value.trim();
            if (!captcha) {
                errorText.textContent = 'Please enter the captcha code';
                errorMsg.classList.remove('hidden');
                captchaInput.focus();
                return;
            }

            if (captcha.length !== 6 || !/^\d+$/.test(captcha)) {
                errorText.textContent = 'Captcha must be exactly 6 digits';
                errorMsg.classList.remove('hidden');
                captchaInput.focus();
                return;
            }

            try {
                verifyBtn.disabled = true;
                verifyBtn.innerHTML = `
                    <span class="flex items-center justify-center gap-2">
                        <svg class="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        Verifying...
                    </span>
                `;
                errorMsg.classList.add('hidden');
                successMsg.classList.add('hidden');

                const result = await this.verifyGSTIN(gstin, captcha);

                if (result.success) {
                    successText.textContent = 'GST verified successfully! Auto-filling form...';
                    successMsg.classList.remove('hidden');
                    
                    // Call success callback with data
                    if (onSuccess) {
                        onSuccess(result.data);
                    }

                    // Close modal after 1.5 seconds
                    setTimeout(() => {
                        modal.remove();
                    }, 1500);
                } else {
                    errorText.textContent = result.error || 'Verification failed';
                    errorMsg.classList.remove('hidden');
                    
                    // Only refresh captcha if it's a captcha error, not GST error
                    const isCaptchaError = result.error && (
                        result.error.toLowerCase().includes('captcha') ||
                        result.error.toLowerCase().includes('invalid captcha')
                    );
                    
                    if (isCaptchaError) {
                        // Refresh captcha for captcha errors
                        await loadCaptcha();
                    } else {
                        // For GST errors, just clear the captcha input and keep the same image
                        captchaInput.value = '';
                        captchaInput.focus();
                    }
                }
            } catch (error) {
                errorText.textContent = error.message;
                errorMsg.classList.remove('hidden');
                await loadCaptcha();
            } finally {
                verifyBtn.disabled = false;
                verifyBtn.textContent = 'Verify GST';
            }
        };

        // Event listeners
        refreshBtn.addEventListener('click', (e) => {
            e.preventDefault();
            loadCaptcha();
        });
        closeBtn.addEventListener('click', (e) => {
            e.preventDefault();
            modal.remove();
        });
        cancelBtn.addEventListener('click', (e) => {
            e.preventDefault();
            modal.remove();
        });
        verifyBtn.addEventListener('click', (e) => {
            e.preventDefault();
            verify();
        });
        captchaInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                verify();
            }
        });
        
        // Auto-format captcha input (only allow digits)
        captchaInput.addEventListener('input', (e) => {
            e.target.value = e.target.value.replace(/\D/g, '').slice(0, 6);
        });
        
        // Allow ESC key to close modal
        document.addEventListener('keydown', function escHandler(e) {
            if (e.key === 'Escape') {
                modal.remove();
                document.removeEventListener('keydown', escHandler);
            }
        });

        // Initial load
        loadCaptcha();
    }
}

// Export for use in other scripts
window.GSTVerification = GSTVerification;
