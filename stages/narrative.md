# Stage: Narrative（故事结构）— Gate 2

## 输入

- `evidence/evidence.yaml`：可用的事实。
- `brief/brief.yaml`（已过 Gate 1）：为谁、为什么、要什么效果。

## 你做什么

设计**媒介无关**的故事结构，写入 `narrative/narrative.yaml`。它不是大纲——大纲是
某种媒介的投影；narrative 是"这一场沟通由哪些动作构成"。

结构：

- `claims[]`：论断登记表。
  - `statement`：一句可真可假的话（不是话题）。
  - `evidence`：引用的 `Exxx` 列表。
  - `status` 必须诚实：`supported`（有据）/ `partial`（部分有据）/ `background`
    （背景知识，无需证据）/ `assumption`（假设，明确标注）/ `needs_research`（缺料）。
    **宁可诚实的 background，不要编造的 supported。** 校验器会拒绝"supported 却无
    证据"的 claim。
  - `importance`：`primary` / `supporting` / 自定义。
- `story[]`：有序的 beats（沟通动作）。
  - `purpose`：开放词汇——`establish_problem`、`demonstrate_effect`、`concede_limit`、
    `explain_mechanism`、`recommend`、`address_risk`……可自由发明，可参考
    `references/narrative-patterns.md` 的模式词汇（参考，不是边界）。
  - `message`：这个 beat 要让受众接受的那**一句话**。这是 narrative 的灵魂——
    投影层的标题、报告的段旨都从这里长出来。
  - `claims`：本 beat 依赖的 `Cxx`。

## 纯度规则（校验对象）

narrative 里**禁止**出现任何媒介信息：布局、字数、页数、颜色、"slide"、"章节"。
检验标准：一份电台讲稿和一份 deck 应该能同时是同一个 narrative 的投影。媒介取舍
全部留给 projection 层。

## 叙事设计要求

- 每个故事都能回答：为什么值得关注？→ 我们做了什么？→ 发现了什么？→ 边界在哪？
  → 所以建议什么？（顺序可以变，缺环要显式。）
- `needs_research` 的 claim 要在 Gate 2 摘要里明确告知用户，由用户决定：补材料、
  降级为 assumption、还是砍掉。
- recommendation 必须能从前面的 beats 推出来；推不出来就补 beat 或改 recommendation。

## Gate 2（硬规则）

给用户看的摘要格式（人类可读的逻辑链，不是 YAML）：

```
01 <purpose> — <message 一句话>
02 ……
03 ……
```

附：primary claims 及其证据状态、无据/存疑项清单。用户确认后：

```
comh save narrative
comh confirm narrative      # 必须由用户明确同意后才能执行
```

需要回头改 brief 的（对齐错了），回到 brief stage 改文件、重新过 Gate 1，
narrative 会自动标脏——不要绕。
