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
  - raw 表 (`keypresses`) 默认 7 天后自动清理,可调
  - 自动 7 天一次备份到 `backups/`,保留 7 份日备 + 4 份周备
  - 手动备份 / VACUUM / 保留天数均可通过托盘菜单调整
- **系统托盘**: 显示窗口 / 暂停 / 数据管理 / 退出 / 切换设置
- **设置** (托盘菜单内):
  - 关闭窗口 → 隐藏到托盘 (默认开)
  - 开机自启 (默认关)

## 项目结构

```
key_note/
├── key_note.py         # 入口
├── config.py           # 配置持久化
├── db.py               # SQLite 异步写入 + 聚合表 + 备份 + 保留
├── listener.py         # pynput 键盘监听
├── tray.py             # pystray 系统托盘 (含数据管理子菜单)
├── window.py           # customtkinter 主窗口 + 图表
├── keynote.db          # 数据 (运行后自动创建)
├── keynote.db-wal      # WAL 日志 (运行中)
├── keynote.db-shm      # 共享内存 (运行中)
├── config.json         # 用户配置 (运行后自动创建)
├── backups/            # 自动备份目录 (运行后自动创建)
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

## 依赖 (均已安装)

| 包 | 用途 |
|----|------|
| `customtkinter` | GUI |
| `matplotlib` | 图表 |
| `pynput` | 全局键盘监听 |
| `pystray` | 系统托盘 |
| `Pillow` | 托盘图标 |
| `numpy` | 热力图数据 |

## 数据隐私

- 只记录按键名 + 时间戳
- **不记录**当前窗口、应用名、剪贴板、按键周围文本
- 数据完全本地 (`keynote.db`)
- 自动备份也仅存于本地 `backups/` 目录

## 配置 (config.json)

```json
{
  "auto_start": false,
  "close_to_tray": true,
  "refresh_interval_sec": 5,
  "heatmap_days": 7,
  "rate_chart_hours": 24,
  "db_flush_batch_size": 200,
  "db_flush_interval_sec": 1.0,
  "db_retention_days": 7,
  "db_auto_backup_days": 7
}
```

## 数据库 Schema

| 表 | 说明 |
|---|---|
| `keypresses` | 原始按键记录 (受保留策略影响) |
| `sessions` | 录制会话 (启动/结束时间) |
| `agg_minute` | 每分钟按键总数 (永久) |
| `agg_hour` | 每小时按键总数 (永久) |
| `agg_dow_hour` | 按 (星期, 小时) 累计 (永久) |
| `agg_key_total` | 按键累计次数 (永久) |
| `schema_version` | 迁移版本 |