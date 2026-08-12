#!/usr/bin/env bash
# 第二批功能 E2E 验证：工人通讯录 + 施工团队排期 + 待办 + 里程碑自动任务 + 推送 + 通知配置 + 站内红点
set -u
BASE=http://127.0.0.1:8013
CJ=/tmp/batch2_cj.txt
rm -f "$CJ"
TODAY=$(date +%F)

echo "== 1. 登录 =="
code=$(curl -s -c "$CJ" -o /dev/null -w "%{http_code}" -X POST "$BASE/app/login" --data "identifier=admin@bimuyu.work&password=admin123")
echo "login http=$code"

echo "== 2. 工人通讯录页 / 待办页 / 通知配置 Tab 加载 =="
curl -s -b "$CJ" -o /dev/null -w "workers page http=%{http_code}\n" "$BASE/app/workers"
curl -s -b "$CJ" -o /dev/null -w "tasks page http=%{http_code}\n"   "$BASE/app/tasks"
curl -s -b "$CJ" -o /dev/null -w "notif tab http=%{http_code}\n"   "$BASE/app/settings?tab=notification"

echo "== 3. 新增工人 =="
curl -s -b "$CJ" -X POST "$BASE/app/workers/new" -F "name=张师傅" -F "role=木工" -F "phone=13900001234" -F "daily_rate=450" -F "status=active" -o /dev/null -w "add worker http=%{http_code}\n"
WID=$(./venv/bin/python - <<'PY'
from app.database import get_connection
c=get_connection()
r=c.execute("SELECT id FROM worker WHERE name='张师傅' ORDER BY id DESC LIMIT 1").fetchone()
print(r['id'] if r else 0)
c.close()
PY
)
echo "worker_id=$WID"

echo "== 4. 项目分配（设为现场负责人）=="
curl -s -b "$CJ" -X POST "$BASE/app/projects/1/assignments/new" -F "worker_id=$WID" -F "role_on_project=木工班长" -F "is_lead=on" -F "status=active" -o /dev/null -w "add assignment http=%{http_code}\n"
echo "team tab 含张师傅? $(curl -s -b "$CJ" "$BASE/app/projects/1?tab=team" | grep -c 张师傅)"

echo "== 5. 手动创建待办（今日到期）=="
curl -s -b "$CJ" -X POST "$BASE/app/tasks/new" -F "title=确认现场交底" -F "project_id=1" -F "due_date=$TODAY" -F "priority=high" -o /dev/null -w "add task http=%{http_code}\n"

echo "== 6. Dashboard 今日待办卡片 =="
echo "dashboard 含『今日待办』? $(curl -s -b "$CJ" "$BASE/app/" | grep -c 今日待办)"

echo "== 7. 站内红点计数 =="
curl -s -b "$CJ" "$BASE/app/tasks/count"; echo

echo "== 8. 配置通知（启用 + 假 webhook）并立即推送 =="
curl -s -b "$CJ" -X POST "$BASE/app/settings/notification" -F "push_enabled=on" -F "push_time=08:00" -F "feishu_webhook=http://127.0.0.1:9/hook" -o /dev/null -w "save notify http=%{http_code}\n"
curl -s -b "$CJ" -X POST "$BASE/app/tasks/push-now" -o /dev/null -w "push-now http=%{http_code}\n"
./venv/bin/python - <<'PY'
from app.database import get_connection
c=get_connection()
r=c.execute("SELECT pushed_at FROM task WHERE title='确认现场交底' ORDER BY id DESC LIMIT 1").fetchone()
print("task pushed_at after push:", r['pushed_at'] if r else None)
c.close()
PY

echo "== 9. 里程碑自动生成任务 =="
curl -s -b "$CJ" -X POST "$BASE/app/projects/1/milestones/add" -F "name=隐蔽工程验收" -F "start_date=$TODAY" -F "end_date=$TODAY" -F "status=active" -o /dev/null -w "add milestone http=%{http_code}\n"
./venv/bin/python - <<'PY'
from app.database import get_connection
c=get_connection()
rows=c.execute("SELECT id, milestone_id FROM task WHERE source='milestone' AND title LIKE '里程碑：隐蔽工程验收'").fetchall()
print("auto tasks:", [(r['id'], r['milestone_id']) for r in rows])
c.close()
PY

echo "== 10. 删除里程碑 → 关联任务应被清理 =="
MID=$(./venv/bin/python - <<'PY'
from app.database import get_connection
c=get_connection()
r=c.execute("SELECT id FROM project_milestones WHERE name='隐蔽工程验收' ORDER BY id DESC LIMIT 1").fetchone()
print(r['id'] if r else 0)
c.close()
PY
)
curl -s -b "$CJ" -X POST "$BASE/app/projects/1/milestones/$MID/delete" -o /dev/null -w "del milestone http=%{http_code}\n"
./venv/bin/python - <<'PY'
from app.database import get_connection
c=get_connection()
n=c.execute("SELECT COUNT(*) FROM task WHERE source='milestone' AND title LIKE '里程碑：隐蔽工程验收'").fetchone()[0]
print("remaining auto tasks:", n)
c.close()
PY

echo "== 清理测试数据 =="
curl -s -b "$CJ" -X POST "$BASE/app/tasks/$(./venv/bin/python - <<'PY'
from app.database import get_connection
c=get_connection()
r=c.execute("SELECT id FROM task WHERE title='确认现场交底' ORDER BY id DESC LIMIT 1").fetchone()
print(r['id'] if r else 0)
c.close()
PY
)/delete" -o /dev/null -w "del manual task http=%{http_code}\n"
curl -s -b "$CJ" -X POST "$BASE/app/workers/$WID/delete" -o /dev/null -w "del worker http=%{http_code}\n"
echo "DONE"
