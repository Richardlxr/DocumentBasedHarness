# Stage: Report Projection + Authoring（报告契约与正文）

分两步：先写契约 `projection/report_plan.yaml`，再按契约写正文 `documents/report.md`。
报告和 deck 是**同一个 narrative 的不同投影**——报告不是 deck 的展开版，deck 也不是
报告的摘要版。

## Step 1 — report_plan（写作契约）

- `sections[]`：允许合并/拆分 beats（合并写 `merge_rationale`），允许与 story 顺序
  不同（报告可以方法前置，deck 通常不行）——这正是 co-projection 的意义。
- 每个 section：`heading`（报告标题可以是主题式的）、`beats`、`claims`、`evidence`
  （要求 inline 引用的 `Exxx`）、`depth`（`brief` / `detailed` / 自定义）、
  `must_include`。
- 报告的职责：展开 context / method / evidence / analysis / limitation / implication。
  deck 上放不下、被 demote 到 `report_only` 的内容，必须在这里有着落——plan 阶段就
  对账，不要等写完发现丢了。

## Step 2 — report.md（正文，Markdown 为主、DOCX 为辅）

用 docx-harness 的 Markdown/MyST 方言写 `documents/report.md`：

- **语域：报告是书面语。**完整句子、主语齐全、严谨展开——deck 上砍掉的细节
  在这里补全；和 deck 的口语短句不是一档，brief.voice.report 可覆盖全局风格。
- 普通 Markdown：标题、段落、列表、表格、图片、链接。公式用 `$...$` / `$$...$$`；
  示意图用 ```` ```mermaid ```` fenced 块（flowchart/graph 子集，确定性编译；
  需要 `DRAWIO_CLI` 指向 draw.io Desktop）。
- 插图纪律：`![图说明（数据来源：E001/E002）](../assets/p99-comparison.png)` ——
  caption 与证据标注写在图片语法里，报告里的图和 deck 里的图同样不许成为溯源盲区。
- 方言写错编译器会带行号报错——把编译错误当免费质检，改完重编译。
- 引用标注：正文中以 `[E001]` 形式 inline 标注证据；数字一律来自 evidence。
- 长度与深度按 `report_plan.depth` 和 brief 的 spec 判断，没有死规则。

## 收尾

```
comh save report_plan
# ……写正文……
comh save report_md
comh render report      # 编译 build/report.docx（副产物；正主是 report.md 本身）
```
