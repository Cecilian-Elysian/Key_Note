using KeyNote.App.Services;

namespace KeyNote.App.Views;

/// 设置项声明表:字段种类 + 元数据(扩字段只加一行)。
public sealed partial class SettingsPage
{
    private enum FieldKind { Switch, Slider, Combo, Number, Path, Action, Info }

    private sealed record FieldSpec(
        FieldKind Kind,
        string Key,
        string Title,
        string Desc,
        double Lo = 0,
        double Hi = 0,
        double Step = 0,
        string[]? Options = null,
        string? ActionKey = null,
        bool Advanced = false,
        string? Value = null);

    private static readonly (string Name, FieldSpec[] Fields)[] Groups =
    {
        ("启动与常规", new[]
        {
            new FieldSpec(FieldKind.Switch, "auto_start", "开机自启动", "系统登录时自动启动 KeyNote,持续后台记录按键。"),
            new FieldSpec(FieldKind.Switch, "silent_start", "静默启动", "完全静默启动,无窗口、无托盘通知(适合后台常驻)。"),
            new FieldSpec(FieldKind.Switch, "start_minimized", "启动时最小化", "开机后直接驻留托盘,不弹出主窗口。"),
            new FieldSpec(FieldKind.Switch, "close_to_tray", "关闭窗口到托盘", "点关闭按钮时最小化到托盘而不是退出程序。"),
            new FieldSpec(FieldKind.Switch, "hide_tray_icon", "隐藏托盘图标", "隐藏后重启仍保持隐藏;打开主窗口,回到本页关闭此项即可恢复显示。", Advanced: true),
            new FieldSpec(FieldKind.Switch, "listener_enabled", "启动时启动监听", "关闭后不再记录按键;重新打开会立即开始记录,无需重启。", Advanced: true),
            new FieldSpec(FieldKind.Switch, "mouse_listener_enabled", "记录鼠标点击", "后台记录鼠标左/右/中键与侧键(X1/X2)点击次数;关闭后立即停止。", Advanced: true),
            new FieldSpec(FieldKind.Number, "idle_pause_min", "闲置自动暂停(分钟)", "无键盘/鼠标活动超过该时长后自动暂停记录,0 = 不暂停。", 0, 240, 1, Advanced: true),
        }),
        ("界面", new[]
        {
            new FieldSpec(FieldKind.Switch, "remember_window_pos", "记住窗口位置", "记住主窗口位置,下次启动恢复。"),
            new FieldSpec(FieldKind.Slider, "window_alpha", "内容透明度", "WinUI3 非打包窗口不支持整窗透明,该滑块调节内容与卡片的不透明度。", 0.6, 1.0, 0.05, Advanced: true),
            new FieldSpec(FieldKind.Number, "heatmap_days", "热力图天数", "年度热力图统计的天数范围。", 30, 730, 1, Advanced: true),
            new FieldSpec(FieldKind.Number, "refresh_interval_sec", "自动刷新间隔(秒)", "当前页数据的自动刷新间隔。", 2, 120, 1, Advanced: true),
        }),
        ("数据", new[]
        {
            new FieldSpec(FieldKind.Action, "backup_now", "立即备份", "对当前数据库做一致性快照。", ActionKey: "backup"),
            new FieldSpec(FieldKind.Action, "export_csv", "导出 CSV", "导出最近 30 天原始按键记录到数据目录。", ActionKey: "csv"),
            new FieldSpec(FieldKind.Combo, "db_retention_days", "保留 raw 数据", "原始按键记录的保留时长,到期自动清理(聚合表永久保留)。",
                Options: ["永久", "7 天", "180 天", "365 天", "730 天"], Advanced: true),
            new FieldSpec(FieldKind.Path, "backup_dir", "备份目录", "备份 .db 文件的目标目录,空 = 使用数据目录下的 backups/。", Advanced: true),
            new FieldSpec(FieldKind.Action, "vacuum_now", "立即 VACUUM", "重建数据库回收空间。", ActionKey: "vacuum", Advanced: true),
        }),
        ("关于", new[]
        {
            new FieldSpec(FieldKind.Info, "app_version", "当前版本", "程序与安装包版本信息。", Value: $"v{UpdateService.CurrentVersionText}"),
            new FieldSpec(FieldKind.Action, "check_update", "检查更新", "查询 GitHub Releases 是否有新版本;发现新版后可下载安装。", ActionKey: "update"),
            new FieldSpec(FieldKind.Action, "quit_app", "退出 KeyNote", "关闭程序(隐藏托盘图标时唯一的退出入口)。", ActionKey: "quit"),
        }),
    };

    private static readonly int[] RetentionValues = [0, 7, 180, 365, 730];
}
