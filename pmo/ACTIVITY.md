# 动态（Activity Feed）

> 关键决策与里程碑的"救命日志"。只记摘要，不记琐碎过程。
> 格式：`[日期] [类型] 摘要`

---

[2026-08-12] [决策] 确立《比目鱼（Bimuyu） 项目宪法》，四层结构（动态 / 计划 / 任务 / 资产）+ 自动化与技能 + 全局约束固化，PMO 框架正式生效，本文件为唯一事实来源。

[2026-08-12] [里程碑] 资产归档完成：根目录散落的 `preview_workbench.html` 与 `demo/*.html` 归入 `design-drafts/`（参考页 / 预览稿），`OS4.01-设计规范.md` 移入 `设计规范/` 分类；建立 设计规范 / 预览稿 / 参考页 / 截图 四类。

[2026-08-12] [里程碑] PMO 初始任务建立（4 条，均标 `本地`）；每周日"备份 db + 8013 可达性自检"自动化创建；"启动 8013 + 可达性自检"技能固化至 `~/.workbuddy/skills/studio-os-start-8013`。

[2026-08-12] [自检] 服务当前 8013 未监听（会话重载后 uvicorn 被回收）；已用固化技能拉起并验证 `/app/dashboard` 200、登录 303→dashboard，可达性全绿。

[2026-08-12] [里程碑] **Studio OS 冻结 + 派生 bimuyu-os + 品牌全量重命名完成**。原项目冻结于 tag `v0-original-studio-os` / 分支 `archive/studio-os-origin`（提交 `40cd28c`），物理双备份存 `~/Desktop/_archive/`（目录副本 + 66MB tar.gz，含 .git 与本地私有资产）。派生目录 `~/Desktop/bimuyu-os` 继承完整历史，8 个分类提交完成替换：48 文件 / 109 处（Studio OS→比目鱼（Bimuyu）68、studio-os→bimuyu-os 7、studio_os_→bimuyu_os_ 4、studio.local→bimuyu.work 16、studio.db→bimuyu.db 13、studio_token→bimuyu_token 1）。`grep "Studio OS"` 残留 0。

[2026-08-12] [决策] 重命名边界确立：**产品品牌**替换，**业务领域词汇保留**。保留 `studio_profile` 表 / `studio_id` 列 / 模板变量 `studio.*` —— 其中 studio 意为「工作室」业务实体（库内实际值为 `vsence问世`），非产品名；另保留 vsence 全系、公开站 `STUDIO NOTE` 栏目名、示例客户 `Pixel Studio`、真实技能名 `studio-os-start-8013`。域名采用宪法既定的 `bimuyu.work`（而非指令中的占位 `bimuyu.xxx`）。

[2026-08-12] [自检] bimuyu-os 可达性全绿：venv 已重建（Python 3.11.9，断开对 studio-os 的反向依赖）；登录 `admin@bimuyu.work`/`admin` 均 303；后台 12 条路由 + 公开站 3 条全部 200/302；登录页与工作台实测「Studio OS」0 处。

[2026-08-12] [修复] 补齐 `requirements.txt` 遗漏的 `httpx==0.28.1`（`app/routers/cost_estimate.py` 依赖）—— 该缺失被重建 venv 暴露，原环境靠历史手工安装掩盖，换机器必炸。

[2026-08-12] [里程碑] 技能 `bimuyu-os-start-8013` 建立（含"沙箱会回收 nohup 后台进程，启动与验证必须同一 bash 调用内完成"的修正）；旧技能 `studio-os-start-8013` 标记为冻结存档。

[2026-08-12] [更正] 撤回第 16 行"grep Studio OS 残留 0"的不严谨表述，实测分三层：(a) 产物源码/模板/配置/库活数据 **0 残留**；(b) 数据库文件 `bimuyu.db` 二进制曾检出 4 处旧名（3×Studio OS + 1×studio.local），实为 SQLite freelist 空闲页幽灵字节，经 `VACUUM` 重建后实测 **0 残留**（提交 ceed354）；(c) `pmo/ACTIVITY.md`（本历史日志）与 `.git/logs` reflog 含旧名属正常（历史叙述 + git 元数据），非产品缺陷。另更正第 20 行登录口令：实测口令为 `admin123`（identifier=`admin@bimuyu.work`），非 `admin`。

[2026-08-13] [自检] **独立重验 Phase A 全绿**（应 Jerry 要求，不沿用旧结论）：tag/分支正确——studio-os 与 bimuyu-os 均含 `v0-original-studio-os` + `archive/studio-os-origin`，HEAD 分别为 `40cd28c`/`ceed354`；产物代码/模板/配置/库活数据 0 品牌残留；`import app.main` 全解析 OK；项目无 CI/Docker/pyproject/setup，此类旧引用不适用；唯一未覆盖变体 `init_db.py` 联系信息默认 seed `studio_design` 已修为 `bimuyu_design`（品牌根残留，存量 contact.json 为真实值不受影响）。可达性复测全绿。结论：可安全进入下一阶段。
