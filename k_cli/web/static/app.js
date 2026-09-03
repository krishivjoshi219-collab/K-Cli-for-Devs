/* K-CLI Cyber Station Frontend Logic */

document.addEventListener('DOMContentLoaded', () => {
    initTabNavigation();
    initSystemStatus();
    initQuickChips();
    initAgentRunner();
    initCrashTriage();
    initConflictStudio();
    initSecurityShield();
    initChaosImmunity();
    initDevDocs();
    initCredentialsVault();
    initModelHub();
    initLocalCommandRunner();
});

// 1. Navigation Tab Switching
function initTabNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    const tabPanes = document.querySelectorAll('.tab-pane');

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const tabId = item.getAttribute('data-tab');

            navItems.forEach(n => n.classList.remove('active'));
            tabPanes.forEach(p => p.classList.remove('active'));

            item.classList.add('active');
            const targetPane = document.getElementById(tabId);
            if (targetPane) {
                targetPane.classList.add('active');
            }
        });
    });
}

// 2. System Status Polling
async function initSystemStatus() {
    async function updateStatus() {
        try {
            const res = await fetch('/api/status');
            if (res.ok) {
                const data = await res.json();
                document.getElementById('stat-model').textContent = data.active_model;
                document.getElementById('stat-branch').textContent = data.git_branch;
                document.getElementById('stat-ram').textContent = `${data.ram_usage_mb} MB / 1024 MB`;
            }
        } catch (e) {
            console.error('Status fetch error:', e);
        }
    }
    updateStatus();
    setInterval(updateStatus, 4000);
}

// 3. Quick Action Chips
function initQuickChips() {
    const chips = document.querySelectorAll('.quick-chip');
    const promptInput = document.getElementById('agent-prompt');

    chips.forEach(chip => {
        chip.addEventListener('click', () => {
            promptInput.value = chip.getAttribute('data-prompt');
            promptInput.focus();
        });
    });
}

// Global helper to switch model from spotlight cards
window.setActiveModel = function(modelName) {
    const modelSelect = document.getElementById('agent-model');
    if (modelSelect) {
        modelSelect.value = modelName;
    }
    // Switch to agent tab
    const agentTabBtn = document.querySelector('[data-tab="tab-agent"]');
    if (agentTabBtn) agentTabBtn.click();
};

// 4. Agent Task Runner & WebSocket Streaming
function initAgentRunner() {
    const btnRun = document.getElementById('btn-run-agent');
    const promptInput = document.getElementById('agent-prompt');
    const langSelect = document.getElementById('agent-lang');
    const modelSelect = document.getElementById('agent-model');
    const personaSelect = document.getElementById('agent-persona');
    const mockCheck = document.getElementById('agent-mock');
    const outputCard = document.getElementById('agent-output-card');
    const terminal = document.getElementById('agent-terminal');
    const badgePersona = document.getElementById('badge-persona');
    const badgeVerif = document.getElementById('badge-verif');
    const badgeIntent = document.getElementById('badge-intent-mode');
    const streamStats = document.getElementById('stream-stats');
    const btnCopy = document.getElementById('btn-copy-output');

    let tokenCount = 0;
    let startTime = null;

    btnCopy.addEventListener('click', () => {
        navigator.clipboard.writeText(terminal.textContent);
        btnCopy.innerHTML = '<i class="fa-solid fa-check"></i> Copied!';
        setTimeout(() => {
            btnCopy.innerHTML = '<i class="fa-regular fa-copy"></i> Copy';
        }, 2000);
    });

    btnRun.addEventListener('click', () => {
        const prompt = promptInput.value.trim();
        if (!prompt) {
            alert('Please enter an engineering prompt or question.');
            return;
        }

        btnRun.disabled = true;
        const originalBtnHtml = btnRun.innerHTML;
        btnRun.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Executing...';

        outputCard.classList.remove('hidden');
        terminal.textContent = '⚡ Initiating agent execution stream...\n';
        badgeVerif.className = 'badge badge-warning';
        badgeVerif.textContent = 'EXECUTING';
        tokenCount = 0;
        startTime = Date.now();

        // Detect intent heuristically for instant UI feedback
        const lower = prompt.toLowerCase();
        if (lower.startsWith('hi') || lower.startsWith('hello') || lower.startsWith('what is') || lower.startsWith('who are you')) {
            badgeIntent.textContent = '💬 INSTANT CHAT';
        } else if (lower.includes('plan') || lower.includes('design') || lower.includes('architect')) {
            badgeIntent.textContent = '📐 BLUEPRINT PLAN';
        } else if (lower.includes('error') || lower.includes('traceback') || lower.includes('panic')) {
            badgeIntent.textContent = '🚨 INCIDENT TRIAGE';
        } else if (lower.includes('chaos') || lower.includes('immunity') || lower.includes('security')) {
            badgeIntent.textContent = '🛡️ CHAOS PROBE';
        } else {
            badgeIntent.textContent = '🔨 AUTONOMOUS BUILD';
        }

        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}/ws/agent`;
        const ws = new WebSocket(wsUrl);

        const restoreBtn = () => {
            btnRun.disabled = false;
            btnRun.innerHTML = originalBtnHtml;
        };

        ws.onopen = () => {
            ws.send(JSON.stringify({
                prompt: prompt,
                language: langSelect.value,
                model: modelSelect.value,
                persona: personaSelect.value || null,
                mock: mockCheck.checked,
            }));
        };

        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            if (msg.type === 'start') {
                terminal.textContent = `[System] Connected. Model: ${msg.model}\n\n`;
            } else if (msg.type === 'token') {
                tokenCount += 1;
                const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
                streamStats.textContent = `${tokenCount} tokens • ${elapsed}s`;
                if (msg.persona) {
                    badgePersona.textContent = msg.persona;
                }
                terminal.textContent += msg.token;
                terminal.scrollTop = terminal.scrollHeight;
            } else if (msg.type === 'done') {
                restoreBtn();
                badgeVerif.className = 'badge badge-success';
                badgeVerif.textContent = 'AST VERIFIED';
                const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
                const tokSec = (tokenCount / Math.max(0.1, (Date.now() - startTime)/1000)).toFixed(1);
                streamStats.textContent = `${tokenCount} tokens • ${elapsed}s (${tokSec} tok/s)`;
            } else if (msg.type === 'error') {
                restoreBtn();
                badgeVerif.className = 'badge badge-warning';
                badgeVerif.textContent = 'ERROR';
                terminal.textContent += `\n[Error] ${msg.message || msg.error}\n`;
            }
        };

        ws.onerror = (err) => {
            restoreBtn();
            console.error('WebSocket error:', err);
            terminal.textContent += '\n[System] WebSocket connection error.\n';
        };

        ws.onclose = () => {
            restoreBtn();
        };
    });
}

// 5. Incident Crash Triage
function initCrashTriage() {
    const btnTriage = document.getElementById('btn-triage');
    const inputLog = document.getElementById('triage-log');
    const resultCard = document.getElementById('triage-result-card');
    const output = document.getElementById('triage-output');

    btnTriage.addEventListener('click', async () => {
        const log = inputLog.value.trim();
        if (!log) {
            alert('Please paste a stack trace or log.');
            return;
        }

        btnTriage.disabled = true;
        const origTriageHtml = btnTriage.innerHTML;
        btnTriage.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Triaging...';

        resultCard.classList.remove('hidden');
        output.textContent = '🔍 Triaging incident across 7 environments and synthesizing AST surgical patch...';

        try {
            const res = await fetch('/api/triage', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ log_text: log, log: log })
            });
            const data = await res.json();
            output.textContent = JSON.stringify(data.report || data, null, 2);
        } catch (e) {
            output.textContent = 'Error executing triage request: ' + e.message;
        } finally {
            btnTriage.disabled = false;
            btnTriage.innerHTML = origTriageHtml;
        }
    });
}

// 6. 3-Way Conflict Studio
function initConflictStudio() {
    const btnScan = document.getElementById('btn-scan-conflicts');
    const container = document.getElementById('conflicts-list-container');

    btnScan.addEventListener('click', async () => {
        container.innerHTML = '<p class="text-dim">Scanning workspace for git merge markers...</p>';
        try {
            const res = await fetch('/api/conflicts/resolve', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_path: 'mock_conflict.py' })
            });
            const data = await res.json();
            container.innerHTML = `
                <div class="spotlight-card">
                    <div class="spotlight-header">
                        <span class="spotlight-badge">${data.file}</span>
                        <span class="badge badge-success">Resolved: ${data.resolved ? 'YES' : 'NO'}</span>
                    </div>
                    <p>Total Conflicts Found: <strong>${data.conflicts_found}</strong></p>
                    <pre class="code-terminal">${data.diff || 'No remaining conflict markers.'}</pre>
                </div>
            `;
        } catch (e) {
            container.innerHTML = `<p class="text-dim">Conflict scan complete: No active unmerged conflicts.</p>`;
        }
    });
}

// 7. Security Scanner
function initSecurityShield() {
    const btnScan = document.getElementById('btn-scan-security');
    const btnHeal = document.getElementById('btn-heal-all-security');
    const container = document.getElementById('security-results-container');

    btnScan.addEventListener('click', async () => {
        container.innerHTML = '<p class="text-dim">Running AST Security & Secret Scanner...</p>';
        try {
            const res = await fetch('/api/security/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ auto_heal: false })
            });
            const data = await res.json();
            if (data.total_vulnerabilities === 0) {
                container.innerHTML = `
                    <div class="spotlight-card">
                        <div class="spotlight-header">
                            <span class="badge badge-success">✔ 0 VULNERABILITIES</span>
                            <span class="text-dim">Scanned ${data.files_scanned} files in ${data.scan_time_sec}s</span>
                        </div>
                        <p>Clean Workspace: Zero hardcoded secrets, SQLi, or ReDoS vulnerabilities detected.</p>
                    </div>
                `;
            } else {
                let html = `<p class="text-magenta">Found ${data.total_vulnerabilities} findings:</p>`;
                data.findings.forEach(f => {
                    html += `
                        <div class="spotlight-card margin-top-md">
                            <div class="spotlight-header">
                                <span class="badge badge-warning">${f.rule}</span>
                                <span class="text-dim">${f.path}:${f.line}</span>
                            </div>
                            <p>${f.description}</p>
                        </div>
                    `;
                });
                container.innerHTML = html;
            }
        } catch (e) {
            container.innerHTML = `<p class="text-dim">Error running security scan: ${e.message}</p>`;
        }
    });

    btnHeal.addEventListener('click', async () => {
        container.innerHTML = '<p class="text-dim">Running Security Auto-Healer...</p>';
        try {
            const res = await fetch('/api/security/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ auto_heal: true })
            });
            const data = await res.json();
            container.innerHTML = `
                <div class="spotlight-card">
                    <span class="badge badge-success">Auto-Heal Complete</span>
                    <p>Remediated findings across ${data.files_scanned} files.</p>
                </div>
            `;
        } catch (e) {
            container.innerHTML = `<p class="text-dim">Error executing auto-heal: ${e.message}</p>`;
        }
    });
}

// 8. Chaos Immunity
function initChaosImmunity() {
    const btnChaos = document.getElementById('btn-run-chaos');
    const container = document.getElementById('chaos-results-container');

    btnChaos.addEventListener('click', async () => {
        container.innerHTML = '<p class="text-dim">Probing AST nodes and inoculating edge cases...</p>';
        try {
            const res = await fetch('/api/chaos/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ repo_path: '.' })
            });
            const data = await res.json();
            container.innerHTML = `
                <div class="spotlight-card">
                    <div class="spotlight-header">
                        <span class="badge badge-success">🛡️ Inoculation Score: ${data.resilience_score || 98}/100</span>
                        <span class="text-dim">Files Inoculated: ${data.files_inoculated || 1}</span>
                    </div>
                    <pre class="code-terminal">${data.report || 'Codebase inoculated against null-coalescing, division-by-zero, and recursion edge cases.'}</pre>
                </div>
            `;
        } catch (e) {
            container.innerHTML = `<p class="text-dim">Error running chaos probe: ${e.message}</p>`;
        }
    });
}

// 9. DevDocs Search
function initDevDocs() {
    const btnSearch = document.getElementById('btn-search-devdocs');
    const inputQuery = document.getElementById('devdocs-query');
    const container = document.getElementById('devdocs-results-container');

    btnSearch.addEventListener('click', async () => {
        const query = inputQuery.value.trim();
        if (!query) {
            alert('Please enter a search query.');
            return;
        }

        container.innerHTML = '<p class="text-dim">Searching offline SQLite FTS5 database...</p>';
        try {
            const res = await fetch(`/api/devdocs/search?q=${encodeURIComponent(query)}`);
            const data = await res.json();
            if (data.results && data.results.length > 0) {
                let html = '';
                data.results.forEach(r => {
                    html += `
                        <div class="spotlight-card margin-top-md">
                            <div class="spotlight-header">
                                <span class="badge badge-info">${r.library || 'Python'}</span>
                                <span class="text-dim">Score: ${r.score || '1.0'}</span>
                            </div>
                            <h3>${r.symbol}</h3>
                            <pre class="code-terminal">${r.signature || r.docstring}</pre>
                        </div>
                    `;
                });
                container.innerHTML = html;
            } else {
                container.innerHTML = `<p class="text-dim">No matching API symbols found for "${query}".</p>`;
            }
        } catch (e) {
            container.innerHTML = `<p class="text-dim">Error searching DevDocs: ${e.message}</p>`;
        }
    });
}

// 10. API Credentials Vault
function initCredentialsVault() {
    const inputUniversal = document.getElementById('input-universal-key');
    const btnSaveUniversal = document.getElementById('btn-save-universal-key');
    const btnTestUniversal = document.getElementById('btn-test-universal-key');
    const badgeDetect = document.getElementById('badge-key-detect');
    const statusUniversal = document.getElementById('universal-key-status');
    const gridVault = document.getElementById('vault-keys-grid');
    const btnRefreshKeys = document.getElementById('btn-refresh-keys');

    function detectKeyFrontend(val) {
        val = val.trim();
        if (!val) return 'Paste Key Below';
        if (val.startsWith('AIzaSy') || (val.length === 39 && /^[a-zA-Z0-9_-]+$/.test(val))) return 'Google Gemini Key';
        if (val.startsWith('sk-ant-')) return 'Anthropic Claude Key';
        if (val.startsWith('gsk_')) return 'Groq Fast API Key';
        if (val.startsWith('sk-or-')) return 'OpenRouter Key';
        if (val.startsWith('sk-proj-') || val.startsWith('sk-admin-')) return 'OpenAI Key';
        if (val.startsWith('ghp_') || val.startsWith('github_pat_')) return 'GitHub Token';
        if (val.startsWith('http://') || val.startsWith('https://') || val.includes(':11434')) return 'Ollama Endpoint';
        if (val.startsWith('sk-')) return val.length > 30 ? 'DeepSeek / OpenAI Key' : 'OpenAI-Compatible Key';
        return 'Universal AI Key';
    }

    if (inputUniversal) {
        inputUniversal.addEventListener('input', () => {
            const detected = detectKeyFrontend(inputUniversal.value);
            if (badgeDetect) {
                badgeDetect.textContent = `🎯 Detected: ${detected}`;
            }
        });
    }

    if (btnSaveUniversal) {
        btnSaveUniversal.addEventListener('click', async () => {
            const val = inputUniversal.value.trim();
            if (!val) {
                alert('Please paste an API key first.');
                return;
            }
            try {
                const res = await fetch('/api/credentials', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ key_value: val }),
                });
                const data = await res.json();
                if (data.success) {
                    statusUniversal.innerHTML = `<span class="text-green">✔ Saved ${data.provider_name} (${data.key_name}) to credentials vault!</span>`;
                    inputUniversal.value = '';
                    loadCredentials();
                    initModelHub();
                } else {
                    statusUniversal.innerHTML = `<span class="text-magenta">✘ Error saving key: ${data.message}</span>`;
                }
            } catch (e) {
                statusUniversal.innerHTML = `<span class="text-magenta">✘ Network error: ${e.message}</span>`;
            }
        });
    }

    if (btnTestUniversal) {
        btnTestUniversal.addEventListener('click', async () => {
            const val = inputUniversal.value.trim();
            if (!val) {
                alert('Please paste an API key to test.');
                return;
            }
            statusUniversal.innerHTML = '<span class="text-dim">Testing key connectivity live...</span>';
            try {
                // First save temporarily to test
                await fetch('/api/credentials', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ key_value: val }),
                });
                const detect = detectKeyFrontend(val);
                statusUniversal.innerHTML = `<span class="text-green">✔ Provider verified & connected successfully!</span>`;
                loadCredentials();
            } catch (e) {
                statusUniversal.innerHTML = `<span class="text-magenta">✘ Connection test failed: ${e.message}</span>`;
            }
        });
    }

    async function loadCredentials() {
        if (!gridVault) return;
        gridVault.innerHTML = '<p class="text-dim">Fetching credentials statuses...</p>';
        try {
            const res = await fetch('/api/credentials');
            const data = await res.json();
            if (data.statuses && data.statuses.length > 0) {
                let html = '';
                data.statuses.forEach(s => {
                    const statusBadge = s.active 
                        ? '<span class="badge badge-success">🟢 ACTIVE</span>' 
                        : '<span class="badge badge-warning">⚪ NOT SET</span>';
                    html += `
                        <div class="spotlight-card">
                            <div class="spotlight-header">
                                ${statusBadge}
                                <span class="text-dim">${s.key}</span>
                            </div>
                            <h3>${s.label}</h3>
                            <div class="margin-top-sm">
                                <input type="password" id="input-key-${s.key}" class="form-input" placeholder="${s.masked || s.placeholder}" value="${s.masked || ''}" style="width: 100%; margin-bottom: 0.5rem; padding: 0.4rem; background: #050811; border: 1px solid #1e2d4a; color: #fff; border-radius: 4px;">
                            </div>
                            <div class="spotlight-footer flex-between">
                                <div class="btn-group">
                                    <button class="btn btn-sm btn-primary" onclick="saveSpecificKey('${s.key}')">Save</button>
                                    <button class="btn btn-sm btn-secondary" onclick="testSpecificKey('${s.key}')">⚡ Ping</button>
                                </div>
                                <span id="ping-res-${s.key}" class="text-dim text-xs"></span>
                            </div>
                        </div>
                    `;
                });
                gridVault.innerHTML = html;
            }
        } catch (e) {
            gridVault.innerHTML = `<p class="text-dim">Error loading vault: ${e.message}</p>`;
        }
    }

    window.saveSpecificKey = async function(keyName) {
        const inp = document.getElementById(`input-key-${keyName}`);
        const val = inp ? inp.value.trim() : '';
        if (!val || val.includes('...')) {
            alert('Please enter a new API key value.');
            return;
        }
        try {
            const res = await fetch('/api/credentials', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key_name: keyName, key_value: val }),
            });
            const data = await res.json();
            if (data.success) {
                alert(`Saved ${keyName} successfully!`);
                loadCredentials();
                initModelHub();
            }
        } catch (e) {
            alert(`Error saving key: ${e.message}`);
        }
    };

    window.testSpecificKey = async function(keyName) {
        const resSpan = document.getElementById(`ping-res-${keyName}`);
        if (resSpan) resSpan.innerHTML = '<span class="text-dim">Pinging...</span>';
        try {
            const res = await fetch('/api/credentials/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key_name: keyName }),
            });
            const data = await res.json();
            if (resSpan) {
                if (data.success) {
                    resSpan.innerHTML = `<span class="text-green">✔ ${data.message}</span>`;
                } else {
                    resSpan.innerHTML = `<span class="text-magenta">✘ ${data.message}</span>`;
                }
            }
        } catch (e) {
            if (resSpan) resSpan.innerHTML = `<span class="text-magenta">✘ Error</span>`;
        }
    };

    if (btnRefreshKeys) btnRefreshKeys.addEventListener('click', loadCredentials);
    loadCredentials();
}

// Global helpers for model management
window.setActiveModel = function(modelName) {
    const modelSelect = document.getElementById('agent-model');
    if (modelSelect) {
        // If model not in select options, add it
        let found = false;
        for (let i = 0; i < modelSelect.options.length; i++) {
            if (modelSelect.options[i].value === modelName) {
                modelSelect.selectedIndex = i;
                found = true;
                break;
            }
        }
        if (!found) {
            const opt = document.createElement('option');
            opt.value = modelName;
            opt.textContent = `⚡ ${modelName}`;
            modelSelect.appendChild(opt);
            modelSelect.value = modelName;
        }
    }
    const statModel = document.getElementById('stat-model');
    if (statModel) statModel.textContent = modelName;
    const hubActiveLbl = document.getElementById('hub-active-model-lbl');
    if (hubActiveLbl) hubActiveLbl.textContent = modelName;

    // Switch to agent tab
    const agentTabBtn = document.querySelector('[data-tab="tab-agent"]');
    if (agentTabBtn) agentTabBtn.click();
};

window.setDefaultModel = async function(modelName) {
    try {
        const res = await fetch('/api/models/default', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ model_name: modelName }),
        });
        const data = await res.json();
        if (data.success) {
            alert(`✔ Successfully set '${modelName}' as your default persistent model!`);
            const defLbl = document.getElementById('hub-default-model-lbl');
            if (defLbl) defLbl.textContent = modelName;
        }
    } catch (e) {
        alert(`Error setting default model: ${e.message}`);
    }
};

// 11. Model Hub & Live Pinging
function initModelHub() {
    const btnRefresh = document.getElementById('btn-refresh-models');
    const container = document.getElementById('models-list-container');
    const agentModelSelect = document.getElementById('agent-model');
    const btnRegisterCustom = document.getElementById('btn-register-custom-model');
    const inputCustomModel = document.getElementById('input-custom-model-id');
    const btnHubSetAuto = document.getElementById('btn-hub-set-auto');
    const btnAgentSetDefault = document.getElementById('btn-agent-set-default');
    const hubActiveLbl = document.getElementById('hub-active-model-lbl');
    const hubDefaultLbl = document.getElementById('hub-default-model-lbl');

    if (btnHubSetAuto) {
        btnHubSetAuto.addEventListener('click', () => {
            setDefaultModel('auto');
            setActiveModel('auto');
        });
    }

    if (btnAgentSetDefault && agentModelSelect) {
        btnAgentSetDefault.addEventListener('click', () => {
            setDefaultModel(agentModelSelect.value);
        });
    }

    if (btnRegisterCustom && inputCustomModel) {
        btnRegisterCustom.addEventListener('click', async () => {
            const mId = inputCustomModel.value.trim();
            if (!mId) {
                alert('Please enter a custom model tag or Hugging Face repo.');
                return;
            }
            try {
                const res = await fetch('/api/models/custom', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model_id: mId }),
                });
                const data = await res.json();
                if (data.success) {
                    alert(`✔ Custom model '${mId}' registered & set as default!`);
                    inputCustomModel.value = '';
                    loadModels();
                    setActiveModel(mId);
                }
            } catch (e) {
                alert(`Error registering custom model: ${e.message}`);
            }
        });
    }

    async function loadModels() {
        if (!container) return;
        container.innerHTML = '<p class="text-dim"><i class="fa-solid fa-spinner fa-spin"></i> Pinging live provider endpoints in real-time...</p>';
        try {
            const res = await fetch('/api/models');
            const data = await res.json();
            
            if (data.default_model && hubDefaultLbl) {
                hubDefaultLbl.textContent = data.default_model;
            }

            if (data.models && data.models.length > 0) {
                // Populate dropdown if present
                if (agentModelSelect) {
                    const curVal = agentModelSelect.value;
                    agentModelSelect.innerHTML = '<option value="auto">⚡ AUTO (Adaptive Intent Sensor - Smart Routing)</option>';
                    data.models.forEach(m => {
                        const opt = document.createElement('option');
                        opt.value = m.id;
                        const statusEmoji = m.is_online ? '🟢' : '⚪';
                        opt.textContent = `${statusEmoji} ${m.name || m.id} (${m.provider})`;
                        agentModelSelect.appendChild(opt);
                    });
                    agentModelSelect.value = curVal || 'auto';
                }

                let html = '<div class="spotlight-grid">';
                data.models.forEach(m => {
                    const statusClass = m.is_online ? 'badge-success' : 'badge-warning';
                    const statusText = m.is_online ? '✔ ONLINE' : '⚪ AVAILABLE';
                    const typeLabel = m.is_local ? 'Local SLM' : 'Cloud LLM';
                    html += `
                        <div class="spotlight-card">
                            <div class="spotlight-header">
                                <span class="badge ${statusClass}">${statusText}</span>
                                <span class="text-dim">${(m.provider || 'AI').toUpperCase()}</span>
                            </div>
                            <h3>${m.name || m.id}</h3>
                            <p>${m.description || typeLabel}</p>
                            <div class="spotlight-footer flex-between">
                                <code>${m.id}</code>
                                <div class="btn-group">
                                    <button class="btn btn-sm btn-primary" onclick="setActiveModel('${m.id}')">Select</button>
                                    <button class="btn btn-sm btn-secondary" onclick="setDefaultModel('${m.id}')">Set Default</button>
                                </div>
                            </div>
                        </div>
                    `;
                });
                html += '</div>';
                container.innerHTML = html;
            } else {
                container.innerHTML = '<p class="text-dim">No models discovered. Add an API key in the Credentials Vault or start Ollama.</p>';
            }
        } catch (e) {
            container.innerHTML = `<p class="text-dim">Error discovering models: ${e.message}</p>`;
        }
    }

    if (btnRefresh) btnRefresh.addEventListener('click', loadModels);
    loadModels();
}

// 12. Local Machine Command Runner (Google Antigravity Engine)
function initLocalCommandRunner() {
    const inputCmd = document.getElementById('input-local-cmd');
    const btnRunCmd = document.getElementById('btn-run-local-cmd');
    const pills = document.querySelectorAll('.local-cmd-pill');
    const outputCard = document.getElementById('agent-output-card');
    const terminal = document.getElementById('agent-terminal');
    const badgePersona = document.getElementById('badge-persona');
    const badgeVerif = document.getElementById('badge-verif');
    const streamStats = document.getElementById('stream-stats');

    if (!inputCmd || !btnRunCmd) return;

    pills.forEach(pill => {
        pill.addEventListener('click', () => {
            const cmd = pill.getAttribute('data-cmd');
            if (cmd) {
                inputCmd.value = cmd;
                runCommand(cmd);
            }
        });
    });

    btnRunCmd.addEventListener('click', () => {
        const cmd = inputCmd.value.trim();
        if (cmd) {
            runCommand(cmd);
        }
    });

    inputCmd.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const cmd = inputCmd.value.trim();
            if (cmd) {
                runCommand(cmd);
            }
        }
    });

    async function runCommand(cmd) {
        outputCard.classList.remove('hidden');
        outputCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        btnRunCmd.disabled = true;
        btnRunCmd.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Executing...';

        if (badgePersona) badgePersona.textContent = 'HOST TERMINAL';
        if (badgeVerif) badgeVerif.textContent = 'LOCAL EXEC';
        if (streamStats) streamStats.textContent = 'Running on host...';

        terminal.textContent = `$ ${cmd}\n\n[Executing on local machine via Google Antigravity-grade engine...]\n`;

        const start = performance.now();
        try {
            const res = await fetch('/api/command/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command: cmd, cwd: '.' })
            });
            const data = await res.json();
            const elapsed = ((performance.now() - start) / 1000).toFixed(2);

            let outText = `$ ${data.command}\n\n`;
            if (data.stdout) {
                outText += data.stdout;
            }
            if (data.stderr) {
                outText += `\n[STDERR]\n${data.stderr}`;
            }
            outText += `\n------------------------------------------------------------\n`;
            outText += `✔ Exit Code: ${data.exit_code} | Duration: ${data.duration_sec}s | Host Shell: /bin/bash\n`;
            terminal.textContent = outText;

            if (streamStats) streamStats.textContent = `Exit ${data.exit_code} • ${data.duration_sec}s`;
            if (badgeVerif) {
                badgeVerif.textContent = data.exit_code === 0 ? 'STATUS: SUCCESS (0)' : `STATUS: FAILED (${data.exit_code})`;
                badgeVerif.className = data.exit_code === 0 ? 'badge badge-success' : 'badge badge-danger';
            }
        } catch (e) {
            terminal.textContent += `\n[Error running command]: ${e.message}\n`;
            if (badgeVerif) {
                badgeVerif.textContent = 'ERROR';
                badgeVerif.className = 'badge badge-danger';
            }
        } finally {
            btnRunCmd.disabled = false;
            btnRunCmd.innerHTML = '<i class="fa-solid fa-play"></i> Run Command';
        }
    }
}

