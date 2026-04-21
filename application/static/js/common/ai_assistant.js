(function () {
    const state = {
        initialized: false,
        currentSessionId: null,
        isWaitingForResponse: false,
        sharedFileContent: null,
        lastSelectedModel: 'deepseek-chat',
        elements: null,
    };

    function getElements() {
        const triggerNodes = Array.from(document.querySelectorAll('[data-ai-trigger], #ai-assistant-switch'));
        const aiSwitches = Array.from(new Set(triggerNodes.filter(Boolean)));

        return {
            aiSidebar: document.getElementById('ai-assistant-sidebar'),
            shellBackdrop: document.getElementById('shell-backdrop'),
            chatWindow: document.getElementById('chat-window'),
            userInput: document.getElementById('user-input'),
            sendBtn: document.getElementById('send-btn'),
            uploadInitialScreen: document.getElementById('upload-initial-screen'),
            uploadBtn: document.getElementById('upload-btn'),
            fileInput: document.getElementById('topology-file-input'),
            uploadError: document.getElementById('upload-error'),
            chatInputArea: document.getElementById('chat-input-area'),
            suggestedQuestionsContainer: document.getElementById('suggested-questions'),
            showFormatDetailsLink: document.getElementById('show-format-details'),
            formatDetails: document.getElementById('format-details'),
            aiSwitches,
            closeBtn: document.getElementById('close-ai-sidebar'),
            modelSelect: document.getElementById('llm-model-select'),
        };
    }

    function renderMarkdown(content) {
        if (window.marked && typeof window.marked.parse === 'function') {
            return window.marked.parse(content);
        }
        return content;
    }

    function escapeHtml(content) {
        return String(content)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function initSidebarControls(elements) {
        const { aiSidebar, aiSwitches, closeBtn, shellBackdrop, uploadBtn, userInput, uploadInitialScreen } = elements;
        if (!aiSidebar || !closeBtn || !Array.isArray(aiSwitches) || aiSwitches.length === 0 || aiSidebar.dataset.p4primeSidebarBound === '1') {
            return;
        }

        aiSidebar.dataset.p4primeSidebarBound = '1';

        function syncTriggerState(isExpanded) {
            aiSwitches.forEach((button) => {
                button.setAttribute('aria-expanded', isExpanded ? 'true' : 'false');
                button.setAttribute('aria-controls', 'ai-assistant-sidebar');
            });
        }

        function openSidebar() {
            aiSidebar.classList.add('open');
            aiSidebar.setAttribute('aria-hidden', 'false');
            if (shellBackdrop) {
                shellBackdrop.classList.add('is-visible');
                shellBackdrop.setAttribute('aria-hidden', 'false');
            }
            document.body.classList.add('is-ai-open');
            syncTriggerState(true);

            window.requestAnimationFrame(() => {
                const shouldFocusInput = uploadInitialScreen && uploadInitialScreen.style.display === 'none';
                const focusTarget = shouldFocusInput ? userInput : uploadBtn;
                focusTarget?.focus();
            });
        }

        function closeSidebar() {
            aiSidebar.classList.remove('open');
            aiSidebar.setAttribute('aria-hidden', 'true');
            if (shellBackdrop) {
                shellBackdrop.classList.remove('is-visible');
                shellBackdrop.setAttribute('aria-hidden', 'true');
            }
            document.body.classList.remove('is-ai-open');
            syncTriggerState(false);
        }

        aiSwitches.forEach((button) => {
            if (button.dataset.p4primeAiTriggerBound === '1') {
                return;
            }

            button.dataset.p4primeAiTriggerBound = '1';
            button.addEventListener('click', (event) => {
                event.stopPropagation();
                openSidebar();
            });
        });

        closeBtn.addEventListener('click', closeSidebar);
        shellBackdrop?.addEventListener('click', closeSidebar);

        document.addEventListener('click', (event) => {
            if (!aiSidebar.classList.contains('open') || !(event.target instanceof Node)) {
                return;
            }

            if (aiSwitches.some((button) => button.contains(event.target))) {
                return;
            }

            if (!aiSidebar.contains(event.target)) {
                closeSidebar();
            }
        });

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && aiSidebar.classList.contains('open')) {
                closeSidebar();
            }
        });

        aiSidebar.setAttribute('aria-hidden', 'true');
        syncTriggerState(false);
    }

    function displayError(message) {
        const { uploadError } = state.elements || {};
        if (!uploadError) {
            return;
        }

        uploadError.textContent = message;
        uploadError.style.display = 'block';
    }

    function toggleLoadingState(isLoading) {
        const { userInput, sendBtn } = state.elements || {};
        state.isWaitingForResponse = isLoading;

        if (!userInput || !sendBtn) {
            return;
        }

        userInput.disabled = isLoading;
        sendBtn.disabled = isLoading;
        sendBtn.innerHTML = isLoading
            ? '<i class="fas fa-spinner fa-spin"></i>'
            : '<i class="fas fa-paper-plane"></i>';
    }

    function appendUserMessage(text) {
        const { chatWindow } = state.elements || {};
        if (!chatWindow) {
            return;
        }

        const messageDiv = document.createElement('div');
        messageDiv.className = 'chat-message user';
        messageDiv.textContent = text;
        chatWindow.appendChild(messageDiv);
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }

    async function handleBuildTopologyRedirect(event) {
        event.preventDefault();

        try {
            const response = await fetch('/apply_intent', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
            });
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.error || '后端意图接口调用失败');
            }

            if (!state.sharedFileContent) {
                throw new Error('文件内容为空，无法存储。');
            }

            localStorage.setItem('pendingTopology', state.sharedFileContent);
            localStorage.setItem('pendingModel', state.lastSelectedModel);
            window.location.href = '/topology/your_topology';
        } catch (error) {
            console.error('构建并跳转失败:', error);
            window.alert('无法保存会话状态，跳转失败。请检查浏览器设置。');
        }
    }

    function appendBotMessage(data, isInitialUpload = false) {
        const elements = state.elements;
        if (!elements || !elements.chatWindow) {
            return;
        }

        const messageDiv = document.createElement('div');
        messageDiv.className = 'chat-message bot';

        const aiResponse = isInitialUpload ? data.initial_response : data;
        if (!aiResponse || typeof aiResponse !== 'object') {
            const errorContent = `AI回复格式错误: ${JSON.stringify(aiResponse)}`;
            messageDiv.innerHTML = `<div class="message-content">${renderMarkdown(errorContent)}</div>`;
            elements.chatWindow.appendChild(messageDiv);
            return;
        }

        let htmlContent = '';

        if (aiResponse.analysis) {
            htmlContent += `<div class="message-content">${renderMarkdown(aiResponse.analysis)}</div>`;
        }

        if (isInitialUpload && data.topology_summary) {
            const summary = data.topology_summary;
            htmlContent += `
                <div class="message-content">
                    <p><strong>已识别拓扑规模：</strong>${summary.switch_count} 台交换机，${summary.host_count} 台主机，${summary.link_count} 条链路。</p>
                    <p><strong>构建方式：</strong>后端会在 topo/user_topology 下生成独立运行目录，并基于这份上传配置构建真实的当前拓扑。</p>
                </div>
            `;
        }

        if (aiResponse.intent && typeof aiResponse.intent === 'object') {
            const hasIntentSummary = Boolean(aiResponse.intent.summary);
            const hasIntentFlows = Array.isArray(aiResponse.intent.flows) && aiResponse.intent.flows.length > 0;
            if (hasIntentSummary || hasIntentFlows) {
                htmlContent += `
                    <div class="message-content">
                        <h4>形式化意图 intent.json</h4>
                        <pre><code>${escapeHtml(JSON.stringify(aiResponse.intent, null, 2))}</code></pre>
                    </div>
                `;
            }
        }

        if (Array.isArray(aiResponse.files) && aiResponse.files.length > 0) {
            htmlContent += '<div class="download-section">';
            aiResponse.files.forEach((file) => {
                if (!file.content) {
                    return;
                }

                const blob = new Blob([file.content], { type: 'text/plain' });
                const url = URL.createObjectURL(blob);
                htmlContent += `<a href="${url}" download="${escapeHtml(file.filename)}" class="download-button"><i class="fas fa-download"></i> 下载 ${escapeHtml(file.filename)}</a> `;
            });
            htmlContent += '</div>';
        }

        if (isInitialUpload && data.download_links) {
            htmlContent += '<div class="download-section">';
            htmlContent += `<a href="${data.download_links.script}" download="network.py" class="download-button"><i class="fab fa-python"></i> 下载生成的 network.py</a> `;
            htmlContent += `<a href="${data.download_links.config}" download="topology.json" class="download-button"><i class="fas fa-file-code"></i> 下载 topology.json</a> `;
            if (data.download_links.intent) {
                htmlContent += `<a href="${data.download_links.intent}" download="intent.json" class="download-button"><i class="fas fa-diagram-project"></i> 下载 intent.json</a>`;
            }
            htmlContent += '</div>';
        }

        const isBuildPage = window.location.pathname.includes('/topology/your_topology');
        if (isInitialUpload && data.build_enabled && !isBuildPage) {
            htmlContent += `
                <div class="build-topology-section">
                    <p>是否根据这份上传拓扑生成对应 network.py，并进入构建页面？</p>
                    <a href="javascript:void(0);" class="chat-button build-button" data-action="build-topology">
                        <i class="fas fa-cogs"></i> 构建并进入我的拓扑
                    </a>
                </div>
            `;
        }

        messageDiv.innerHTML = htmlContent;
        elements.chatWindow.appendChild(messageDiv);

        const buildButton = messageDiv.querySelector('[data-action="build-topology"]');
        if (buildButton) {
            buildButton.addEventListener('click', handleBuildTopologyRedirect);
        }

        if (elements.suggestedQuestionsContainer) {
            elements.suggestedQuestionsContainer.innerHTML = '';
            if (Array.isArray(aiResponse.questions) && aiResponse.questions.length > 0) {
                aiResponse.questions.forEach((question) => {
                    if (!question) {
                        return;
                    }

                    const button = document.createElement('button');
                    button.className = 'suggested-question-btn';
                    button.textContent = question;
                    button.addEventListener('click', (event) => {
                        event.stopPropagation();
                        if (elements.userInput) {
                            elements.userInput.value = question;
                        }
                        sendMessage();
                    });
                    elements.suggestedQuestionsContainer.appendChild(button);
                });
            }
        }

        elements.chatWindow.scrollTop = elements.chatWindow.scrollHeight;
    }

    async function sendMessage() {
        const elements = state.elements;
        if (!elements || !elements.userInput) {
            return;
        }

        const messageText = elements.userInput.value.trim();
        if (messageText === '' || state.isWaitingForResponse) {
            return;
        }

        toggleLoadingState(true);
        appendUserMessage(messageText);
        elements.userInput.value = '';
        if (elements.suggestedQuestionsContainer) {
            elements.suggestedQuestionsContainer.innerHTML = '';
        }

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: messageText }),
            });
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.error || '请求失败');
            }

            appendBotMessage(data);
        } catch (error) {
            appendBotMessage({
                analysis: `抱歉，请求出错：${error.message}`,
                files: [],
                questions: [],
            });
        } finally {
            toggleLoadingState(false);
        }
    }

    async function handleUploadFile(file, modelNameOverride) {
        const elements = state.elements;
        if (!elements || !file) {
            return null;
        }

        state.sharedFileContent = await file.text();

        if (elements.uploadError) {
            elements.uploadError.style.display = 'none';
        }

        const selectedModel = modelNameOverride || (elements.modelSelect ? elements.modelSelect.value : 'deepseek-chat');
        state.lastSelectedModel = selectedModel;
        if (elements.modelSelect) {
            elements.modelSelect.value = selectedModel;
        }

        if (elements.uploadBtn) {
            elements.uploadBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 上传并验证中...';
            elements.uploadBtn.disabled = true;
        }

        const formData = new FormData();
        formData.append('file', file);
        formData.append('model', selectedModel);

        try {
            const response = await fetch('/upload_topology', {
                method: 'POST',
                body: formData,
            });
            const data = await response.json();

            if (!response.ok) {
                let errorMessage = data.error || `服务器错误: ${response.status}`;
                if (data.template) {
                    errorMessage += `\n期望的格式类似: ${data.template}`;
                }
                throw new Error(errorMessage);
            }

            state.currentSessionId = data.session_id;
            window.currentSessionId = data.session_id;
            window.dispatchEvent(new CustomEvent('uploaded-topology-ready', {
                detail: data.topology_summary || null,
            }));

            if (elements.uploadInitialScreen) {
                elements.uploadInitialScreen.style.display = 'none';
            }
            if (elements.chatInputArea) {
                elements.chatInputArea.style.display = 'block';
            }

            appendBotMessage(data, true);
            toggleLoadingState(false);
            return data;
        } catch (error) {
            displayError(error.message);
            throw error;
        } finally {
            if (elements.uploadBtn) {
                elements.uploadBtn.innerHTML = '<i class="fas fa-upload"></i> 点击上传文件';
                elements.uploadBtn.disabled = false;
            }
            if (elements.fileInput) {
                elements.fileInput.value = '';
            }
        }
    }

    function init() {
        if (state.initialized) {
            return true;
        }

        const elements = getElements();
        state.elements = elements;

        if (!elements.aiSidebar) {
            return false;
        }

        state.initialized = true;
        initSidebarControls(elements);

        if (elements.uploadBtn && elements.fileInput && elements.uploadBtn.dataset.p4primeUploadBound !== '1') {
            elements.uploadBtn.dataset.p4primeUploadBound = '1';
            elements.uploadBtn.addEventListener('click', () => elements.fileInput.click());
            elements.fileInput.addEventListener('change', async (event) => {
                const [file] = event.target.files;
                if (!file) {
                    return;
                }

                try {
                    await handleUploadFile(file);
                } catch (error) {
                    console.error('上传拓扑失败:', error);
                }
            });
        }

        if (elements.sendBtn && elements.sendBtn.dataset.p4primeSendBound !== '1') {
            elements.sendBtn.dataset.p4primeSendBound = '1';
            elements.sendBtn.addEventListener('click', sendMessage);
        }

        if (elements.userInput && elements.userInput.dataset.p4primeInputBound !== '1') {
            elements.userInput.dataset.p4primeInputBound = '1';
            elements.userInput.addEventListener('keypress', (event) => {
                if (event.key === 'Enter') {
                    sendMessage();
                }
            });
        }

        if (elements.showFormatDetailsLink && elements.formatDetails && elements.showFormatDetailsLink.dataset.p4primeFormatBound !== '1') {
            elements.showFormatDetailsLink.dataset.p4primeFormatBound = '1';
            elements.showFormatDetailsLink.addEventListener('click', (event) => {
                event.preventDefault();
                elements.formatDetails.style.display = elements.formatDetails.style.display === 'none' ? 'block' : 'none';
            });
        }

        window.toggleLoadingState = toggleLoadingState;
        window.appendBotMessage = appendBotMessage;
        return true;
    }

    async function autoUploadAndInitAI(file, modelName) {
        const isReady = init();
        if (!isReady) {
            return null;
        }

        try {
            return await handleUploadFile(file, modelName || state.lastSelectedModel);
        } catch (error) {
            console.error('自动恢复 AI 会话失败:', error);
            return null;
        }
    }

    window.P4PrimeAssistant = {
        init,
        autoUploadAndInitAI,
        appendBotMessage,
        toggleLoadingState,
    };
}());