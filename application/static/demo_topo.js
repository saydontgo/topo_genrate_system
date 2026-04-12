// 获取FatTree4和FatTree6的点击事件
// const fatTree4 = document.querySelector('.fatTree4');
const fatTree6 = document.querySelector('.generateFattree6');
let network;
let currentEdges = [];
let topoSettings = {
    hostShape: 'ellipse',
    hostColor: '#FFD700',
    hostSize: 25,
    switchShape: 'box',
    switchColor: '#87CEEB',
    switchSize: 25
};
// 更新显示选中的拓扑
// fatTree4.addEventListener('click', () => {
//     sendTopology(4);
// });

fatTree6.addEventListener('click', () => {
    sendTopology("demo");
});

let nodeDetailMap = {};  // 保存节点的详细信息（IP、MAC）

function sendTopology(topology) {
    fetch('/select_topology', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topology: topology })
    }).then(response => response.json())
      .then(data => {
        console.log('Topology selected:', data);

        // 获取拓扑边数据
        fetch('/get_topology_data')
            .then(response => response.json())
            .then(edgesData => {
                // 获取节点详细信息
                fetch('/get_topology_nodes')
                    .then(res => res.json())
                    .then(nodeDetails => {
                        // 构建节点信息映射
                        nodeDetails.nodes.forEach(node => {
                            nodeDetailMap[node.id] = node;
                        });

                        // 获取设置并绘图（修改点）
                        fetchSettingsAndDraw(edgesData);

                    })
                    .catch(err => console.error('获取节点详细信息失败:', err));
            })
            .catch(err => console.error('获取拓扑数据失败:', err));
    })
    .catch(error => console.error('Error:', error));
}


// 获取拓扑设置
function fetchSettingsAndDraw(edgeList) {
    fetch('/get_topo_settings')
        .then(res => res.json())
        .then(settings => {
            topoSettings = settings || topoSettings;
            drawNetwork(edgeList); // 在设置加载后绘图
        })
        .catch(err => {
            console.warn("读取拓扑设置失败，使用默认设置");
            drawNetwork(edgeList);
        });
}

function drawNetwork(edgeList) {
    currentEdges = edgeList;
    const nodesSet = new Set();
    edgeList.forEach(edge => {
        nodesSet.add(edge.from);
        nodesSet.add(edge.to);
    });

    const hostList = [];
    const switchList = [];

    // 构建节点对象数组，读取设置
    const nodes = Array.from(nodesSet).map((id) => {
        let nodeType = id.startsWith('s') ? 'switch' : 'host';
        let shape = nodeType === 'switch' ? topoSettings.switchShape : topoSettings.hostShape;
        let color = nodeType === 'switch' ? topoSettings.switchColor : topoSettings.hostColor;
        let size = nodeType === 'switch' ? topoSettings.switchSize : topoSettings.hostSize;

        if (nodeType === 'host') hostList.push(id);
        else switchList.push(id);

        return {
            id: id,
            label: id,
            shape: shape,
            color: color,
            size: size
        };
    });

    // 排序主机和交换机 ID
    hostList.sort((a, b) => parseInt(a.slice(1)) - parseInt(b.slice(1)));
    switchList.sort((a, b) => parseInt(a.slice(1)) - parseInt(b.slice(1)));

    // 显示提示范围
    const hostRange = hostList.length ? `${hostList[0]} - ${hostList[hostList.length - 1]}` : '无';
    const switchRange = switchList.length ? `${switchList[0]} - ${switchList[switchList.length - 1]}` : '无';
    document.getElementById("hostHint").innerText = `可填写主机范围：${hostRange}`;
    document.getElementById("switchHint").innerText = `可填写交换机范围：${switchRange}`;

    // 初始化网络图
    const container = document.getElementById('network');
    const data = {
        nodes: new vis.DataSet(nodes),
        edges: new vis.DataSet(edgeList)
    };

    const options = {
        interaction: { hover: true },
        physics: {
            enabled: true,
            barnesHut: { gravitationalConstant: -10000 }
        },
        nodes: {
            font: { size: 25 }
        }
    };

    network = new vis.Network(container, data, options);

    // 保存主机和交换机ID全局
    window.hostList = hostList;
    window.switchList = switchList;

    // 绑定点击事件显示节点信息
    network.on("click", function (params) {
        if (params.nodes.length > 0) {
            const nodeId = params.nodes[0];
            const node = data.nodes.get(nodeId);
            showNodeInfo(node, edgeList);
        } else {
            clearNodeInfo();
        }
    });
}

function showNodeInfo(node, edgeList) {
    const infoContainer = document.getElementById('nodeInfoContent');
    const detail = nodeDetailMap[node.id];

    const connectedEdges = edgeList.filter(edge => edge.from === node.id || edge.to === node.id);
    const connectedNodes = new Set();
    connectedEdges.forEach(edge => {
        connectedNodes.add(edge.from === node.id ? edge.to : edge.from);
    });

    let html = `<p><strong>节点ID：</strong> ${node.id}</p>`;
    html += `<p><strong>类型：</strong> ${node.id.startsWith('s') ? '交换机' : '主机'}</p>`;

    if (detail) {
        html += `<p><strong>IP地址：</strong> ${detail.ip || '-'}</p>`;
        html += `<p><strong>MAC地址：</strong> ${detail.mac || '-'}</p>`;
    }

    html += `<p><strong>连接节点：</strong></p><ul>`;
    connectedNodes.forEach(n => {
        html += `<li>${n}</li>`;
    });
    html += `</ul>`;

    infoContainer.innerHTML = html;
}

function clearNodeInfo() {
    document.getElementById('nodeInfoContent').innerHTML = '点击任意节点查看详情';
}

document.addEventListener("DOMContentLoaded", function () {
    // --- START: 自动上传和构建拓扑的逻辑 ---
    const pendingTopology = localStorage.getItem('pendingTopology');
    const pendingModel = localStorage.getItem('pendingModel');

    if (pendingTopology) {
        console.log("检测到待处理的拓扑，开始自动构建...");

        // 1. 清除 localStorage，防止刷新页面时重复构建
        localStorage.removeItem('pendingTopology');
        localStorage.removeItem('pendingModel');

        // 2. 将存储的拓扑字符串转换为一个File对象，以便复用上传逻辑
        const topoFile = new File([pendingTopology], "config.json", { type: "application/json" });

        // 3. 打开AI助手侧边栏，让用户看到过程
        const aiSidebar = document.getElementById('ai-assistant-sidebar');
        if (aiSidebar) {
            aiSidebar.classList.add('open');
        }
        // 4. 调用辅助函数，自动上传拓扑并初始化AI会话
        autoUploadAndInitAI(topoFile,pendingModel);

    } else {
        console.log("未检测到待处理的拓扑。");
    }
    // --- END: 自动上传和构建拓扑的逻辑 ---
    const loadP4Button = document.querySelector(".loadP4Code");
    const injectFlowTableButton = document.querySelector(".injectFlowTable");

    if (loadP4Button) {
        loadP4Button.addEventListener("click", loadP4Code);
    }
    if (injectFlowTableButton) {
        injectFlowTableButton.addEventListener("click", injectFlowTable);
    }
});

function loadP4Code() {
    fetch("/load_p4_code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
    })
        .then(response => response.json())
        .then(data => {
            document.getElementById("loadResult").innerText = data.message;
        })
        .catch(error => {
            console.error("Error loading P4 code:", error);
            document.getElementById("loadResult").innerText = "装载 P4 代码失败！";
        });
}

function injectFlowTable() {
    fetch("/inject_flow_table", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
    })
        .then(response => response.json())
        .then(data => {
            document.getElementById("injectResult").innerText = data.message;
        })
        .catch(error => {
            console.error("Error injecting flow table:", error);
            document.getElementById("injectResult").innerText = "注入流表失败！";
        });
}

document.getElementById('sendButton').addEventListener('click', function () {
    sendTraffic('/send_command', '单路径验证');
});

document.getElementById('sendVbpButton').addEventListener('click', function () {
    sendTraffic('/send_command_vbp', 'VBP 合法行为池验证');
});

function sendTraffic(endpoint, modeLabel) {
    const srcHost = document.getElementById('srcHost').value.trim();
    const dstHost = document.getElementById('dstHost').value.trim();
    const resultBox = document.getElementById('sendResult');

    if (!srcHost || !dstHost) {
        resultBox.style.color = 'red';
        resultBox.textContent = '请填写完整的两个主机 ID';
        return;
    }

    fetch(endpoint, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ src: srcHost, dst: dstHost })
    })
    .then(response => response.json())
    .then(data => {
        if (data.result) {
            resultBox.style.color = 'green';
            resultBox.textContent = `[${modeLabel}] 发送成功：` + data.result;
        } else if (data.error) {
            resultBox.style.color = 'red';
            resultBox.textContent = `[${modeLabel}] 发送失败：` + data.error;
            return;
        }

        // 等待文件生成完成（读取 res.json）
        setTimeout(() => {
            fetch('/get_res_json')
                .then(response => response.json())
                .then(pathData => {
                    if (pathData) {
                        // 如果返回了路径信息，则处理路径高亮
                        const jsonData = JSON.parse(pathData);
                        highlightPath(jsonData);
                        const expectedPath = Array.isArray(jsonData.expected_path) ? jsonData.expected_path : [];
                        const matchedBehaviorPath = Array.isArray(jsonData.matched_behavior_path) ? jsonData.matched_behavior_path : [];
                        const recoverPath = Array.isArray(jsonData.recover_path) ? jsonData.recover_path : [];
                        let pathText = expectedPath.length
                            ? `预期主路径：${expectedPath.map(id => 's' + id).join(' → ')}`
                            : '预期主路径：无';

                        if (jsonData.behavior_status) {
                            pathText += `\nVBP 判定：${jsonData.behavior_label || jsonData.behavior_status}`;
                            if (jsonData.behavior_status === 'backup') {
                                resultBox.style.color = '#f9a825';
                            } else if (jsonData.behavior_status === 'illegal') {
                                resultBox.style.color = '#c62828';
                            } else if (jsonData.behavior_status === 'primary') {
                                resultBox.style.color = '#2e7d32';
                            }
                        }
                        if (matchedBehaviorPath.length > 0) {
                            pathText += `\n命中路径：${matchedBehaviorPath.map(id => 's' + id).join(' → ')}`;
                        }
                        if (!jsonData.consistence && recoverPath.length > 0) {
                            pathText += `\n实际错误路径：${recoverPath.map(id => 's' + id).join(' → ')}`;
                        }
                        resultBox.innerText += '\n' + pathText;
                    }
                })
                .catch(error => {
                    resultBox.style.color = 'red';
                    resultBox.textContent = '读取路径数据失败：' + error.message;
                });
        }, 5000);  // 等待5秒后读取 res.json
    })
    .catch(error => {
        resultBox.style.color = 'red';
        resultBox.textContent = '发送请求出错：' + error.message;
    });
}

function highlightPath(data) {
    // 确保 paths 是数组，若不存在或无效则设为空数组
    const expectedPath = Array.isArray(data.expected_path) ? data.expected_path : [];
    const matchedBehaviorPath = Array.isArray(data.matched_behavior_path) ? data.matched_behavior_path : [];
    const recoverPath = Array.isArray(data.recover_path) ? data.recover_path : [];
    const consistence = data.consistence;
    const behaviorStatus = data.behavior_status;
    const edgeUpdates = [];

    if (behaviorStatus === 'primary' && matchedBehaviorPath.length > 1) {
        for (let i = 0; i < matchedBehaviorPath.length - 1; i++) {
            edgeUpdates.push({
                from: `s${matchedBehaviorPath[i]}`,
                to: `s${matchedBehaviorPath[i + 1]}`,
                color: { color: '#2e7d32' },
                width: 4
            });
        }
    } else if (behaviorStatus === 'backup' && matchedBehaviorPath.length > 1) {
        for (let i = 0; i < matchedBehaviorPath.length - 1; i++) {
            edgeUpdates.push({
                from: `s${matchedBehaviorPath[i]}`,
                to: `s${matchedBehaviorPath[i + 1]}`,
                color: { color: '#f9a825' },
                width: 4
            });
        }
    } else if (!consistence && recoverPath.length > 1) {
        for (let i = 0; i < recoverPath.length - 1; i++) {
            edgeUpdates.push({
                from: `s${recoverPath[i]}`,
                to: `s${recoverPath[i + 1]}`,
                color: { color: '#c62828' },
                width: 4
            });
        }
    } else if (expectedPath.length > 1) {
        for (let i = 0; i < expectedPath.length - 1; i++) {
            edgeUpdates.push({
                from: `s${expectedPath[i]}`,
                to: `s${expectedPath[i + 1]}`,
                color: { color: '#2e7d32' },
                width: 4
            });
        }
    }

    // 在 network 完全加载后访问 edges
    if (network && network.body && network.body.data && network.body.data.edges) {
        const allEdges = network.body.data.edges.get();

        allEdges.forEach(edge => {
            // 还原所有边为默认颜色
            network.body.data.edges.update({ id: edge.id, color: { color: '#848484' }, width: 1 });
        });

        edgeUpdates.forEach(update => {
            // 找到符合的边并更新颜色
            const matchedEdge = allEdges.find(e => 
                (e.from === update.from && e.to === update.to) || 
                (e.from === update.to && e.to === update.from)
            );
            if (matchedEdge) {
                network.body.data.edges.update({
                    id: matchedEdge.id,
                    color: update.color,
                    width: update.width
                });
            }
        });
    } else {
        console.error("Network body data edges are not available");
    }
}



document.getElementById("modifyButton").addEventListener("click", function () {
    const swid = document.getElementById("modSwid").value.trim();
    const dstHost = document.getElementById("modDstHost").value.trim();
    const dstSwid = document.getElementById("modDstSwid").value.trim();

    if (!swid || !dstHost || !dstSwid) {
        alert("请填写所有输入项！");
        return;
    }

    fetch("/modify_flow_table", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            swid: swid,
            dst_host: dstHost,
            dst_swid: dstSwid
        })
    })
    .then(response => response.json())
    .then(data => {
        const resultBox = document.getElementById("modifyResult");
        if (data.status === 'success') {
            resultBox.style.color = 'green';
            resultBox.innerText = data.msg;
        } else {
            resultBox.style.color = 'red';
            resultBox.innerText = `修改失败：${data.msg}`;
        }
    })
    .catch(err => {
        console.error("请求失败:", err);
        document.getElementById("modifyResult").innerText = "请求失败，请检查服务器连接。";
    });
});

// 监听输入框失去焦点或内容变化时更新目标交换机下拉框
document.getElementById("modSwid").addEventListener("blur", updateDstSwitchOptions);
// 或者也可以使用 input 实时更新
// document.getElementById("modSwid").addEventListener("input", updateDstSwitchOptions);

function updateDstSwitchOptions() {
    const modSwid = document.getElementById("modSwid").value.trim();
    const dstSelect = document.getElementById("modDstSwid");

    // 清空旧选项
    dstSelect.innerHTML = "";

    if (!modSwid || !modSwid.startsWith('s')) {
        dstSelect.innerHTML = '<option value="">请输入有效交换机ID</option>';
        return;
    }

    const neighborSet = new Set();
    currentEdges.forEach(edge => {
        if (edge.from === modSwid && edge.to.startsWith('s')) {
            neighborSet.add(edge.to);
        }
        if (edge.to === modSwid && edge.from.startsWith('s')) {
            neighborSet.add(edge.from);
        }
    });

    if (neighborSet.size === 0) {
        dstSelect.innerHTML = '<option value="">无相邻交换机</option>';
        return;
    }

    dstSelect.innerHTML = '<option value="">请选择相邻交换机</option>';
    neighborSet.forEach(sw => {
        const option = document.createElement("option");
        option.value = sw;
        option.textContent = sw;
        dstSelect.appendChild(option);
    });
}

// 【新增】一个辅助函数，用于在新页面自动上传拓扑给AI
async function autoUploadAndInitAI(file, modelName) {
    const uploadInitialScreen = document.getElementById('upload-initial-screen');
    const uploadBtn = document.getElementById('upload-btn');
    const chatInputArea = document.getElementById('chat-input-area');
    const displayError = (message) => { // 需要一个本地的错误显示函数
        const uploadError = document.getElementById('upload-error');
        if (uploadError) {
            uploadError.textContent = message;
            uploadError.style.display = 'block';
        }
    };
    
    if (!uploadInitialScreen || !uploadBtn || !chatInputArea) return;

    uploadInitialScreen.innerHTML = '<p><i class="fas fa-spinner fa-spin"></i> 正在恢复AI对话状态...</p>';

    const formData = new FormData();
    formData.append('file', file);

    formData.append('model', modelName);
    try {
        const response = await fetch('/upload_topology', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();

        if (!response.ok) throw new Error(data.error || 'AI会话恢复失败');

        // 会话恢复成功！
        window.currentSessionId = data.session_id; // 将session_id存到全局，以便main.js能用
        uploadInitialScreen.style.display = 'none';
        chatInputArea.style.display = 'block';

        // 手动调用在 main.js 中定义的 appendBotMessage
        if (typeof window.appendBotMessage === 'function') {
            window.appendBotMessage(data, true);
            window.toggleLoadingState(false);
        }

    } catch (error) {
        displayError(error.message);
    }
}
