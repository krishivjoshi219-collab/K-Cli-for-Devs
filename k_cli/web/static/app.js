/* K-CLI World-Class Web UI Frontend Logic */

document.addEventListener('DOMContentLoaded', () => {
    initTabNavigation();
    initSystemStatus();
    initAgentRunner();
    initCrashTriage();
    initConflictStudio();
    initSecurityShield();
    initChaosImmunity();
    initDevDocs();
    initModelHub();
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
    setInterval(updateStatus, 5000);
}

// 3. Agent Task Runner & WebSocket Streaming
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

    btnRun.addEventListener('click', () => {
        const prompt = promptInput.value.trim();
        if (!prompt) {
            alert('Please enter a prompt goal.');
            return;
        }

        outputCard.classList.remove('hidden');
        terminal.textContent = '⚡ Initiating agent task execution...\n';
        badgeVerif.className = 'badge badge-warning';
        badgeVerif.textContent = 'EXECUTING';

        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}/ws/agent`;
        const ws = new WebSocket(wsUrl);

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
                if (msg.persona) {
                    badgePersona.textContent = msg.persona;
                }
                terminal.textContent += msg.token;
                terminal.scrollTop = terminal.scrollHeight;
            } else if (msg.type === 'complete') {
                if (msg.success) {
                    badgeVerif.className = 'badge badge-success';
                    badgeVerif.textContent = 'GROUND-TRUTH VERIFIED';
                    terminal.textContent += `\n\n✔ Verified Code Output (Attempts: ${msg.attempts}, RAM: ${msg.ram_usage_mb} MB):\n\n${msg.final_code}`;
                } else {
                    badgeVerif.className = 'badge badge-danger';
                    badgeVerif.textContent = 'VERIFICATION FAILED';
                    terminal.textContent += `\n\n✘ Execution completed but verification failed.`;
                }
                ws.close();
            } else if (msg.type === 'error') {
                badgeVerif.className = 'badge badge-danger';
                badgeVerif.textContent = 'ERROR';
                terminal.textContent += `\n\n[Error] ${msg.message}`;
                ws.close();
            }
        };

        ws.onerror = (err) => {
            console.error('WebSocket Error:', err);
            // Fallback to REST API if WebSocket fails
            runAgentRestAPI(prompt, langSelect.value, modelSelect.value, personaSelect.value, mockCheck.checked);
        };
    });

    async function runAgentRestAPI(prompt, language, model, persona, mock) {
        try {
            const res = await fetch('/api/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt, language, model, persona, mock })
            });
            const data = await res.json();
            if (data.success) {
                badgeVerif.className = 'badge badge-success';
                badgeVerif.textContent = 'VERIFIED';
                terminal.textContent = data.final_code;
            } else {
                badgeVerif.className = 'badge badge-danger';
                badgeVerif.textContent = 'FAILED';
                terminal.textContent = data.verification ? JSON.stringify(data.verification, null, 2) : 'Execution failed.';
            }
        } catch (e) {
            terminal.textContent = `API Error: ${e.message}`;
        }
    }
}

// 4. Crash Triage
function initCrashTriage() {
    const btnTriage = document.getElementById('btn-triage');
    const logInput = document.getElementById('triage-log');
    const resultCard = document.getElementById('triage-result-card');
    const output = document.getElementById('triage-output');

    btnTriage.addEventListener('click', async () => {
        const text = logInput.value.trim();
        if (!text) {
            alert('Please paste a stack trace or log.');
            return;
        }

        resultCard.classList.remove('hidden');
        output.textContent = 'Diagnosing crash trace...';

        try {
            const res = await fetch('/api/triage', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ log_text: text })
            });
            const data = await res.json();
            output.textContent = JSON.stringify(data, null, 2);
        } catch (e) {
            output.textContent = `Error: ${e.message}`;
        }
    });
}

// 5. Conflict Studio
function initConflictStudio() {
    const btnScan = document.getElementById('btn-scan-conflicts');
    const container = document.getElementById('conflicts-list-container');

    btnScan.addEventListener('click', async () => {
        container.innerHTML = '<p class="text-dim">Scanning workspace for 3-way git merge conflicts...</p>';
        try {
            const res = await fetch('/api/conflicts');
            const data = await res.json();
            if (data.total_conflicts === 0) {
                container.innerHTML = '<p class="badge badge-success">✔ Clean: No git merge conflicts detected in working tree.</p>';
            } else {
                let html = `<p class="badge badge-warning" style="margin-bottom:1rem;">Found ${data.total_conflicts} conflict block(s)</p>`;
                html += '<table class="data-table"><thead><tr><th>File</th><th>Lines</th><th>Scope</th><th>Ours</th><th>Theirs</th></tr></thead><tbody>';
                data.conflicts.forEach(c => {
                    html += `<tr><td>${c.file_path}</td><td>L${c.start_line}-${c.end_line}</td><td>${c.scope_name || 'Global'}</td><td>${c.ours_label}</td><td>${c.theirs_label}</td></tr>`;
                });
                html += '</tbody></table>';
                container.innerHTML = html;
            }
        } catch (e) {
            container.innerHTML = `<p class="badge badge-danger">Error: ${e.message}</p>`;
        }
    });
}

// 6. Security Shield
function initSecurityShield() {
    const btnScan = document.getElementById('btn-scan-security');
    const btnHealAll = document.getElementById('btn-heal-all-security');
    const container = document.getElementById('security-results-container');

    btnScan.addEventListener('click', async () => {
        container.innerHTML = '<p class="text-dim">Scanning codebase for vulnerabilities...</p>';
        try {
            const res = await fetch('/api/security/scan');
            const data = await res.json();
            if (!data.findings || data.findings.length === 0) {
                container.innerHTML = `<p class="badge badge-success">✔ Clean: 0 security vulnerabilities found across ${data.scanned_files_count} files.</p>`;
            } else {
                let html = `<p class="badge badge-danger" style="margin-bottom:1rem;">Found ${data.total_findings} security finding(s)</p>`;
                html += '<table class="data-table"><thead><tr><th>ID</th><th>Severity</th><th>Type</th><th>File:Line</th><th>CWE</th><th>Description</th></tr></thead><tbody>';
                data.findings.forEach(f => {
                    html += `<tr><td>${f.id}</td><td><span class="badge badge-danger">${f.severity}</span></td><td>${f.vuln_type}</td><td>${f.file_path}:${f.line_number}</td><td>${f.cwe_id}</td><td>${f.description}</td></tr>`;
                });
                html += '</tbody></table>';
                container.innerHTML = html;
            }
        } catch (e) {
            container.innerHTML = `<p class="badge badge-danger">Error: ${e.message}</p>`;
        }
    });

    btnHealAll.addEventListener('click', async () => {
        container.innerHTML = '<p class="text-dim">Auto-healing security findings...</p>';
        try {
            const res = await fetch('/api/security/heal', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ heal_all: true })
            });
            const data = await res.json();
            container.innerHTML = `<p class="badge badge-success">✔ Auto-heal operation complete.</p><pre class="code-terminal" style="margin-top:1rem;">${JSON.stringify(data, null, 2)}</pre>`;
        } catch (e) {
            container.innerHTML = `<p class="badge badge-danger">Error: ${e.message}</p>`;
        }
    });
}

// 7. Chaos Immunity
function initChaosImmunity() {
    const btnRun = document.getElementById('btn-run-chaos');
    const container = document.getElementById('chaos-results-container');

    btnRun.addEventListener('click', async () => {
        container.innerHTML = '<p class="text-dim">Probing brittle AST edge cases and synthesizing adversarial tests...</p>';
        try {
            const res = await fetch('/api/chaos/scan');
            const data = await res.json();
            let html = `<p class="badge badge-info" style="margin-bottom:1rem;">Scanned ${data.total_modules} module(s)</p>`;
            html += '<table class="data-table"><thead><tr><th>Target File</th><th>Brittle Patterns</th><th>Tests Synthesized</th><th>Patches Applied</th><th>Status</th></tr></thead><tbody>';
            data.reports.forEach(r => {
                html += `<tr><td>${r.target_file}</td><td>${r.patterns_detected}</td><td>${r.generated_tests_count}</td><td>${r.patches_applied_count}</td><td><span class="badge badge-success">${r.verification_passed ? 'PASSED' : 'FAILED'}</span></td></tr>`;
            });
            html += '</tbody></table>';
            container.innerHTML = html;
        } catch (e) {
            container.innerHTML = `<p class="badge badge-danger">Error: ${e.message}</p>`;
        }
    });
}

// 8. DevDocs Search
function initDevDocs() {
    const btnSearch = document.getElementById('btn-search-devdocs');
    const queryInput = document.getElementById('devdocs-query');
    const container = document.getElementById('devdocs-results-container');

    btnSearch.addEventListener('click', async () => {
        const query = queryInput.value.trim();
        if (!query) return;

        container.innerHTML = '<p class="text-dim">Searching FTS5 DevDocs database...</p>';
        try {
            const res = await fetch('/api/devdocs/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: query, limit: 5 })
            });
            const data = await res.json();
            if (!data.results || data.results.length === 0) {
                container.innerHTML = `<p class="text-dim">No results found for "${query}".</p>`;
            } else {
                let html = '';
                data.results.forEach(r => {
                    html += `<div style="background:var(--bg-input); padding:1rem; border-radius:0.375rem; margin-bottom:0.75rem; border:1px solid var(--border-color);">
                        <div style="font-weight:700; color:var(--primary-cyan); font-family:var(--font-mono);">${r.signature || r.name}</div>
                        <div style="font-size:0.8rem; color:var(--text-muted); margin-top:0.25rem;">Module: ${r.module}</div>
                        <div style="font-size:0.85rem; color:var(--text-secondary); margin-top:0.5rem;">${r.doc || ''}</div>
                    </div>`;
                });
                container.innerHTML = html;
            }
        } catch (e) {
            container.innerHTML = `<p class="badge badge-danger">Error: ${e.message}</p>`;
        }
    });
}

// 9. Model Hub
function initModelHub() {
    const btnRefresh = document.getElementById('btn-refresh-models');
    const container = document.getElementById('models-list-container');

    async function loadModels() {
        container.innerHTML = '<p class="text-dim">Fetching model catalog...</p>';
        try {
            const res = await fetch('/api/models');
            const data = await res.json();
            let html = '<table class="data-table"><thead><tr><th>Model ID</th><th>Provider</th><th>Type</th><th>Context</th><th>Status</th></tr></thead><tbody>';
            data.models.forEach(m => {
                const statusBadge = m.is_installed ? '<span class="badge badge-success">Installed</span>' : '<span class="badge badge-info">Available</span>';
                html += `<tr><td>${m.id}</td><td>${m.provider.toUpperCase()}</td><td>${m.is_local ? 'Local SLM' : 'Cloud LLM'}</td><td>${Math.round(m.context_window/1024)}k</td><td>${statusBadge}</td></tr>`;
            });
            html += '</tbody></table>';
            container.innerHTML = html;
        } catch (e) {
            container.innerHTML = `<p class="badge badge-danger">Error: ${e.message}</p>`;
        }
    }

    btnRefresh.addEventListener('click', loadModels);
    loadModels();
}
