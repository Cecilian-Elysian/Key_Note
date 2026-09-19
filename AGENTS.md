# 项目风格指南 — KeyNote

## 核心理念
- **简洁小巧** — 不堆功能,不建多余文件,不改框架
- **Windows 单机工具** — pynput 键盘监听 + SQLite 持久化 + customtkinter UI + pystray 托盘

## 架构约束
- 主窗口硬编码 `400×550`,不响应式
- 2 页(统计 / 后台),底部 tab bar 切换,默认 Page 1 = 统计
  - Page 1 `OverviewPage`(`dashboard.py`):segmented 主卡 + 趋势图 + WPM + GH 年度
  - Page 2 `KeyboardPage`(`keyboard.py`):3 紧凑副卡 + 7×24 + QWERTY 键盘热力图(标签显示为"后台")
  - 切换走 `App._switch_page(name)`,auto-refresh 只刷新当前页
- 设置面板通过主窗口顶部 ⚙ 按钮或托盘菜单 `⚙ → SettingsPanel Toplevel` 打开(两入口共用 `settings_panel.open_or_focus()`),而非页面导航

## 代码风格
- **声明式 > 手写**: `settings_panel.py` 用 `FieldSpec` + `GROUPS` 描述控件,扩字段只加一行
- **主题集中管**: `theme.py::ColorTokens` 做颜色 pipeline,页面从 `theme.current().colors` 取
- **页面内部硬编码专属色**: 不污染全局主题,settings 面板的卡片底/蓝 toggle/黄 ? 直接写常量
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
| `settings_panel.py` | FieldSpec 声明式设置面板 |

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
| `window.py` | 主窗口 UI(2 页 + tab bar)+ 自动刷新 + 闲置检测 + 设置回调 |
| `ui/pages/base.py` | BasePage 基类 |
| `ui/pages/dashboard.py` | OverviewPage(Page 1):segmented 主卡 + 趋势图 + WPM + GH 热力图 |
| `ui/pages/keyboard.py` | KeyboardPage(Page 2):3 副卡 + 7×24 + QWERTY 键盘热力图 |

### 6. 主题系统
| 文件 | 职责 |
|---|---|
| `theme.py` | 仅 dark 一套 ColorTokens(2026-07-13 起永久移除亮色)+ apply/recolor |

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

## 死代码(暂不动)
`ui/pages/{heatmap,top_keys,settings}.py` — 3 个页面,有完整实现但未挂载到 `App._build_ui`,后续可作第 3 页候选恢复。
`ui/pages/keyboard.py` 是原 `rate.py` 改名 + 内容重写后激活为 Page 2,已不属于死代码。
`ui/widgets/chart_utils.py` 已从死代码复活(供 dashboard 趋势图复用)。

## 硬约束(违反即不收)
- `theme.py` **只有 dark 一套**,不新增亮色 / 第三方主题,页内专属色直接写模块顶部常量
- **不建新文件**,扩功能优先走现有模块(扩 `FieldSpec` 加字段 / 扩 `tray.py` 加方法 / 扩 `window.py` 加回调分支)
- **不删死代码**(3 个 ui/pages 占位:`heatmap` / `top_keys` / `settings`),它们是后续页面恢复的占位
- `build.ps1` 删 PyInstaller 工作目录只删 `build/KeyNote/`,**禁止** `Remove-Item build/`(会把 `build/_data_bak/` 用户备份一起删)
- `build.ps1` 调 Python 用 `py`(WindowsApps 的 `python.exe` 是占位 stub)
- `build.ps1` **不写中文字符串**(PowerShell 5.1 解析报错);`KeyNote_Setup.iss` 中文可用(Inno Setup 6 实测通过,2026-09-19)
- 配色 / 图标颜色 / toggle 进度色等页内专属视觉色,**写在对应页面模块顶部常量**,不污染 `theme.py`

## 未来规划

潜在接入功能,按文件分:

| 文件 | 可扩展方向 |
|---|---|
| `settings_panel.py` | 加新字段 → GROUPS 加一行 + config.py 加默认值 + 对应模块加处理逻辑 |
| `dashboard.py` | 新增图表类型 / 布局微调 / 数据维度扩展 |
| `theme.py` | **不动**—dark 一套已足够 |
| `window.py` | 加新回调分支处理新配置;扩展第 3 页 |
| `tray.py` | 加新菜单项 / 托盘交互优化 |
| `listener.py` | 加新事件类型(如快捷键组合统计)/ 修饰键追踪 |
| `db.py` | 新增聚合查询 / 新迁移版本 |

## 惯用模式
```python
# 1. 取主题色
c = theme.current().colors

# 2. 声明式字段 (settings_panel.py)
FieldSpec("switch", "auto_start", "开机自启动")

# 3. 页面生命周期
class XxxPage(BasePage):
    name = "xxx"
    def _build(self) -> None: ...
    def _do_refresh(self) -> None: ...
    def _do_apply_theme(self) -> None: ...

```