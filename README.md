# KeyNote - 键盘 / 鼠标使用统计

轻量级 Windows 单机输入统计工具,WinUI3 原生实现(.NET 8 + Windows App SDK,非打包)。

紧凑 800×600 窗口、Win11 Mica 材质、永久暗色 Fluent 主题,无需管理员权限安装。

## 功能

- **全局输入监听**(`InputHookService`,Win32 低级钩子)
  - 键盘:字母 / 数字 / 符号 / 功能键 四类自动分类(修饰键只记活跃,不计入统计)
  - 鼠标:左 / 右 / 中 / X1 / X2 五键
  - 按物理按下计数(系统自动重复只算一次),Shift / CapsLock / AltGr 正确还原字符
- **5 页侧边栏界面**(左侧导航,快捷键 Alt+1~5)
  - **统计页**:时间范围筛选(今日 / 近 7 天 / 近 30 天)+ 3 张 KPI 卡(范围内按键 / 鼠标点击 / 活跃天数)+ 键型分布胶囊行 + 按键趋势图(悬停十字线)
  - **后台页**:7×24 小时活跃度热力图 + QWERTY 键盘按键分布热力图
  - **热力图页**:GitHub 风格年度热力图(活跃天数 / 峰值概要,按设置天数动态扩展,最多 730 天)
  - **常用按键页**:Top 10 按键横向条形图(与键盘热力图同为合并大小写口径)
  - **设置页**:声明式字段表(4 组配置 + 分组"高级设置"折叠区 + 搜索过滤 + 固定底栏)
- **异步 SQLite**(`KeyNoteDb`)
  - 队列 + 后台 writer 线程批写,读写连接分离,WAL + NORMAL synchronous,长期运行零卡顿
  - 聚合表永久保留,毫秒级查询;raw 按键记录默认 365 天自动清理
  - 自动周期备份(保留 7 份日备 + 4 份周备);手动备份 / VACUUM / CSV 导出
  - 数据库迁移 v1~v6,启动自动升级,与历史 Python 版库完全兼容
- **系统托盘**(`TrayService`,纯 Win32):显示窗口 / 暂停监听 / 实时统计 / 最近活动 / 数据管理 / 设置 / 检查更新 / 退出;图标按 accent 色 30% tint 渲染
  - Win11 可能默认把图标收进溢出区(`^`):右键任务栏 → 任务栏设置 → 其他系统托盘图标 → 打开 KeyNote,即可常显在任务栏
- **应用内更新检查**(`UpdateService`)
  - 设置页「关于」分组「检查更新」+ 托盘「🔄 检查更新」;启动后每日静默检查一次(24h 判重)
  - 比对 GitHub Releases 最新稳定版与当前程序集版本(组件式比较,同版本不误报;预发布/草稿版自动排除)
  - **发现新版 → 托盘气泡提示 → 点气泡 → 确认框(版本对比 + 更新说明)→ 应用内下载安装包 → 自动替换并重启**
  - 便携版运行副本无法自动安装(没有安装器可替换自己),改为提示并打开下载页
  - 不引入更新框架依赖(不用 Squirrel/Velopack)
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

要求 .NET 8 SDK + Windows 10 2004(19041)以上。
产物为**框架依赖 .NET**(需目标机已装 .NET 8 运行时);Windows App SDK 运行时已随包自带,无需另装。

## 打包

```bash
powershell -ExecutionPolicy Bypass -File build.ps1
```

一键完成:杀残留实例 → 备份便携版用户数据 → `dotnet publish`(Release/x64)→ 发布瘦身(去 pdb、裁卫星语言目录)→ 还原用户数据(校验通过才删备份)→ 体积构成报告 → Inno Setup 编译安装包。产出:

- `dist\` — 便携版(~95MB,其中约 88MB 是 Windows App SDK 运行时)
- `installer\KeyNote_Setup.exe` — 安装包(22MB)

> 打包源是干净 staging(`build\setup_stage`),**不会把用户数据打进安装包**。
> 本机 Inno Setup 6 安装于 `%LOCALAPPDATA%\Programs\Inno Setup 6\`(不在 PATH);缺失时脚本以 exit 2 结束并提示。

## 依赖

| 组件 | 版本 | 用途 |
|---|---|---|
| .NET SDK | 8.0+(本机 10.0 可编 net8.0) | 编译 |
| .NET 运行时 | 8.0 | **目标机需预装**(产物非 .NET 自包含) |
| Windows App SDK | 1.7.260224002 | WinUI3 运行时(随包自带) |
| Microsoft.Windows.SDK.BuildTools | 10.0.26100.1742 | WinUI 编译期 |
| Windows SDK NET Ref | 10.0.19041.38 | WinUI 编译期 |
| Microsoft.Data.Sqlite | 9.0.0 | SQLite 访问 |
| System.Drawing.Common | 8.0.7 | 托盘图标 tint 渲染 |

## 配置(config.json)

常规配置全部在设置页修改、保存即生效(自启 / 静默启动 / 关闭到托盘 / 闲置暂停 / 透明度 / 保留天数 / 备份目录等)。少数底层项仅可手编 `config.json`:`data_dir`(数据目录,重启生效)、`db_flush_batch_size` / `db_flush_interval_sec`(写盘节奏)、`db_auto_backup_days`(自动备份周期)。

## 项目结构

```
key_note/
├── KeyNote.sln           # 解决方案
├── src/
│   ├── KeyNote.App/      # WinUI3 壳:App / MainWindow / 5 页 / 9 控件 / 8 服务
│   └── KeyNote.Core/     # 无 UI:AppSettings / KeyNoteDb(4 分部) / InputHookService / AppPaths / CrashLog
├── build.ps1             # 一键构建:publish → 瘦身 → 体积报告 → 安装包 → dist/
├── KeyNote_Setup.iss     # Inno Setup 安装脚本
├── icon.ico              # 应用 / 托盘图标(蓝色圆环)
├── dist/                 # 便携版产物(构建产物,不入库)
└── installer/            # Inno Setup 产物(构建产物,不入库)
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
| `agg_key_total` / `agg_key_type_total` | 按键累计 / 键型累计(letter/digit/symbol/function;永久) |
| `agg_mouse_button_total` | 鼠标按键累计(永久) |

> `agg_dow_hour` 按(星期,小时)累计,**当前只写不读**(留作作息画像的数据基础)。

## 统计口径变更(2026-10)

本轮修了几处统计失真,历史数据的含义随之变化,**数字变小属正常**:

| 变更 | 原因 | 影响 |
|---|---|---|
| 长按只计一次 | 原按 80ms 窗口去重,而系统首次自动重复延迟 250~500ms → 长按被算 2 次以上 | 累计总数下降(更接近真实按键次数) |
| 大小写正确还原 | 原 `GetKeyboardState` 在钩子线程恒为空 → Shift+A 记成 "a" | 键名分布变化(大小写不再分开统计) |
| 鼠标点击精确计数 | 原鼠标钩子结构体缺 `POINT` 字段 + 消息常量用错 → 按鼠标 X 坐标记按钮 | 鼠标总数大幅下降(原为垃圾数据) |
| KPI 跟随时间筛选 | 原「累计按键 / 鼠标点击」恒为全时口径 | 选「今日」时显示当日数字 |
| 键盘热力图 / Top10 合并大小写 | 原两页口径不一致(`a`/`A` 分开 vs 合并) | 两页数字现在对得上 |
| 年度热力图按设置天数展开 | 原固定 53 周,`heatmap_days > 371` 时超出部分被丢弃 | 730 天设置现在完整显示 |
| 非 ASCII 字符归入字母类 | 原按 ASCII 字符集判定,中文输入的每个字都被算成「功能键」 | 功能键占比大幅下降(原先 18% 里绝大部分是中文输入) |
| 修饰键不再计入统计 | 修饰键只触发活动不记录,原先仍占一个「修饰键」分类位 | 键型胶囊从 5 项变 4 项,占比加总为 100% |

## 路线图

- [x] **应用内更新检查**:对接 GitHub Releases(`Cecilian-Elysian/Key_Note`)
  - 设置页「关于」分组「检查更新」+ 托盘「🔄 检查更新」,启动后每日静默检查一次
  - 比对最新稳定版与当前程序集版本(预发布/草稿排除);发现新版 → 托盘气泡 → 确认框 → 应用内下载 → 自动替换并重启
  - 实现见 `Services/UpdateService.cs` / `UpdateInstaller.cs` / `UpdatePrompt.cs`;不引入更新框架依赖(不用 Squirrel/Velopack)
- [x] ~~应用内静默更新~~:已实现(应用内下载 + 大小校验 + 拉起安装器,安装器用 Restart Manager 自动替换并重启)
- [ ] **发布体积瘦身**:当前 `dist` 95MB 中约 88MB 是 Windows App SDK 自带运行时
  - 已确认 `Microsoft.Windows.SDK.NET.dll` 单文件占 23.8MB(疑似重复的旧式 SDK 投影),需实验验证
  - 可裁项:Widgets / AI / 通知推送 / 网页组件 / 任务调度 等应用未使用的模块(约 60 文件 / 12MB)
  - 更彻底的做法:改 `WindowsAppSDKSelfContained=false`,但目标机需预装 Windows App Runtime(本机已装 1.7)

### 发布流程

1. 改 `src/KeyNote.App/KeyNote.App.csproj` 的 `<Version>`(安装包版本由 `build.ps1` 派生,不必手改 `.iss`)
2. `powershell -ExecutionPolicy Bypass -File build.ps1` → 产出 `dist\`(便携)与 `installer\KeyNote_Setup.exe`
3. `git tag v1.0.1 && git push --tags`
4. 在 GitHub 仓库创建 Release:tag 选 `v1.0.1`,上传 `installer\KeyNote_Setup.exe` 作为资产
5. 应用内「检查更新」即可发现新版本(资产名需为 `KeyNote_Setup.exe`;无该资产时仍可打开 Release 页手动下载)

## 参与开发

克隆本仓库 → `dotnet build src/KeyNote.App/KeyNote.App.csproj -c Debug -p:Platform=x64` → 运行产物。开发约定见 `AGENTS.md`。

## 许可

MIT
