# 待办事项后端 API

## 概述

本 API 为待办事项网页应用提供后端数据能力，覆盖新增、查看、编辑、删除、完成状态切换等操作。后端使用 JSON 文件持久化数据，服务重启后数据不丢失。

- 基础路径：`/api`
- 所有请求和响应均使用 JSON 格式（删除接口除外）

## 数据模型

待办对象字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | string | 待办唯一标识 |
| content | string | 待办内容（去首尾空格后非空） |
| completed | boolean | 是否已完成 |
| createdAt | string | 创建时间（ISO 8601 UTC） |
| updatedAt | string | 最近更新时间（ISO 8601 UTC） |

示例：

```json
{
  "id": "e3b0c44298fc4c149afbf4c8996fb924",
  "content": "买菜",
  "completed": false,
  "createdAt": "2025-01-01T00:00:00.000Z",
  "updatedAt": "2025-01-01T00:00:00.000Z"
}
```

## 错误响应

错误统一返回 JSON，包含 `error` 字段：

```json
{"error": "待办内容不能为空"}
```

常见状态码：

- 400：请求体格式错误 / 校验失败
- 404：待办不存在
- 500：服务内部错误

## 接口列表

### 1. 查看待办列表

- 方法：GET
- 路径：`/api/todos`
- 说明：返回所有待办事项，按创建时间从旧到新排序。
- 请求：无
- 请求示例：`GET /api/todos`
- 响应示例（200）：

```json
[
  {
    "id": "e3b0c44298fc4c149afbf4c8996fb924",
    "content": "买菜",
    "completed": false,
    "createdAt": "2025-01-01T00:00:00.000Z",
    "updatedAt": "2025-01-01T00:00:00.000Z"
  }
]
```

### 2. 新增待办

- 方法：POST
- 路径：`/api/todos`
- 说明：创建一条待办。`content` 必填，去除首尾空格后不能为空。
- 请求体：

```json
{"content": "买菜"}
```

- 响应（201）：

```json
{
  "id": "e3b0c44298fc4c149afbf4c8996fb924",
  "content": "买菜",
  "completed": false,
  "createdAt": "2025-01-01T00:00:00.000Z",
  "updatedAt": "2025-01-01T00:00:00.000Z"
}
```

- 错误示例（400）：`{"error": "待办内容不能为空"}`

### 3. 查看单个待办

- 方法：GET
- 路径：`/api/todos/{id}`
- 说明：根据 id 获取一条待办。
- 响应（200）：见上方待办对象示例
- 错误（404）：`{"error":"待办不存在"}`

### 4. 编辑待办内容

- 方法：PUT
- 路径：`/api/todos/{id}`
- 说明：整体更新待办内容。`content` 必填。
- 请求体：`{"content": "买水果"}`
- 响应（200）：更新后的待办对象
- 错误（400 / 404）

### 5. 切换完成状态 / 部分更新

- 方法：PATCH
- 路径：`/api/todos/{id}`
- 说明：支持更新 `content` 或 `completed` 或两者同时更新。
- 请求体示例：`{"completed": true}` 或 `{"content": "买水果"}` 或 `{"content":"买水果","completed":true}`
- 响应（200）：更新后的待办对象
- 错误（400 / 404）

### 6. 删除待办

- 方法：DELETE
- 路径：`/api/todos/{id}`
- 说明：删除指定待办。删除成功返回 204，无响应体。
- 响应（204）
- 错误（404）：`{"error":"待办不存在"}`

## 与 PRD 验收标准的对应关系

- AC2 / AC3：新增 → `POST /api/todos`
- AC4：空内容校验 → `POST` 返回 400
- AC5 / AC6 / AC7：编辑 → `PUT /api/todos/{id}` 或 `PATCH`
- AC8 / AC9：删除 → `DELETE /api/todos/{id}`（确认对话框由前端负责，删除接口本身为一次性删除）
- AC10：完成状态切换 → `PATCH /api/todos/{id}` 传入 `{"completed": ...}`
- AC11 / AC12 / AC13：数据持久化 → 后端 JSON 文件存储，列表接口返回全部记录
