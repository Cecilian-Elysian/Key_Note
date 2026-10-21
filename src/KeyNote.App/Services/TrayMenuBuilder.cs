using System.Text;
using KeyNote.App.Helpers;
using KeyNote.Core.Storage;

namespace KeyNote.App.Services;

/// 托盘右键菜单构建(每次右键实时取数)与命令 ID 定义。
internal static class TrayMenuBuilder
{
    // 菜单命令 ID
    public const int IdShow = 1;
    public const int IdPause = 2;
    public const int IdSettings = 3;
    public const int IdUpdateCheck = 4;
    public const int IdBackup = 10;
    public const int IdVacuum = 11;
    public const int IdRetentionBase = 20;
    public const int IdQuit = 99;

    private static readonly (string Label, int Days)[] RetentionOptions =
    {
        ("永久", 0), ("7 天", 7), ("180 天", 180), ("365 天", 365), ("730 天", 730),
    };

    /// 保留策略选项数
    public static int RetentionCount => RetentionOptions.Length;

    /// 取第 i 个保留策略的天数
    public static int RetentionDays(int index) => RetentionOptions[index].Days;

    /// 构建菜单句柄(paused = 当前是否暂停记录)
    public static nint Build(bool paused)
    {
        var menu = TrayNative.CreatePopupMenu();
        if (menu == IntPtr.Zero) return IntPtr.Zero;

        var health = KeyNoteDb.Health();
        var sizeMb = health.SizeBytes / (1024.0 * 1024.0);
        var lastBackup = health.LastBackupTs > 0
            ? DateTimeOffset.FromUnixTimeSeconds(health.LastBackupTs).LocalDateTime.ToString("MM-dd HH:mm")
            : "从未";

        Append(menu, TrayNative.MfString | TrayNative.MfDefault, IdShow, "显示主窗口");
        Append(menu, TrayNative.MfString, IdPause, paused ? "▶ 继续" : "⏸ 暂停");
        Append(menu, TrayNative.MfString, IdSettings, "⚙ 设置...");
        Append(menu, TrayNative.MfString, IdUpdateCheck, "🔄 检查更新");
        Append(menu, TrayNative.MfSeparator, 0, null);

        var realtime = TrayNative.CreatePopupMenu();
        Append(realtime, TrayNative.MfString | TrayNative.MfGrayed, 0, $"总按键: {KeyNoteDb.CountTotal():N0}");
        Append(realtime, TrayNative.MfString | TrayNative.MfGrayed, 0, $"今日: {KeyNoteDb.CountToday():N0}");
        Append(realtime, TrayNative.MfString | TrayNative.MfGrayed, 0, $"连续打卡: {KeyNoteDb.StreakDays(365)} 天");
        Append(realtime, TrayNative.MfString | TrayNative.MfGrayed, 0, $"近 1h 平均: {Rate1h():F1}/分钟");
        Append(menu, TrayNative.MfPopup, (uint)realtime, "📈 实时统计");

        var recent = TrayNative.CreatePopupMenu();
        Append(recent, TrayNative.MfString | TrayNative.MfGrayed, 0, $"最近 5 分钟: {RecentBars()}");
        Append(recent, TrayNative.MfString | TrayNative.MfGrayed, 0, paused ? "当前状态: ⏸ 暂停" : "当前状态: ● 记录中");
        Append(menu, TrayNative.MfPopup, (uint)recent, "🕐 最近活动");

        var data = TrayNative.CreatePopupMenu();
        Append(data, TrayNative.MfString | TrayNative.MfGrayed, 0, $"总按键: {KeyNoteDb.CountTotal():N0}");
        Append(data, TrayNative.MfString | TrayNative.MfGrayed, 0, $"原始记录: {health.RawCount:N0}");
        Append(data, TrayNative.MfString | TrayNative.MfGrayed, 0, $"数据库: {sizeMb:F1} MB");
        Append(data, TrayNative.MfString | TrayNative.MfGrayed, 0, $"上次备份: {lastBackup}");
        Append(data, TrayNative.MfSeparator, 0, null);
        Append(data, TrayNative.MfString, IdBackup, "💾 立即备份");
        Append(data, TrayNative.MfString, IdVacuum, "🗜 立即 VACUUM");
        Append(data, TrayNative.MfSeparator, 0, null);

        var retention = TrayNative.CreatePopupMenu();
        var current = health.RetentionDays;
        for (var i = 0; i < RetentionOptions.Length; i++)
        {
            var (label, days) = RetentionOptions[i];
            var flags = TrayNative.MfString | (days == current ? TrayNative.MfChecked : 0);
            Append(retention, flags, (uint)(IdRetentionBase + i), label);
        }
        Append(data, TrayNative.MfPopup, (uint)retention, "保留 raw 数据");
        Append(menu, TrayNative.MfPopup, (uint)data, "📊 数据管理");

        Append(menu, TrayNative.MfSeparator, 0, null);
        Append(menu, TrayNative.MfString, IdQuit, "退出");
        return menu;
    }

    private static void Append(nint menu, uint flags, uint id, string? text)
    {
        TrayNative.AppendMenuW(menu, flags, id, text ?? string.Empty);
    }

    /// 近 1 小时平均按键/分钟:分母固定 60 分钟(按活跃分钟平均会在空闲时虚高)
    private static double Rate1h()
    {
        return KeyNoteDb.CpmRecent(60);
    }

    private static string RecentBars()
    {
        var rows = KeyNoteDb.RateSeries(1);
        var bucket = new long[5];
        var now = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        var cutoff = now - 5 * 60 * 1000;
        foreach (var (ts, c) in rows)
        {
            if (ts < cutoff) continue;
            var idx = (int)Math.Min(4, Math.Max(0, (ts - cutoff) / 60000));
            bucket[4 - idx] += c;
        }
        var peak = Math.Max(1, bucket.Max());
        const string glyphs = " ▁▂▃▄▅▆▇█";
        var sb = new StringBuilder();
        foreach (var v in bucket)
        {
            sb.Append(glyphs[Math.Min(8, (int)(v / (double)peak * 8))]);
        }
        return sb.ToString();
    }
}
