# 开发环境

目标生产环境是 Python 3.11+、Ubuntu/Debian 和 systemd。macOS 本地开发只能验证 Web、数据库、协议和界面；不能等价验证 Linux UID、systemd sandbox 与目录越权。

## 安装

```bash
python3.11 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
```

创建仅供本地使用的环境变量：

```bash
export JOBHUNT_DATABASE_URL="sqlite:///$PWD/.runtime/dev.sqlite3"
export JOBHUNT_COOKIE_SECURE=false
export JOBHUNT_DEVELOPMENT_RUNNER=true
export JOBHUNT_DEVELOPMENT_ROOT="$PWD/.runtime/users"
export JOBHUNT_STAGING_ROOT="$PWD/.runtime/staging"
export JOBHUNT_SECRET_KEY="dev-local-only-change-me-32-characters"
```

开发 Runner 以普通目录模拟 provision、文件和 Claude 进程，不创建 Linux 用户。不要把 `JOBHUNT_DEVELOPMENT_RUNNER=true` 用于生产。

## 初始化与启动

```bash
alembic upgrade head
jobhunt-admin bootstrap-admin --username admin
uvicorn webapp.main:app --host 127.0.0.1 --port 8000 --reload
```

打开 `http://127.0.0.1:8000/login`。若需要真实对话，还必须设置内部代理可用的 DeepSeek Key，并确保本机 `claude` 已安装。开发环境也应使用专门测试 Key。

## 测试

```bash
pytest
python -m compileall -q webapp
```

纯单元测试覆盖密码、代理凭证、路径校验、stream-json 净化、模板升级和限额逻辑。真实 Linux 隔离、systemd、Caddy、DeepSeek 流式响应以及六条求职命令属于部署验收测试，必须在一次性 Ubuntu/Debian 测试机运行。

## 数据库迁移

修改模型后生成迁移并人工审阅：

```bash
alembic revision --autogenerate -m "中文变更说明"
alembic upgrade head
```

不要把 `Base.metadata.create_all()` 当成生产升级机制；应用入口调用它只用于首启容错，正式部署仍由 systemd 的 `ExecStartPre=alembic upgrade head` 驱动。

