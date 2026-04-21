(function () {
    let initialized = false;

    function normalizeTopologySettings(settings) {
        return {
            hostShape: settings?.hostShape || settings?.host?.shape || 'ellipse',
            hostColor: settings?.hostColor || settings?.host?.color || '#FFD700',
            hostSize: settings?.hostSize || settings?.host?.size || 25,
            switchShape: settings?.switchShape || settings?.switch?.shape || 'box',
            switchColor: settings?.switchColor || settings?.switch?.color || '#87CEEB',
            switchSize: settings?.switchSize || settings?.switch?.size || 25,
        };
    }

    function updateRangeValue(inputNode, valueNode) {
        if (!inputNode || !valueNode) {
            return;
        }

        valueNode.textContent = inputNode.value;
    }

    function setStatus(targetId, message, color) {
        const statusNode = document.getElementById(targetId);
        if (!statusNode) {
            return;
        }

        statusNode.style.color = color;
        statusNode.textContent = message;
    }

    async function requestJson(url, options, fallbackMessage) {
        const response = await fetch(url, options);
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || payload.msg || fallbackMessage);
        }
        return payload;
    }

    async function loadTopologySettings() {
        const settings = normalizeTopologySettings(await requestJson('/get_topo_settings', undefined, '读取拓扑设置失败'));

        document.getElementById('hostShape').value = settings.hostShape;
        document.getElementById('hostColor').value = settings.hostColor;
        document.getElementById('hostSize').value = settings.hostSize;
        document.getElementById('hostSizeValue').textContent = settings.hostSize;

        document.getElementById('switchShape').value = settings.switchShape;
        document.getElementById('switchColor').value = settings.switchColor;
        document.getElementById('switchSize').value = settings.switchSize;
        document.getElementById('switchSizeValue').textContent = settings.switchSize;
    }

    async function loadLlmSettings() {
        const settings = await requestJson('/get_llm_settings', undefined, '读取 AI 配置失败');
        if (!settings) {
            return;
        }

        document.getElementById('deepseekBaseUrl').value = settings.deepseek?.base_url || '';
        document.getElementById('deepseekApiKey').value = settings.deepseek?.api_key || '';
        document.getElementById('ecnuBaseUrl').value = settings.ecnu?.base_url || '';
        document.getElementById('ecnuApiKey').value = settings.ecnu?.api_key || '';
    }

    async function saveTopologySettings() {
        const settings = {
            hostShape: document.getElementById('hostShape').value,
            hostColor: document.getElementById('hostColor').value,
            hostSize: parseInt(document.getElementById('hostSize').value, 10),
            switchShape: document.getElementById('switchShape').value,
            switchColor: document.getElementById('switchColor').value,
            switchSize: parseInt(document.getElementById('switchSize').value, 10),
        };

        try {
            await requestJson('/save_topo_settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings),
            }, '保存拓扑设置失败');
            setStatus('saveStatus', '设置已保存', '#2e7d32');
        } catch (error) {
            setStatus('saveStatus', `保存失败：${error.message}`, '#c62828');
        }
    }

    async function saveLlmSettings() {
        const llmSettings = {
            deepseek: {
                base_url: document.getElementById('deepseekBaseUrl').value.trim(),
                api_key: document.getElementById('deepseekApiKey').value.trim(),
            },
            ecnu: {
                base_url: document.getElementById('ecnuBaseUrl').value.trim(),
                api_key: document.getElementById('ecnuApiKey').value.trim(),
            },
        };

        try {
            const result = await requestJson('/save_llm_settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(llmSettings),
            }, '保存 AI 配置失败');
            setStatus('llmSaveStatus', result.msg || 'AI 配置已保存', result.status === 'success' ? '#2e7d32' : '#c62828');
        } catch (error) {
            setStatus('llmSaveStatus', `AI 配置保存失败：${error.message}`, '#c62828');
        }
    }

    async function init() {
        if (initialized) {
            return;
        }

        const hostSizeInput = document.getElementById('hostSize');
        const switchSizeInput = document.getElementById('switchSize');
        const hostSizeValue = document.getElementById('hostSizeValue');
        const switchSizeValue = document.getElementById('switchSizeValue');

        if (!hostSizeInput || !switchSizeInput || !hostSizeValue || !switchSizeValue) {
            return;
        }

        initialized = true;

        hostSizeInput.addEventListener('input', () => updateRangeValue(hostSizeInput, hostSizeValue));
        switchSizeInput.addEventListener('input', () => updateRangeValue(switchSizeInput, switchSizeValue));

        document.getElementById('saveSettingsBtn')?.addEventListener('click', saveTopologySettings);
        document.getElementById('saveLlmSettingsBtn')?.addEventListener('click', saveLlmSettings);

        try {
            await loadTopologySettings();
        } catch (error) {
            setStatus('saveStatus', `读取节点样式失败：${error.message}`, '#c62828');
        }

        try {
            await loadLlmSettings();
        } catch (error) {
            setStatus('llmSaveStatus', `读取 AI 配置失败：${error.message}`, '#c62828');
        }
    }

    window.P4PrimeSettingsPage = { init };
}());