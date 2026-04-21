import os


USER_TOPOLOGY_DIR = os.path.join('topo', 'user_topology')
USER_TOPOLOGY_RUNTIME_DIR = os.path.join(USER_TOPOLOGY_DIR, 'runtime')


def _with_root(root_path, relative_path):
    if root_path:
        return os.path.join(root_path, relative_path)
    return relative_path


def get_user_topology_dir(root_path=None):
    return _with_root(root_path, USER_TOPOLOGY_DIR)


def get_user_topology_runtime_dir(root_path=None):
    return _with_root(root_path, USER_TOPOLOGY_RUNTIME_DIR)


def get_user_uploaded_topology_path(root_path=None):
    return _with_root(root_path, os.path.join(USER_TOPOLOGY_DIR, 'uploaded_topology.json'))


def get_user_network_script_path(root_path=None):
    return _with_root(root_path, os.path.join(USER_TOPOLOGY_DIR, 'network.py'))


def get_user_runtime_topology_path(root_path=None):
    return _with_root(root_path, os.path.join(USER_TOPOLOGY_RUNTIME_DIR, 'topology.json'))


def get_user_runtime_rules_path(root_path=None):
    return _with_root(root_path, os.path.join(USER_TOPOLOGY_RUNTIME_DIR, 'rules.json'))


def get_user_runtime_behavior_pool_path(root_path=None):
    return _with_root(root_path, os.path.join(USER_TOPOLOGY_RUNTIME_DIR, 'behavior_pool.json'))


def get_user_runtime_semantic_policy_path(root_path=None):
    return _with_root(root_path, os.path.join(USER_TOPOLOGY_RUNTIME_DIR, 'semantic_policy.json'))


def get_user_runtime_semantic_state_path(root_path=None):
    return _with_root(root_path, os.path.join(USER_TOPOLOGY_RUNTIME_DIR, 'semantic_state.json'))


def get_user_runtime_semantic_history_path(root_path=None):
    return _with_root(root_path, os.path.join(USER_TOPOLOGY_RUNTIME_DIR, 'semantic_history.json'))


def get_user_runtime_topo_txt_path(root_path=None):
    return _with_root(root_path, os.path.join(USER_TOPOLOGY_RUNTIME_DIR, 'topo.txt'))


def get_user_runtime_switch_command_dir(root_path=None):
    return _with_root(root_path, os.path.join(USER_TOPOLOGY_RUNTIME_DIR, 'switch_commands'))


def ensure_user_topology_dirs(root_path=None):
    os.makedirs(get_user_topology_dir(root_path), exist_ok=True)
    os.makedirs(get_user_topology_runtime_dir(root_path), exist_ok=True)
    os.makedirs(get_user_runtime_switch_command_dir(root_path), exist_ok=True)