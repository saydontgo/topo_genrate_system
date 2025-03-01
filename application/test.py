from flask import Flask, render_template, jsonify, request
import topo.FatTree6.FatTree6 as ft6
app = Flask(__name__)

# 定义路由，渲染 HTML 文件
@app.route('/')
def home():
    return render_template('test.html')

@app.route('/trigger-action', methods=['GET'])
def trigger_action():
    # 获取查询参数
    message_type = request.args.get('message')

    # 根据参数返回不同的消息
    if message_type == '4' or message_type == '6':
        ft6.genrate_topo()
        return jsonify(message="Hello World")
    elif message_type == 'goodbye':
        return jsonify(message="Goodbye World")
    else:
        return jsonify(message="Unknown action")

@app.route('/process-input', methods=['POST'])
def process_input():
    # 获取前端传过来的 JSON 数据
    data = request.get_json()

    # 获取输入框的内容
    user_input = data.get('input')

    # 可以根据输入内容做任何操作，这里只是返回一个简单的响应
    if user_input:
        response_message = f"You entered: {user_input}"
        ft6.genrate_topo()
    else:
        response_message = "No input received."

    # 返回一个 JSON 响应
    return jsonify(message=response_message)

@app.route('/your-backend-endpoint', methods=['POST'])
def handle_topology():
    data = request.get_json()
    topology = data.get('topology')
    print(f'Received topology: {topology}')
    ft6.genrate_topo()
    return jsonify({'message': f'Topology {topology} received successfully'})


if __name__ == '__main__':
    app.run(debug=True)
