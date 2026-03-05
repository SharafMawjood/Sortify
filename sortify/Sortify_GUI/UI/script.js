document.addEventListener('DOMContentLoaded', () => {
    const sortForm = document.getElementById('sortForm');
    const modeRadios = document.querySelectorAll('input[name="mode"]');
    const customTargetGroup = document.getElementById('custom_target_group');
    const customTargetInput = document.getElementById('custom_target');
    const flattenGroup = document.getElementById('flatten_group');
    const flattenCheckbox = document.getElementById('flatten');
    const submitBtn = document.getElementById('submitBtn');
    
    const resultsSection = document.getElementById('results');
    const resultMessage = document.getElementById('resultMessage');
    const resultCount = document.getElementById('resultCount');
    const logContainer = document.getElementById('logContainer');

    // Toggle logic for custom destination input
    modeRadios.forEach(radio => {
        radio.addEventListener('change', (e) => {
            const mode = e.target.value;
            
            if (mode === 'custom' || mode === 'revert') {
                customTargetGroup.classList.remove('hidden');
                customTargetInput.required = true;
                
                if (mode === 'revert') {
                    flattenGroup.classList.add('hidden');
                    flattenCheckbox.checked = false;
                } else {
                    flattenGroup.classList.remove('hidden');
                }
            } else {
                customTargetGroup.classList.add('hidden');
                customTargetInput.required = false;
                customTargetInput.value = '';
                flattenGroup.classList.remove('hidden');
            }
        });
    });

    sortForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        // Reset results UI
        resultsSection.classList.add('hidden');
        resultMessage.className = 'result-message';
        resultMessage.textContent = '';
        logContainer.innerHTML = '';
        resultCount.textContent = '';
        
        const targetDir = document.getElementById('target_dir').value;
        const mode = document.querySelector('input[name="mode"]:checked').value;
        const customTarget = document.getElementById('custom_target').value;
        const flatten = document.getElementById('flatten').checked;
        
        // Basic validation
        if (!targetDir) return;
        if ((mode === 'custom' || mode === 'revert') && !customTarget) {
            showError("Destination path is required for this mode.");
            return;
        }

        // Set Loading state
        setLoadingState(true);

        try {
            // Call Python function via Eel
            const data = await eel.api_sort(targetDir, mode, customTarget, flatten)();

            if (data.error) {
                throw new Error(data.error);
            }

            showSuccess(data.message, data.moved_count);
            renderLogs(data.logs);

        } catch (error) {
            showError(error.message);
        } finally {
            setLoadingState(false);
        }
    });

    function setLoadingState(isLoading) {
        if (isLoading) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = `
                <svg class="btn-icon" style="animation: spin 1s linear infinite;" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"></path></svg>
                <span>Processing...</span>
            `;
        } else {
            submitBtn.disabled = false;
            submitBtn.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="btn-icon"><path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242"></path><path d="m8 17 4 4 4-4"></path><path d="M12 13v8"></path></svg>
                <span>Sort Files</span>
            `;
        }
    }

    function showSuccess(message, count) {
        resultsSection.classList.remove('hidden');
        resultMessage.className = 'result-message success';
        resultMessage.textContent = message;
        resultCount.textContent = `${count} item(s)`;
    }

    function showError(message) {
        resultsSection.classList.remove('hidden');
        resultMessage.className = 'result-message error';
        resultMessage.textContent = `Error: ${message}`;
        resultCount.textContent = '0 item(s)';
    }

    function renderLogs(logs) {
        if (!logs || logs.length === 0) {
            logContainer.innerHTML = '<div class="log-entry"><span class="log-details">No items were moved.</span></div>';
            return;
        }

        const fragment = document.createDocumentFragment();

        logs.forEach(log => {
            const entry = document.createElement('div');
            entry.className = 'log-entry';
            
            const statusStr = log.success ? '✓ SUCCESS' : '✗ ERROR';
            const statusClass = log.success ? 'success' : 'error';
            
            let detailStr = '';
            if (log.success) {
                const actionBadge = log.action || log.category || 'Moved';
                detailStr = `<span class="log-filename">${log.name}</span> → [${actionBadge}] ${log.dest}`;
            } else {
                detailStr = `<span class="log-filename">${log.name}</span> → ${log.error || 'Unknown error'}`;
            }

            entry.innerHTML = `
                <div class="log-status ${statusClass}">${statusStr}</div>
                <div class="log-details">${detailStr}</div>
            `;
            
            fragment.appendChild(entry);
        });

        logContainer.appendChild(fragment);
    }
});
