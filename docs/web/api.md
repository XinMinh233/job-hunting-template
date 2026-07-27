# API 与 SSE 协议

所有业务接口都使用 Cookie 会话。除登录和只读 GET 外，写接口必须带当前会话返回的 `X-CSRF-Token`。JSON 错误使用 FastAPI 的 `{"detail": ...}`；浏览器不得根据错误文本决定权限。

## 认证

- `POST /api/auth/login`：`{"username","password"}`。
- `POST /api/auth/logout`：注销当前 Web 会话。
- `GET /api/auth/me`：当前用户、角色、CSRF 和额度。
- `POST /api/auth/change-password`：`{"current_password","new_password"}`。

临时密码首次登录后，除改密与登出外的业务接口返回 `password_change_required`。

## 会话与任务

- `GET /api/chats`：未归档会话。
- `POST /api/chats`：创建会话。
- `GET /api/chats/{id}/messages`：历史消息。
- `POST /api/chats/{id}/messages`：创建任务，返回 `{"job_id","status":"queued"}`。
- `POST /api/chats/{id}/archive`：无活动任务时归档。
- `GET /api/jobs/{id}/events?after=0`：SSE。
- `POST /api/jobs/{id}/stop`：停止本人任务。
- `GET /api/usage`：当天任务与 Token。

SSE 每个数据帧的 `data` 是统一信封：

```json
{
  "seq": 12,
  "job_id": "任务 UUID",
  "type": "text_delta",
  "data": {"text": "新增文本"}
}
```

事件类型只允许：

- `status`：排队、启动、中断等可读状态。
- `text_delta`：可展示文本增量。
- `tool`：工具名、净化后的说明和状态；不含输入参数、命令或推理。
- `artifact`：新产物相对路径。
- `done`：成功结束。
- `error`：净化后的失败信息。

客户端记录最后 `seq`，重连时传 `after=<seq>`。任务达到终态且历史事件补发完毕后，服务端关闭 SSE。

## 文件

- `GET /api/files`：Runner 在白名单根目录中列出的文件。
- `POST /api/files/upload`：multipart 字段 `upload`。
- `GET /api/files/download?path=...&inline=true`：认证下载或预览。
- `GET /api/files/preview?path=...`：读取不超过 2 MB 的 UTF-8 Markdown，供站内安全预览页渲染。

允许根目录仅为 `master.md`、`base/`、`tailored/`、`dist/`、`data/` 和 `uploads/`。上传原文件与 PDF/DOCX 提取文本都进入随机 UUID 子目录。

## 管理

- `GET/POST /api/admin/users`
- `POST /api/admin/users/{id}/disable`
- `POST /api/admin/users/{id}/enable`
- `POST /api/admin/users/{id}/reset-password`
- `PUT /api/admin/users/{id}/quota`
- `POST /api/admin/users/{id}/upgrade-template`
- `GET /api/admin/jobs`
- `POST /api/admin/jobs/{id}/stop`
- `GET /api/admin/audit`

临时密码只在创建或重置响应中出现一次，不写入审计详情。

## Runner 协议

Unix socket 每次连接处理一个换行结尾的 JSON 请求。外部调用者不能提供 Linux 用户名、路径、环境变量或任意命令。

核心动作：`provision`、`enable`、`disable`、`run`、`stop`、`upgrade`、`health`。由于 Web 服务不能读取 `0700` workspace，另有固定的 `file_list`、`file_import`、`file_read`；三者都强制内部 UUID、白名单路径和符号链接检查，不接受 shell 字符串。
