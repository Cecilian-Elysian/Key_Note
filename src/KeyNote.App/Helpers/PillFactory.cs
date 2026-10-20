using KeyNote.App.Theme;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace KeyNote.App.Helpers;

/// 胶囊徽标:语义色文字 + 同色 16% tint 底 + radius 4(vigil-watt 徽标同款)。
public static class PillFactory
{
    public static Border Create(string text, Windows.UI.Color color)
    {
        var tb = new TextBlock
        {
            Text = text,
            FontSize = 11,
            Foreground = UiColors.Brush(color),
            VerticalAlignment = VerticalAlignment.Center,
        };
        return new Border
        {
            CornerRadius = new CornerRadius(4),
            Padding = new Thickness(6, 2, 6, 2),
            Background = UiColors.Brush(UiColors.Tint(color)),
            Child = tb,
            VerticalAlignment = VerticalAlignment.Center,
        };
    }
}
