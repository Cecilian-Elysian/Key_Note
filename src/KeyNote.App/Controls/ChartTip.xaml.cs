using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace KeyNote.App.Controls;

/// 图表悬浮提示气泡:圆角底 + 白字,定位逻辑统一(贴鼠标右上,不出画布)。
public sealed partial class ChartTip : UserControl
{
    public ChartTip()
    {
        InitializeComponent();
    }

    /// 提示文本
    public string Text
    {
        get => TipText.Text;
        set => TipText.Text = value;
    }

    /// 显示气泡(canvas 为宿主画布,x/y 为指针位置)
    public void ShowAt(Canvas canvas, double x, double y)
    {
        if (canvas is null) return;
        TipBorder.Measure(new Windows.Foundation.Size(400, 40));
        var left = Math.Clamp(x + 12, 0, Math.Max(0, canvas.ActualWidth - TipBorder.DesiredSize.Width));
        var top = Math.Max(0, y - 34);
        Canvas.SetLeft(TipBorder, left);
        Canvas.SetTop(TipBorder, top);
        TipBorder.Visibility = Visibility.Visible;
    }

    /// 隐藏气泡
    public void Hide()
    {
        TipBorder.Visibility = Visibility.Collapsed;
    }

    /// 气泡是否可见
    public bool IsVisible => TipBorder.Visibility == Visibility.Visible;
}
