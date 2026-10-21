using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace KeyNote.App.Controls;

/// 空数据三段式空状态:图标字形 + 主文案 + 说明(AGENTS 规定的页面骨架元素)。
public sealed partial class EmptyStateView : UserControl
{
    public EmptyStateView()
    {
        InitializeComponent();
    }

    /// 图标字形(Segoe Fluent Icons)
    public string IconGlyph
    {
        get => EmptyIcon.Glyph;
        set => EmptyIcon.Glyph = value;
    }

    /// 主文案
    public string Title
    {
        get => EmptyTitle.Text;
        set => EmptyTitle.Text = value;
    }

    /// 说明文案
    public string Hint
    {
        get => EmptyHint.Text;
        set => EmptyHint.Text = value;
    }

    /// 显示空状态(统一文案入口)
    public void Show(string title, string hint, string glyph = "\uE787")
    {
        Title = title;
        Hint = hint;
        IconGlyph = glyph;
        Visibility = Visibility.Visible;
    }

    /// 隐藏空状态
    public void Hide() => Visibility = Visibility.Collapsed;
}
