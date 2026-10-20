using KeyNote.App.Controls;
using KeyNote.App.Helpers;
using KeyNote.App.Theme;
using KeyNote.Core.Storage;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace KeyNote.App.Views;

/// 统计页(Page 1):设备行式主卡 + 电量图趋势 + 年度热力图。
public sealed partial class StatsPage : Page, IRefreshable
{
    private const int RangeIdxToday = 0;
    private const int RangeIdxWeek = 1;
    private const int RangeIdxMonth = 2;

    private int _range = RangeIdxMonth;
    private string? _fp;

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
            var key = _range switch
            {
                RangeIdxToday => "today",
                RangeIdxWeek => "week",
                _ => "month",
            };

            long value;
            List<ChartPoint> points;
            string title;
            switch (_range)
            {
                case RangeIdxToday:
                    value = KeyNoteDb.CountToday();
                    points = KeyNoteDb.HourlyToday()
                        .Select(r => new ChartPoint(r.Count, $"{DateTimeOffset.FromUnixTimeMilliseconds(r.HourTs).LocalDateTime:HH:mm}"))
                        .ToList();
                    title = "按键趋势 · 逐时";
                    break;
                case RangeIdxWeek:
                {
                    var rows = KeyNoteDb.DailyCounts(7);
                    value = rows.Sum(r => r.Count);
                    points = rows.Select(r => new ChartPoint(r.Count,
                        DateTimeOffset.FromUnixTimeMilliseconds(r.DayTs).LocalDateTime.ToString("MM-dd"))).ToList();
                    title = "按键趋势";
                    break;
                }
                default:
                {
                    var rows = KeyNoteDb.DailyCounts(30);
                    value = rows.Sum(r => r.Count);
                    points = rows.Select(r => new ChartPoint(r.Count,
                        DateTimeOffset.FromUnixTimeMilliseconds(r.DayTs).LocalDateTime.ToString("MM-dd"))).ToList();
                    title = "按键趋势";
                    break;
                }
            }

            var fp = $"{key}|{value}|{points.Count}";
            if (fp != _fp)
            {
                _fp = fp;
                MainValue.Text = value > 0 ? value.ToString("N0") : "—";
                TrendTitle.Text = title;
                TrendChart.SetData(points);
                UpdateMainFooter();
            }

            var streak = KeyNoteDb.StreakDays(365);
            Header.Subtitle = streak > 0 ? $"已连续记录 {streak} 天" : "暂无历史记录";

            Heatmap.Refresh();
            YearTitle.Text = $"过去 {Heatmap.Days} 天 · 每日贡献";
            YearSummary.Text = Heatmap.Summary;
        }
        catch (Exception ex)
        {
            Core.Utils.CrashLog.Write("stats.refresh", ex);
        }
    }

    /// 主卡脚注:今日模式 → 进度条(今日 vs 近 30 日均)+ 较昨日胶囊;其他模式 → 日均
    private void UpdateMainFooter()
    {
        try
        {
            if (_range == RangeIdxToday)
            {
                var avg30 = Math.Max(KeyNoteDb.DailyAverage(30), 1);
                var today = KeyNoteDb.CountToday();
                var ratio = Math.Min(today / (double)avg30, 1.0);
                MainProgress.Visibility = Visibility.Visible;
                MainProgress.Value = ratio;
                MainProgress.Foreground = ratio >= 1.0 ? UiColors.Brush(UiColors.Success) : UiColors.Brush(UiColors.Accent);

                var (text, color) = YesterdayCompare();
                MainPillHost.Content = text.Length > 0 ? PillFactory.Create(text, color) : null;
                MainSub.Text = $"日均 {KeyNoteDb.DailyAverage(30):N0} 次";
            }
            else
            {
                MainProgress.Visibility = Visibility.Collapsed;
                MainPillHost.Content = null;
                var days = _range == RangeIdxWeek ? 7 : 30;
                MainSub.Text = $"日均 {KeyNoteDb.DailyAverage(days):N0} 次";
            }
        }
        catch (Exception ex)
        {
            Core.Utils.CrashLog.Write("stats.footer", ex);
        }
    }

    /// 今日 vs 昨日对比 → (胶囊文本, 语义色)
    private static (string, Windows.UI.Color) YesterdayCompare()
    {
        var today = DateTime.Today;
        var byDay = new Dictionary<DateTime, long>();
        foreach (var (ts, c) in KeyNoteDb.DailyCounts(2))
        {
            byDay[DateTimeOffset.FromUnixTimeMilliseconds(ts).LocalDateTime.Date] = c;
        }
        var y = byDay.GetValueOrDefault(today.AddDays(-1));
        var t = byDay.GetValueOrDefault(today);
        if (y <= 0) return ("", UiColors.FgMuted);
        var pct = (t - y) / (double)y * 100;
        if (pct > 0.5) return ($"较昨日 +{pct:F0}%", UiColors.Success);
        if (pct < -0.5) return ($"较昨日 −{Math.Abs(pct):F0}%", UiColors.Danger);
        return ("与昨日持平", UiColors.FgMuted);
    }
}
