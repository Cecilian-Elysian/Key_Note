using Microsoft.UI;

namespace KeyNote.App.Services;

/// 语义状态色板(对齐 vigil-watt UiPalette);中性色一律走 ThemeResource,不进这里。
internal static class UiPalette
{
    public static readonly Windows.UI.Color Accent = FromHex("#0A84FF");
    public static readonly Windows.UI.Color Low = FromHex("#E2445C");
    public static readonly Windows.UI.Color Mid = FromHex("#FAAA17");
    public static readonly Windows.UI.Color Good = FromHex("#34C759");
    public static readonly Windows.UI.Color Offline = FromHex("#8E8E93");
    public static readonly Windows.UI.Color Source24G = FromHex("#AF52DE");

    /// 16% tint 底(胶囊徽标同款),XAML 原生支持 alpha,无需预混。
    public static Windows.UI.Color Tint(Windows.UI.Color c, byte alpha = 0x28)
        => Windows.UI.Color.FromArgb(alpha, c.R, c.G, c.B);

    public static Windows.UI.Color FromHex(string hex)
    {
        var h = hex.TrimStart('#');
        return Windows.UI.Color.FromArgb(
            0xFF,
            Convert.ToByte(h[0..2], 16),
            Convert.ToByte(h[2..4], 16),
            Convert.ToByte(h[4..6], 16));
    }
}
