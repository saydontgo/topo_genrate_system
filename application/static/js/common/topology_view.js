(function () {
    const DEFAULT_SETTINGS = {
        hostShape: 'ellipse',
        hostColor: '#FFD700',
        hostSize: 25,
        switchShape: 'box',
        switchColor: '#87CEEB',
        switchSize: 25,
    };

    function normalizeSettings(settings) {
        return {
            hostShape: settings?.hostShape || settings?.host?.shape || DEFAULT_SETTINGS.hostShape,
            hostColor: settings?.hostColor || settings?.host?.color || DEFAULT_SETTINGS.hostColor,
            hostSize: settings?.hostSize || settings?.host?.size || DEFAULT_SETTINGS.hostSize,
            switchShape: settings?.switchShape || settings?.switch?.shape || DEFAULT_SETTINGS.switchShape,
            switchColor: settings?.switchColor || settings?.switch?.color || DEFAULT_SETTINGS.switchColor,
            switchSize: settings?.switchSize || settings?.switch?.size || DEFAULT_SETTINGS.switchSize,
        };
    }

    function create(selectors = {}) {
        const state = {
            network: null,
            currentEdges: [],
            nodeDetailMap: {},
            topoSettings: { ...DEFAULT_SETTINGS },
            selectors: {
                network: '#network',
                hostHint: '#hostHint',
                switchHint: '#switchHint',
                nodeInfoContent: '#nodeInfoContent',
                topologyBuildStatus: '#topologyBuildStatus',
                modDstSwid: '#modDstSwid',
                ...selectors,
            },
        };

        function query(selectorKey) {
            return document.querySelector(state.selectors[selectorKey]);
        }

        function setTopologyBuildStatus(message, color = '#006064') {
            const statusNode = query('topologyBuildStatus');
            if (!statusNode) {
                return;
            }

            statusNode.style.color = color;
            statusNode.textContent = message;
        }

        function applyNodeDetails(nodeDetails) {
            if (!nodeDetails || !Array.isArray(nodeDetails.nodes)) {
                return;
            }

            nodeDetails.nodes.forEach((node) => {
                state.nodeDetailMap[node.id] = {
                    ...(state.nodeDetailMap[node.id] || {}),
                    ...node,
                };
            });
        }

        function showNodeInfo(node) {
            const infoContainer = query('nodeInfoContent');
            if (!infoContainer || !node) {
                return;
            }

            const detail = {
                ...(state.nodeDetailMap[node.id] || {}),
                ...node,
            };
            const connectedEdges = state.currentEdges.filter((edge) => edge.from === node.id || edge.to === node.id);
            const connectedNodes = new Set();
            const isSwitch = node.id.startsWith('s');

            connectedEdges.forEach((edge) => {
                connectedNodes.add(edge.from === node.id ? edge.to : edge.from);
            });

            let html = `<p><strong>节点ID：</strong> ${node.id}</p>`;
            html += `<p><strong>类型：</strong> ${isSwitch ? '交换机' : '主机'}</p>`;

            if (!isSwitch) {
                html += `<p><strong>IP地址：</strong> ${detail.ip || '-'}</p>`;
                html += `<p><strong>MAC地址：</strong> ${detail.mac || '-'}</p>`;
                if (detail.access_switch) {
                    html += `<p><strong>接入交换机：</strong> ${detail.access_switch}</p>`;
                }
            } else {
                html += `<p><strong>设备编号：</strong> ${detail.device_id || '-'}</p>`;
                html += `<p><strong>Thrift 端口：</strong> ${detail.thrift_port || '-'}</p>`;
            }

            html += '<p><strong>连接节点：</strong></p><ul>';
            connectedNodes.forEach((connectedNodeId) => {
                html += `<li>${connectedNodeId}</li>`;
            });
            html += '</ul>';

            infoContainer.innerHTML = html;
        }

        function clearNodeInfo() {
            const infoContainer = query('nodeInfoContent');
            if (!infoContainer) {
                return;
            }

            infoContainer.innerHTML = '点击任意节点查看详情';
        }

        function updateRangeHints(hostList, switchList) {
            const hostHint = query('hostHint');
            const switchHint = query('switchHint');

            if (hostHint) {
                const hostRange = hostList.length ? `${hostList[0]} - ${hostList[hostList.length - 1]}` : '无';
                hostHint.innerText = `可填写主机范围：${hostRange}`;
            }

            if (switchHint) {
                const switchRange = switchList.length ? `${switchList[0]} - ${switchList[switchList.length - 1]}` : '无';
                switchHint.innerText = `可填写交换机范围：${switchRange}`;
            }
        }

        function drawNetwork(edgeList) {
            if (!Array.isArray(edgeList)) {
                console.error('drawNetwork 收到的 edgeList 不是数组:', edgeList);
                setTopologyBuildStatus('拓扑边数据异常，无法渲染图结构。', '#c62828');
                return;
            }

            if (edgeList.length === 0) {
                console.error('drawNetwork 收到的 edgeList 为空');
                setTopologyBuildStatus('当前没有可绘制的边数据，拓扑图未生成。', '#c62828');
                return;
            }

            if (!window.vis || !window.vis.DataSet || !window.vis.Network) {
                setTopologyBuildStatus('vis-network 未正确加载，无法渲染拓扑图。', '#c62828');
                return;
            }

            state.currentEdges = edgeList;
            const nodesSet = new Set();
            edgeList.forEach((edge) => {
                nodesSet.add(edge.from);
                nodesSet.add(edge.to);
            });

            const hostList = [];
            const switchList = [];
            const nodes = Array.from(nodesSet).map((id) => {
                const isSwitch = id.startsWith('s');
                const detail = state.nodeDetailMap[id] || {};
                if (isSwitch) {
                    switchList.push(id);
                } else {
                    hostList.push(id);
                }

                return {
                    id,
                    label: id,
                    shape: isSwitch ? state.topoSettings.switchShape : state.topoSettings.hostShape,
                    color: isSwitch ? state.topoSettings.switchColor : state.topoSettings.hostColor,
                    size: isSwitch ? state.topoSettings.switchSize : state.topoSettings.hostSize,
                    ip: detail.ip || '',
                    mac: detail.mac || '',
                    access_switch: detail.access_switch || '',
                    device_id: detail.device_id || '',
                    thrift_port: detail.thrift_port || '',
                };
            });

            hostList.sort((left, right) => parseInt(left.slice(1), 10) - parseInt(right.slice(1), 10));
            switchList.sort((left, right) => parseInt(left.slice(1), 10) - parseInt(right.slice(1), 10));
            updateRangeHints(hostList, switchList);

            const container = query('network');
            if (!container) {
                console.error('未找到 #network 容器');
                setTopologyBuildStatus('页面缺少拓扑容器，无法渲染图结构。', '#c62828');
                return;
            }

            if (state.network) {
                state.network.destroy();
                state.network = null;
            }
            container.innerHTML = '';

            const data = {
                nodes: new window.vis.DataSet(nodes),
                edges: new window.vis.DataSet(edgeList),
            };
            const options = {
                interaction: { hover: true },
                physics: {
                    enabled: true,
                    barnesHut: { gravitationalConstant: -10000 },
                },
                nodes: {
                    font: { size: 25 },
                },
            };

            state.network = new window.vis.Network(container, data, options);
            window.hostList = hostList;
            window.switchList = switchList;

            state.network.on('click', (params) => {
                if (params.nodes.length > 0) {
                    const nodeId = params.nodes[0];
                    const node = data.nodes.get(nodeId);
                    showNodeInfo(node);
                    return;
                }

                clearNodeInfo();
            });
        }

        function highlightPath(data, options = {}) {
            const expectedPath = Array.isArray(data.expected_path) ? data.expected_path : [];
            const matchedBehaviorPath = Array.isArray(data.matched_behavior_path) ? data.matched_behavior_path : [];
            const recoverPath = Array.isArray(data.recover_path) ? data.recover_path : [];
            const consistence = data.consistence;
            const behaviorStatus = data.behavior_status;
            const behaviors = Array.isArray(options.behaviors) ? options.behaviors : [];
            const edgeUpdates = [];

            function toSwitchPath(path) {
                if (!Array.isArray(path)) {
                    return [];
                }

                return path.map((nodeId) => {
                    if (typeof nodeId === 'string') {
                        return nodeId.startsWith('s') ? nodeId : `s${nodeId}`;
                    }
                    return `s${nodeId}`;
                });
            }

            function queuePath(path, color, width, dashes = false) {
                const switchPath = toSwitchPath(path);
                if (switchPath.length <= 1) {
                    return;
                }

                for (let index = 0; index < switchPath.length - 1; index += 1) {
                    edgeUpdates.push({
                        from: switchPath[index],
                        to: switchPath[index + 1],
                        color: { color },
                        width,
                        dashes,
                    });
                }
            }

            behaviors.forEach((behavior, index) => {
                const switchPath = behavior.switch_path || behavior.path;
                const isPrimary = behavior.level === 'primary' || index === 0;
                queuePath(switchPath, isPrimary ? '#2e7d32' : '#f9a825', isPrimary ? 3.2 : 2.6, !isPrimary);
            });

            if (behaviorStatus === 'primary' && matchedBehaviorPath.length > 1) {
                queuePath(matchedBehaviorPath, '#2e7d32', 4.8);
            } else if (behaviorStatus === 'backup' && matchedBehaviorPath.length > 1) {
                queuePath(matchedBehaviorPath, '#f9a825', 4.8);
            } else if (!consistence && recoverPath.length > 1) {
                queuePath(recoverPath, '#c62828', 4.4);
            } else if (expectedPath.length > 1) {
                queuePath(expectedPath, '#2e7d32', 4);
            }

            if (!state.network || !state.network.body || !state.network.body.data || !state.network.body.data.edges) {
                console.error('Network body data edges are not available');
                return;
            }

            const allEdges = state.network.body.data.edges.get();
            allEdges.forEach((edge) => {
                state.network.body.data.edges.update({
                    id: edge.id,
                    color: { color: '#848484' },
                    width: 1,
                    dashes: false,
                });
            });

            edgeUpdates.forEach((update) => {
                const matchedEdge = allEdges.find((edge) => (
                    (edge.from === update.from && edge.to === update.to)
                    || (edge.from === update.to && edge.to === update.from)
                ));
                if (!matchedEdge) {
                    return;
                }

                state.network.body.data.edges.update({
                    id: matchedEdge.id,
                    color: update.color,
                    width: update.width,
                    dashes: update.dashes,
                });
            });
        }

        function updateDstSwitchOptions(switchId) {
            const dstSelect = query('modDstSwid');
            if (!dstSelect) {
                return;
            }

            dstSelect.innerHTML = '';

            if (!switchId || !switchId.startsWith('s')) {
                dstSelect.innerHTML = '<option value="">请输入有效交换机ID</option>';
                return;
            }

            const neighborSet = new Set();
            state.currentEdges.forEach((edge) => {
                if (edge.from === switchId && edge.to.startsWith('s')) {
                    neighborSet.add(edge.to);
                }
                if (edge.to === switchId && edge.from.startsWith('s')) {
                    neighborSet.add(edge.from);
                }
            });

            if (neighborSet.size === 0) {
                dstSelect.innerHTML = '<option value="">无相邻交换机</option>';
                return;
            }

            dstSelect.innerHTML = '<option value="">请选择相邻交换机</option>';
            neighborSet.forEach((switchName) => {
                const option = document.createElement('option');
                option.value = switchName;
                option.textContent = switchName;
                dstSelect.appendChild(option);
            });
        }

        return {
            setTopologyBuildStatus,
            applyNodeDetails,
            clearNodeInfo,
            drawNetwork,
            highlightPath,
            updateDstSwitchOptions,
            setSettings(settings) {
                state.topoSettings = normalizeSettings(settings || {});
            },
            getCurrentEdges() {
                return state.currentEdges.slice();
            },
        };
    }

    window.P4PrimeTopologyView = { create };
}());