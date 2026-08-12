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
