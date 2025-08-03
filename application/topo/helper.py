def d2h(d):
    if d > 15:
        return f'{hex(d)[2:]}'
    return f'0{hex(d)[2:]}'

def hex_IP(ip):
    res = ""
    tmp = ""
    for s in ip:
        if s == '.':
            res += d2h(int(tmp))
            tmp = ""
        else:
            tmp += s
    if tmp != "":
        res += d2h(int(tmp))
    return res