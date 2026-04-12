import sys
import time
import logging
import json

logging.getLogger("scapy.runtime").setLevel(logging.ERROR)

from scapy.all import sniff
from scapy.all import Packet
from scapy.all import IP, UDP, TCP
from tools import get_if, IPOption_TAG, IPOption_MRI
from topo import Topology
from behavior_pool import BehaviorPool


def load_rules(rule_path):
    rules = {}
    with open(rule_path, 'r') as json_file:
        rule_list = json.load(json_file)
        for rule in rule_list:
            key = rule['src_ip'] + '-' + rule['dst_ip']
            rules[key] = rule['path']
    return rules


def get_5tuple(pkt):
    if TCP in pkt:
        return pkt[IP].src, pkt[IP].dst, pkt[TCP].sport, pkt[TCP].dport, pkt[IP].proto
    elif UDP in pkt:
        return pkt[IP].src, pkt[IP].dst, pkt[UDP].sport, pkt[UDP].dport, pkt[IP].proto


def recover_path_from_prime_product(topo, dst_ip, prime_prod):
    tmp_prod = prime_prod
    pre_switch = None
    end_switch = None
    path = []
    found = False

    for node in topo.get_neighbors(topo.get_id(dst_ip)):
        tmp_prime = topo.get_prime(node)
        if tmp_prod % tmp_prime == 0:
            end_switch = node
            tmp_prod /= tmp_prime
            found = True
            break

    if end_switch is not None:
        path.append(int(end_switch[1:]))
        while tmp_prod > 1:
            found = False
            for node in topo.get_neighbors(end_switch):
                if pre_switch is None or node != pre_switch:
                    prime = topo.get_prime(node)
                    if prime == 1:
                        continue
                    if tmp_prod % prime == 0:
                        pre_switch = end_switch
                        end_switch = node
                        tmp_prod /= prime
                        path.append(int(end_switch[1:]))
                        found = True
                        break

    if found:
        return path[::-1]
    return None


NUM = 0
bytes = 0
check_bytes = 0
end_time = time.time()
topo = Topology('topology.json')
rules = load_rules('topo/rules.json')
behavior_pool = BehaviorPool('topo/demo/rules/behavior_pool.json', 'topology.json')


def verification(pkt: Packet):
    src_ip, dst_ip, _, _, _ = get_5tuple(pkt)
    key = src_ip + '-' + dst_ip

    with open("res.json", "w") as f:
        primary_behavior = behavior_pool.get_primary_behavior(src_ip, dst_ip)
        expected_path = primary_behavior['path'] if primary_behavior else rules.get(key)
        res = {
            "src_ip": src_ip,
            "dst_ip": dst_ip,
            "expected_path": expected_path,
            "consistence": True,
            "recover_path": None,
            "behavior_status": "unknown",
            "behavior_label": "未启用合法行为池判定",
            "matched_behavior_path": None
        }

        if key not in rules:
            print("not found src_ip: %s, dest_ip: %s in rules store.\n" % (src_ip, dst_ip))
            sys.exit()

        if IPOption_TAG in pkt:
            prime_prod = pkt['TAG'].prime_product
            match_result = behavior_pool.classify(src_ip, dst_ip, prime_prod)

            if match_result['matched']:
                res['behavior_status'] = match_result['level']
                res['behavior_label'] = match_result['label']
                res['matched_behavior_path'] = match_result['path']
                res['consistence'] = True
                print(
                    'VBP matched = source-destination pair: (%s, %s), level: %s, prime_prod: %s, path: %s\n'
                    % (src_ip, dst_ip, match_result['level'], prime_prod, match_result['path'])
                )
            else:
                print(
                    'VBP illegal = source-destination pair: (%s, %s), prime_prod: %s, time: %s\n'
                    % (src_ip, dst_ip, prime_prod, time.time())
                )
                res['consistence'] = False
                res['behavior_status'] = 'illegal'
                res['behavior_label'] = '未命中合法行为池'
                res['recover_path'] = recover_path_from_prime_product(topo, dst_ip, prime_prod)
                if res['recover_path']:
                    print("recover success! prime_prod: %s, forward path: %s\n" % (prime_prod, res['recover_path']))
                else:
                    print("Error: can't recover the actual forward path. prime product: %s\n" % (prime_prod))
                    sys.exit()

        elif IPOption_MRI in pkt:
            count = pkt['MRI'].count - 1
            path = []
            while count >= 0:
                swid = pkt['MRI'].swtraces[count].swid
                path.append(swid)
                count = count - 1

            primary_path = expected_path or []
            match_result = None
            for behavior in behavior_pool.get_behaviors(src_ip, dst_ip):
                if behavior['path'] == path:
                    match_result = behavior
                    break

            if match_result:
                res['behavior_status'] = match_result['level']
                res['behavior_label'] = match_result['label']
                res['matched_behavior_path'] = match_result['path']
            else:
                res['consistence'] = False
                res['behavior_status'] = 'illegal'
                res['behavior_label'] = '未命中合法行为池'
                res['recover_path'] = path

            if path != primary_path and not match_result:
                print('VBP illegal = source-destination pair: (%s, %s), path: %s, primary_path: %s, time: %s'
                      % (src_ip, dst_ip, path, primary_path, time.time()))

        json.dump(res, f, indent=4)


def handle_pkt(pkt: Packet):
    global NUM
    global bytes
    global check_bytes
    global end_time

    verification(pkt)
    sys.stdout.flush()


def main():
    iface = get_if()
    print("sniffing on %s" % iface)
    sys.stdout.flush()
    sniff(iface=iface, filter='inbound', prn=lambda x: handle_pkt(x))


if __name__ == '__main__':
    main()
