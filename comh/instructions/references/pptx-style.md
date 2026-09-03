# PPTX 样式模板（按需加载）

只在用户提供 PPTX、要求保留其背景/品牌装饰/字体时加载本页。

## 边界

- **样式模板**：背景、Logo、固定 icon、装饰、配色、字体、字号、粗斜体。
- **风格模板**：信息密度、版面结构、图文比例、内容槽位、节奏。完整模板编译尚未实现；
  已有独立的 [内容预设](presentation-profiles.md) 管理密度与简单布局建议，不从样式文件推导。
- 现有 `theme.yaml` 是样式 token，不等于上述风格模板。
- 不根据原文件的双栏内容框、示例页数量或占位符位置推导内容结构。
  即使元素在母版上，也可能是样例内容或布局槽位，必须逐项判断。
- `narrative.yaml` 保持媒介无关；内容仍在 `projection/deck_plan.yaml`。

## 接入一次，重复编译

Gate 1 先明确意向，不用提早加载模板所有页：

```yaml
appearance:
  selection: specified
  reference: templates/brand/style.yaml
  review: sample
```

给定单模板直接采用；模板合集记录 `selection: deferred`，故事线和粗大纲接受后给少量候选。
未指定模板可建议 `selection: default`，与契约一起确认。`selection: delegated` 是委托选择，
`review: delegated` 是委托样张审阅，必须分别有用户依据；大纲协作档位不能隐式代替它们。

```sh
comh style-inspect /absolute/path/brand.pptx --slide 1
comh style-import /absolute/path/brand.pptx --name brand --run runs/example
```

导入只复制本地源文件、生成 `templates/brand/inventory.json` 和 `style.yaml` 草案。
源文件不改写，已有同名目录不覆盖。初始 surfaces 为空，必须配置后才能编译。
完整 inventory 保留在磁盘；只检查当前需要的源页/图层，不整份塞进上下文。

形状选择器由源文件哈希、**可见页序号（从 1 开始）**、作用域和 shape ID 组成。
作用域为 master/layout/slide；不能只凭 shape name 或 ZIP 中 slide 文件名排序。
仅明确选择背景装饰、Logo、icon。排除示例文案、页码、图表、内容框和占位符。
嵌套 icon 可单独选 ID，保留父组变换而不导入其兄弟内容。

示意契约（ID 必须来自实际 inventory）：

```yaml
version: 1
kind: pptx-style
name: brand
source: source.pptx
sha256: <导入时生成的哈希>
tokens:
  colors: {background: FFFFFF, title: '123456', text: '222222', card_fill: FFFFFF}
  fonts: {latin: [Arial, Arial], cjk: [微软雅黑, 微软雅黑]}
  sizes: {cover_title: 40, content_title: 32, body: 24, body_wide: 24}
  font_styles: {title: {bold: true}, body: {bold: false}}
surfaces:
  content:
    slide: 1
    keep: {master: [7], layout: [], slide: []}
    protect: {master: [7]}
  cover:
    slide: 2
    keep: {master: [], layout: [], slide: [4]}
```

`protect` 是禁止内容遮挡的品牌元素 ID，须为已选的顶层形状/组。背景不要设为
protect。编译器报碰撞时修正样式选择或已授权的内容；不能为让测试通过而取消 Logo
保护。复杂原始背景与现有排版不兼容时，明确说明，风格/布局改造另议。

对确认本应单行的品牌文字，可加 `single_line: {layout: [11]}`，ID 同样必须在 keep 中。
这是一项通用修复契约，不匹配某个模板文件名。编译器按本机测量字体、粗斜体和内边距估算
宽度，保留文字、字号和左侧位置，必要时扩宽文本框，显式禁用换行与自动缩放。
扩宽后检查越界、与内容的碰撞及新增的装饰碰撞。仅支持顶层、简单单段、单 run 的横排文字；
复杂文本拒绝此自动修复。不能把所有短文本一律设为单行，也不能保证其他播放器的字形度量一致。

封面、分节、结尾要各有明确 surface；其他现有 page_role 使用 content 样式。
这只是背景/品牌层切换，不导入源页面的内容位置、结构或密度。

`tokens` 是一次性审阅后的样式值。主题色提取仅提供候选，不能把 theme 的 lt1
当作实际背景色。`inventory` 的 `text_style` 是首段/首 run 提示：渐变字色、颜色变换、
混合格式等会列 warnings，不能猜一个颜色声称原样继承。需要简化时展示实际差异。
生效顺序：全局 tokens → surface tokens → deck.style.tokens_override。

计划仅引用配置：

```yaml
deck:
  style:
    pptx_style: templates/brand/style.yaml
```

不要同时设置旧的 `style.template` 或逐页背景。沿用原有 brief、故事线和大纲确认：

```sh
comh validate all --run runs/example
comh render deck --preview --run runs/example
# 展示实际样张与重要适配差异，等待真实用户回复：
comh present deck_appearance --run runs/example
comh respond Dxxxx --decision accepted --reply '实际原话' --source '消息引用' --run runs/example
# 正式细节对齐完成后：
comh render deck --run runs/example
```

精确预览必须来自生成的 PPTX；`deck-html` 明确拒绝此模式。
已有确认仍有效时不重新问已回答的问题；新模板歧义或简化效果要用典型样张说明。
编译器内部步骤不需要用户逐一批准，不能代用户记录样张/交付接受。
重要的字体替换、品牌删改、配色简化写入 `deck.appearance_review: {summary, adjustments: [...]}`，
它与实际样式配置共同绑定接受记录。只改正文不重新问样式；样式变化重新展示，机械缺陷修复直接 QA。

## 可保证与仍需检查

- 本地纯代码：加载契约 → 类型化样式 IR → 现有内容排版 → 原生样式合成 → 检查 → 发布。
- 支持 16:9、4:3。内容在既有画布空间统一缩放适配，目标字号在测量前补偿，不能偷偷缩字。
- 背景与选定品牌资源保留原生 XML/图片；源示例正文、备注、动画不导入。
  内容文字、图表、数据工作簿仍可编辑；源页脚品牌由样式提供，不额外叠加默认页脚。
- 固定 icon 是模板装饰层；内容绑定的 icon 仍走现有本地图标库。本次不做可动态排布的模板 icon 注册表。
- 哈希/选择器错误、受保护元素碰撞、测量发现的溢出、外链资源和不支持对象会阻断，
  不回退默认主题。失败不覆盖上一份 PPTX，并使当前正式构建凭据无效。
- 源 PPTX、配置、素材和渲染器变更都进入现有快照失效机制。
- 构建报告记录模板/配置哈希、原页映射、原生资源、测量字体及替代情况。
  原生文字也纳入 `native_text_diagnostics`，inventory 的 `text_layout` 列出文本框宽度、
  内边距、换行、自适应和字体替代风险。它们是候选风险，不能把正常多行文字判为故障。
  字体未安装、复杂图片背景对比度、未标 protect 的装饰遮挡、播放软件差异仍需实际预览。
- 明确的浅色背景硬约束会检查真实背景；图片/主题填充等无法确定时阻断，不用声明色冒充证明。
- 当前只承诺经验证的对象范围。渐变文字 token、SmartArt/OLE、源动画、字体嵌入、
  任意画布与完整母版语义不作兼容承诺。必须完成实际 PPTX 视觉 QA 和原有交付确认。

## 错位的诊断顺序

1. 在同一播放器、同一字体环境渲染原模板和编译稿，定位到相同源页/图层/shape。
2. 比较位置、尺寸、文本、字体继承和 bodyPr。输出发生了非预期变更，优先修编译器；
   两者一致且都异常，继续查字体替代、自动适配和播放器行为，不能归咎于内容排版。
3. 依据风险记录检查品牌短字、页脚及边缘元素；原生继承文字也要看，不能只检查新增正文。
4. 在目标软件重新渲染验证。记录软件版本、缺失字体和验证范围；本机通过不代表跨软件通过。
