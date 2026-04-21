import json
import os

from flask import Blueprint, current_app, jsonify, request, send_file, session
from p4utils.mininetlib.log import error, info

from LLM import call_llm, deepseek, ecnu_ai, secure_session_id
from error import InvalidModelException
from services.topology_service import (
    build_llm_topology_payload,
    build_topology_summary,
    get_generated_intent_path,
    get_generated_network_script_path,
    get_uploaded_topology_path,
    instantiate_uploaded_topology,
    load_uploaded_topology_data,
    persist_intent,
    persist_uploaded_topology,
    validate_uploaded_topology_payload,
)
from services.topology_state import switch_current_topology


upload_api = Blueprint('upload_api', __name__)


@upload_api.route('/upload_topology', methods=['POST'])
def upload_topology():
    if 'file' not in request.files or 'model' not in request.form:
        return jsonify({'error': '请求中没有找到文件或模型部分'}), 400

    file = request.files['file']
    model = request.form['model']
    if file.filename == '':
        return jsonify({'error': '没有选择任何文件'}), 400

    if not file or not file.filename.endswith('.json'):
        return jsonify({'error': '文件无效或不是.json格式'}), 400

    if model not in {deepseek, ecnu_ai}:
        return jsonify({'error': 'invalid model'}), 400

    try:
        content = file.read().decode('utf-8')
        topo_data = json.loads(content)
    except Exception as exc:
        return jsonify({'error': f'JSON文件解析失败，请检查语法: {str(exc)}'}), 400

    if not isinstance(topo_data, dict):
        return jsonify({'error': 'JSON格式错误：文件顶层必须是对象，不能是数组或其他类型。'}), 400

    try:
        topo_data = validate_uploaded_topology_payload(topo_data)
    except ValueError as exc:
        return jsonify({
            'error': str(exc),
            'template': json.dumps({
                'intent_description': '例如：h1 到 h2 的流量优先走低时延路径，必须经过 s2，避免经过 s3。',
                'switch': ['s1', 's2', 's3', 's4'],
                'host': ['h1', 'h2'],
                'link': [
                    {'h1': 's1', 's1': 'h1'},
                    {'s1': 's2', 's2': 's1'},
                    {'s2': 's4', 's4': 's2'},
                    {'s4': 'h2', 'h2': 's4'},
                ],
            }, ensure_ascii=False, indent=2),
        }), 400
    except TypeError as exc:
        return jsonify({'error': f'JSON数据类型错误，请检查所有值是否为正确的类型 (列表、字符串、对象等)。错误详情: {exc}'}), 400

    session['topology_data'] = topo_data
    session['model'] = model
    session_id = secure_session_id()
    session['session_id'] = session_id

    try:
        switch_current_topology(instantiate_uploaded_topology(current_app.root_path, topo_data))
    except PermissionError:
        runtime_dir = os.path.join(current_app.root_path, 'topo', 'user_topology')
        return jsonify({
            'error': (
                '上传拓扑运行目录不可写，无法生成动态拓扑实例。'
                f'请修复目录权限后重试：{runtime_dir}'
            )
        }), 500
    except Exception as exc:
        error(f"根据上传配置实例化动态拓扑失败: {exc}\n")
        return jsonify({'error': f'后端生成动态拓扑实例失败: {str(exc)}'}), 500

    initial_prompt = (
        '请结合用户上传的网络拓扑与其中的 intent_description 进行初步分析，并以Markdown格式返回。'
        '其中 intent_description 是用户对网络编排目标的说明，你需要优先根据这段说明生成对应的结构化 intent.json。'
        '输入内容如下：'
    )

    try:
        llm_payload = build_llm_topology_payload(topo_data)
        response_data = call_llm(model, session_id, initial_prompt, json.dumps(llm_payload, ensure_ascii=False, indent=2))
        if not response_data.get('success'):
            raise RuntimeError(response_data.get('analysis') or 'AI 服务未返回成功状态')
        normalized_intent, _ = persist_intent(current_app.root_path, response_data.get('intent', {}))
        session['intent_data'] = normalized_intent
        return jsonify({
            'message': '文件上传成功并通过验证！',
            'session_id': session_id,
            'topology_summary': build_topology_summary(topo_data),
            'initial_response': response_data,
            'build_enabled': True,
            'download_links': {
                'script': '/download/network_script',
                'config': '/download/topology_json',
                'intent': '/download/intent_json',
            },
            'intent_apply_url': '/apply_intent',
        })
    except Exception as exc:
        info(f'Error calling LLM after upload: {exc}')
        return jsonify({'error': f'AI服务调用失败: {str(exc)}'}), 502


@upload_api.route('/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_message = data.get('message')
    session_id = session.get('session_id')
    model = session.get('model')

    if not session_id:
        return jsonify({'error': '对话未初始化，请先上传拓扑文件。'}), 403

    if not user_message:
        return jsonify({'error': '消息内容不能为空。'}), 400

    try:
        response_data = call_llm(model, session_id, user_message, None)
    except InvalidModelException:
        return jsonify({'error': '模型无效。'}), 400

    if not response_data.get('success'):
        return jsonify({'error': 'AI服务调用失败。'}), 502

    normalized_intent, _ = persist_intent(current_app.root_path, response_data.get('intent', {}))
    session['intent_data'] = normalized_intent
    return jsonify(response_data)


@upload_api.route('/download/network_script')
def download_network_script():
    if 'topology_data' not in session:
        return '会话无效或已过期，请重新上传拓扑。', 403

    try:
        script_path = get_generated_network_script_path(current_app.root_path)
        if not os.path.exists(script_path):
            topo_data = load_uploaded_topology_data(current_app.root_path, session.get('topology_data'))
            if topo_data is None:
                return '服务器上未找到已上传的拓扑配置。', 404
            persist_uploaded_topology(current_app.root_path, topo_data)
        return send_file(script_path, as_attachment=True)
    except FileNotFoundError:
        return '服务器上未找到 network.py 文件。', 404


@upload_api.route('/download/topology_json')
def download_topology_json():
    if 'topology_data' not in session:
        return '会话无效或已过期，请重新上传拓扑。', 403

    try:
        json_path = get_uploaded_topology_path(current_app.root_path)
        if not os.path.exists(json_path):
            topo_data = load_uploaded_topology_data(current_app.root_path, session.get('topology_data'))
            if topo_data is None:
                return '服务器上未找到上传后的 topology.json 文件。', 404
            persist_uploaded_topology(current_app.root_path, topo_data)
        return send_file(json_path, as_attachment=True, mimetype='application/json')
    except FileNotFoundError:
        return '服务器上未找到上传后的 topology.json 文件。', 404


@upload_api.route('/download/intent_json')
def download_intent_json():
    if 'session_id' not in session:
        return '会话无效或已过期，请重新上传拓扑。', 403

    try:
        intent_path = get_generated_intent_path(current_app.root_path)
        if not os.path.exists(intent_path):
            normalized_intent, intent_path = persist_intent(current_app.root_path, session.get('intent_data', {}))
            session['intent_data'] = normalized_intent
        return send_file(intent_path, as_attachment=True, download_name='intent.json', mimetype='application/json')
    except FileNotFoundError:
        return '服务器上未找到 intent.json 文件。', 404


@upload_api.route('/apply_intent', methods=['POST'])
def apply_intent():
    if 'session_id' not in session:
        return jsonify({'error': '对话未初始化，请先上传拓扑文件。'}), 403

    intent_data = session.get('intent_data', {})
    normalized_intent, intent_path = persist_intent(current_app.root_path, intent_data)
    flow_count = len(normalized_intent.get('flows', []))

    return jsonify({
        'status': 'success',
        'message': 'intent.json 已提交到后端编排接口（演示版）。当前版本仅完成意图接入与记录，暂未实际下发到拓扑。',
        'intent_path': intent_path,
        'flow_count': flow_count,
        'summary': normalized_intent.get('summary', ''),
    })