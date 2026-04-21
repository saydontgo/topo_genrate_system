# 迁移映射 V1

## 重点热点文件

| 当前文件 | 目标文件 | 当前问题 | 迁移优先级 |
| --- | --- | --- | --- |
| `app.py` | `routes/*` + `services/*` + 薄 `app.py` | 路由、业务、状态、下载、AI 设置全部混在一起 | 高 |
| `LLM.py` | `services/ai_service.py` | 配置、会话、调用、降级逻辑耦合 | 高 |
| `static/main.js` | `common/shell.js` + `common/chat_assistant.js` + `pages/home.js` | AI、导航、上传、构建按钮全堆在一起 | 高 |
| `static/demo_topo.js` | `common/topology_view.js` + `pages/uploaded_workspace.js` | 页面工作区逻辑过长 | 高 |
| `topo/dynamic_demo.py` | `runtime/uploaded/dynamic_topology.py` | 网络定义、规则生成、脚本执行、发送逻辑耦合 | 高 |
| `topo/demo/network.py` | `runtime/builtins/demo_topology.py` | 预制 demo 和通用行为边界不清 | 中 |
| `topo/FatTree6/FatTree6.py` | `runtime/builtins/fattree6_topology.py` | 大型预制拓扑类过重 | 中 |
| `topo/topo.py` | `runtime/common/topology_graph.py` | 文件名语义过弱 | 中 |
| `static/style.css` | `css/base.css` + `css/layout.css` + `css/components.css` + `css/pages/*` | 样式过度集中 | 中 |

## 推荐迁移顺序

### Phase 1

先拆后端入口：

1. `topology_state.py`
2. `topology_service.py`
3. `routes/upload_api.py`
4. `routes/topology_api.py`

### Phase 2

再拆前端：

1. `common/chat_assistant.js`
2. `common/topology_view.js`
3. `pages/uploaded_workspace.js`

### Phase 3

最后拆运行时：

1. `dynamic_topology.py`
2. `demo_topology.py`
3. `fattree6_topology.py`

## 本草案的用途

这不是最终迁移结果，而是第一版结构草案。

你确认方向后，下一步就可以按这个映射开始真实迁移，而不是继续在大文件里追加逻辑。