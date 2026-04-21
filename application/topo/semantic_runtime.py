import copy
import json
import os
import time

try:
    from .runtime_files import atomic_write_json
except ImportError:
    from runtime_files import atomic_write_json


SEMANTIC_TAGS = {
    'flow_state': 'STATE_VAR',
    'packet_count': 'COUNTER',
    'behavior_index': 'INDEX',
    'path_hops': 'RESOURCE',
    'path_legal': 'FLAG',
}

VIOLATION_TYPES = {
    'BOUND_VIOLATION',
    'INVALID_TRANSITION',
    'UNINITIALIZED_USE',
    'INCONSISTENT_STATE',
    'RESOURCE_OVERFLOW',
}

DEFAULT_MAX_PACKETS = 64
DEFAULT_MAX_DEGRADED_PACKETS = 3
DEFAULT_MAX_STATE_CHANGES = 6
MAX_HISTORY_ITEMS = 40


def make_flow_key(src_ip, dst_ip):
    return f'{src_ip}-{dst_ip}'


def _read_json(path, default_value):
    if not path or not os.path.exists(path):
        return default_value

    with open(path, 'r', encoding='utf-8') as file_obj:
        return json.load(file_obj)


def _confidence(value):
    return round(value, 2)


def _coerce_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on'}
    return bool(value)


def _default_max_degraded_packets(allowed_behavior_count):
    return max(DEFAULT_MAX_DEGRADED_PACKETS, max(1, allowed_behavior_count))


def _default_max_state_changes(allowed_behavior_count):
    return max(DEFAULT_MAX_STATE_CHANGES, max(2, allowed_behavior_count * 3))


def build_yaml_preview(invariants):
    lines = ['invariants:']
    for invariant in invariants:
        lines.append(f"  - var: {invariant['var']}")
        lines.append(f"    type: {invariant['type']}")
        if 'suggested_bound' in invariant:
            lines.append(f"    suggested_bound: {invariant['suggested_bound']}")
        if 'rule' in invariant:
            lines.append(f"    rule: \"{invariant['rule']}\"")
        lines.append(f"    confidence: {invariant.get('confidence', '')}")
    return '\n'.join(lines)


def _coerce_int(value, field_name, minimum=None):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{field_name} 必须是整数') from exc

    if minimum is not None and parsed < minimum:
        raise ValueError(f'{field_name} 必须大于等于 {minimum}')

    return parsed


def normalize_allowed_transitions(transitions):
    if not isinstance(transitions, list) or not transitions:
        raise ValueError('allowed_transitions 必须是非空数组')

    normalized = []
    seen = set()
    for index, transition in enumerate(transitions, start=1):
        if not isinstance(transition, dict):
            raise ValueError(f'allowed_transitions 第 {index} 项必须是对象')

        from_state = str(transition.get('from', '')).strip()
        to_state = str(transition.get('to', '')).strip()
        if not from_state or not to_state:
            raise ValueError(f'allowed_transitions 第 {index} 项必须同时包含 from 和 to')

        transition_key = (from_state, to_state)
        if transition_key in seen:
            continue

        seen.add(transition_key)
        normalized.append({
            'from': from_state,
            'to': to_state,
        })

    return normalized


def normalize_invariants(invariants):
    if not isinstance(invariants, list) or not invariants:
        raise ValueError('invariants 必须是非空数组')

    normalized = []
    for index, invariant in enumerate(invariants, start=1):
        if not isinstance(invariant, dict):
            raise ValueError(f'invariants 第 {index} 项必须是对象')

        var_name = str(invariant.get('var', '')).strip()
        invariant_type = str(invariant.get('type', '')).strip()
        if not var_name or not invariant_type:
            raise ValueError(f'invariants 第 {index} 项必须包含 var 和 type')

        normalized_item = {
            key: value
            for key, value in invariant.items()
            if key not in {'var', 'type', 'suggested_bound', 'rule', 'confidence'}
        }
        normalized_item['var'] = var_name
        normalized_item['type'] = invariant_type

        if invariant.get('suggested_bound') not in (None, ''):
            normalized_item['suggested_bound'] = _coerce_int(invariant.get('suggested_bound'), f'invariants[{index}].suggested_bound')

        rule = str(invariant.get('rule', '')).strip()
        if rule:
            normalized_item['rule'] = rule

        confidence = invariant.get('confidence')
        if confidence not in (None, ''):
            try:
                normalized_item['confidence'] = round(min(max(float(confidence), 0.0), 1.0), 2)
            except (TypeError, ValueError) as exc:
                raise ValueError(f'invariants[{index}].confidence 必须是数值') from exc

        normalized.append(normalized_item)

    return normalized


def _upsert_invariant(invariants, var_name, invariant_type, *, suggested_bound=None, rule=None, confidence=None):
    target = None
    for invariant in invariants:
        if invariant.get('var') == var_name:
            target = invariant
            break

    if target is None:
        target = {
            'var': var_name,
            'type': invariant_type,
        }
        invariants.append(target)

    target['type'] = invariant_type
    if suggested_bound is None:
        target.pop('suggested_bound', None)
    else:
        target['suggested_bound'] = suggested_bound

    if rule:
        target['rule'] = rule

    if confidence is not None:
        target['confidence'] = confidence


def merge_user_flow_policy(
    flow_policy,
    max_packets=None,
    max_hops=None,
    invariants=None,
    allowed_transitions=None,
    max_degraded_packets=None,
    max_state_changes=None,
    require_primary_recovery=None,
):
    updated_flow = copy.deepcopy(flow_policy)
    allowed_behavior_count = _coerce_int(updated_flow.get('allowed_behavior_count', 1), 'allowed_behavior_count', minimum=1)

    if max_packets is None:
        max_packets = updated_flow.get('max_packets', DEFAULT_MAX_PACKETS)
    if max_hops is None:
        max_hops = updated_flow.get('max_hops', 0)
    if max_degraded_packets is None:
        max_degraded_packets = updated_flow.get('max_degraded_packets', _default_max_degraded_packets(allowed_behavior_count))
    if max_state_changes is None:
        max_state_changes = updated_flow.get('max_state_changes', _default_max_state_changes(allowed_behavior_count))
    if require_primary_recovery is None:
        require_primary_recovery = updated_flow.get('require_primary_recovery', allowed_behavior_count > 1)

    normalized_max_packets = _coerce_int(max_packets, 'max_packets', minimum=1)
    normalized_max_hops = _coerce_int(max_hops, 'max_hops', minimum=0)
    normalized_max_degraded_packets = _coerce_int(max_degraded_packets, 'max_degraded_packets', minimum=1)
    normalized_max_state_changes = _coerce_int(max_state_changes, 'max_state_changes', minimum=1)
    normalized_require_primary_recovery = _coerce_bool(require_primary_recovery)
    normalized_invariants = normalize_invariants(invariants if invariants is not None else updated_flow.get('invariants', []))
    normalized_transitions = normalize_allowed_transitions(
        allowed_transitions if allowed_transitions is not None else updated_flow.get('allowed_transitions', [])
    )

    _upsert_invariant(
        normalized_invariants,
        'packet_count',
        'COUNTER',
        suggested_bound=normalized_max_packets,
        rule=f'0 <= packet_count <= {normalized_max_packets}',
        confidence=_confidence(0.88),
    )
    _upsert_invariant(
        normalized_invariants,
        'behavior_index',
        'INDEX',
        suggested_bound=max(allowed_behavior_count - 1, 0),
        rule=f'0 <= behavior_index < {allowed_behavior_count}',
        confidence=_confidence(0.91),
    )
    _upsert_invariant(
        normalized_invariants,
        'flow_state',
        'STATE_VAR',
        rule='(prev_state, current_state) in AllowedTransitions',
        confidence=_confidence(0.93),
    )
    _upsert_invariant(
        normalized_invariants,
        'path_hops',
        'RESOURCE',
        suggested_bound=normalized_max_hops,
        rule=f'path_hops <= {normalized_max_hops}',
        confidence=_confidence(0.79),
    )
    _upsert_invariant(
        normalized_invariants,
        'degraded_packets',
        'COUNTER',
        suggested_bound=normalized_max_degraded_packets,
        rule=f'0 <= degraded_packets <= {normalized_max_degraded_packets}',
        confidence=_confidence(0.82),
    )
    _upsert_invariant(
        normalized_invariants,
        'state_change_count',
        'COUNTER',
        suggested_bound=normalized_max_state_changes,
        rule=f'0 <= state_change_count <= {normalized_max_state_changes}',
        confidence=_confidence(0.8),
    )
    _upsert_invariant(
        normalized_invariants,
        'recovery_to_primary',
        'STATE_VAR',
        rule=(
            f'backup state must recover to PRIMARY within {normalized_max_degraded_packets} packets'
            if normalized_require_primary_recovery else
            'backup state recovery is advisory'
        ),
        confidence=_confidence(0.76),
    )

    updated_flow['max_packets'] = normalized_max_packets
    updated_flow['max_hops'] = normalized_max_hops
    updated_flow['max_degraded_packets'] = normalized_max_degraded_packets
    updated_flow['max_state_changes'] = normalized_max_state_changes
    updated_flow['require_primary_recovery'] = normalized_require_primary_recovery
    updated_flow['invariants'] = normalized_invariants
    updated_flow['allowed_transitions'] = normalized_transitions
    updated_flow['yaml_preview'] = build_yaml_preview(normalized_invariants)
    updated_flow['customized'] = True
    updated_flow['customized_at'] = int(time.time())
    return updated_flow


def _state_name_for_index(index):
    if index == 0:
        return 'PRIMARY'
    return f'BACKUP_{index}'


def _tier_name(index):
    if index == 0:
        return '主路径'
    return f'第{index}级备份路径'


def _transition_pairs(allowed_behavior_count):
    legal_states = [_state_name_for_index(index) for index in range(allowed_behavior_count)]
    transitions = []
    for state in legal_states:
        transitions.append({'from': 'INIT', 'to': state})

    for left_state in legal_states:
        transitions.append({'from': left_state, 'to': left_state})
        for right_state in legal_states:
            if left_state == right_state:
                continue
            transitions.append({'from': left_state, 'to': right_state})

    return transitions


def rebuild_semantic_policy(behavior_pool_items, flow_overrides=None, existing_policy=None, default_max_packets=DEFAULT_MAX_PACKETS):
    rebuilt_policy = build_semantic_policy(
        behavior_pool_items,
        flow_overrides=flow_overrides,
        default_max_packets=default_max_packets,
    )

    if not existing_policy:
        return rebuilt_policy

    existing_flows = {
        flow.get('flow_id'): flow
        for flow in existing_policy.get('flows', [])
        if isinstance(flow, dict) and flow.get('flow_id')
    }

    for index, flow in enumerate(rebuilt_policy.get('flows', [])):
        existing_flow = existing_flows.get(flow.get('flow_id'))
        if not existing_flow:
            continue

        if existing_flow.get('customized'):
            merged_flow = merge_user_flow_policy(
                flow,
                max_packets=existing_flow.get('max_packets'),
                max_hops=existing_flow.get('max_hops'),
                invariants=existing_flow.get('invariants'),
                allowed_transitions=existing_flow.get('allowed_transitions'),
                max_degraded_packets=existing_flow.get('max_degraded_packets'),
                max_state_changes=existing_flow.get('max_state_changes'),
                require_primary_recovery=existing_flow.get('require_primary_recovery'),
            )
            if existing_flow.get('customized_at'):
                merged_flow['customized_at'] = existing_flow['customized_at']
            rebuilt_policy['flows'][index] = merged_flow

    rebuilt_policy['updated_at'] = int(time.time())
    return rebuilt_policy


def refresh_semantic_runtime(policy_path, state_path, history_path, behavior_pool_items, flow_overrides=None, preserve_existing=True, reset_runtime_state=False):
    existing_policy = _read_json(policy_path, {'flows': []}) if preserve_existing else None
    policy = rebuild_semantic_policy(
        behavior_pool_items,
        flow_overrides=flow_overrides,
        existing_policy=existing_policy,
    )
    atomic_write_json(policy_path, policy, ensure_ascii=False, indent=2)

    if reset_runtime_state:
        atomic_write_json(state_path, {'flows': {}, 'updated_at': int(time.time())}, ensure_ascii=False, indent=2)
        atomic_write_json(history_path, [], ensure_ascii=False, indent=2)

    return policy


def build_semantic_policy(behavior_pool_items, flow_overrides=None, default_max_packets=DEFAULT_MAX_PACKETS):
    flow_overrides = flow_overrides or {}
    flows = []

    for item in behavior_pool_items:
        src_ip = item.get('src_ip', '')
        dst_ip = item.get('dst_ip', '')
        if not src_ip or not dst_ip:
            continue

        flow_key = make_flow_key(src_ip, dst_ip)
        override = flow_overrides.get(flow_key, {})
        behaviors = item.get('behaviors', [])
        normalized_behaviors = []
        for index, behavior in enumerate(behaviors):
            path = behavior.get('path', [])
            normalized_behaviors.append({
                'index': index,
                'level': behavior.get('level', 'primary' if index == 0 else 'backup'),
                'tier': behavior.get('tier', index),
                'label': behavior.get('label') or f'命中{_tier_name(index)}',
                'path': path,
                'switch_path': behavior.get('switch_path', [f's{node}' for node in path]),
                'path_hops': len(path),
                'prime_product': behavior.get('prime_product'),
            })

        active_signatures = {tuple(behavior.get('switch_path', [])) for behavior in normalized_behaviors}
        normalized_catalog = []
        raw_catalog = item.get('path_catalog', [])
        for index, candidate in enumerate(raw_catalog):
            if isinstance(candidate, dict):
                path = candidate.get('path', [])
                switch_path = candidate.get('switch_path', [f's{node}' for node in path])
                label = candidate.get('label') or f'候选路径 {index + 1}'
            elif isinstance(candidate, list):
                switch_path = [str(node) for node in candidate]
                path = [int(str(node)[1:]) for node in switch_path if str(node).startswith('s')]
                label = f'候选路径 {index + 1}'
            else:
                continue

            normalized_catalog.append({
                'index': index,
                'label': label,
                'path': path,
                'switch_path': switch_path,
                'active': tuple(switch_path) in active_signatures,
            })

        if not normalized_catalog:
            normalized_catalog = [
                {
                    'index': behavior['index'],
                    'label': behavior.get('label') or f'候选路径 {behavior["index"] + 1}',
                    'path': list(behavior.get('path', [])),
                    'switch_path': list(behavior.get('switch_path', [])),
                    'active': True,
                }
                for behavior in normalized_behaviors
            ]

        requested_backup_level = override.get('backup_level', 1)
        try:
            requested_backup_level = int(requested_backup_level)
        except (TypeError, ValueError):
            requested_backup_level = 1
        requested_backup_level = max(0, requested_backup_level)

        allowed_behavior_count = max(1, min(len(normalized_behaviors), requested_backup_level + 1))
        max_hops = max((behavior['path_hops'] for behavior in normalized_behaviors[:allowed_behavior_count]), default=0)
        max_packets = override.get('max_packets', default_max_packets)
        try:
            max_packets = max(1, int(max_packets))
        except (TypeError, ValueError):
            max_packets = default_max_packets
        max_degraded_packets = override.get('max_degraded_packets', _default_max_degraded_packets(allowed_behavior_count))
        try:
            max_degraded_packets = max(1, int(max_degraded_packets))
        except (TypeError, ValueError):
            max_degraded_packets = _default_max_degraded_packets(allowed_behavior_count)

        max_state_changes = override.get('max_state_changes', _default_max_state_changes(allowed_behavior_count))
        try:
            max_state_changes = max(1, int(max_state_changes))
        except (TypeError, ValueError):
            max_state_changes = _default_max_state_changes(allowed_behavior_count)

        require_primary_recovery = _coerce_bool(override.get('require_primary_recovery', allowed_behavior_count > 1))

        invariants = [
            {
                'var': 'packet_count',
                'type': 'COUNTER',
                'suggested_bound': max_packets,
                'rule': f'0 <= packet_count <= {max_packets}',
                'confidence': _confidence(0.88),
            },
            {
                'var': 'behavior_index',
                'type': 'INDEX',
                'suggested_bound': max(allowed_behavior_count - 1, 0),
                'rule': f'0 <= behavior_index < {allowed_behavior_count}',
                'confidence': _confidence(0.91),
            },
            {
                'var': 'flow_state',
                'type': 'STATE_VAR',
                'rule': '(prev_state, current_state) in AllowedTransitions',
                'confidence': _confidence(0.93),
            },
            {
                'var': 'path_hops',
                'type': 'RESOURCE',
                'suggested_bound': max_hops,
                'rule': f'path_hops <= {max_hops}',
                'confidence': _confidence(0.79),
            },
            {
                'var': 'degraded_packets',
                'type': 'COUNTER',
                'suggested_bound': max_degraded_packets,
                'rule': f'0 <= degraded_packets <= {max_degraded_packets}',
                'confidence': _confidence(0.82),
            },
            {
                'var': 'state_change_count',
                'type': 'COUNTER',
                'suggested_bound': max_state_changes,
                'rule': f'0 <= state_change_count <= {max_state_changes}',
                'confidence': _confidence(0.8),
            },
            {
                'var': 'recovery_to_primary',
                'type': 'STATE_VAR',
                'rule': (
                    f'backup state must recover to PRIMARY within {max_degraded_packets} packets'
                    if require_primary_recovery else
                    'backup state recovery is advisory'
                ),
                'confidence': _confidence(0.76),
            },
        ]

        flows.append({
            'flow_id': flow_key,
            'flow_scope': {
                'src_ip': src_ip,
                'dst_ip': dst_ip,
                'src_host': override.get('src_host') or item.get('src_host', ''),
                'dst_host': override.get('dst_host') or item.get('dst_host', ''),
            },
            'priority': override.get('priority', 'shortest'),
            'must_pass': override.get('must_pass', []),
            'avoid': override.get('avoid', []),
            'backup_level': requested_backup_level,
            'preferred_path': override.get('preferred_path', []),
            'enabled_paths': override.get(
                'enabled_paths',
                [list(behavior.get('switch_path', [])) for behavior in normalized_behaviors],
            ),
            'allowed_behavior_count': allowed_behavior_count,
            'max_packets': max_packets,
            'max_hops': max_hops,
            'max_degraded_packets': max_degraded_packets,
            'max_state_changes': max_state_changes,
            'require_primary_recovery': require_primary_recovery,
            'semantic_tags': dict(SEMANTIC_TAGS),
            'behaviors': normalized_behaviors,
            'path_catalog': normalized_catalog,
            'allowed_transitions': _transition_pairs(allowed_behavior_count),
            'invariants': invariants,
            'yaml_preview': build_yaml_preview(invariants),
        })

    return {
        'method': 'Flow-Aware Semantic SSA Runtime Verification (MVP)',
        'flow_key_fields': ['src_ip', 'dst_ip'],
        'violation_types': sorted(VIOLATION_TYPES),
        'semantic_tags': dict(SEMANTIC_TAGS),
        'flows': flows,
        'generated_at': int(time.time()),
    }


def initialize_semantic_runtime(policy_path, state_path, history_path, behavior_pool_items, flow_overrides=None):
    return refresh_semantic_runtime(
        policy_path,
        state_path,
        history_path,
        behavior_pool_items,
        flow_overrides=flow_overrides,
        preserve_existing=False,
        reset_runtime_state=True,
    )


class SemanticVerifier:
    def __init__(self, policy_path, state_path, history_path):
        self.policy_path = policy_path
        self.state_path = state_path
        self.history_path = history_path

        self.policy = _read_json(policy_path, {'flows': []})
        self.state = _read_json(state_path, {'flows': {}, 'updated_at': int(time.time())})
        self.history = _read_json(history_path, [])
        self.flow_policies = {
            flow['flow_id']: flow
            for flow in self.policy.get('flows', [])
            if isinstance(flow, dict) and flow.get('flow_id')
        }

    def _transition_allowed(self, previous_state, current_state, flow_policy):
        allowed_transitions = {
            (item.get('from'), item.get('to'))
            for item in flow_policy.get('allowed_transitions', [])
            if isinstance(item, dict)
        }
        return (previous_state, current_state) in allowed_transitions

    def _behavior_index(self, flow_policy, match_result, observed_path):
        if match_result and isinstance(match_result.get('index'), int):
            return match_result['index']

        behaviors = flow_policy.get('behaviors', [])
        for behavior in behaviors:
            if behavior.get('path') == observed_path:
                return behavior.get('index')
        return None

    def _current_state(self, match_result, behavior_index):
        if not match_result or not match_result.get('matched') or behavior_index is None:
            return 'ILLEGAL'
        return _state_name_for_index(behavior_index)

    def _invariant_result(self, name, passed, detail):
        return {
            'name': name,
            'passed': passed,
            'detail': detail,
        }

    def verify_observation(self, src_ip, dst_ip, observed_path, match_result=None):
        flow_key = make_flow_key(src_ip, dst_ip)
        flow_policy = self.flow_policies.get(flow_key)
        if flow_policy is None:
            fallback_policy = build_semantic_policy([{
                'src_ip': src_ip,
                'dst_ip': dst_ip,
                'behaviors': [{
                    'path': observed_path or [],
                    'level': 'primary',
                    'tier': 0,
                    'label': '自动推断主路径',
                }],
            }])
            flow_policy = fallback_policy['flows'][0]
            self.flow_policies[flow_key] = flow_policy

        flow_state = self.state.setdefault('flows', {}).setdefault(flow_key, {
            'packet_count': 0,
            'current_state': 'INIT',
            'last_path': [],
            'degraded_packets': 0,
            'state_change_count': 0,
            'consecutive_backup_packets': 0,
            'seen_primary': False,
        })

        previous_state = flow_state.get('current_state', 'INIT')
        packet_count = int(flow_state.get('packet_count', 0)) + 1
        behavior_index = self._behavior_index(flow_policy, match_result, observed_path)
        current_state = self._current_state(match_result, behavior_index)
        transition_allowed = self._transition_allowed(previous_state, current_state, flow_policy)

        allowed_behavior_count = int(flow_policy.get('allowed_behavior_count', 1))
        max_packets = int(flow_policy.get('max_packets', DEFAULT_MAX_PACKETS))
        max_hops = int(flow_policy.get('max_hops', 0))
        max_degraded_packets = int(flow_policy.get('max_degraded_packets', _default_max_degraded_packets(allowed_behavior_count)))
        max_state_changes = int(flow_policy.get('max_state_changes', _default_max_state_changes(allowed_behavior_count)))
        require_primary_recovery = _coerce_bool(flow_policy.get('require_primary_recovery', allowed_behavior_count > 1))
        observed_hops = len(observed_path or [])
        state_change_count = int(flow_state.get('state_change_count', 0)) + (1 if current_state != previous_state else 0)
        degraded_packets = int(flow_state.get('degraded_packets', 0)) + (1 if current_state.startswith('BACKUP_') else 0)
        consecutive_backup_packets = (
            int(flow_state.get('consecutive_backup_packets', 0)) + 1
            if current_state.startswith('BACKUP_') else 0
        )
        seen_primary_before = _coerce_bool(flow_state.get('seen_primary', False))
        seen_primary_after = seen_primary_before or current_state == 'PRIMARY'

        invariant_results = []
        violation_types = []

        counter_ok = packet_count <= max_packets
        invariant_results.append(self._invariant_result('COUNTER_BOUND', counter_ok, f'packet_count={packet_count}, bound={max_packets}'))
        if not counter_ok:
            violation_types.append('BOUND_VIOLATION')

        index_ok = behavior_index is not None and 0 <= behavior_index < allowed_behavior_count
        invariant_results.append(self._invariant_result('INDEX_BOUND', index_ok, f'behavior_index={behavior_index}, allowed={allowed_behavior_count}'))
        if not index_ok:
            violation_types.append('BOUND_VIOLATION')

        resource_ok = max_hops == 0 or observed_hops <= max_hops
        invariant_results.append(self._invariant_result('RESOURCE_BOUND', resource_ok, f'path_hops={observed_hops}, bound={max_hops}'))
        if not resource_ok:
            violation_types.append('RESOURCE_OVERFLOW')

        legal_ok = bool(match_result and match_result.get('matched'))
        invariant_results.append(self._invariant_result('LEGAL_BEHAVIOR', legal_ok, f'matched={legal_ok}'))
        if not legal_ok:
            violation_types.append('INCONSISTENT_STATE')

        degraded_budget_ok = degraded_packets <= max_degraded_packets
        invariant_results.append(
            self._invariant_result(
                'DEGRADED_BUDGET',
                degraded_budget_ok,
                f'degraded_packets={degraded_packets}, bound={max_degraded_packets}',
            )
        )
        if not degraded_budget_ok:
            violation_types.append('RESOURCE_OVERFLOW')

        state_budget_ok = state_change_count <= max_state_changes
        invariant_results.append(
            self._invariant_result(
                'STATE_CHANGE_BUDGET',
                state_budget_ok,
                f'state_change_count={state_change_count}, bound={max_state_changes}',
            )
        )
        if not state_budget_ok:
            violation_types.append('BOUND_VIOLATION')

        primary_entry_ok = not (require_primary_recovery and current_state.startswith('BACKUP_') and not seen_primary_before)
        invariant_results.append(
            self._invariant_result(
                'PRIMARY_ENTRY',
                primary_entry_ok,
                f'seen_primary_before={seen_primary_before}, current_state={current_state}',
            )
        )
        if not primary_entry_ok:
            violation_types.append('UNINITIALIZED_USE')

        recovery_window_ok = True
        if require_primary_recovery and current_state.startswith('BACKUP_'):
            recovery_window_ok = consecutive_backup_packets <= max_degraded_packets
        invariant_results.append(
            self._invariant_result(
                'PRIMARY_RECOVERY_WINDOW',
                recovery_window_ok,
                (
                    f'consecutive_backup_packets={consecutive_backup_packets}, '
                    f'bound={max_degraded_packets}, require_primary_recovery={require_primary_recovery}'
                ),
            )
        )
        if not recovery_window_ok:
            violation_types.append('INCONSISTENT_STATE')

        invariant_results.append(self._invariant_result('TRANSITION_VALID', transition_allowed, f'{previous_state} -> {current_state}'))
        if not transition_allowed:
            violation_types.append('INVALID_TRANSITION')

        violation_types = sorted(set(violation_types))
        verdict = 'violation' if violation_types else ('degraded' if current_state.startswith('BACKUP_') else 'pass')
        verdict_label = {
            'pass': '语义状态合法',
            'degraded': '命中合法备份状态',
            'violation': '检测到语义违规',
        }[verdict]

        flow_state.update({
            'packet_count': packet_count,
            'current_state': current_state,
            'last_path': observed_path or [],
            'last_behavior_index': behavior_index,
            'last_verdict': verdict,
            'degraded_packets': degraded_packets,
            'state_change_count': state_change_count,
            'consecutive_backup_packets': consecutive_backup_packets,
            'seen_primary': seen_primary_after,
            'updated_at': int(time.time()),
        })
        self.state['updated_at'] = int(time.time())

        history_record = {
            'timestamp': int(time.time()),
            'flow_id': flow_key,
            'previous_state': previous_state,
            'current_state': current_state,
            'packet_count': packet_count,
            'behavior_index': behavior_index,
            'observed_path': observed_path or [],
            'verdict': verdict,
            'violation_types': violation_types,
            'degraded_packets': degraded_packets,
            'state_change_count': state_change_count,
            'consecutive_backup_packets': consecutive_backup_packets,
        }
        self.history.append(history_record)
        self.history = self.history[-MAX_HISTORY_ITEMS:]

        atomic_write_json(self.state_path, self.state, ensure_ascii=False, indent=2)
        atomic_write_json(self.history_path, self.history, ensure_ascii=False, indent=2)

        return {
            'flow_id': flow_key,
            'flow_scope': flow_policy.get('flow_scope', {}),
            'semantic_tags': flow_policy.get('semantic_tags', dict(SEMANTIC_TAGS)),
            'previous_state': previous_state,
            'current_state': current_state,
            'packet_count': packet_count,
            'behavior_index': behavior_index,
            'allowed_behavior_count': allowed_behavior_count,
            'max_packets': max_packets,
            'max_hops': max_hops,
            'max_degraded_packets': max_degraded_packets,
            'max_state_changes': max_state_changes,
            'require_primary_recovery': require_primary_recovery,
            'observed_path_hops': observed_hops,
            'degraded_packets': degraded_packets,
            'state_change_count': state_change_count,
            'consecutive_backup_packets': consecutive_backup_packets,
            'transition_allowed': transition_allowed,
            'verdict': verdict,
            'verdict_label': verdict_label,
            'violation_types': violation_types,
            'invariant_results': invariant_results,
            'allowed_transitions': flow_policy.get('allowed_transitions', []),
        }