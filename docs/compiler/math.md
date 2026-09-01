# 数学公式

## 源语法

行内公式使用一对美元符号：

```markdown
往返时延记为 $RTT_i$，样本数为 $n$。
```

独立公式使用两对美元符号：

```markdown
$$
\bar{x}=\frac{1}{n}\sum_{i=1}^{n}x_i
$$
```

反引号仍用于字段名、命令、路径和代码，例如 `` `run_id` ``；数学变量、上下标、分式、
根式、求和及单位使用 TeX。源中不要嵌入由 Word 复制出的 OMML、MathML 或公式图片。

## 编译链

```text
Markdown/MyST
  → Docutils math/math_block
  → InlineMath/MathBlock IR
  → latex2mathml
  → mathml2omml compatibility adapter
  → validated native OMML
  → DOCX
```

转换器在 AST→IR 阶段验证公式，所以语法错误、缺失参数和未解析命令会携带 Markdown
文件及行号终止构建。renderer 不会把失败公式改成普通文本、代码块或 PNG。

## 输出与样式

- 行内公式进入原段落并继承正文、列表、标题或表格上下文。
- 独立公式使用 `DR Math Block`，默认居中且取消首行缩进。
- 表格内独立公式使用 `DR Table Math Block`，字号与表格文字一致。
- `cn-official` 中正文公式为 14 pt，表格公式为 12 pt。
- 输出为 DOCX 原生 Office Math，Word 和 WPS 中可继续编辑。

公式样式由生成模板维护；公式结构由 renderer 维护。项目不需要复制转换实现，仅在确有
不同排版要求时调整模板样式。

## 当前边界

支持范围以回归测试覆盖的 TeX 数学子集为准，包括上下标、分数、根式、求和、极值、
括号、常用运算符、`\mathrm`、`\text` 和常用重音符号。第三方库可能接受但错误输出的
命令会在 OMML XML 校验阶段失败。

当前不支持公式编号和交叉引用。带标签的 `$$...$$ (label)` 会显式报错，避免标签被静默
丢弃。以后可以在保持 `MathBlock` 语义不变的前提下，增加编号策略和引用 IR。
