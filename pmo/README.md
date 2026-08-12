# 比目鱼（Bimuyu） · PMO 工作台

项目宪法驱动的轻量项目管理中枢。所有规则以 [`CONSTITUTION.md`](./CONSTITUTION.md) 为唯一事实来源。

## 四层结构
| 层 | 文件 / 工具 | 用途 |
|---|---|---|
| 动态 Activity Feed | [`ACTIVITY.md`](./ACTIVITY.md) | 关键决策 + 里程碑摘要日志（救命日志） |
| 计划 Plan | [`PLAN.md`](./PLAN.md) | P0/P1/P2 优先级路线图，不排具体任务 |
| 任务 Tasks | WorkBuddy `TaskCreate` | 可执行、可验收的拆碎任务，必标 `本地/服务器/设计` |
| 资产 Assets | `../design-drafts/` | 设计规范 / 预览稿 / 参考页 / 截图，可回退事实来源 |

## 资产归档（design-drafts/）
- `设计规范/` — `OS4.01-设计规范.md`（视觉冻结单一事实来源）
- `参考页/` — `preview_workbench.html`（工作台参考视觉）
- `预览稿/` — `hero_redesign_preview.html` / `iphone_preview.html` / `dark_preview.html`
- `截图/` — 关键设计截图（侧边栏 / Bento Grid / 插件入口），待补充

## 自动化与技能
- **每周日自动化**：备份 `bimuyu.db` + 8013 可达性自检 + 异常提醒（WorkBuddy Automation）
- **技能 `studio-os-start-8013`**：`~/.workbuddy/skills/studio-os-start-8013` — 拉起 8013 → 等端口 → curl 验证 → 回报状态

## 全局约束（不可违反）
1. 视觉改动前先确认 `OS4.01-设计规范.md` 是否允许
2. 新功能上线前必有任务卡 + 自检结论
3. 不预排超过 4 个模块的迭代
4. 不把琐碎调试写进动态
5. 插件/扩展/平台决策默认 C 模式（官方自营），除非 Jerry 明确"开放"

## 隐私
单人主导项目；任务与资产保持私密，仅 Jerry 主动开启共享/协作者时才暴露对应模块。
PMO 文件与 `design-drafts/` 均为本地私有，不提交远端（见仓库 `.gitignore`）。
