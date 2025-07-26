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
    sendTopology(6);
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
    const srcHost = document.getElementById('srcHost').value.trim();
    const dstHost = document.getElementById('dstHost').value.trim();
    const resultBox = document.getElementById('sendResult');

    if (!srcHost || !dstHost) {
        resultBox.style.color = 'red';
        resultBox.textContent = '请填写完整的两个主机 ID';
        return;
    }

    fetch('/send_command', {
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
            resultBox.textContent = '发送成功：' + data.result;
        } else if (data.error) {
            resultBox.style.color = 'red';
            resultBox.textContent = '发送失败：' + data.error;
        }

        // 等待文件生成完成（读取 res.json）
        setTimeout(() => {
            fetch('/get_res_json')
                .then(response => response.json())
                .then(pathData => {
                    if (pathData) {
                        // 如果返回了路径信息，则处理路径高亮
                        jsonData = JSON.parse(pathData);
                        highlightPath(jsonData);
                        let pathText = `预期路径：${jsonData.expected_path.map(id => 's' + id).join(' → ')}`;
                        if (!jsonData.consistence && jsonData.recover_path) {
                            pathText += `\n实际错误路径：${jsonData.recover_path.map(id => 's' + id).join(' → ')}`;
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
});

function highlightPath(data) {
    // 确保 paths 是数组，若不存在或无效则设为空数组
    const expectedPath = Array.isArray(data.expected_path) ? data.expected_path : [];
    const recoverPath = Array.isArray(data.recover_path) ? data.recover_path : [];
    const consistence = data.consistence;
    const edgeUpdates = [];

    // 构造 expected_path 的边（绿色）
    if (expectedPath.length > 0) {
        for (let i = 0; i < expectedPath.length - 1; i++) {
            edgeUpdates.push({
                from: `s${expectedPath[i]}`,
                to: `s${expectedPath[i + 1]}`,
                color: { color: 'green' },
                width: 4
            });
        }
    }

    // 如果路径不一致，构造 recover_path 的边（红色）
    if (!consistence && recoverPath.length > 1) {
        for (let i = 0; i < recoverPath.length - 1; i++) {
            edgeUpdates.push({
                from: `s${recoverPath[i]}`,
                to: `s${recoverPath[i + 1]}`,
                color: { color: 'red' },
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

// ========== AI 助手交互功能 (V2 - 文件上传 & Markdown) ==========
document.addEventListener('DOMContentLoaded', function() {
    // --- 获取DOM元素 ---
    const aiSidebar = document.getElementById('ai-assistant-sidebar');
    if (!aiSidebar) return; // 如果页面没有助手，直接退出

    const chatWindow = document.getElementById('chat-window');
    const userInput = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');
    const uploadInitialScreen = document.getElementById('upload-initial-screen');
    const uploadBtn = document.getElementById('upload-btn');
    const fileInput = document.getElementById('topology-file-input');
    const uploadError = document.getElementById('upload-error');
    const chatInputArea = document.getElementById('chat-input-area');
    const suggestedQuestionsContainer = document.getElementById('suggested-questions');
    
    // 格式详情提示
    const showFormatDetailsLink = document.getElementById('show-format-details');
    const formatDetails = document.getElementById('format-details');

    // --- 状态变量 ---
    let currentSessionId = null;
    let isWaitingForResponse = false;
    // 1. 获取控制滑动的相关元素
    const aiSwitch = document.getElementById('ai-assistant-switch');
    const closeBtn = document.getElementById('close-ai-sidebar');

    // 2. 确保这些控制元素存在，再绑定事件
    if (aiSwitch && closeBtn && aiSidebar) {
        
        // 点击页面右上角的开关按钮
        aiSwitch.addEventListener('click', (event) => {
            // 阻止事件冒泡到document，以防立即触发下面的外部点击关闭逻辑
            event.stopPropagation(); 
            // 为侧边栏添加 .open 类，CSS会根据这个类来执行滑入动画
            aiSidebar.classList.add('open');
        });

        // 点击侧边栏内部的关闭按钮 (X)
        closeBtn.addEventListener('click', () => {
            // 移除 .open 类，CSS会执行滑出动画
            aiSidebar.classList.remove('open');
        });

        // 点击侧边栏外部的任何地方 (实现点击空白处关闭)
        document.addEventListener('click', (event) => {
            // 检查侧边栏是否是打开状态，并且确认点击的不是开关按钮本身
            if (aiSidebar.classList.contains('open') && !aiSwitch.contains(event.target)) {
                 // 确认点击的目标不是侧边栏或其内部的任何元素
                if (!aiSidebar.contains(event.target)) {
                    aiSidebar.classList.remove('open');
                }
            }
        });
    }

    // --- 工具函数 ---
    const toggleLoadingState = (isLoading) => {
        isWaitingForResponse = isLoading;
        userInput.disabled = isLoading;
        sendBtn.disabled = isLoading;
        if (isLoading) {
            sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        } else {
            sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i>';
        }
    };
    
    const displayError = (message) => {
        uploadError.textContent = message;
        uploadError.style.display = 'block';
    };

    // --- 核心功能 ---

    // 1. 文件上传逻辑
    uploadBtn.addEventListener('click', () => fileInput.click());

    fileInput.addEventListener('change', async (event) => {
        const file = event.target.files[0];
        if (!file) return;

        uploadError.style.display = 'none';
        uploadBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 上传并验证中...';
        uploadBtn.disabled = true;

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('/upload_topology', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                // 显示后端返回的详细错误信息
                let errorMsg = data.error || `服务器错误: ${response.status}`;
                if (data.template) {
                    errorMsg += `\n期望的格式类似: ${data.template}`;
                }
                throw new Error(errorMsg);
            }
            
            // 上传成功！
            currentSessionId = data.session_id;
            uploadInitialScreen.style.display = 'none'; // 隐藏上传界面
            chatInputArea.style.display = 'block';     // 显示输入框

            // 显示AI的首次分析
            appendBotMessage(data.initial_response);
            toggleLoadingState(false);

        } catch (error) {
            displayError(error.message);
        } finally {
            uploadBtn.innerHTML = '<i class="fas fa-upload"></i> 点击上传文件';
            uploadBtn.disabled = false;
            fileInput.value = ''; // 清空文件选择，以便下次上传
        }
    });

    // 2. 发送消息逻辑
    const sendMessage = async () => {
        const messageText = userInput.value.trim();
        if (messageText === '' || isWaitingForResponse) return;

        toggleLoadingState(true);
        appendUserMessage(messageText);
        userInput.value = '';
        suggestedQuestionsContainer.innerHTML = ''; // 清空旧的推荐问题

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: messageText })
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || '请求失败');

            appendBotMessage(data);

        } catch (error) {
            const errorData = { analysis: `抱歉，请求出错：${error.message}`, files: [], questions: [] };
            appendBotMessage(errorData);
        } finally {
            toggleLoadingState(false);
        }
    };

    // 3. 渲染消息到UI
    const appendUserMessage = (text) => {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'chat-message user';
        messageDiv.textContent = text;
        chatWindow.appendChild(messageDiv);
        chatWindow.scrollTop = chatWindow.scrollHeight;
    };
    
    const appendBotMessage = (data) => {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'chat-message bot';
        
        let htmlContent = '';
        
        // 渲染Markdown分析
        if (data.analysis) {
            htmlContent += `<div class="message-content">${marked.parse(data.analysis)}</div>`;
        }

        // 创建可下载的文件链接
        if (data.files && data.files.length > 0) {
            htmlContent += '<div class="download-section">';
            data.files.forEach(file => {
                if (file.content) {
                    const blob = new Blob([file.content], { type: 'text/plain' });
                    const url = URL.createObjectURL(blob);
                    htmlContent += `<a href="${url}" download="${file.filename}" class="download-button"><i class="fas fa-download"></i> 下载 ${file.filename}</a> `;
                }
            });
            htmlContent += '</div>';
        }
        
        messageDiv.innerHTML = htmlContent;
        chatWindow.appendChild(messageDiv);

        // 渲染"猜你想问"
        suggestedQuestionsContainer.innerHTML = '';
        if (data.questions && data.questions.length > 0) {
            data.questions.forEach(q => {
                if (!q) return;
                const btn = document.createElement('button');
                btn.className = 'suggested-question-btn';
                btn.textContent = q;
                
                // 【核心修正】为按钮的点击事件添加 event.stopPropagation()
                btn.onclick = (event) => {
                    // 阻止这个点击事件继续冒泡到 document
                    event.stopPropagation(); 
                    
                    // 执行原有的功能
                    userInput.value = q;
                    sendMessage();
                };
                
                suggestedQuestionsContainer.appendChild(btn);
            });
        }
        
        chatWindow.scrollTop = chatWindow.scrollHeight;
    };
    
    // --- 绑定事件 ---
    sendBtn.addEventListener('click', sendMessage);
    userInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });

    showFormatDetailsLink.addEventListener('click', (e) => {
        e.preventDefault();
        formatDetails.style.display = formatDetails.style.display === 'none' ? 'block' : 'none';
    });

    // (这里可以保留打开/关闭侧边栏的逻辑)
    // ...
});