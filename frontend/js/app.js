/**
 * ViralClip - Main Application JavaScript
 * Handles UI interactions, WebSocket connection, and API calls
 */

// ============================================================================
// State Management
// ============================================================================

const state = {
    currentJob: null,
    clips: [],
    wsConnected: false,
    ws: null
};

// ============================================================================
// DOM Elements
// ============================================================================

const elements = {
    // Form
    jobForm: document.getElementById('jobForm'),
    sourceUrl: document.getElementById('sourceUrl'),
    sourceFile: document.getElementById('sourceFile'),
    fileUpload: document.getElementById('fileUpload'),
    filePreview: document.getElementById('filePreview'),
    clipCount: document.getElementById('clipCount'),
    minDuration: document.getElementById('minDuration'),
    maxDuration: document.getElementById('maxDuration'),
    uploadToS3: document.getElementById('uploadToS3'),
    enableDubbing: document.getElementById('enableDubbing'),
    dubbingOptions: document.getElementById('dubbingOptions'),
    dubbingLanguage: document.getElementById('dubbingLanguage'),
    submitBtn: document.getElementById('submitBtn'),

    // Tabs
    tabBtns: document.querySelectorAll('.tab-btn'),
    urlTab: document.getElementById('url-tab'),
    fileTab: document.getElementById('file-tab'),

    // Progress
    progressSection: document.getElementById('progressSection'),
    progressBar: document.getElementById('progressBar'),
    progressStatus: document.getElementById('progressStatus'),
    progressPercent: document.getElementById('progressPercent'),
    progressSteps: document.getElementById('progressSteps'),

    // Clips
    clipsSection: document.getElementById('clipsSection'),
    clipsGrid: document.getElementById('clipsGrid'),
    clipCountBadge: document.getElementById('clipCountBadge'),

    // Logs
    logViewer: document.getElementById('logViewer'),
    clearLogsBtn: document.getElementById('clearLogsBtn'),

    // Connection
    connectionStatus: document.getElementById('connectionStatus'),

    // Settings Modal
    settingsBtn: document.getElementById('settingsBtn'),
    settingsModal: document.getElementById('settingsModal'),
    closeSettings: document.getElementById('closeSettings'),
    serviceList: document.getElementById('serviceList'),
    systemStats: document.getElementById('systemStats'),

    // Preview Modal
    previewModal: document.getElementById('previewModal'),
    closePreview: document.getElementById('closePreview'),
    previewVideo: document.getElementById('previewVideo'),
    previewTitle: document.getElementById('previewTitle'),
    previewScore: document.getElementById('previewScore'),
    previewDuration: document.getElementById('previewDuration'),
    previewMode: document.getElementById('previewMode'),
    previewDescription: document.getElementById('previewDescription'),
    downloadClipBtn: document.getElementById('downloadClipBtn'),
    shareClipBtn: document.getElementById('shareClipBtn')
};

// ============================================================================
// WebSocket Connection
// ============================================================================

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    try {
        state.ws = new WebSocket(wsUrl);

        state.ws.onopen = () => {
            state.wsConnected = true;
            updateConnectionStatus('connected');
            addLog('Connected to server', 'success');
        };

        state.ws.onclose = () => {
            state.wsConnected = false;
            updateConnectionStatus('disconnected');
            addLog('Disconnected from server', 'warning');

            // Attempt reconnection
            setTimeout(connectWebSocket, 3000);
        };

        state.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            updateConnectionStatus('error');
        };

        state.ws.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                handleWebSocketMessage(message);
            } catch (e) {
                console.error('Failed to parse WebSocket message:', e);
            }
        };
    } catch (error) {
        console.error('Failed to connect WebSocket:', error);
        updateConnectionStatus('error');
        setTimeout(connectWebSocket, 5000);
    }
}

function handleWebSocketMessage(message) {
    switch (message.type) {
        case 'progress':
            updateProgress(message.data);
            break;
        case 'log':
            addLog(message.data.message, message.data.level?.toLowerCase());
            break;
        case 'clip_ready':
            addClip(message.data);
            break;
        case 'pong':
            // Heartbeat response
            break;
    }
}

function updateConnectionStatus(status) {
    const el = elements.connectionStatus;
    el.className = `status-indicator ${status}`;

    const statusText = el.querySelector('.status-text');
    switch (status) {
        case 'connected':
            statusText.textContent = 'Connected';
            break;
        case 'disconnected':
            statusText.textContent = 'Reconnecting...';
            break;
        case 'error':
            statusText.textContent = 'Connection Error';
            break;
        default:
            statusText.textContent = 'Connecting...';
    }
}

// ============================================================================
// API Functions
// ============================================================================

async function createJob(formData) {
    const response = await fetch('/api/jobs/', {
        method: 'POST',
        body: formData
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to create job');
    }

    return response.json();
}

async function getJobClips(jobId) {
    const response = await fetch(`/api/jobs/${jobId}/clips`);
    if (!response.ok) throw new Error('Failed to fetch clips');
    return response.json();
}

async function getSettings() {
    const response = await fetch('/api/settings/');
    if (!response.ok) throw new Error('Failed to fetch settings');
    return response.json();
}

async function getSystemStatus() {
    const response = await fetch('/api/settings/system-status');
    if (!response.ok) throw new Error('Failed to fetch system status');
    return response.json();
}

async function getClipDownloadUrl(clipId) {
    const response = await fetch(`/api/clips/${clipId}/download`);
    if (!response.ok) throw new Error('Failed to get download URL');
    return response.json();
}

// ============================================================================
// UI Functions
// ============================================================================

function updateProgress(data) {
    if (!data) return;

    elements.progressSection.hidden = false;

    const progress = data.progress || 0;
    elements.progressBar.style.width = `${progress}%`;
    elements.progressPercent.textContent = `${Math.round(progress)}%`;

    if (data.message) {
        elements.progressStatus.textContent = data.message;
    }

    // Update step indicators
    updateProgressSteps(progress);

    // Check if complete
    if (progress >= 100) {
        setTimeout(() => {
            if (state.currentJob) {
                loadClips(state.currentJob.id);
            }
        }, 1000);
    }
}

function updateProgressSteps(progress) {
    const steps = elements.progressSteps.querySelectorAll('.step');
    const stepThresholds = [0, 15, 35, 50, 75, 100];

    steps.forEach((step, index) => {
        const threshold = stepThresholds[index];
        const nextThreshold = stepThresholds[index + 1] || 100;

        step.classList.remove('active', 'completed');

        if (progress >= nextThreshold) {
            step.classList.add('completed');
        } else if (progress >= threshold) {
            step.classList.add('active');
        }
    });
}

function addLog(message, level = 'info') {
    const viewer = elements.logViewer;

    const entry = document.createElement('div');
    entry.className = `log-entry ${level}`;

    const time = new Date().toLocaleTimeString();
    entry.innerHTML = `
        <span class="log-time">${time}</span>
        <span class="log-message">${escapeHtml(message)}</span>
    `;

    viewer.appendChild(entry);
    viewer.scrollTop = viewer.scrollHeight;

    // Limit log entries
    while (viewer.children.length > 100) {
        viewer.removeChild(viewer.firstChild);
    }
}

function clearLogs() {
    elements.logViewer.innerHTML = `
        <div class="log-entry info">
            <span class="log-time">${new Date().toLocaleTimeString()}</span>
            <span class="log-message">Logs cleared</span>
        </div>
    `;
}

async function loadClips(jobId) {
    try {
        const clips = await getJobClips(jobId);
        state.clips = clips;
        renderClips(clips);
    } catch (error) {
        console.error('Failed to load clips:', error);
    }
}

function renderClips(clips) {
    if (!clips || clips.length === 0) {
        elements.clipsSection.hidden = true;
        return;
    }

    elements.clipsSection.hidden = false;
    elements.clipCountBadge.textContent = `${clips.length} clip${clips.length !== 1 ? 's' : ''}`;

    elements.clipsGrid.innerHTML = clips.map(clip => `
        <div class="clip-card" data-clip-id="${clip.id}">
            <div class="clip-thumbnail">
                <div class="play-overlay">
                    <div class="play-button">▶</div>
                </div>
            </div>
            <div class="clip-info">
                <h3 class="clip-title">${escapeHtml(clip.title)}</h3>
                <div class="clip-meta">
                    <span class="viral-score ${clip.viral_score >= 80 ? 'high' : ''}">
                        🔥 ${Math.round(clip.viral_score)}
                    </span>
                    <span>${formatDuration(clip.duration)}</span>
                    <span>${clip.cropping_mode}</span>
                </div>
            </div>
        </div>
    `).join('');

    // Add click handlers
    elements.clipsGrid.querySelectorAll('.clip-card').forEach(card => {
        card.addEventListener('click', () => {
            const clipId = card.dataset.clipId;
            const clip = state.clips.find(c => c.id === clipId);
            if (clip) openPreviewModal(clip);
        });
    });
}

function addClip(clipData) {
    state.clips.push(clipData);
    renderClips(state.clips);
}

async function openPreviewModal(clip) {
    elements.previewModal.hidden = false;

    elements.previewTitle.textContent = clip.title;
    elements.previewScore.textContent = Math.round(clip.viral_score);
    elements.previewDuration.textContent = formatDuration(clip.duration);
    elements.previewMode.textContent = clip.cropping_mode;
    elements.previewDescription.textContent = clip.description || 'No description';

    // Get video URL
    try {
        const urlData = await getClipDownloadUrl(clip.id);
        elements.previewVideo.src = urlData.url;
        elements.previewVideo.load();
    } catch (error) {
        console.error('Failed to load video:', error);
        addLog('Failed to load video preview', 'error');
    }

    // Download button
    elements.downloadClipBtn.onclick = async () => {
        try {
            const urlData = await getClipDownloadUrl(clip.id);
            const a = document.createElement('a');
            a.href = urlData.url;
            a.download = `${clip.title}.mp4`;
            a.click();
        } catch (error) {
            alert('Failed to download clip');
        }
    };

    // Share button
    elements.shareClipBtn.onclick = () => {
        alert('Social sharing coming soon! Configure your accounts in Settings.');
    };
}

function closePreviewModal() {
    elements.previewModal.hidden = true;
    elements.previewVideo.pause();
    elements.previewVideo.src = '';
}

async function openSettingsModal() {
    elements.settingsModal.hidden = false;

    try {
        // Load settings
        const settings = await getSettings();
        renderServices(settings.services);

        // Load system status
        const systemStatus = await getSystemStatus();
        renderSystemStats(systemStatus);
    } catch (error) {
        console.error('Failed to load settings:', error);
    }
}

function closeSettingsModal() {
    elements.settingsModal.hidden = true;
}

function renderServices(services) {
    elements.serviceList.innerHTML = services.map(service => `
        <div class="service-item">
            <span class="service-name">${service.name}</span>
            <span class="service-status ${service.configured ? 'ready' : 'pending'}">
                ${service.status}
            </span>
        </div>
    `).join('');
}

function renderSystemStats(stats) {
    elements.systemStats.innerHTML = `
        <div class="stat-card">
            <div class="stat-label">FFmpeg</div>
            <div class="stat-value">${stats.ffmpeg.available ? '✓ Ready' : '✗ Not Found'}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Disk Space</div>
            <div class="stat-value">${stats.disk.free_gb} GB free</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Memory</div>
            <div class="stat-value">${stats.memory.available_gb} GB available</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">CPU Usage</div>
            <div class="stat-value">${100 - Math.round(stats.memory.used_percent)}% free</div>
        </div>
    `;
}

function setFormLoading(loading) {
    const btn = elements.submitBtn;
    const content = btn.querySelector('.btn-content');
    const loadingEl = btn.querySelector('.btn-loading');

    btn.disabled = loading;
    content.hidden = loading;
    loadingEl.hidden = !loading;
}

// ============================================================================
// Event Handlers
// ============================================================================

function setupEventListeners() {
    // Form submission
    elements.jobForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const formData = new FormData();

        // Get active tab
        const activeTab = document.querySelector('.tab-btn.active').dataset.tab;

        if (activeTab === 'url') {
            const url = elements.sourceUrl.value.trim();
            if (!url) {
                alert('Please enter a YouTube URL');
                return;
            }
            formData.append('source_url', url);
        } else {
            const file = elements.sourceFile.files[0];
            if (!file) {
                alert('Please select a video file');
                return;
            }
            formData.append('file', file);
        }

        formData.append('clip_count', elements.clipCount.value);
        formData.append('min_duration', elements.minDuration.value);
        formData.append('max_duration', elements.maxDuration.value);
        formData.append('upload_to_s3', elements.uploadToS3.checked);
        formData.append('enable_dubbing', elements.enableDubbing.checked);

        if (elements.enableDubbing.checked && elements.dubbingLanguage.value) {
            formData.append('dubbing_language', elements.dubbingLanguage.value);
        }

        try {
            setFormLoading(true);
            addLog('Creating new job...', 'info');

            const job = await createJob(formData);
            state.currentJob = job;
            state.clips = [];

            addLog(`Job created: ${job.id}`, 'success');
            elements.progressSection.hidden = false;
            elements.clipsSection.hidden = true;

        } catch (error) {
            addLog(`Failed to create job: ${error.message}`, 'error');
            alert('Failed to create job: ' + error.message);
        } finally {
            setFormLoading(false);
        }
    });

    // Tab switching
    elements.tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            elements.tabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const tab = btn.dataset.tab;
            elements.urlTab.classList.toggle('active', tab === 'url');
            elements.fileTab.classList.toggle('active', tab === 'file');
        });
    });

    // File upload
    elements.fileUpload.addEventListener('click', () => {
        elements.sourceFile.click();
    });

    elements.sourceFile.addEventListener('change', () => {
        const file = elements.sourceFile.files[0];
        if (file) {
            showFilePreview(file);
        }
    });

    // Drag and drop
    elements.fileUpload.addEventListener('dragover', (e) => {
        e.preventDefault();
        elements.fileUpload.classList.add('dragover');
    });

    elements.fileUpload.addEventListener('dragleave', () => {
        elements.fileUpload.classList.remove('dragover');
    });

    elements.fileUpload.addEventListener('drop', (e) => {
        e.preventDefault();
        elements.fileUpload.classList.remove('dragover');

        const file = e.dataTransfer.files[0];
        if (file && file.type.startsWith('video/')) {
            elements.sourceFile.files = e.dataTransfer.files;
            showFilePreview(file);
        }
    });

    // Dubbing toggle
    elements.enableDubbing.addEventListener('change', () => {
        elements.dubbingOptions.hidden = !elements.enableDubbing.checked;
    });

    // Clear logs
    elements.clearLogsBtn.addEventListener('click', clearLogs);

    // Settings modal
    elements.settingsBtn.addEventListener('click', openSettingsModal);
    elements.closeSettings.addEventListener('click', closeSettingsModal);
    elements.settingsModal.querySelector('.modal-backdrop').addEventListener('click', closeSettingsModal);

    // Preview modal
    elements.closePreview.addEventListener('click', closePreviewModal);
    elements.previewModal.querySelector('.modal-backdrop').addEventListener('click', closePreviewModal);

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeSettingsModal();
            closePreviewModal();
        }
    });
}

function showFilePreview(file) {
    const uploadContent = elements.fileUpload.querySelector('.upload-content');
    const preview = elements.filePreview;

    uploadContent.hidden = true;
    preview.hidden = false;
    preview.querySelector('.file-name').textContent = file.name;

    preview.querySelector('.remove-file').onclick = (e) => {
        e.stopPropagation();
        elements.sourceFile.value = '';
        uploadContent.hidden = false;
        preview.hidden = true;
    };
}

// ============================================================================
// Utilities
// ============================================================================

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDuration(seconds) {
    if (!seconds) return '--:--';
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// ============================================================================
// Initialize
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    connectWebSocket();
    addLog('ViralClip initialized', 'info');
});
