import json
import os

from flask import Blueprint, current_app, jsonify, request

from llm_config import load_llm_settings, save_llm_settings
from topo.runtime_files import atomic_write_json


settings_api = Blueprint('settings_api', __name__)


DEFAULT_TOPOLOGY_STYLE_SETTINGS = {
    'host': {'shape': 'ellipse', 'color': '#FFD700', 'size': 25},
    'switch': {'shape': 'box', 'color': '#87CEEB', 'size': 25},
}


def _get_style_settings_path():
    return os.path.join(current_app.root_path, 'topo', 'style_settings.json')


@settings_api.route('/save_topo_settings', methods=['POST'])
def save_topology_settings():
    data = request.json
    try:
        atomic_write_json(_get_style_settings_path(), data, ensure_ascii=False, indent=2)
        return jsonify({'status': 'success', 'msg': '设置已保存'})
    except Exception as exc:
        return jsonify({'status': 'error', 'msg': str(exc)})


@settings_api.route('/get_llm_settings', methods=['GET'])
def get_llm_settings():
    return jsonify(load_llm_settings())


@settings_api.route('/save_llm_settings', methods=['POST'])
def save_llm_settings_route():
    data = request.json
    if not isinstance(data, dict):
        return jsonify({'status': 'error', 'msg': '配置格式错误'}), 400

    try:
        settings = save_llm_settings(data)
        return jsonify({'status': 'success', 'msg': 'AI 设置已保存', 'settings': settings})
    except Exception as exc:
        return jsonify({'status': 'error', 'msg': str(exc)}), 500


@settings_api.route('/get_topo_settings', methods=['GET'])
def get_topology_settings():
    try:
        settings_path = _get_style_settings_path()
        if not os.path.exists(settings_path):
            return jsonify(DEFAULT_TOPOLOGY_STYLE_SETTINGS)

        with open(settings_path, 'r', encoding='utf-8') as file_obj:
            settings = json.load(file_obj)
        return jsonify(settings)
    except Exception as exc:
        return jsonify({'status': 'error', 'msg': str(exc)})