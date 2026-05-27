(function () {
    function create(userConfig = {}) {
        const config = {
            topologySelection: 'current',
            initialStatusMessage: '',
            buildAcceptedMessage: (data) => `后端已接受 ${data.topology} 构建请求，正在同步拓扑视图...`,
            p4LoadedMessage: 'P4 程序已装载，可以继续生成当前拓扑。',
            flowInjectedMessage: '流表已注入，可以开始发送验证流量。',
            primarySendLabel: '发送',
            primarySendEndpoint: '/send_command',
            secondarySendLabel: 'VBP 验证',
            secondarySendEndpoint: '/send_command_vbp',
            enableSecondarySend: false,
            expectedPathLabel: '预期路径',
            autoRestorePendingTopology: false,
            autoRestoreStatusMessage: '检测到刚上传的拓扑，正在恢复 AI 会话并准备构建当前网络...',
            uploadReadyMessage: () => '已载入新的上传拓扑，现在可以装载 P4 并生成当前拓扑。',
            ...userConfig,
        };

        const view = window.P4PrimeTopologyView.create();
        let detailRefreshTimer = null;
        let initialized = false;
        let latestVerificationProfile = null;
        let selectedSemanticFlowId = '';
        let selectedPathFlowId = '';
        let selectedFaultFlowId = '';

        function escapeHtml(value) {
            return String(value ?? '')
                .replaceAll('&', '&amp;')
                .replaceAll('<', '&lt;')
                .replaceAll('>', '&gt;')
                .replaceAll('"', '&quot;')
                .replaceAll("'", '&#39;');
        }

        function prettyJson(value) {
            return JSON.stringify(value ?? [], null, 2);
        }

        function stripCidr(value) {
            return String(value ?? '').split('/', 1)[0];
        }

        function switchPathNames(path) {
            if (!Array.isArray(path)) {
                return [];
            }

            return path
                .map((nodeId) => {
                    if (typeof nodeId === 'string') {
                        return nodeId.startsWith('s') ? nodeId : `s${nodeId}`;
                    }
                    return `s${nodeId}`;
                })
                .filter(Boolean);
        }

        function pathSignature(path) {
            return switchPathNames(path).join('>');
        }

        function formatTimestamp(unixValue) {
            const timestamp = Number(unixValue || 0);
            if (!Number.isFinite(timestamp) || timestamp <= 0) {
                return '未知时间';
            }

            return new Date(timestamp * 1000).toLocaleString('zh-CN', {
                hour12: false,
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
            });
        }

        function resolveHostLabel(scope, keyPrefix) {
            const hostKey = `${keyPrefix}_host`;
            const ipKey = `${keyPrefix}_ip`;
            if (scope?.[hostKey]) {
                return scope[hostKey];
            }

            const lookup = latestVerificationProfile?.host_lookup || {};
            const ipAddress = stripCidr(scope?.[ipKey] || '');
            return lookup[ipAddress] || '';
        }

        function flowDisplayLabel(flow) {
            const scope = flow?.flow_scope || {};
            const srcHost = resolveHostLabel(scope, 'src');
            const dstHost = resolveHostLabel(scope, 'dst');
            if (srcHost && dstHost) {
                return `${srcHost} -> ${dstHost}`;
            }
            if (scope.src_ip && scope.dst_ip) {
                return `${stripCidr(scope.src_ip)} -> ${stripCidr(scope.dst_ip)}`;
            }
            return flow?.flow_id || 'unknown-flow';
        }

        function formatSwitchPath(path) {
            const switchPath = switchPathNames(path);
            return switchPath.length > 0
                ? switchPath.join(' -> ')
                : '空路径';
        }

        function getFlowCatalog(selectedFlow) {
            const activeSignatures = new Set(
                (selectedFlow?.behaviors || []).map((behavior) => pathSignature(behavior.switch_path || behavior.path))
            );
            const rawCatalog = Array.isArray(selectedFlow?.path_catalog) ? selectedFlow.path_catalog : [];
            const catalogSource = rawCatalog.length > 0
                ? rawCatalog
                : (selectedFlow?.behaviors || []).map((behavior, index) => ({
                    index,
                    label: behavior.label || `候选路径 ${index + 1}`,
                    path: behavior.path || [],
                    switch_path: behavior.switch_path || behavior.path || [],
                    active: true,
                }));

            const seen = new Set();
            return catalogSource.map((item, index) => {
                const switchPath = switchPathNames(item.switch_path || item.path || []);
                const signature = switchPath.join('>');
                if (!signature || seen.has(signature)) {
                    return null;
                }

                seen.add(signature);
                return {
                    index: Number.isInteger(item.index) ? item.index : index,
                    label: item.label || `候选路径 ${index + 1}`,
                    switchPath,
                    signature,
                    active: Boolean(item.active) || activeSignatures.has(signature),
                };
            }).filter(Boolean);
        }

        function findFlowForResult(pathJson) {
            const flows = Array.isArray(latestVerificationProfile?.semantic_policy?.flows)
                ? latestVerificationProfile.semantic_policy.flows
                : [];
            const targetFlowId = pathJson?.semantic_verification?.flow_id || '';
            if (targetFlowId) {
                const matchedFlow = flows.find((flow) => flow.flow_id === targetFlowId);
                if (matchedFlow) {
                    return matchedFlow;
                }
            }

            const srcIp = stripCidr(pathJson?.src_ip || pathJson?.semantic_verification?.flow_scope?.src_ip || '');
            const dstIp = stripCidr(pathJson?.dst_ip || pathJson?.semantic_verification?.flow_scope?.dst_ip || '');
            if (!srcIp || !dstIp) {
                return null;
            }

            return flows.find((flow) => {
                const scope = flow.flow_scope || {};
                return stripCidr(scope.src_ip || '') === srcIp && stripCidr(scope.dst_ip || '') === dstIp;
            }) || null;
        }

        function findSelectedSemanticFlow(profile) {
            const flows = Array.isArray(profile?.semantic_policy?.flows) ? profile.semantic_policy.flows : [];
            if (flows.length === 0) {
                return null;
            }

            if (selectedSemanticFlowId) {
                const matchedFlow = flows.find((flow) => flow.flow_id === selectedSemanticFlowId);
                if (matchedFlow) {
                    return matchedFlow;
                }
            }

            selectedSemanticFlowId = flows[0].flow_id;
            return flows[0];
        }

        function findSelectedPathFlow(profile) {
            const flows = Array.isArray(profile?.semantic_policy?.flows) ? profile.semantic_policy.flows : [];
            if (flows.length === 0) {
                return null;
            }

            if (selectedPathFlowId) {
                const matchedFlow = flows.find((flow) => flow.flow_id === selectedPathFlowId);
                if (matchedFlow) {
                    return matchedFlow;
                }
            }

            selectedPathFlowId = flows[0].flow_id;
            return flows[0];
        }

        function findSelectedFaultFlow(profile) {
            const flows = Array.isArray(profile?.semantic_policy?.flows) ? profile.semantic_policy.flows : [];
            if (flows.length === 0) {
                return null;
            }

            if (selectedFaultFlowId) {
                const matchedFlow = flows.find((flow) => flow.flow_id === selectedFaultFlowId);
                if (matchedFlow) {
                    return matchedFlow;
                }
            }

            selectedFaultFlowId = flows[0].flow_id;
            return flows[0];
        }

        function setSemanticEditorStatus(message, color = '#607d8b') {
            const statusNode = document.getElementById('semanticSaveStatus');
            if (!statusNode) {
                return;
            }

            statusNode.textContent = message;
            statusNode.style.color = color;
        }

        function setPathPlannerStatus(message, color = '#607d8b') {
            const statusNode = document.getElementById('pathPlannerStatus');
            if (!statusNode) {
                return;
            }

            statusNode.textContent = message;
            statusNode.style.color = color;
        }

        function setPathPlannerDisabled(disabled) {
            [
                'pathFlowSelector',
                'pathCandidateSelector',
                'applyExpectedPathButton',
                'resetExpectedPathButton',
            ].forEach((elementId) => {
                const node = document.getElementById(elementId);
                if (node) {
                    node.disabled = disabled;
                }
            });
        }

        function setFaultDrillDisabled(disabled) {
            [
                'faultFlowSelector',
                'faultLinkSelector',
                'injectFaultDrillButton',
                'restoreFaultDrillButton',
            ].forEach((elementId) => {
                const node = document.getElementById(elementId);
                if (node) {
                    node.disabled = disabled;
                }
            });
        }

        function setVbpPathEditorDisabled(disabled) {
            ['saveVbpPathsButton', 'resetVbpPathsButton'].forEach((elementId) => {
                const node = document.getElementById(elementId);
                if (node) {
                    node.disabled = disabled;
                }
            });

            document.querySelectorAll('#vbpPathManager input[type="checkbox"]').forEach((node) => {
                node.disabled = disabled;
            });
        }

        function setSemanticEditorDisabled(disabled) {
            [
                'semanticFlowSelector',
                'semanticMaxPackets',
                'semanticMaxHops',
                'semanticMaxDegradedPackets',
                'semanticMaxStateChanges',
                'semanticRequireRecovery',
                'semanticInvariantsEditor',
                'semanticTransitionsEditor',
                'semanticReloadButton',
                'semanticSaveButton',
            ].forEach((elementId) => {
                const node = document.getElementById(elementId);
                if (node) {
                    node.disabled = disabled;
                }
            });
        }

        function setVbpPathStatus(message, color = '#607d8b') {
            const statusNode = document.getElementById('vbpPathStatus');
            if (!statusNode) {
                return;
            }

            statusNode.textContent = message;
            statusNode.style.color = color;
        }

        function setFaultDrillStatus(message, color = '#607d8b') {
            const statusNode = document.getElementById('faultDrillStatus');
            if (!statusNode) {
                return;
            }

            statusNode.textContent = message;
            statusNode.style.color = color;
        }

        function getFaultLinkCatalog(selectedFlow) {
            const catalog = getFlowCatalog(selectedFlow);
            const primaryPath = switchPathNames(selectedFlow?.behaviors?.[0]?.switch_path || selectedFlow?.behaviors?.[0]?.path || []);
            const primaryEdges = new Set(primaryPath.slice(1).map((nodeId, index) => [primaryPath[index], nodeId].sort().join('>')));
            const linkMap = new Map();

            catalog.forEach((item) => {
                item.switchPath.slice(1).forEach((nodeId, index) => {
                    const link = [item.switchPath[index], nodeId].sort();
                    const signature = link.join('>');
                    const existing = linkMap.get(signature) || {
                        signature,
                        link,
                        label: `${link[0]} <-> ${link[1]}`,
                        impactCount: 0,
                        affectsPrimary: primaryEdges.has(signature),
                        pathLabels: [],
                    };

                    existing.impactCount += 1;
                    if (!existing.pathLabels.includes(item.label)) {
                        existing.pathLabels.push(item.label);
                    }
                    linkMap.set(signature, existing);
                });
            });

            return Array.from(linkMap.values()).sort((left, right) => {
                if (left.affectsPrimary !== right.affectsPrimary) {
                    return left.affectsPrimary ? -1 : 1;
                }
                if (left.impactCount !== right.impactCount) {
                    return right.impactCount - left.impactCount;
                }
                return left.label.localeCompare(right.label, 'zh-CN');
            });
        }

        async function requestJson(url, options, fallbackErrorMessage) {
            const response = await fetch(url, options);
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.error || data.message || fallbackErrorMessage);
            }
            return data;
        }

        function scheduleNodeDetailRefresh() {
            if (detailRefreshTimer) {
                window.clearTimeout(detailRefreshTimer);
            }
            detailRefreshTimer = window.setTimeout(() => refreshNodeDetails(6), 1200);
        }

        async function refreshNodeDetails(retryCount = 0) {
            try {
                const nodeDetails = await requestJson('/get_topology_nodes', undefined, '刷新节点详情失败');
                view.applyNodeDetails(nodeDetails);

                const hostsReady = Array.isArray(nodeDetails?.nodes)
                    && nodeDetails.nodes.some((node) => (node.isHost || String(node.id || '').startsWith('h')) && node.ip && node.mac);

                if (!hostsReady && retryCount > 0) {
                    detailRefreshTimer = window.setTimeout(() => refreshNodeDetails(retryCount - 1), 1200);
                    return;
                }

                view.setTopologyBuildStatus('当前拓扑节点详情已同步，可以继续注入流表并进行发送验证。', '#2e7d32');
            } catch (error) {
                console.error('刷新节点详细信息失败:', error);
            }
        }

        async function fetchSettingsAndDraw(edgeList) {
            try {
                const settings = await requestJson('/get_topo_settings', undefined, '读取拓扑设置失败');
                view.setSettings(settings || {});
            } catch (error) {
                console.warn('读取拓扑设置失败，使用默认设置');
                view.setSettings({});
            }

            view.drawNetwork(edgeList);
        }

        async function syncTopologyView() {
            const edgesData = await requestJson('/get_topology_data', undefined, '获取拓扑边数据失败');
            if (!Array.isArray(edgesData)) {
                throw new Error('拓扑边数据格式无效');
            }

            await fetchSettingsAndDraw(edgesData);
            const nodeDetails = await requestJson('/get_topology_nodes', undefined, '获取节点详情失败');
            view.applyNodeDetails(nodeDetails);
            await refreshVerificationProfile();
            scheduleNodeDetailRefresh();
        }

        function renderSemanticPolicySummary(profile) {
            const policyNode = document.getElementById('semanticPolicySummary');
            if (policyNode) {
                const flows = Array.isArray(profile?.semantic_policy?.flows) ? profile.semantic_policy.flows : [];
                if (flows.length === 0) {
                    policyNode.textContent = '当前拓扑还没有生成 semantic policy。先装载 P4、生成拓扑并注入流表后再查看。';
                } else {
                    const expanded = policyNode.dataset.semanticPolicyExpanded === '1';
                    const shouldCollapse = flows.length > 3 && !expanded;
                    const visibleFlows = shouldCollapse ? flows.slice(0, 3) : flows;
                    const hiddenCount = Math.max(flows.length - visibleFlows.length, 0);
                    const summaryLine = `当前已生成 ${flows.length} 条 flow 的 semantic policy，默认展示 ${visibleFlows.length} 条${hiddenCount > 0 ? `，另有 ${hiddenCount} 条已折叠` : ''}。`;
                    const flowCards = visibleFlows.map((flow) => {
                        const scopeLabel = flowDisplayLabel(flow);
                        const customizationLabel = flow.customized ? '人工微调' : '自动生成';
                        return [
                            '<article style="padding: 12px 14px; border: 1px solid var(--line); border-radius: 10px; background: var(--surface-bright); box-shadow: 0 1px 2px rgba(0,0,0,0.04);">',
                            `<div style="display:flex; justify-content:space-between; align-items:flex-start; gap:12px; margin-bottom:8px;"><strong style="font-size:0.95rem; color:var(--text-main);">${escapeHtml(scopeLabel)}</strong><span style="font-size:0.78rem; padding:2px 8px; border-radius:999px; background: var(--surface-muted); color: var(--text-soft); white-space:nowrap;">${escapeHtml(customizationLabel)}</span></div>`,
                            `<p style="margin:0 0 6px 0; color: var(--text-soft);">合法路径数：${flow.allowed_behavior_count} | 优先级：${escapeHtml(flow.priority || 'shortest')}</p>`,
                            `<p style="margin:0 0 6px 0; color: var(--text-soft);">must_pass：${escapeHtml((flow.must_pass || []).join(', ') || '无')} | avoid：${escapeHtml((flow.avoid || []).join(', ') || '无')}</p>`,
                            `<p style="margin:0; color: var(--text-soft);">自动不变量：包计数 ≤ ${flow.max_packets}，跳数 ≤ ${flow.max_hops}，备份预算 ≤ ${flow.max_degraded_packets}，状态变更 ≤ ${flow.max_state_changes}</p>`,
                            '</article>',
                        ].join('');
                    }).join('');

                    const toggleLabel = shouldCollapse ? `展开全部 ${flows.length} 条策略` : '收起多余策略';
                    policyNode.innerHTML = [
                        `<div style="margin-bottom:12px; padding:10px 12px; border-radius:10px; background: var(--surface-muted); border: 1px solid var(--line); color: var(--text-main); font-size:0.9rem; line-height:1.5;">${escapeHtml(summaryLine)}</div>`,
                        `<div style="display:grid; gap:10px; margin-bottom:12px;">${flowCards}</div>`,
                        hiddenCount > 0 || expanded
                            ? `<button type="button" data-semantic-policy-toggle="1" style="width:100%; border:1px solid var(--line); background: var(--surface-muted); color: var(--brand-strong); padding:10px 12px; border-radius:10px; font-weight:600; cursor:pointer;">${escapeHtml(toggleLabel)}</button>`
                            : '',
                    ].join('');

                    const toggleButton = policyNode.querySelector('[data-semantic-policy-toggle="1"]');
                    if (toggleButton && !toggleButton.dataset.bound) {
                        toggleButton.dataset.bound = '1';
                        toggleButton.addEventListener('click', () => {
                            policyNode.dataset.semanticPolicyExpanded = shouldCollapse ? '1' : '0';
                            renderSemanticPolicySummary(profile);
                        });
                    }
                }
            }
        }

        function renderSemanticRuntimeSummary(profile) {
            const runtimeNode = document.getElementById('semanticRuntimeSummary');
            if (runtimeNode) {
                const recentHistory = Array.isArray(profile?.semantic_history) ? profile.semantic_history : [];
                const stateSummary = Array.isArray(profile?.semantic_state_summary) ? profile.semantic_state_summary : [];

                if (recentHistory.length === 0 && stateSummary.length === 0) {
                    runtimeNode.textContent = '还没有 flow 级语义验证历史。发送一次单路径或 VBP 流量后，这里会显示状态演化与违规分类。';
                } else {
                    const summarizedFlowIds = new Set(stateSummary.map((item) => String(item.flow_id || '')));
                    const stateBlocks = stateSummary.slice(0, 6).map((item) => (
                        `<p><strong>${escapeHtml(item.flow_label || item.flow_id)}</strong> | state=${escapeHtml(item.current_state)} | packets=${item.packet_count} | degraded=${item.degraded_packets || 0} | state_changes=${item.state_change_count || 0} | verdict=${escapeHtml(item.last_verdict_label || item.last_verdict || 'unknown')} | risk=${item.risk_score || 0}/100 (${escapeHtml(item.risk_label || '低风险')})</p>`
                    ));
                    const historyBlocks = recentHistory
                        .slice(-10)
                        .reverse()
                        .filter((item) => !summarizedFlowIds.has(String(item.flow_id || '')))
                        .slice(0, 3)
                        .map((item) => (
                            `<p>${escapeHtml(item.flow_id)}：${escapeHtml(item.previous_state)} -> ${escapeHtml(item.current_state)}，违规=${escapeHtml((item.violation_types || []).join(', ') || '无')}，risk=${item.risk_score || 0}/100 (${escapeHtml(item.risk_label || '低风险')})，degraded=${item.degraded_packets || 0}，state_changes=${item.state_change_count || 0}</p>`
                        ));

                    runtimeNode.innerHTML = historyBlocks.length > 0
                        ? [...stateBlocks, '<hr style="border:0; border-top:1px dashed var(--line); margin:10px 0;">', ...historyBlocks].join('')
                        : stateBlocks.join('');
                }
            }
        }

        function renderRiskAlertSummary(profile) {
            const riskNode = document.getElementById('semanticRiskSummary');
            if (!riskNode) {
                return;
            }

            const riskSummary = Array.isArray(profile?.semantic_risk_summary) ? profile.semantic_risk_summary : [];
            const alerts = Array.isArray(profile?.semantic_alerts) ? profile.semantic_alerts : [];
            if (riskSummary.length === 0 && alerts.length === 0) {
                riskNode.textContent = '发送一次单路径或 VBP 验证流量后，这里会生成 flow 风险分、风险等级和可解释告警。';
                return;
            }

            const summaryBlocks = riskSummary.slice(0, 5).map((item) => [
                '<article class="risk-summary-card">',
                '<div class="risk-summary-head">',
                `<strong>${escapeHtml(item.flow_label || item.flow_id)}</strong>`,
                `<span class="risk-badge" data-risk="${escapeHtml(item.risk_level || 'low')}">${escapeHtml(`${item.risk_score || 0}/100 · ${item.risk_label || '低风险'}`)}</span>`,
                '</div>',
                `<p>${escapeHtml(item.risk_summary || '暂无风险摘要。')}</p>`,
                (item.risk_reasons || []).length > 0
                    ? `<ul class="risk-reasons">${item.risk_reasons.slice(0, 3).map((reason) => `<li>${escapeHtml(reason)}</li>`).join('')}</ul>`
                    : '',
                `<p class="risk-meta">状态=${escapeHtml(item.current_state || 'INIT')} | verdict=${escapeHtml(item.last_verdict || 'unknown')} | 违规=${escapeHtml((item.violation_types || []).join(', ') || '无')}</p>`,
                '</article>',
            ].join(''));

            const alertBlocks = alerts.slice(0, 4).map((item) => [
                '<article class="risk-alert-item">',
                '<div class="risk-summary-head">',
                `<strong>${escapeHtml(item.flow_label || item.flow_id)}</strong>`,
                `<span class="risk-badge" data-risk="${escapeHtml(item.risk_level || 'low')}">${escapeHtml(item.risk_label || '低风险')}</span>`,
                '</div>',
                `<p>${escapeHtml(item.risk_summary || '暂无风险摘要。')}</p>`,
                `<p class="risk-meta">${escapeHtml(formatTimestamp(item.timestamp))} | ${escapeHtml(item.previous_state || 'INIT')} -> ${escapeHtml(item.current_state || 'UNKNOWN')} | 违规=${escapeHtml((item.violation_types || []).join(', ') || '无')}</p>`,
                '</article>',
            ].join(''));

            riskNode.innerHTML = [
                `<div class="risk-summary-list">${summaryBlocks.join('')}</div>`,
                alertBlocks.length > 0 ? `<div class="risk-alert-stream">${alertBlocks.join('')}</div>` : '',
            ].join('');
        }

        function renderPathPlanner(profile) {
            const selectorNode = document.getElementById('pathFlowSelector');
            const candidateNode = document.getElementById('pathCandidateSelector');
            const metaNode = document.getElementById('pathPlannerMeta');
            if (!selectorNode || !candidateNode || !metaNode) {
                return;
            }

            const flows = Array.isArray(profile?.semantic_policy?.flows) ? profile.semantic_policy.flows : [];
            if (flows.length === 0) {
                selectedPathFlowId = '';
                selectorNode.innerHTML = '<option value="">暂无可调 flow</option>';
                candidateNode.innerHTML = '<option value="">暂无候选路径</option>';
                metaNode.textContent = '生成拓扑并注入流表后，这里会显示当前 flow 的候选路径、must_pass / avoid 和主路径说明。';
                setPathPlannerDisabled(true);
                setPathPlannerStatus('当前还没有可调整的预期路径。', '#607d8b');
                return;
            }

            setPathPlannerDisabled(false);
            const selectedFlow = findSelectedPathFlow(profile);
            selectorNode.innerHTML = flows.map((flow) => (
                `<option value="${escapeHtml(flow.flow_id)}">${escapeHtml(flowDisplayLabel(flow))}</option>`
            )).join('');
            selectorNode.value = selectedFlow?.flow_id || '';

            if (!selectedFlow) {
                return;
            }

            const behaviors = Array.isArray(selectedFlow.behaviors) ? selectedFlow.behaviors : [];
            candidateNode.innerHTML = behaviors.length > 0
                ? behaviors.map((behavior, index) => (
                    `<option value="${behavior.index}">${escapeHtml(`${behavior.label || `候选路径 ${index}`} | ${formatSwitchPath(behavior.path)}${index === 0 ? ' | 当前主路径' : ''}`)}</option>`
                )).join('')
                : '<option value="">暂无候选路径</option>';
            if (behaviors.length > 0) {
                candidateNode.value = String(behaviors[0].index ?? 0);
            }

            metaNode.textContent = [
                `作用域: ${flowDisplayLabel(selectedFlow)}`,
                `flow_id: ${selectedFlow.flow_id}`,
                `当前主路径: ${formatSwitchPath(behaviors[0]?.path || [])}`,
                `must_pass=${(selectedFlow.must_pass || []).join(', ') || '无'} | avoid=${(selectedFlow.avoid || []).join(', ') || '无'} | priority=${selectedFlow.priority || 'shortest'}`,
                '切换后会自动重写 intent.preferred_path，重新生成 runtime rules / behavior pool / semantic policy，并把对应流表重新下发到交换机。',
            ].join('\n');

            setPathPlannerStatus('选择一个候选路径后点击“切换为当前候选路径”，即可直接更新预期主路径。', '#607d8b');
        }

        function renderVbpPathManager(profile) {
            const container = document.getElementById('vbpPathManager');
            if (!container) {
                return;
            }

            const selectedFlow = findSelectedPathFlow(profile);
            if (!selectedFlow) {
                container.textContent = '生成拓扑并注入流表后，这里会显示当前 flow 的 VBP 路径集合。';
                setVbpPathEditorDisabled(true);
                setVbpPathStatus('当前没有可编辑的 VBP 路径集合。', '#607d8b');
                return;
            }

            const catalog = getFlowCatalog(selectedFlow);
            if (catalog.length === 0) {
                container.textContent = '当前 flow 暂时没有可选路径。';
                setVbpPathEditorDisabled(true);
                setVbpPathStatus('当前 flow 暂时没有可选路径。', '#607d8b');
                return;
            }

            setVbpPathEditorDisabled(false);
            const activeSignatures = new Set((selectedFlow.behaviors || []).map((behavior) => pathSignature(behavior.switch_path || behavior.path)));
            container.innerHTML = catalog.map((item, index) => {
                const badge = activeSignatures.has(item.signature)
                    ? (index === 0 ? '当前主路径' : '当前备份')
                    : '可加入';
                return [
                    '<label class="path-catalog-item">',
                    `<input type="checkbox" data-path-index="${item.index}" ${activeSignatures.has(item.signature) ? 'checked' : ''}>`,
                    '<span class="path-catalog-copy">',
                    `<strong>${escapeHtml(item.label)}</strong>`,
                    `<span>${escapeHtml(formatSwitchPath(item.switchPath))}</span>`,
                    '</span>',
                    `<span class="path-catalog-badge">${escapeHtml(badge)}</span>`,
                    '</label>',
                ].join('');
            }).join('');

            setVbpPathStatus('勾选后保存即可增删当前 flow 的 VBP 路径；第一条会作为主路径，其余路径按顺序作为备份。', '#607d8b');
        }

        function renderSemanticEditor(profile) {
            const selectorNode = document.getElementById('semanticFlowSelector');
            const metaNode = document.getElementById('semanticFlowMeta');
            const maxPacketsNode = document.getElementById('semanticMaxPackets');
            const maxHopsNode = document.getElementById('semanticMaxHops');
            const maxDegradedNode = document.getElementById('semanticMaxDegradedPackets');
            const maxStateChangesNode = document.getElementById('semanticMaxStateChanges');
            const requireRecoveryNode = document.getElementById('semanticRequireRecovery');
            const invariantsNode = document.getElementById('semanticInvariantsEditor');
            const transitionsNode = document.getElementById('semanticTransitionsEditor');

            if (!selectorNode || !metaNode || !maxPacketsNode || !maxHopsNode || !maxDegradedNode || !maxStateChangesNode || !requireRecoveryNode || !invariantsNode || !transitionsNode) {
                return;
            }

            const flows = Array.isArray(profile?.semantic_policy?.flows) ? profile.semantic_policy.flows : [];
            if (flows.length === 0) {
                selectedSemanticFlowId = '';
                selectorNode.innerHTML = '<option value="">暂无可编辑 flow</option>';
                maxPacketsNode.value = '';
                maxHopsNode.value = '';
                maxDegradedNode.value = '';
                maxStateChangesNode.value = '';
                requireRecoveryNode.value = 'true';
                invariantsNode.value = '[]';
                transitionsNode.value = '[]';
                metaNode.textContent = '选择一个 flow 后，这里会显示当前策略作用域、候选路径和编辑提示。';
                setSemanticEditorDisabled(true);
                setSemanticEditorStatus('当前还没有可编辑的 semantic policy。', '#607d8b');
                return;
            }

            setSemanticEditorDisabled(false);
            const selectedFlow = findSelectedSemanticFlow(profile);
            selectorNode.innerHTML = flows.map((flow) => {
                const scopeLabel = flowDisplayLabel(flow);
                return `<option value="${escapeHtml(flow.flow_id)}">${escapeHtml(scopeLabel)}</option>`;
            }).join('');
            selectorNode.value = selectedFlow?.flow_id || '';

            if (!selectedFlow) {
                return;
            }

            maxPacketsNode.value = String(selectedFlow.max_packets ?? '');
            maxHopsNode.value = String(selectedFlow.max_hops ?? '');
            maxDegradedNode.value = String(selectedFlow.max_degraded_packets ?? '');
            maxStateChangesNode.value = String(selectedFlow.max_state_changes ?? '');
            requireRecoveryNode.value = selectedFlow.require_primary_recovery === false ? 'false' : 'true';
            invariantsNode.value = prettyJson(selectedFlow.invariants || []);
            transitionsNode.value = prettyJson(selectedFlow.allowed_transitions || []);

            const behaviorLines = Array.isArray(selectedFlow.behaviors)
                ? selectedFlow.behaviors.map((behavior) => {
                    const hops = formatSwitchPath(behavior.path);
                    return `${behavior.label || `行为 ${behavior.index}`}: ${hops}`;
                })
                : [];
            const hiddenBehaviorCount = Math.max(behaviorLines.length - 2, 0);
            const behaviorPreview = behaviorLines.slice(0, 2);

            metaNode.textContent = [
                `作用域: ${flowDisplayLabel(selectedFlow)}`,
                `flow_id: ${selectedFlow.flow_id}`,
                `priority=${selectedFlow.priority || 'shortest'} | backup_level=${selectedFlow.backup_level ?? 1} | allowed_behavior_count=${selectedFlow.allowed_behavior_count ?? 1}`,
                `must_pass=${(selectedFlow.must_pass || []).join(', ') || '无'} | avoid=${(selectedFlow.avoid || []).join(', ') || '无'}`,
                `degraded_budget=${selectedFlow.max_degraded_packets ?? 0} | state_change_budget=${selectedFlow.max_state_changes ?? 0} | require_recovery=${selectedFlow.require_primary_recovery === false ? '否' : '是'}`,
                behaviorPreview.length > 0
                    ? `候选路径: ${behaviorPreview.join(' | ')}${hiddenBehaviorCount > 0 ? ` | 另有 ${hiddenBehaviorCount} 条已折叠` : ''}`
                    : '候选路径: 暂无',
                '保存时会自动同步 packet_count / path_hops / behavior_index / degraded_packets / state_change_count 这几类核心不变量。',
            ].join('\n');

            setSemanticEditorStatus(
                selectedFlow.customized
                    ? '当前 flow 正在使用人工微调后的语义策略。'
                    : '当前 flow 使用自动生成策略。调整后保存，下一次发送流量时就会按新约束验证。',
                selectedFlow.customized ? '#b66918' : '#607d8b',
            );
        }

        function renderFaultDrill(profile) {
            const flowSelector = document.getElementById('faultFlowSelector');
            const linkSelector = document.getElementById('faultLinkSelector');
            const metaNode = document.getElementById('faultDrillMeta');
            if (!flowSelector || !linkSelector || !metaNode) {
                return;
            }

            const flows = Array.isArray(profile?.semantic_policy?.flows) ? profile.semantic_policy.flows : [];
            if (flows.length === 0) {
                selectedFaultFlowId = '';
                flowSelector.innerHTML = '<option value="">暂无可演示 flow</option>';
                linkSelector.innerHTML = '<option value="">暂无可选链路</option>';
                metaNode.textContent = '生成拓扑并注入流表后，这里会按 flow 提供可直接注入故障的链路。';
                setFaultDrillDisabled(true);
                setFaultDrillStatus('当前没有可执行的故障演示。', '#607d8b');
                return;
            }

            setFaultDrillDisabled(false);
            const selectedFlow = findSelectedFaultFlow(profile);
            flowSelector.innerHTML = flows.map((flow) => (
                `<option value="${escapeHtml(flow.flow_id)}">${escapeHtml(flowDisplayLabel(flow))}</option>`
            )).join('');
            flowSelector.value = selectedFlow?.flow_id || '';

            if (!selectedFlow) {
                return;
            }

            const linkCatalog = getFaultLinkCatalog(selectedFlow);
            linkSelector.innerHTML = linkCatalog.length > 0
                ? linkCatalog.map((item) => (
                    `<option value="${escapeHtml(item.signature)}">${escapeHtml(`${item.label} | 影响 ${item.impactCount} 条候选路径${item.affectsPrimary ? ' | 含当前主路径' : ''}`)}</option>`
                )).join('')
                : '<option value="">暂无可选链路</option>';

            const selectedLink = linkCatalog[0] || null;
            if (selectedLink) {
                linkSelector.value = selectedLink.signature;
            }

            const lastReport = profile?.fault_drill_state || {};
            const isSameFlow = lastReport?.flow_id && lastReport.flow_id === selectedFlow.flow_id;
            metaNode.textContent = [
                `作用域: ${flowDisplayLabel(selectedFlow)}`,
                `当前主路径: ${formatSwitchPath(selectedFlow?.behaviors?.[0]?.path || [])}`,
                selectedLink
                    ? `推荐故障链路: ${selectedLink.label}（影响 ${selectedLink.impactCount} 条候选路径${selectedLink.affectsPrimary ? '，且覆盖当前主路径' : ''}）`
                    : '当前没有可执行的链路级故障点。',
                isSameFlow
                    ? `最近一次演示: ${lastReport.link_label || '未知链路'} | 状态=${lastReport.status || 'unknown'} | 注入后主路径=${formatSwitchPath(lastReport.after_primary_path || [])}`
                    : '点击“注入故障并自动自愈”后，系统会下线指定链路、剔除受影响路径并重新下发表。',
            ].join('\n');

            if (isSameFlow) {
                const restored = lastReport.status === 'restored';
                setFaultDrillStatus(
                    restored
                        ? `最近一次已恢复 ${lastReport.link_label || '链路'}，当前回到自动编排。`
                        : `最近一次故障演示已完成：${lastReport.link_label || '链路'} 下线后自动切换到 ${formatSwitchPath(lastReport.after_primary_path || [])}。`,
                    restored ? '#2e7d32' : '#b66918',
                );
            } else {
                setFaultDrillStatus('选择一条链路后点击“注入故障并自动自愈”，即可演示主备切换与自动重编排。', '#607d8b');
            }
        }

        function renderVerificationProfile(profile) {
            latestVerificationProfile = profile;
            renderPathPlanner(profile);
            renderVbpPathManager(profile);
            renderSemanticPolicySummary(profile);
            renderSemanticRuntimeSummary(profile);
            renderRiskAlertSummary(profile);
            renderSemanticEditor(profile);
            renderFaultDrill(profile);
        }

        async function refreshVerificationProfile() {
            if (!document.getElementById('semanticPolicySummary') && !document.getElementById('semanticRuntimeSummary')) {
                return;
            }

            try {
                const profile = await requestJson('/get_verification_profile', undefined, '读取验证配置失败');
                renderVerificationProfile(profile);
            } catch (error) {
                const policyNode = document.getElementById('semanticPolicySummary');
                const runtimeNode = document.getElementById('semanticRuntimeSummary');
                if (policyNode) {
                    policyNode.textContent = `读取 semantic policy 失败：${error.message}`;
                }
                if (runtimeNode) {
                    runtimeNode.textContent = `读取 flow 运行态失败：${error.message}`;
                }
                setPathPlannerStatus(`读取路径编排信息失败：${error.message}`, '#c62828');
                setSemanticEditorStatus(`读取 semantic policy 失败：${error.message}`, '#c62828');
                setFaultDrillStatus(`读取故障演示信息失败：${error.message}`, '#c62828');
            }
        }

        function handlePathFlowSelection() {
            const selectorNode = document.getElementById('pathFlowSelector');
            selectedPathFlowId = selectorNode?.value || '';
            if (latestVerificationProfile) {
                renderPathPlanner(latestVerificationProfile);
                renderVbpPathManager(latestVerificationProfile);
            }
        }

        function handleFaultFlowSelection() {
            const selectorNode = document.getElementById('faultFlowSelector');
            selectedFaultFlowId = selectorNode?.value || '';
            if (latestVerificationProfile) {
                renderFaultDrill(latestVerificationProfile);
            }
        }

        async function runFaultDrill(restore = false) {
            const selectedFlow = findSelectedFaultFlow(latestVerificationProfile);
            if (!selectedFlow) {
                setFaultDrillStatus('当前没有可执行故障演示的 flow。', '#c62828');
                return;
            }

            const linkCatalog = getFaultLinkCatalog(selectedFlow);
            const selectedSignature = document.getElementById('faultLinkSelector')?.value || '';
            const selectedLink = linkCatalog.find((item) => item.signature === selectedSignature) || linkCatalog[0];
            if (!selectedLink) {
                setFaultDrillStatus('请先选择一条可演示的链路。', '#c62828');
                return;
            }

            setFaultDrillStatus(
                restore ? '正在恢复链路并回归自动编排...' : '正在注入链路故障并执行自动自愈...',
                '#607d8b',
            );

            try {
                const data = await requestJson('/run_fault_drill', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        action: restore ? 'restore' : 'inject',
                        flow_id: selectedFlow.flow_id,
                        link: selectedLink.link,
                    }),
                }, '执行故障演示失败');

                await refreshVerificationProfile();
                setFaultDrillStatus(
                    data.message || '故障演示已完成。',
                    restore ? '#2e7d32' : '#b66918',
                );
            } catch (error) {
                setFaultDrillStatus(`执行失败：${error.message}`, '#c62828');
            }
        }

        async function applyExpectedPath(resetToAuto = false) {
            const selectedFlow = findSelectedPathFlow(latestVerificationProfile);
            if (!selectedFlow) {
                setPathPlannerStatus('当前没有可调整的 flow。', '#c62828');
                return;
            }

            const candidateValue = document.getElementById('pathCandidateSelector')?.value;
            const behaviorIndex = Number.parseInt(candidateValue || '', 10);
            if (!resetToAuto && !Number.isInteger(behaviorIndex)) {
                setPathPlannerStatus('请先选择一个候选路径。', '#c62828');
                return;
            }

            setPathPlannerStatus(resetToAuto ? '正在恢复自动主路径...' : '正在切换预期主路径...', '#607d8b');
            try {
                const data = await requestJson('/apply_expected_path', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        flow_id: selectedFlow.flow_id,
                        behavior_index: resetToAuto ? undefined : behaviorIndex,
                        reset_to_auto: resetToAuto,
                    }),
                }, '切换预期路径失败');

                await refreshVerificationProfile();
                setPathPlannerStatus(data.message || '预期路径已更新。', '#2e7d32');
            } catch (error) {
                setPathPlannerStatus(`切换失败：${error.message}`, '#c62828');
            }
        }

        async function saveVbpPathSet(resetToAuto = false) {
            const selectedFlow = findSelectedPathFlow(latestVerificationProfile);
            if (!selectedFlow) {
                setVbpPathStatus('当前没有可编辑的 flow。', '#c62828');
                return;
            }

            const catalog = getFlowCatalog(selectedFlow);
            const selectedPaths = Array.from(document.querySelectorAll('#vbpPathManager input[type="checkbox"]:checked'))
                .map((node) => Number.parseInt(node.getAttribute('data-path-index') || '', 10))
                .filter(Number.isInteger)
                .map((index) => catalog.find((item) => item.index === index))
                .filter(Boolean)
                .map((item) => item.switchPath);

            if (!resetToAuto && selectedPaths.length === 0) {
                setVbpPathStatus('请至少保留一条 VBP 路径。', '#c62828');
                return;
            }

            setVbpPathStatus(resetToAuto ? '正在恢复系统推荐路径集合...' : '正在保存 VBP 路径集合...', '#607d8b');

            try {
                const data = await requestJson('/update_vbp_paths', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        flow_id: selectedFlow.flow_id,
                        enabled_paths: selectedPaths,
                        reset_to_auto: resetToAuto,
                    }),
                }, '更新 VBP 路径集合失败');

                await refreshVerificationProfile();
                setVbpPathStatus(data.message || 'VBP 路径集合已更新。', '#2e7d32');
            } catch (error) {
                setVbpPathStatus(`保存失败：${error.message}`, '#c62828');
            }
        }

        function handleSemanticFlowSelection() {
            const selectorNode = document.getElementById('semanticFlowSelector');
            selectedSemanticFlowId = selectorNode?.value || '';
            if (latestVerificationProfile) {
                renderSemanticEditor(latestVerificationProfile);
            }
        }

        function restoreSemanticEditor() {
            if (!latestVerificationProfile) {
                return;
            }

            renderSemanticEditor(latestVerificationProfile);
            setSemanticEditorStatus('已恢复当前加载值，尚未保存。', '#607d8b');
        }

        async function saveSemanticPolicy() {
            const selectedFlow = findSelectedSemanticFlow(latestVerificationProfile);
            if (!selectedFlow) {
                setSemanticEditorStatus('当前没有可保存的 flow。', '#c62828');
                return;
            }

            const maxPacketsValue = document.getElementById('semanticMaxPackets')?.value.trim();
            const maxHopsValue = document.getElementById('semanticMaxHops')?.value.trim();
            const maxDegradedValue = document.getElementById('semanticMaxDegradedPackets')?.value.trim();
            const maxStateChangesValue = document.getElementById('semanticMaxStateChanges')?.value.trim();
            const requireRecoveryValue = document.getElementById('semanticRequireRecovery')?.value || 'true';
            const invariantsValue = document.getElementById('semanticInvariantsEditor')?.value || '[]';
            const transitionsValue = document.getElementById('semanticTransitionsEditor')?.value || '[]';

            const maxPackets = Number.parseInt(maxPacketsValue, 10);
            const maxHops = Number.parseInt(maxHopsValue, 10);
            const maxDegradedPackets = Number.parseInt(maxDegradedValue, 10);
            const maxStateChanges = Number.parseInt(maxStateChangesValue, 10);
            if (!Number.isInteger(maxPackets) || maxPackets < 1) {
                setSemanticEditorStatus('最大包计数必须是大于等于 1 的整数。', '#c62828');
                return;
            }
            if (!Number.isInteger(maxHops) || maxHops < 0) {
                setSemanticEditorStatus('最大跳数必须是大于等于 0 的整数。', '#c62828');
                return;
            }
            if (!Number.isInteger(maxDegradedPackets) || maxDegradedPackets < 1) {
                setSemanticEditorStatus('备份包预算必须是大于等于 1 的整数。', '#c62828');
                return;
            }
            if (!Number.isInteger(maxStateChanges) || maxStateChanges < 1) {
                setSemanticEditorStatus('状态变更预算必须是大于等于 1 的整数。', '#c62828');
                return;
            }

            let invariants;
            let allowedTransitions;
            try {
                invariants = JSON.parse(invariantsValue);
                allowedTransitions = JSON.parse(transitionsValue);
            } catch (error) {
                setSemanticEditorStatus(`JSON 解析失败：${error.message}`, '#c62828');
                return;
            }

            if (!Array.isArray(invariants)) {
                setSemanticEditorStatus('不变量编辑区必须是 JSON 数组。', '#c62828');
                return;
            }
            if (!Array.isArray(allowedTransitions)) {
                setSemanticEditorStatus('AllowedTransitions 编辑区必须是 JSON 数组。', '#c62828');
                return;
            }

            setSemanticEditorStatus('正在保存语义策略...', '#607d8b');

            try {
                const data = await requestJson('/update_semantic_policy', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        flow_id: selectedFlow.flow_id,
                        max_packets: maxPackets,
                        max_hops: maxHops,
                        max_degraded_packets: maxDegradedPackets,
                        max_state_changes: maxStateChanges,
                        require_primary_recovery: requireRecoveryValue !== 'false',
                        invariants,
                        allowed_transitions: allowedTransitions,
                    }),
                }, '保存 semantic policy 失败');

                await refreshVerificationProfile();
                setSemanticEditorStatus(data.message || '语义策略已保存。', '#2e7d32');
            } catch (error) {
                setSemanticEditorStatus(`保存失败：${error.message}`, '#c62828');
            }
        }

        async function sendTopology() {
            view.setTopologyBuildStatus('正在向后端提交当前拓扑构建请求...');

            try {
                const data = await requestJson('/select_topology', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ topology: config.topologySelection }),
                }, '拓扑生成请求失败');

                console.log('Topology selected:', data);
                view.setTopologyBuildStatus(config.buildAcceptedMessage(data));
                await syncTopologyView();
            } catch (error) {
                console.error('Error:', error);
                view.setTopologyBuildStatus(`构建请求失败：${error.message}`, '#c62828');
            }
        }

        async function loadP4Code() {
            try {
                const data = await requestJson('/load_p4_code', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                }, '装载 P4 代码失败');

                const resultNode = document.getElementById('loadResult');
                if (resultNode) {
                    resultNode.innerText = data.message;
                }
                view.setTopologyBuildStatus(config.p4LoadedMessage, '#2e7d32');
                await refreshVerificationProfile();
            } catch (error) {
                console.error('Error loading P4 code:', error);
                const resultNode = document.getElementById('loadResult');
                if (resultNode) {
                    resultNode.innerText = error.message;
                }
                view.setTopologyBuildStatus(`P4 装载失败：${error.message}`, '#c62828');
            }
        }

        async function injectFlowTable() {
            try {
                const data = await requestJson('/inject_flow_table', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                }, '注入流表失败');

                const resultNode = document.getElementById('injectResult');
                if (resultNode) {
                    resultNode.innerText = data.message;
                }
                view.setTopologyBuildStatus(config.flowInjectedMessage, '#2e7d32');
                await refreshVerificationProfile();
            } catch (error) {
                console.error('Error injecting flow table:', error);
                const resultNode = document.getElementById('injectResult');
                if (resultNode) {
                    resultNode.innerText = error.message;
                }
                view.setTopologyBuildStatus(`流表注入失败：${error.message}`, '#c62828');
            }
        }

        function buildPathSummary(pathJson, resultBox, flowProfile) {
            const expectedPath = Array.isArray(pathJson.expected_path) ? pathJson.expected_path : [];
            const matchedBehaviorPath = Array.isArray(pathJson.matched_behavior_path) ? pathJson.matched_behavior_path : [];
            const recoverPath = Array.isArray(pathJson.recover_path) ? pathJson.recover_path : [];

            let pathText = expectedPath.length
                ? `${config.expectedPathLabel}：${expectedPath.map((id) => `s${id}`).join(' → ')}`
                : `${config.expectedPathLabel}：无`;

            if (pathJson.behavior_status) {
                pathText += `\nVBP 判定：${pathJson.behavior_label || pathJson.behavior_status}`;
                if (pathJson.behavior_status === 'backup') {
                    resultBox.style.color = '#f9a825';
                } else if (pathJson.behavior_status === 'illegal') {
                    resultBox.style.color = '#c62828';
                } else if (pathJson.behavior_status === 'primary') {
                    resultBox.style.color = '#2e7d32';
                }
            }

            if (matchedBehaviorPath.length > 0) {
                pathText += `\n命中路径：${matchedBehaviorPath.map((id) => `s${id}`).join(' → ')}`;
            }
            if (Array.isArray(flowProfile?.behaviors) && flowProfile.behaviors.length > 0) {
                const legalPathLines = flowProfile.behaviors.map((behavior, index) => (
                    `${index === 0 ? '主路径' : `备份 ${index}`}：${formatSwitchPath(behavior.switch_path || behavior.path)}`
                ));
                pathText += `\n合法 VBP 路径集合：\n${legalPathLines.join('\n')}`;
            }
            if (!pathJson.consistence && recoverPath.length > 0) {
                pathText += `\n实际错误路径：${recoverPath.map((id) => `s${id}`).join(' → ')}`;
            }

            const semantic = pathJson.semantic_verification;
            if (semantic) {
                pathText += `\n语义判定：${semantic.verdict_label || semantic.verdict}`;
                pathText += `\nFlow 状态：${semantic.previous_state} → ${semantic.current_state}`;
                pathText += `\n包计数：${semantic.packet_count}/${semantic.max_packets}`;
                pathText += `\n备份包预算：${semantic.degraded_packets}/${semantic.max_degraded_packets}`;
                pathText += `\n状态变更预算：${semantic.state_change_count}/${semantic.max_state_changes}`;
                pathText += `\n风险评分：${semantic.risk_score || 0}/100 (${semantic.risk_label || '低风险'})`;
                if (Array.isArray(semantic.risk_reasons) && semantic.risk_reasons.length > 0) {
                    pathText += `\n风险说明：${semantic.risk_reasons.slice(0, 2).join('；')}`;
                }
                if (semantic.require_primary_recovery) {
                    pathText += `\n恢复约束：备份状态需在 ${semantic.max_degraded_packets} 包内回到 PRIMARY`;
                }
                if (Array.isArray(semantic.violation_types) && semantic.violation_types.length > 0) {
                    pathText += `\n违规类型：${semantic.violation_types.join(', ')}`;
                    resultBox.style.color = '#c62828';
                } else if (semantic.verdict === 'degraded') {
                    resultBox.style.color = '#f9a825';
                }
            }

            return pathText;
        }

        async function sendTraffic(endpoint, modeLabel) {
            const srcHost = document.getElementById('srcHost')?.value.trim();
            const dstHost = document.getElementById('dstHost')?.value.trim();
            const resultBox = document.getElementById('sendResult');
            if (!resultBox) {
                return;
            }

            if (!srcHost || !dstHost) {
                resultBox.style.color = 'red';
                resultBox.textContent = '请填写完整的两个主机 ID';
                return;
            }

            try {
                const data = await requestJson(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ src: srcHost, dst: dstHost }),
                }, '发送请求失败');

                resultBox.style.color = 'green';
                resultBox.textContent = `[${modeLabel}] 发送成功：${data.result}`;

                window.setTimeout(async () => {
                    try {
                        const pathData = await requestJson('/get_res_json', undefined, '读取路径数据失败');
                        const pathJson = typeof pathData === 'string' ? JSON.parse(pathData) : pathData;
                        if (!pathJson || pathJson.error) {
                            throw new Error(pathJson?.error || '路径数据为空');
                        }

                        const flowProfile = findFlowForResult(pathJson);
                        view.highlightPath(pathJson, {
                            behaviors: flowProfile?.behaviors || [],
                        });
                        resultBox.innerText += `\n${buildPathSummary(pathJson, resultBox, flowProfile)}`;
                        await refreshVerificationProfile();
                    } catch (error) {
                        resultBox.style.color = 'red';
                        resultBox.textContent = `读取路径数据失败：${error.message}`;
                    }
                }, 5000);
            } catch (error) {
                resultBox.style.color = 'red';
                resultBox.textContent = `[${modeLabel}] 发送失败：${error.message}`;
            }
        }

        async function handleFlowTableModification() {
            const swid = document.getElementById('modSwid')?.value.trim();
            const dstHost = document.getElementById('modDstHost')?.value.trim();
            const dstSwid = document.getElementById('modDstSwid')?.value.trim();

            if (!swid || !dstHost || !dstSwid) {
                window.alert('请填写所有输入项！');
                return;
            }

            try {
                const data = await requestJson('/modify_flow_table', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        swid,
                        dst_host: dstHost,
                        dst_swid: dstSwid,
                    }),
                }, '修改流表失败');

                const resultBox = document.getElementById('modifyResult');
                if (!resultBox) {
                    return;
                }

                resultBox.style.color = data.status === 'success' ? 'green' : 'red';
                resultBox.innerText = data.status === 'success' ? data.msg : `修改失败：${data.msg}`;
            } catch (error) {
                console.error('请求失败:', error);
                const resultBox = document.getElementById('modifyResult');
                if (resultBox) {
                    resultBox.innerText = '请求失败，请检查服务器连接。';
                }
            }
        }

        function handleUploadReady(event) {
            const summary = event.detail;
            view.setTopologyBuildStatus(config.uploadReadyMessage(summary));
        }

        function autoRestorePendingTopology() {
            if (!config.autoRestorePendingTopology) {
                return;
            }

            const pendingTopology = localStorage.getItem('pendingTopology');
            const pendingModel = localStorage.getItem('pendingModel');
            if (!pendingTopology) {
                console.log('未检测到待处理的拓扑。');
                return;
            }

            console.log('检测到待处理的拓扑，开始自动构建...');
            view.setTopologyBuildStatus(config.autoRestoreStatusMessage);
            localStorage.removeItem('pendingTopology');
            localStorage.removeItem('pendingModel');

            const topoFile = new File([pendingTopology], 'config.json', { type: 'application/json' });
            const aiSidebar = document.getElementById('ai-assistant-sidebar');
            if (aiSidebar) {
                aiSidebar.classList.add('open');
            }

            if (window.P4PrimeAssistant && typeof window.P4PrimeAssistant.autoUploadAndInitAI === 'function') {
                window.P4PrimeAssistant.autoUploadAndInitAI(topoFile, pendingModel);
            }
        }

        function bindEvents() {
            document.querySelector('.generateFattree6')?.addEventListener('click', sendTopology);
            document.querySelector('.loadP4Code')?.addEventListener('click', loadP4Code);
            document.querySelector('.injectFlowTable')?.addEventListener('click', injectFlowTable);
            document.getElementById('sendButton')?.addEventListener('click', () => {
                sendTraffic(config.primarySendEndpoint, config.primarySendLabel);
            });

            if (config.enableSecondarySend) {
                document.getElementById('sendVbpButton')?.addEventListener('click', () => {
                    sendTraffic(config.secondarySendEndpoint, config.secondarySendLabel);
                });
            }

            document.getElementById('modifyButton')?.addEventListener('click', handleFlowTableModification);
            document.getElementById('modSwid')?.addEventListener('blur', () => {
                const switchId = document.getElementById('modSwid')?.value.trim();
                view.updateDstSwitchOptions(switchId);
            });
            document.getElementById('pathFlowSelector')?.addEventListener('change', handlePathFlowSelection);
            document.getElementById('applyExpectedPathButton')?.addEventListener('click', () => applyExpectedPath(false));
            document.getElementById('resetExpectedPathButton')?.addEventListener('click', () => applyExpectedPath(true));
            document.getElementById('saveVbpPathsButton')?.addEventListener('click', () => saveVbpPathSet(false));
            document.getElementById('resetVbpPathsButton')?.addEventListener('click', () => saveVbpPathSet(true));
            document.getElementById('faultFlowSelector')?.addEventListener('change', handleFaultFlowSelection);
            document.getElementById('injectFaultDrillButton')?.addEventListener('click', () => runFaultDrill(false));
            document.getElementById('restoreFaultDrillButton')?.addEventListener('click', () => runFaultDrill(true));
            document.getElementById('semanticFlowSelector')?.addEventListener('change', handleSemanticFlowSelection);
            document.getElementById('semanticReloadButton')?.addEventListener('click', restoreSemanticEditor);
            document.getElementById('semanticSaveButton')?.addEventListener('click', saveSemanticPolicy);
            window.addEventListener('uploaded-topology-ready', handleUploadReady);
        }

        function init() {
            if (initialized) {
                return;
            }

            initialized = true;
            if (config.initialStatusMessage) {
                view.setTopologyBuildStatus(config.initialStatusMessage);
            }

            bindEvents();
            autoRestorePendingTopology();
            refreshVerificationProfile();
        }

        return { init };
    }

    window.P4PrimeWorkspaceRuntime = { create };
}());