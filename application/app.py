from flask import Flask, render_template, jsonify, request
from flask import send_file
from flask import session
from p4utils.mininetlib.log import setLogLevel, debug, info, output, warning, error
import threading
import atexit
import json
import os
import io
import topo.FatTree6.FatTree6 as ft6
import topo.demo.network as demo
from LLM import secure_session_id, call_llm, r, deepseek, ecnu_ai
app = Flask(__name__)
app.secret_key = 'your-very-secret-and-complex-key-here'
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

# -------------demo的新增后端代码---------------
# demo 拓扑页面
@app.route('/topology/your_topology')
def demo_page():
    return render_template('demo.html')
# -------------demo的新增后端代码---------------

# 设置页面
@app.route('/settings')
def settings_page():
    return render_template('settings.html')

@app.route('/get_topology_data')
def get_topology_data():
    # 假设你保存的是 txt 文件，可以在构建拓扑时自动写入或读取已有文件
    edges = []
    if current_topology.topoType == 'ft6':
        topo_data_file = r'topo/FatTree6/topo.txt'
    elif current_topology.topoType == 'demo':
        topo_data_file = r'topo/demo/topo.txt'
    else:
        return jsonify({'error': 'invalid topo'}), 404
    
    try:
        with open(topo_data_file, 'r') as f:
            for line in f:
                # 格式：(s1, h1)
                line = line.strip().replace('(', '').replace(')', '').replace(',', '')
                parts = line.split()
                if len(parts) == 2:
                    edges.append({'from': parts[0], 'to': parts[1]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return jsonify(edges)

# 跳转界面后立即初始化
@app.route('/initiate_topo', methods=['POST'])
def initiate_topo():
    url = request.json.get('url')
    global current_topology
    domains = url.rstrip('/').split('/')
    if len(domains) < 2:
        return jsonify({'error': 'in the wrong page!'}), 404
    last_domain = domains[-2]
    if last_domain != 'topology':
        return jsonify({'error': 'in the wrong page!'}), 404
    topology = domains[-1]
    if topology == 'fattree6':
        current_topology = ft6.FatTree6()
    elif topology == 'your_topology':
        current_topology = demo.demo()
    else:
        return jsonify({'error': f'invalid topo: {topology}'}), 404
    
    info(f"successfully initiate topo {topology}\n")
    return jsonify({'status': 'success', 'topology': topology})

# 启动拓扑线程
def run_mininet_topology(topology):
    global current_topology
    info(f"开始构建拓扑: {topology}")
    try:
        current_topology.startNetwork()
    except Exception as e:
        error(f"something wrong while building the network. Detailed info is as followed: {e}")
        current_topology.stopNetwork()
    info(f"{topology} 拓扑构建完成")


# 接收选择拓扑的请求
@app.route('/select_topology', methods=['POST'])
def handle_select_topology():
    data = request.json
    topology = data.get('topology')
    info(f"收到拓扑选择请求: {topology}")

    # 旧的拓扑判断
    # if topology not in [4, 6]:
    #     return jsonify({'error': 'Invalid topology'}), 400

    # 新的拓扑判断
    if topology not in ['fat4', 'fat6', 'demo']:
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

    info(f"Receive: {src_host}({src_ip}) → {dst_host}({dst_ip})")

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
        result = current_topology.modify_switch(swid, dst_host, dst_swid)
        return jsonify({'status': 'success', 'msg': '修改完成'})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})
   
@app.route('/save_topo_settings', methods=['POST'])
def save_settings():
    data = request.json
    try:
        with open('topo/style_settings.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return jsonify({'status': 'success', 'msg': '设置已保存'})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})

@app.route('/get_topo_settings', methods=['GET'])
def get_settings():
    try:
        if not os.path.exists('topo/style_settings.json'):
            # 返回默认设置
            default = {
                "host": {"shape": "ellipse", "color": "#FFD700", "size": 25},
                "switch": {"shape": "box", "color": "#87CEEB", "size": 25}
            }
            return jsonify(default)
        with open('topo/style_settings.json', 'r', encoding='utf-8') as f:
            settings = json.load(f)
            return jsonify(settings)
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)})
    
@app.route("/load_p4_code", methods=["POST"])
def load_p4_code():
    info("开始加载p4代码...")
    success = current_topology.clean_and_compile()
    info("p4代码加载完成")
    if success:
        return jsonify({"message": "P4 代码装载成功！"})
    return jsonify({"message": "P4 代码装载失败，请检查错误！"}), 500

@app.route("/inject_flow_table", methods=["POST"])
def inject_flow_table():
    info("开始注入流表...")
    success = current_topology.program_switches()
    info("流表注入完成")
    if success:
        return jsonify({"message": "流表注入成功！"})
    return jsonify({"message": "流表注入失败，请检查错误！"}), 500

# -------------ai大模型的调用逻辑--------------
# [新增] 拓扑文件上传与验证路由
@app.route("/upload_topology", methods=["POST"])
def upload_topology():
    if 'file' not in request.files or 'model' not in request.form:
        return jsonify({"error": "请求中没有找到文件或模型部分"}), 400
    
    file = request.files['file']
    model = request.form['model']
    if file.filename == '':
        return jsonify({"error": "没有选择任何文件"}), 400

    if not file or not file.filename.endswith('.json'):
        return jsonify({"error": "文件无效或不是.json格式"}), 400

    if model != deepseek and model != ecnu_ai:
        return jsonify({"error": "invalid model"}), 400
    
    try:
        content = file.read().decode('utf-8')
        topo_data = json.loads(content)
    except Exception as e:
        return jsonify({"error": f"JSON文件解析失败，请检查语法: {str(e)}"}), 400
  
    # --- START: 【核心修改】基于新格式的严格验证逻辑 ---
    try:
        # 1. 验证顶层必需的键是否存在
        required_keys = {"switch", "host", "link"}
        if not required_keys.issubset(topo_data.keys()):
            return jsonify({
                "error": "JSON格式错误：文件必须包含 'switch', 'host', 和 'link' 三个顶级键。",
                "template": "{ \"switch\": [...], \"host\": [...], \"link\": [...] }"
            }), 400
        
        # 2. 验证非 'switch', 'host', 'link' 的其他键是否存在
        allowed_keys = {"switch", "host", "link"}
        extra_keys = set(topo_data.keys()) - allowed_keys
        if extra_keys:
             return jsonify({"error": f"JSON格式错误：发现了不允许的顶级键: {', '.join(extra_keys)}"}), 400

        # 3. 创建所有已定义节点的集合，用于快速查找
        all_nodes = set(topo_data.get("switch", [])) | set(topo_data.get("host", []))
        if not all_nodes:
            return jsonify({"error": "JSON格式错误：'switch' 和 'host' 列表不能为空。"}), 400

        # 4. 遍历并验证 'link' 数组中的每一个链接对象
        for link_obj in topo_data.get("link", []):
            if not isinstance(link_obj, dict):
                 return jsonify({"error": f"JSON格式错误：link数组中的元素必须是对象 (字典)。出错的元素: {link_obj}"}), 400

            # a. 验证每个对象是否正好包含两个键 (代表一个连接的两个端点)
            endpoints = list(link_obj.keys())
            if len(endpoints) != 2:
                return jsonify({"error": f"JSON格式错误：link对象必须正好包含两对键值对。出错的对象: {link_obj}"}), 400
            
            # b. 验证这个链接是否是双向的 (key1:value1, key2:value2 -> key1==value2, key2==value1)
            ep1, ep2 = endpoints[0], endpoints[1]
            if not (link_obj.get(ep1) == ep2 and link_obj.get(ep2) == ep1):
                return jsonify({"error": f"JSON格式错误：link对象必须是双向的 (例如 {{'h1':'s1', 's1':'h1'}})。出错的对象: {link_obj}"}), 400

            # c. 验证链接的两个端点是否都在已定义的节点集合中
            if not {ep1, ep2}.issubset(all_nodes):
                undefined_node = ep1 if ep1 not in all_nodes else ep2
                return jsonify({"error": f"JSON格式错误：link中包含未在'switch'或'host'中定义的节点ID '{undefined_node}'。"}), 400

    except TypeError as e:
        return jsonify({"error": f"JSON数据类型错误，请检查所有值是否为正确的类型 (列表、字符串、对象等)。错误详情: {e}"}), 400
    # --- END: 验证逻辑结束 ---

    # 验证通过，将拓扑数据存入session，并初始化对话
    session['topology_data'] = topo_data
    session_id = secure_session_id()
    session['session_id'] = session_id
    
    initial_prompt = "请对以下网络拓扑进行初步分析，并以Markdown格式返回。拓扑结构如下："
    
    try:
        # 这里的 call_llm
        response_data = call_llm(model, session_id, initial_prompt, json.dumps(topo_data, indent=2))
        print(response_data)
        return jsonify({
            "message": "文件上传成功并通过验证！",
            "session_id": session_id,
            "initial_response": response_data,
            "build_enabled": True,
            "download_links": {
                "script": "/download/network_script",
                "config": "/download/topology_json"
            }
        })
    except Exception as e:
        info(f"Error calling LLM after upload: {e}") # 在服务器端打印错误日志
        return jsonify({"error": f"AI服务调用失败: {str(e)}"}), 502

# [新增] 对话路由
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message")
    session_id = session.get("session_id") # 从session中安全地获取session_id

    if not session_id:
        return jsonify({"error": "对话未初始化，请先上传拓扑文件。"}), 403
    
    if not user_message:
        return jsonify({"error": "消息内容不能为空。"}), 400

    # 这里不再需要传递拓扑信息，因为它已经包含在Redis的历史记录中了
    response_data = call_llm(session_id, user_message)
    
    # 假设 response_data 是一个包含分析、代码、问题等内容的复杂JSON字符串
    return jsonify(response_data)

# 路由1: 用于下载静态的 network.py 文件
@app.route('/download/network_script')
def download_network_script():
    # 从session中检查拓扑是否已上传，增加安全性，防止随意下载
    if 'topology_data' not in session:
        return "会话无效或已过期，请重新上传拓扑。", 403
    try:
        # 构建文件的安全路径
        script_path = os.path.join(app.root_path, 'topo', 'demo', 'network.py')
        return send_file(script_path, as_attachment=True)
    except FileNotFoundError:
        return "服务器上未找到 network.py 文件。", 404

# 路由2: 用于下载用户刚刚上传的、存储在session中的 topology.json
@app.route('/download/topology_json')
def download_topology_json():
    # 同样可以保留 session 检查作为权限控制
    if 'topology_data' not in session:
        return "会话无效或已过期，请重新上传拓扑。", 403
    try:
        # 构建 topology.json 的安全路径
        json_path = os.path.join(app.root_path, 'topology.json')
        return send_file(json_path, as_attachment=True, mimetype='json')
    except FileNotFoundError:
        return "服务器上未找到 application/topology.json 文件。", 404

# 清除redis内存  
@atexit.register
def cleanup_redis():
    info("quiting Flask, cleanning all the history")
    keys = r.keys("chat_history:*")
    if keys:
        r.delete(*keys)
# -------------ai大模型的调用逻辑--------------




# -------------demo的新增后端代码---------------
@app.route('/get_topology_data_demo')
def get_topology_data_demo():
    # 假设你保存的是 txt 文件，可以在构建拓扑时自动写入或读取已有文件
    edges = []
    try:
        with open('topo/demo/topo.txt', 'r') as f:
            for line in f:
                # 格式：(s1, h1)
                line = line.strip().replace('(', '').replace(')', '').replace(',', '')
                parts = line.split()
                if len(parts) == 2:
                    edges.append({'from': parts[0], 'to': parts[1]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return jsonify(edges)



# -------------demo的新增后端代码---------------



# 启动服务
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)