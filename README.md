# KeyNote - 键盘记录器

轻量级键盘按键使用统计工具,纯 Python (customtkinter + matplotlib)。

## 功能

- **后台键盘监听**: 全局记录每次按键 (含字母、数字、功能键)
- **异步写入**: 队列 + 后台 writer 线程批量提交,长期使用零卡顿
- **统计图表** (从聚合表读取,毫秒级响应):
  - 总量速率 (过去 24h 每分钟按键数)
  - 7×24 活跃度热力图 (周一~周日 × 0~23 小时)
  - Top 20 按键排行
- **数据长期保存**:
  - WAL + NORMAL synchronous,崩溃安全 + 高吞吐
  - 聚合表 (`agg_minute` / `agg_hour` / `agg_dow_hour` / `agg_key_total`) 永久保留
  - raw 表 (`keypresses`) 默认 365 天后自动清理,可调
  - 自动 7 天一次备份到 `backups/`,保留 7 份日备 + 4 份周备(锁定默认,不可配置)
  - 手动备份 / VACUUM / 保留天数均可通过托盘菜单调整
- **系统托盘**: 显示窗口 / 暂停 / 数据管理 / 退出 / 设置
- **设置面板** (从托盘菜单 "⚙ 设置..." 进入):
  - 3 组配置(常规设置 / 全局热键 / 界面),其余高级参数锁定默认值
  - 含启动最小化、闲置自动暂停、全局热键、主题、字体、窗口透明度、记住窗口位置等

## 项目结构

```
key_note/
├── key_note.py         # 入口 (按 start_minimized / listener_enabled 分支)
├── config.py           # 配置持久化 + exe_dir() PyInstaller 兼容
├── db.py               # SQLite 异步写入 + 聚合表 + 备份 + 保留 + CSV 导出 + 日志
├── listener.py         # pynput 键盘监听
├── tray.py             # pystray 系统托盘 (含数据管理子菜单 + 设置入口)
├── window.py           # customtkinter 主窗口 + 图表 + 设置回调
├── settings_panel.py   # 设置面板 (主窗口第 4 个 Tab)
├── theme.py            # 颜色/间距/圆角 设计令牌 + dark/light 主题
├── keynote.db          # 数据 (运行后自动创建,位置由 data_dir 决定)
├── keynote.db-wal      # WAL 日志 (运行中)
├── keynote.db-shm      # 共享内存 (运行中)
├── keynote.log         # 日志 (启用 log_to_file 后创建)
├── config.json         # 用户配置 (运行后自动创建)
├── backups/            # 自动备份目录
├── ui/                 # UI 子包
│   ├── pages/          # 页面类 (dashboard / heatmap / rate / top_keys / settings)
│   └── widgets/        # 复用组件 (gh_heatmap / chart_utils)
├── build.ps1           # 一键构建脚本 (备份用户数据 → PyInstaller → 恢复)
├── KeyNote.spec        # PyInstaller 配置
├── KeyNote_Setup.iss   # Inno Setup 安装脚本
├── requirements.txt    # 运行时依赖 (customtkinter / matplotlib / pynput / pystray / Pillow / numpy)
├── dist/               # PyInstaller 产物 (便携版 KeyNote.exe)
├── installer/          # Inno Setup 产物 (KeyNote_Setup.exe)
└── .gitignore
```

## 运行

```bash
python key_note.py
```

## 打包 (.exe)

```bash
pyinstaller --noconfirm --windowed --onefile --name KeyNote key_note.py
```

## 依赖

```bash
pip install -r requirements.txt
```

| 包 | 用途 | 版本范围 |
|----|------|---------|
| `customtkinter` | GUI | `>=5.2.0,<6.0` |
| `matplotlib` | 图表 | `>=3.7,<4.0` |
| `pynput` | 全局键盘监听 | `>=1.7.6,<2.0` |
| `pystray` | 系统托盘 | `>=0.19.5,<1.0` |
| `Pillow` | 托盘图标 | `>=10.0,<12.0` |
| `numpy` | 热力图数据 | `>=1.24,<3.0` |

## 数据隐私

- 只记录按键名 + 时间戳
- **不记录**当前窗口、应用名、剪贴板、按键周围文本
- 数据完全本地 (`keynote.db`),默认存到 KeyNote.exe 同目录
- 自动备份也仅存于本地 `backups/` 目录

## 配置 (config.json)

```json
{
  "auto_start": false,
  "close_to_tray": true,
  "start_minimized": false,
  "listener_enabled": true,
  "idle_pause_min": 0,
  "theme": "dark",
  "font_family": "Microsoft YaHei UI",
  "window_alpha": 1.0,
  "remember_window_pos": true,
  "_window_geometry": "",
  "chart_auto_refresh": true,
  "refresh_interval_sec": 5,
  "heatmap_days": 7,
  "rate_chart_hours": 24,
  "db_retention_days": 365,
  "db_auto_backup_days": 7,
  "backup_keep_daily": 7,
  "backup_keep_weekly": 4,
  "db_flush_batch_size": 200,
  "db_flush_interval_sec": 1.0,
  "log_to_file": false,
  "enable_global_hotkey": false,
  "global_hotkey": "ctrl+shift+k",
  "data_dir": ""
}
```

完整配置可在主窗口 **设置** 选项卡里改,也可直接编辑 `config.json`。大部分配置保存即生效,下列项 **重启后** 生效: `start_minimized`、`listener_enabled`、`theme`(主题切换需重启刷新所有 widget 颜色)。

> **锁定默认值、不暴露 UI** 的配置(仍可手编 `config.json` 修改):
> - `font_family` 字体(默认 Microsoft YaHei UI;UI 不再提供下拉)
> - 数据库与备份组(自动备份间隔 / 保留份数 / 批量写入大小 / 写入间隔 / 数据目录)
> - 高级功能组(图表自动刷新 / 刷新间隔 / 热力图天数 / 闲置自动暂停 / 日志写入)

## 数据存储位置

默认情况下(安装版),`keynote.db` / `config.json` / `backups/` / `keynote.log` 都放在 `%LOCALAPPDATA%\KeyNote\` 下。便携版(直接运行 KeyNote.exe 不安装)放到 KeyNote.exe 同目录。

如需自定义数据存储目录(例如存到 D:\KeyNoteData),设置面板不再提供此选项,只能**手动编辑 `config.json`**:把 `"data_dir": ""` 改为 `"data_dir": "D:\\KeyNoteData"`,重启生效。

注意:修改 `data_dir` 后,旧位置的数据**不会自动迁移**(因为每个 app 用户的数据习惯不同)。如需迁移,手动把 `keynote.db` / `config.json` / `backups/` 复制到新位置即可。

> 数据库与备份组(自动备份间隔 / 保留份数 / 批量写入大小)与高级功能组(图表刷新 / 刷新间隔 / 热力图天数)的所有参数均锁定为默认值,不再提供 UI 调整入口。

## 数据库 Schema

| 表 | 说明 |
|---|---|
| `schema_version` | 迁移版本 (v1~v4,每次启动自动迁移) |
| `sessions` | 录制会话 (启动/结束时间) |
| `keypresses` | 原始按键记录 (受保留策略影响,默认 365 天) |
| `agg_minute` | 每分钟按键总数 (本地整分;永久) |
| `agg_hour` | 每小时按键总数 (本地整点;永久) |
| `agg_day` | 每日按键总数 (本地午夜;永久;v4 引入) |
| `agg_dow_hour` | 按 (星期, 小时) 累计 (永久) |
| `agg_key_total` | 按键累计次数 (永久) |

> 历史 v3 之前 `agg_day` 桶按 UTC 午夜分桶,导致 UTC+8 时区凌晨 00:00–08:00 按键被错误归类。v4 修复后改用本地午夜分桶,首次启动会自动迁移。