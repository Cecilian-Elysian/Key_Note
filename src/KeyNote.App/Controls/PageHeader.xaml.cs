using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace KeyNote.App.Controls;

/// 页头:标题 + 副标题 + 右侧"⟳ 刷新"文字钮。
public sealed partial class PageHeader : UserControl
{
    public static readonly DependencyProperty TitleProperty = DependencyProperty.Register(
        nameof(Title), typeof(string), typeof(PageHeader), new PropertyMetadata("", OnTitleChanged));

    public static readonly DependencyProperty SubtitleProperty = DependencyProperty.Register(
        nameof(Subtitle), typeof(string), typeof(PageHeader), new PropertyMetadata("", OnSubtitleChanged));

    public PageHeader()
    {
        InitializeComponent();
        RefreshButton.Click += (_, _) => RefreshRequested?.Invoke(this, new RoutedEventArgs());
    }

    public event EventHandler<RoutedEventArgs>? RefreshRequested;

    public string Title
    {
        get => (string)GetValue(TitleProperty);
        set => SetValue(TitleProperty, value);
    }

    public string Subtitle
    {
        get => (string)GetValue(SubtitleProperty);
        set => SetValue(SubtitleProperty, value);
    }

    private static void OnTitleChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        => ((PageHeader)d).TitleText.Text = (string)e.NewValue;

    private static void OnSubtitleChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        => ((PageHeader)d).SubtitleText.Text = (string)e.NewValue;
}
