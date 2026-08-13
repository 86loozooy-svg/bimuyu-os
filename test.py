"""Phase B 测试占位：基础冒烟探针（不覆盖业务）。

验证目标：
1. app 可正常导入（依赖解析 / 路由装配无错）
2. 健康检查路由 /health 返回 200 且 body.status == "ok"

实现说明：故意不使用 TestClient 的 `with` 上下文管理器，
以避免触发 startup 中的 APScheduler 后台线程导致 pytest 进程挂死。
"""
from fastapi.testclient import TestClient

from app.main import app


def test_app_importable():
    assert app is not None
    assert any(getattr(r, "path", None) == "/health" for r in app.routes)


def test_health_ok():
    client = TestClient(app)  # 不进 with 上下文 -> 不启动调度器
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
