# PPTX 样式编译实施验证

2026-09-03；分支 `codex/pptx-template-compiler`。范围仅样式模板，未实现风格模板。

## 交付能力

- `comh style-inspect` / `style-import`：本地源清单、真实可见页序、逐层 shape ID、
  字体提示、只读源复制和哈希锁定。导入草案必须明确选择样式面，不猜内容槽位。
- `comh/pptx_style/`：严格配置 → 不可变样式 IR → 现有内容 renderer → 原生样式合成
  → 检查 → 暂存发布。配置拒绝 density/structure/slots 等组织信息。
- 保留原背景、Logo/icon、图片与矢量关系；支持分组选择和 Office HD Photo。
  源样例文字、原页码、源备注和动画不复制。生成文字/图表/工作簿可编辑。
- 固定目标字号、浅色背景硬约束预检、指定品牌区域碰撞检查；错误不回退主题、
  不覆盖旧文件，正式失败写入 QA 并使构建凭据失效。
- 模板版本沿用现有 snapshot；context 只披露当前样式摘要和需要的 surface。
  正式生产仍经过 brief、故事线、大纲、详情和交付决策。
- 模板意向在 Gate 1 显式处置；首次原生适配通过独立 `deck_appearance` 样张决策，
  位于故事线/粗大纲后、批量细化前。样式委托独立于大纲委托，内容修改可复用当前样式接受。
- 所有保留的原生文字增加字体/宽度/换行/自适应风险诊断；显式 `single_line` 修复契约
  按测量宽度扩框并检查新增碰撞，普通文字不自动改写。适用范围与原因见
  [文字兼容性诊断](2026-09-03-pptx-text-compatibility.md)。

## 实际模板测试

输入是用户授权测试的交大模板目录，源文件均保持原哈希，未写入 Git。
结构检查覆盖 **9 个文件、225 个源页**；每份抽取封面/正文样式各一面，
用相同两页内容和现有排版编译 **9 份 PPTX、18 个输出页**。
全部生成并以 LibreOffice headless 转成 PDF/PNG，逐页检查文字可见性、品牌元素、
明显遮挡与越界。未测试全部 225 页的视觉效果，未在 PowerPoint 验收。

| 探针 | 原模板 | 画布 |
|---|---|---|
| sjtu-red | 百廿红 | 16:9 |
| sjtu-blue-wide | 简单蓝 | 16:9 |
| sjtu-blue-standard | 简单蓝 | 4:3 |
| sjtu-gold | 深海金芒 | 16:9 |
| sjtu-galaxy | 浩瀚星河 | 16:9 |
| sjtu-wine | 诗意校园·酒红醉人 | 16:9 |
| sjtu-youth | 诗意校园·蓝绿青春 | 16:9 |
| sjtu-silver | 诗意校园·赤霞银珠 | 16:9 |
| sjtu-night | 诗意校园·暗夜奔驰 | 16:9 |

测试中暴露并处理了：原页码为普通形状、嵌套组合图、HD Photo 扩展关系、主题色
与实际直接 RGB 不一致、默认页脚与模板页脚叠加、双栏框被误当装饰、渐变文字
错误回退黑色。探针排除内容框和依赖原标题布局的分隔线，编译器按明确选择执行。

**样张适配不是原样复刻承诺**：酒红/赤霞/深海金芒正文样张明确使用 24pt 标题，
以适配现有排版与原生标题条；赤霞/暗夜渐变文字明确取白色端点。每项写入
`results.json` 的 specimen_adaptations，不是编译器静默缩字或降级。
模板原 XML/图片保持原状；这些是内容文字的显式样式配置。
用户随后指出浩瀚星河的 `SJTU` 异常换行，上一轮 QA 确有漏检。对照原稿确认同机也异常，
本轮在配置中显式标为单行，按测量扩宽该标签并禁用换行/自动适配，18pt 与原位置保留。
实际 LibreOffice PDF/PNG 已复核四个字母位于同一行；原文件未修改。原生 XML 保留承诺
应理解为没有显式适配的元素保持原状，不能覆盖已记录的单行修复。

本机缺少模板要求的部分 HarmonyOS/微软雅黑字体。预览使用系统字体替代，
输出 PPTX 仍声明原字体；原生资源字节一致不等于播放器像素一致。
未标 protect 的复杂装饰仍靠视觉审阅；bbox 保护是保守检查，不负责自动调整布局。
模板固定 icon 可导入，本轮未建立可动态排布的模板 icon 注册表。

## 自动化验证

完整回归：**277 passed，2 skipped，37 warnings**（MyST/Docutils 原有弃用提示）。
样式测试覆盖：16:9/4:3、原生资源/源文件哈希、可编辑图表及证据值、真实页序、
严格样式边界、过期选择器、长中文溢出、前一成品保留、跨页修改隔离、HTML 拒绝、
Logo 碰撞、嵌套 icon 不带入兄弟正文、内容 icon 保留、浅色背景声明不能冒充实际
背景、CLI 上游门控，以及失败记录/构建失效；新增原生文字风险检查、单行修复与扩框碰撞。
对话测试覆盖意向完整性、先样张后正式渲染、独立样式委托、延期选择、样式变更失效、
内容编辑/缺陷修复复用、等待期间替换样张阻断。最后的有效主题 token 绑定调整后，
相关 **43 项**测试重跑通过。Ruff 与 `git diff --check` 通过。

```sh
.venv/bin/pytest -p no:cacheprovider \
  --basetemp=/private/tmp/codex-dev-cache/DocumentBasedHarness/pptx-style-tests
.venv/bin/ruff check . --no-cache
.venv/bin/python scripts/probe_pptx_styles.py \
  --source-dir '/Users/richard/Vault/SJTU视觉形象/上海交大PPT模板-文明办出品' \
  --output runs/pptx-style-probe
```

探针直接调用 renderer 公共入口作为工程测试，不生成用户决策、接受记录或交付
凭据。`scripts/probe_pptx_styles.py` 的选择器仅适用于这份已检查语料，不是通用的
背景识别器；它只应写入专用工程输出目录，会重建其中的样式配置和样张。

本地复现证据保存在忽略的 `runs/pptx-style-probe/`：源复制、配置、清单、两页计划、
PPTX、PDF、18 张预览、`results.json`、`render-results.json` 和预览索引。
预览运行参数与字体配置随 render-results 保留；用户素材不随代码提交。
本轮额外检查九份模板的已选样式文字，两个原生文字对象中一处宽度压力命中 SJTU，
结果保存在 `qa/native-text-compatibility.json`；这不是对全部源页正文的视觉验收。

## 后续独立议题

风格模板（密度/结构/内容布局）待用户讨论后定义；本轮不预设契约。
将来可以为样式装饰与内容边界建立布局求解机制，但不能以导入源内容框代替设计。
复杂文字效果、字体嵌入、更多画布/Office 对象与 PowerPoint 实机矩阵是兼容性扩展。
减负效果需要另做 agent 调用量、修复轮次对照，当前不宣称量化收益。

前一实施轮清理专用缓存约 **8.24 MiB**；本轮核对无活跃文件后，清理专用测试目录、
LibreOffice/Fontconfig 预览缓存及新增模块/测试字节码，共回收约 **12.33 MiB**。
精确路径与大小记录在 `qa/task-cleanup.json`。保留用户源复制、编译样张和 QA 证据，
它们是测试交付物，不作为缓存删除。未清理共享缓存。
