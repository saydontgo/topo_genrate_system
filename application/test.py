# from flask import Flask, render_template, jsonify, request
# import threading
# import json
# import os
# import topo.FatTree6.FatTree6 as ft6

# app = Flask(__name__)

# current_topology = None

# # 首页（主页）
# @app.route('/')
# def home():
#     return render_template('home.html')  # 改为 index.html 页面

# # 拓扑页面
# @app.route('/topology')
# def topology_page():
#     return render_template('topology.html')

# # FatTree6 拓扑页面
# @app.route('/topology/fattree6')
# def fattree6_page():
#     return render_template('fattree6.html')

# # 设置页面
# @app.route('/settings')
# def settings_page():
#     return render_template('settings.html')

# @app.route('/get_topology_data')
# def get_topology_data():
#     # 假设你保存的是 txt 文件，可以在构建拓扑时自动写入或读取已有文件
#     edges = []
#     try:
#         with open('topo/FatTree6/topo.txt', 'r') as f:
#             for line in f:
#                 # 格式：(s1, h1)
#                 line = line.strip().replace('(', '').replace(')', '').replace(',', '')
#                 parts = line.split()
#                 if len(parts) == 2:
#                     edges.append({'from': parts[0], 'to': parts[1]})
#     except Exception as e:
#         return jsonify({'error': str(e)}), 500

#     return jsonify(edges)

# # 启动拓扑线程
# def run_mininet_topology(topology):
#     global current_topology
#     print(f"开始构建拓扑: {topology}")
#     current_topology = ft6.FatTree6()
#     print(f"{topology} 拓扑构建完成")
#     try:
#         current_topology.startNetwork()
#     except Exception:
#         current_topology.stopNetwork()

# # 接收选择拓扑的请求
# @app.route('/select_topology', methods=['POST'])
# def handle_select_topology():
#     data = request.json
#     topology = data.get('topology')
#     print(f"收到拓扑选择请求: {topology}")

#     if topology not in [4, 6]:
#         return jsonify({'error': 'Invalid topology'}), 400

#     # 启动新线程运行 Mininet 拓扑
#     thread = threading.Thread(target=run_mininet_topology, args=(topology,), daemon=True)
#     thread.start()

#     return jsonify({'status': 'Topology selection received', 'topology': topology})

# @app.route('/get_topology_nodes')
# def get_topology_nodes():
#     with open('topology.json', 'r') as f:
#         topology = json.load(f)
#     return jsonify({'nodes': topology.get('nodes', [])})


# @app.route('/send_command', methods=['POST'])
# def handle_send_command():
#     global current_topology

#     if current_topology is None:
#         return jsonify({'error': 'No topology built yet'}), 400

#     data = request.get_json()
#     src_host = data.get('src')
#     dst_host = data.get('dst')

#     if not src_host or not dst_host:
#         return jsonify({'error': '请提供源主机和目标主机'}), 400

#     try:
#         with open('topology.json', 'r', encoding='utf-8') as f:
#             topo = json.load(f)
#             node_map = {node['id']: node for node in topo.get('nodes', [])}
#             if src_host not in node_map or dst_host not in node_map:
#                 return jsonify({'error': '主机 ID 不存在'}), 400
#             src_ip = node_map[src_host].get('ip', '')
#             dst_ip = node_map[dst_host].get('ip', '')
#     except Exception as e:
#         return jsonify({'error': f'IP地址查找失败: {str(e)}'}), 500

#     print(f"Receive: {src_host}({src_ip}) → {dst_host}({dst_ip})")

#     try:
#         current_topology.send(src_host, dst_host)
#     except Exception as e:
#         return jsonify({'error': f'发送执行失败: {str(e)}'}), 500

#     return jsonify({'result': f'命令已发送：{src_host} → {dst_host}'})

# @app.route('/get_res_json', methods=['GET'])
# def get_res_json():
#     # 假设 res.json 位于项目根目录
#     res_file_path = os.path.join(os.path.dirname(__file__), 'res.json')
    
#     if os.path.exists(res_file_path):
#         with open(res_file_path, 'r') as f:
#             data = f.read()
#             return jsonify(data), 200
#     else:
#         return jsonify({"error": "res.json not found"}), 404


# # 启动服务
# if __name__ == '__main__':
#     app.run(host='0.0.0.0', debug=True)
from flask import Flask, render_template, jsonify, request
import threading
import json
import os
import topo.FatTree6.FatTree6 as ft6

app = Flask(__name__)

current_topology = None

# 首页（主页）
@app.route('/')
def home():
    return render_template('home.html')  # 改为 index.html 页面

# 拓扑页面
@app.route('/topology')
def topology_page():
    return render_template('topology.html')

# FatTree6 拓扑页面
@app.route('/topology/fattree6')
def fattree6_page():
    return render_template('fattree6.html')

# 设置页面
@app.route('/settings')
def settings_page():
    return render_template('settings.html')

@app.route('/get_topology_data')
def get_topology_data():
    # 假设你保存的是 txt 文件，可以在构建拓扑时自动写入或读取已有文件
    edges = []
    try:
        with open('topo/FatTree6/topo.txt', 'r') as f:
            for line in f:
                # 格式：(s1, h1)
                line = line.strip().replace('(', '').replace(')', '').replace(',', '')
                parts = line.split()
                if len(parts) == 2:
                    edges.append({'from': parts[0], 'to': parts[1]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return jsonify(edges)

# 启动拓扑线程
def run_mininet_topology(topology):
    global current_topology
    print(f"开始构建拓扑: {topology}")
    current_topology = ft6.FatTree6()
    print(f"{topology} 拓扑构建完成")
    try:
        current_topology.clean_and_compile()
        current_topology.startNetwork()
        current_topology.program_switches()
    except Exception:
        current_topology.stopNetwork()

# 接收选择拓扑的请求
@app.route('/select_topology', methods=['POST'])
def handle_select_topology():
    data = request.json
    topology = data.get('topology')
    print(f"收到拓扑选择请求: {topology}")

    if topology not in [4, 6]:
        return jsonify({'error': 'Invalid topology'}), 400

    # 启动新线程运行 Mininet 拓扑
    thread = threading.Thread(target=run_mininet_topology, args=(topology,), daemon=True)
    thread.start()

    return jsonify({'status': 'Topology selection received', 'topology': topology})

@app.route('/get_topology_nodes')
def get_topology_nodes():
    with open('topology.json', 'r') as f:
        topology = json.load(f)
    return jsonify({'nodes': topology.get('nodes', [])})


@app.route('/send_command', methods=['POST'])
def handle_send_command():
    global current_topology

    if current_topology is None:
        return jsonify({'error': 'No topology built yet'}), 400

    data = request.get_json()
    src_host = data.get('src')
    dst_host = data.get('dst')

    if not src_host or not dst_host:
        return jsonify({'error': '请提供源主机和目标主机'}), 400

    try:
        with open('topology.json', 'r', encoding='utf-8') as f:
            topo = json.load(f)
            node_map = {node['id']: node for node in topo.get('nodes', [])}
            if src_host not in node_map or dst_host not in node_map:
                return jsonify({'error': '主机 ID 不存在'}), 400
            src_ip = node_map[src_host].get('ip', '')
            dst_ip = node_map[dst_host].get('ip', '')
    except Exception as e:
        return jsonify({'error': f'IP地址查找失败: {str(e)}'}), 500

    print(f"Receive: {src_host}({src_ip}) → {dst_host}({dst_ip})")

    try:
        current_topology.send(src_host, dst_host)
    except Exception as e:
        return jsonify({'error': f'发送执行失败: {str(e)}'}), 500

    return jsonify({'result': f'命令已发送：{src_host} → {dst_host}'})

@app.route('/get_res_json', methods=['GET'])
def get_res_json():
    # 假设 res.json 位于项目根目录
    res_file_path = os.path.join(os.path.dirname(__file__), 'res.json')
    
    if os.path.exists(res_file_path):
        with open(res_file_path, 'r') as f:
            data = f.read()
            return jsonify(data), 200
    else:
        return jsonify({"error": "res.json not found"}), 404

@app.route('/modify_flow_table', methods=['POST'])
def modify_flow_table():
    data = request.json
    swid = data.get('swid')          # 被修改的交换机 ID
    dst_host = data.get('dst_host')  # 流表涉及的主机 ID
    dst_swid = data.get('dst_swid')  # 目标交换机 ID

    if not (swid and dst_host and dst_swid):
        return jsonify({'status': 'error', 'msg': '参数不完整'})

    try:
        # current_topology.compile()
        # current_topology.program_switches()
        result = current_topology.modify_switch(swid, dst_host, dst_swid)
        return jsonify({'status': 'success', 'msg': '修改完成'})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})
   


# 启动服务
if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
