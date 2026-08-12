#!/usr/bin/env bash
# 第一批功能 E2E 验证：预算追踪 + 开销记账 + BOM CRUD + 导出 + 造价打通预算
set -u
BASE=http://127.0.0.1:8013
CJ=/tmp/batch1_cj.txt
rm -f "$CJ"

echo "== 1. 登录 =="
code=$(curl -s -c "$CJ" -o /dev/null -w "%{http_code}" -X POST "$BASE/app/login" --data "identifier=admin@bimuyu.work&password=admin123")
echo "login http=$code"

echo "== 2. 初始 budget =="
curl -s -b "$CJ" "$BASE/api/projects/1/budget" | python3 -c "import sys,json;d=json.load(sys.stdin);print('total_planned',d['total_planned'],'items',len(d['items']))"

echo "== 3. 新增预算分项 =="
IID=$(curl -s -b "$CJ" -X POST "$BASE/api/projects/1/budget-items" -H "Content-Type: application/json" --data '{"name":"硬装基础","category":"基础","planned_amount":100000}' | python3 -c "import sys,json;print(json.load(sys.stdin)['item']['id'])")
echo "budget_item_id=$IID"

echo "== 4. 记一笔开销 30000 =="
curl -s -b "$CJ" -X POST "$BASE/api/projects/1/expenses" -F "budget_item_id=$IID" -F "amount=30000" -F "payee=测试材料商" -F "occurred_date=2026-08-07" -F "note=测试" -o /dev/null -w "expense http=%{http_code}\n"

echo "== 5. 复核 budget（应 spent=30000, remaining=70000）=="
curl -s -b "$CJ" "$BASE/api/projects/1/budget" | python3 -c "import sys,json;d=json.load(sys.stdin);it=d['items'][0];print('spent',it['spent'],'remaining',it['remaining'],'pct',it['pct'],'over',it['over']);print('total_spent',d['total_spent'],'total_remaining',d['total_remaining']);print('chart_labels',d['chart']['labels'],'cum_budget',d['chart']['cum_budget'],'cum_actual',d['chart']['cum_actual'])"

echo "== 6. 新增物料 =="
MID=$(curl -s -b "$CJ" -X POST "$BASE/api/projects/1/materials" -H "Content-Type: application/json" --data '{"name":"乳胶漆","brand":"立邦","spec":"内墙","quantity":50,"unit":"L","unit_price":45,"category":"主材","purchase_stage":"前期","status":"ordered"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['material']['id'])")
echo "material_id=$MID"

echo "== 7. 从造价生成草稿 =="
curl -s -b "$CJ" -X POST "$BASE/api/projects/1/materials/generate-from-cost" | python3 -c "import sys,json;d=json.load(sys.stdin);print('generated',d['count'])"

echo "== 8. 导出 Excel =="
curl -s -b "$CJ" -o /tmp/bom.xlsx -w "excel http=%{http_code} type=%{content_type} size=%{size_download}\n" "$BASE/api/projects/1/materials/export/excel"

echo "== 9. 导出 PDF =="
curl -s -b "$CJ" -o /tmp/bom.pdf -w "pdf http=%{http_code} type=%{content_type} size=%{size_download}\n" "$BASE/api/projects/1/materials/export/pdf"
file /tmp/bom.pdf /tmp/bom.xlsx

echo "== 10. 造价保存为预算 =="
curl -s -b "$CJ" -X POST "$BASE/api/cost-estimate/save-to-budget" -H "Content-Type: application/json" --data '{"project_id":1,"survey":{"type":"餐饮","area":100,"city_tier":"二线","old_status":"全新毛坯","floor_height":3.5,"zones":[],"materials":{"地面":["瓷砖"],"墙面":["乳胶漆"]},"service_scope":"EPC"}}' | python3 -c "import sys,json;d=json.load(sys.stdin);print('ok',d.get('ok'),'items',d.get('items'),'mid_total',d.get('mid_total'))"

echo "== 11. 复核 budget 分项数量 =="
curl -s -b "$CJ" "$BASE/api/projects/1/budget" | python3 -c "import sys,json;d=json.load(sys.stdin);print('budget_items_after_save',len(d['items']),'labels',d['chart']['labels'])"

echo "== 清理测试数据 =="
for id in $(curl -s -b "$CJ" "$BASE/api/projects/1/budget" | python3 -c "import sys,json;[print(i['id']) for i in json.load(sys.stdin)['items']]"); do
  curl -s -b "$CJ" -X DELETE "$BASE/api/projects/1/budget-items/$id" -o /dev/null -w "del item $id: %{http_code}\n"
done
for id in $(curl -s -b "$CJ" "$BASE/api/projects/1/materials" | python3 -c "import sys,json;[print(m['id']) for m in json.load(sys.stdin)['materials']]"); do
  curl -s -b "$CJ" -X DELETE "$BASE/api/projects/1/materials/$id" -o /dev/null -w "del mat $id: %{http_code}\n"
done
for id in $(curl -s -b "$CJ" "$BASE/api/projects/1/expenses" | python3 -c "import sys,json;[print(e['id']) for e in json.load(sys.stdin)['expenses']]"); do
  curl -s -b "$CJ" -X DELETE "$BASE/api/projects/1/expenses/$id" -o /dev/null -w "del exp $id: %{http_code}\n"
done
echo "== 复核清理后 budget 应为空 =="
curl -s -b "$CJ" "$BASE/api/projects/1/budget" | python3 -c "import sys,json;d=json.load(sys.stdin);print('items',len(d['items']),'materials_check_via_separate_call')"
echo "DONE"
