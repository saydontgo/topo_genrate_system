// 获取FatTree4和FatTree6的点击事件
// const fatTree4 = document.querySelector('.fatTree4');
const fatTree6 = document.querySelector('.generateFattree6');

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
                        drawNetwork(edgesData);
                    })
                    .catch(err => console.error('获取节点详细信息失败:', err));
            })
            .catch(err => console.error('获取拓扑数据失败:', err));
    })
    .catch(error => console.error('Error:', error));
}


function drawNetwork(edgeList) {
    const nodesSet = new Set();
    edgeList.forEach(edge => {
        nodesSet.add(edge.from);
        nodesSet.add(edge.to);
    });

    const nodes = Array.from(nodesSet).map((id) => {
        return {
            id: id,
            label: id,
            shape: id.startsWith('s') ? 'box' : 'ellipse',
            color: id.startsWith('s') ? '#87CEEB' : '#FFD700'
        };
    });

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
    const network = new vis.Network(container, data, options);

    // 绑定点击事件
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
    })
    .catch(error => {
        resultBox.style.color = 'red';
        resultBox.textContent = '发送请求出错：' + error.message;
    });
});
