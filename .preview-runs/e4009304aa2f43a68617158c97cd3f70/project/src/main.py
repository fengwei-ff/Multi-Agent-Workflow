#!/usr/bin/env python3
"""待办事项后端 API（仅使用 Python 标准库）。"""

import argparse
import json
import os
import re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from uuid import uuid4

TODO_STORE_PATH = os.environ.get("TODO_STORE_PATH", "todos.json")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TodoStore:
    """基于 JSON 文件的待办事项存储。"""

    def __init__(self, path: str | None = None):
        self.path = path or TODO_STORE_PATH
        self.todos: dict[str, dict] = {}
        self.load()

    def load(self) -> None:
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
                items = data.get("items", [])
                self.todos = {item["id"]: item for item in items}
        else:
            self.todos = {}

    def persist(self) -> None:
        items = sorted(self.todos.values(), key=lambda x: x["created_at"])
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump({"items": items}, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.path)

    def list(self) -> list[dict]:
        return sorted(self.todos.values(), key=lambda x: x["created_at"])

    def get(self, todo_id: str) -> dict | None:
        return self.todos.get(todo_id)

    def create(self, content: str) -> dict:
        if not isinstance(content, str) or not content.strip():
            raise ValueError("待办内容不能为空")
        now = utc_now_iso()
        todo = {
            "id": uuid4().hex,
            "content": content.strip(),
            "completed": False,
            "created_at": now,
            "updated_at": now,
        }
        self.todos[todo["id"]] = todo
        self.persist()
        return todo

    def update_content(self, todo_id: str, content: str) -> dict | None:
        if not isinstance(content, str) or not content.strip():
            raise ValueError("待办内容不能为空")
        todo = self.get(todo_id)
        if not todo:
            return None
        todo["content"] = content.strip()
        todo["updated_at"] = utc_now_iso()
        self.persist()
        return todo

    def update_completed(self, todo_id: str, completed: bool) -> dict | None:
        todo = self.get(todo_id)
        if not todo:
            return None
        if not isinstance(completed, bool):
            raise ValueError("completed 必须为布尔值")
        todo["completed"] = completed
        todo["updated_at"] = utc_now_iso()
        self.persist()
        return todo

    def delete(self, todo_id: str) -> bool:
        if todo_id in self.todos:
            del self.todos[todo_id]
            self.persist()
            return True
        return False


class TodoAPIHandler(BaseHTTPRequestHandler):
    server_version = "TodoAPI/1.0"

    # ---------- HTTP 辅助方法 ----------
    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_empty(self, status: int = 204) -> None:
        self.send_response(status)
        self._send_cors_headers()
        self.end_headers()

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _read_json_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) else None

    # ---------- 路由 ----------
    def _match_list(self, path: str) -> bool:
        return bool(re.fullmatch(r"/api/todos/?", path))

    def _match_detail(self, path: str) -> str | None:
        m = re.fullmatch(r"/api/todos/([^/]+)", path)
        return m.group(1) if m else None

    # ---------- HTTP 方法 ----------
    def do_OPTIONS(self) -> None:
        self._send_empty(204)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if self._match_list(path):
            items = self.server.store.list()
            self._send_json(200, {"data": items})
            return
        todo_id = self._match_detail(path)
        if todo_id:
            todo = self.server.store.get(todo_id)
            if todo is None:
                self._send_json(404, {"error": {"code": "NOT_FOUND", "message": "待办不存在"}})
            else:
                self._send_json(200, {"data": todo})
            return
        self._send_json(404, {"error": {"code": "NOT_FOUND", "message": "接口不存在"}})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if not self._match_list(path):
            self._send_json(404, {"error": {"code": "NOT_FOUND", "message": "接口不存在"}})
            return
        body = self._read_json_body()
        if body is None:
            self._send_json(400, {"error": {"code": "INVALID_JSON", "message": "请求体不是合法 JSON"}})
            return
        try:
            todo = self.server.store.create(body.get("content"))
        except ValueError as exc:
            self._send_json(400, {"error": {"code": "VALIDATION_ERROR", "message": str(exc)}})
            return
        self._send_json(201, {"data": todo})

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        todo_id = self._match_detail(path)
        if not todo_id:
            self._send_json(404, {"error": {"code": "NOT_FOUND", "message": "接口不存在"}})
            return
        body = self._read_json_body()
        if body is None:
            self._send_json(400, {"error": {"code": "INVALID_JSON", "message": "请求体不是合法 JSON"}})
            return
        try:
            todo = self.server.store.update_content(todo_id, body.get("content"))
        except ValueError as exc:
            self._send_json(400, {"error": {"code": "VALIDATION_ERROR", "message": str(exc)}})
            return
        if todo is None:
            self._send_json(404, {"error": {"code": "NOT_FOUND", "message": "待办不存在"}})
            return
        self._send_json(200, {"data": todo})

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        todo_id = self._match_detail(path)
        if not todo_id:
            self._send_json(404, {"error": {"code": "NOT_FOUND", "message": "接口不存在"}})
            return
        body = self._read_json_body()
        if body is None:
            self._send_json(400, {"error": {"code": "INVALID_JSON", "message": "请求体不是合法 JSON"}})
            return
        if "completed" not in body:
            self._send_json(400, {"error": {"code": "VALIDATION_ERROR", "message": "缺少 completed 字段"}})
            return
        try:
            todo = self.server.store.update_completed(todo_id, body.get("completed"))
        except ValueError as exc:
            self._send_json(400, {"error": {"code": "VALIDATION_ERROR", "message": str(exc)}})
            return
        if todo is None:
            self._send_json(404, {"error": {"code": "NOT_FOUND", "message": "待办不存在"}})
            return
        self._send_json(200, {"data": todo})

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        todo_id = self._match_detail(path)
        if not todo_id:
            self._send_json(404, {"error": {"code": "NOT_FOUND", "message": "接口不存在"}})
            return
        deleted = self.server.store.delete(todo_id)
        if not deleted:
            self._send_json(404, {"error": {"code": "NOT_FOUND", "message": "待办不存在"}})
            return
        self._send_empty(204)

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} - {format % args}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="待办事项后端 API")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    args = parser.parse_args()

    store = TodoStore()
    server = ThreadingHTTPServer((args.host, args.port), TodoAPIHandler)
    server.store = store
    print(f"Todo API serving at http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
