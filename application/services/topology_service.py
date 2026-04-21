import json
import os
import re

import networkx as nx
from p4utils.mininetlib.log import warning

import topo.dynamic_demo as dynamic_demo
from topo.runtime_files import atomic_write_json, atomic_write_text
from topo.runtime_paths import (
    ensure_user_topology_dirs,
    get_user_network_script_path,
    get_user_uploaded_topology_path,
)

from services.topology_state import get_current_topology, switch_current_topology


SWITCH_ID_PATTERN = re.compile(r'^s\d+$')
HOST_ID_PATTERN = re.compile(r'^h\d+$')


def get_generated_dir(app_root_path):
    generated_dir = os.path.join(app_root_path, 'generated')
    os.makedirs(generated_dir, exist_ok=True)
    return generated_dir


def resolve_app_path(app_root_path, path):
    if os.path.isabs(path):
        return path
    return os.path.join(app_root_path, path)


def get_runtime_topology_path(app_root_path, active_topology=None):
    active_topology = active_topology or get_current_topology()
    if active_topology is not None and hasattr(active_topology, 'get_runtime_topology_path'):
        return resolve_app_path(app_root_path, active_topology.get_runtime_topology_path())
    return os.path.join(app_root_path, 'topology.json')


def get_uploaded_topology_path(app_root_path):
    ensure_user_topology_dirs(app_root_path)
    return get_user_uploaded_topology_path(app_root_path)


def get_generated_network_script_path(app_root_path):
    ensure_user_topology_dirs(app_root_path)
    return get_user_network_script_path(app_root_path)


def get_generated_intent_path(app_root_path):
    return os.path.join(get_generated_dir(app_root_path), 'intent.json')


def build_llm_topology_payload(topo_data):
    return {
        'intent_description': topo_data.get('intent_description', ''),
        'topology': {
            'switch': topo_data.get('switch', []),
            'host': topo_data.get('host', []),
            'link': topo_data.get('link', []),
        },
    }


def normalize_intent_payload(intent_data):
    if not isinstance(intent_data, dict):
        intent_data = {}

    flows = intent_data.get('flows', [])
    if not isinstance(flows, list):
        flows = []

    normalized_flows = []
    for flow in flows:
        if not isinstance(flow, dict):
            continue
        preferred_path = flow.get('preferred_path', [])
        if not isinstance(preferred_path, list):
            preferred_path = []
        enabled_paths = flow.get('enabled_paths', [])
        if not isinstance(enabled_paths, list):
            enabled_paths = []
        normalized_flows.append({
            'src': flow.get('src', ''),
            'dst': flow.get('dst', ''),
            'must_pass': flow.get('must_pass', []) if isinstance(flow.get('must_pass', []), list) else [],
            'avoid': flow.get('avoid', []) if isinstance(flow.get('avoid', []), list) else [],
            'priority': flow.get('priority', ''),
            'backup_level': flow.get('backup_level', 0),
            'preferred_path': [node for node in preferred_path if isinstance(node, str) and node.strip()],
            'enabled_paths': [
                [node for node in path if isinstance(node, str) and node.strip()]
                for path in enabled_paths
                if isinstance(path, list)
            ],
        })

    return {
        'summary': intent_data.get('summary', ''),
        'flows': normalized_flows,
    }


def persist_intent(app_root_path, intent_data):
    normalized_intent = normalize_intent_payload(intent_data)
    intent_path = get_generated_intent_path(app_root_path)
    atomic_write_json(intent_path, normalized_intent, ensure_ascii=False, indent=2)
    return normalized_intent, intent_path


def node_sort_key(node_id):
    match = re.match(r'^([A-Za-z_]+)(\d+)$', node_id)
    if match:
        return match.group(1), int(match.group(2))
    return node_id, 0


def normalize_link_objects(links, all_nodes):
    normalized_links = []
    seen_pairs = set()

    for link_obj in links:
        if not isinstance(link_obj, dict):
            raise ValueError(f"JSON格式错误：link数组中的元素必须是对象 (字典)。出错的元素: {link_obj}")

        endpoints = list(link_obj.keys())
        if len(endpoints) != 2:
            raise ValueError(f"JSON格式错误：link对象必须正好包含两对键值对。出错的对象: {link_obj}")

        ep1, ep2 = endpoints[0], endpoints[1]
        if not (link_obj.get(ep1) == ep2 and link_obj.get(ep2) == ep1):
            raise ValueError(
                f"JSON格式错误：link对象必须是双向的 (例如 {{'h1':'s1', 's1':'h1'}})。出错的对象: {link_obj}"
            )

        if ep1 not in all_nodes or ep2 not in all_nodes:
            undefined_node = ep1 if ep1 not in all_nodes else ep2
            raise ValueError(f"JSON格式错误：link中包含未在'switch'或'host'中定义的节点ID '{undefined_node}'。")

        pair = tuple(sorted((ep1, ep2), key=node_sort_key))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        normalized_links.append({pair[0]: pair[1], pair[1]: pair[0]})

    return normalized_links


def validate_uploaded_topology_payload(topo_data):
    required_keys = {'intent_description', 'switch', 'host', 'link'}
    if not required_keys.issubset(topo_data.keys()):
        raise ValueError(
            "JSON格式错误：文件必须包含 'intent_description', 'switch', 'host', 和 'link' 四个顶级键。"
        )

    allowed_keys = {'intent_description', 'switch', 'host', 'link'}
    extra_keys = set(topo_data.keys()) - allowed_keys
    if extra_keys:
        raise ValueError(f"JSON格式错误：发现了不允许的顶级键: {', '.join(sorted(extra_keys))}")

    intent_description = topo_data.get('intent_description')
    if not isinstance(intent_description, str) or not intent_description.strip():
        raise ValueError("JSON格式错误：'intent_description' 必须是非空字符串，用于说明用户希望实现的网络意图。")

    switches = topo_data.get('switch', [])
    hosts = topo_data.get('host', [])
    links = topo_data.get('link', [])
    if not isinstance(switches, list) or not isinstance(hosts, list) or not isinstance(links, list):
        raise ValueError("JSON格式错误：'switch'、'host'、'link' 的值都必须是数组。")

    if not switches:
        raise ValueError("JSON格式错误：'switch' 列表不能为空。")
    if len(hosts) < 2:
        raise ValueError("JSON格式错误：至少需要两个主机，才能进行路径发送与验证。")
    if len(switches) > 45:
        raise ValueError("JSON格式错误：交换机数量不能超过 45 个，当前质数编码表无法支持更多交换机。")

    if any(not isinstance(node, str) or not node.strip() for node in switches + hosts):
        raise ValueError("JSON格式错误：'switch' 和 'host' 列表中的节点 ID 必须都是非空字符串。")
    if len(set(switches)) != len(switches):
        raise ValueError("JSON格式错误：'switch' 列表中存在重复的交换机 ID。")
    if len(set(hosts)) != len(hosts):
        raise ValueError("JSON格式错误：'host' 列表中存在重复的主机 ID。")
    if set(switches) & set(hosts):
        raise ValueError("JSON格式错误：'switch' 和 'host' 列表中存在重名节点。")

    invalid_switches = [node for node in switches if not SWITCH_ID_PATTERN.match(node)]
    invalid_hosts = [node for node in hosts if not HOST_ID_PATTERN.match(node)]
    if invalid_switches:
        raise ValueError("JSON格式错误：交换机 ID 必须采用 s1、s2 这样的格式。")
    if invalid_hosts:
        raise ValueError("JSON格式错误：主机 ID 必须采用 h1、h2 这样的格式。")

    sorted_switches = sorted(switches, key=node_sort_key)
    sorted_hosts = sorted(hosts, key=node_sort_key)
    all_nodes = set(sorted_switches) | set(sorted_hosts)
    normalized_links = normalize_link_objects(links, all_nodes)
    if not normalized_links:
        raise ValueError("JSON格式错误：'link' 列表不能为空。")

    graph = nx.Graph()
    graph.add_nodes_from(sorted_switches + sorted_hosts)
    for link_obj in normalized_links:
        endpoints = list(link_obj.keys())
        graph.add_edge(endpoints[0], endpoints[1])

        left_is_host = endpoints[0] in sorted_hosts
        right_is_host = endpoints[1] in sorted_hosts
        if left_is_host and right_is_host:
            raise ValueError("JSON格式错误：不支持主机与主机直连，请改为主机连接交换机。")

    if not nx.is_connected(graph):
        raise ValueError("JSON格式错误：当前拓扑不是连通图，存在无法到达的节点。")

    for host in sorted_hosts:
        host_neighbors = list(graph.neighbors(host))
        if len(host_neighbors) != 1:
            raise ValueError(f"JSON格式错误：主机 {host} 必须且只能连接一台交换机。")
        if host_neighbors[0] not in sorted_switches:
            raise ValueError(f"JSON格式错误：主机 {host} 只能连接交换机，不能连接其他主机。")

    return {
        'intent_description': intent_description.strip(),
        'switch': sorted_switches,
        'host': sorted_hosts,
        'link': normalized_links,
    }


def build_topology_summary(topo_data):
    return {
        'switch_count': len(topo_data.get('switch', [])),
        'host_count': len(topo_data.get('host', [])),
        'link_count': len(topo_data.get('link', [])),
    }


def build_nodes_from_edges(edges):
    nodes = []
    seen = set()
    for edge in edges:
        for node_id in (edge.get('from'), edge.get('to')):
            if not node_id or node_id in seen:
                continue
            seen.add(node_id)
            nodes.append({
                'id': node_id,
                'isHost': node_id.startswith('h'),
            })
    return sorted(nodes, key=lambda item: node_sort_key(item['id']))


def load_topology_edges_from_file(topo_data_file):
    edges = []
    with open(topo_data_file, 'r', encoding='utf-8') as file_obj:
        for line in file_obj:
            line = line.strip().replace('(', '').replace(')', '').replace(',', '')
            parts = line.split()
            if len(parts) == 2:
                edges.append({'from': parts[0], 'to': parts[1]})
    return edges


def persist_uploaded_topology(app_root_path, topo_data):
    topo_path = get_uploaded_topology_path(app_root_path)
    atomic_write_json(topo_path, topo_data, ensure_ascii=False, indent=2)

    script_path = get_generated_network_script_path(app_root_path)
    script_content = dynamic_demo.render_network_script(
        topo_data,
        os.path.relpath(topo_path, app_root_path).replace(os.sep, '/'),
    )
    atomic_write_text(script_path, script_content)

    return topo_path, script_path


def load_uploaded_topology_data(app_root_path, session_topology_data=None):
    if isinstance(session_topology_data, dict):
        return session_topology_data

    topo_path = get_uploaded_topology_path(app_root_path)
    if os.path.exists(topo_path):
        try:
            with open(topo_path, 'r', encoding='utf-8') as file_obj:
                return json.load(file_obj)
        except OSError as exc:
            warning(f"读取上传拓扑配置失败，忽略当前运行时文件并回退默认拓扑: {exc}\n")
            return None
        except json.JSONDecodeError as exc:
            warning(f"上传拓扑配置内容损坏，忽略当前运行时文件并回退默认拓扑: {exc}\n")
            return None
    return None


def instantiate_uploaded_topology(app_root_path, topo_data):
    topo_path, _ = persist_uploaded_topology(app_root_path, topo_data)
    return dynamic_demo.DynamicDemo(topo_path)


def get_or_restore_current_topology(app_root_path, session_topology_data=None):
    current_topology = get_current_topology()
    if current_topology is not None:
        return current_topology

    uploaded_topology = load_uploaded_topology_data(app_root_path, session_topology_data)
    if uploaded_topology is None:
        return None

    try:
        switch_current_topology(instantiate_uploaded_topology(app_root_path, uploaded_topology))
    except Exception as exc:
        warning(f"恢复上传拓扑失败，当前会话没有可用运行时拓扑: {exc}\n")
        return None

    return get_current_topology()