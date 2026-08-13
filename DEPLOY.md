# 部署 bimuyu-os

bimuyu-os 是一个 **FastAPI + SQLite** 的 Web 应用（对外展示站 + 对内管理后台），默认运行在 `0.0.0.0:8013`。下面给出三种部署方式。

---

## 1. 本地运行（开发 / 自托管最简）

```bash
# 进入项目目录
cd bimuyu-os

# 虚拟环境（仅首次）
python3 -m venv venv
source venv/bin/activate

# 依赖（仅首次）
pip install -r requirements.txt

# 初始化数据库（仅首次，自动建表并写入默认管理员）
python -m app.init_db

# 启动
uvicorn app.main:app --host 0.0.0.0 --port 8013
```

访问 http://localhost:8013/app/login
默认管理员：`admin@bimuyu.work` / `admin123`

生产环境建议加 `--workers` 或用进程管理器（systemd / supervisor），例如：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8013 --workers 2
```

---

## 2. Docker 部署（推荐用于服务器 / VPS）

### 2.1 直接用命令构建并运行

```bash
docker build -t bimuyu-os .
docker run -d --name bimuyu-os \
  -p 8013:8013 \
  -v "$(pwd)/data:/app/data" \
  bimuyu-os
```

> ⚠️ 务必挂载 `data/` 卷，否则容器重启后 SQLite 数据与上传文件会丢失。
> 首次启动进入容器执行一次 `python -m app.init_db` 写入默认管理员（或在镜像启动命令里加 `&& python -m app.init_db`）。

### 2.2 最小化 Dockerfile（如仓库未附带，可自行创建）

```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN python -m app.init_db || true

EXPOSE 8013
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8013"]
```

### 2.3 反向代理（Nginx 示例片段）

```nginx
location / {
    proxy_pass http://127.0.0.1:8013;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

---

## 3. Vercel 部署（注意 SQLite 持久化限制）

> ⚠️ **重要**：Vercel 的函数文件系统是临时且只读的（除 `/tmp`），**SQLite 数据库无法在多次请求间持久保存**，APScheduler 后台调度也无法常驻。
> 因此 Vercel 更适合托管**静态前端 / 营销站（如 `bimuyu-web`）**；完整 bimuyu-os（含后台、调度、数据库）建议用上面的 Docker / 服务器方式，或改用 Railway、Render、Fly.io 等支持常驻进程 + 持久磁盘的平台。

若仅做轻量演示 / 只读展示，可用 Vercel 的 Python 服务端函数为入口（需把 SQLite 换成外部数据库如 Supabase / Neon 才能持久化）：

`vercel.json`

```json
{
  "version": 2,
  "builds": [{ "src": "api/index.py", "use": "@vercel/python" }],
  "routes": [{ "src": "/(.*)", "dest": "api/index.py" }]
}
```

`api/index.py`（示例，仅转发到 ASGI app，持久化需外接数据库）

```python
from app.main import app

# Vercel 的 @vercel/python 会以 WSGI/ASGI 方式加载 `app`
# 注意：本地 SQLite 在 Vercel 上不持久，演示用途请外接 Postgres/MySQL。
```

**结论**：保持 bimuyu-os 默认 SQLite 部署时，**不要**用 Vercel 作为生产环境；优先 Docker（第 2 节）或常驻进程平台。

---

## 健康检查

部署后可用 `GET /health` 验证服务存活，正常返回：

```json
{ "status": "ok" }
```
