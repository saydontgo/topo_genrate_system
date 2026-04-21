import json
import os
import tempfile


def _parent_dir(path):
    return os.path.dirname(path) or '.'


def atomic_write_text(path, content, encoding='utf-8'):
    parent_dir = _parent_dir(path)
    os.makedirs(parent_dir, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(prefix='.tmp-', dir=parent_dir)
    try:
        with os.fdopen(fd, 'w', encoding=encoding) as temp_file:
            temp_file.write(content)
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def atomic_write_json(path, payload, ensure_ascii=False, indent=2):
    atomic_write_text(path, json.dumps(payload, ensure_ascii=ensure_ascii, indent=indent) + '\n')


def copy_text_file(source_path, target_path, encoding='utf-8'):
    with open(source_path, 'r', encoding=encoding) as source_file:
        atomic_write_text(target_path, source_file.read(), encoding=encoding)


def prepare_output_path(path):
    parent_dir = _parent_dir(path)
    os.makedirs(parent_dir, exist_ok=True)

    if not os.path.exists(path):
        return

    if os.access(path, os.W_OK):
        return

    os.remove(path)


def prepare_p4_build_outputs(p4_source_path):
    source_root, _ = os.path.splitext(p4_source_path)
    prepare_output_path(source_root + '.json')
    prepare_output_path(p4_source_path + 'i')