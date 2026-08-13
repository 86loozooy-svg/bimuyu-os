# bimuyu-os · 比目鱼（Bimuyu）

由 Studio OS 派生而来的**比目鱼品牌操作系统** —— 一人设计工作室的 AI 管理工具：对外展示站 + 对内管理后台。

## 快速开始

```bash
# 1. 进入项目目录
cd bimuyu-os

# 2. 创建并激活虚拟环境（仅首次）
python3 -m venv venv
source venv/bin/activate

# 3. 安装依赖（仅首次）
pip install -r requirements.txt

# 4. 初始化数据库（仅首次，会自动建表并写入默认管理员）
python -m app.init_db

# 5. 启动服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8013
```

启动后访问 http://localhost:8013/app/login

## 默认管理员

- 邮箱：`admin@bimuyu.work`
- 密码：`admin123`

## 本地测试

```bash
pip install pytest
pytest -q
```

冒烟探针验证：app 可正常导入、健康检查路由 `/health` 返回 200。

## 项目结构

```
bimuyu-os/
├── app/           # 后端（FastAPI）
├── templates/     # 页面模板
├── static/        # CSS、图片
├── data/          # 数据库与上传文件（bimuyu.db 由 init_db 自动生成，已被 .gitignore 忽略）
├── contact.json   # 公开站联系方式
└── SPEC.md        # 完整需求文档
```

## CI

推送至 `bimuyu-os` 分支会触发 GitHub Actions（`.github/workflows/ci.yml`）：Python 3.11 + 安装依赖 + 运行 pytest。
