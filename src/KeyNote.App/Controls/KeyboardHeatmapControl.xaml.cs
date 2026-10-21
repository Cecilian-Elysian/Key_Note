using KeyNote.App.Theme;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;

namespace KeyNote.App.Controls;

/// QWERTY 键盘热力图(1:1 移植 Python keyboard.py 的 _draw_keyboard)。
public sealed partial class KeyboardHeatmapControl : UserControl
{
    private static readonly string[][] KeyRows =
    {
        ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-"],
        ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],
        ["a", "s", "d", "f", "g", "h", "j", "k", "l"],
        ["z", "x", "c", "v", "b", "n", "m"],
    };

    private static readonly double[] RowOffsets = [0.0, 0.5, 0.75, 1.25];
    private const int SpaceSpacerW = 5;

    private readonly Dictionary<string, (int x0, int y0, int x1, int y1)> _rects = [];
    private Dictionary<string, int> _counts = new(StringComparer.OrdinalIgnoreCase);
    private int _max;

    public KeyboardHeatmapControl()
    {
        InitializeComponent();
        SizeChanged += (_, _) => Render();
        PointerMoved += OnPointerMoved;
        PointerExited += (_, _) => Tip.Hide();
    }

    public void SetCounts(Dictionary<string, int> counts)
    {
        _counts = counts;
        _max = counts.Count > 0 ? counts.Values.Max() : 0;
        Render();
    }

    private Windows.UI.Color ColorFor(string key)
    {
        if (_max <= 0 || !_counts.TryGetValue(key, out var count) || count == 0)
        {
            return UiColors.BgTertiary;
        }
        var t = Math.Pow(count / (double)_max, 0.5);
        return Lerp(UiColors.BgTertiary, UiColors.Accent, t);
    }

    private static Windows.UI.Color Lerp(Windows.UI.Color a, Windows.UI.Color b, double t)
    {
        t = Math.Clamp(t, 0, 1);
        return Windows.UI.Color.FromArgb(
            0xFF,
            (byte)Math.Round(a.R + (b.R - a.R) * t),
            (byte)Math.Round(a.G + (b.G - a.G) * t),
            (byte)Math.Round(a.B + (b.B - a.B) * t));
    }

    private void Render()
    {
        var cv = Surface;
        cv.Children.Clear();
        _rects.Clear();
        var w = cv.ActualWidth;
        if (w < 50) return;

        if (_max <= 0)
        {
            EmptyState.Show("暂无记录", "开始记录后,这里会显示键盘按键分布");
            return;
        }
        EmptyState.Hide();

        const double gap = 5;
        var maxCols = KeyRows.Max(r => r.Length);
        var cellW = Math.Max(20, Math.Min(30, (w - 8 - (maxCols - 1) * gap) / maxCols));
        const double cellH = 30;
        var gridW = maxCols * cellW + (maxCols - 1) * gap;
        var startX = (w - gridW) / 2;

        var y = 8.0;
        for (var rowIdx = 0; rowIdx < KeyRows.Length; rowIdx++)
        {
            var row = KeyRows[rowIdx];
            var ox = startX + RowOffsets[rowIdx] * (cellW + gap) / 2;
            for (var kIdx = 0; kIdx < row.Length; kIdx++)
            {
                var key = row[kIdx];
                var x0 = ox + kIdx * (cellW + gap);
                var y0 = y;
                AddKey(cv, key, x0, y0, x0 + cellW, y0 + cellH, key.ToUpperInvariant());
            }
            y += cellH + gap;
        }

        var spaceCount = _counts.GetValueOrDefault("space");
        var spaceW = cellW * SpaceSpacerW + (SpaceSpacerW - 1) * gap;
        var sx0 = (w - spaceW) / 2;
        var sx1 = sx0 + spaceW;
        var sy0 = y;
        AddKey(cv, "space", sx0, sy0, sx1, sy0 + cellH, "SPACE", 9);

        // 色阶图例
        var legendY = sy0 + cellH + 4;
        var colors = new List<Windows.UI.Color>();
        for (double t = 0; t <= 1.0001; t += 0.25) colors.Add(Lerp(UiColors.BgTertiary, UiColors.Accent, t));
        var box = 9;
        var bgap = 3;
        var textW = 11;
        var legendW = textW + 8 + colors.Count * box + (colors.Count - 1) * bgap + 8 + textW;
        var lx = sx1 - legendW;
        var less = new TextBlock { Text = "少", FontSize = 9, Foreground = UiColors.Brush(UiColors.FgMuted) };
        Canvas.SetLeft(less, lx);
        Canvas.SetTop(less, legendY + box / 2 - 7);
        cv.Children.Add(less);
        lx += textW + 8;
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

        cv.Height = (int)(legendY + 14);
        Height = cv.Height;
    }

    private void AddKey(Canvas cv, string key, double x0, double y0, double x1, double y1, string label, double fontSize = 10)
    {
        var rect = new Rectangle
        {
            Width = x1 - x0,
            Height = y1 - y0,
            Fill = UiColors.Brush(ColorFor(key)),
            Stroke = UiColors.Brush(UiColors.Border),
            StrokeThickness = 1,
            RadiusX = 3,
            RadiusY = 3,
        };
        Canvas.SetLeft(rect, x0);
        Canvas.SetTop(rect, y0);
        cv.Children.Add(rect);

        var tb = new TextBlock
        {
            Text = label,
            FontSize = fontSize,
            FontWeight = Microsoft.UI.Text.FontWeights.Bold,
            Foreground = UiColors.Brush(UiColors.FgPrimary),
        };
        tb.Measure(new Windows.Foundation.Size(200, 40));
        Canvas.SetLeft(tb, (x0 + x1) / 2 - tb.DesiredSize.Width / 2);
        Canvas.SetTop(tb, (y0 + y1) / 2 - tb.DesiredSize.Height / 2);
        cv.Children.Add(tb);

        _rects[key] = ((int)x0, (int)y0, (int)x1, (int)y1);
    }

    private void OnPointerMoved(object sender, PointerRoutedEventArgs e)
    {
        var cv = Surface;
        var p = e.GetCurrentPoint(cv).Position;
        foreach (var (key, rect) in _rects)
        {
            if (p.X < rect.x0 || p.X > rect.x1 || p.Y < rect.y0 || p.Y > rect.y1) continue;
            var count = _counts.GetValueOrDefault(key);
            var label = key == "space" ? "Space" : key.ToUpperInvariant();
            if (_max > 0 && count > 0)
            {
                var pct = Math.Round(count / (double)_max * 100);
                Tip.Text = $"{label} · {count:N0} 次 · 占峰值 {pct}%";
            }
            else
            {
                Tip.Text = $"{label} · 0 次";
            }
            Tip.ShowAt(cv, p.X, p.Y);
            return;
        }
        Tip.Hide();
    }
}
