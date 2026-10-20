# 项目风格指南 — KeyNote(WinUI3 / C#)

## 核心理念
- **简洁小巧** — 不堆功能,不建多余工程,不改技术栈
- **Windows 单机工具** — Win32 LL 钩子 + SQLite 持久化 + WinUI3 界面 + 纯 Win32 托盘

## 架构约束
- 技术栈锁定:`net8.0-windows10.0.19041.0` + Windows App SDK 1.7(`WindowsPackageType=None` 非打包 + `WindowsAppSDKSelfContained=true`)
- 双工程:`src/KeyNote.App`(WinUI 壳 + 页面 + 控件)与 `src/KeyNote.Core`(无 UI:设置 / 存储 / 钩子 / 工具)
- 主窗口硬编码 800×600(按 DPI 缩放),不响应式
- 布局:48px 通栏标题栏(状态胶囊)+ NavigationView 左侧导航(5 页)+ 内容区,切换走 `App._switch_page` 等价的 `MainWindow.NavigateTo(tag)`
- 5 页侧边栏导航(Segoe 字形图标 + 药丸选中态 + 左缘 accent 竖条),快捷键 Alt+1~5
  - Page 1 `StatsPage`(`Views/StatsPage`):页头 + 时间筛选(SelectorBar) + 设备行主卡(进度条/对比胶囊)+ 趋势图(悬停十字线)+ GH 年度热力图
  - Page 2 `KeyboardPage`(`Views/KeyboardPage`):3 张 KPI 副卡 + 键型分布胶囊行 + 7×24 + QWERTY 键盘热力图
  - Page 3 `HeatmapPage`(`Views/HeatmapPage`):4 张 KPI 统计卡 + 年度热力图
  - Page 4 `TopKeysPage`(`Views/TopKeysPage`):Top 10 按键条形图
  - Page 5 `SettingsPage`(`Views/SettingsPage`):声明式字段表(分组/搜索/固定底栏)
- auto-refresh 只刷新当前页(设置页不实现 `IRefreshable`,自然跳过)
- ⚙ 入口(托盘菜单)统一走 `MainWindow.NavigateTo("settings")`
- Win11 Mica 材质(`Services/WindowBackdrop.cs`):Mica → Acrylic → 纯色三级回退;有材质时 `Root.Background = null` + NavigationView pane/content 背景覆写 Transparent(MainWindow.xaml 资源,让材质直透整窗,卡片仍实底)
- 标题栏:`ExtendsContentIntoTitleBar = true` + `SetTitleBar(AppTitleBar)`

## UI 设计语言(WinUI 暗色 Fluent,vigil-watt 复刻)
- 色板 / 间距 / 圆角 / 字号:`theme` 概念在 C# 侧落为 `App.xaml` 资源字典(卡片/字号层级)+ `Theme/UiColors.cs`(语义色)+ `Services/UiPalette.cs`(状态色板)
- 卡片语言:`AppCardStyle`(radius 8 + 1px 描边 + CardBackgroundFillColorDefaultBrush)/ `AppKpiCardStyle`
- KPI 卡三层:标签(12 secondary)/ 数值(24 bold,主卡 hero 32)/ 脚注(11 tertiary)
- 页面骨架:页头(`PageHeader`:标题 18 + 副标题 12 + 右侧"⟳ 刷新"图标+文字钮,padding 20,16)→ 筛选/副卡 → 内容卡;空数据画三段式空状态(图标字形 + 主文案 + 说明)
- 主卡(vigil-watt 设备行):图标 + 标签 + 右侧 hero 数值 + 进度条(达标转绿)+ 语义胶囊 + 脚注
- 趋势图(vigil-watt 电量图签名):2px 圆角线 + 同色 15% 面积 + ≤40 点圆点 + 线端值标签 + 悬停十字虚线/白描边圆点/圆角气泡
- 胶囊(vigil-watt 徽标):语义色文字 + 同色 16% tint 底 `radius 4`(`Helpers/PillFactory`)
- 设置面板:分组标题带强调色竖条,行内左标题 + 常驻说明 / 右控件,行间 1px 分隔线,底栏固定
- 新增颜色一律进 `Theme/UiColors.cs` 或 `App.xaml` 资源;页内专属色写模块顶部常量

## 代码风格
- **声明式 > 手写**: `SettingsPage` 用 `FieldSpec` 数组描述控件,扩字段只加一行
- **主题集中管**: `Theme/UiColors.cs` 做颜色 pipeline,页面从 `Theme.UiColors` 取
- **页面内部硬编码专属色**: 不污染全局主题
- **页面三要素**: XAML + code-behind;实现 `IRefreshable.RefreshData()` 才会被自动刷新
- **松耦合回调**: 模块间通过回调通信,不走直接导入
- **注释规范**: 模块头部加中文 docstring 说明功能,大文件内按功能分区加 `# ──── 标题 ────` 章节注释,不添加逐行注释(代码即文档)
- **每改必提交**: 每次文件修改后写一笔 git commit,变更以 commit message 记录
- **每改必同步 `.gitignore`**: 新文件类型/目录产生后,检查 `.gitignore` 是否需要更新

## 功能模块分类

### 1. 启动与生命周期
| 文件 | 职责 |
|---|---|
| `src/KeyNote.App/Program.cs` | 入口:命名互斥单实例 `Local\KeyNoteSingleInstance` + 唤起已有实例 + XAML 启动 |

### 2. 配置管理
| 文件 | 职责 |
|---|---|
| `src/KeyNote.Core/Settings/AppSettings.cs` | config.json 持久化(字典模型保留未知键 + 原子写)|
| `src/KeyNote.App/Views/SettingsPage.xaml(.cs)` | 声明式设置面板(分组 / 搜索 / 固定底栏) |

### 3. 输入监听(键盘 + 鼠标)
| 文件 | 职责 |
|---|---|
| `src/KeyNote.Core/Input/InputHookService.cs` | Win32 LL 钩子 + 按键分类(letter/digit/symbol/modifier/function)+ 80ms 去重 + 暂停/恢复 |

### 4. 数据持久化
| 文件 | 职责 |
|---|---|
| `src/KeyNote.Core/Storage/KeyNoteDb.cs` | SQLite 读写分离连接 + 聚合(分钟/小时/天/周×时/按键/键型/鼠标)+ 迁移 v1~v6 + 备份/清理/CSV |

### 5. UI 窗口
| 文件 | 职责 |
|---|---|
| `src/KeyNote.App/MainWindow.xaml(.cs)` | 主窗口(标题栏 + 侧边栏 + 5 页 + Mica + 自动刷新 + 关闭到托盘 + Alt+1~5)|
| `src/KeyNote.App/App.xaml(.cs)` | 应用根:设置加载 → DB 初始化 → 钩子 → 托盘 → 窗口显隐策略 + 全局异常落盘 |
| `src/KeyNote.App/Views/*.xaml(.cs)` | 5 个页面 + `IRefreshable` |
| `src/KeyNote.App/Controls/*.xaml(.cs)` | KpiCard / PageHeader / TrendChartControl / GhHeatmapControl / HourlyGridControl / KeyboardHeatmapControl / BarChartControl |
| `src/KeyNote.App/Theme/UiColors.cs` | 暗色语义色板 |
| `src/KeyNote.App/Helpers/PillFactory.cs` | 胶囊徽标工厂 |

### 6. 系统托盘与自启
| 文件 | 职责 |
|---|---|
| `src/KeyNote.App/Services/TrayService.cs` | 纯 Win32 托盘(隐藏消息窗口 + Shell_NotifyIconW + TrackPopupMenuEx,动态菜单)|
| `src/KeyNote.App/Services/AutostartService.cs` | 开机自启(HKCU Run 注册表) |
| `src/KeyNote.App/Services/WindowBackdrop.cs` | Mica/Acrylic 能力探测与回退 |
| `src/KeyNote.App/Services/UiPalette.cs` | 状态语义色板(accent/低电/中/正常/离线) |

### 7. 构建与部署
| 文件 | 职责 |
|---|---|
| `build.ps1` | `dotnet publish`(Release/x64/self-contained)→ `dist/` + 用户数据备份恢复 |
| `KeyNote_Setup.iss` | Inno Setup 安装器(打包 `dist/*`) |

## 硬约束(违反即不收)
- 技术栈只允许 `.NET 8 + Windows App SDK`;不引入第二套 UI 框架
- **不建新工程**;扩功能优先走现有模块(加控件 / 加字段 / 加服务方法)
- `build.ps1` 删发布目录只删 `build/publish/`,**禁止** `Remove-Item build/`(会把 `build/_data_bak/` 用户备份一起删)
- 配色 / 状态色写 `Theme/UiColors.cs` 或页面顶部常量,不散落字面量
- 数据库 schema 与 Python 版保持一致(v1~v6),不破坏既有 `keynote.db`
- WinUI3 非打包窗口不支持整窗透明:`window_alpha` 退化为**内容区**不透明度,不得宣称整窗透明

## 已知取舍(Python → C# 迁移)
- `window_alpha`:WinUI3 不支持整窗 alpha,改为内容区不透明度
- 托盘图标 30% accent tint:GDI+ ColorMatrix 运行时渲染(`TrayService.CreateTintedIcon`,依赖 System.Drawing.Common),失败回退原图
- 图表全部改为 XAML 绘制(无 matplotlib),精度与交互按 vigil-watt 规格复刻

## 惯用模式
```csharp
// 1. 取主题色
var c = Theme.UiColors.Accent;

// 2. 声明式字段 (SettingsPage)
new FieldSpec(FieldKind.Switch, "auto_start", "开机自启动", "系统登录时自动启动 KeyNote。");

// 3. 页面生命周期
public sealed partial class StatsPage : Page, IRefreshable
{
    public StatsPage() { InitializeComponent(); Loaded += (_, _) => RefreshData(); }
    public void RefreshData() { /* 查 KeyNoteDb → 更新控件 */ }
}
```
