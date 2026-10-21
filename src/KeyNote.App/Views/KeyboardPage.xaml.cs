using KeyNote.App.Controls;
using KeyNote.Core.Storage;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace KeyNote.App.Views;

/// 后台页(Page 2):7×24 小时活跃度 + QWERTY 键盘热力图。
public sealed partial class KeyboardPage : Page, IRefreshable
{
    private string? _kbFp;

    public KeyboardPage()
    {
        InitializeComponent();
        PageRefresh.Wire(this, Header, RefreshData);
    }

    public void RefreshData()
    {
        UpdateHourly();
        UpdateKeyboard();
    }

    private void UpdateHourly()
    {
        var grid = KeyNoteDb.HeatmapData(7);
        HourlyGrid.SetGrid(grid);
        // 高度由页面决定(控件只给建议值)
        HourlyGrid.Height = HourlyGrid.DesiredHeight;
        var total = 0;
        var active = 0;
        var peak = 0;
        for (var d = 0; d < 7; d++)
        {
            for (var h = 0; h < 24; h++)
            {
                var v = grid[d, h];
                total += v;
                if (v > 0) active++;
                if (v > peak) peak = v;
            }
        }
        HourlySummary.Text = $"活跃 {active}/168 桶 · 峰值 {peak:N0}";
    }

    private void UpdateKeyboard()
    {
        var rows = KeyNoteDb.TopKeysMergedCase(5000);
        var fp = string.Join(",", rows.Select(r => $"{r.Key}:{r.Count}"));
        if (fp == _kbFp) return;
        _kbFp = fp;

        var counts = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        foreach (var (k, c) in rows)
        {
            // 合并大小写:同一键的大小写要累加,不能覆盖(否则 "a" 与 "A" 只会留下一个)
            var key = k.ToLowerInvariant();
            counts[key] = counts.GetValueOrDefault(key) + (int)Math.Min(c, int.MaxValue);
        }
        KeyboardHeatmap.SetCounts(counts);
        // 高度由页面决定(控件只给建议值)
        KeyboardHeatmap.Height = KeyboardHeatmap.DesiredHeight;

        if (counts.Count > 0)
        {
            var top = counts.OrderByDescending(kv => kv.Value).First();
            KbLegend.Text = $"最高 {top.Key.ToUpperInvariant()} × {top.Value:N0}";
        }
        else
        {
            KbLegend.Text = "";
        }
    }
}
