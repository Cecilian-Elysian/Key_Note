namespace KeyNote.App.Theme;

/// 暗色设计令牌(1:1 移植 Python theme.py 的 dark 主题);中性色与 WinUI ThemeResource 并存。
internal static class UiColors
{
    public static readonly Windows.UI.Color BgPrimary = Hex("#1C1C1C");
    public static readonly Windows.UI.Color BgSecondary = Hex("#272727");
    public static readonly Windows.UI.Color BgTertiary = Hex("#333333");
    public static readonly Windows.UI.Color FgPrimary = Hex("#FFFFFF");
    public static readonly Windows.UI.Color FgSecondary = Hex("#C5C5C5");
    public static readonly Windows.UI.Color FgMuted = Hex("#8D8D8D");
    public static readonly Windows.UI.Color Accent = Hex("#0A84FF");
    public static readonly Windows.UI.Color AccentHover = Hex("#3A96FF");
    public static readonly Windows.UI.Color Success = Hex("#34C759");
    public static readonly Windows.UI.Color Warning = Hex("#FAA817");
    public static readonly Windows.UI.Color Danger = Hex("#E2445C");
    public static readonly Windows.UI.Color Offline = Hex("#8E8E93");
    public static readonly Windows.UI.Color Source24G = Hex("#AF52DE");
    public static readonly Windows.UI.Color Border = Hex("#3D3D3D");
    public static readonly Windows.UI.Color Divider = Hex("#2F2F2F");
    public static readonly Windows.UI.Color ChartFace = Hex("#272727");
    public static readonly Windows.UI.Color ChartLine = Hex("#0A84FF");
    public static readonly Windows.UI.Color ChartTipBg = Hex("#F21C1C1C");
    public static readonly Windows.UI.Color ChartTipBorder = Hex("#FF3D3D3D");
    public static readonly Windows.UI.Color ChartTipFg = Hex("#FFFFFFFF");
    public static readonly Windows.UI.Color HeatmapEmpty = Hex("#303030");
    public static readonly Windows.UI.Color HeatmapL1 = Hex("#0E4429");
    public static readonly Windows.UI.Color HeatmapL2 = Hex("#006D32");
    public static readonly Windows.UI.Color HeatmapL3 = Hex("#26A641");
    public static readonly Windows.UI.Color HeatmapL4 = Hex("#39D353");

    public static Windows.UI.Color Hex(string hex)
    {
        var h = hex.TrimStart('#');
        return Windows.UI.Color.FromArgb(
            0xFF,
            Convert.ToByte(h[0..2], 16),
            Convert.ToByte(h[2..4], 16),
            Convert.ToByte(h[4..6], 16));
    }

    /// 同色 16% tint 底(胶囊徽标);WinUI 原生支持 alpha,无需预混。
    public static Windows.UI.Color Tint(Windows.UI.Color c, byte alpha = 0x28)
        => Windows.UI.Color.FromArgb(alpha, c.R, c.G, c.B);

    public static Microsoft.UI.Xaml.Media.SolidColorBrush Brush(Windows.UI.Color c)
        => new(c);
}
