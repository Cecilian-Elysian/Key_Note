# KeyNote - 键盘 / 鼠标使用统计

轻量级 Windows 单机输入统计工具,WinUI3 原生实现(.NET 8 + Windows App SDK,非打包自包含)。

紧凑 800×600 窗口、Win11 Mica 材质、永久暗色 Fluent 主题(vigil-watt 视觉复刻)、无需管理员权限安装。

## 功能

- **全局输入监听**
  - 键盘: 字母 / 数字 / 符号 / 修饰键 / 功能键 五类自动分类
  - 鼠标: 左/右/中/X1/X2 五键
  - 80ms 去重窗口,过滤 OS auto-repeat 虚高
- **5 页侧边栏界面** (左侧导航,WinUI 暗色 Fluent 视觉(vigil-watt 复刻) + Win11 Mica 材质,快捷键 Alt+1~5)
  - **📊 统计页** (`Views/StatsPage`): 页头(标题 + 副标题 + 刷新) + 时间范围筛选 + 设备行主卡(图标/进度条/对比胶囊) + 趋势图(悬停十字线) + GitHub 风格年度热力图
  - **⌨️ 后台页** (`Views/KeyboardPage`): 3 张 KPI 副卡(累计按键 / 鼠标点击 / 活跃天数) + 键型分布胶囊行 + 7×24 活跃度热力图 + QWERTY 键盘热力图,各带色阶图例
  - **🔥 热力图页** (`Views/HeatmapPage`): 4 张 KPI 统计卡(今日 / 7 日均 / 30 日均 / 累计) + GitHub 风格年度热力图
  - **⭐ 常用按键页** (`Views/TopKeysPage`): Top 10 按键次数横向条形图
  - **⚙️ 设置页** (`Views/SettingsPage`): 整页设置面板 + 固定底栏
- **异步 SQLite** (`KeyNoteDb`)
  - 队列 + 后台 writer 线程批写,读写连接分离,WAL + NORMAL synchronous,长期运行零卡顿
  - 聚合表永久保留 (`agg_minute` / `agg_hour` / `agg_day` / `agg_dow_hour` / `agg_key_total` / `agg_mouse_button_total` / `agg_key_type_total`),毫秒级查询
  - raw 表 (`keypresses`) 默认 365 天后自动清理
  - 自动 7 天一次备份到 `backups/`,保留 7 份日备 + 4 份周备
  - 手动备份 / VACUUM / 保留天数 / CSV 导出 均通过托盘菜单或设置页
  - 数据库迁移 v1~v6,启动自动升级(与历史 Python 版库完全兼容)
- **系统托盘** (`TrayService`): 显示窗口 / 暂停监听 / 实时统计 / 最近活动 / 数据管理 / 退出 / 设置
- **设置面板** (`SettingsPage`)
  - 3 组配置(启动与常规 / 界面 / 数据)
  - 行式布局:左标题 + 常驻说明 / 右控件,分组标题带强调色竖条,底栏固定不随内容滚动
  - 顶部搜索框按标题/说明过滤设置项
  - 含开机自启、启动最小化、闲置自动暂停、鼠标监听开关、内容透明度、记住位置、保留天数、备份目录等
  - 保存即生效
- **数据隐私**
  - 只记录按键名 + 时间戳,**不记录**窗口 / 应用名 / 剪贴板 / 按键上下文
  - 数据完全本地,默认存到 `%LOCALAPPDATA%\KeyNote\`

## 安装

下载 [Release](../../releases) 中最新的 `KeyNote_Setup.exe`,运行安装即可。无需管理员权限,无需 UAC。

> 便携版: 解压 `dist/` 目录,把 `KeyNote.App.exe` 放在任意目录运行;在同目录放一个 `portable.flag` 即可让数据也落在该目录。

## 数据存储位置

| 来源 | 存储目录 |
|---|---|
| 安装版 (推荐) | `%LOCALAPPDATA%\KeyNote\` |
| 便携版 (同目录 `portable.flag`) | KeyNote.App.exe 同级目录 |

目录内含 `keynote.db` (数据) / `config.json` (配置) / `backups/` (备份) / `keynote.crash.log` (异常日志)。

如需自定义目录,在设置页「数据 → 备份目录」或编辑 `config.json` 的 `"data_dir"` 字段,重启生效。旧数据**不会自动迁移**,手动复制过去即可。

## 运行 (开发模式)

```bash
dotnet build src/KeyNote.App/KeyNote.App.csproj -c Debug -p:Platform=x64
src/KeyNote.App/bin/x64/Debug/net8.0-windows10.0.19041.0/win-x64/KeyNote.App.exe
```

要求 **.NET 8 SDK**(或更新的 SDK,按 `net8.0-windows10.0.19041.0` 目标编译)+ Windows 10 1809 以上。运行时自包含,目标机器无需预装 .NET 运行时。

## 打包

```bash
powershell -ExecutionPolicy Bypass -File build.ps1
```

先杀残留 KeyNote.App → 备份用户数据 → `dotnet publish`(Release/x64/self-contained)→ 恢复用户数据。产出 `dist\KeyNote.App.exe` 及整套自包含运行时(~98MB)。

如需生成安装包,用 [Inno Setup](https://jrsoftware.org/isinfo.php) 6 编译 `KeyNote_Setup.iss`,产出 `installer\KeyNote_Setup.exe`。

## 依赖

| 组件 | 版本 | 用途 |
|---|---|---|
| .NET SDK | 8.0+(实测 10.0.300) | 编译 |
| Windows App SDK | 1.7 | WinUI3 运行时(自包含,目标机无需安装) |
| `Microsoft.Data.Sqlite` | 9.0.0 | SQLite 访问 |

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

完整配置可在设置页修改,也可直接编辑 `config.json`。大部分配置保存即生效,下列项 **重启后** 生效: `start_minimized` / `silent_start` / `hide_tray_icon` / `db_auto_backup_days` / `db_flush_batch_size` / `db_flush_interval_sec` / `data_dir`。

> **锁定默认值、不暴露 UI** 的配置(仍可手编 `config.json` 修改):
> - `font_family` 字体、`window_topmost`
> - 数据库与备份组(`db_auto_backup_days` / `backup_keep_*` / `db_flush_*` / `data_dir`)
> - 日志组(`log_to_file`)

## 项目结构

```
key_note/
├── KeyNote.sln           # 解决方案
├── src/
│   ├── KeyNote.App/      # WinUI3 壳:App / MainWindow / 5 页 / 6 控件 / 4 服务
│   └── KeyNote.Core/     # 无 UI:AppSettings / KeyNoteDb / InputHookService / AppPaths / CrashLog
├── build.ps1             # 一键构建脚本 (dotnet publish → dist/)
├── KeyNote_Setup.iss     # Inno Setup 安装脚本
├── icon.ico              # 应用 / 托盘图标
├── dist/                 # 发布产物 (自包含,便携版)
└── installer/            # Inno Setup 产物 (安装版)
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

克隆本仓库 → `dotnet build src/KeyNote.App/KeyNote.App.csproj -c Debug -p:Platform=x64` → 运行产物。开发约定见 `AGENTS.md`。

## 许可

MIT
