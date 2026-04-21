import json
import os
import threading
import time

from flask import Blueprint, current_app, jsonify, request, session
from p4utils.mininetlib.log import error, info, warning

import topo.FatTree6.FatTree6 as ft6
import topo.demo.network as demo
from topo.runtime_files import atomic_write_json
from topo.semantic_runtime import merge_user_flow_policy
from services.topology_service import (
    build_nodes_from_edges,
    get_generated_intent_path,
    get_or_restore_current_topology,
    get_runtime_topology_path,
    instantiate_uploaded_topology,
    load_topology_edges_from_file,
    load_uploaded_topology_data,
    persist_intent,
)
from services.topology_state import switch_current_topology


topology_api = Blueprint('topology_api', __name__)


def _resolve_runtime_artifact_paths(active_topology):
    fallback_paths = {
        'behavior_pool': os.path.join(current_app.root_path, 'topo', 'behavior_pool.json'),
        'semantic_policy': os.path.join(current_app.root_path, 'topo', 'semantic_policy.json'),
        'semantic_state': os.path.join(current_app.root_path, 'topo', 'semantic_state.json'),
        'semantic_history': os.path.join(current_app.root_path, 'topo', 'semantic_history.json'),
    }

    if active_topology is None:
        return fallback_paths

    getter_map = {
        'behavior_pool': 'get_runtime_behavior_pool_path',
        'semantic_policy': 'get_runtime_semantic_policy_path',
        'semantic_state': 'get_runtime_semantic_state_path',
        'semantic_history': 'get_runtime_semantic_history_path',
    }

    resolved = {}
    for key, getter_name in getter_map.items():
        if hasattr(active_topology, getter_name):
            value = getattr(active_topology, getter_name)()
            if not os.path.isabs(value):
                value = os.path.join(current_app.root_path, value)
            resolved[key] = value
        else:
            resolved[key] = fallback_paths[key]
    return resolved


def _load_json_artifact(path, default_value):
    if not path or not os.path.exists(path):
        return default_value

    with open(path, 'r', encoding='utf-8') as file_obj:
        return json.load(file_obj)


def _switch_path_names(path_numbers):
    return [f's{int(node_id)}' for node_id in (path_numbers or [])]


def _strip_cidr(value):
    return str(value or '').split('/', 1)[0]


def _build_runtime_host_lookup(active_topology):
    try:
        node_map = _load_runtime_node_map(active_topology)
    except Exception:
        return {}

    host_lookup = {}
    for node in node_map.values():
        node_id = node.get('id', '')
        if not node.get('isHost') and not str(node_id).startswith('h'):
            continue
        ip_address = _strip_cidr(node.get('ip'))
        if ip_address:
            host_lookup[ip_address] = node_id
    return host_lookup


def _resolve_flow_scope_hosts(flow_scope, flow_id, host_lookup):
    resolved_scope = dict(flow_scope or {})
    src_ip = _strip_cidr(resolved_scope.get('src_ip', ''))
    dst_ip = _strip_cidr(resolved_scope.get('dst_ip', ''))

    if (not src_ip or not dst_ip) and flow_id and '-' in flow_id:
        src_ip, dst_ip = flow_id.split('-', 1)

    if src_ip:
        resolved_scope['src_ip'] = src_ip
        if not resolved_scope.get('src_host'):
            resolved_scope['src_host'] = host_lookup.get(src_ip, '')
    if dst_ip:
        resolved_scope['dst_ip'] = dst_ip
        if not resolved_scope.get('dst_host'):
            resolved_scope['dst_host'] = host_lookup.get(dst_ip, '')

    return resolved_scope


def _upsert_intent_flow(intent_payload, flow_scope, flow_policy, preferred_path):
    intent_payload = dict(intent_payload or {})
    flows = intent_payload.get('flows', [])
    if not isinstance(flows, list):
        flows = []

    src_host = flow_scope.get('src_host', '')
    dst_host = flow_scope.get('dst_host', '')
    enabled_paths = [
        [str(node).strip() for node in path if str(node).strip()]
        for path in flow_policy.get('enabled_paths', [])
        if isinstance(path, list)
    ]
    updated = False
    for flow in flows:
        if not isinstance(flow, dict):
            continue
        if flow.get('src') != src_host or flow.get('dst') != dst_host:
            continue

        flow['must_pass'] = list(flow_policy.get('must_pass', []))
        flow['avoid'] = list(flow_policy.get('avoid', []))
        flow['priority'] = flow_policy.get('priority', 'shortest')
        flow['backup_level'] = flow_policy.get('backup_level', 1)
        flow['preferred_path'] = list(preferred_path)
        flow['enabled_paths'] = enabled_paths
        updated = True
        break

    if not updated and src_host and dst_host:
        flows.append({
            'src': src_host,
            'dst': dst_host,
            'must_pass': list(flow_policy.get('must_pass', [])),
            'avoid': list(flow_policy.get('avoid', [])),
            'priority': flow_policy.get('priority', 'shortest'),
            'backup_level': flow_policy.get('backup_level', 1),
            'preferred_path': list(preferred_path),
            'enabled_paths': enabled_paths,
        })

    intent_payload['flows'] = flows
    return intent_payload


def _require_runtime_root():
    if os.geteuid() == 0:
        return None

    return jsonify({
        'error': 'Mininet/P4 运行需要 root 权限。请使用 sudo python3 app.py 启动服务，或在具备 root 权限的环境中运行。'
    }), 403


def _get_active_topology():
    return get_or_restore_current_topology(current_app.root_path, session.get('topology_data'))


def _get_preview_topology_file(active_topology):
    if active_topology.topoType == 'ft6':
        return os.path.join(current_app.root_path, 'topo', 'FatTree6', 'topo.txt')
    if active_topology.topoType == 'demo':
        return os.path.join(current_app.root_path, 'topo', 'demo', 'topo.txt')
    return None


def _load_runtime_node_map(active_topology):
    runtime_topology_path = get_runtime_topology_path(current_app.root_path, active_topology)
    with open(runtime_topology_path, 'r', encoding='utf-8') as file_obj:
        topology = json.load(file_obj)
    return {node['id']: node for node in topology.get('nodes', [])}


def _run_mininet_topology(topology_name, active_topology):
    info(f"开始构建拓扑: {topology_name}")
    try:
        active_topology.startNetwork()
    except Exception as exc:
        error(f"something wrong while building the network. Detailed info is as followed: {exc}")
        if hasattr(active_topology, 'stopNetwork'):
            active_topology.stopNetwork()
    info(f"{topology_name} 拓扑构建完成")


def _build_page_topology(topology_name):
    if topology_name == 'fattree6':
        return ft6.FatTree6()

    if topology_name == 'your_topology':
        uploaded_topology = load_uploaded_topology_data(current_app.root_path, session.get('topology_data'))
        if uploaded_topology:
            try:
                return instantiate_uploaded_topology(current_app.root_path, uploaded_topology)
            except Exception as exc:
                error(f"根据上传配置初始化动态拓扑失败，回退到默认 demo: {exc}\n")
        return demo.demo()

    return None


@topology_api.route('/get_topology_data')
def get_topology_data():
    active_topology = _get_active_topology()
    if active_topology is None:
        return jsonify({'error': '当前没有可展示的拓扑'}), 400

    if hasattr(active_topology, 'get_visual_edges'):
        return jsonify(active_topology.get_visual_edges())

    topo_data_file = _get_preview_topology_file(active_topology)
    if topo_data_file is None:
        return jsonify({'error': 'invalid topo'}), 404

    try:
        edges = load_topology_edges_from_file(topo_data_file)
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500

    return jsonify(edges)


@topology_api.route('/initiate_topo', methods=['POST'])
def initiate_topo():
    url = request.json.get('url')
    domains = url.rstrip('/').split('/')
    if len(domains) < 2:
        return jsonify({'error': 'in the wrong page!'}), 404

    last_domain = domains[-2]
    if last_domain != 'topology':
        return jsonify({'error': 'in the wrong page!'}), 404

    topology_name = domains[-1]
    selected_topology = _build_page_topology(topology_name)
    if selected_topology is None:
        return jsonify({'error': f'invalid topo: {topology_name}'}), 404

    switch_current_topology(selected_topology)
    info(f"successfully initiate topo {topology_name}\n")
    return jsonify({'status': 'success', 'topology': topology_name})


@topology_api.route('/select_topology', methods=['POST'])
def handle_select_topology():
    root_error = _require_runtime_root()
    if root_error is not None:
        return root_error

    data = request.json
    topology_name = data.get('topology')
    info(f"收到拓扑选择请求: {topology_name}")

    if topology_name not in ['fat4', 'fat6', 'demo', 'current']:
        return jsonify({'error': 'Invalid topology'}), 400

    active_topology = _get_active_topology()
    if active_topology is None:
        return jsonify({'error': '拓扑尚未初始化'}), 400

    active_topology_name = getattr(active_topology, 'topoType', topology_name)
    thread = threading.Thread(
        target=_run_mininet_topology,
        args=(active_topology_name, active_topology),
        daemon=True,
    )
    thread.start()

    return jsonify({'status': 'Topology selection received', 'topology': active_topology_name})


@topology_api.route('/get_topology_nodes')
def get_topology_nodes():
    active_topology = _get_active_topology()
    if active_topology is None:
        return jsonify({'error': '当前没有可展示的拓扑'}), 400

    if hasattr(active_topology, 'is_network_started') and active_topology.is_network_started():
        runtime_topology_path = get_runtime_topology_path(current_app.root_path, active_topology)
        if os.path.exists(runtime_topology_path):
            with open(runtime_topology_path, 'r', encoding='utf-8') as file_obj:
                topology = json.load(file_obj)
            return jsonify({'nodes': topology.get('nodes', [])})

    if hasattr(active_topology, 'get_visual_nodes'):
        return jsonify({'nodes': active_topology.get_visual_nodes()})

    topo_data_file = _get_preview_topology_file(active_topology)
    if topo_data_file and os.path.exists(topo_data_file):
        try:
            edges = load_topology_edges_from_file(topo_data_file)
            return jsonify({'nodes': build_nodes_from_edges(edges)})
        except Exception as exc:
            warning(f"根据 topo.txt 生成预览节点失败，已忽略: {exc}\n")

    runtime_topology_path = get_runtime_topology_path(current_app.root_path, active_topology)
    if os.path.exists(runtime_topology_path):
        with open(runtime_topology_path, 'r', encoding='utf-8') as file_obj:
            topology = json.load(file_obj)
        return jsonify({'nodes': topology.get('nodes', [])})

    return jsonify({'nodes': []})


@topology_api.route('/send_command', methods=['POST'])
def handle_send_command():
    active_topology = _get_active_topology()
    if active_topology is None:
        return jsonify({'error': 'No topology built yet'}), 400

    data = request.get_json()
    src_host = data.get('src')
    dst_host = data.get('dst')
    if not src_host or not dst_host:
        return jsonify({'error': '请提供源主机和目标主机'}), 400

    try:
        node_map = _load_runtime_node_map(active_topology)
        if src_host not in node_map or dst_host not in node_map:
            return jsonify({'error': '主机 ID 不存在'}), 400
        src_ip = node_map[src_host].get('ip', '')
        dst_ip = node_map[dst_host].get('ip', '')
    except Exception as exc:
        return jsonify({'error': f'IP地址查找失败: {str(exc)}'}), 500

    info(f"Receive: {src_host}({src_ip}) → {dst_host}({dst_ip})")
    try:
        active_topology.send(src_host, dst_host)
    except Exception as exc:
        return jsonify({'error': f'发送执行失败: {str(exc)}'}), 500

    return jsonify({'result': f'命令已发送：{src_host} → {dst_host}'})


@topology_api.route('/send_command_vbp', methods=['POST'])
def handle_send_command_vbp():
    active_topology = _get_active_topology()
    if active_topology is None:
        return jsonify({'error': 'No topology built yet'}), 400

    data = request.get_json()
    src_host = data.get('src')
    dst_host = data.get('dst')
    if not src_host or not dst_host:
        return jsonify({'error': '请提供源主机和目标主机'}), 400

    try:
        node_map = _load_runtime_node_map(active_topology)
        if src_host not in node_map or dst_host not in node_map:
            return jsonify({'error': '主机 ID 不存在'}), 400
        src_ip = node_map[src_host].get('ip', '')
        dst_ip = node_map[dst_host].get('ip', '')
    except Exception as exc:
        return jsonify({'error': f'IP地址查找失败: {str(exc)}'}), 500

    info(f"Receive VBP: {src_host}({src_ip}) → {dst_host}({dst_ip})")

    if not hasattr(active_topology, 'send_vbp'):
        return jsonify({'error': '当前拓扑未启用 VBP 演示接口'}), 400

    try:
        active_topology.send_vbp(src_host, dst_host)
    except Exception as exc:
        return jsonify({'error': f'VBP 发送执行失败: {str(exc)}'}), 500

    return jsonify({'result': f'VBP 命令已发送：{src_host} → {dst_host}'})


@topology_api.route('/get_res_json', methods=['GET'])
def get_res_json():
    res_file_path = os.path.join(current_app.root_path, 'res.json')
    if os.path.exists(res_file_path):
        with open(res_file_path, 'r', encoding='utf-8') as file_obj:
            data = file_obj.read()
        return jsonify(data), 200
    return jsonify({'error': 'res.json not found'}), 404


@topology_api.route('/get_verification_profile', methods=['GET'])
def get_verification_profile():
    active_topology = _get_active_topology()
    artifact_paths = _resolve_runtime_artifact_paths(active_topology)
    behavior_pool = _load_json_artifact(artifact_paths['behavior_pool'], [])
    semantic_policy = _load_json_artifact(artifact_paths['semantic_policy'], {'flows': []})
    semantic_state = _load_json_artifact(artifact_paths['semantic_state'], {'flows': {}})
    semantic_history = _load_json_artifact(artifact_paths['semantic_history'], [])
    host_lookup = _build_runtime_host_lookup(active_topology)

    enriched_policy = dict(semantic_policy or {})
    enriched_flows = []
    for flow in semantic_policy.get('flows', []):
        if not isinstance(flow, dict):
            continue

        enriched_flow = dict(flow)
        enriched_flow['flow_scope'] = _resolve_flow_scope_hosts(flow.get('flow_scope', {}), flow.get('flow_id', ''), host_lookup)
        if not enriched_flow.get('path_catalog'):
            enriched_flow['path_catalog'] = [
                {
                    'index': behavior.get('index', index),
                    'label': behavior.get('label') or f'候选路径 {index + 1}',
                    'path': behavior.get('path', []),
                    'switch_path': behavior.get('switch_path') or _switch_path_names(behavior.get('path', [])),
                    'active': True,
                }
                for index, behavior in enumerate(flow.get('behaviors', []))
                if isinstance(behavior, dict)
            ]
        if not enriched_flow.get('enabled_paths'):
            enriched_flow['enabled_paths'] = [
                list(behavior.get('switch_path') or _switch_path_names(behavior.get('path', [])))
                for behavior in flow.get('behaviors', [])
                if isinstance(behavior, dict)
            ]
        enriched_flows.append(enriched_flow)

    enriched_policy['flows'] = enriched_flows

    behavior_pool_summary = []
    for item in behavior_pool:
        behaviors = item.get('behaviors', [])
        src_ip = _strip_cidr(item.get('src_ip', ''))
        dst_ip = _strip_cidr(item.get('dst_ip', ''))
        src_host = item.get('src_host') or host_lookup.get(src_ip, '')
        dst_host = item.get('dst_host') or host_lookup.get(dst_ip, '')
        behavior_pool_summary.append({
            'flow_id': f"{item.get('src_ip', '')}-{item.get('dst_ip', '')}",
            'src_ip': item.get('src_ip', ''),
            'dst_ip': item.get('dst_ip', ''),
            'src_host': src_host,
            'dst_host': dst_host,
            'legal_path_count': len(behaviors),
            'labels': [behavior.get('label', '') for behavior in behaviors],
        })

    state_summary = []
    for flow_id, flow_state in (semantic_state.get('flows', {}) or {}).items():
        state_summary.append({
            'flow_id': flow_id,
            'packet_count': flow_state.get('packet_count', 0),
            'current_state': flow_state.get('current_state', 'INIT'),
            'last_verdict': flow_state.get('last_verdict', 'unknown'),
            'last_behavior_index': flow_state.get('last_behavior_index'),
            'degraded_packets': flow_state.get('degraded_packets', 0),
            'state_change_count': flow_state.get('state_change_count', 0),
            'consecutive_backup_packets': flow_state.get('consecutive_backup_packets', 0),
        })

    return jsonify({
        'behavior_pool': behavior_pool,
        'behavior_pool_summary': behavior_pool_summary,
        'semantic_policy': enriched_policy,
        'semantic_state': semantic_state,
        'semantic_state_summary': state_summary,
        'semantic_history': semantic_history[-10:],
        'host_lookup': host_lookup,
    })


@topology_api.route('/update_semantic_policy', methods=['POST'])
def update_semantic_policy():
    active_topology = _get_active_topology()
    if active_topology is None:
        return jsonify({'error': '当前没有可编辑的拓扑运行时策略'}), 400

    artifact_paths = _resolve_runtime_artifact_paths(active_topology)
    policy_path = artifact_paths['semantic_policy']
    policy = _load_json_artifact(policy_path, {'flows': []})
    flows = policy.setdefault('flows', [])

    data = request.get_json(silent=True) or {}
    flow_id = str(data.get('flow_id', '')).strip()
    if not flow_id:
        return jsonify({'error': '请提供 flow_id'}), 400

    for index, flow in enumerate(flows):
        if flow.get('flow_id') != flow_id:
            continue

        try:
            flows[index] = merge_user_flow_policy(
                flow,
                max_packets=data.get('max_packets'),
                max_hops=data.get('max_hops'),
                invariants=data.get('invariants'),
                allowed_transitions=data.get('allowed_transitions'),
                max_degraded_packets=data.get('max_degraded_packets'),
                max_state_changes=data.get('max_state_changes'),
                require_primary_recovery=data.get('require_primary_recovery'),
            )
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400

        policy['updated_at'] = int(time.time())

        try:
            atomic_write_json(policy_path, policy, ensure_ascii=False, indent=2)
        except OSError as exc:
            return jsonify({'error': f'写入 semantic policy 失败：{exc}'}), 500

        return jsonify({
            'message': f'已保存 {flow_id} 的语义策略。下次发送验证流量时将使用新的不变量和状态转移集合。',
            'flow': flows[index],
        })

    return jsonify({'error': f'未找到 flow: {flow_id}'}), 404


@topology_api.route('/apply_expected_path', methods=['POST'])
def apply_expected_path():
    root_error = _require_runtime_root()
    if root_error is not None:
        return root_error

    active_topology = _get_active_topology()
    if active_topology is None:
        return jsonify({'error': '当前没有可用拓扑，请先上传并构建拓扑。'}), 400

    if getattr(active_topology, 'topoType', '') != 'dynamic_demo':
        return jsonify({'error': '当前仅上传拓扑支持 flow 级预期路径编排。'}), 400

    if not hasattr(active_topology, 'is_network_started') or not active_topology.is_network_started():
        return jsonify({'error': '请先装载 P4、生成当前上传拓扑并注入流表。'}), 400

    artifact_paths = _resolve_runtime_artifact_paths(active_topology)
    policy = _load_json_artifact(artifact_paths['semantic_policy'], {'flows': []})

    data = request.get_json(silent=True) or {}
    flow_id = str(data.get('flow_id', '')).strip()
    reset_to_auto = bool(data.get('reset_to_auto'))
    behavior_index = data.get('behavior_index')
    if not flow_id:
        return jsonify({'error': '请提供 flow_id'}), 400

    selected_flow = None
    for flow in policy.get('flows', []):
        if flow.get('flow_id') == flow_id:
            selected_flow = flow
            break

    if not selected_flow:
        return jsonify({'error': f'未找到 flow: {flow_id}'}), 404

    behaviors = selected_flow.get('behaviors', [])
    chosen_behavior = None
    if not reset_to_auto:
        try:
            behavior_index = int(behavior_index)
        except (TypeError, ValueError):
            return jsonify({'error': 'behavior_index 必须是整数'}), 400

        if behavior_index < 0 or behavior_index >= len(behaviors):
            return jsonify({'error': 'behavior_index 超出候选路径范围'}), 400

        chosen_behavior = behaviors[behavior_index]

    host_lookup = _build_runtime_host_lookup(active_topology)
    flow_scope = _resolve_flow_scope_hosts(selected_flow.get('flow_scope', {}), selected_flow.get('flow_id', ''), host_lookup)
    if not flow_scope.get('src_host') or not flow_scope.get('dst_host'):
        return jsonify({'error': '当前 flow 缺少主机作用域，无法应用预期路径。'}), 400

    preferred_path = [] if reset_to_auto else _switch_path_names(chosen_behavior.get('path', []))
    generated_intent_path = get_generated_intent_path(current_app.root_path)
    intent_payload = session.get('intent_data') or _load_json_artifact(generated_intent_path, {'summary': '', 'flows': []})
    intent_payload = _upsert_intent_flow(intent_payload, flow_scope, selected_flow, preferred_path)
    normalized_intent, intent_path = persist_intent(current_app.root_path, intent_payload)
    session['intent_data'] = normalized_intent

    success = active_topology.program_switches()
    if not success:
        return jsonify({'error': '预期路径已写入 intent，但重新编排交换机流表失败。'}), 500

    if reset_to_auto:
        message = f'已恢复 {flow_id} 的自动主路径选择，并重新同步运行时规则与流表。'
    else:
        message = f'已将 {flow_id} 的预期主路径切换为候选路径 #{behavior_index}，并重新同步运行时规则与流表。'

    return jsonify({
        'message': message,
        'flow_id': flow_id,
        'primary_path': None if reset_to_auto else chosen_behavior.get('path', []),
        'intent_path': intent_path,
    })


@topology_api.route('/update_vbp_paths', methods=['POST'])
def update_vbp_paths():
    root_error = _require_runtime_root()
    if root_error is not None:
        return root_error

    active_topology = _get_active_topology()
    if active_topology is None:
        return jsonify({'error': '当前没有可用拓扑，请先上传并构建拓扑。'}), 400

    if getattr(active_topology, 'topoType', '') != 'dynamic_demo':
        return jsonify({'error': '当前仅上传拓扑支持自定义 VBP 候选路径。'}), 400

    if not hasattr(active_topology, 'is_network_started') or not active_topology.is_network_started():
        return jsonify({'error': '请先装载 P4、生成当前上传拓扑并注入流表。'}), 400

    artifact_paths = _resolve_runtime_artifact_paths(active_topology)
    policy = _load_json_artifact(artifact_paths['semantic_policy'], {'flows': []})
    data = request.get_json(silent=True) or {}
    flow_id = str(data.get('flow_id', '')).strip()
    reset_to_auto = bool(data.get('reset_to_auto'))
    if not flow_id:
        return jsonify({'error': '请提供 flow_id'}), 400

    selected_flow = None
    for flow in policy.get('flows', []):
        if flow.get('flow_id') == flow_id:
            selected_flow = flow
            break

    if not selected_flow:
        return jsonify({'error': f'未找到 flow: {flow_id}'}), 404

    host_lookup = _build_runtime_host_lookup(active_topology)
    flow_scope = _resolve_flow_scope_hosts(selected_flow.get('flow_scope', {}), selected_flow.get('flow_id', ''), host_lookup)
    if not flow_scope.get('src_host') or not flow_scope.get('dst_host'):
        return jsonify({'error': '当前 flow 缺少主机作用域，无法更新 VBP 路径集合。'}), 400

    normalized_enabled_paths = []
    if not reset_to_auto:
        enabled_paths = data.get('enabled_paths', [])
        if not isinstance(enabled_paths, list) or not enabled_paths:
            return jsonify({'error': '请至少保留一条 VBP 路径。'}), 400

        seen_paths = set()
        for index, path in enumerate(enabled_paths, start=1):
            if not isinstance(path, list) or not path:
                return jsonify({'error': f'第 {index} 条路径格式无效。'}), 400

            normalized_path = []
            for node in path:
                node_id = str(node).strip()
                if not node_id.startswith('s'):
                    return jsonify({'error': f'第 {index} 条路径中包含无效交换机 ID: {node_id}'}), 400
                normalized_path.append(node_id)

            signature = tuple(normalized_path)
            if signature in seen_paths:
                continue
            seen_paths.add(signature)
            normalized_enabled_paths.append(normalized_path)

        if not normalized_enabled_paths:
            return jsonify({'error': '请至少保留一条唯一的 VBP 路径。'}), 400

    current_preferred_path = selected_flow.get('preferred_path', []) if isinstance(selected_flow.get('preferred_path', []), list) else []
    preferred_path = current_preferred_path
    if normalized_enabled_paths and tuple(preferred_path) not in {tuple(path) for path in normalized_enabled_paths}:
        preferred_path = normalized_enabled_paths[0]

    generated_intent_path = get_generated_intent_path(current_app.root_path)
    intent_payload = session.get('intent_data') or _load_json_artifact(generated_intent_path, {'summary': '', 'flows': []})
    flow_policy = dict(selected_flow)
    flow_policy['enabled_paths'] = normalized_enabled_paths
    flow_policy['backup_level'] = selected_flow.get('backup_level', max(len(selected_flow.get('behaviors', [])) - 1, 0)) if reset_to_auto else max(len(normalized_enabled_paths) - 1, 0)
    intent_payload = _upsert_intent_flow(intent_payload, flow_scope, flow_policy, preferred_path)
    normalized_intent, intent_path = persist_intent(current_app.root_path, intent_payload)
    session['intent_data'] = normalized_intent

    success = active_topology.program_switches()
    if not success:
        return jsonify({'error': 'VBP 路径集合已写入 intent，但重新编排交换机流表失败。'}), 500

    if reset_to_auto:
        message = f'已恢复 {flow_id} 的系统推荐 VBP 候选集合。'
    else:
        message = f'已更新 {flow_id} 的 VBP 候选集合，当前保留 {len(normalized_enabled_paths)} 条路径。'

    return jsonify({
        'message': message,
        'flow_id': flow_id,
        'enabled_path_count': len(normalized_enabled_paths),
        'intent_path': intent_path,
    })


@topology_api.route('/modify_flow_table', methods=['POST'])
def modify_flow_table():
    data = request.json
    swid = data.get('swid')
    dst_host = data.get('dst_host')
    dst_swid = data.get('dst_swid')

    if not (swid and dst_host and dst_swid):
        return jsonify({'status': 'error', 'msg': '参数不完整'})

    active_topology = _get_active_topology()
    if active_topology is None:
        return jsonify({'status': 'error', 'msg': '当前没有可用拓扑，请先上传并构建拓扑'})

    try:
        active_topology.modify_switch(swid, dst_host, dst_swid)
        return jsonify({'status': 'success', 'msg': '修改完成'})
    except Exception as exc:
        return jsonify({'status': 'error', 'msg': str(exc)})


@topology_api.route('/load_p4_code', methods=['POST'])
def load_p4_code():
    active_topology = _get_active_topology()
    if active_topology is None:
        return jsonify({'message': '当前没有可用拓扑，请先上传或初始化拓扑。'}), 400

    info('开始加载p4代码...')
    success = active_topology.clean_and_compile()
    info('p4代码加载完成')
    if success:
        return jsonify({'message': 'P4 代码装载成功！'})
    return jsonify({'message': 'P4 代码装载失败，请检查错误！'}), 500


@topology_api.route('/inject_flow_table', methods=['POST'])
def inject_flow_table():
    active_topology = _get_active_topology()
    if active_topology is None:
        return jsonify({'message': '当前没有可用拓扑，请先上传或初始化拓扑。'}), 400

    info('开始注入流表...')
    success = active_topology.program_switches()
    info('流表注入完成')
    if success:
        return jsonify({'message': '流表注入成功！'})
    return jsonify({'message': '流表注入失败，请检查错误！'}), 500


@topology_api.route('/get_topology_data_demo')
def get_topology_data_demo():
    edges = []
    try:
        with open(os.path.join(current_app.root_path, 'topo', 'demo', 'topo.txt'), 'r', encoding='utf-8') as file_obj:
            for line in file_obj:
                line = line.strip().replace('(', '').replace(')', '').replace(',', '')
                parts = line.split()
                if len(parts) == 2:
                    edges.append({'from': parts[0], 'to': parts[1]})
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500

    return jsonify(edges)