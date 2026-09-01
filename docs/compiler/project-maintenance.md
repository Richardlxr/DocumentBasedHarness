# Managed Project 手工维护指南

本文面向需要手工修改文档正文、表格、公式或协议图，并重新生成 DOCX 的维护人员。它适用于
父仓库 `docx-harness` 下的所有 managed Project。具体 Project 的正文文件名、输出文件名、
专用语义和额外测试仍以该 Project 的 `project.toml`、README、AGENTS.md 和测试为准。

## 1. 基本原则

Managed Project 的内容源和生成物严格分开：

```text
documents/ 中的 Markdown/MyST 和手工维护的 Draw.io
                         ↓
              docx-harness 编译
                         ↓
       build/ 中的 DOCX、PDF、PNG、VSDX 和图形副本
```

- 要修改内容，编辑 `documents/` 中的原始源；
- 要查看或交付结果，打开 `build/` 中的生成物；
- 不要手工修改 `build/`，下一次构建可能清理或覆盖其中任何文件；
- 不要把生成的 DOCX、PDF、PNG、VSDX 或带哈希名称的 Draw.io 副本当作内容源；
- 正常渲染不应改写受版本管理的模板，也不应重新打开 DOCX 做常规后处理。

## 2. 找到当前 Project 的真实入口

先打开 Project 根目录的 `project.toml`。常用字段包括：

| 字段 | 含义 |
| --- | --- |
| `source` | 默认 Markdown/MyST 正文，必须位于 `documents/` 中 |
| `documents` | 原始内容源目录 |
| `template` | 受版本管理的 DOCX 模板 |
| `extensions` | Project 专用解析、渲染和生命周期钩子 |
| `output` | 默认 DOCX 输出，必须位于 `build/` 中 |
| `build` | 所有生成物的边界 |

典型文件职责如下：

| 路径 | 用途 | 日常是否手工修改 |
| --- | --- | --- |
| `documents/*.md` | 规范正文的唯一内容源 | 是 |
| `documents/diagrams/*.drawio` | 手工维护的原生 Draw.io 图源 | 是 |
| `templates/base.docx` | Word 模板和可复用样式 | 一般不要修改 |
| `extensions.py` 和 Project Python 模块 | 本 Project 的编译行为 | 仅熟悉工具链时修改 |
| `references/` | 可复现的资料、样式证据和来源版本 | 按发布需要维护 |
| `.workspace/` | 本机路径和跨会话上下文 | 不提交到 Git |
| `build/` | 可重新生成的发布件、预览和中间产物 | 否 |

如果 Project README 与 `project.toml` 不一致，以 `project.toml` 的路径契约为准，并修正
README。Project 可以包含多个 Markdown 文档；非默认源也必须位于配置的 `documents/` 中，
输出仍必须位于配置的 `build/` 中。

## 3. 修改 Markdown/MyST

普通维护优先使用标准 Markdown：

- `#`、`##`、`###` 表示标题层级；
- 空行分隔段落；
- `-` 表示无序列表，`1.` 表示有序列表；
- 使用普通 Markdown 表格表达字段和规则；
- 字段名、接口路径、命令和字面值使用反引号；
- 多行示例使用带语言名称的 fenced code block，例如 `text`、`bash`、`html`；
- 行内公式使用 `$...$`，独立公式使用 `$$...$$`；
- 不要在源文件中手写 Word 字体、列宽、页码、标题编号或分页空行。

Project 可能使用 `{test-case}`、`{document-cover}` 等语义化 MyST directive。保留 directive
的语义字段，不要把边框、颜色、合并单元格等表现规则写进标注。新增 directive 或改变字段
契约属于 Project/renderer 实现工作，不是普通内容编辑。

同一份文档中避免重复使用完全相同的小标题。MyST 会为标题生成隐式锚点，重复标题可能产生：

```text
Duplicate implicit target name
```

应把标题改成更具体且唯一的名称，而不是修改生成的 DOCX。

遇到不支持的 Markdown/MyST 节点时，编译器会带源文件位置失败，不会静默丢弃内容。先修正
原始源；不要通过直接编辑 DOCX 隐藏源文件错误。

## 4. 修改图形源

### 4.1 先判断哪一个文件才是原始源

图形有两种常见来源：

1. Markdown 中的 `mermaid` fenced block：Mermaid 文本是原始源，构建生成 Draw.io 和 PNG；
2. Markdown 中的 `drawio-file`：`documents/` 下被引用的 `.drawio` 是原始源。

`drawio-file` 路径相对于引用它的 Markdown 文件：

````markdown
```drawio-file
diagrams/example.drawio
```
````

不要把 PNG、截图、VSDX 或 `build/diagrams/` 中的文件路径写入 `drawio-file`。同一个文件名
即使同时出现在 `documents/` 和 `build/`，也只能编辑 `documents/` 中的版本。

### 4.2 手工维护 Draw.io 的规则

使用 diagrams.net 或 Draw.io Desktop 修改原生图源时：

1. 保留每个框、文字和连线为独立、可编辑的原生 `mxCell`；
2. 不要把整图替换成 PNG、SVG、截图、`shape=image` 或 Mermaid 插件 payload；
3. 连线应真正连接源节点和目标节点，保留 `source`、`target` 关系；
4. 不要让节点重叠、文字裁切、连线穿过无关节点或标签；
5. 颜色只辅助表达，同时使用边框、形状、线型和箭头保证灰度可读；
6. 字体应选择目标 WPS/Word 和构建环境可用的字体；
7. 保留 Project 已有的特殊几何语义，例如总线、梯形承载边、汇聚点或显式交叉点；
8. 保存后运行该 Project 的结构测试和实际渲染。

Renderer 可以读取标准的压缩或未压缩 Draw.io 文件。对于需要代码评审、文本检索或直接检查
`mxCell` 的 Project，优先保存为未压缩 XML；Project 的 README、AGENTS.md 或测试可能明确
要求未压缩格式。未压缩文件用文本编辑器打开时，可以直接搜索到 `<mxGraphModel` 和
`<mxCell`。

不要编辑 `build/diagrams/` 中带哈希名称的 `.drawio`、`.png` 或 `.vsdx`。它们是本次构建
保留的副本和预览，后续构建可直接覆盖。

### 4.3 Mermaid 的边界

内置 Mermaid 转换器只支持父仓库文档承诺的 flowchart/graph 子集。遇到不支持的图类型、
subgraph、class/style/click 等语句时会带 Markdown 行号失败。不要把失败的 Mermaid 截图后
伪装成可编辑 Draw.io；应简化为受支持语法、改用手工维护的 `drawio-file`，或由开发者扩展
Project 的图形注册表。

## 5. 构建环境

以下命令默认从父仓库 `docx-harness` 根目录执行。先确认虚拟环境和工具链可用：

```bash
.venv/bin/docx-harness --help
```

若 `.venv` 尚不存在，按父仓库 README 的“快速开始”初始化。首次在工作站生成图形时，显式
安装固定版本的 Draw.io CLI：

```bash
.venv/bin/docx-harness install-drawio
```

正常渲染离线运行，不会隐式下载 Draw.io。自动安装当前支持 Linux x86_64；其他平台设置
`DRAWIO_CLI`，指向兼容的 Draw.io 可执行文件。

## 6. 推荐工作流

将下列 `<project>` 替换为实际 Project 名称。

### 6.1 文字或接口内容修改

```text
读取 Project README/project.toml
→ 编辑 documents/ 中的 Markdown
→ validate-project
→ 运行 Project 测试（如果存在）
→ render-project
→ 在 WPS/Word 中检查变化页面
```

### 6.2 图形、表格、字体、模板或分页修改

```text
确认原始源
→ 修改源文件或 Project 实现
→ validate-project
→ 运行 Project 测试和 Ruff
→ render-project
→ 必要时转换 PDF
→ 在目标 WPS/Word 中检查图形、表格、字体和分页
```

通用命令：

```bash
.venv/bin/docx-harness validate-project projects/<project>
.venv/bin/pytest projects/<project>/tests
.venv/bin/ruff check projects/<project> --no-cache
.venv/bin/docx-harness render-project projects/<project>
```

新建 Project 的 `tests/` 可能暂时为空；此时 Pytest 会报告没有收集到测试。不要为了让命令
返回成功而添加无意义测试，应在形成真实输出契约后补充对应回归测试。

构建成功只说明内容能够编译，不代表分页、字体和图形比例一定合适。至少打开 DOCX 检查变化
页面；修改图形、表格、字体、模板、页边距、页眉页脚或分页时，必须在目标 WPS/Word 环境中
检查。可使用 LibreOffice PDF 辅助发现裁切和分页问题，但字体缺失时 PDF 可能使用替代字体。

## 7. 事实来源和版本边界

- 正式采用的外部仓库 commit、协议版本或参考资料版本写入
  `references/source-revisions.toml`；
- 机器本地绝对路径只写入忽略的 `.workspace/references.toml`；
- 外部仓库是证据，不是第二份规范正文源；
- 不确定的事实写成待确认项，不要伪装成已经冻结的契约；
- 正式发布按 Project 的 `VERSIONING.md` 记录父级 renderer commit 和参考资料快照；
- `build/`、`.workspace/`、缓存、预览和临时锁文件不进入 Project Git。

## 8. 常见问题

### 已修改 DOCX，但重新构建后内容丢失

DOCX 是生成物。把需要保留的修改还原到 `documents/` 下的 Markdown 或图源，再重新构建。

### Draw.io 能打开，但测试失败

检查是否编辑了 `build/diagrams/` 副本、替换成整图图片、破坏 `source/target` 连线、改变了
受保护的语义节点，或保存格式不符合 Project 的本地测试要求。

### 找不到或无法启动 Draw.io CLI

先运行 `install-drawio`。如果受控环境阻止 Draw.io/Electron 启动，应在正常桌面终端中运行，
或设置受支持的 `DRAWIO_CLI`；不要随意关闭系统安全机制。

### Markdown 报重复隐式目标

文档存在重复标题。把标题改得更具体且唯一，然后重新验证。

### PDF 与 WPS/Word 字体不同

构建机缺少源文档或图形指定字体时，LibreOffice 会进行字体替代。最终交付效果以安装目标
字体的 WPS/Word 环境为准，并在 Project README 中记录必需字体。

## 9. 提交前检查单

- [ ] 已读取 Project README、`project.toml` 和必要的本地维护说明；
- [ ] 只修改了 `documents/` 中的原始内容源或明确受控的 Project 实现；
- [ ] 没有手工修改或提交 `build/`、`.workspace/`、缓存和临时锁文件；
- [ ] Markdown 标题层级合理，语义 directive 没有退化为表现标注；
- [ ] Draw.io 仍由原生可编辑节点和真实连接线组成；
- [ ] `validate-project`、已有 Project 测试和 Ruff 均通过；
- [ ] 已重新生成 DOCX，并在 WPS/Word 中检查变化页面；
- [ ] 图形、表格、字体和分页没有裁切或不可读内容；
- [ ] 事实来源变化时已更新来源版本或待确认项；
- [ ] 正式发布时已按 Project 的 `VERSIONING.md` 创建 tag 和发布说明。
