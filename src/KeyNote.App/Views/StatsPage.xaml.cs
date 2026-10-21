using KeyNote.App.Controls;
using KeyNote.App.Helpers;
using KeyNote.App.Theme;
using KeyNote.Core.Storage;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace KeyNote.App.Views;

/// 统计页(Page 1):3 张 KPI 卡 + 键型分布胶囊 + 按键趋势。
public sealed partial class StatsPage : Page, IRefreshable
{
    private const int RangeIdxToday = 0;
    private const int RangeIdxWeek = 1;
    private const int RangeIdxMonth = 2;

    private static readonly (string Type, string Label, Windows.UI.Color Color)[] TypeMeta =
    {
        ("letter", "字母", Windows.UI.Color.FromArgb(0xFF, 0x0A, 0x84, 0xFF)),
        ("digit", "数字", Windows.UI.Color.FromArgb(0xFF, 0x34, 0xC7, 0x59)),
        ("symbol", "符号", Windows.UI.Color.FromArgb(0xFF, 0xFA, 0xAA, 0x17)),
        ("modifier", "修饰键", Windows.UI.Color.FromArgb(0xFF, 0xBF, 0x5A, 0xF2)),
        ("function", "功能键", Windows.UI.Color.FromArgb(0xFF, 0x8E, 0x8E, 0x93)),
    };

    private int _range = RangeIdxMonth;
    private string? _fp;
    private string? _typeFp;

    public StatsPage()
    {
        InitializeComponent();
        Header.RefreshRequested += (_, _) => RefreshData();
        Loaded += (_, _) => RefreshData();
    }

    private void RangeBar_SelectionChanged(SelectorBar sender, SelectorBarSelectionChangedEventArgs args)
    {
        var selected = sender.SelectedItem;
        var idx = selected == RangeToday ? RangeIdxToday
            : selected == RangeWeek ? RangeIdxWeek
            : RangeIdxMonth;
        if (idx == _range) return;
        _range = idx;
        RefreshData();
    }

    public void RefreshData()
    {
        try
        {
            var days = RangeDays(_range);
            var rangeLabel = RangeLabel(_range);

            KpiTotal.Value = KeyNoteDb.CountKeysSince(days).ToString("N0");
            KpiMouse.Value = KeyNoteDb.MouseSince(days).ToString("N0");
            KpiActive.Value = KeyNoteDb.DailyActiveDays(days).ToString("N0");
            KpiTotal.Footnote = $"全时累计 {KeyNoteDb.CountTotal():N0}";
            KpiMouse.Footnote = MouseFoot();
            KpiActive.Footnote = rangeLabel;

            UpdateTypePills();
            UpdateTrend();

            var streak = KeyNoteDb.StreakDays(365);
            Header.Subtitle = streak > 0 ? $"已连续记录 {streak} 天" : "暂无历史记录";
        }
        catch (Exception ex)
        {
            Core.Utils.CrashLog.Write("stats.refresh", ex);
        }
    }

    /// 时间范围 → 天数
    private static int RangeDays(int range) => range switch
    {
        RangeIdxToday => 1,
        RangeIdxWeek => 7,
        _ => 30,
    };

    private static string RangeLabel(int range) => range switch
    {
        RangeIdxToday => "今日",
        RangeIdxWeek => "近 7 天",
        _ => "近 30 天",
    };

    private void UpdateTrend()
    {
        var key = _range switch
        {
            RangeIdxToday => "today",
            RangeIdxWeek => "week",
            _ => "month",
        };

        List<ChartPoint> points;
        string title;
        switch (_range)
        {
            case RangeIdxToday:
                points = KeyNoteDb.HourlyToday()
                    .Select(r => new ChartPoint(r.Count, $"{DateTimeOffset.FromUnixTimeMilliseconds(r.HourTs).LocalDateTime:HH:mm}"))
                    .ToList();
                title = "按键趋势 · 逐时";
                break;
            case RangeIdxWeek:
            {
                var rows = KeyNoteDb.DailyCounts(7);
                points = rows.Select(r => new ChartPoint(r.Count,
                    DateTimeOffset.FromUnixTimeMilliseconds(r.DayTs).LocalDateTime.ToString("MM-dd"))).ToList();
                title = "按键趋势";
                break;
            }
            default:
            {
                var rows = KeyNoteDb.DailyCounts(30);
                points = rows.Select(r => new ChartPoint(r.Count,
                    DateTimeOffset.FromUnixTimeMilliseconds(r.DayTs).LocalDateTime.ToString("MM-dd"))).ToList();
                title = "按键趋势";
                break;
            }
        }

        var fp = $"{key}|{points.Count}|{points.LastOrDefault()?.Value ?? 0}";
        if (fp == _fp) return;
        _fp = fp;
        TrendTitle.Text = title;
        TrendChart.SetData(points);
    }

    private static string MouseFoot()
    {
        var rows = KeyNoteDb.MouseByButton();
        var total = KeyNoteDb.MouseTotal();
        if (rows.Count == 0 || total <= 0) return "暂无数据";
        var name = rows[0].Button switch
        {
            "left" => "左键",
            "right" => "右键",
            "middle" => "中键",
            "x1" => "侧键 1",
            "x2" => "侧键 2",
            _ => rows[0].Button,
        };
        return $"{name} {Math.Round(rows[0].Count / (double)total * 100)}%";
    }

    private void UpdateTypePills()
    {
        var rows = KeyNoteDb.KeyTypeDistribution().ToDictionary(r => r.Type, r => r.Count);
        var fp = string.Join(",", rows.OrderBy(kv => kv.Key).Select(kv => $"{kv.Key}:{kv.Value}"));
        if (fp == _typeFp) return;
        _typeFp = fp;

        var total = rows.Values.Sum();
        TypePillRow.Children.Clear();
        if (total <= 0)
        {
            TypePillRow.Visibility = Visibility.Collapsed;
            return;
        }
        TypePillRow.Visibility = Visibility.Visible;
        foreach (var (type, label, color) in TypeMeta)
        {
            var count = rows.GetValueOrDefault(type);
            var pct = Math.Round(count / (double)total * 100);
            TypePillRow.Children.Add(PillFactory.Create($"{label} {pct}%", color));
        }
    }
}
