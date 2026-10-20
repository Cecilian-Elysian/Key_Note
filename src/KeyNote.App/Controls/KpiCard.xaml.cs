using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace KeyNote.App.Controls;

/// KPI 副卡:标签(12 secondary)/ 数值(24 bold,hero 32)/ 脚注(11 tertiary)。
public sealed partial class KpiCard : UserControl
{
    public static readonly DependencyProperty LabelProperty = DependencyProperty.Register(
        nameof(Label), typeof(string), typeof(KpiCard), new PropertyMetadata("", OnLabelChanged));

    public static readonly DependencyProperty ValueProperty = DependencyProperty.Register(
        nameof(Value), typeof(string), typeof(KpiCard), new PropertyMetadata("—", OnValueChanged));

    public static readonly DependencyProperty FootnoteProperty = DependencyProperty.Register(
        nameof(Footnote), typeof(string), typeof(KpiCard), new PropertyMetadata("", OnFootnoteChanged));

    public static readonly DependencyProperty IsHeroProperty = DependencyProperty.Register(
        nameof(IsHero), typeof(bool), typeof(KpiCard), new PropertyMetadata(false, OnIsHeroChanged));

    public KpiCard()
    {
        InitializeComponent();
    }

    public string Label
    {
        get => (string)GetValue(LabelProperty);
        set => SetValue(LabelProperty, value);
    }

    public string Value
    {
        get => (string)GetValue(ValueProperty);
        set => SetValue(ValueProperty, value);
    }

    public string Footnote
    {
        get => (string)GetValue(FootnoteProperty);
        set => SetValue(FootnoteProperty, value);
    }

    /// 主卡 hero 数值(32 bold)
    public bool IsHero
    {
        get => (bool)GetValue(IsHeroProperty);
        set => SetValue(IsHeroProperty, value);
    }

    private static void OnLabelChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        => ((KpiCard)d).LabelText.Text = (string)e.NewValue;

    private static void OnValueChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        => ((KpiCard)d).ValueText.Text = (string)e.NewValue;

    private static void OnFootnoteChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        => ((KpiCard)d).FootText.Text = (string)e.NewValue;

    private static void OnIsHeroChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
    {
        var card = (KpiCard)d;
        card.ValueText.Style = (bool)e.NewValue
            ? (Style)Application.Current.Resources["CardHeroValueStyle"]
            : (Style)Application.Current.Resources["CardValueStyle"];
    }
}
