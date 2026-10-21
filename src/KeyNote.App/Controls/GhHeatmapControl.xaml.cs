using KeyNote.App.Theme;
using KeyNote.Core.Storage;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;

namespace KeyNote.App.Controls;

/// GitHub 风格年度贡献热力图(1:1 移植 Python gh_heatmap.py:多行拆分 + 分位数四色阶 + 悬停提示)。
public sealed partial class GhHeatmapControl : UserControl
{
    private const int Rows = 7;

    private const double CellMin = 6;
    private const double CellMax = 17;
    private const double CellSpacing = 2;
    private const double WeekdayLabelW = 30;
    private const double MonthLabelH = 16;
    private const double LegendH = 16;
    private const double MarginPx = 6;
    private const double MonthMinGap = 6;
    private const double InterRowGap = 18;

    private static readonly string[] CnWeekdays = { "一", "三", "五" };
    private static readonly string[] CnMonths =
    {
        "", "1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月",
    };

    private int _days = 365;
    private int _rowsCount = 2;
    private int _totalCols = 53;
    private long[] _dailyValues = [];
    private int[] _subCols = [53];
    private int[] _subStartCol = [0];
    private DateTime _startDt;
    private DateTime _gridStart;
    private long[] _percentiles = [1, 1, 1];
    private (int col, int row, int sub) _hovered = (-1, -1, -1);
    private Rectangle? _hoverRect;

    public GhHeatmapControl()
    {
        InitializeComponent();
        SizeChanged += (_, _) => Render();
        PointerMoved += OnPointerMoved;
        PointerExited += (_, _) => HideTip();
    }

    public int Days => _days;

    /// 注入数据(日粒度计数 + 起止日);控件不直接查库,与其余图表控件契约一致。
    public void SetData(long[] daily, DateTime start, DateTime end)
    {
        try
        {
            if (daily.Length == 0) return;
            if (SameData(daily, start)) return;

            _days = daily.Length;
            _dailyValues = daily;
            _startDt = start;
            _gridStart = start.AddDays(-DowIndex(start));
            _totalCols = (int)((end - _gridStart).TotalDays / 7) + 1;

            SplitIntoRows();

            var nonZero = daily.Where(v => v > 0).OrderBy(v => v).ToList();
            _percentiles = CalcPercentiles(nonZero);

            var active = daily.Count(v => v > 0);
            var maxVal = daily.Max();
            Summary = $"活跃 {active}/{_days} · 峰值 {maxVal:N0}";

            Render();
        }
        catch (Exception ex)
        {
            Core.Utils.CrashLog.Write("ghheatmap.setdata", ex);
        }
    }

    /// 数据未变化则跳过重绘
    private bool SameData(long[] daily, DateTime start)
    {
        if (_dailyValues.Length != daily.Length) return false;
        if (_startDt != start) return false;
        for (var i = 0; i < daily.Length; i++)
        {
            if (_dailyValues[i] != daily[i]) return false;
        }
        return true;
    }

    /// 摘要文本(活跃天数 / 峰值),供外部标题栏显示
    public string Summary { get; private set; } = "";

    private static int DowIndex(DateTime d) => ((int)d.DayOfWeek + 6) % 7;

    private static long[] CalcPercentiles(List<long> sorted)
    {
        var n = sorted.Count;
        if (n == 0) return [1, 1, 1];
        if (n == 1) return [sorted[0], sorted[0], sorted[0]];
        if (n == 2) return [sorted[0], sorted[0], sorted[1]];
        if (n == 3) return [sorted[0], sorted[1], sorted[2]];
        return [sorted[n / 4], sorted[n / 2], sorted[n * 3 / 4]];
    }

    private void SplitIntoRows()
    {
        var r = _rowsCount;
        var baseCols = _totalCols / r;
        var rem = _totalCols - baseCols * r;
        var cols = new List<int>();
        var starts = new List<int>();
        var cursor = 0;
        for (var i = 0; i < r; i++)
        {
            var n = baseCols + (i < rem ? 1 : 0);
            cols.Add(n);
            starts.Add(cursor);
            cursor += n;
        }
        _subCols = cols.ToArray();
        _subStartCol = starts.ToArray();
    }

    private Windows.UI.Color BucketColor(long value)
    {
        if (value <= 0) return UiColors.HeatmapEmpty;
        var (p25, p50, p75) = (_percentiles[0], _percentiles[1], _percentiles[2]);
        if (value <= p25) return UiColors.HeatmapL1;
        if (value <= p50) return UiColors.HeatmapL2;
        if (value <= p75) return UiColors.HeatmapL3;
        return UiColors.HeatmapL4;
    }

    // ──── 布局 ────
    private (double ox, double cell, double spacing, double gridW, double gridH, double[] origins, double totalUsed)? ComputeLayout(double w, double h)
    {
        if (w < 100 || h < 60) return null;
        var availW = w - WeekdayLabelW - 2 * MarginPx;
        var rows = _rowsCount;
        var inter = (rows - 1) * InterRowGap;
        var totalNeeded = rows * MonthLabelH + rows * Rows * CellMin +
                          (rows * (Rows - 1)) * CellSpacing + inter + LegendH + 2 * MarginPx;
        if (availW < 50 || h < totalNeeded / 2) return null;

        var maxCols = _subCols.Length > 0 ? _subCols.Max() : _totalCols;
        var spacing = Math.Max(1, CellSpacing);
        var cell = (availW - (maxCols - 1) * spacing) / maxCols;
        cell = Math.Max(CellMin, Math.Min(CellMax, cell));
        var gridW = maxCols * cell + (maxCols - 1) * spacing;
        if (gridW > availW)
        {
            spacing = Math.Max(1, (availW - maxCols * cell) / (maxCols - 1));
            gridW = maxCols * cell + (maxCols - 1) * spacing;
        }
        var gridH = Rows * cell + (Rows - 1) * spacing;
        var ox = MarginPx + WeekdayLabelW + Math.Max(0, (availW - gridW) / 2);

        var origins = new double[rows];
        var curY = MarginPx;
        for (var r = 0; r < rows; r++)
        {
            origins[r] = curY + MonthLabelH;
            curY += MonthLabelH + gridH;
            if (r < rows - 1) curY += InterRowGap;
        }
        var totalUsed = curY + LegendH + MarginPx;
        return (ox, cell, spacing, gridW, gridH, origins, totalUsed);
    }

    // ──── 渲染 ────
    private void Render()
    {
        if (_dailyValues.Length == 0) return;
        var cv = Surface;
        cv.Children.Clear();
        _hoverRect = null;

        if (_dailyValues.All(v => v <= 0))
        {
            EmptyState.Show("暂无记录", "开始记录后,这里会显示每日按键分布");
            return;
        }
        EmptyState.Hide();

        var w = cv.ActualWidth > 0 ? cv.ActualWidth : 0;
        var h = cv.ActualHeight > 0 ? cv.ActualHeight : 0;
        var layout = ComputeLayout(w, h);
        if (layout is null) return;
        var (ox, cell, spacing, gridW, _, origins, totalUsed) = layout.Value;

        for (var sub = 0; sub < _rowsCount; sub++)
        {
            var subOx = ox;
            var subOy = origins[sub];
            var cols = _subCols[sub];
            var startCol = _subStartCol[sub];

            for (var localCol = 0; localCol < cols; localCol++)
            {
                var globalCol = startCol + localCol;
                for (var row = 0; row < Rows; row++)
                {
                    var cellDate = _gridStart.AddDays(globalCol * 7 + row);
                    var delta = (cellDate - _startDt).Days;
                    var value = delta >= 0 && delta < _days ? _dailyValues[delta] : 0;
                    var x1 = subOx + localCol * (cell + spacing);
                    var y1 = subOy + row * (cell + spacing);
                    var rect = new Rectangle
                    {
                        Width = cell,
                        Height = cell,
                        Fill = UiColors.Brush(BucketColor(value)),
                        RadiusX = 2,
                        RadiusY = 2,
                    };
                    Canvas.SetLeft(rect, x1);
                    Canvas.SetTop(rect, y1);
                    cv.Children.Add(rect);
                }
            }

            foreach (var (idx, row) in new[] { (0, 0), (1, 2), (2, 4) })
            {
                var ty = subOy + row * (cell + spacing) + cell / 2;
                AddText(cv, CnWeekdays[idx], MarginPx, ty, UiColors.FgMuted, 10, middleLeft: true);
            }

            DrawMonthLabels(cv, subOx, subOy, cell, spacing, startCol, cols);
        }

        var legendY = totalUsed - LegendH;
        DrawLegend(cv, ox + gridW, legendY, cell);

        _hoverRect = new Rectangle
        {
            Stroke = UiColors.Brush(UiColors.Accent),
            StrokeThickness = 2,
            Visibility = Visibility.Collapsed,
            RadiusX = 2,
            RadiusY = 2,
        };
        cv.Children.Add(_hoverRect);
        if (_hovered.col >= 0) UpdateHoverRect();

        // 高度由页面决定(DesiredHeight 仅供页面参考),控件不改自身 Height
        DesiredHeight = totalUsed;
    }

    /// 布局计算出的建议高度(由页面决定实际高度)
    public double DesiredHeight { get; private set; }

    private void DrawMonthLabels(Canvas cv, double ox, double oy, double cell, double spacing, int startCol, int colsInRow)
    {
        var lastMonth = -1;
        var lastLabelMaxX = -1e9;
        var textY = oy - 4;
        for (var localCol = 0; localCol < colsInRow; localCol++)
        {
            var globalCol = startCol + localCol;
            var weekStart = _gridStart.AddDays(globalCol * 7);
            if (weekStart.Month == lastMonth) continue;
            var label = CnMonths[weekStart.Month];
            var labelX = ox + localCol * (cell + spacing);
            if (labelX - lastLabelMaxX < MonthMinGap) continue;
            var tb = AddText(cv, label, labelX, textY, UiColors.FgMuted, 10, bottomLeft: true);
            tb.Measure(new Windows.Foundation.Size(200, 24));
            lastLabelMaxX = labelX + tb.DesiredSize.Width;
            lastMonth = weekStart.Month;
        }
    }

    private void DrawLegend(Canvas cv, double rightX, double y, double cell)
    {
        var boxSize = Math.Max(8, Math.Min((int)cell, 10));
        var boxSpacing = 3;
        var textW = 11;
        var legendW = textW + 8 + 5 * boxSize + 4 * boxSpacing + 8 + textW;
        var x = rightX - legendW;

        AddText(cv, "少", x, y + boxSize / 2, UiColors.FgMuted, 10, middleLeft: true);
        x += textW + 8;
        var colors = new[]
        {
            UiColors.HeatmapEmpty, UiColors.HeatmapL1, UiColors.HeatmapL2,
            UiColors.HeatmapL3, UiColors.HeatmapL4,
        };
        foreach (var col in colors)
        {
            var rect = new Rectangle
            {
                Width = boxSize,
                Height = boxSize,
                Fill = UiColors.Brush(col),
                RadiusX = 2,
                RadiusY = 2,
            };
            Canvas.SetLeft(rect, x);
            Canvas.SetTop(rect, y);
            cv.Children.Add(rect);
            x += boxSize + boxSpacing;
        }
        AddText(cv, "多", x + 5, y + boxSize / 2, UiColors.FgMuted, 10, middleLeft: true);
    }

    private static TextBlock AddText(Canvas cv, string text, double x, double y,
        Windows.UI.Color color, double size, bool middleLeft = false, bool bottomLeft = false)
    {
        var tb = new TextBlock
        {
            Text = text,
            FontSize = size,
            Foreground = UiColors.Brush(color),
            TextWrapping = TextWrapping.NoWrap,
        };
        tb.Measure(new Windows.Foundation.Size(400, 40));
        var h = tb.DesiredSize.Height;
        var top = middleLeft ? y - h / 2 : bottomLeft ? y - h : y;
        Canvas.SetLeft(tb, x);
        Canvas.SetTop(tb, top);
        cv.Children.Add(tb);
        return tb;
    }

    // ──── 悬停 ────
    private void OnPointerMoved(object sender, PointerRoutedEventArgs e)
    {
        if (_dailyValues.Length == 0) return;
        var cv = Surface;
        var w = cv.ActualWidth;
        var h = cv.ActualHeight;
        var layout = ComputeLayout(w, h);
        if (layout is null) return;
        var (ox, cell, spacing, _, gridH, origins, _) = layout.Value;

        var p = e.GetCurrentPoint(cv).Position;
        for (var sub = 0; sub < _rowsCount; sub++)
        {
            var subOy = origins[sub];
            var localCol = (int)((p.X - ox) / (cell + spacing));
            var row = (int)((p.Y - subOy) / (cell + spacing));
            if (localCol < 0 || localCol >= _subCols[sub] || row < 0 || row >= Rows) continue;
            var x1 = ox + localCol * (cell + spacing);
            var y1 = subOy + row * (cell + spacing);
            if (p.X > x1 + cell || p.Y > y1 + cell) continue;
            _hovered = (_subStartCol[sub] + localCol, row, sub);
            UpdateHoverRect();

            var cellDate = _gridStart.AddDays(_hovered.col * 7 + row);
            var delta = (cellDate - _startDt).Days;
            var value = delta >= 0 && delta < _days ? _dailyValues[delta] : 0;
            Tip.Text = $"{cellDate:yyyy-MM-dd} · {value:N0} 次";
            Tip.ShowAt(cv, p.X, p.Y);
            return;
        }
        _hovered = (-1, -1, -1);
        if (_hoverRect is not null) _hoverRect.Visibility = Visibility.Collapsed;
        HideTip();
    }

    private void UpdateHoverRect()
    {
        if (_hoverRect is null) return;
        var layout = ComputeLayout(Surface.ActualWidth, Surface.ActualHeight);
        if (layout is null) return;
        var (ox, cell, spacing, _, _, origins, _) = layout.Value;
        var sub = _hovered.sub;
        var localCol = _hovered.col - _subStartCol[sub];
        var x1 = ox + localCol * (cell + spacing);
        var y1 = origins[sub] + _hovered.row * (cell + spacing);
        Canvas.SetLeft(_hoverRect, x1 - 1);
        Canvas.SetTop(_hoverRect, y1 - 1);
        _hoverRect.Width = cell + 2;
        _hoverRect.Height = cell + 2;
        _hoverRect.Visibility = Visibility.Visible;
    }

    private void HideTip()
    {
        Tip.Hide();
        if (_hoverRect is not null) _hoverRect.Visibility = Visibility.Collapsed;
        _hovered = (-1, -1, -1);
    }
}
