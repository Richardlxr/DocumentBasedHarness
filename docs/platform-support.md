# Windows / Linux 平台支持

Communication Harness 的 Python 核心、HTML、DOCX 和 PPTX 生成链路支持 Windows 与 Linux。
平台相关的外部程序是 Draw.io Desktop、Chromium 系浏览器和字体；缺失时 CLI 会报出明确错误
或记录字体测量回退，不会静默联网安装。

完整开发与渲染环境需要 Python 3.11+、Git，以及至少一套实际交付使用的字体。带 Mermaid
图形的报告需要 Draw.io Desktop；PPTX / HTML 的流程图支持子集使用原生对象 / SVG，
不需要该外部程序。PPTX 使用图标或执行 HTML 布局检查时需要 Chrome、Edge 或
Chromium。只安装 Python 依赖的极简容器不等于完整运行环境。

## 支持矩阵

| 能力 | Windows x64/ARM64 | Linux x64/ARM64 | macOS x64/ARM64 |
|---|---|---|---|
| Python CLI、校验、状态机 | 支持，Python 3.11+ | 支持，Python 3.11+ | 支持，Python 3.11+ |
| HTML 输出 | 支持 | 支持 | 支持 |
| DOCX / PPTX 输出 | 建议用 Microsoft Office 做最终视觉验收 | 建议用 LibreOffice/WPS 做视觉检查 | 建议用 Microsoft Office/Keynote 做视觉检查 |
| Draw.io 图形导出 | 手工安装 26.0.16；自动发现标准位置或设置 `DRAWIO_CLI` | x64 可自动安装；ARM64 手工安装 | 手工安装并设置 `DRAWIO_CLI` |
| PPTX 图标与 HTML 布局检查 | 自动发现 Chrome、Edge 或 Chromium；也可设置 `COMH_CHROME` | 自动发现 Chrome/Chromium；也可设置 `COMH_CHROME` | 自动发现 Chrome/Chromium；也可设置 `COMH_CHROME` |
| 字体测量 | Windows 字体注册表及字体目录；缺字库时回退并保守估算 CJK | Fontconfig (`fc-match`) | Fontconfig (`fc-match`) |

自动化测试在 Windows、Ubuntu 与 macOS 的 x64/ARM64 runner 上运行。CI 不安装 Microsoft Office，
也不把跳过的 Draw.io 实机导出当成已验证；成品仍需在实际交付播放器中检查。

## Windows PowerShell

```powershell
git clone git@github.com:Richardlxr/DocumentBasedHarness.git
Set-Location DocumentBasedHarness
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\comh.exe --help
.\.venv\Scripts\comh.exe init-run runs/my-report
```

Draw.io Desktop 需要与仓库固定版本 `26.0.16` 一致。标准的系统或当前用户安装位置会被自动
发现；非标准位置可在当前 PowerShell 会话配置：

```powershell
$env:DRAWIO_CLI = "C:\Tools\draw.io\draw.io.exe"
```

Chrome、Edge 和 Chromium 的标准 Windows 安装位置也会自动发现。使用便携版浏览器时配置：

```powershell
$env:COMH_CHROME = "C:\Tools\Chrome\chrome.exe"
```

`.agents/skills/communication-harness/SKILL.md` 是常规文件，Windows 克隆不需要创建符号链接。
根目录的 `skill/`、`stages/`、`references/` 仅是旧入口；如果 Git 将它们检出为包含目标路径
的普通文件，直接使用 `comh/instructions/` 或 `comh instructions <stage>`。

## Linux

```bash
git clone git@github.com:Richardlxr/DocumentBasedHarness.git
cd DocumentBasedHarness
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/comh --help
.venv/bin/docx-harness install-drawio  # 当前自动安装支持 Linux x86_64
```

无桌面会话时，Draw.io 适配器会在系统存在 `xvfb-run` 时自动使用它。Linux ARM64 或受控环境
应自行安装兼容的 Draw.io Desktop CLI，并设置 `DRAWIO_CLI`。

Debian/Ubuntu 的最小环境至少应补齐 Git、Fontconfig 和一种字体；使用浏览器渲染能力时再
安装发行版提供的 Chromium，或设置 `COMH_CHROME` 指向已有浏览器。具体包名随发行版变化。
容器中应以普通用户运行渲染命令，让 Chromium 保持默认沙箱；不要为了 root 运行而关闭沙箱。

若要让中文 PPTX/DOCX 的换行更接近 Windows Office，请在 Linux 构建机安装交付目标实际
使用的字体。找不到指定字体时，布局诊断会记录 Fontconfig 替代；字体替代不是像素级兼容证明。

## 成品兼容边界

- `deck.html` 是离线浏览器文件，在当前 Chrome、Edge、Chromium 中使用。
- `report.docx` 和 `deck.pptx` 使用 Office Open XML，但 Office、WPS、LibreOffice 的字体替代、
  行高、分页及复杂文字效果可能不同。
- 自动布局检查用于提前发现风险，不代替目标平台视觉验收。最终交付前应使用接收方的软件和
  字体检查一遍 PDF/PNG 预览或原文件。
