using KeyNote.App.Controls;
using KeyNote.App.Helpers;
using KeyNote.App.Theme;
using KeyNote.Core.Storage;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace KeyNote.App.Views;

/// 后台页(Page 2):3 张 KPI 副卡 + 键型分布胶囊行 + 7×24 + QWERTY 键盘热力图。
public sealed partial class KeyboardPage : Page, IRefreshable
{
    private static readonly (string Type, string Label, Windows.UI.Color Color)[] TypeMeta =
    {
        ("letter", "字母", Windows.UI.Color.FromArgb(0xFF, 0x0A, 0x84, 0xFF)),
        ("digit", "数字", Windows.UI.Color.FromArgb(0xFF, 0x34, 0xC7, 0x59)),
        ("symbol", "符号", Windows.UI.Color.FromArgb(0xFF, 0xFA, 0xAA, 0x17)),
        ("modifier", "修饰键", Windows.UI.Color.FromArgb(0xFF, 0xBF, 0x5A, 0xF2)),
        ("function", "功能键", Windows.UI.Color.FromArgb(0xFF, 0x8E, 0x8E, 0x93)),
    };

    private string? _typeFp;
    private string? _kbFp;

    public KeyboardPage()
    {
        InitializeComponent();
        Header.RefreshRequested += (_, _) => RefreshData();
        Loaded += (_, _) => RefreshData();
    }

    public void RefreshData()
    {
        try
        {
            var total = KeyNoteDb.CountTotal();
            var mouse = KeyNoteDb.MouseTotal();
            var active = KeyNoteDb.DailyActiveDays(30);
            KpiTotal.Value = total.ToString("N0");
            KpiMouse.Value = mouse.ToString("N0");
            KpiActive.Value = active.ToString("N0");
            KpiTotal.Footnote = $"今日 +{KeyNoteDb.CountToday():N0}";
            KpiMouse.Footnote = MouseFoot();
            KpiActive.Footnote = "近 30 天";

            UpdateTypePills();
            UpdateHourly();
            UpdateKeyboard();
        }
        catch (Exception ex)
        {
            Core.Utils.CrashLog.Write("keyboard.refresh", ex);
        }
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

    private void UpdateHourly()
    {
        var grid = KeyNoteDb.HeatmapData(7);
        HourlyGrid.SetGrid(grid);
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
        var rows = KeyNoteDb.TopKeys(5000);
        var fp = string.Join(",", rows.Select(r => $"{r.Key}:{r.Count}"));
        if (fp == _kbFp) return;
        _kbFp = fp;

        var counts = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        foreach (var (k, c) in rows) counts[k.ToLowerInvariant()] = (int)c;
        KeyboardHeatmap.SetCounts(counts);

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
