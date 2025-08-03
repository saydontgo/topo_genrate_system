from p4utils.mininetlib.network_API import NetworkAPI
from p4utils.mininetlib.log import setLogLevel, debug, info, output, warning, error
import json
import time
import os
import re

from ..helper import hex_IP


class demo(NetworkAPI):
    def __init__(self, *args, **params):
        super().__init__(*args, **params)
        super().__init__()
        self.setLogLevel('info')
        self.disableCli()
        self.isNetworkStart = False
        self.isCompiled = False

        # Network definition
        # Switch
        for i in range(1, 5):
            self.addP4Switch(f's{i}', cli_input=f'topo/demo/rules/s{i}-commands.txt')
        self.setP4SourceAll('p4src/switch.p4')

        self.addHost('h1')
        self.addHost('h2')

        self.addLink('h1', 's1')
        self.addLink('h2', 's4')

        self.addLink('s1', 's2')
        self.addLink('s1', 's3')
        self.addLink('s2', 's4')
        self.addLink('s3', 's4')

        # Assignment strategy
        self.mixed()  
    
    def clean_and_compile(self):
        """清理旧网络信息并加载p4代码进入交换机"""
        debug('Cleanup old files and processes...\n')
        self.cleanup()

        debug('Auto configuration of not configured interfaces...\n')
        self.auto_assignment()

        try:
            info('Compiling P4 files...\n')
            self.compile()
            output('P4 Files compiled!\n')
        except Exception as e:
            error('There is something wrong while compiling p4 source\n')
            return False
        self.printPortMapping()

        self.isCompiled = True

        return True

    def program_switches(self):  
        """装载流表"""  
        try:    
            info('Programming switches...\n')
            # super().program_switches()
            for i in range(1,5):
                cur_sw = self.net.get(f's{i}')
                thriftPort = 9089+i
                cur_sw.cmd(f"simple_switch_CLI --thrift-port {thriftPort} < topo/demo/rules/s{i}-commands.txt")
            output('Switches programmed correctly!\n')
        except Exception as e:
            error(f"There is something wrong while programming switches. Detailed info is as followed:{e}\n")
            return False
        return True

    def startNetwork(self):
        """Starts and configures the network."""
        
        assert self.isCompiled

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
        self.save_topology()
        output('Topology saved to disk!\n')

        # 装载流表的部分，需单独写出
        # info('Programming switches...\n')
        # self.program_switches()
        # output('Switches programmed correctly!\n')

        info('Programming hosts...\n')
        self.program_hosts()
        output('Hosts programmed correctly!\n')

        info('Executing scripts...\n')
        self.exec_scripts()
        output('All scripts executed correctly!\n')

        info('Distributing tasks...\n')
        self.distribute_tasks()
        output('All tasks distributed correctly!\n')

        if self.cli_enabled:
            self.start_net_cli()
            # Stop right after the CLI is exited
            self.stopNetwork()


        self.isNetworkStart = True  

    def get_path(self, src_host, dst_host):
        dst_ip = self.net.get(dst_host).IP()
        src_ip = self.net.get(src_host).IP()
        with open("topo/demo/rules/rules.json", "r")as f:
            paths = json.load(f)
            for path in paths:
                if path['src_ip'] == src_ip and path['dst_ip'] == dst_ip:
                    return path['path']
        return None   
    
    def send(self, src_host, dst_host):
        """
        返回值为bool 表示send操作是否成功，如果失败将不会产生任何文件，成功将会在application文件夹下生成res.json。
        调用此方法前网络必须启动。
        """
        assert self.isNetworkStart and self.isCompiled
        dst_shell = self.net.get(dst_host)
        src_shell = self.net.get(src_host)
        output = ""
        try:
            info('executing receive.py...\n')
            output = dst_shell.cmd('./topo/dmeo/receive.py &')
        except Exception as e:
            error(f"fail to launch receive.py on {dst_host}. Detailed info is as follow:{e}\n")
            return False
        
        if output != "":
            print("successful execution:")
            print(output)
        time.sleep(3)

        try:
            output = src_shell.cmd(f'./topo/demo/send.py --ip {dst_shell.IP()} --m tag')
        except Exception as e:
            error(f"fail to launch send.py on {src_host}. Detailed info is as follow:{e}\n")
            return False
        if output != "":
            print("successful execution:")
            print(output)
        time.sleep(1)

        res=None

        if not os.path.isfile('res.json'):
            return False

        with open("res.json", "r")as f:
            res = json.load(f)

        res["stop_receiving"] = False

        try:
            dst_shell.cmd("pkill -f 'python3 ./topo/demo/receive.py'")
            info('receive.py killed.\n')
            res["stop_receiving"] = True
        except Exception as e:
            error(f'fail to kill receive.py. Detailed info is as follow:{e}\n')

        with open("res.json", "w")as f:
            json.dump(res, f, indent=4)
    
    def modify_switch(self, swid, dst_host, dst_swid):
        """
        swid:被修改的交换机
        dst_host:被修改流表表项对应的主机
        dst_swid:流表表项修改的目标交换机
        """

        assert self.isNetworkStart and self.isCompiled
        cur_sw = self.net.get(swid)
        dst_sw = self.net.get(dst_swid)
        dst_port = None

        # 获取交换机连接的端口信息
        for intf in cur_sw.intfList():
            if intf.name != 'lo':
                peer = intf.link.intf2 if intf.link.intf1 == intf else intf.link.intf1
                if peer.node == dst_sw:
                    dst_port = re.findall("eth(.*)", intf.name)[0]
        if dst_port == None: 
            info(f'These two switches are not neighbours! You can\'t modify switch {swid}.\n')
            return False
        
        # 将每一条有关该目的地主机的流表进行修改
        h = self.net.get(dst_host)
        thriftPort = 9089+int(swid[1:])
        try:
            output = self.net.get(swid).cmd(f'echo "table_dump MyIngress.ipv4_lpm" | simple_switch_CLI --thrift-port {thriftPort}')
        except Exception as e:
            error(f"Execution of your command failed. Detailed info is as follow:{e}\n")
            return False
        handle = None
        hexIP = hex_IP(h.IP())
        for line in output.strip().split('\n'):
            if "Dumping entry" in line:
                handle = int(line[16:], 16)
            if hexIP in line:
                if handle == None:
                    continue
                cmd = f'echo "table_modify ipv4_lpm ipv4_forward {handle} {h.MAC()} {dst_port}" | simple_switch_CLI --thrift-port {thriftPort}'
                res = self.net.get(swid).cmd(cmd)
                handle = None
                info('modify results:\n' + res + '\n')
        
        return True

    def stopNetwork(self):
        super().stopNetwork()
        self.isNetworkStart = False

if __name__ == '__main__':
    topo = demo()
    topo.clean_and_compile()
    topo.startNetwork()
    topo.program_switches()
    topo.stopNetwork()