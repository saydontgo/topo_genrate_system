import json
import os
import re
import shlex
import time

import networkx as nx
from p4utils.mininetlib.log import debug, info, output, error
from p4utils.mininetlib.network_API import NetworkAPI

from .helper import hex_IP
from .runtime_files import (
    atomic_write_json,
    atomic_write_text,
    copy_text_file,
    prepare_output_path,
    prepare_p4_build_outputs,
)
from .runtime_paths import (
    ensure_user_topology_dirs,
    get_user_runtime_behavior_pool_path,
    get_user_runtime_semantic_history_path,
    get_user_runtime_semantic_policy_path,
    get_user_runtime_semantic_state_path,
    get_user_runtime_rules_path,
    get_user_runtime_switch_command_dir,
    get_user_runtime_topo_txt_path,
    get_user_runtime_topology_path,
    get_user_topology_runtime_dir,
)
from .semantic_runtime import initialize_semantic_runtime, refresh_semantic_runtime
from .topo import Topology


def node_sort_key(node_id):
    match = re.match(r'^([A-Za-z_]+)(\d+)$', node_id)
    if match:
        return match.group(1), int(match.group(2))
    return node_id, 0


def render_network_script(topology_config, config_path='topo/user_topology/uploaded_topology.json'):
    topology_literal = json.dumps(topology_config, ensure_ascii=False, indent=4)
    normalized_config_path = config_path.replace('\\', '/')
    return f"""import json

from topo.dynamic_demo import DynamicDemo

UPLOADED_TOPOLOGY = {topology_literal}


def write_uploaded_topology():
    with open({normalized_config_path!r}, 'w', encoding='utf-8') as f:
        json.dump(UPLOADED_TOPOLOGY, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    write_uploaded_topology()
    topo = DynamicDemo({normalized_config_path!r})
    topo.clean_and_compile()
    topo.startNetwork()
    topo.program_switches()
"""


class DynamicDemo(NetworkAPI):
    def __init__(self, config_path, *args, **params):
        super().__init__(*args, **params)
        self.setLogLevel('info')
        self.disableCli()
        self._topoType = 'dynamic_demo'
        self.__isNetworkStart = False
        self.__isCompiled = False
        self.config_path = config_path
        ensure_user_topology_dirs()
        self.artifact_dir = os.path.abspath(get_user_topology_runtime_dir())
        self.switch_command_dir = os.path.abspath(get_user_runtime_switch_command_dir())
        self.runtime_topology_path = os.path.abspath(get_user_runtime_topology_path())
        self.runtime_rules_path = os.path.abspath(get_user_runtime_rules_path())
        self.runtime_behavior_pool_path = os.path.abspath(get_user_runtime_behavior_pool_path())
        self.runtime_semantic_policy_path = os.path.abspath(get_user_runtime_semantic_policy_path())
        self.runtime_semantic_state_path = os.path.abspath(get_user_runtime_semantic_state_path())
        self.runtime_semantic_history_path = os.path.abspath(get_user_runtime_semantic_history_path())
        self.runtime_topo_txt_path = os.path.abspath(get_user_runtime_topo_txt_path())
        os.makedirs(self.switch_command_dir, exist_ok=True)

        self.config = self._load_config(config_path)
        self.configured_switches = sorted(self.config['switch'], key=node_sort_key)
        self.configured_hosts = sorted(self.config['host'], key=node_sort_key)
        self.link_pairs = self._normalize_links(self.config['link'])
        self.graph = nx.Graph()
        self.graph.add_nodes_from(self.configured_switches + self.configured_hosts)
        self.graph.add_edges_from(self.link_pairs)
        self.host_attachments = self._build_host_attachments()
        self.switch_order = {switch_name: index + 1 for index, switch_name in enumerate(self.configured_switches)}
        self._switch_commands = {}
        self._preview_edges = [{'from': left, 'to': right} for left, right in self.link_pairs]
        self._preview_nodes = self._build_preview_nodes()

        self._activate_empty_rule_files()
        self._write_preview_topology_file()
        self._build_network_definition()

    @property
    def topoType(self):
        return self._topoType

    def is_network_started(self):
        return self.__isNetworkStart

    def get_runtime_topology_path(self):
        return self.runtime_topology_path

    def get_runtime_behavior_pool_path(self):
        return self.runtime_behavior_pool_path

    def get_runtime_semantic_policy_path(self):
        return self.runtime_semantic_policy_path

    def get_runtime_semantic_state_path(self):
        return self.runtime_semantic_state_path

    def get_runtime_semantic_history_path(self):
        return self.runtime_semantic_history_path

    def get_visual_edges(self):
        return list(self._preview_edges)

    def get_visual_nodes(self):
        return list(self._preview_nodes)

    def _load_config(self, config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _normalize_links(self, link_objects):
        normalized_links = []
        seen_pairs = set()

        for link_obj in link_objects:
            endpoints = list(link_obj.keys())
            left, right = sorted((endpoints[0], endpoints[1]), key=node_sort_key)
            pair = (left, right)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            normalized_links.append(pair)

        return normalized_links

    def _build_host_attachments(self):
        attachments = {}
        for host_name in self.configured_hosts:
            neighbors = [neighbor for neighbor in self.graph.neighbors(host_name) if neighbor in self.configured_switches]
            attachments[host_name] = neighbors[0]
        return attachments

    def _host_number(self, host_name):
        match = re.search(r'(\d+)$', host_name)
        if match:
            return int(match.group(1))
        return 0

    def _preview_host_runtime(self, host_name):
        access_switch = self.host_attachments[host_name]
        switch_number = self._switch_number(access_switch)
        host_number = self._host_number(host_name)
        return {
            'ip': f'10.0.{switch_number}.{host_number}/24',
            'mac': f'00:00:0a:00:{switch_number:02x}:{host_number:02x}',
            'access_switch': access_switch,
        }

    def _build_preview_nodes(self):
        preview_nodes = []
        for host_name in self.configured_hosts:
            runtime_meta = self._preview_host_runtime(host_name)
            preview_nodes.append({
                'id': host_name,
                'isHost': True,
                'ip': runtime_meta['ip'],
                'mac': runtime_meta['mac'],
                'access_switch': runtime_meta['access_switch'],
            })

        for switch_name in self.configured_switches:
            preview_nodes.append({
                'id': switch_name,
                'isHost': False,
                'isSwitch': True,
                'device_id': self._switch_number(switch_name),
                'thrift_port': self._thrift_port(switch_name),
            })

        return preview_nodes

    def _host_runtime(self):
        return {
            host_name: {
                'ip': self.net.get(host_name).IP(),
                'mac': self.net.get(host_name).MAC(),
                'access_switch': self.host_attachments[host_name],
            }
            for host_name in self.configured_hosts
        }

    def _build_network_definition(self):
        for switch_name in self.configured_switches:
            self.addP4Switch(switch_name)
        self.setP4SourceAll('p4src/switch.p4')

        for host_name in self.configured_hosts:
            self.addHost(host_name)

        for left, right in self.link_pairs:
            self.addLink(left, right)

        self.mixed()

    def _activate_empty_rule_files(self):
        self._write_json(self.runtime_rules_path, [])
        self._write_json(self.runtime_behavior_pool_path, [])
        initialize_semantic_runtime(
            self.runtime_semantic_policy_path,
            self.runtime_semantic_state_path,
            self.runtime_semantic_history_path,
            [],
        )

    def _write_preview_topology_file(self):
        preview_lines = [f'({left}, {right})' for left, right in self.link_pairs]
        self._write_text(self.runtime_topo_txt_path, '\n'.join(preview_lines) + '\n')

    def _sync_runtime_topology_metadata(self):
        copy_text_file('topology.json', self.runtime_topology_path)

    def _write_json(self, output_path, payload):
        atomic_write_json(output_path, payload, ensure_ascii=False, indent=2)

    def _write_text(self, output_path, content):
        atomic_write_text(output_path, content)

    def _switch_number(self, switch_name):
        match = re.search(r'(\d+)$', switch_name)
        if match:
            return int(match.group(1))
        return self.switch_order[switch_name]

    def _thrift_port(self, switch_name):
        return 9089 + self.switch_order[switch_name]

    def _build_port_map(self, switch_name):
        port_map = {}
        current_switch = self.net.get(switch_name)
        for interface in current_switch.intfList():
            if interface.name == 'lo' or interface.link is None:
                continue
            peer = interface.link.intf2 if interface.link.intf1 == interface else interface.link.intf1
            peer_node = getattr(peer, 'node', None)
            if peer_node is None:
                continue
            match = re.search(r'eth(\d+)$', interface.name)
            if not match:
                continue
            port_map[peer_node.name] = int(match.group(1))
        return port_map

    def _switch_graph(self):
        return self.graph.subgraph(self.configured_switches).copy()

    def _load_intent_overrides(self, host_runtime):
        intent_path = os.path.join('generated', 'intent.json')
        if not os.path.exists(intent_path):
            return {}

        try:
            with open(intent_path, 'r', encoding='utf-8') as file_obj:
                intent_payload = json.load(file_obj)
        except Exception:
            return {}

        overrides = {}
        for flow in intent_payload.get('flows', []):
            src_host = flow.get('src')
            dst_host = flow.get('dst')
            if src_host not in host_runtime or dst_host not in host_runtime:
                continue

            src_ip = host_runtime[src_host]['ip']
            dst_ip = host_runtime[dst_host]['ip']
            overrides[f'{src_ip}-{dst_ip}'] = {
                'src_host': src_host,
                'dst_host': dst_host,
                'must_pass': [node for node in flow.get('must_pass', []) if node in self.configured_switches],
                'avoid': [node for node in flow.get('avoid', []) if node in self.configured_switches],
                'priority': flow.get('priority', 'shortest') or 'shortest',
                'backup_level': flow.get('backup_level', 1),
                'preferred_path': [node for node in flow.get('preferred_path', []) if node in self.configured_switches],
                'enabled_paths': [
                    [node for node in path if node in self.configured_switches]
                    for path in flow.get('enabled_paths', [])
                    if isinstance(path, list)
                ],
                'max_degraded_packets': flow.get('max_degraded_packets'),
                'max_state_changes': flow.get('max_state_changes'),
                'require_primary_recovery': flow.get('require_primary_recovery', True),
            }

        return overrides

    def _discover_switch_paths(self, src_host, dst_host, flow_override=None):
        flow_override = flow_override or {}
        src_switch = self.host_attachments[src_host]
        dst_switch = self.host_attachments[dst_host]
        if src_switch == dst_switch:
            return [[src_switch]]

        switch_graph = self._switch_graph()
        must_pass = set(flow_override.get('must_pass', []))
        avoid = set(flow_override.get('avoid', []))
        preferred_path = flow_override.get('preferred_path', [])
        preferred_candidate = preferred_path if self._is_valid_switch_path(preferred_path, src_switch, dst_switch) else None
        candidate_limit = 6

        discovered_paths = []
        seen_paths = set()
        for path in nx.shortest_simple_paths(switch_graph, src_switch, dst_switch):
            if avoid and any(node in avoid for node in path):
                continue
            if must_pass and not must_pass.issubset(set(path)):
                continue

            signature = tuple(path)
            if signature in seen_paths:
                continue

            seen_paths.add(signature)
            discovered_paths.append(path)
            if len(discovered_paths) >= candidate_limit:
                break

        if not discovered_paths:
            fallback_paths = []
            fallback_seen = set()
            if preferred_candidate:
                fallback_paths.append(preferred_candidate)
                fallback_seen.add(tuple(preferred_candidate))

            for path in nx.shortest_simple_paths(switch_graph, src_switch, dst_switch):
                signature = tuple(path)
                if signature in fallback_seen:
                    continue
                fallback_seen.add(signature)
                fallback_paths.append(path)
                if len(fallback_paths) >= candidate_limit:
                    break

            return fallback_paths[:candidate_limit]

        if preferred_candidate:
            discovered_paths = [preferred_candidate] + [path for path in discovered_paths if path != preferred_candidate]

        return discovered_paths[:candidate_limit]

    def _is_valid_switch_path(self, switch_path, src_switch, dst_switch):
        if not isinstance(switch_path, list) or not switch_path:
            return False
        if switch_path[0] != src_switch or switch_path[-1] != dst_switch:
            return False
        if any(node not in self.configured_switches for node in switch_path):
            return False
        if len(set(switch_path)) != len(switch_path):
            return False
        return all(self.graph.has_edge(left, right) for left, right in zip(switch_path, switch_path[1:]))

    def _candidate_switch_paths(self, src_host, dst_host, flow_override=None):
        flow_override = flow_override or {}
        src_switch = self.host_attachments[src_host]
        dst_switch = self.host_attachments[dst_host]
        available_paths = self._discover_switch_paths(src_host, dst_host, flow_override)
        if not available_paths:
            return []

        preferred_path = flow_override.get('preferred_path', [])
        preferred_candidate = preferred_path if self._is_valid_switch_path(preferred_path, src_switch, dst_switch) else None
        available_signatures = {tuple(path) for path in available_paths}

        enabled_paths = []
        seen_enabled = set()
        for path in flow_override.get('enabled_paths', []):
            if not self._is_valid_switch_path(path, src_switch, dst_switch):
                continue

            signature = tuple(path)
            if signature not in available_signatures or signature in seen_enabled:
                continue

            seen_enabled.add(signature)
            enabled_paths.append(path)

        if enabled_paths:
            if preferred_candidate and tuple(preferred_candidate) in seen_enabled:
                enabled_paths = [preferred_candidate] + [path for path in enabled_paths if path != preferred_candidate]
            return enabled_paths[:5]

        try:
            backup_level = max(0, int(flow_override.get('backup_level', 1)))
        except (TypeError, ValueError):
            backup_level = 1
        max_paths = min(max(backup_level + 1, 2), 5)
        priority = flow_override.get('priority', 'shortest') or 'shortest'

        discovered_paths = available_paths
        primary_path = discovered_paths[0]
        if priority == 'load_balance' and len(discovered_paths) > 1:
            primary_edges = set(zip(primary_path, primary_path[1:]))

            def sort_key(path):
                if path == primary_path:
                    return (-1, len(path), tuple(path))
                path_edges = set(zip(path, path[1:]))
                overlap = len(primary_edges & path_edges)
                return (overlap, len(path), tuple(path))

            backups = sorted(discovered_paths[1:], key=sort_key)
            return ([primary_path] + backups)[:max_paths]

        return discovered_paths[:max_paths]

    def _format_switch_command(self, dst_ip, ingress_port, dst_mac, egress_port):
        return (
            f'table_add MyIngress.ipv4_lpm MyIngress.ipv4_forward '
            f'{dst_ip}/32 {ingress_port} => {dst_mac} {egress_port}'
        )

    def _seed_default_switch_entries(self, switch_graph, host_runtime):
        command_entries = {switch_name: {} for switch_name in self.configured_switches}

        for dst_host, dst_info in host_runtime.items():
            for switch_name in self.configured_switches:
                port_map = self._build_port_map(switch_name)
                if not port_map:
                    continue

                if switch_name == dst_info['access_switch']:
                    next_hop = dst_host
                else:
                    switch_path = nx.shortest_path(switch_graph, switch_name, dst_info['access_switch'])
                    next_hop = switch_path[1]

                if next_hop not in port_map:
                    raise RuntimeError(f'{switch_name} 到 {next_hop} 的端口映射不存在，无法生成流表。')

                egress_port = port_map[next_hop]
                for ingress_port in sorted(port_map.values()):
                    command_entries[switch_name][(dst_info['ip'], ingress_port)] = {
                        'dst_ip': dst_info['ip'],
                        'ingress_port': ingress_port,
                        'dst_mac': dst_info['mac'],
                        'egress_port': egress_port,
                    }

        return command_entries

    def _override_primary_path_entries(self, command_entries, host_runtime, src_host, dst_host, switch_path):
        dst_info = host_runtime[dst_host]

        for index, switch_name in enumerate(switch_path):
            port_map = self._build_port_map(switch_name)
            previous_hop = src_host if index == 0 else switch_path[index - 1]
            next_hop = dst_host if index == len(switch_path) - 1 else switch_path[index + 1]

            if previous_hop not in port_map or next_hop not in port_map:
                raise RuntimeError(
                    f'{switch_name} 缺少 {previous_hop} -> {next_hop} 的端口映射，无法应用预期路径。'
                )

            ingress_port = port_map[previous_hop]
            egress_port = port_map[next_hop]
            command_entries[switch_name][(dst_info['ip'], ingress_port)] = {
                'dst_ip': dst_info['ip'],
                'ingress_port': ingress_port,
                'dst_mac': dst_info['mac'],
                'egress_port': egress_port,
            }

    def _path_to_numbers(self, switch_path):
        return [self._switch_number(switch_name) for switch_name in switch_path]

    def _build_dynamic_artifacts(self):
        switch_graph = self._switch_graph()
        runtime_topology = Topology(self.runtime_topology_path)
        host_runtime = self._host_runtime()
        flow_overrides = self._load_intent_overrides(host_runtime)
        switch_command_entries = self._seed_default_switch_entries(switch_graph, host_runtime)

        rules = []
        behavior_pool = []
        for src_host in self.configured_hosts:
            for dst_host in self.configured_hosts:
                if src_host == dst_host:
                    continue

                src_ip = host_runtime[src_host]['ip']
                dst_ip = host_runtime[dst_host]['ip']
                flow_key = f'{src_ip}-{dst_ip}'
                flow_override = flow_overrides.get(flow_key, {
                    'src_host': src_host,
                    'dst_host': dst_host,
                    'must_pass': [],
                    'avoid': [],
                    'priority': 'shortest',
                    'backup_level': 1,
                    'enabled_paths': [],
                })

                path_catalog = self._discover_switch_paths(src_host, dst_host, flow_override)
                candidate_paths = self._candidate_switch_paths(src_host, dst_host, flow_override)
                primary_path = candidate_paths[0]
                self._override_primary_path_entries(switch_command_entries, host_runtime, src_host, dst_host, primary_path)
                rules.append({
                    'src_ip': src_ip,
                    'dst_ip': dst_ip,
                    'path': self._path_to_numbers(primary_path),
                })

                behaviors = []
                for index, switch_path in enumerate(candidate_paths):
                    behaviors.append({
                        'index': index,
                        'path': self._path_to_numbers(switch_path),
                        'switch_path': list(switch_path),
                        'level': 'primary' if index == 0 else 'backup',
                        'tier': index,
                        'label': '命中主路径' if index == 0 else f'命中第{index}级备份路径',
                    })

                behavior_pool.append({
                    'src_ip': src_ip,
                    'dst_ip': dst_ip,
                    'src_host': src_host,
                    'dst_host': dst_host,
                    'enabled_paths': [list(path) for path in flow_override.get('enabled_paths', []) if isinstance(path, list)],
                    'path_catalog': [
                        {
                            'index': index,
                            'path': self._path_to_numbers(switch_path),
                            'switch_path': list(switch_path),
                            'label': '系统推荐主路径' if index == 0 else f'候选路径 {index}',
                        }
                        for index, switch_path in enumerate(path_catalog)
                    ],
                    'behaviors': behaviors,
                })

        self._write_json(self.runtime_rules_path, rules)
        self._write_json(self.runtime_behavior_pool_path, behavior_pool)
        refresh_semantic_runtime(
            self.runtime_semantic_policy_path,
            self.runtime_semantic_state_path,
            self.runtime_semantic_history_path,
            behavior_pool,
            flow_overrides=flow_overrides,
            preserve_existing=True,
            reset_runtime_state=True,
        )

        switch_commands = {}
        for switch_name in self.configured_switches:
            command_entries = switch_command_entries.get(switch_name, {})
            commands = [
                self._format_switch_command(
                    entry['dst_ip'],
                    entry['ingress_port'],
                    entry['dst_mac'],
                    entry['egress_port'],
                )
                for entry in sorted(
                    command_entries.values(),
                    key=lambda item: (item['dst_ip'], item['ingress_port'], item['egress_port']),
                )
            ]
            commands.append(
                f'table_set_default MyEgress.tbl_prime prime_multiply {runtime_topology.get_prime(switch_name)}'
            )
            commands.append(
                f'table_set_default MyEgress.swtrace add_swtrace {self._switch_number(switch_name)}'
            )
            switch_commands[switch_name] = commands
            command_file_path = os.path.join(self.switch_command_dir, f'{switch_name}-commands.txt')
            self._write_text(command_file_path, '\n'.join(commands) + '\n')

        self._switch_commands = switch_commands

    def clean_and_compile(self):
        debug('Cleanup old files and processes...\n')
        self.cleanup()

        debug('Auto configuration of not configured interfaces...\n')
        self.auto_assignment()
        prepare_p4_build_outputs('p4src/switch.p4')

        try:
            info('Compiling P4 files...\n')
            self.compile()
            output('P4 Files compiled!\n')
        except Exception:
            error('There is something wrong while compiling p4 source\n')
            return False
        self.printPortMapping()

        self.__isCompiled = True
        return True

    def startNetwork(self):
        assert self.__isCompiled

        info('Creating network...\n')
        self.net = self.module('net', topo=self, controller=None)
        output('Network created!\n')

        info('Starting network...\n')
        self.net.start()
        output('Network started!\n')

        info('Starting schedulers...\n')
        self.start_schedulers()
        output('Schedulers started correctly!\n')

        info('Saving topology to disk...\n')
        prepare_output_path('topology.json')
        self.save_topology()
        self._sync_runtime_topology_metadata()
        output('Topology saved to disk!\n')

        info('Programming hosts...\n')
        self.program_hosts()
        output('Hosts programmed correctly!\n')

        info('Refreshing topology metadata...\n')
        prepare_output_path('topology.json')
        self.save_topology()
        self._sync_runtime_topology_metadata()
        output('Topology metadata refreshed!\n')

        info('Generating routing artifacts...\n')
        self._build_dynamic_artifacts()
        output('Routing artifacts generated!\n')

        info('Executing scripts...\n')
        self.exec_scripts()
        output('All scripts executed correctly!\n')

        info('Distributing tasks...\n')
        self.distribute_tasks()
        output('All tasks distributed correctly!\n')

        if self.cli_enabled:
            self.start_net_cli()
            self.stopNetwork()

        self.__isNetworkStart = True

    def program_switches(self):
        assert self.__isNetworkStart and self.__isCompiled

        try:
            self._build_dynamic_artifacts()
            info('Programming switches...\n')
            for switch_name in self.configured_switches:
                commands = self._switch_commands.get(switch_name, [])
                if not commands:
                    continue
                thrift_port = self._thrift_port(switch_name)
                cli_script = 'table_clear MyIngress.ipv4_lpm\n' + '\n'.join(commands)
                self.net.get(switch_name).cmd(
                    f"cat <<'EOF' | simple_switch_CLI --thrift-port {thrift_port}\n{cli_script}\nEOF"
                )
            output('Switches programmed correctly!\n')
        except Exception as exc:
            error(f"There is something wrong while programming switches. Detailed info is as followed:{exc}\n")
            return False
        return True

    def send(self, src_host, dst_host):
        assert self.__isNetworkStart and self.__isCompiled
        dst_shell = self.net.get(dst_host)
        src_shell = self.net.get(src_host)
        command_output = ''

        try:
            info('executing receive.py...\n')
            command_output = dst_shell.cmd(f'{self._runtime_env_prefix()} python3 topo/receive.py &')
        except Exception as exc:
            error(f"fail to launch receive.py on {dst_host}. Detailed info is as follow:{exc}\n")
            return False

        if command_output:
            info('successful execution:')
            info(command_output)
        time.sleep(3)

        try:
            info('executing send.py...\n')
            command_output = src_shell.cmd(f'python3 topo/send.py --ip {dst_shell.IP()} --m tag')
        except Exception as exc:
            error(f"fail to launch send.py on {src_host}. Detailed info is as follow:{exc}\n")
            return False
        if command_output:
            info('successful execution:')
            info(command_output)
        time.sleep(1)

        if not os.path.isfile('res.json'):
            return False

        with open('res.json', 'r', encoding='utf-8') as f:
            res = json.load(f)

        res['stop_receiving'] = False

        try:
            dst_shell.cmd("pkill -f 'python3 ./topo/receive.py'")
            info('receive.py killed.\n')
            res['stop_receiving'] = True
        except Exception as exc:
            error(f'fail to kill receive.py. Detailed info is as follow:{exc}\n')

        with open('res.json', 'w', encoding='utf-8') as f:
            json.dump(res, f, indent=4)

    def send_vbp(self, src_host, dst_host):
        assert self.__isNetworkStart and self.__isCompiled
        dst_shell = self.net.get(dst_host)
        src_shell = self.net.get(src_host)
        command_output = ''

        try:
            info('executing receive_vbp.py...\n')
            command_output = dst_shell.cmd(f'{self._runtime_env_prefix(include_behavior_pool=True)} python3 topo/receive_vbp.py &')
        except Exception as exc:
            error(f"fail to launch receive_vbp.py on {dst_host}. Detailed info is as follow:{exc}\n")
            return False

        if command_output:
            info('successful execution:')
            info(command_output)
        time.sleep(3)

        try:
            info('executing send.py in VBP mode...\n')
            command_output = src_shell.cmd(f'python3 topo/send.py --ip {dst_shell.IP()} --m tag')
        except Exception as exc:
            error(f"fail to launch send.py on {src_host}. Detailed info is as follow:{exc}\n")
            return False
        if command_output:
            info('successful execution:')
            info(command_output)
        time.sleep(1)

        if not os.path.isfile('res.json'):
            return False

        with open('res.json', 'r', encoding='utf-8') as f:
            res = json.load(f)

        res['stop_receiving'] = False

        try:
            dst_shell.cmd("pkill -f 'python3 topo/receive_vbp.py'")
            info('receive_vbp.py killed.\n')
            res['stop_receiving'] = True
        except Exception as exc:
            error(f'fail to kill receive_vbp.py. Detailed info is as follow:{exc}\n')

        with open('res.json', 'w', encoding='utf-8') as f:
            json.dump(res, f, indent=4)

    def _runtime_env_prefix(self, include_behavior_pool=False):
        runtime_env = {
            'RUNTIME_TOPOLOGY_JSON_PATH': self.runtime_topology_path,
            'RUNTIME_RULES_JSON_PATH': self.runtime_rules_path,
            'RUNTIME_SEMANTIC_POLICY_PATH': self.runtime_semantic_policy_path,
            'RUNTIME_SEMANTIC_STATE_PATH': self.runtime_semantic_state_path,
            'RUNTIME_SEMANTIC_HISTORY_PATH': self.runtime_semantic_history_path,
        }
        if include_behavior_pool:
            runtime_env['RUNTIME_BEHAVIOR_POOL_PATH'] = self.runtime_behavior_pool_path

        return ' '.join(
            f'{key}={shlex.quote(value)}'
            for key, value in runtime_env.items()
        )

    def modify_switch(self, swid, dst_host, dst_swid):
        assert self.__isNetworkStart and self.__isCompiled
        current_switch = self.net.get(swid)
        destination_switch = self.net.get(dst_swid)
        destination_port = None

        for interface in current_switch.intfList():
            if interface.name == 'lo':
                continue
            peer = interface.link.intf2 if interface.link.intf1 == interface else interface.link.intf1
            if peer.node == destination_switch:
                destination_port = re.findall('eth(.*)', interface.name)[0]

        if destination_port is None:
            info(f"These two switches are not neighbours! You can't modify switch {swid}.\n")
            return False

        thrift_port = self._thrift_port(swid)
        host = self.net.get(dst_host)
        try:
            command_output = current_switch.cmd(
                f'echo "table_dump MyIngress.ipv4_lpm" | simple_switch_CLI --thrift-port {thrift_port}'
            )
        except Exception as exc:
            error(f'Execution of your command failed. Detailed info is as follow:{exc}\n')
            return False

        handle = None
        hex_ip = hex_IP(host.IP())
        for line in command_output.strip().split('\n'):
            if 'Dumping entry' in line:
                handle = int(line[16:], 16)
            if hex_ip in line:
                if handle is None:
                    continue
                modify_command = (
                    f'echo "table_modify ipv4_lpm ipv4_forward {handle} {host.MAC()} {destination_port}" '
                    f'| simple_switch_CLI --thrift-port {thrift_port}'
                )
                result = current_switch.cmd(modify_command)
                handle = None
                info('modify results:\n' + result + '\n')

        return True

    def stopNetwork(self):
        try:
            super().stopNetwork()
        finally:
            self.__isNetworkStart = False