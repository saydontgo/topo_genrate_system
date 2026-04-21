from p4utils.mininetlib.log import warning


_current_topology = None


def get_current_topology():
    return _current_topology


def switch_current_topology(new_topology):
    global _current_topology

    previous_topology = _current_topology
    if previous_topology is not None and previous_topology is not new_topology and hasattr(previous_topology, 'stopNetwork'):
        try:
            previous_topology.stopNetwork()
        except Exception as exc:
            warning(f"切换拓扑时停止旧拓扑失败，已忽略: {exc}\n")

    _current_topology = new_topology
    return _current_topology