# P4Prime 项目说明

## 项目简介
本项目是一个面向 SDN 场景的数据平面与控制平面一致性验证系统。项目的核心目标是：

- 对控制平面给出的预期转发路径进行编码与验证
- 在数据平面发生偏离时检测不一致行为
- 在发现异常后恢复实际转发路径，辅助定位故障交换机
- 通过 Web 可视化页面展示拓扑、流量转发结果与异常路径

项目整体采用 `Flask + P4 + Mininet + P4Utils` 的方式实现，其中：

- Flask 负责本地 Web 应用和接口组织
- P4 程序负责在交换机侧携带和处理路径验证信息
- Mininet/P4Utils 负责构建实验拓扑与加载交换机规则
- 前端页面负责拓扑展示、路径高亮和交互演示

## 核心机制
项目当前围绕两类验证机制展开：

- 单路径验证：
  对于一个给定的源宿主机对，控制平面预先给出一条预期路径。系统为路径中的交换机分配质数，并将路径编码为质数乘积；接收端根据数据包中的编码结果判断当前转发是否与预期一致。
- VBP 合法行为池验证：
  在单路径验证基础上，进一步将“唯一合法路径”扩展为“一组合法路径”。这样系统不仅可以识别错误路径，也可以识别备份路径、绕行路径等仍然属于合法范围内的行为。

## 目录结构与功能

### 根目录
- `README.md`
  项目总说明文档。
- `application/`
  项目的主要代码目录，包含后端、前端页面、拓扑定义、P4 程序和规则文件。

### 后端与页面
- `application/app.py`
  Flask 应用主入口。
  主要负责：
  - 页面路由
  - 拓扑初始化与构建接口
  - 流量发送接口
  - 流表修改接口
  - 拓扑数据读取接口
  - AI 分析接口
  - VBP 演示接口

- `application/templates/`
  前端 HTML 页面模板目录。
  主要页面包括：
  - `home.html`：项目主页与功能入口说明
  - `fattree6.html`：FatTree6 拓扑演示页面
  - `demo.html`：Demo 拓扑演示页面，支持普通验证与 VBP 验证
  - `settings.html`：拓扑样式设置页面
  - `topology.html`：拓扑入口页

- `application/static/`
  前端静态资源目录。
  主要包括：
  - `main.js`：主页与 AI 助手相关交互逻辑
  - `topo.js`：FatTree6 页面拓扑展示与交互逻辑
  - `demo_topo.js`：Demo 页面拓扑展示、路径高亮、普通发送与 VBP 发送逻辑
  - `settings.js`：拓扑样式设置逻辑
  - `loading.js`：页面初始化时的拓扑启动逻辑
  - `style.css`：页面样式文件

### AI 分析模块
- `application/LLM.py`
  AI 调用与会话管理模块。
  主要负责：
  - 与大模型接口通信
  - 管理对话历史
  - 返回结构化分析结果
  - 为前端提供网络分析、问答和结构化输出支持

### 拓扑与验证逻辑
- `application/topo/`
  核心实验逻辑目录。

- `application/topo/topo.py`
  拓扑图结构与质数分配模块。
  主要负责：
  - 读取 `topology.json`
  - 建立图结构
  - 为交换机分配质数
  - 提供邻居查询和路径遍历能力

- `application/topo/send.py`
  主机侧发送数据包脚本。
  支持普通包、质数标记包等发送方式。

- `application/topo/receive.py`
  原始单路径一致性验证脚本。
  主要负责：
  - 接收数据包
  - 读取规则中的预期路径
  - 计算预期路径质数乘积
  - 对比包中携带的路径编码
  - 在异常时恢复实际路径并写入 `res.json`

- `application/topo/behavior_pool.py`
  VBP 合法行为池模块。
  主要负责：
  - 读取合法行为池配置
  - 为多条合法路径建立行为集合
  - 根据接收端观测到的质数乘积判断当前行为属于主路径、备份路径还是非法路径

- `application/topo/receive_vbp.py`
  VBP 验证脚本。
  在保留原有单路径验证逻辑的基础上，新增“合法行为集合”判定能力，用于演示：
  - 主路径合法
  - 备份路径合法
  - 非法路径告警

- `application/topo/tools.py`
  数据包字段和工具函数定义文件，供发送与接收逻辑使用。

- `application/topo/helper.py`
  一些辅助函数，例如 IP 处理工具。

### Demo 拓扑
- `application/topo/demo/network.py`
  Demo 拓扑定义与操作逻辑。
  主要负责：
  - 构建 4 台交换机、2 台主机的简单实验拓扑
  - 加载 P4 程序
  - 注入流表
  - 执行普通一致性验证发送
  - 执行 VBP 模式发送

- `application/topo/demo/rules/rules.json`
  Demo 场景下的单路径规则文件。

- `application/topo/demo/rules/behavior_pool.json`
  Demo 场景下的合法行为池文件。
  用于定义一组允许的主路径与备份路径。

### FatTree6 拓扑
- `application/topo/FatTree6/FatTree6.py`
  FatTree6 拓扑定义与运行逻辑。

- `application/topo/FatTree6/rules.json`
  FatTree6 拓扑下的路径规则文件。

### P4 程序与实验数据
- `application/p4src/switch.p4`
  项目的 P4 交换机程序。
  负责在数据平面中处理路径相关信息。

- `application/pcap/`
  实验抓包结果目录，用于保留各交换机端口上的抓包文件，辅助实验分析与结果展示。

### 其他文件
- `application/error.py`
  自定义异常定义。

- `application/topo/style_settings.json`
  前端拓扑节点样式配置文件。

- `application/instance/blog.db`
  Flask 运行产生的本地数据库文件。

## 系统功能概览
当前项目主要支持以下功能：

- 拓扑构建与可视化展示
- P4 代码装载与交换机规则注入
- 源宿主机之间的流量发送与路径验证
- 基于质数乘积的单路径一致性检测
- 出现异常后的路径恢复与故障定位展示
- 流表手动修改与路径变化观察
- 基于合法行为池的 VBP 演示验证
- 基于大模型的网络分析辅助功能

## 启动方式

### 环境要求
建议运行环境：

- [Ubuntu 22.04](https://releases.ubuntu.com/22.04/)
- [Mininet](http://mininet.org/)
- [P4 Language](https://p4.org/)
- [P4Utils](https://github.com/nsg-ethz/p4-utils)

### 启动步骤
- 进入 `application/` 目录
- 在具备相应权限的环境中运行：

```bash
python3 app.py
```

- 打开本地浏览器访问：

```text
http://localhost:5000
```

## 演示建议
推荐的演示顺序如下：

- 进入主页，介绍系统目标和核心机制
- 进入 Demo 页面，展示拓扑生成与规则注入
- 进行一次正常发送，展示预期路径与路径一致性验证
- 修改流表后再次发送，展示路径偏离与异常定位
- 在 Demo 页面中使用 VBP 模式发送，展示主路径、备份路径和非法路径三种判定思路
