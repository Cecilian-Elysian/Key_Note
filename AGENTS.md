# 项目风格指南 — KeyNote

## 核心理念
- **简洁小巧** — 不堆功能,不建多余文件,不改框架
- **Windows 单机工具** — pynput 键盘监听 + SQLite 持久化 + customtkinter UI + pystray 托盘

## 架构约束
- 主窗口硬编码 `800×600`(逻辑尺寸,DPI 感知下物理像素按缩放系数放大),不响应式
- 布局:48px 通栏标题栏 + 左侧 160px 侧边栏 + 内容区,切换走 `App._switch_page(name)`
- 5 页侧边栏导航(Segoe 字形图标 + 药丸选中态 + 左缘 accent 竖条),快捷键 Alt+1~5
  - Page 1 `OverviewPage`(`dashboard.py`):页头 + 紧凑时间筛选 + 设备行主卡(进度条/对比胶囊)+ 趋势图(悬停十字线)+ GH 年度
  - Page 2 `KeyboardPage`(`keyboard.py`):3 张 KPI 副卡 + 键型分布胶囊行 + 7×24 + QWERTY 键盘热力图(标签显示为"后台")
  - Page 3 `HeatmapPage`(`heatmap.py`):4 张 KPI 统计卡 + 年度热力图
  - Page 4 `TopKeysPage`(`top_keys.py`):Top 10 按键条形图
  - Page 5 `SettingsPage`(`settings.py`):整页嵌入 SettingsPanel + 固定底栏(表单不参与 auto-refresh,防覆盖编辑中值)
- auto-refresh 只刷新当前页(设置页除外)
- ⚙ 入口(托盘菜单 / 标题栏按钮)统一走 `App._open_settings()` → 唤起窗口 + 切到设置页;`settings_panel.open_or_focus()` 已无调用方,保留备用
- Win11 Mica 材质(`window.py::MICA` 常量开关):DWM SystemBackdrop + 侧边栏窗格键控透壁纸;标题栏/内容区实底防点击穿透,异常自动回退纯色

## UI 设计语言(WinUI 暗色 Fluent,vigil-watt 复刻)
- 色板 / 间距 / 圆角 / 字号全部来自 `theme.py`:`ColorTokens` + `SPACE` + `RADIUS` + `FONTS`,页面只取不写
- 卡片语言:`corner_radius=8` + `border_width=1` + `border_color=border` + `fg_color=bg_secondary`
- KPI 卡三层:标签(12 secondary)/ 数值(24 bold,主卡 hero 32 bold)/ 脚注(11 tertiary)
- 页面骨架:页头(标题 18 + 副标题 12 + 右侧"⟳ 刷新"图标+文字钮,padding 20,16)→ 筛选/副卡 → 内容卡;空数据画三段式空状态(图标字形 + 主文案 + 说明)
- 主卡(vigil-watt 设备行):图标 + 标签 + 右侧 hero 数值 + 6px 进度条(达标转绿)+ 语义胶囊 + 脚注
- 趋势图(vigil-watt 电量图签名):2px 圆角线 + 同色 alpha 面积 + ≤40 点圆点 + 线端值标签 + 悬停十字虚线/白描边圆点/圆角气泡
- 胶囊(vigil-watt 徽标):语义色文字 + 同色 16% tint 底 `radius 4`(Tk 无 alpha,`theme.mix_hex` 预混)
- 侧边栏:Segoe Fluent/MDL2 字形图标(PIL 渲染,字体缺失回退圆点)+ 文字;Mica 键控区上的按钮一律实底近色(防点击穿透)
- 设置面板:分组标题带强调色竖条,行内左标题 + 常驻说明 / 右控件,行间 1px 分隔线,底栏固定
- 新增颜色一律进 `theme.py` 的 dark 令牌;页内专属色仍写模块顶部常量(键型胶囊色在 `keyboard.py::_TYPE_META`)

## 代码风格
- **声明式 > 手写**: `settings_panel.py` 用 `FieldSpec` + `GROUPS` 描述控件,扩字段只加一行
- **主题集中管**: `theme.py::ColorTokens` 做颜色 pipeline,页面从 `theme.current().colors` 取
- **页面内部硬编码专属色**: 不污染全局主题,settings 面板的黄色 ? 等直接写常量
- **BasePage 三接口**: `_build` / `_do_refresh` / `_do_apply_theme`
- **松耦合回调**: 模块间通过回调(如 `_on_settings_changed`)通信,不走直接导入
- **注释规范**: 模块头部加中文 docstring 说明功能,大文件内按功能分区加 `# ──── 标题 ────` 章节注释,不添加逐行注释(代码即文档)
- **每改必提交**: 每次文件修改后写一笔 git commit,变更以 commit message 记录
- **每改必同步 `.gitignore`**: 新文件类型/目录产生后,检查 `.gitignore` 是否需要更新

## 功能模块分类

### 1. 启动与生命周期
| 文件 | 职责 |
|---|---|
| `key_note.py` | 入口:按序启动 DB→窗口→监听→托盘→热键→mainloop |

### 2. 配置管理
| 文件 | 职责 |
|---|---|
| `config.py` | JSON 持久化 + 默认键字典 |
| `settings_panel.py` | FieldSpec 声明式设置面板(行式布局 + 搜索 + 固定底栏) |

### 3. 输入监听(键盘 + 鼠标)
| 文件 | 职责 |
|---|---|
| `listener.py` | pynput 全局键盘+鼠标监听 + 按键分类(letter/digit/symbol/modifier/function)+ 暂停/恢复 |

### 4. 数据持久化
| 文件 | 职责 |
|---|---|
| `db.py` | SQLite 异步写入 + 聚合(键盘/鼠标/按键类型)+ 迁移(v1~v6) + 备份/清理/CSV |

### 5. UI 窗口
| 文件 | 职责 |
|---|---|
| `window.py` | 主窗口 UI(标题栏 + 侧边栏 + 5 页)+ Mica 材质 + 自动刷新 + 闲置检测 + 设置回调 |
| `ui/pages/base.py` | BasePage 基类 |
| `ui/pages/dashboard.py` | OverviewPage(Page 1):页头 + 筛选 + 设备行主卡 + 趋势图(悬停)+ GH 热力图 |
| `ui/pages/keyboard.py` | KeyboardPage(Page 2):页头 + 3 张 KPI 副卡 + 键型胶囊行 + 7×24 + QWERTY 键盘热力图 |
| `ui/pages/heatmap.py` | HeatmapPage(Page 3):页头 + 4 张 KPI 统计卡 + 年度热力图 |
| `ui/pages/top_keys.py` | TopKeysPage(Page 4):页头 + Top 10 按键条形图 |
| `ui/pages/settings.py` | SettingsPage(Page 5):整页嵌入 SettingsPanel + 固定底栏 |

### 6. 主题系统
| 文件 | 职责 |
|---|---|
| `theme.py` | 仅 dark 一套 ColorTokens(2026-07-13 起永久移除亮色)+ 间距/圆角/字号常量 + apply |

### 7. 系统托盘
| 文件 | 职责 |
|---|---|
| `tray.py` | pystray 图标 + 动态菜单 + 开机自启 |

### 8. 图表组件
| 文件 | 职责 |
|---|---|
| `ui/widgets/gh_heatmap.py` | GitHub 风格热力图(Canvas 渲染,Page 1 底部年度图) |
| `ui/widgets/chart_utils.py` | matplotlib 画布工厂(供 Page 1 趋势图复用) |

### 9. 构建与部署
| 文件 | 职责 |
|---|---|
| `build.ps1` | PyInstaller (--onefile) + 自动备份/恢复 |
| `KeyNote_Setup.iss` | Inno Setup 安装器 |

## 前死代码,现已全部挂载(2026-10 侧边栏改版)
`ui/pages/{heatmap,top_keys,settings}.py` — 原 3 个未挂载页面已激活为 Page 3/4/5 并 Fluent 化重写,不再属于死代码。
`ui/pages/keyboard.py` 是原 `rate.py` 改名 + 内容重写后激活为 Page 2。
`ui/widgets/chart_utils.py` 已从死代码复活(供 dashboard 趋势图与 top_keys 条形图复用)。
目前项目内已无未挂载页面。

## 硬约束(违反即不收)
- `theme.py` **只有 dark 一套**,不新增亮色 / 第三方主题,页内专属色直接写模块顶部常量;只允许往现有 dark 令牌里加字段(色值 / 间距 / 圆角 / 字号),不加第二套主题
- **不建新文件**,扩功能优先走现有模块(扩 `FieldSpec` 加字段 / 扩 `tray.py` 加方法 / 扩 `window.py` 加回调分支)
- `build.ps1` 删 PyInstaller 工作目录只删 `build/KeyNote/`,**禁止** `Remove-Item build/`(会把 `build/_data_bak/` 用户备份一起删)
- `build.ps1` 调 Python 用 `py`(WindowsApps 的 `python.exe` 是占位 stub)
- `build.ps1` **不写中文字符串**(PowerShell 5.1 解析报错);`KeyNote_Setup.iss` 中文可用(Inno Setup 6 实测通过,2026-09-19)
- 配色 / 图标颜色 / toggle 进度色等页内专属视觉色,**写在对应页面模块顶部常量**,不污染 `theme.py`;通用色一律走 `theme.current().colors`

## 未来规划

潜在接入功能,按文件分:

| 文件 | 可扩展方向 |
|---|---|
| `settings_panel.py` | 加新字段 → GROUPS 加一行 + config.py 加默认值 + 对应模块加处理逻辑 |
| `dashboard.py` | 新增图表类型 / 布局微调 / 数据维度扩展 |
| `theme.py` | **只扩 dark 令牌**(色值 / 间距 / 圆角 / 字号),不加第二套主题 |
| `window.py` | 加新回调分支处理新配置;侧边栏扩页 / Mica 调优 |
| `tray.py` | 加新菜单项 / 托盘交互优化 |
| `listener.py` | 加新事件类型(如快捷键组合统计)/ 修饰键追踪 |
| `db.py` | 新增聚合查询 / 新迁移版本 |

## 惯用模式
```python
# 1. 取主题色
c = theme.current().colors

# 2. 声明式字段 (settings_panel.py),第 4 参为常驻说明
FieldSpec("switch", "auto_start", "开机自启动", "随系统登录后自动在托盘启动")

# 3. 页面生命周期
class XxxPage(BasePage):
    name = "xxx"
    def _build(self) -> None: ...
    def _do_refresh(self) -> None: ...
    def _do_apply_theme(self) -> None: ...

```