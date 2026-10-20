using KeyNote.App.Theme;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;

namespace KeyNote.App.Controls;

/// 趋势图数据点
public sealed record ChartPoint(double Value, string Label);

/// 趋势图(vigil-watt 电量图签名):2px 圆角线 + 同色 15% 面积 + ≤40 点圆点
/// + 线端值标签 + 悬停十字虚线 / 白描边圆点 / 圆角气泡。
public sealed partial class TrendChartControl : UserControl
{
    private const int MaxPoints = 40;
    private const double LineThickness = 2;
    private const double DotRadius = 2.5;
    private const double PadLeft = 34;
    private const double PadRight = 44;
    private const double PadTop = 10;
    private const double PadBottom = 22;

    private IReadOnlyList<ChartPoint> _points = [];
    private Polyline? _line;
    private Polyline? _area;
    private Line? _hoverLine;
    private Ellipse? _hoverDot;
    private Border? _hoverTip;
    private TextBlock? _endLabel;

    public TrendChartControl()
    {
        InitializeComponent();
        SizeChanged += (_, _) => Render();
        PointerMoved += OnPointerMoved;
        PointerExited += (_, _) => HideHover();
    }

    public void SetData(IReadOnlyList<ChartPoint> points)
    {
        _points = points.Count > MaxPoints ? Downsample(points, MaxPoints) : points;
        Render();
    }

    /// 超过上限时按等距抽稀(保留首尾)
    private static IReadOnlyList<ChartPoint> Downsample(IReadOnlyList<ChartPoint> src, int max)
    {
        if (src.Count <= max) return src;
        var result = new List<ChartPoint>(max);
        var step = (double)src.Count / max;
        for (var i = 0; i < max; i++)
        {
            var idx = (int)Math.Round(i * step);
            if (idx >= src.Count) idx = src.Count - 1;
            result.Add(src[idx]);
        }
        return result;
    }

    // ──── 渲染 ────
    private void Render()
    {
        var cv = Surface;
        cv.Children.Clear();
        _line = null;
        _area = null;
        _hoverLine = null;
        _hoverDot = null;
        _hoverTip = null;
        _endLabel = null;

        var w = cv.ActualWidth;
        var h = cv.ActualHeight;
        if (w < 40 || h < 40) return;

        if (_points.Count == 0)
        {
            EmptyState.Visibility = Visibility.Visible;
            return;
        }
        EmptyState.Visibility = Visibility.Collapsed;

        var maxV = _points.Max(p => p.Value);
        var top = maxV <= 0 ? 1 : maxV * 1.15;

        // 网格:3 条虚线
        for (var i = 0; i <= 3; i++)
        {
            var y = PadTop + (h - PadTop - PadBottom) * i / 3.0;
            var line = new Line
            {
                X1 = PadLeft,
                X2 = w - PadRight,
                Y1 = y,
                Y2 = y,
                Stroke = UiColors.Brush(UiColors.FgMuted),
                StrokeThickness = 1,
                Opacity = 0.28,
                StrokeDashArray = new DoubleCollection { 3, 3 },
            };
            cv.Children.Add(line);

            var lbl = new TextBlock
            {
                Text = ((int)(top * (1 - i / 3.0))).ToString("N0"),
                FontSize = 10,
                Foreground = UiColors.Brush(UiColors.FgMuted),
            };
            Canvas.SetLeft(lbl, 0);
            Canvas.SetTop(lbl, y - 8);
            cv.Children.Add(lbl);
        }

        var plotW = w - PadLeft - PadRight;
        var plotH = h - PadTop - PadBottom;

        double X(int i) => _points.Count == 1
            ? PadLeft + plotW / 2
            : PadLeft + plotW * i / (double)(_points.Count - 1);
        double Y(double v) => PadTop + plotH * (1 - v / top);

        var pts = new PointCollection();
        for (var i = 0; i < _points.Count; i++)
        {
            pts.Add(new Windows.Foundation.Point(X(i), Y(_points[i].Value)));
        }

        // 面积(同色 15%)
        var areaPts = new PointCollection();
        foreach (var p in pts) areaPts.Add(p);
        areaPts.Add(new Windows.Foundation.Point(X(_points.Count - 1), PadTop + plotH));
        areaPts.Add(new Windows.Foundation.Point(X(0), PadTop + plotH));
        _area = new Polyline
        {
            Points = areaPts,
            Fill = UiColors.Brush(UiColors.Tint(UiColors.Accent, 0x26)),
            Stroke = null,
            IsHitTestVisible = false,
        };
        cv.Children.Add(_area);

        // 折线
        _line = new Polyline
        {
            Points = pts,
            Stroke = UiColors.Brush(UiColors.Accent),
            StrokeThickness = LineThickness,
            StrokeLineJoin = PenLineJoin.Round,
            StrokeStartLineCap = PenLineCap.Round,
            StrokeEndLineCap = PenLineCap.Round,
            IsHitTestVisible = false,
        };
        cv.Children.Add(_line);

        // 数据点(≤40)
        for (var i = 0; i < _points.Count; i++)
        {
            var dot = new Ellipse
            {
                Width = DotRadius * 2,
                Height = DotRadius * 2,
                Fill = UiColors.Brush(UiColors.Accent),
                IsHitTestVisible = false,
            };
            Canvas.SetLeft(dot, X(i) - DotRadius);
            Canvas.SetTop(dot, Y(_points[i].Value) - DotRadius);
            cv.Children.Add(dot);
        }

        // 线端值标签
        var last = _points.Count - 1;
        _endLabel = new TextBlock
        {
            Text = _points[last].Value.ToString("N0"),
            FontSize = 11,
            FontWeight = Microsoft.UI.Text.FontWeights.SemiBold,
            Foreground = UiColors.Brush(UiColors.Accent),
        };
        Canvas.SetLeft(_endLabel, X(last) + 8);
        Canvas.SetTop(_endLabel, Y(_points[last].Value) - 9);
        cv.Children.Add(_endLabel);

        // 悬停元素(初始隐藏)
        _hoverLine = new Line
        {
            Stroke = UiColors.Brush(UiColors.FgSecondary),
            StrokeThickness = 1,
            Opacity = 0.55,
            StrokeDashArray = new DoubleCollection { 3, 3 },
            Visibility = Visibility.Collapsed,
            IsHitTestVisible = false,
        };
        cv.Children.Add(_hoverLine);

        _hoverDot = new Ellipse
        {
            Width = 9,
            Height = 9,
            Fill = UiColors.Brush(UiColors.Accent),
            Stroke = new SolidColorBrush(UiColors.FgPrimary),
            StrokeThickness = 2,
            Visibility = Visibility.Collapsed,
            IsHitTestVisible = false,
        };
        cv.Children.Add(_hoverDot);

        _hoverTip = new Border
        {
            CornerRadius = new CornerRadius(4),
            Background = new SolidColorBrush(Windows.UI.Color.FromArgb(0xF2, 0x2A, 0x2A, 0x2A)),
            BorderBrush = UiColors.Brush(UiColors.Border),
            BorderThickness = new Thickness(1),
            Padding = new Thickness(8, 4, 8, 4),
            Visibility = Visibility.Collapsed,
            IsHitTestVisible = false,
            Child = new TextBlock
            {
                FontSize = 11,
                Foreground = UiColors.Brush(UiColors.FgPrimary),
                Text = "",
            },
        };
        cv.Children.Add(_hoverTip);
    }

    // ──── 悬停 ────
    private void OnPointerMoved(object sender, PointerRoutedEventArgs e)
    {
        if (_points.Count == 0 || _hoverDot is null || _hoverLine is null || _hoverTip is null) return;
        var cv = Surface;
        var p = e.GetCurrentPoint(cv).Position;
        var w = cv.ActualWidth;
        var h = cv.ActualHeight;
        var plotW = w - PadLeft - PadRight;
        var plotH = h - PadTop - PadBottom;
        if (plotW <= 0) return;

        var maxV = _points.Max(x => x.Value);
        var top = maxV <= 0 ? 1 : maxV * 1.15;

        var ratio = (p.X - PadLeft) / plotW;
        var idx = _points.Count == 1
            ? 0
            : (int)Math.Round(ratio * (_points.Count - 1));
        idx = Math.Clamp(idx, 0, _points.Count - 1);

        double X(int i) => _points.Count == 1
            ? PadLeft + plotW / 2
            : PadLeft + plotW * i / (double)(_points.Count - 1);
        double Y(double v) => PadTop + plotH * (1 - v / top);

        var x = X(idx);
        var y = Y(_points[idx].Value);

        _hoverLine.X1 = x;
        _hoverLine.X2 = x;
        _hoverLine.Y1 = PadTop;
        _hoverLine.Y2 = PadTop + plotH;
        _hoverLine.Visibility = Visibility.Visible;

        Canvas.SetLeft(_hoverDot, x - 4.5);
        Canvas.SetTop(_hoverDot, y - 4.5);
        _hoverDot.Visibility = Visibility.Visible;

        if (_hoverTip.Child is TextBlock tipText)
        {
            tipText.Text = $"{_points[idx].Value:N0}  {_points[idx].Label}";
        }
        _hoverTip.Measure(new Windows.Foundation.Size(400, 40));
        var tipW = _hoverTip.DesiredSize.Width;
        var left = Math.Clamp(x + 10, 0, Math.Max(0, w - tipW));
        Canvas.SetLeft(_hoverTip, left);
        Canvas.SetTop(_hoverTip, Math.Max(0, y - 40));
        _hoverTip.Visibility = Visibility.Visible;
    }

    private void HideHover()
    {
        _hoverLine?.Visibility = Visibility.Collapsed;
        _hoverDot?.Visibility = Visibility.Collapsed;
        _hoverTip?.Visibility = Visibility.Collapsed;
    }
}
