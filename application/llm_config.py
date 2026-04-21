import copy
import json
import os

from topo.runtime_files import atomic_write_json


DEEPSEEK_MODEL = 'deepseek-chat'
ECNU_MODEL = 'ecnu-max'

_DEFAULT_SETTINGS = {
    'deepseek': {
        'model': DEEPSEEK_MODEL,
        'base_url': 'https://api.deepseek.com/v1',
        'api_key': '',
    },
    'ecnu': {
        'model': ECNU_MODEL,
        'base_url': '',
        'api_key': '',
    },
}

_ENV_MAPPING = {
    'deepseek': {
        'base_url': ['DEEPSEEK_BASE_URL', 'OPENAI_BASE_URL'],
        'api_key': ['DEEPSEEK_API_KEY', 'OPENAI_API_KEY'],
    },
    'ecnu': {
        'base_url': ['ECNU_AI_BASE_URL'],
        'api_key': ['ECNU_AI_API_KEY'],
    },
}


def get_llm_settings_path():
    return os.path.join(os.path.dirname(__file__), 'instance', 'llm_config.json')


def _read_file_settings():
    settings_path = get_llm_settings_path()
    if not os.path.exists(settings_path):
        return {}

    try:
        with open(settings_path, 'r', encoding='utf-8') as config_file:
            payload = json.load(config_file)
    except (OSError, json.JSONDecodeError):
        return {}

    return payload if isinstance(payload, dict) else {}


def _merge_provider(base_settings, provider_name, override_settings):
    provider_settings = override_settings.get(provider_name, {})
    if not isinstance(provider_settings, dict):
        return

    for field_name in ('base_url', 'api_key', 'model'):
        if field_name in provider_settings and isinstance(provider_settings[field_name], str):
            base_settings[provider_name][field_name] = provider_settings[field_name].strip()


def _apply_env_overrides(settings):
    for provider_name, field_mapping in _ENV_MAPPING.items():
        for field_name, env_names in field_mapping.items():
            for env_name in env_names:
                env_value = os.environ.get(env_name, '').strip()
                if env_value:
                    settings[provider_name][field_name] = env_value
                    break


def load_llm_settings():
    settings = copy.deepcopy(_DEFAULT_SETTINGS)
    file_settings = _read_file_settings()
    _merge_provider(settings, 'deepseek', file_settings)
    _merge_provider(settings, 'ecnu', file_settings)
    _apply_env_overrides(settings)
    return settings


def save_llm_settings(settings):
    normalized_settings = copy.deepcopy(_DEFAULT_SETTINGS)
    if isinstance(settings, dict):
        _merge_provider(normalized_settings, 'deepseek', settings)
        _merge_provider(normalized_settings, 'ecnu', settings)

    atomic_write_json(get_llm_settings_path(), normalized_settings, ensure_ascii=False, indent=2)
    return normalized_settings


def get_provider_settings(model_name):
    settings = load_llm_settings()
    if model_name == settings['deepseek']['model']:
        return settings['deepseek']
    if model_name == settings['ecnu']['model']:
        return settings['ecnu']
    return None