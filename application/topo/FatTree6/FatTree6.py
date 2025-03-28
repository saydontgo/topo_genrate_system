from p4utils.mininetlib.network_API import NetworkAPI
from p4utils.mininetlib.log import setLogLevel, debug, info, output, warning, error
import time
import json
import re
import os

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

class FatTree6(NetworkAPI):
    def __init__(self):
        super().__init__()
        self.setLogLevel('info')
        self.disableCli()
        self.isNetworkStart = False
        self.isCompiled = False
        # Switch
        for i in range(1, 46):
            self.addP4Switch(f's{i}', cli_input=f'topo/FatTree6/rules/s{i}-commands.txt')
        
        self.setP4SourceAll('p4src/switch.p4')

        # Host
        for i in range(1, 55):
            self.addHost(f'h{i}')

        # core Link
        self.addLink('s37', 's19')
        self.addLink('s37', 's22')
        self.addLink('s37', 's25')
        self.addLink('s37', 's28')
        self.addLink('s37', 's31')
        self.addLink('s37', 's34')

        self.addLink('s38', 's19')
        self.addLink('s38', 's22')
        self.addLink('s38', 's25')
        self.addLink('s38', 's28')
        self.addLink('s38', 's31')
        self.addLink('s38', 's34')

        self.addLink('s39', 's19')
        self.addLink('s39', 's22')
        self.addLink('s39', 's25')
        self.addLink('s39', 's28')
        self.addLink('s39', 's31')
        self.addLink('s39', 's34')

        self.addLink('s40', 's20')
        self.addLink('s40', 's23')
        self.addLink('s40', 's26')
        self.addLink('s40', 's29')
        self.addLink('s40', 's32')
        self.addLink('s40', 's35')

        self.addLink('s41', 's20')
        self.addLink('s41', 's23')
        self.addLink('s41', 's26')
        self.addLink('s41', 's29')
        self.addLink('s41', 's32')
        self.addLink('s41', 's35')

        self.addLink('s42', 's20')
        self.addLink('s42', 's23')
        self.addLink('s42', 's26')
        self.addLink('s42', 's29')
        self.addLink('s42', 's32')
        self.addLink('s42', 's35')

        self.addLink('s43', 's21')
        self.addLink('s43', 's24')
        self.addLink('s43', 's27')
        self.addLink('s43', 's30')
        self.addLink('s43', 's33')
        self.addLink('s43', 's36')

        self.addLink('s44', 's21')
        self.addLink('s44', 's24')
        self.addLink('s44', 's27')
        self.addLink('s44', 's30')
        self.addLink('s44', 's33')
        self.addLink('s44', 's36')

        self.addLink('s45', 's21')
        self.addLink('s45', 's24')
        self.addLink('s45', 's27')
        self.addLink('s45', 's30')
        self.addLink('s45', 's33')
        self.addLink('s45', 's36')

        # aggregate Link
        self.addLink('s19', 's1')
        self.addLink('s19', 's2')
        self.addLink('s19', 's3')
        self.addLink('s20', 's1')
        self.addLink('s20', 's2')
        self.addLink('s20', 's3')
        self.addLink('s21', 's1')
        self.addLink('s21', 's2')
        self.addLink('s21', 's3')

        self.addLink('s22', 's4')
        self.addLink('s22', 's5')
        self.addLink('s22', 's6')
        self.addLink('s23', 's4')
        self.addLink('s23', 's5')
        self.addLink('s23', 's6')
        self.addLink('s24', 's4')
        self.addLink('s24', 's5')
        self.addLink('s24', 's6')

        self.addLink('s25', 's7')
        self.addLink('s25', 's8')
        self.addLink('s25', 's9')
        self.addLink('s26', 's7')
        self.addLink('s26', 's8')
        self.addLink('s26', 's9')
        self.addLink('s27', 's7')
        self.addLink('s27', 's8')
        self.addLink('s27', 's9')

        self.addLink('s28', 's10')
        self.addLink('s28', 's11')
        self.addLink('s28', 's12')
        self.addLink('s29', 's10')
        self.addLink('s29', 's11')
        self.addLink('s29', 's12')
        self.addLink('s30', 's10')
        self.addLink('s30', 's11')
        self.addLink('s30', 's12')

        self.addLink('s31', 's13')
        self.addLink('s31', 's14')
        self.addLink('s31', 's15')
        self.addLink('s32', 's13')
        self.addLink('s32', 's14')
        self.addLink('s32', 's15')
        self.addLink('s33', 's13')
        self.addLink('s33', 's14')
        self.addLink('s33', 's15')

        self.addLink('s34', 's16')
        self.addLink('s34', 's17')
        self.addLink('s34', 's18')
        self.addLink('s35', 's16')
        self.addLink('s35', 's17')
        self.addLink('s35', 's18')
        self.addLink('s36', 's16')
        self.addLink('s36', 's17')
        self.addLink('s36', 's18')

        # host link
        self.addLink('s1', 'h1')
        self.addLink('s1', 'h2')
        self.addLink('s1', 'h3')
        self.addLink('s2', 'h4')
        self.addLink('s2', 'h5')
        self.addLink('s2', 'h6')
        self.addLink('s3', 'h7')
        self.addLink('s3', 'h8')
        self.addLink('s3', 'h9')
        self.addLink('s4', 'h10')
        self.addLink('s4', 'h11')
        self.addLink('s4', 'h12')
        self.addLink('s5', 'h13')
        self.addLink('s5', 'h14')
        self.addLink('s5', 'h15')
        self.addLink('s6', 'h16')
        self.addLink('s6', 'h17')
        self.addLink('s6', 'h18')
        self.addLink('s7', 'h19')
        self.addLink('s7', 'h20')
        self.addLink('s7', 'h21')
        self.addLink('s8', 'h22')
        self.addLink('s8', 'h23')
        self.addLink('s8', 'h24')
        self.addLink('s9', 'h25')
        self.addLink('s9', 'h26')
        self.addLink('s9', 'h27')
        self.addLink('s10', 'h28')
        self.addLink('s10', 'h29')
        self.addLink('s10', 'h30')
        self.addLink('s11', 'h31')
        self.addLink('s11', 'h32')
        self.addLink('s11', 'h33')
        self.addLink('s12', 'h34')
        self.addLink('s12', 'h35')
        self.addLink('s12', 'h36')
        self.addLink('s13', 'h37')
        self.addLink('s13', 'h38')
        self.addLink('s13', 'h39')
        self.addLink('s14', 'h40')
        self.addLink('s14', 'h41')
        self.addLink('s14', 'h42')
        self.addLink('s15', 'h43')
        self.addLink('s15', 'h44')
        self.addLink('s15', 'h45')
        self.addLink('s16', 'h46')
        self.addLink('s16', 'h47')
        self.addLink('s16', 'h48')
        self.addLink('s17', 'h49')
        self.addLink('s17', 'h50')
        self.addLink('s17', 'h51')
        self.addLink('s18', 'h52')
        self.addLink('s18', 'h53')
        self.addLink('s18', 'h54')


        # Asignment strategy
        self.mixed()
        # Nodes general options
        # self.enableCpuPortAll()
        # self.enablePcapDumpAll()
        # self.enableLogAll()

        # Start the self.network

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
            for i in range(1,46):
                cur_sw = self.net.get(f's{i}')
                thriftPort = 9089+i
                cur_sw.cmd(f"simple_switch_CLI --thrift-port {thriftPort} < topo/FatTree6/rules/s{i}-commands.txt")
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
        with open("topo/FatTree6/rules.json", "r")as f:
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
            output = dst_shell.cmd('./topo/FatTree6/receive.py &')
        except Exception as e:
            error(f"fail to launch receive.py on {dst_host}. Detailed info is as follow:{e}\n")
            return False
        
        if output != "":
            print("successful execution:")
            print(output)
        time.sleep(3)

        try:
            output = src_shell.cmd(f'./topo/FatTree6/send.py --ip {dst_shell.IP()} --m tag')
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
            dst_shell.cmd("pkill -f 'python3 ./topo/FatTree6/receive.py'")
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
        #TODO 要将结果以什么样的形式传回去？

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
    ft6=FatTree6()
    ft6.startNetwork()
