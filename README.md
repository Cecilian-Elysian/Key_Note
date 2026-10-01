# KeyNote - 键盘 / 鼠标使用统计

轻量级 Windows 单机输入统计工具,纯 Python 实现 (`customtkinter` + `matplotlib` + `pynput`)。

紧凑 400×550 窗口、永久暗色主题、无需管理员权限安装。

## 截图(略)

## 功能

- **全局输入监听**
  - 键盘: 字母 / 数字 / 符号 / 修饰键 / 功能键 五类自动分类
  - 鼠标: 左/右/中/X1/X2 五键
  - 80ms 去重窗口,过滤 OS auto-repeat 虚高
- **2 页界面** (底部 tab 切换)
  - **📊 统计页** (`dashboard.py`): segmented 今日/近 7 天/近 30 天 + 主大数 + 趋势图 (今日 hourly / 7d&30d daily) + GitHub 风格年度热力图
  - **🔧 后台页** (`keyboard.py`): 3 张紧凑副卡 (累计按键 / 鼠标点击 / 活跃天数) + 7×24 活跃度热力图 + QWERTY 键盘热力图
- **异步 SQLite** (`db.py`)
  - 队列 + 后台 writer 线程批写,WAL + NORMAL synchronous,长期运行零卡顿
  - 聚合表永久保留 (`agg_minute` / `agg_hour` / `agg_day` / `agg_dow_hour` / `agg_key_total` / `agg_mouse_button_total` / `agg_key_type_total`),毫秒级查询
  - raw 表 (`keypresses`) 默认 365 天后自动清理
  - 自动 7 天一次备份到 `backups/`,保留 7 份日备 + 4 份周备
  - 手动备份 / VACUUM / 保留天数 / CSV 导出 均通过托盘菜单
  - 数据库迁移 v1~v6,启动自动升级
- **系统托盘** (`tray.py`): 显示窗口 / 暂停监听 / 数据管理子菜单 / 退出 / 设置
- **设置面板** (`settings_panel.py`)
  - 2 组配置(常规设置 / 界面),其余高级参数锁定默认值
  - 含开机自启、启动最小化、闲置暂停、鼠标监听开关、窗口透明度、记住位置、备份目录等
  - 关闭对话框自动保存
- **数据隐私**
  - 只记录按键名 + 时间戳,**不记录**窗口 / 应用名 / 剪贴板 / 按键上下文
  - 数据完全本地,默认存到 `%LOCALAPPDATA%\KeyNote\`

## 安装

下载 [Release](../../releases) 中最新的 `KeyNote_Setup.exe`,运行安装即可。无需管理员权限,无需 UAC。

> 便携版: 直接在 [Release](../../releases) 中下载 `KeyNote.exe`(单文件,无需安装)。

## 数据存储位置

| 来源 | 存储目录 |
|---|---|
| 安装版 (推荐) | `%LOCALAPPDATA%\KeyNote\` |
| 便携版 (exe 同目录) | KeyNote.exe 同级目录 |

目录内含 `keynote.db` (数据) / `config.json` (配置) / `backups/` (备份) / `keynote.log` (日志,需开启)。

如需自定义目录(如 `D:\KeyNoteData`),编辑 `config.json` 把 `"data_dir": ""` 改为目标路径,重启生效。注意旧数据**不会自动迁移**,手动复制过去即可。

## 运行 (开发模式)

```bash
pip install -r requirements.txt
python key_note.py
```

要求 **Python 3.10+**,Windows 系统。

## 打包 (.exe)

```bash
powershell -ExecutionPolicy Bypass -File build.ps1
```

先杀残留 KeyNote.exe → 备份用户数据 → PyInstaller 打包 → 恢复用户数据。产出 `dist\KeyNote.exe` (~42MB)。

如需生成安装包,用 [Inno Setup](https://jrsoftware.org/isinfo.php) 编译 `KeyNote_Setup.iss`,产出 `installer\KeyNote_Setup.exe` (~46MB)。

## 依赖

```bash
pip install -r requirements.txt
```

| 包 | 用途 | 版本范围 |
|---|---|---|
| `customtkinter` | GUI | `>=5.2.0,<6.0` |
| `matplotlib` | 图表 | `>=3.7,<4.0` |
| `pynput` | 全局键盘监听 | `>=1.7.6,<2.0` |
| `pystray` | 系统托盘 | `>=0.19.5,<1.0` |
| `Pillow` | 托盘图标 | `>=10.0,<12.0` |
| `numpy` | 热力图数据 | `>=1.24,<3.0` |

## 配置 (config.json)

```json
{
  "auto_start": false,
  "close_to_tray": true,
  "start_minimized": false,
  "silent_start": false,
  "hide_tray_icon": false,
  "listener_enabled": true,
  "mouse_listener_enabled": true,
  "idle_pause_min": 0,
  "window_alpha": 1.0,
  "window_topmost": false,
  "remember_window_pos": true,
  "_window_geometry": "",
  "db_retention_days": 365,
  "db_auto_backup_days": 7,
  "backup_keep_daily": 7,
  "backup_keep_weekly": 4,
  "db_flush_batch_size": 200,
  "db_flush_interval_sec": 1.0,
  "log_to_file": false,
  "heatmap_days": 365,
  "font_family": "Microsoft YaHei UI",
  "data_dir": "",
  "backup_dir": ""
}
```

完整配置可在主窗口 ⚙ 设置面板修改,也可直接编辑 `config.json`。大部分配置保存即生效,下列项 **重启后** 生效: `start_minimized` / `silent_start` / `hide_tray_icon` / `listener_enabled` / `mouse_listener_enabled` / `window_topmost` / `db_auto_backup_days` / `db_flush_batch_size` / `db_flush_interval_sec` / `heatmap_days` / `backup_dir` / `data_dir`。

> **锁定默认值、不暴露 UI** 的配置(仍可手编 `config.json` 修改):
> - `font_family` 字体
> - 数据库与备份组(`db_auto_backup_days` / `backup_keep_*` / `db_flush_*` / `data_dir`)
> - 高级功能组(`heatmap_days` / `idle_pause_min` / `log_to_file`)

## 项目结构

```
key_note/
├── key_note.py         # 入口,按序启动 DB → 窗口 → 监听 → 托盘 → mainloop
├── config.py           # 配置持久化 + exe_dir() PyInstaller 兼容
├── db.py               # SQLite 异步写入 + 聚合表 + 备份 + 迁移 v1~v6
├── listener.py         # pynput 键盘+鼠标监听 + 按键分类 + 暂停/恢复
├── settings_panel.py   # 设置面板 (FieldSpec 声明式)
├── theme.py            # 设计令牌 (dark 主题集中管)
├── tray.py             # pystray 系统托盘
├── window.py           # 主窗口 (2 页 + tab bar + 自动刷新)
├── ui/
│   ├── pages/          # 页面: dashboard / keyboard (+ 占位 heatmap/top_keys/settings)
│   └── widgets/        # 组件: gh_heatmap (年度热力图) / chart_utils (matplotlib 工厂)
├── build.ps1           # 一键构建脚本
├── KeyNote_Setup.iss   # Inno Setup 安装脚本
├── requirements.txt    # 运行时依赖
├── dist/               # PyInstaller 产物 (KeyNote.exe,便携版)
└── installer/          # Inno Setup 产物 (KeyNote_Setup.exe,安装版)
```

## 数据库 Schema

| 表 | 说明 |
|---|---|
| `schema_version` | 迁移版本 (v1~v6,启动自动升级) |
| `sessions` | 录制会话 (启动/结束时间) |
| `keypresses` | 原始按键记录 (受保留策略影响,默认 365 天) |
| `mouse_clicks` | 原始鼠标点击 (受保留策略影响,v5 引入) |
| `agg_minute` | 每分钟按键总数 (本地整分;永久) |
| `agg_hour` | 每小时按键总数 (本地整点;永久) |
| `agg_day` | 每日按键总数 (本地午夜;永久;v4 引入) |
| `agg_dow_hour` | 按 (星期, 小时) 累计 (永久) |
| `agg_key_total` | 按键累计次数 (永久) |
| `agg_mouse_button_total` | 鼠标按键累计 (永久;v5 引入) |
| `agg_key_type_total` | 按键类型累计 (letter/digit/symbol/modifier/function;v6 引入) |

> 历史 v3 之前 `agg_day` 桶按 UTC 午夜分桶,导致 UTC+8 时区凌晨 00:00–08:00 按键被错误归类。v4 修复后改用本地午夜分桶,首次启动会自动迁移。

## 参与开发

克隆本仓库 → `pip install -r requirements.txt` → `python key_note.py`。开发约定见 `AGENTS.md`。

## 许可

MIT
