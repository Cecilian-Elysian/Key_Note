using KeyNote.App.Theme;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;

namespace KeyNote.App.Controls;

/// 7×24 小时活跃度热力图(1:1 移植 Python keyboard.py 的 _draw_hourly)。
public sealed partial class HourlyGridControl : UserControl
{
    /// 布局计算出的建议高度(由页面决定实际高度)
    public double DesiredHeight { get; private set; }
    private static readonly string[] CnWeekdays = { "一", "二", "三", "四", "五", "六", "日" };

    private int[,] _grid = new int[7, 24];
    private double _ox, _oy, _cell, _gap;
    private int _peak;

    public HourlyGridControl()
    {
        InitializeComponent();
        SizeChanged += (_, _) => Render();
        PointerMoved += OnPointerMoved;
        PointerExited += (_, _) => Tip.Hide();
    }

    public void SetGrid(int[,] grid)
    {
        _grid = grid;
        _peak = 0;
        for (var d = 0; d < 7; d++)
        {
            for (var h = 0; h < 24; h++)
            {
                if (grid[d, h] > _peak) _peak = grid[d, h];
            }
        }
        Render();
    }

    private Windows.UI.Color Bucket(int val)
    {
        if (val <= 0 || _peak <= 0) return UiColors.HeatmapEmpty;
        var r = val / (double)_peak;
        if (r <= 0.25) return UiColors.HeatmapL1;
        if (r <= 0.50) return UiColors.HeatmapL2;
        if (r <= 0.75) return UiColors.HeatmapL3;
        return UiColors.HeatmapL4;
    }

    private void Render()
    {
        var cv = Surface;
        cv.Children.Clear();
        var w = cv.ActualWidth;
        var h = cv.ActualHeight;
        if (w < 60 || h < 40) return;

        if (_peak <= 0)
        {
            EmptyState.Show("暂无记录", "开始记录后,这里会显示 7×24 活跃度");
            return;
        }
        EmptyState.Hide();

        const double marginX = 24;
        const double gap = 1;
        const double labelH = 12;
        const double legendH = 16;
        const double padY = 8;

        var usableW = Math.Max(40, w - marginX - 4);
        var cell = Math.Max(10, Math.Min(22, (usableW - 23 * gap) / 24));
        var gridW = 24 * cell + 23 * gap;
        var gridH = 7 * cell + 6 * gap;
        var contentH = gridH + 2 + labelH + legendH;
        var needed = (int)(contentH + padY * 2);
        // 高度由页面决定(DesiredHeight 仅供页面参考),控件不改自身 Height
        DesiredHeight = needed;
        if (Math.Abs(h - needed) > 2) h = needed;

        _ox = marginX + Math.Max(0, (usableW - gridW) / 2);
        _oy = Math.Max(padY, (h - contentH) / 2);
        _cell = cell;
        _gap = gap;

        for (var dow = 0; dow < 7; dow++)
        {
            var ty = _oy + dow * (cell + gap) + cell / 2;
            var lbl = new TextBlock
            {
                Text = CnWeekdays[dow],
                FontSize = 9,
                Foreground = UiColors.Brush(UiColors.FgMuted),
            };
            Canvas.SetLeft(lbl, 4);
            Canvas.SetTop(lbl, ty - 7);
            cv.Children.Add(lbl);

            for (var hour = 0; hour < 24; hour++)
            {
                var x1 = _ox + hour * (cell + gap);
                var y1 = _oy + dow * (cell + gap);
                var rect = new Rectangle
                {
                    Width = cell,
                    Height = cell,
                    Fill = UiColors.Brush(Bucket(_grid[dow, hour])),
                    RadiusX = 2,
                    RadiusY = 2,
                };
                Canvas.SetLeft(rect, x1);
                Canvas.SetTop(rect, y1);
                cv.Children.Add(rect);
            }
        }

        foreach (var hr in new[] { 0, 6, 12, 18, 23 })
        {
            var tx = _ox + hr * (cell + gap) + cell / 2;
            var lbl = new TextBlock
            {
                Text = hr.ToString(),
                FontSize = 8,
                Foreground = UiColors.Brush(UiColors.FgMuted),
                HorizontalAlignment = HorizontalAlignment.Center,
            };
            Canvas.SetLeft(lbl, tx - 6);
            Canvas.SetTop(lbl, _oy + gridH + 2);
            cv.Children.Add(lbl);
        }

        // 色阶图例(右对齐)
        var legendY = _oy + gridH + 2 + labelH;
        var box = Math.Max(6, Math.Min(10, (int)cell));
        var bgap = 3;
        var textW = 11;
        var legendW = textW + 8 + 5 * box + 4 * bgap + 8 + textW;
        var lx = _ox + gridW - legendW;
        var less = new TextBlock { Text = "少", FontSize = 9, Foreground = UiColors.Brush(UiColors.FgMuted) };
        Canvas.SetLeft(less, lx);
        Canvas.SetTop(less, legendY + box / 2 - 7);
        cv.Children.Add(less);
        lx += textW + 8;
        var colors = new[]
        {
            UiColors.HeatmapEmpty, UiColors.HeatmapL1, UiColors.HeatmapL2,
            UiColors.HeatmapL3, UiColors.HeatmapL4,
        };
        foreach (var c in colors)
        {
            var rect = new Rectangle { Width = box, Height = box, Fill = UiColors.Brush(c) };
            Canvas.SetLeft(rect, lx);
            Canvas.SetTop(rect, legendY);
            cv.Children.Add(rect);
            lx += box + bgap;
        }
        var more = new TextBlock { Text = "多", FontSize = 9, Foreground = UiColors.Brush(UiColors.FgMuted) };
        Canvas.SetLeft(more, lx + 5);
        Canvas.SetTop(more, legendY + box / 2 - 7);
        cv.Children.Add(more);
    }

    private void OnPointerMoved(object sender, PointerRoutedEventArgs e)
    {
        var cv = Surface;
        var p = e.GetCurrentPoint(cv).Position;
        var col = (int)((p.X - _ox) / (_cell + _gap));
        var row = (int)((p.Y - _oy) / (_cell + _gap));
        if (col < 0 || col > 23 || row < 0 || row > 6)
        {
            Tip.Hide();
            return;
        }
        var cellX = _ox + col * (_cell + _gap);
        var cellY = _oy + row * (_cell + _gap);
        if (p.X > cellX + _cell || p.Y > cellY + _cell)
        {
            Tip.Hide();
            return;
        }
        Tip.Text = $"周{CnWeekdays[row]} {col}:00 · {_grid[row, col]:N0} 次键";
        Tip.ShowAt(cv, p.X, p.Y);
    }
}
