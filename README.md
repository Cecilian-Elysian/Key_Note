# KeyNote - 键盘 / 鼠标使用统计

轻量级 Windows 单机输入统计工具,WinUI3 原生实现(.NET 8 + Windows App SDK,非打包自包含)。

紧凑 800×600 窗口、Win11 Mica 材质、永久暗色 Fluent 主题,无需管理员权限安装。

## 功能

- **全局输入监听**(`InputHookService`,Win32 低级钩子)
  - 键盘:字母 / 数字 / 符号 / 修饰键 / 功能键 五类自动分类
  - 鼠标:左 / 右 / 中 / X1 / X2 五键
  - 80ms 去重窗口,过滤 OS auto-repeat 虚高
- **5 页侧边栏界面**(左侧导航 + 药丸选中态,快捷键 Alt+1~5)
  - **统计页**:时间范围筛选(今日 / 近 7 天 / 近 30 天)+ 3 张 KPI 卡(累计按键 / 鼠标点击 / 活跃天数)+ 键型分布胶囊行 + 按键趋势图(悬停十字线)
  - **后台页**:7×24 小时活跃度热力图 + QWERTY 键盘按键分布热力图
  - **热力图页**:GitHub 风格年度热力图(活跃天数 / 峰值概要)
  - **常用按键页**:Top 10 按键横向条形图
  - **设置页**:声明式字段表(3 组配置 + 分组"高级设置"折叠区 + 搜索过滤 + 固定底栏)
- **异步 SQLite**(`KeyNoteDb`)
  - 队列 + 后台 writer 线程批写,读写连接分离,WAL + NORMAL synchronous,长期运行零卡顿
  - 聚合表永久保留,毫秒级查询;raw 按键记录默认 365 天自动清理
  - 自动周期备份(保留 7 份日备 + 4 份周备);手动备份 / VACUUM / CSV 导出
  - 数据库迁移 v1~v6,启动自动升级,与历史 Python 版库完全兼容
- **系统托盘**(`TrayService`,纯 Win32):显示窗口 / 暂停监听 / 实时统计 / 数据管理 / 退出;图标按 accent 色 30% tint 渲染
  - Win11 可能默认把图标收进溢出区(`^`):右键任务栏 → 任务栏设置 → 其他系统托盘图标 → 打开 KeyNote,即可常显在任务栏
- **数据隐私**
  - 只记录按键名 + 时间戳,**不记录**窗口 / 应用名 / 剪贴板 / 按键上下文
  - 数据完全本地,默认存到 `%LOCALAPPDATA%\KeyNote\`

## 安装

运行 `KeyNote_Setup.exe` 安装即可,无需管理员权限、无需 UAC。

> 便携版:直接运行 `dist/KeyNote.App.exe`;在同目录放一个 `portable.flag` 可让数据落在该目录。

## 数据存储位置

| 来源 | 存储目录 |
|---|---|
| 安装版(推荐) | `%LOCALAPPDATA%\KeyNote\` |
| 便携版(同目录 `portable.flag`) | KeyNote.App.exe 同级目录 |

目录内含 `keynote.db`(数据)/ `config.json`(配置)/ `backups/`(备份)/ `keynote.crash.log`(异常日志)。

## 运行(开发模式)

```bash
dotnet build src/KeyNote.App/KeyNote.App.csproj -c Debug -p:Platform=x64
src/KeyNote.App/bin/x64/Debug/net8.0-windows10.0.19041.0/win-x64/KeyNote.App.exe
```

要求 .NET 8 SDK + Windows 10 1809 以上。产物自包含,目标机器无需预装 .NET 运行时。

## 打包

```bash
powershell -ExecutionPolicy Bypass -File build.ps1
```

一键完成:杀残留实例 → 保留便携版用户数据 → `dotnet publish`(Release/x64/self-contained)→ 发布瘦身(去 pdb、裁卫星语言目录)→ Inno Setup 编译安装包。产出:

- `dist\` — 便携版(~95MB,自包含)
- `dist\KeyNote_Setup.exe` — 安装包(同步在 `installer\`)

> 本机 Inno Setup 6 安装于 `%LOCALAPPDATA%\Programs\Inno Setup 6\`(不在 PATH),缺失时跳过安装包步骤。

## 依赖

| 组件 | 版本 | 用途 |
|---|---|---|
| .NET SDK | 8.0+ | 编译 |
| Windows App SDK | 1.7 | WinUI3 运行时(自包含) |
| Microsoft.Data.Sqlite | 9.0.0 | SQLite 访问 |
| System.Drawing.Common | 8.0.7 | 托盘图标 tint 渲染 |

## 配置(config.json)

常规配置全部在设置页修改、保存即生效(自启 / 静默启动 / 关闭到托盘 / 闲置暂停 / 透明度 / 保留天数 / 备份目录等)。少数底层项仅可手编 `config.json`:`data_dir`(数据目录,重启生效)、`db_flush_batch_size` / `db_flush_interval_sec`(写盘节奏)、`db_auto_backup_days`(自动备份周期)。

## 项目结构

```
key_note/
├── KeyNote.sln           # 解决方案
├── src/
│   ├── KeyNote.App/      # WinUI3 壳:App / MainWindow / 5 页 / 7 控件 / 5 服务
│   └── KeyNote.Core/     # 无 UI:AppSettings / KeyNoteDb / InputHookService / AppPaths / CrashLog
├── build.ps1             # 一键构建:publish → 瘦身 → 安装包 → dist/
├── KeyNote_Setup.iss     # Inno Setup 安装脚本
├── icon.ico              # 应用 / 托盘图标(蓝色圆环)
├── dist/                 # 便携版产物 + KeyNote_Setup.exe
└── installer/            # Inno Setup 产物
```

## 数据库 Schema

| 表 | 说明 |
|---|---|
| `schema_version` | 迁移版本(v1~v6,启动自动升级) |
| `sessions` | 录制会话(启动 / 结束时间) |
| `keypresses` | 原始按键记录(受保留策略影响) |
| `mouse_clicks` | 原始鼠标点击(受保留策略影响) |
| `agg_minute` / `agg_hour` / `agg_day` | 每分 / 每时 / 每日按键总数(本地时区分桶;永久) |
| `agg_dow_hour` | 按(星期,小时)累计(永久) |
| `agg_key_total` / `agg_key_type_total` | 按键累计 / 键型累计(letter/digit/symbol/modifier/function;永久) |
| `agg_mouse_button_total` | 鼠标按键累计(永久) |

## 路线图

- [ ] **应用内更新检查**:对接 GitHub Releases(`Cecilian-Elysian/Key_Note`)
  - 设置页(或关于区)提供「检查更新」:请求 Releases API,比对最新 tag 与当前程序集版本(`Assembly.GetExecutingAssembly().GetName().Version`)
  - 有新版 → 托盘气泡通知 + 设置页提示,附 Release 页链接(用系统浏览器打开)
  - 下载方式先走浏览器手动下载 `KeyNote_Setup.exe`;应用内静默更新(下载 + 校验 + 拉起安装)后续评估
  - 约束:保持单机工具轻量,不引入更新框架依赖(不用 Squirrel/Velopack),实现放 `Services/UpdateService.cs`,设置页/托盘各加一个入口

## 参与开发

克隆本仓库 → `dotnet build` → 运行产物。开发约定见 `AGENTS.md`。

## 许可

MIT
