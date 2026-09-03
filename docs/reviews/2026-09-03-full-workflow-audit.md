# 全流程审查与用户协作说明

日期：2026-09-03。检查对象为当前工作区，包括此前尚未提交的 PPTX 样式编译、样式决定、
学术密度预设和受众文案检查。保留原有未提交改动；本轮未提交或推送。

## 结论

发现并修复两处跨阶段检查缺口：样式重审被绕过、报告正文保存未检查到期问题。
修复后完整回归为 **306 passed、2 skipped**，Ruff 和差异空白检查通过。
当前审查范围内未发现仍未解决的阻断性流程缺陷；语义质量、实际阅读与播放器兼容性仍需
每次内容任务各自检查，不能用本次工程测试替代。

## 审查范围与证据

| 阶段 | 核查内容 | 主要回归证据 |
|---|---|---|
| Intake / evidence | 目标范围、来源覆盖、反证、派生数值、来源变化后的失效 | `test_dialogue.py`、`test_workflow_integrity.py`、`test_evidence_pack.py` |
| Brief | 必填要求的逐字段处置、真实回复依据、默认值、密度与模板意向、延期问题 | `test_dialogue.py`、`test_presentation_profile.py`、`test_appearance_dialogue.py` |
| Narrative | 不能被细化委托跳过；不确定论断需处置；媒介字段隔离 | `test_dialogue.py`、`test_workflow_integrity.py` |
| Outline / refinement | 各媒介自己的大纲、共同打磨逐节点决定、草稿与正式稿区分、协作方式切换 | `test_dialogue.py`、新增 `test_workflow_audit.py` |
| Appearance | 选择和样张分开；模板/内容委托分开；样张绑定、改变失效、机械修复复用 | `test_appearance_dialogue.py`、新增重审回归 |
| Authoring | 可见文案检查、真实限制保留、密度仅提示、正文到期问题 | `test_audience_copy.py`、`test_presentation_profile.py`、新增到期回归 |
| Render | 预览不算交付、原生模板与 HTML 边界、构建失败/篡改/重渲染失效、DOCX 编译器 | `test_pptx_style.py`、`test_closed_loop.py`、`tests/compiler/` |
| QA / delivery | 当前审稿、实际读者输出引用、人工硬约束、样式决定、全部所选输出与版本绑定 | `test_workflow_integrity.py`、`test_dialogue.py`、新增组合回归 |
| Recovery / repair | next/context、拒绝历史、局部证据切片、反证保留、有效决定复用 | `test_dialogue.py`、新增局部修改回归 |

表内未另注目录的测试均位于 `tests/runtime/`。测试中的用户与读者回复有明确 fixture 标识，
验证的是协议和版本管理，并非一次真人验收或独立语义审稿。

## 已修复的问题

### 1. 已有构建可绕过重新打开的样式审阅

复现：样式接受并正式构建 → 重新展示同一套样式 → 用户要求修改 → 文件和内容未变化，
旧构建凭据仍有效。原先审稿/交付准备只检查构建和内容决定，未重新要求有效样式决定，
因此 `comh review` 仍返回成功。默认样式重新打开审阅时还可能被原默认策略忽略。

修复：审稿和交付共用的 `_require_deliverables` 对 PPTX 再检查 `require_appearance`；
`needs_review` 识别当前绑定的显式样式请求，等待/要求修改均不能被原默认或委托策略绕过。
用户新接受当前样式后可恢复，不需要把仍有效的文件改写一遍。

新增回归同时覆盖原生模板和默认样式、等待回复和要求修改、已有构建与重新接受后的恢复。

### 2. 非逐节打磨的报告可提前保存正文

复现：brief 的问题延期到 authoring → 接受故事及报告粗大纲 → 未答该问题 →
`comh save report_md` 原先仍成功。正式渲染和最终交付会检查，但正文保存已越过约定截止点。

修复：正文保存先运行 authoring 阶段的 readiness 检查，与正式渲染保持一致。
回归同时确认：到 authoring 的问题阻断；延期到 QA 的问题不会被提前当作到期。

## 组合路径验证

新增组合回归使用学术默认预设、共同打磨模式，同时选择 PPTX、HTML、DOCX：

1. 接受契约、故事与演示稿大纲；遗漏页级确认时正式渲染被拒。
2. 接受对应页细节；接受报告大纲，遗漏节级确认时正文保存被拒。
3. 完成节级确认并保存正文；实际生成 PPTX、HTML、DOCX，Markdown 作为报告源同时交付。
4. 登记明确标注为模拟的读者结果和审稿，再接受交付，状态进入 complete。
5. 仅修改一页要点：故事、大纲和报告细节决定仍有效，对应页细节及旧交付失效。
6. 重新接受该页并重编演示稿；未变化的 DOCX 构建仍有效，重新审稿验收后恢复交付。

原生 PPTX 模板不能直接供 HTML 使用，因此上述联合交付使用通用主题；原生模板路径单独回归。

## README 与阶段指令修订

README 现在逐阶段列出“会看到什么、可以提出什么要求、agent 如何响应、何时需要确认”，
覆盖材料、证据、契约、故事、大纲、样式、细化、QA、交付，以及协作档位、部分委托、
中途修改和恢复。强调先故事后大纲、样式审阅与细化委托独立、当前版本接受不扩展到未来提案。

同步修正原文中超过实现范围的承诺：

- 局部修复不保证仅重编一页；当前部分依赖采用文件/目录整体指纹。
- 原生 PPTX 样式不能原样进入 HTML，演示主题也不会自动成为 DOCX 报告主题。
- PPTX 动画为实验性出场/淡入；HTML 的强调与其他效果不能承诺等价播放。
- 编译成功与对比度估计不等于所有页面、字体环境和播放器都无错位。
- “去检索素材”已有明确授权时不重复询问，只有未授权或扩展范围才需要询问。
- `hero_split` 当前图在右侧，移除原来直接承诺“左边放图”的示例。

用户指南和相关阶段指令同步补齐密度、样式、到期问题和授权范围说明，避免 README 与执行入口冲突。

## 验证范围与限制

- `.venv/bin/pytest -p no:cacheprovider --basetemp=/private/tmp/codex-dev-cache/DocumentBasedHarness/workflow-audit-tests`
  完成：306 passed、2 skipped，耗时 95.18 秒。38 条提示来自既有 MyST/Docutils 弃用接口。
- 两项跳过分别涉及当前 SimHei 替代字体不满足比例字形假设，以及未配置 draw.io CLI 的实际图形导出。
  不能据此宣称此次验证了 draw.io 实机导出。
- `.venv/bin/ruff check . --no-cache`、`git diff --check` 通过。
- README/用户指南的本地链接、阶段锚点和 Markdown 表格另作结构检查。
- 本轮没有重做全部真实模板的视觉 QA，也没有修改用户提供的 PPTX；既有真实模板分析见相关审查文档。
- CLI 记录仍由 agent 代录，不能认证真人身份、保证模型理解、证明独立审阅，也不能控制宿主上下文压缩。

只清理本轮专用测试缓存与临时日志，保留源代码和审查证据；清理记录与原始测试结果保存在
Git 忽略的 `runs/workflow-audit/`。
