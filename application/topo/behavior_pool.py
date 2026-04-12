import json

from topo import Topology


class BehaviorPool:
    def __init__(self, pool_path, topo_json='topology.json'):
        self.topology = Topology(topo_json)
        self.pool = {}
        self._load(pool_path)

    def _load(self, pool_path):
        with open(pool_path, 'r') as json_file:
            behavior_items = json.load(json_file)

        for item in behavior_items:
            key = self._make_key(item['src_ip'], item['dst_ip'])
            behaviors = []
            for behavior in item.get('behaviors', []):
                path = behavior.get('path', [])
                prime_product = behavior.get('prime_product')
                if prime_product is None and path:
                    prime_product = self.calculate_prime_product(path)
                behaviors.append({
                    'path': path,
                    'prime_product': prime_product,
                    'level': behavior.get('level', 'primary'),
                    'label': behavior.get('label', '')
                })
            self.pool[key] = behaviors

    def _make_key(self, src_ip, dst_ip):
        return f'{src_ip}-{dst_ip}'

    def calculate_prime_product(self, path):
        prime_product = 1
        for node in path:
            prime = self.topology.get_prime(f's{node}')
            if prime == 1:
                continue
            prime_product *= prime
        return prime_product

    def get_behaviors(self, src_ip, dst_ip):
        return self.pool.get(self._make_key(src_ip, dst_ip), [])

    def get_primary_behavior(self, src_ip, dst_ip):
        behaviors = self.get_behaviors(src_ip, dst_ip)
        for behavior in behaviors:
            if behavior['level'] == 'primary':
                return behavior
        return behaviors[0] if behaviors else None

    def classify(self, src_ip, dst_ip, observed_prime_product):
        behaviors = self.get_behaviors(src_ip, dst_ip)
        for behavior in behaviors:
            if behavior['prime_product'] == observed_prime_product:
                return {
                    'matched': True,
                    'level': behavior['level'],
                    'label': behavior['label'],
                    'path': behavior['path'],
                    'prime_product': behavior['prime_product']
                }

        return {
            'matched': False,
            'level': 'illegal',
            'label': '未命中合法行为池',
            'path': None,
            'prime_product': observed_prime_product
        }
