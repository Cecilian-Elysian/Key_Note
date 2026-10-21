using KeyNote.App.Theme;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;

namespace KeyNote.App.Controls;

/// Top N 横向条形图(1:1 移植 Python top_keys.py:accent 配色 + 值标签 + 空态三段式)。
public sealed partial class BarChartControl : UserControl
{
    private IReadOnlyList<(string Key, long Count)> _data = [];

    public BarChartControl()
    {
        InitializeComponent();
        SizeChanged += (_, _) => Render();
    }

    public void SetData(IReadOnlyList<(string Key, long Count)> data)
    {
        _data = data;
        Render();
    }

    private void Render()
    {
        var cv = Surface;
        cv.Children.Clear();
        var w = cv.ActualWidth;
        var h = cv.ActualHeight;
        if (w < 60 || h < 40) return;

        if (_data.Count == 0)
        {
            EmptyState.Show("暂无记录", "开始记录后,这里会显示常用 Top 10");
            return;
        }
        EmptyState.Hide();

        var labelW = 52;
        var valueW = 52;
        var top = 8;
        var bottom = 8;
        var barH = Math.Max(10, Math.Min(26, (h - top - bottom) / _data.Count - 6));
        var gap = 6;
        var plotX = labelW;
        var plotW = Math.Max(20, w - labelW - valueW);
        var max = _data.Max(d => d.Count);
        if (max <= 0) max = 1;

        double y = top;
        foreach (var (key, count) in _data)
        {
            var name = key.Length > 8 ? key[..8] : key;
            var lbl = new TextBlock
            {
                Text = name,
                FontSize = 11,
                Foreground = UiColors.Brush(UiColors.FgSecondary),
                TextTrimming = TextTrimming.CharacterEllipsis,
            };
            lbl.Measure(new Windows.Foundation.Size(labelW, 30));
            Canvas.SetLeft(lbl, 0);
            Canvas.SetTop(lbl, y + (barH - lbl.DesiredSize.Height) / 2);
            cv.Children.Add(lbl);

            var track = new Rectangle
            {
                Width = plotW,
                Height = barH,
                Fill = UiColors.Brush(UiColors.BgTertiary),
                RadiusX = 3,
                RadiusY = 3,
            };
            Canvas.SetLeft(track, plotX);
            Canvas.SetTop(track, y);
            cv.Children.Add(track);

            var bw = Math.Max(2, plotW * count / (double)max);
            var bar = new Rectangle
            {
                Width = bw,
                Height = barH,
                Fill = UiColors.Brush(UiColors.Accent),
                RadiusX = 3,
                RadiusY = 3,
            };
            Canvas.SetLeft(bar, plotX);
            Canvas.SetTop(bar, y);
            cv.Children.Add(bar);

            var val = new TextBlock
            {
                Text = count.ToString("N0"),
                FontSize = 11,
                Foreground = UiColors.Brush(UiColors.FgSecondary),
            };
            Canvas.SetLeft(val, plotX + bw + 6);
            Canvas.SetTop(val, y + (barH - val.DesiredSize.Height) / 2);
            cv.Children.Add(val);

            y += barH + gap;
        }
    }
}
