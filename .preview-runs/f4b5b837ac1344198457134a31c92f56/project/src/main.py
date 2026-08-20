import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request

app = Flask(__name__)

DATA_FILE = Path(__file__).resolve().parent / 'data' / 'todos.json'


def load_todos():
    """从 JSON 文件加载待办数据。"""
    if not DATA_FILE.exists():
        return []
    with open(DATA_FILE, encoding='utf-8') as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def save_todos(todos):
    """将待办数据写入 JSON 文件。"""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, encoding='utf-8') as f:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(todos, f, ensure_ascii=False, indent=2)


def find_todo(todo_id):
    """按 id 查找待办。"""
    todos = load_todos()
    for todo in todos:
        if todo.get('id') == todo_id:
            return todo
    return None


def parse_iso(value):
    from datetime import datetime
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None


def iso_now():
    return datetime.now(timezone.utc).isoformat()


def validate_content(content, check_empty_only=False):
    """校验 content 字段。"""
    if not isinstance(content, str):
        return False, '请求体必须包含字符串类型的 content 字段'
    if not content.strip():
        return False, '待办内容不能为空'
    return True, None


@app.get('/api/todos')
def list_todos():
    todos = load_todos()
    todos.sort(key=lambda t: t.get('createdAt', ''))
    return jsonify(todos)


@app.post('/api/todos')
def create_todo():
    body = request.get_json(silent=True)
    if not body or not isinstance(body, dict):
        return jsonify({'error': '请求体必须为 JSON 对象'}), 400
    content = body.get('content')
    ok, err = validate_content(content)
    if not ok:
        return jsonify({'error': err}), 400

    now = iso_now()
    todo = {
        'id': str(uuid.uuid4()).replace('-', ''),
        'content': content.strip(),
        'completed': False,
        'createdAt': now,
        'updatedAt': now,
    }
    todos = load_todos()
    todos.append(todo)
    save_todos(todos)
    return jsonify(todo), 201


@app.put('/api/todos/<todo_id>')
def update_todo(todo_id):
    todos = load_todos()
    todo = find_todo(todo_id)
    if todo is None:
        return jsonify({'error': '待办不存在'}), 404
    body = request.get_json(silent=True)
    if not body or not isinstance(body, dict):
        return jsonify({'error': '请求体必须为 JSON 对象'}), 400
    content = body.get('content')
    if 'content' not in body:
        return jsonify({'error': '请求体必须包含 content 字段'}), 400
    ok, err = validate_content(content)
    if not ok:
        return jsonify({'error': err}), 400
    todo['content'] = content.strip()
    todo['updatedAt'] = iso_now()
    save_todos(todos)
    return jsonify(todo), 200


@app.patch('/api/todos/<todo_id>')
def patch_todo(todo_id):
    todos = load_todos()
    todo = find_todo(todo_id)
    if todo is None:
        return jsonify({'error': '待办不存在'}), 404
    body = request.get_json(silent=True)
    if not body or not isinstance(body, dict):
        return jsonify({'error': '请求体必须为 JSON 对象'}), 400

    if 'content' in body:
        content = body.get('content')
        ok, err = validate_content(content)
        if not ok:
            return jsonify({'error': err}), 400
        todo['content'] = content.strip()

    if 'completed' in body:
        completed = body.get('completed')
        if not isinstance(completed, bool):
            return jsonify({'error': 'completed 必须为布尔值'}), 400
        todo['completed'] = completed

    if 'content' not in body and 'completed' not in body:
        return jsonify({'error': '请求体必须包含 content 或 completed 字段'}), 400

    todo['updatedAt'] = iso_now()
    save_todos(todos)
    return jsonify(todo), 200


@app.delete('/api/todos/<todo_id>')
def delete_todo(todo_id):
    todos = load_todos()
    todo = find_todo(todo_id)
    if todo is None:
        return jsonify({'error': '待办不存在'}), 404
    todos = [t for t in todos if t.get('id') != todo_id]
    save_todos(todos)
    return '', 204


if __name__ == '__main__':
    app.run(debug=True)
