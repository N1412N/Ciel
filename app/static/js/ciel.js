/* ==========================================================================
   CIEL INFINITE STUDIO — CLIENT APPLICATION LOGIC
   Seamless management of Chat, Agent Tools, IDE, Primitive Art, Tasks,
   Diffusion, Memory, and Voice Engine.
   ========================================================================== */

(function () {
  'use strict';

  // --- Global Application State ---
  const state = {
    activeView: 'chat',
    currentChatId: 'chat_' + Date.now(),
    messages: [],
    models: [],
    selectedModel: 'ciel-auto',
    agentMode: true,
    ttsEnabled: false,
    wakeActive: false,
    isListening: false,
    currentAudio: null,
    isGenerating: false,
    currentWorkspacePath: '',
    activeFile: '',
    activeFileContent: '',
    tasks: [],
    imageModels: [],
    selectedImageModel: 'counterfeit-v3',
    primitive: {
      imagePath: '',
      imageB64: '',
      mode: 'combo',
      numShapes: 50,
      alpha: 0.55,
      asyncTask: false,
      svgContent: '',
      pngPath: '',
      svgPath: ''
    },
    diffusion: {
      imagePath: '',
      imageUrl: '',
      imageB64: ''
    }
  };

  let abortController = null;
  let permPollTimer = null;
  let sysPollTimer = null;
  let wakePollTimer = null;

  // --- DOM Elements Helper ---
  const $ = (id) => document.getElementById(id);
  const $$ = (sel) => document.querySelectorAll(sel);

  // --- Toast Notifications ---
  function showToast(message, type = 'info', duration = 3500) {
    const container = $('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    const iconMap = {
      success: 'fa-check-circle',
      error: 'fa-exclamation-triangle',
      info: 'fa-info-circle',
      warning: 'fa-bell'
    };
    toast.innerHTML = `<i class="fas ${iconMap[type] || 'fa-info-circle'}"></i> <span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(100%)';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // --- Sound Effects ---
  
  // --- Universal Image & File Downloader ---
  async function triggerDownload(urlOrBlobOrSvg, filename, options = {}) {
    let blobUrl = null;
    let cleanupNeeded = false;

    try {
      if (urlOrBlobOrSvg instanceof Blob) {
        blobUrl = URL.createObjectURL(urlOrBlobOrSvg);
        cleanupNeeded = true;
      } else if (typeof urlOrBlobOrSvg === 'string' && urlOrBlobOrSvg.trim().startsWith('<svg')) {
        const blob = new Blob([urlOrBlobOrSvg], { type: 'image/svg+xml;charset=utf-8' });
        blobUrl = URL.createObjectURL(blob);
        cleanupNeeded = true;
      } else if (typeof urlOrBlobOrSvg === 'string' && urlOrBlobOrSvg.startsWith('data:')) {
        const res = await fetch(urlOrBlobOrSvg);
        const blob = await res.blob();
        blobUrl = URL.createObjectURL(blob);
        cleanupNeeded = true;
      } else if (typeof urlOrBlobOrSvg === 'string' && urlOrBlobOrSvg.length > 0) {
        try {
          const fetchUrl = urlOrBlobOrSvg.includes('?') ? `${urlOrBlobOrSvg}&download=1` : `${urlOrBlobOrSvg}?download=1`;
          const res = await fetch(fetchUrl);
          if (res.ok) {
            const blob = await res.blob();
            blobUrl = URL.createObjectURL(blob);
            cleanupNeeded = true;
          } else {
            blobUrl = urlOrBlobOrSvg;
          }
        } catch (e) {
          blobUrl = urlOrBlobOrSvg;
        }
      }

      // Trigger browser anchor download
      if (blobUrl) {
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = filename || 'download.png';
        a.target = '_blank';
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
          if (a.parentNode) a.parentNode.removeChild(a);
          if (cleanupNeeded && blobUrl.startsWith('blob:')) {
            URL.revokeObjectURL(blobUrl);
          }
        }, 2000);
      }

      // Simultaneously trigger backend disk saving for desktop app
      if (options.serverSync !== false) {
        fetch('/api/save-image-to-downloads', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            filename: options.filename || (typeof urlOrBlobOrSvg === 'string' && !urlOrBlobOrSvg.startsWith('data:') && !urlOrBlobOrSvg.startsWith('<svg') ? urlOrBlobOrSvg : ''),
            image_url: typeof urlOrBlobOrSvg === 'string' && !urlOrBlobOrSvg.startsWith('data:') && !urlOrBlobOrSvg.startsWith('<svg') ? urlOrBlobOrSvg : '',
            image_b64: options.image_b64 || (typeof urlOrBlobOrSvg === 'string' && urlOrBlobOrSvg.startsWith('data:') ? urlOrBlobOrSvg : ''),
            svg_content: options.svg_content || (typeof urlOrBlobOrSvg === 'string' && urlOrBlobOrSvg.trim().startsWith('<svg') ? urlOrBlobOrSvg : ''),
            target_name: filename
          })
        }).then(r => r.json()).then(data => {
          if (data.status === 'success') {
            showToast(`Saved to Downloads: ${filename}`, 'success');
          } else {
            showToast(`Downloaded: ${filename}`, 'success');
          }
        }).catch(() => {
          showToast(`Downloaded: ${filename}`, 'success');
        });
      } else {
        showToast(`Downloaded: ${filename}`, 'success');
      }
    } catch (err) {
      console.error('Download error:', err);
      showToast('Download error: ' + err.message, 'error');
    }
  }

  function playAudioChime() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(587.33, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.15);
      gain.gain.setValueAtTime(0.08, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.25);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.25);
    } catch (e) {}
  }

  // --- Living Core State Engine (Jakub Antalik Thinking Orbs) ---
  let mainThinkingOrb = null;
  const pickerOrbInstances = [];

  const CORE_STATE_MAP = {
    idle: { state: 'breathing', tint: { r: 56, g: 189, b: 248 } },
    breathing: { state: 'breathing', tint: { r: 56, g: 189, b: 248 } },
    listening: { state: 'listening', tint: { r: 52, g: 211, b: 153 } },
    thinking: { state: 'composing', tint: { r: 14, g: 165, b: 233 } },
    composing: { state: 'composing', tint: { r: 14, g: 165, b: 233 } },
    searching: { state: 'searching', tint: { r: 251, g: 191, b: 36 } },
    solving: { state: 'solving', tint: { r: 168, g: 85, b: 247 } },
    shaping: { state: 'shaping', tint: { r: 244, g: 63, b: 94 } },
    working: { state: 'working', tint: { r: 99, g: 102, b: 241 } },
    connecting: { state: 'connecting', tint: { r: 20, g: 184, b: 166 } },
    weaving: { state: 'weaving', tint: { r: 59, g: 130, b: 246 } },
    offline: { state: 'breathing', tint: { r: 100, g: 116, b: 139 } }
  };

  function setCoreState(newState, customTint = null) {
    const config = CORE_STATE_MAP[newState] || { state: newState, tint: customTint || { r: 56, g: 189, b: 248 } };
    const orb = $('ciel-core-wrapper');
    if (orb) {
      orb.className = orb.className.replace(/\bstate-\w+\b/g, '').trim();
      orb.classList.add(`state-${config.state}`);
    }

    if (mainThinkingOrb) {
      mainThinkingOrb.setState(config.state);
      mainThinkingOrb.setTint(customTint || config.tint);
    }

    updateOrbStateUI(config.state);
  }

  function updateOrbStateUI(stateName) {
    const info = (window.THINKING_ORB_STATES || []).find(s => s.id === stateName) || {
      label: stateName.charAt(0).toUpperCase() + stateName.slice(1),
      desc: 'Cognitive Core Active',
      tint: { r: 56, g: 189, b: 248 }
    };

    if ($('hud-orb-mode')) $('hud-orb-mode').textContent = info.label;
    if ($('hud-orb-pulse') && info.tint) {
      const rgb = `rgb(${info.tint.r}, ${info.tint.g}, ${info.tint.b})`;
      $('hud-orb-pulse').style.background = rgb;
      $('hud-orb-pulse').style.boxShadow = `0 0 8px ${rgb}`;
    }
    if ($('ciel-orb-dot')) $('ciel-orb-dot').title = `Cognitive State: ${info.label}`;
    if ($('ciel-core-wrapper')) $('ciel-core-wrapper').title = `Ciel Living Core · ${info.label} (${info.desc})`;
  }

  function initThinkingOrb() {
    const canvas = $('ciel-core-canvas');
    if (!canvas || typeof ThinkingOrb === 'undefined') return;
    try {
      mainThinkingOrb = new ThinkingOrb(canvas, {
        size: 44,
        state: 'breathing',
        dark: true,
        tint: { r: 56, g: 189, b: 248 }
      });
      updateOrbStateUI('breathing');
    } catch (e) {
      console.warn('[ThinkingOrb Init Error]', e);
    }
  }

  function openOrbPickerModal() {
    const modal = $('orb-picker-modal');
    const grid = $('orb-picker-grid');
    if (!modal || !grid) return;

    modal.classList.add('active');
    grid.innerHTML = '';

    // Clean up past preview orb instances
    while (pickerOrbInstances.length) {
      const o = pickerOrbInstances.pop();
      try { o.destroy(); } catch (e) {}
    }

    const states = window.THINKING_ORB_STATES || [];
    const currentState = mainThinkingOrb ? mainThinkingOrb.state : 'breathing';

    states.forEach(s => {
      const item = document.createElement('div');
      item.className = `orb-picker-item ${s.id === currentState ? 'active' : ''}`;
      item.innerHTML = `
        <canvas class="orb-preview-canvas" width="44" height="44"></canvas>
        <div class="orb-picker-name">
          <i class="fas ${s.icon}" style="color: rgb(${s.tint.r}, ${s.tint.g}, ${s.tint.b});"></i>
          <span>${s.label}</span>
        </div>
        <div class="orb-picker-desc">${s.desc}</div>
      `;

      const previewCanvas = item.querySelector('.orb-preview-canvas');
      if (typeof ThinkingOrb !== 'undefined') {
        const previewOrb = new ThinkingOrb(previewCanvas, {
          size: 44,
          state: s.id,
          dark: true,
          tint: s.tint
        });
        pickerOrbInstances.push(previewOrb);
      }

      item.addEventListener('click', () => {
        setCoreState(s.id, s.tint);
        showToast(`Engaged Core State: ${s.label} — ${s.desc}`, 'success');
        modal.classList.remove('active');
      });

      grid.appendChild(item);
    });
  }

  // --- View Switching ---
  function switchView(viewName) {
    state.activeView = viewName;
    $$('.view-panel').forEach(p => p.classList.remove('active'));
    $$('.rail-btn').forEach(b => b.classList.remove('active'));

    const panel = $(`view-${viewName}`);
    const btn = $(`nav-${viewName}`);
    if (panel) panel.classList.add('active');
    if (btn) btn.classList.add('active');

    // Breadcrumb Update
    const titles = {
      chat: { title: 'Chat & Copilot', icon: 'fa-comment-dots' },
      tasks: { title: 'Autonomous Tasks', icon: 'fa-bolt' },
      ide: { title: 'Code IDE & Terminal', icon: 'fa-code' },
      primitive: { title: 'Primitive Geometric Studio', icon: 'fa-shapes' },
      diffusion: { title: 'AI Image Diffusion', icon: 'fa-palette' },
      memory: { title: 'Knowledge Vault', icon: 'fa-brain' },
      settings: { title: 'System HUD & Settings', icon: 'fa-sliders-h' }
    };
    const info = titles[viewName] || { title: 'Workspace', icon: 'fa-layer-group' };
    $('breadcrumb-icon').className = `fas ${info.icon}`;
    $('breadcrumb-title').textContent = info.title;

    // View specific hooks
    if (viewName === 'tasks') loadTasks();
    if (viewName === 'ide') loadIdeTree();
    if (viewName === 'diffusion') loadDiffusionModels();
    if (viewName === 'memory') loadMemories();
    if (viewName === 'settings') loadSettingsInfo();

    // Living Core state morphing per workstation view
    if (!state.isGenerating && !state.isListening) {
      const viewStateMap = {
        chat: 'breathing',
        tasks: 'working',
        ide: 'solving',
        primitive: 'shaping',
        diffusion: 'shaping',
        memory: 'connecting',
        settings: 'weaving'
      };
      if (viewStateMap[viewName]) {
        setCoreState(viewStateMap[viewName]);
      }
    }
  }

  // --- Model Routing & Fetching ---
  async function loadModels() {
    try {
      const res = await fetch('/api/tags');
      if (!res.ok) throw new Error('Models fetch failed');
      const data = await res.json();
      const models = data.models || [];
      state.models = models;

      const sel = $('model-select');
      sel.innerHTML = '';

      const autoOpt = document.createElement('option');
      autoOpt.value = 'ciel-auto';
      autoOpt.textContent = 'Auto Router (Smart Dispatch)';
      sel.appendChild(autoOpt);

      models.forEach(m => {
        if (m.name === 'ciel-auto') return;
        const opt = document.createElement('option');
        opt.value = m.name;
        opt.textContent = m.name;
        sel.appendChild(opt);
      });

      sel.value = state.selectedModel;
      $('ollama-badge').classList.remove('offline');
      $('ollama-status-text').textContent = 'Ollama Online';
    } catch (err) {
      console.warn('Ollama offline:', err);
      $('ollama-badge').classList.add('offline');
      $('ollama-status-text').textContent = 'Ollama Offline';
    }
  }

  // --- Telemetry Polling ---
  async function pollSysinfo() {
    try {
      const res = await fetch('/api/sysinfo');
      if (res.ok) {
        const data = await res.json();
        const cpu = Math.round(data.cpu_percent || 0);
        const ram = Math.round(data.ram_percent || 0);

        $('hud-cpu-val').textContent = `${cpu}%`;
        $('hud-cpu-bar').style.width = `${cpu}%`;
        $('hud-ram-val').textContent = `${ram}%`;
        $('hud-ram-bar').style.width = `${ram}%`;

        if ($('settings-cpu-val')) $('settings-cpu-val').textContent = `${cpu}%`;
        if ($('settings-ram-val')) $('settings-ram-val').textContent = `${ram}%`;
      }
      checkWakeState();
    } catch (e) {}
  }

  // --- Markdown Safe Parser Fallback ---
  function renderMarkdownSafely(text) {
    if (!text) return '';
    try {
      if (typeof marked !== 'undefined' && marked.parse) {
        return marked.parse(text);
      }
    } catch (e) {
      console.warn('[Markdown parse error, falling back to escapeHtml]', e);
    }
    return escapeHtml(text);
  }

  // --- CHAT WORKSPACE LOGIC ---
  function renderMessage(msg) {
    const feed = $('chat-feed');
    const row = document.createElement('div');
    row.className = `msg-row ${msg.role}`;
    row.id = `msg-${msg.id || Date.now()}`;

    const avatarHtml = msg.role === 'user' 
      ? `<div class="msg-avatar user"><i class="fas fa-user"></i></div>`
      : `<div class="msg-avatar ciel"><img src="/static/favicon.png?v=8.0" alt="Ciel"></div>`;

    const formattedContent = renderMarkdownSafely(msg.content || '');

    let toolCallsHtml = '';
    if (msg.toolCalls && msg.toolCalls.length) {
      toolCallsHtml = msg.toolCalls.map(tc => `
        <div class="tool-call-card">
          <div class="tool-call-header">
            <span><i class="fas fa-terminal"></i> ${escapeHtml(tc.name || 'Tool Execution')}</span>
            <span class="badge-success">Executed</span>
          </div>
          ${tc.args ? `<div class="tool-call-args">${escapeHtml(typeof tc.args === 'object' ? JSON.stringify(tc.args, null, 2) : tc.args)}</div>` : ''}
          ${tc.result ? `<div class="tool-call-result">â†’ ${escapeHtml(String(tc.result))}</div>` : ''}
        </div>
      `).join('');
    }

    row.innerHTML = `
      ${avatarHtml}
      <div class="msg-bubble">
        <div class="msg-body">${formattedContent}</div>
        <div class="tool-calls-container">${toolCallsHtml}</div>
        <div class="msg-actions">
          <button class="msg-action-btn btn-copy" title="Copy text"><i class="far fa-copy"></i></button>
          ${msg.role === 'ciel' ? `<button class="msg-action-btn btn-speak" title="Speak message"><i class="fas fa-volume-up"></i></button>` : ''}
        </div>
      </div>
    `;

    // Hook buttons
    row.querySelector('.btn-copy').addEventListener('click', () => {
      navigator.clipboard.writeText(msg.content);
      showToast('Copied to clipboard', 'success');
    });

    const speakBtn = row.querySelector('.btn-speak');
    if (speakBtn) {
      speakBtn.addEventListener('click', () => speakText(msg.content));
    }

    // Enhance code blocks with Run & Send to IDE
    enhanceCodeBlocks(row);

    feed.appendChild(row);
    feed.scrollTop = feed.scrollHeight;
    return row;
  }

  function enhanceCodeBlocks(container) {
    container.querySelectorAll('pre code').forEach((block) => {
      hljs.highlightElement(block);
      const pre = block.parentElement;
      if (pre.parentElement && pre.parentElement.classList.contains('code-block-wrapper')) return;

      const wrapper = document.createElement('div');
      wrapper.className = 'code-block-wrapper';
      
      const lang = block.className.replace('hljs', '').replace('language-', '').trim() || 'code';
      const header = document.createElement('div');
      header.className = 'code-header';
      header.innerHTML = `
        <span><i class="fas fa-code"></i> ${lang}</span>
        <div class="code-actions">
          <button class="code-btn btn-code-copy"><i class="far fa-copy"></i> Copy</button>
          <button class="code-btn btn-code-run"><i class="fas fa-play"></i> Run</button>
          <button class="code-btn btn-code-ide"><i class="fas fa-external-link-alt"></i> IDE</button>
        </div>
      `;

      pre.parentNode.insertBefore(wrapper, pre);
      wrapper.appendChild(header);
      wrapper.appendChild(pre);

      header.querySelector('.btn-code-copy').addEventListener('click', () => {
        navigator.clipboard.writeText(block.innerText);
        showToast('Code copied!', 'success');
      });

      header.querySelector('.btn-code-run').addEventListener('click', async () => {
        showToast('Executing code snippet...', 'info');
        try {
          const res = await fetch('/api/ide/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code: block.innerText, lang: lang })
          });
          const result = await res.json();
          let outBox = wrapper.querySelector('.code-run-output');
          if (!outBox) {
            outBox = document.createElement('div');
            outBox.className = 'tool-call-args code-run-output';
            outBox.style.marginTop = '8px';
            wrapper.appendChild(outBox);
          }
          outBox.textContent = (result.stdout || '') + (result.stderr || `[Exit Code: ${result.exit_code}]`);
        } catch (e) {
          showToast('Execution error: ' + e, 'error');
        }
      });

      header.querySelector('.btn-code-ide').addEventListener('click', () => {
        $('ide-code-input').value = block.innerText;
        $('ide-current-filename').textContent = 'snippet.' + (lang === 'python' ? 'py' : lang === 'javascript' ? 'js' : 'txt');
        switchView('ide');
        showToast('Opened in IDE', 'info');
      });
    });
  }

  async function sendChatMessage(promptText = null) {
    const input = $('chat-input');
    const text = (promptText || input.value).trim();
    if (!text || state.isGenerating) return;

    input.value = '';
    input.style.height = 'auto';

    // Add user message to UI
    const userMsg = { id: Date.now(), role: 'user', content: text };
    state.messages.push(userMsg);
    renderMessage(userMsg);

    // Prepare Ciel response placeholder
    const cielMsgId = Date.now() + 1;
    const cielMsg = { id: cielMsgId, role: 'ciel', content: '', toolCalls: [] };
    state.messages.push(cielMsg);
    const cielRow = renderMessage(cielMsg);
    const msgBody = cielRow.querySelector('.msg-body');
    const toolContainer = cielRow.querySelector('.tool-calls-container');

    // UI state adjustments with Border Beam (Libraries.dev)
    state.isGenerating = true;
    setCoreState('composing');
    const compGlass = $('composer-glass');
    if (compGlass) compGlass.classList.add('beam-active');
    $('btn-send-chat').style.display = 'none';
    $('btn-stop-chat').style.display = 'flex';

    abortController = new AbortController();

    try {
      const activeCode = state.activeFileContent || '';
      const activeFile = state.activeFile || '';

      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream'
        },
        body: JSON.stringify({
          messages: state.messages.filter(m => !m.wasAborted && (m.role !== 'ciel' || (m.content && m.content.trim()))).map(m => ({ role: m.role === 'ciel' ? 'assistant' : 'user', content: m.content })), 
          model: state.selectedModel,
          agent_mode: state.agentMode,
          active_code: activeCode,
          active_file: activeFile
        }),
        signal: abortController.signal
      });

      if (!response.ok) {
        throw new Error(`Server returned status ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // keep partial chunk

        for (const line of lines) {
          let trimmed = line.trim();
          if (!trimmed || trimmed.startsWith(':')) continue; // skip comments / keepalives

          if (trimmed.startsWith('data:')) {
            trimmed = trimmed.slice(5).trim();
          }

          if (!trimmed || trimmed === '[DONE]') continue;

          try {
            const data = JSON.parse(trimmed);

            // Handle content token
            if (data.content) {
              cielMsg.content += data.content;
              msgBody.innerHTML = renderMarkdownSafely(cielMsg.content);
              $('chat-feed').scrollTop = $('chat-feed').scrollHeight;
            }

            // Handle tool execution result
            if (data.tool_result) {
              setCoreState('solving');
              cielMsg.toolCalls.push({ name: 'Subsystem Tool', args: '', result: data.tool_result });
              toolContainer.innerHTML += `
                <div class="tool-call-card has-border-beam beam-active">
                  <div class="border-beam-glow"></div>
                  <div class="tool-call-header">
                    <span><i class="fas fa-terminal"></i> Subsystem Tool</span>
                    <span class="badge-success">Executed</span>
                  </div>
                  <div class="tool-call-result">â†’ ${escapeHtml(String(data.tool_result))}</div>
                </div>
              `;
            }

            // Handle routed model announcement
            if (data.routed_model) {
              showToast(`Task routed to: ${data.routed_model}`, 'info');
            }

          } catch (e) {
            // raw token text fallback if plain text
            cielMsg.content += trimmed;
            msgBody.innerHTML = renderMarkdownSafely(cielMsg.content);
          }
        }
      }

      // Format code blocks
      enhanceCodeBlocks(cielRow);

      // Auto speak if TTS is toggled on OR talk toggle is active
      if ((state.ttsEnabled || state.wakeActive) && cielMsg.content) {
        speakText(cielMsg.content);
      }

      // Save chat session
      saveCurrentChatSession();

    } catch (err) {
      if (err.name === 'AbortError') {
        cielMsg.wasAborted = true;
        userMsg.wasAborted = true;
        cielMsg.content = cielMsg.content ? (cielMsg.content + ' \n\n*[Generation stopped]*') : '*[Generation cancelled by Master]*';
        msgBody.innerHTML = renderMarkdownSafely(cielMsg.content);
        // Prune both the cancelled user question and assistant placeholder from state.messages
        // so Ollama will never receive the cancelled question on the next turn!
        const cIdx = state.messages.indexOf(cielMsg);
        if (cIdx !== -1) state.messages.splice(cIdx, 1);
        const uIdx = state.messages.indexOf(userMsg);
        if (uIdx !== -1) state.messages.splice(uIdx, 1);
      } else {
        cielMsg.content += `\n\nâš ï¸  **Error**: ${err.message}`;
        msgBody.innerHTML = renderMarkdownSafely(cielMsg.content);
        showToast('Chat error: ' + err.message, 'error');
      }
    } finally {
      state.isGenerating = false;
      setCoreState('breathing');
      const compGlass = $('composer-glass');
      if (compGlass) compGlass.classList.remove('beam-active');
      $('btn-send-chat').style.display = 'flex';
      $('btn-stop-chat').style.display = 'none';
      abortController = null;
    }
  }

  async function stopGeneration() {
    if (abortController) {
      abortController.abort();
    }
    try {
      fetch('/api/chat/abort', { method: 'POST' }).catch(() => {});
    } catch (e) {}
  }

  async function saveCurrentChatSession() {
    try {
      await fetch(`/api/chats/${state.currentChatId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: state.currentChatId,
          messages: state.messages,
          title: state.messages[0]?.content?.slice(0, 30) || 'New Conversation'
        })
      });
    } catch (e) {}
  }

  async function createNewChat() {
    state.currentChatId = 'chat_' + Date.now();
    state.messages = [];
    $('chat-feed').innerHTML = '';
    showToast('Started new conversation', 'info');
    const welcome = {
      id: Date.now(),
      role: 'ciel',
      content: "Greetings Master. I am Ciel, your autonomous AI partner. How may I assist your engineering, creative, or computational endeavors today?"
    };
    state.messages.push(welcome);
    renderMessage(welcome);
  }

  // --- CHAT HISTORY MODAL ---
  async function openChatHistory() {
    const modal = $('history-modal');
    const container = $('history-list-container');
    container.innerHTML = '<div style="padding: 20px; text-align: center;"><i class="fas fa-spinner fa-spin"></i> Loading conversations...</div>';
    modal.classList.add('active');

    try {
      const res = await fetch('/api/chats');
      const data = await res.json();
      const chats = data.chats || [];
      container.innerHTML = '';

      if (!chats.length) {
        container.innerHTML = '<div class="text-muted" style="padding: 30px; text-align: center;">No saved conversations found.</div>';
        return;
      }

      chats.forEach(c => {
        const item = document.createElement('div');
        item.className = `history-item ${c.id === state.currentChatId ? 'active' : ''}`;
        item.innerHTML = `
          <div>
            <div class="history-title">${escapeHtml(c.title || c.id)}</div>
            <div class="history-meta">${c.message_count || 0} messages · ${c.updated_at ? c.updated_at.slice(0, 16).replace('T', ' ') : ''}</div>
          </div>
          <button class="ide-action-btn btn-del-chat" style="color: var(--rose);" data-id="${c.id}"><i class="fas fa-trash-alt"></i></button>
        `;

        item.addEventListener('click', (e) => {
          if (e.target.closest('.btn-del-chat')) return;
          loadChatSession(c.id);
          modal.classList.remove('active');
        });

        item.querySelector('.btn-del-chat').addEventListener('click', async (e) => {
          e.stopPropagation();
          if (confirm('Delete this conversation?')) {
            await fetch(`/api/chats/${c.id}`, { method: 'DELETE' });
            showToast('Conversation deleted', 'info');
            openChatHistory();
          }
        });

        container.appendChild(item);
      });
    } catch (e) {
      container.innerHTML = `<div style="color: var(--rose); padding: 20px;">Failed to load history: ${e}</div>`;
    }
  }

  async function loadChatSession(chatId) {
    try {
      const res = await fetch(`/api/chats/${chatId}`);
      const data = await res.json();
      if (data && data.messages) {
        state.currentChatId = chatId;
        state.messages = data.messages;
        $('chat-feed').innerHTML = '';
        state.messages.forEach(m => renderMessage(m));
        showToast('Loaded conversation', 'success');
      }
    } catch (e) {
      showToast('Failed to load conversation: ' + e, 'error');
    }
  }

  // --- TTS & AUDIO SPEECH ---
  async function speakText(text, force = false) {
    if (!text || (!force && !state.ttsEnabled && !state.wakeActive)) return;
    try {
      if (state.currentAudio) {
        try { state.currentAudio.pause(); } catch(e) {}
        state.currentAudio = null;
      }
      const cleanText = text
        .replace(/```[\s\S]*?```/g, ' [code block] ')
        .replace(/[#*`_~><]/g, '')
        .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
        .replace(/\s+/g, ' ')
        .trim()
        .slice(0, 350);
      if (!cleanText) return;
      const res = await fetch('/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: cleanText })
      });
      const data = await res.json();
      if (data.status === 'success' && data.audio_url && (force || state.ttsEnabled || state.wakeActive)) {
        const audio = new Audio(data.audio_url);
        state.currentAudio = audio;
        audio.onended = () => { if (state.currentAudio === audio) state.currentAudio = null; };
        audio.play().catch(e => console.warn('Audio play prevented:', e));
      }
    } catch (e) {
      console.warn('TTS error:', e);
    }
  }

  function initTts() {
    const saved = localStorage.getItem('ciel_tts_enabled');
    state.ttsEnabled = (saved === 'true');
    const btn = $('btn-toggle-tts');
    if (btn) btn.classList.toggle('active', state.ttsEnabled);
  }

  function toggleTts() {
    state.ttsEnabled = !state.ttsEnabled;
    localStorage.setItem('ciel_tts_enabled', state.ttsEnabled ? 'true' : 'false');
    const btn = $('btn-toggle-tts');
    if (btn) btn.classList.toggle('active', state.ttsEnabled);
    if (!state.ttsEnabled && state.currentAudio) {
      try { state.currentAudio.pause(); state.currentAudio = null; } catch(e) {}
    }
    showToast(state.ttsEnabled ? 'Voice Responses ON' : 'Voice Responses Muted', 'info');
  }


  // =========================================================================
  // VOICE COMMAND CONFIRMATION FLOW
  // =========================================================================
  let pendingConfirmationCommand = null;
  let isConfirmingCommand = false;
  let confirmListenAbort = null;

  function closeConfirmationModal() {
    isConfirmingCommand = false;
    if (confirmListenAbort) {
      try { confirmListenAbort.abort(); } catch(e) {}
      confirmListenAbort = null;
    }
    const modal = $('command-confirm-modal');
    if (modal) modal.classList.remove('active');
  }

  function promptCommandConfirmation(command) {
    if (!command || !command.trim()) return;
    const cleanCmd = command.trim();
    pendingConfirmationCommand = cleanCmd;
    isConfirmingCommand = true;

    const modal = $('command-confirm-modal');
    const textEl = $('confirm-command-text');
    const subText = $('confirm-status-subtext');
    if (textEl) textEl.textContent = `"${cleanCmd}"`;
    if (subText) subText.innerHTML = '<i class="fas fa-microphone-lines" style="animation: pulseRec 1.2s infinite;"></i> <span>Listening for "Yes" to execute, or "No" if incorrect...</span>';
    if (modal) modal.classList.add('active');

    // Ciel verbally asks to confirm
    speakText(`Did you say: "${cleanCmd}"? Please confirm: say yes to execute, or say no if incorrect.`, true);

    // Automatically listen for confirmation answer after question finishes
    setTimeout(() => {
      if (isConfirmingCommand) {
        listenForConfirmationAnswer();
      }
    }, 2800);
  }

  async function listenForConfirmationAnswer() {
    if (!isConfirmingCommand) return;
    confirmListenAbort = new AbortController();

    try {
      const res = await fetch('/api/voice/listen_once', { 
        method: 'POST',
        signal: confirmListenAbort.signal 
      });
      if (!res.ok) return;
      const data = await res.json();
      if (!isConfirmingCommand) return;

      const answer = (data.transcript || '').toLowerCase().trim();
      const subText = $('confirm-status-subtext');

      if (!answer) {
        if (subText) subText.innerHTML = '<span>No response heard. Please say "Yes" or "No", or click below.</span>';
        return;
      }

      const positiveWords = ['yes', 'yeah', 'yep', 'correct', 'confirm', 'do it', 'right', 'sure', 'proceed', 'go ahead', 'okay', 'ok', 'execute', 'yup', 'aye'];
      const negativeWords = ['no', 'nope', 'wrong', 'not right', 'incorrect', 'cancel', 'stop', 'negative', 'false', 'nah', 'not that'];

      const isPositive = positiveWords.some(w => answer.includes(w));
      const isNegative = negativeWords.some(w => answer.includes(w));

      if (isPositive && !isNegative) {
        handleConfirmedCommand();
      } else if (isNegative) {
        handleRejectedCommand();
      } else {
        if (subText) subText.innerHTML = `<span>Heard "${answer}". Please say "Yes" to execute or "No" to re-prompt.</span>`;
        speakText(`I heard "${answer}". Is that a yes or a no, Master?`, true);
        setTimeout(() => {
          if (isConfirmingCommand) listenForConfirmationAnswer();
        }, 2200);
      }
    } catch (e) {
      if (e.name !== 'AbortError') console.warn('Confirmation listen error:', e);
    }
  }

  function handleConfirmedCommand() {
    const cmd = pendingConfirmationCommand;
    closeConfirmationModal();
    if (cmd) {
      speakText('Confirmed. Executing now, Master.', true);
      $('chat-input').value = cmd;
      sendChatMessage();
      showToast(`Executing confirmed command: "${cmd}"`, 'success');
    }
  }

  function handleRejectedCommand() {
    closeConfirmationModal();
    speakText('Understood. What is the correct command, Master?', true);
    showToast('Command cancelled. Please speak the correct command...', 'info');

    // Wait for question to finish speaking, then open mic to capture the correct command
    setTimeout(async () => {
      try {
        const res = await fetch('/api/voice/listen_once', { method: 'POST' });
        if (res.ok) {
          const data = await res.json();
          const newCmd = (data.transcript || '').trim();
          if (newCmd && newCmd.length >= 2) {
            promptCommandConfirmation(newCmd);
          } else {
            showToast('No speech detected', 'info');
            speakText('I did not catch that, Master. Whenever you are ready, please ask again.', true);
          }
        }
      } catch (e) {
        console.warn('Re-listen error:', e);
      }
    }, 2600);
  }


  // --- VOICE CAPTURE (MIC) WITH VOICE GLOW ---
  let listenAbortController = null;

  async function triggerVoiceInput() {
    // Toggle behavior: If already listening, clicking again cancels / stops recording immediately!
    if (state.isListening) {
      if (listenAbortController) {
        try { listenAbortController.abort(); } catch(e) {}
        listenAbortController = null;
      }
      // Immediately tell backend to abort recording & PyAudio stream
      fetch('/api/voice/listen_cancel', { method: 'POST' }).catch(() => {});
      state.isListening = false;
      setCoreState('breathing');
      const voiceGlow = $('voice-glow-beam');
      if (voiceGlow) voiceGlow.classList.remove('active');
      const voiceModal = $('voice-modal');
      if (voiceModal) voiceModal.classList.remove('active');
      const micBtn = $('btn-mic');
      if (micBtn) micBtn.classList.remove('recording');
      const compMicBtn = $('btn-composer-mic');
      if (compMicBtn) compMicBtn.classList.remove('recording');
      showToast('Voice input stopped', 'info');
      // Resume wake word detection if it was enabled
      fetch('/api/voice/resume_wake', { method: 'POST' }).catch(() => {});
      return;
    }

    state.isListening = true;
    setCoreState('listening');
    listenAbortController = new AbortController();
    
    const voiceGlow = $('voice-glow-beam');
    if (voiceGlow) voiceGlow.classList.add('active');
    const voiceModal = $('voice-modal');
    if (voiceModal) voiceModal.classList.add('active');
    
    const micBtn = $('btn-mic');
    if (micBtn) micBtn.classList.add('recording');
    const compMicBtn = $('btn-composer-mic');
    if (compMicBtn) compMicBtn.classList.add('recording');

    try {
      const res = await fetch('/api/voice/listen_once', { 
        method: 'POST',
        signal: listenAbortController.signal 
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      if (data.status === 'success' && data.transcript) {
        const spoken = data.transcript.trim();
        $('chat-input').value = spoken;
        $('chat-input').focus();
        showToast(`Heard: "${spoken}"`, 'success');
        promptCommandConfirmation(spoken);
      } else {
        showToast('No speech detected', 'info');
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        showToast('Voice capture: ' + err.message, 'error');
      }
    } finally {
      state.isListening = false;
      listenAbortController = null;
      setCoreState('breathing');
      if (voiceGlow) voiceGlow.classList.remove('active');
      if (voiceModal) voiceModal.classList.remove('active');
      if (micBtn) micBtn.classList.remove('recording');
      if (compMicBtn) compMicBtn.classList.remove('recording');
    }
  }

  // --- WAKE WORD CONTROLLER & POLLER ---
  let isTogglingWake = false;
  let lastWakeToggleTime = 0;
  let pendingWakeTarget = null;

  function updateWakeUI(active) {
    state.wakeActive = !!active;
    const btn = $('btn-toggle-wake');
    if (btn) {
      btn.classList.toggle('active', state.wakeActive);
      btn.title = state.wakeActive 
        ? "Wake Word 'Hey Ciel': ACTIVE (Click to Pause)" 
        : "Wake Word 'Hey Ciel': PAUSED (Click to Activate)";
    }
  }

  async function checkWakeState() {
    try {
      const res = await fetch('/api/voice/wake_status');
      if (res.ok) {
        const data = await res.json();
        // Don't override if user recently clicked toggle (< 4.0s)
        if (Date.now() - lastWakeToggleTime > 4000) {
          updateWakeUI(data.wake_active);
          if (data.wake_active && !wakePollTimer) {
            wakePollTimer = setInterval(pollWakeWord, 1000);
          } else if (!data.wake_active && wakePollTimer) {
            clearInterval(wakePollTimer);
            wakePollTimer = null;
          }
        }
      }
    } catch(e) {}
  }

  async function pollWakeWord() {
    if (!state.wakeActive) {
      if (wakePollTimer) { clearInterval(wakePollTimer); wakePollTimer = null; }
      return;
    }
    try {
      const res = await fetch('/api/voice/wake_poll');
      if (!res.ok) return;
      const data = await res.json();
      
      // Update UI if changed from external source (e.g. System Tray menu) and user didn't just click (< 4.0s)
      if (typeof data.wake_active === 'boolean' && Date.now() - lastWakeToggleTime > 4000) {
        if (data.wake_active !== state.wakeActive) {
          updateWakeUI(data.wake_active);
          localStorage.setItem('ciel_wake_enabled', data.wake_active ? 'true' : 'false');
          if (!data.wake_active && wakePollTimer) {
            clearInterval(wakePollTimer);
            wakePollTimer = null;
            return;
          }
        }
      }

      if (state.wakeActive && data.status === 'event' && data.event) {
        if (document.hidden || !document.hasFocus()) {
          fetch('/api/system/summon', { method: 'POST' }).catch(() => {});
        }
        const directive = (data.event.directive || '').trim();
        if (directive && directive.length >= 2) {
          showToast(`Wake directive: "${directive}"`, 'info');
          promptCommandConfirmation(directive);
        } else {
          showToast('Wake word detected — listening...', 'info');
          speakText('Yes, Master? I am listening.', true);
          triggerVoiceInput();
        }
      }
    } catch(e) {}
  }

  async function toggleWakeWord() {
    const target = !state.wakeActive;
    lastWakeToggleTime = Date.now();

    // 1. Instant optimistic UI feedback — 0ms immediate response on every click
    updateWakeUI(target);
    localStorage.setItem('ciel_wake_enabled', target ? 'true' : 'false');
    if (target) {
      state.ttsEnabled = true;
      localStorage.setItem('ciel_tts_enabled', 'true');
      const ttsBtn = $('btn-toggle-tts');
      if (ttsBtn) ttsBtn.classList.add('active');
      speakText('Voice conversation active. I am listening, Master.', true);
    } else {
      speakText('Voice paused.', true);
    }
    showToast(target ? 'Wake word "Hey Ciel" Active' : 'Wake word paused', target ? 'success' : 'info');

    // 2. Manage polling timer immediately
    if (target) {
      if (!wakePollTimer) wakePollTimer = setInterval(pollWakeWord, 1000);
    } else {
      if (wakePollTimer) { clearInterval(wakePollTimer); wakePollTimer = null; }
    }

    // 3. Queue network synchronization to prevent concurrent HTTP races
    if (isTogglingWake) {
      pendingWakeTarget = target;
      return;
    }

    isTogglingWake = true;
    try {
      let desired = target;
      while (true) {
        const res = await fetch('/api/voice/wake_toggle', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enable: desired })
        });
        const data = await res.json();
        if (typeof data.wake_active === 'boolean') {
          if (pendingWakeTarget === null) {
            updateWakeUI(data.wake_active);
            localStorage.setItem('ciel_wake_enabled', data.wake_active ? 'true' : 'false');
          }
        }
        if (pendingWakeTarget !== null) {
          desired = pendingWakeTarget;
          pendingWakeTarget = null;
        } else {
          break;
        }
      }
    } catch (e) {
      updateWakeUI(!target);
      localStorage.setItem('ciel_wake_enabled', (!target) ? 'true' : 'false');
      showToast('Wake toggle network error', 'error');
    } finally {
      isTogglingWake = false;
    }
  }

  // --- TASKS CENTER LOGIC ---
  async function loadTasks() {
    try {
      const res = await fetch('/api/tasks');
      const data = await res.json();
      const tasks = data.tasks || [];
      state.tasks = tasks;

      const grid = $('tasks-grid');
      grid.innerHTML = '';

      if (!tasks.length) {
        grid.innerHTML = '<div class="text-muted" style="grid-column: 1/-1; padding: 40px; text-align: center;">No active background tasks.</div>';
        $('task-badge').style.display = 'none';
        return;
      }

      const runningCount = tasks.filter(t => t.status === 'running').length;
      if (runningCount > 0) {
        $('task-badge').textContent = runningCount;
        $('task-badge').style.display = 'block';
      } else {
        $('task-badge').style.display = 'none';
      }

      tasks.forEach(task => {
        const card = document.createElement('div');
        card.className = 'task-card';
        card.innerHTML = `
          <div class="task-card-header">
            <span class="task-type-badge">${escapeHtml(task.task_type || 'task')}</span>
            <span class="task-status-pill ${task.status}">${task.status}</span>
          </div>
          <div class="task-msg-preview">${escapeHtml(task.message || task.id)}</div>
          <div class="task-progress-bar">
            <div class="task-progress-fill" style="width: ${task.progress || 0}%"></div>
          </div>
          <div class="task-card-footer">
            <span>Progress: ${task.progress || 0}%</span>
            ${task.status === 'running' ? `<button class="btn-cancel-task" data-id="${task.id}"><i class="fas fa-stop"></i> Cancel</button>` : ''}
          </div>
        `;

        const cancelBtn = card.querySelector('.btn-cancel-task');
        if (cancelBtn) {
          cancelBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            await fetch(`/api/tasks/${task.id}/cancel`, { method: 'POST' });
            showToast('Cancelled task ' + task.id, 'info');
            loadTasks();
          });
        }

        grid.appendChild(card);
      });
    } catch (e) {
      console.warn('Error loading tasks:', e);
    }
  }

  // --- CODE IDE WORKSPACE LOGIC ---
  async function loadIdeTree(dirPath = '') {
    try {
      const url = dirPath ? `/api/ide/tree?path=${encodeURIComponent(dirPath)}` : '/api/ide/tree';
      const res = await fetch(url);
      const data = await res.json();
      const list = $('ide-tree-list');
      list.innerHTML = '';

      if (data.status === 'success' && data.items) {
        state.currentWorkspacePath = data.current_path || '';

        // If parent path available, add Up row
        if (data.parent_path) {
          const upRow = document.createElement('div');
          upRow.className = 'tree-item';
          upRow.innerHTML = `<i class="fas fa-level-up-alt" style="color: var(--amber);"></i> <span>.. (Parent Folder)</span>`;
          upRow.addEventListener('click', () => loadIdeTree(data.parent_path));
          list.appendChild(upRow);
        }

        data.items.forEach(item => {
          const row = document.createElement('div');
          row.className = `tree-item ${item.path === state.activeFile ? 'active' : ''}`;
          const isDir = item.type === 'directory' || item.is_dir;
          const icon = isDir ? 'fa-folder' : 'fa-file-code';
          const iconColor = isDir ? 'color: var(--amber);' : 'color: var(--cyan);';
          row.innerHTML = `<i class="fas ${icon}" style="${iconColor}"></i> <span>${escapeHtml(item.name)}</span>`;
          
          if (isDir) {
            row.addEventListener('click', () => loadIdeTree(item.path));
          } else {
            row.addEventListener('click', () => openIdeFile(item.path, item.name));
          }
          list.appendChild(row);
        });
      }
    } catch (e) {
      console.warn('Failed to load IDE tree:', e);
    }
  }

  async function openIdeFile(filePath, fileName) {
    try {
      const res = await fetch('/api/ide/read', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: filePath })
      });
      const data = await res.json();
      if (data.status === 'success') {
        state.activeFile = filePath;
        state.activeFileContent = data.content;
        $('ide-code-input').value = data.content;
        $('ide-current-filename').textContent = fileName;
        showToast('Loaded ' + fileName, 'success');
        // highlight tree active item
        $$('.tree-item').forEach(el => el.classList.remove('active'));
      }
    } catch (e) {
      showToast('Failed to open file: ' + e, 'error');
    }
  }

  async function saveIdeFile() {
    if (!state.activeFile) {
      showToast('No active file selected. Create a file first.', 'warning');
      return;
    }
    const content = $('ide-code-input').value;
    try {
      const res = await fetch('/api/ide/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: state.activeFile, content: content })
      });
      const data = await res.json();
      if (data.status === 'success') {
        state.activeFileContent = content;
        showToast('Saved ' + state.activeFile, 'success');
      } else {
        showToast('Save failed: ' + data.message, 'error');
      }
    } catch (e) {
      showToast('Save error: ' + e, 'error');
    }
  }

  async function createIdeFile() {
    const filename = prompt('Enter new file name (e.g., test.py, index.js):');
    if (!filename || !filename.trim()) return;

    try {
      const res = await fetch('/api/ide/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          folder: state.currentWorkspacePath || undefined,
          filename: filename.trim()
        })
      });
      const data = await res.json();
      if (data.status === 'success') {
        showToast('Created ' + filename, 'success');
        loadIdeTree(state.currentWorkspacePath);
        openIdeFile(data.path, filename);
      } else {
        showToast('File creation failed: ' + data.message, 'error');
      }
    } catch (e) {
      showToast('Creation error: ' + e, 'error');
    }
  }

  async function runIdeCode() {
    const code = $('ide-code-input').value;
    const term = $('ide-terminal-output');
    term.textContent = 'Executing...\n';
    try {
      const res = await fetch('/api/ide/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: code, path: state.activeFile })
      });
      const data = await res.json();
      term.textContent = (data.stdout || '') + (data.stderr || '') + `\n[Process terminated with exit code: ${data.exit_code}]`;
    } catch (e) {
      term.textContent = `Execution failed: ${e}`;
    }
  }

  // --- PRIMITIVE GEOMETRIC ART STUDIO (fogleman/primitive) ---
  function setupPrimitiveStudio() {
    $$('.mode-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        $$('.mode-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.primitive.mode = btn.dataset.mode;
      });
    });

    const shapesSlider = $('prim-shapes-slider');
    const shapesVal = $('prim-shapes-val');
    shapesSlider.addEventListener('input', () => {
      shapesVal.textContent = shapesSlider.value;
      state.primitive.numShapes = parseInt(shapesSlider.value, 10);
    });

    const alphaSlider = $('prim-alpha-slider');
    const alphaVal = $('prim-alpha-val');
    alphaSlider.addEventListener('input', () => {
      alphaVal.textContent = alphaSlider.value;
      state.primitive.alpha = parseFloat(alphaSlider.value);
    });

    const dropzone = $('prim-dropzone');
    const fileInput = $('prim-file-input');

    dropzone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => handlePrimitiveFile(e.target.files[0]));

    dropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropzone.classList.add('dragover');
    });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.classList.remove('dragover');
      if (e.dataTransfer.files.length) {
        handlePrimitiveFile(e.dataTransfer.files[0]);
      }
    });

    $$('.preset-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const path = chip.dataset.path;
        state.primitive.imagePath = path;
        state.primitive.imageB64 = '';
        $('prim-preview-thumb').src = path;
        $('prim-preview-thumb').style.display = 'block';
        $('prim-drop-prompt').style.display = 'none';
        showToast('Loaded preset: ' + chip.textContent, 'info');
      });
    });

    $('btn-gen-primitive').addEventListener('click', generatePrimitiveArt);

    $('btn-download-svg').addEventListener('click', () => {
      if (!state.primitive.svgContent) {
        showToast('No vector SVG to download.', 'warning');
        return;
      }
      const fn = `primitive_${state.primitive.mode || 'shapes'}_${Date.now()}.svg`;
      triggerDownload(state.primitive.svgContent, fn, {
        svg_content: state.primitive.svgContent
      });
    });

    $('btn-download-png').addEventListener('click', () => {
      if (!state.primitive.pngPath) {
        showToast('No PNG to download.', 'warning');
        return;
      }
      const fn = `primitive_${state.primitive.mode || 'shapes'}_${Date.now()}.png`;
      triggerDownload(state.primitive.pngPath, fn, {
        filename: state.primitive.pngPath
      });
    });
  }

  function handlePrimitiveFile(file) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      const b64 = e.target.result;
      state.primitive.imageB64 = b64;
      state.primitive.imagePath = '';
      $('prim-preview-thumb').src = b64;
      $('prim-preview-thumb').style.display = 'block';
      $('prim-drop-prompt').style.display = 'none';
      showToast('Image uploaded: ' + file.name, 'success');
    };
    reader.readAsDataURL(file);
  }

  async function generatePrimitiveArt() {
    if (!state.primitive.imagePath && !state.primitive.imageB64) {
      showToast('Please select or upload an image first.', 'warning');
      return;
    }

    const genBtn = $('btn-gen-primitive');
    genBtn.disabled = true;
    genBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generating Primitives...';
    setCoreState('thinking');

    try {
      const payload = {
        image_path: state.primitive.imagePath,
        image_base64: state.primitive.imageB64,
        mode: state.primitive.mode,
        num_shapes: state.primitive.numShapes,
        alpha: state.primitive.alpha,
        async_task: state.primitive.asyncTask
      };

      const res = await fetch('/api/primitive/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      if (!res.ok || data.status === 'error') {
        throw new Error(data.message || 'Generation failed');
      }

      state.primitive.svgContent = data.svg_content || '';
      state.primitive.svgPath = data.svg_path || '';
      state.primitive.pngPath = data.png_path || '';

      const renderBox = $('prim-svg-display');
      renderBox.innerHTML = data.svg_content || `<img src="${data.png_path}" alt="Primitive result">`;

      $('prim-shape-count-metric').textContent = data.num_shapes || state.primitive.numShapes;
      $('prim-time-metric').textContent = (data.duration_seconds || 1.2) + 's';
      $('prim-actions-bar').style.display = 'flex';

      showToast('Primitive Art Generated Successfully!', 'success');
      playAudioChime();
    } catch (err) {
      showToast('Primitive generation error: ' + err.message, 'error');
    } finally {
      genBtn.disabled = false;
      genBtn.innerHTML = '<i class="fas fa-play"></i> Generate Geometric Art';
      setCoreState('idle');
    }
  }

  // --- DIFFUSION AI IMAGE STUDIO (with Model Selector) ---
  async function loadDiffusionModels() {
    try {
      const res = await fetch('/api/image-models');
      const data = await res.json();
      const models = data.models || [];
      state.imageModels = models;

      const sel = $('diff-model-select');
      sel.innerHTML = '';

      models.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m.key;
        opt.textContent = `${m.label} [${m.badge}]`;
        if (m.key === state.selectedImageModel) opt.selected = true;
        sel.appendChild(opt);
      });

      updateSelectedDiffusionModel(sel.value);
    } catch (e) {
      console.warn('Image models load error:', e);
    }
  }

  function updateSelectedDiffusionModel(modelKey) {
    state.selectedImageModel = modelKey;
    const modelObj = state.imageModels.find(m => m.key === modelKey);
    const badge = $('diff-model-badge');
    const stepsSlider = $('diff-steps-slider');
    const stepsVal = $('diff-steps-val');

    if (modelObj) {
      badge.textContent = modelObj.badge;
      badge.className = modelObj.downloaded ? 'badge-ready' : 'badge-download';
      stepsSlider.value = modelObj.default_steps || 20;
      stepsVal.textContent = stepsSlider.value;
    }
  }

  function setupDiffusionStudio() {
    if ($('diff-model-select')) {
      $('diff-model-select').addEventListener('change', (e) => {
        updateSelectedDiffusionModel(e.target.value);
      });
    }

    if ($('diff-steps-slider')) {
      $('diff-steps-slider').addEventListener('input', (e) => {
        if ($('diff-steps-val')) $('diff-steps-val').textContent = e.target.value;
      });
    }

    // Dynamic Upscaler Button label and icon
    const upscalerMethodSel = $('diff-upscaler-method');
    const updateUpscaleBtnLabel = () => {
      const upBtn = $('btn-upscale-diff');
      if (!upBtn) return;
      const method = upscalerMethodSel ? upscalerMethodSel.value : 'realesrgan';
      if (method === 'latent_diffusion') {
        upBtn.innerHTML = '<i class="fas fa-wand-magic-sparkles"></i> Refine & Upscale 2× (Latent Diffusion)';
      } else {
        upBtn.innerHTML = '<i class="fas fa-wand-magic-sparkles"></i> Upscale 4× (Real-ESRGAN HD)';
      }
    };
    if (upscalerMethodSel) {
      upscalerMethodSel.addEventListener('change', updateUpscaleBtnLabel);
      updateUpscaleBtnLabel();
    }

    // Real-ESRGAN / Latent Diffusion Anime Upscale Button
    if ($('btn-upscale-diff')) {
      $('btn-upscale-diff').addEventListener('click', async () => {
        if (!state.diffusion.imageUrl && !state.diffusion.imagePath) {
          showToast('Please generate an image first before upscaling.', 'warning');
          return;
        }

        const upBtn = $('btn-upscale-diff');
        const method = upscalerMethodSel ? upscalerMethodSel.value : 'realesrgan';
        const isLatent = method === 'latent_diffusion';

        upBtn.disabled = true;
        upBtn.innerHTML = isLatent
          ? '<i class="fas fa-spinner fa-spin"></i> Refining Details (Latent Diffusion)...'
          : '<i class="fas fa-spinner fa-spin"></i> Upscaling 4× (Real-ESRGAN HD)...';
        setCoreState('thinking');
        showToast(isLatent ? 'Refining details with Latent Diffusion Resampler...' : 'Running Real-ESRGAN Anime Super-Resolution...', 'info');

        const container = $('diff-result-container');
        const previousImageHtml = container ? container.innerHTML : '';
        if (container) {
          container.innerHTML = `
            <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px; padding: 40px; text-align: center;">
              <div style="width: 52px; height: 52px; border: 3px solid rgba(236,72,153,0.25); border-top-color: #ec4899; border-radius: 50%; animation: spin 0.8s linear infinite;"></div>
              <div style="font-weight: 600; font-size: 15px; color: #fff;">${isLatent ? 'Latent Diffusion Resampling (2×)...' : 'Real-ESRGAN Anime 4× Neural Upscaling...'}</div>
              <div style="font-size: 12px; color: var(--text-secondary);">Synthesizing high-frequency anime linework & crisp cel-shading</div>
            </div>
          `;
        }

        try {
          const res = await fetch('/api/upscale-image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              filename: state.diffusion.imagePath,
              image_url: state.diffusion.imageUrl,
              scale: isLatent ? 2 : 4,
              upscaler: method,
              prompt: $('diff-prompt') ? $('diff-prompt').value : '',
              negative_prompt: $('diff-neg-prompt') ? $('diff-neg-prompt').value : '',
              image_model: $('diff-model-select') ? $('diff-model-select').value : 'counterfeit-v3'
            })
          });
          const data = await res.json();
          if (!res.ok || data.status === 'error') {
            throw new Error(data.message || 'Upscaling failed');
          }

          state.diffusion.imageUrl = data.image_url;
          state.diffusion.imagePath = data.filename;
          if (data.image_b64) state.diffusion.imageB64 = data.image_b64;

          if (container) {
            container.innerHTML = `<img src="${data.image_url}" alt="Upscaled Anime Artwork" style="max-width: 100%; max-height: 440px; border-radius: 8px; box-shadow: var(--shadow-md); cursor: zoom-in;" title="Click to view full size">`;
          }

          showToast(data.message || `Enhanced & Upscaled to ${data.dimensions || '4×'} HD!`, 'success');
          playAudioChime();
        } catch (err) {
          showToast('Upscale error: ' + err.message, 'error');
          if (container && previousImageHtml) {
            container.innerHTML = previousImageHtml;
          }
        } finally {
          upBtn.disabled = false;
          updateUpscaleBtnLabel();
          setCoreState('idle');
        }
      });
    }

    // Copilot AI Enhance Prompt Button
    if ($('btn-enhance-prompt')) {
      $('btn-enhance-prompt').addEventListener('click', async () => {
        const promptInput = $('diff-prompt');
        if (!promptInput) return;
        const raw = (promptInput.value || '').trim();

        const btn = $('btn-enhance-prompt');
        btn.disabled = true;
        const originalText = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Enhancing...';

        try {
          const res = await fetch('/api/enhance-prompt', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt: raw || '1girl, anime heroine' })
          });
          const data = await res.json();
          if (data.status === 'success' && data.enhanced_prompt) {
            promptInput.value = data.enhanced_prompt;
            showToast('Prompt expanded with Copilot AI!', 'success');
          } else {
            showToast(data.message || 'Failed to enhance prompt', 'warning');
          }
        } catch (err) {
          showToast('Enhance prompt failed: ' + err.message, 'error');
        } finally {
          btn.disabled = false;
          btn.innerHTML = originalText;
        }
      });
    }

    // Quick Anime Style Chips
    $$('.diff-style-chips .style-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const tag = chip.getAttribute('data-tag');
        const input = $('diff-prompt');
        if (!tag || !input) return;
        const current = input.value.trim();
        if (!current) {
          input.value = tag;
        } else if (!current.toLowerCase().includes(tag.toLowerCase())) {
          input.value = current + ', ' + tag;
        }
        showToast(`Added style: ${chip.textContent.trim()}`, 'info');
        input.focus();
      });
    });

    // Reset / Clear Workbench Button
    if ($('btn-diff-clear')) {
      $('btn-diff-clear').addEventListener('click', () => {
        if ($('diff-prompt')) $('diff-prompt').value = '';
        state.diffusion.imageUrl = '';
        state.diffusion.imagePath = '';
        state.diffusion.imageB64 = '';
        const container = $('diff-result-container');
        if (container) {
          container.innerHTML = `
            <div class="text-muted" style="text-align: center;">
              <i class="fas fa-image" style="font-size: 38px; color: var(--text-muted); margin-bottom: 12px;"></i>
              <p>Generated anime illustration will render here.</p>
            </div>
          `;
        }
        if ($('diff-actions-bar')) $('diff-actions-bar').style.display = 'none';
        showToast('Image studio workbench reset.', 'info');
      });
    }

    // Keyboard shortcut (Ctrl+Enter) on prompt textarea
    if ($('diff-prompt')) {
      $('diff-prompt').addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
          e.preventDefault();
          generateDiffusionImage();
        }
      });
    }

    // Click on canvas image opens Fullscreen Modal
    if ($('diff-result-container')) {
      $('diff-result-container').addEventListener('click', (e) => {
        if (e.target && e.target.tagName === 'IMG' && state.diffusion.imageUrl) {
          if ($('image-modal-src')) $('image-modal-src').src = state.diffusion.imageUrl;
          if ($('image-modal')) $('image-modal').classList.add('active');
        }
      });
    }

    // Generate Button
    if ($('btn-gen-diffusion')) {
      $('btn-gen-diffusion').addEventListener('click', generateDiffusionImage);
    }

    // Download Button
    if ($('btn-download-diff')) {
      $('btn-download-diff').addEventListener('click', () => {
        if (!state.diffusion.imageUrl) {
          showToast('No generated image to download.', 'warning');
          return;
        }
        const ext = state.diffusion.imagePath ? state.diffusion.imagePath.split('.').pop() : 'png';
        const fn = `ciel_${state.selectedImageModel || 'anime'}_${Date.now()}.${ext}`;
        triggerDownload(state.diffusion.imageUrl, fn, {
          filename: state.diffusion.imagePath,
          image_b64: state.diffusion.imageB64
        });
      });
    }

    // Fullscreen View
    if ($('btn-view-diff-fullscreen')) {
      $('btn-view-diff-fullscreen').addEventListener('click', () => {
        if (!state.diffusion.imageUrl) return;
        if ($('image-modal-src')) $('image-modal-src').src = state.diffusion.imageUrl;
        if ($('image-modal')) $('image-modal').classList.add('active');
      });
    }

    if ($('btn-close-img-modal')) {
      $('btn-close-img-modal').addEventListener('click', () => {
        if ($('image-modal')) $('image-modal').classList.remove('active');
      });
    }

    // Close image modal when clicking the backdrop
    const imgModal = $('image-modal');
    if (imgModal) {
      imgModal.addEventListener('click', (e) => {
        if (e.target === imgModal) {
          imgModal.classList.remove('active');
        }
      });
    }

    // Close image modal on Escape key
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        const modal = $('image-modal');
        if (modal && modal.classList.contains('active')) {
          modal.classList.remove('active');
        }
      }
    });

    // Vectorize in Primitive
    if ($('btn-diff-to-primitive')) {
      $('btn-diff-to-primitive').addEventListener('click', () => {
        if (!state.diffusion.imagePath && !state.diffusion.imageUrl) return;
        state.primitive.imagePath = state.diffusion.imagePath || state.diffusion.imageUrl;
        if (state.diffusion.imageB64) state.primitive.imageB64 = state.diffusion.imageB64;
        if ($('prim-preview-thumb')) {
          $('prim-preview-thumb').src = state.diffusion.imageUrl;
          $('prim-preview-thumb').style.display = 'block';
        }
        if ($('prim-drop-prompt')) $('prim-drop-prompt').style.display = 'none';
        switchView('primitive');
        showToast('Image loaded into Primitive Studio!', 'success');
      });
    }
  }

  async function generateDiffusionImage() {
    const promptInput = $('diff-prompt');
    const prompt = promptInput ? promptInput.value.trim() : '';
    if (!prompt) {
      showToast('Please enter an image prompt.', 'warning');
      if (promptInput) promptInput.focus();
      return;
    }

    const negPrompt = $('diff-neg-prompt') ? $('diff-neg-prompt').value.trim() : '';
    const modelKey = $('diff-model-select') ? $('diff-model-select').value : 'counterfeit-v3';
    const resVal = $('diff-res-select') ? $('diff-res-select').value.split('x') : ['512', '768'];
    const width = parseInt(resVal[0], 10) || 512;
    const height = parseInt(resVal[1], 10) || 768;
    const steps = $('diff-steps-slider') ? parseInt($('diff-steps-slider').value, 10) : 20;

    const btn = $('btn-gen-diffusion');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Rendering Diffusion Image...';
    }
    setCoreState('thinking');

    const container = $('diff-result-container');
    if (container) {
      container.innerHTML = `
        <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px; padding: 40px; text-align: center;">
          <div style="width: 52px; height: 52px; border: 3px solid rgba(168,85,247,0.25); border-top-color: #a855f7; border-radius: 50%; animation: spin 0.8s linear infinite;"></div>
          <div style="font-weight: 600; font-size: 15px; color: #fff;">Synthesizing Anime Artwork...</div>
          <div style="font-size: 12px; color: var(--cyan);"><i class="fas fa-layer-group"></i> Model: ${modelKey} · ${width}×${height} · ${steps} Steps</div>
          <div style="font-size: 11px; color: var(--text-muted);">Iterative latent denoising running locally...</div>
        </div>
      `;
    }

    try {
      const res = await fetch('/api/generate-image', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: prompt,
          negative_prompt: negPrompt,
          image_model: modelKey,
          width: width,
          height: height,
          steps: steps
        })
      });

      const data = await res.json();
      if (!res.ok || data.status === 'error') {
        throw new Error(data.message || 'Diffusion generation failed');
      }

      state.diffusion.imageUrl = data.image_url;
      state.diffusion.imagePath = data.filename;
      state.diffusion.imageB64 = data.image_b64 || '';

      if (container) {
        container.innerHTML = `<img src="${data.image_url}" alt="AI Generated Image" style="max-width: 100%; max-height: 440px; border-radius: 8px; box-shadow: var(--shadow-md); cursor: zoom-in;" title="Click to view full size">`;
      }

      if ($('diff-actions-bar')) $('diff-actions-bar').style.display = 'flex';
      showToast('Anime Art Generated Successfully!', 'success');
      playAudioChime();
    } catch (err) {
      showToast('Image generation error: ' + err.message, 'error');
      if (container) {
        container.innerHTML = `
          <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; padding: 30px; text-align: center; color: var(--rose);">
            <i class="fas fa-triangle-exclamation" style="font-size: 32px;"></i>
            <div style="font-weight: 600; font-size: 14px;">Generation Failed</div>
            <div style="font-size: 12px; max-width: 380px; color: var(--text-secondary);">${err.message}</div>
            <button class="ide-action-btn primary" id="btn-diff-retry" style="margin-top: 6px;"><i class="fas fa-rotate-right"></i> Try Again</button>
          </div>
        `;
        if ($('btn-diff-retry')) {
          $('btn-diff-retry').addEventListener('click', generateDiffusionImage);
        }
      }
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-magic"></i> Generate Anime Art';
      }
      setCoreState('idle');
    }
  }

  // --- MEMORY VAULT LOGIC ---
  async function loadMemories() {
    try {
      const res = await fetch('/api/memory');
      const data = await res.json();
      const list = Array.isArray(data) ? data : (data.memories || []);
      const grid = $('memory-grid');
      grid.innerHTML = '';

      if (!list.length) {
        grid.innerHTML = '<div class="text-muted" style="grid-column: 1/-1; padding: 40px; text-align: center;">No stored memories yet.</div>';
        return;
      }

      list.forEach((item, idx) => {
        const card = document.createElement('div');
        card.className = 'memory-card';
        const text = typeof item === 'string' ? item : (item.fact || item.text || JSON.stringify(item));
        const id = item.id !== undefined ? item.id : idx;
        card.innerHTML = `
          <div class="memory-text">${escapeHtml(text)}</div>
          <div class="memory-meta">
            <span>Knowledge Fact #${idx + 1}</span>
            <button class="memory-del-btn" data-id="${id}"><i class="fas fa-trash-alt"></i></button>
          </div>
        `;
        card.querySelector('.memory-del-btn').addEventListener('click', async () => {
          await fetch(`/api/memory/${id}`, { method: 'DELETE' });
          showToast('Memory forgotten', 'info');
          loadMemories();
        });
        grid.appendChild(card);
      });
    } catch (e) {
      console.warn('Memory load error:', e);
    }
  }

  async function addMemoryFact() {
    const input = $('memory-add-input');
    const text = input.value.trim();
    if (!text) return;
    try {
      await fetch('/api/memory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fact: text })
      });
      input.value = '';
      showToast('Memory saved', 'success');
      loadMemories();
    } catch (e) {
      showToast('Failed to save memory: ' + e, 'error');
    }
  }

  async function clearAllMemories() {
    if (!confirm('Are you sure you want to clear all stored memories?')) return;
    try {
      await fetch('/api/memory/clear', { method: 'POST' });
      showToast('All memories cleared', 'info');
      loadMemories();
    } catch (e) {
      showToast('Failed to clear memories: ' + e, 'error');
    }
  }

  // --- SETTINGS VIEW LOGIC & JARVIS AUTHORITY AUDIT ---
  async function loadSettingsInfo() {
    try {
      const res = await fetch('/api/version');
      const data = await res.json();
      if ($('settings-version')) $('settings-version').textContent = data.version || '5.4.0';
    } catch (e) {}
    loadAuthorityAuditLog();
  }

  async function loadAuthorityAuditLog() {
    const container = $('audit-log-container');
    if (!container) return;
    try {
      const res = await fetch('/api/authority/audit');
      const data = await res.json();
      const logs = data.audit_log || [];
      if (!logs.length) {
        container.innerHTML = '<div style="color: var(--text-muted); font-size: 12px; padding: 12px; text-align: center;">No tool actions recorded in this session.</div>';
        return;
      }
      container.innerHTML = logs.map(e => `
        <div style="display: flex; align-items: center; justify-content: space-between; padding: 6px 10px; border-bottom: 1px solid rgba(255,255,255,0.05); font-family: var(--font-mono); font-size: 11px;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="color: ${e.status === 'EXECUTED' ? 'var(--emerald)' : e.status === 'DENIED' ? 'var(--rose)' : 'var(--amber)'}; font-weight: 700;">[${escapeHtml(e.status)}]</span>
            <span style="color: var(--cyan); font-weight: 600;">${escapeHtml(e.tool)}</span>
            <span style="color: var(--text-muted); font-size: 10px;">${escapeHtml(e.description || '')}</span>
          </div>
          <div style="display: flex; align-items: center; gap: 10px; color: var(--text-muted);">
            <span>${e.duration_ms || 0}ms</span>
            <span>${escapeHtml(e.timestamp ? e.timestamp.slice(11) : '')}</span>
          </div>
        </div>
      `).join('');
    } catch (e) {
      console.warn('Audit load failed:', e);
    }
  }

  async function startOllamaServer() {
    showToast('Starting Ollama daemon...', 'info');
    try {
      const res = await fetch('/api/ollama/start', { method: 'POST' });
      const data = await res.json();
      showToast(data.message || 'Ollama started', 'success');
      setTimeout(loadModels, 2500);
    } catch (e) {
      showToast('Could not start Ollama: ' + e, 'error');
    }
  }

  async function purgeLoadedModels() {
    showToast('Unloading models from memory...', 'info');
    try {
      const res = await fetch('/api/models/purge', { method: 'POST' });
      const data = await res.json();
      showToast(data.message || 'Models purged from VRAM', 'success');
    } catch (e) {
      showToast('Purge error: ' + e, 'error');
    }
  }

  async function resetPermissionScopes() {
    try {
      await fetch('/api/permission/reset_scopes', { method: 'POST' });
      showToast('Permission scopes reset successfully', 'success');
    } catch (e) {
      showToast('Reset failed: ' + e, 'error');
    }
  }

  // --- PERMISSION POLICIES & POPUP ---
  async function pollPermissions() {
    try {
      const res = await fetch('/api/permission/pending');
      if (res.ok) {
        const data = await res.json();
        if (data.status === 'pending' && (data.action || data.tool)) {
          showPermissionModal(data);
        }
      }
    } catch (e) {}
  }

  function showPermissionModal(perm) {
    const modal = $('perm-modal');
    $('perm-tool-name').textContent = perm.tool || perm.action || 'Unknown Action';
    $('perm-details-text').textContent = perm.description || perm.target || JSON.stringify(perm.params || {});
    modal.classList.add('active');

    $('perm-btn-deny').onclick = async () => {
      await fetch('/api/permission/respond', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: perm.id, allowed: false })
      });
      modal.classList.remove('active');
    };

    $('perm-btn-allow-once').onclick = async () => {
      await fetch('/api/permission/respond', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: perm.id, allowed: true, scope: 'once' })
      });
      modal.classList.remove('active');
    };

    $('perm-btn-allow-session').onclick = async () => {
      await fetch('/api/permission/respond', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: perm.id, allowed: 'allow_read_all', scope: 'session' })
      });
      modal.classList.remove('active');
    };
  }

  // --- INITIALIZATION ---
  function initApp() {
    // Navigation Rail Buttons
    $$('.rail-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const view = btn.dataset.view;
        if (view) switchView(view);
      });
    });

    // Chat Composer
    $('btn-send-chat').addEventListener('click', () => sendChatMessage());
    $('btn-stop-chat').addEventListener('click', stopGeneration);
    $('btn-composer-mic').addEventListener('click', triggerVoiceInput);

    $('chat-input').addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendChatMessage();
      }
    });

    const chatInput = $('chat-input');
    chatInput.addEventListener('input', () => {
      chatInput.style.height = 'auto';
      chatInput.style.height = Math.min(chatInput.scrollHeight, 180) + 'px';
    });

    // Starter Prompts
    $$('.starter-pill').forEach(pill => {
      pill.addEventListener('click', () => {
        const prompt = pill.dataset.prompt;
        if (prompt) {
          $('chat-input').value = prompt;
          sendChatMessage();
        }
      });
    });

    // Agent Toggle
    $('agent-mode-toggle').addEventListener('click', () => {
      state.agentMode = !state.agentMode;
      const toggle = $('agent-mode-toggle');
      if (state.agentMode) {
        toggle.classList.add('active');
        showToast('Autonomous Agent Tools Enabled', 'info');
      } else {
        toggle.classList.remove('active');
        showToast('Agent Tools Disabled', 'info');
      }
    });

    // Topbar Voice Controls
        $('btn-mic').addEventListener('click', triggerVoiceInput);
    if ($('confirm-btn-yes')) $('confirm-btn-yes').addEventListener('click', handleConfirmedCommand);
    if ($('confirm-btn-wrong')) $('confirm-btn-wrong').addEventListener('click', handleRejectedCommand);
    $('btn-toggle-wake').addEventListener('click', toggleWakeWord);
    $('btn-toggle-tts').addEventListener('click', toggleTts);

    // Initial Voice States & Listeners
    initTts();
    checkWakeState();
    const voiceModal = $('voice-modal');
    if (voiceModal) {
      voiceModal.addEventListener('click', (e) => {
        if (e.target === voiceModal) voiceModal.classList.remove('active');
      });
    }

    // Chat History & New Chat
    $('btn-history-chats').addEventListener('click', openChatHistory);
    $('btn-close-history').addEventListener('click', () => $('history-modal').classList.remove('active'));
    $('btn-new-chat').addEventListener('click', createNewChat);

    // Shutdown Button
    $('btn-shutdown').addEventListener('click', async () => {
      if (confirm('Shutdown Ciel backend and exit?')) {
        await fetch('/api/system/shutdown', { method: 'POST' });
        showToast('Ciel is shutting down...', 'warning');
      }
    });

    // Ollama badge start
    $('ollama-badge').addEventListener('click', () => {
      startOllamaServer();
    });

    // Model Selector
    $('model-select').addEventListener('change', (e) => {
      state.selectedModel = e.target.value;
      showToast('Switched model to: ' + state.selectedModel, 'info');
    });

    // Tasks Center
    $('btn-refresh-tasks').addEventListener('click', loadTasks);

    // IDE Buttons & Hotkeys
    $('btn-ide-save').addEventListener('click', saveIdeFile);
    $('btn-ide-run').addEventListener('click', runIdeCode);
    $('btn-ide-refresh').addEventListener('click', () => loadIdeTree(state.currentWorkspacePath));
    $('btn-ide-new-file').addEventListener('click', createIdeFile);
    $('btn-clear-term').addEventListener('click', () => $('ide-terminal-output').textContent = '// Console cleared.\n');
    $('btn-ide-send-chat').addEventListener('click', () => {
      if (!state.activeFileContent) return;
      $('chat-input').value = `Please analyze and improve this code from ${state.activeFile}:\n\n\`\`\`\n${state.activeFileContent}\n\`\`\``;
      switchView('chat');
      $('chat-input').focus();
    });

    window.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        if (state.activeView === 'ide') {
          e.preventDefault();
          saveIdeFile();
        }
      }
    });

    // Memory buttons
    $('btn-add-memory').addEventListener('click', addMemoryFact);
    $('btn-clear-memories').addEventListener('click', clearAllMemories);

    // Settings buttons
    $('btn-start-ollama-settings').addEventListener('click', startOllamaServer);
    $('btn-purge-models').addEventListener('click', purgeLoadedModels);
    $('btn-reset-permissions').addEventListener('click', resetPermissionScopes);

    // Primitive & Diffusion Studios
    setupPrimitiveStudio();
    setupDiffusionStudio();

    if ($('btn-download-modal')) {
      $('btn-download-modal').addEventListener('click', () => {
        const src = $('image-modal-src').src;
        if (!src) return;
        const fn = state.diffusion.imagePath ? `ciel_${state.diffusion.imagePath}` : `ciel_image_${Date.now()}.png`;
        triggerDownload(src, fn, {
          filename: state.diffusion.imagePath,
          image_b64: state.diffusion.imageB64
        });
      });
    }

    if ($('chat-feed')) {
      $('chat-feed').addEventListener('click', (e) => {
        if (e.target && e.target.tagName === 'IMG' && !e.target.closest('.msg-avatar')) {
          $('image-modal-src').src = e.target.src;
          $('image-modal').classList.add('active');
        }
      });
    }

    // Start background pollers
    loadModels();
    loadDiffusionModels();
    pollSysinfo();
    sysPollTimer = setInterval(pollSysinfo, 4000);
    permPollTimer = setInterval(pollPermissions, 1500);

    // Initialize Thinking Orbs & Interactive Core
    initThinkingOrb();
    if ($('ciel-core-wrapper')) $('ciel-core-wrapper').addEventListener('click', openOrbPickerModal);
    if ($('hud-orb-chip')) $('hud-orb-chip').addEventListener('click', openOrbPickerModal);
    if ($('btn-close-orb-picker')) $('btn-close-orb-picker').addEventListener('click', () => $('orb-picker-modal').classList.remove('active'));

    // JARVIS Companion HUD & Authority Audit hooks
    if ($('btn-launch-companion')) {
      $('btn-launch-companion').addEventListener('click', async () => {
        showToast('Launching Ciel Floating Companion Sidecar...', 'info');
        try {
          const res = await fetch('/api/system/launch_companion', { method: 'POST' });
          const data = await res.json();
          showToast(data.message || 'Companion HUD summoned', 'success');
        } catch (e) {
          showToast('Failed to launch companion: ' + e, 'error');
        }
      });
    }

    if ($('btn-refresh-audit')) {
      $('btn-refresh-audit').addEventListener('click', () => {
        loadAuthorityAuditLog();
        showToast('Audit trail refreshed', 'info');
      });
    }
    if ($('orb-picker-modal')) {
      $('orb-picker-modal').addEventListener('click', (e) => {
        if (e.target === $('orb-picker-modal')) $('orb-picker-modal').classList.remove('active');
      });
    }

    // Initial greeting if feed is empty
    if (!$('chat-feed').children.length) {
      createNewChat();
    }
  }

  // Launch when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initApp);
  } else {
    initApp();
  }
})();
