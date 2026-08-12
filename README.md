# 比目鱼（Bimuyu）

一人设计工作室 AI 管理工具 — 对外展示站 + 对内管理后台。

## 快速启动

```bash
# 1. 进入项目目录
cd ~/Desktop/bimuyu-os

# 2. 创建虚拟环境（推荐，只需第一次）
python3 -m venv venv
source venv/bin/activate

# 3. 安装依赖（只需第一次）
pip install -r requirements.txt

# 4. 初始化数据库（只需第一次）
python -m app.init_db

# 5. 启动网站
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 浏览器访问

| 地址 | 说明 |
|------|------|
| http://localhost:8000 | 对外展示站首页 |
| http://localhost:8000/cases | 案例列表 |
| http://localhost:8000/about | 关于页 |
| http://localhost:8000/app/login | 管理后台登录 |

## 默认登录账号

- **邮箱**：`admin@bimuyu.work`
- **密码**：`admin123`

## 停止服务

在终端按 `Ctrl + C`

## 项目结构

```
bimuyu-os/
├── app/           # 后端代码
├── templates/     # 页面模板
├── static/        # CSS、图片
├── data/          # 数据库和上传文件
├── contact.json   # 公开站联系方式
└── SPEC.md        # 完整需求文档
```
