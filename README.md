# P4Prime 拓扑生成与验证系统

这是项目当前唯一保留的主 README，用来说明真实运行结构、页面入口和新增能力。此前散落在 `application/`、`topo/`、`rewrite_v1/` 里的局部 README 已移除，避免文档与代码继续分叉。

## 1. 项目在做什么

这是一个面向 SDN / P4 实验场景的“控制平面预期路径”和“数据平面实际行为”联合验证系统。它把几类能力放在了一条可演示的工作流里：

- 用 Flask 提供页面、接口和上传入口。
- 用 Mininet + P4Utils 启动交换机与主机实验拓扑。
- 用 `switch.p4` 在数据平面携带路径验证相关字段。
- 用单路径校验、VBP 合法行为池和 flow-aware semantic runtime 三层机制判断一条流量是否仍在“允许的行为范围”内。
- 用前端工作台把拓扑、路径、节点详情、策略编辑和验证结果可视化出来。

如果只看一句话，这个系统做的是：

> 给定一个网络拓扑和若干业务流意图，系统自动生成可运行的 P4/Mininet 验证环境，并在发送流量后告诉你这条流到底是命中了主路径、走了备份路径、还是已经偏离到非法状态。

## 2. 当前运行结构

当前代码已经不是早期“所有逻辑都堆在 `app.py` 和单个前端脚本”的形态，而是按“入口、路由、服务、前端页面、运行时”分层组织。

```text
topo_genrate_system/
├── README.md                     # 当前唯一主文档
├── LICENSE
├── config.json                   # 演示上传用的示例拓扑
└── application/
    ├── app.py                    # Flask app factory 与 blueprint 注册入口
    ├── LLM.py                    # AI 对话与分析能力
    ├── llm_config.py             # AI 配置读写
    ├── error.py                  # 异常定义
    ├── routes/                   # Flask 蓝图层
    ├── services/                 # 业务服务层
    ├── templates/                # Jinja 页面模板
    ├── static/                   # CSS / JS 静态资源
    ├── topo/                     # 网络运行时与验证核心
    ├── p4src/                    # P4 程序
    ├── generated/                # AI 生成物与上传解析结果
    ├── instance/                 # 本地配置与敏感环境配置
    ├── topology.json             # 当前运行拓扑元数据
    ├── res.json                  # 最近一次发送结果
    ├── pcap/                     # 抓包结果
    └── rewrite_v1/               # 重构草案目录，不参与当前运行
```

### 2.1 入口层

- `application/app.py`
  现在只保留 Flask 创建与 blueprint 注册，是当前后端的真正入口。

- `application/LLM.py`
  负责 AI 侧的对话能力、会话历史和上传后初始意图分析。

- `application/llm_config.py`
  管理模型地址、密钥等本地配置。

### 2.2 路由层

`application/routes/` 是后端 HTTP 边界，负责把页面和运行时操作分开：

- `pages.py`
  页面渲染入口，负责首页、拓扑页、FatTree6、上传拓扑工作台和设置页。

- `topology_api.py`
  核心运行接口，负责：
  - 读取拓扑节点和边
  - 选择并构建拓扑
  - 装载 P4
  - 注入流表
  - 发送普通流量与 VBP 流量
  - 获取 `res.json`
  - 获取 verification profile
  - 切换某个 flow 的预期主路径
  - 更新某个 flow 的 VBP 候选路径集合
  - 更新某个 flow 的 semantic policy

- `upload_api.py`
  负责上传 JSON 拓扑、下载生成文件等与“用户输入拓扑”直接相关的接口。

- `settings_api.py`
  负责页面样式设置和 AI 配置相关接口。

### 2.3 服务层

`application/services/` 负责把上传拓扑、当前运行态和配置归一化处理掉：

- `topology_service.py`
  负责拓扑 JSON 校验、上传配置持久化、意图归一化和运行前准备。

- `topology_state.py`
  负责当前激活拓扑对象的状态管理，包括恢复上传拓扑实例、切换当前运行拓扑等。

### 2.4 前端模板层

`application/templates/` 现在也做了共享化：

- `base.html`
  所有页面共享的基础壳层。

- `includes/ai_sidebar.html`
  共享 AI 侧边栏，不再每个页面各自复制一套聊天 UI。

- `home.html`
  首页，承担 AI 入口、系统概览和上传起点。

- `topology.html`
  拓扑总入口页。

- `demo.html`
  上传拓扑工作台，也是新增功能最集中的页面。

- `fattree6.html`
  预制 FatTree6 演示页面。

- `settings.html`
  样式和 AI 配置页面。

### 2.5 前端脚本层

前端已经拆成“共享脚本 + 页面脚本 + 启动入口”三层，不再是单个大文件：

#### `application/static/js/common/`

- `shell.js`
  负责全局导航、壳层交互、背景动画和 AI 面板开关。

- `ai_assistant.js`
  负责 AI 上传、对话消息和用户与助手的交互流程。

- `topology_view.js`
  负责 vis-network 拓扑绘制、节点详情显示、路径高亮与 VBP 路径可视化。

- `workspace_runtime.js`
  负责上传拓扑工作台与 FatTree 工作台的公共运行时逻辑，包括构建、装载、注入、发送、读取 profile、编辑 flow 等。

#### `application/static/js/pages/`

- `uploaded_workspace.js`
  只负责上传拓扑工作台页面自己的交互绑定。

- `fattree_workspace.js`
  负责 FatTree6 页面自己的交互绑定。

- `settings_page.js`
  负责设置页表单与保存逻辑。

#### `application/static/js/entrypoints/`

- `main_bootstrap.js`
  首页启动入口。

- `uploaded_workspace_bootstrap.js`
  上传拓扑工作台启动入口。

- `fattree_workspace_bootstrap.js`
  FatTree6 工作台启动入口。

- `settings_page_bootstrap.js`
  设置页启动入口。

### 2.6 前端样式层

`application/static/css/` 按职责拆分：

- `tokens.css`
  颜色、字号、阴影、圆角等设计变量。

- `base.css`
  基础元素和通用排版。

- `layout.css`
  页面骨架和布局。

- `components.css`
  按钮、卡片、表单等可复用组件。

- `pages.css`
  页面级样式和工作台区块样式。

- `responsive.css`
  响应式规则。

### 2.7 运行时与网络验证层

`application/topo/` 是项目里最核心的网络实验目录：

- `demo/`
  内置小型 demo 拓扑，用于基线演示和兜底回退。

- `FatTree6/`
  预制的大拓扑演示环境。

- `user_topology/`
  上传拓扑的独立运行目录。当前上传网络的脚本、规则和语义状态都会落在这里。

- `dynamic_demo.py`
  上传拓扑的动态实例化入口。读取上传 JSON 和 `generated/intent.json`，生成运行时网络、规则、行为池和语义策略。

- `topo.py`
  把运行中的拓扑元数据转成图结构，并为路径验证提供底层图能力。

- `send.py`
  发送验证流量。

- `receive.py`
  单路径验证接收端。

- `receive_vbp.py`
  VBP 验证接收端。

- `behavior_pool.py`
  合法行为池分类逻辑。

- `semantic_runtime.py`
  flow-aware semantic runtime，负责生成 semantic policy、跟踪状态和输出违规分类。

- `runtime_paths.py` 与 `runtime_files.py`
  收口运行时路径约定、文件写入和落盘逻辑，避免路径散落在各模块。

### 2.8 运行时数据与生成物

- `application/generated/intent.json`
  AI 从 `intent_description` 提取出来的结构化业务意图。

- `application/topology.json`
  当前运行拓扑元数据，前端节点详情和部分验证逻辑会读取它。

- `application/res.json`
  最近一次发送后的结果快照，前端用它来高亮路径和显示判定。

- `application/topo/user_topology/runtime/`
  上传拓扑的专属运行时产物，通常包含：
  - `rules.json`
  - `behavior_pool.json`
  - `topology.json`
  - `semantic_policy.json`
  - `semantic_state.json`
  - `semantic_history.json`

- `application/rewrite_v1/`
  这里只是重构草案，不是当前线上运行链路，不要把里面的目录当成真实入口。

## 3. 页面入口与使用方式

系统当前最重要的几个页面：

- `/`
  首页。看整体说明、打开 AI 侧栏、上传拓扑、生成意图。

- `/topology`
  拓扑总入口页。

- `/topology/fattree6`
  预制 FatTree6 工作台。

- `/topology/your_topology`
  上传拓扑工作台，是动态拓扑、VBP、semantic runtime 和 flow 级策略编辑的主战场。

- `/settings`
  页面样式和 AI 配置。

## 4. 新增功能具体是干什么的

这一部分是这次最关键的说明。下面不是简单罗列“新增了什么按钮”，而是说明这些能力在系统里分别承担什么职责。

### 4.1 蓝图化后端结构

新增点：后端从单体 `app.py` 拆成 `routes/ + services/`。

它解决的问题：

- 页面路由、拓扑接口、上传接口和设置接口终于有清晰边界。
- 上传拓扑校验和当前运行态管理从页面逻辑里抽出来，后续改动不需要碰 Flask 主入口。
- 新接口例如“切换主路径”“更新 VBP 路径集合”“更新 semantic policy”可以在明确边界下继续扩展。

### 4.2 前端模块化工作台

新增点：前端从“大脚本堆所有逻辑”改成共享模块、页面脚本和 bootstrap 入口三层。

它解决的问题：

- AI 侧栏、拓扑渲染、工作台运行时逻辑不再互相缠绕。
- 上传拓扑工作台和 FatTree6 工作台可以共享一套运行时逻辑，但保留各自页面入口。
- 后续继续加功能时，可以明确知道应该改 `topology_view.js`、`workspace_runtime.js` 还是某个页面脚本。

### 4.3 动态上传拓扑运行时

新增点：用户上传的 JSON 不再只是“预览一下”，而是会生成真正的运行时拓扑。

它具体做什么：

- 根据上传的 `switches`、`hosts`、`links` 创建当前网络。
- 根据 AI 或用户提供的业务意图生成每个 flow 的运行策略。
- 生成 `rules.json`、`behavior_pool.json`、`semantic_policy.json` 等运行文件。
- 让“我的拓扑”页面可以像内置 demo 一样直接构建、装载 P4、注入流表并发送流量。

### 4.4 AI 意图解析

新增点：首页 AI 助手会读取上传拓扑里的 `intent_description`，输出结构化 `intent.json`。

它具体做什么：

- 把自然语言业务描述转成 flow 级约束。
- 给每条流补出源宿主机、目的宿主机、优先级、must_pass、avoid、备份等级等可执行信息。
- 让后续的路径生成、VBP 行为池和 semantic policy 都有统一输入来源。

### 4.5 单路径一致性验证

这是原有核心机制，但现在仍然是基础层。

它具体做什么：

- 为一条流确定唯一预期路径。
- 在数据平面传递路径验证相关信息。
- 收包后判断实际路径是否与预期一致。
- 一旦不一致，输出恢复出来的实际路径，帮助定位问题。

### 4.6 VBP 合法行为池验证

新增强化点：系统不再只接受“唯一一条正确路径”，而是允许“一组合法路径”。

它具体做什么：

- 给一条流保留主路径和若干备份路径。
- 发送后区分三种结果：命中主路径、命中备份路径、命中非法路径。
- 更贴近真实网络里链路波动、绕行和主备切换的行为。

### 4.7 Flow-aware semantic runtime

这是当前最重要的新能力之一，不只是看“路径对不对”，而是看“这条流的行为是否仍满足业务语义约束”。

它具体做什么：

- 为每条 flow 生成 `semantic_policy`。
- 跟踪 `packet_count`、`degraded_packets`、`state_change_count` 等运行态指标。
- 维护 `semantic_state` 和 `semantic_history`。
- 在结果里告诉你当前 flow 是正常、降级还是违规。

这层能力的意义是：

- 即使包没有走到完全错误的路径，也可能因为长期处于备份状态、频繁抖动或超过恢复预算而被判为违规。

### 4.8 Flow 级预期主路径切换

新增点：上传拓扑工作台里可以针对某一条 flow 切换主路径，而不是只能改底层流表。

它具体做什么：

- 把当前 flow 选中的候选路径写回 `preferred_path`。
- 重新生成该 flow 的运行规则和合法行为池。
- 把新路径重新下发到交换机。

这让演示从“手改底层规则”变成“直接切业务意图层的主路径”。

### 4.9 Flow 级 semantic policy 编辑

新增点：现在可以直接按 flow 编辑语义约束。

它具体做什么：

- 调整 `max_packets`。
- 调整 `max_hops`。
- 调整 `max_degraded_packets`。
- 调整 `max_state_changes`。
- 修改 `invariants` 和 `allowed_transitions`。

这意味着你不仅能演示“系统自动生成了什么策略”，还能演示“如果业务侧提高或降低容忍度，验证结果会怎么变化”。

### 4.10 VBP 候选路径增删管理

这是最近补上的一项非常实用的能力。

它具体做什么：

- 直接在页面里勾选当前 flow 要保留的候选路径。
- 保存后后端会更新 `enabled_paths`。
- 系统会按新的路径集合重建 behavior pool 和 semantic policy。
- 第一条保留路径作为主路径，其余路径作为备份路径。

它解决的问题：

- 演示时不用再去手改底层 JSON。
- 现场可以快速展示“保留 2 条备份”和“只保留 1 条主路径”对判定结果的影响。

### 4.11 完整 VBP 路径高亮

新增点：前端不再只高亮一条命中路径，而是会把整组合法路径画出来。

它具体做什么：

- 主路径用绿色表示。
- 备份路径用黄色表示。
- 实际命中的路径会再加粗强调。
- 节点详情会尽量展示 IP、MAC、接入交换机和设备信息。

这让用户在界面上能直接看懂“合法集合”和“这次具体走了哪一条”。

### 4.12 Runtime verification 面板

新增点：上传拓扑工作台会展示 semantic policy、semantic state 和 semantic history。

它具体做什么：

- 告诉你当前 flow 的策略长什么样。
- 告诉你最近一次发送后 flow 处在哪个状态。
- 告诉你最近几次状态变化历史和违规类型。

这部分是“从一次性判定”走向“跨包、跨次发送的持续验证”的关键可视化入口。

## 5. 典型运行链路

如果你想理解整个系统怎么串起来，可以按下面这条链看：

1. 在首页上传拓扑 JSON，或者直接使用根目录里的 `config.json` 作为示例。
2. AI 助手读取 `intent_description`，生成 `application/generated/intent.json`。
3. 进入“我的拓扑”页面。
4. 选择构建当前拓扑，后端用 `dynamic_demo.py` 生成运行时网络和相关 JSON。
5. 装载 `application/p4src/switch.p4`。
6. 注入流表。
7. 发送普通流量或 VBP 流量。
8. 前端读取 `res.json`、`semantic_policy.json`、`semantic_state.json` 和 `semantic_history.json`，把路径、判定与状态演化展示出来。
9. 如有需要，可以进一步切换主路径、增删 VBP 候选路径或直接编辑 semantic policy，再重新发送流量观察变化。

## 6. 启动方式

### 6.1 环境要求

建议运行环境：

- Ubuntu 22.04 或兼容 Linux 环境
- Mininet
- P4 / BMv2
- P4Utils
- Python 3

### 6.2 启动步骤

进入 `application/` 目录后运行：

```bash
python3 app.py
```

浏览器访问：

```text
http://localhost:5000
```

## 7. 推荐演示顺序

如果你需要向别人完整展示系统，建议按这条顺序讲：

1. 首页介绍系统目标，并演示 AI 解析上传拓扑的意图。
2. 进入“我的拓扑”，构建当前上传网络。
3. 装载 P4 并注入流表。
4. 发送一次正常流量，讲单路径和 VBP 的区别。
5. 演示 semantic runtime 面板，说明为什么“走备份路径”不一定马上算错误，但可能进入降级状态。
6. 切换某条 flow 的预期主路径，展示系统如何按业务语义重建策略。
7. 勾选或取消某些 VBP 候选路径，展示合法行为集合变化。
8. 编辑某条 flow 的 semantic policy，再发送一次流量，展示判定阈值如何影响结果。

## 8. 补充说明

- `application/rewrite_v1/` 只是后续重构草案目录，不参与当前运行链路。
- `application/topology.json` 和 `application/res.json` 仍然是当前工具链的兼容输出文件，前端很多展示会直接读取它们。
- 如果上传拓扑还没构建成功，“我的拓扑”页面会在部分场景下回退到内置 demo 或预览数据，这是为了保证页面可访问，不代表运行时已经真正启动。
