using KeyNote.App.Theme;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace KeyNote.App.Views;

/// 设置项编辑器工厂:按 FieldKind 生成右侧控件。
public sealed partial class SettingsPage
{
    private FrameworkElement BuildSwitch(FieldSpec spec)
    {
        var toggle = new ToggleSwitch
        {
            IsOn = _cfg.GetBool(spec.Key),
            OnContent = "",
            OffContent = "",
        };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(toggle, spec.Title);
        toggle.Toggled += (_, _) => _editors[spec.Key] = toggle.IsOn;
        _editors[spec.Key] = toggle.IsOn;
        return toggle;
    }

    private FrameworkElement BuildSlider(FieldSpec spec)
    {
        var panel = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 10 };
        var value = new TextBlock
        {
            Text = _cfg.GetDouble(spec.Key, 1.0).ToString("0.00"),
            FontSize = 12,
            Foreground = new SolidColorBrush(Theme.UiColors.FgSecondary),
            VerticalAlignment = VerticalAlignment.Center,
            MinWidth = 36,
            TextAlignment = TextAlignment.Right,
        };
        var slider = new Slider
        {
            Minimum = spec.Lo,
            Maximum = spec.Hi,
            StepFrequency = spec.Step,
            Value = _cfg.GetDouble(spec.Key, spec.Hi),
            Width = 180,
        };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(slider, spec.Title);
        slider.ValueChanged += (_, _) =>
        {
            value.Text = slider.Value.ToString("0.00");
            _editors[spec.Key] = slider.Value;
        };
        _editors[spec.Key] = slider.Value;
        panel.Children.Add(slider);
        panel.Children.Add(value);
        return panel;
    }

    private FrameworkElement BuildCombo(FieldSpec spec)
    {
        var combo = new ComboBox
        {
            MinWidth = 120,
            ItemsSource = spec.Options,
        };
        var current = _cfg.GetInt(spec.Key, 365);
        var idx = Array.IndexOf(RetentionValues, current);
        combo.SelectedIndex = idx >= 0 ? idx : 3;
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(combo, spec.Title);
        combo.SelectionChanged += (_, _) =>
        {
            if (combo.SelectedIndex >= 0 && combo.SelectedIndex < RetentionValues.Length)
            {
                _editors[spec.Key] = RetentionValues[combo.SelectedIndex];
            }
        };
        _editors[spec.Key] = RetentionValues[Math.Max(0, combo.SelectedIndex)];
        return combo;
    }

    private FrameworkElement BuildNumber(FieldSpec spec)
    {
        var box = new NumberBox
        {
            Minimum = spec.Lo,
            Maximum = spec.Hi,
            SmallChange = spec.Step,
            LargeChange = spec.Step * 10,
            Value = _cfg.GetInt(spec.Key, (int)spec.Lo),
            Width = 110,
        };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(box, spec.Title);
        box.ValueChanged += (_, _) =>
        {
            if (!double.IsNaN(box.Value)) _editors[spec.Key] = (int)box.Value;
        };
        _editors[spec.Key] = (int)box.Value;
        return box;
    }

    private FrameworkElement BuildPath(FieldSpec spec)
    {
        var panel = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
        var text = new TextBox
        {
            Text = _cfg.GetString(spec.Key),
            PlaceholderText = "默认:数据目录/backups",
            Width = 220,
        };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(text, spec.Title);
        text.TextChanged += (_, _) => _editors[spec.Key] = text.Text;
        var browse = new Button { Content = "浏览…" };
        browse.Click += (_, _) =>
        {
            try
            {
                var picker = new Windows.Storage.Pickers.FolderPicker();
                picker.FileTypeFilter.Add("*");
                var hwnd = WinRT.Interop.WindowNative.GetWindowHandle(WindowService.Current!);
                WinRT.Interop.InitializeWithWindow.Initialize(picker, hwnd);
                var picked = picker.PickSingleFolderAsync();
                picked.AsTask().ContinueWith(t =>
                {
                    if (t.Result is { } folder)
                    {
                        DispatcherQueue.TryEnqueue(() => text.Text = folder.Path);
                    }
                });
            }
            catch (Exception ex)
            {
                Core.Utils.CrashLog.Write("settings.browse", ex);
            }
        };
        panel.Children.Add(text);
        panel.Children.Add(browse);
        _editors[spec.Key] = text.Text;
        return panel;
    }

    private FrameworkElement BuildAction(FieldSpec spec)
    {
        var button = new Button { Content = spec.Title };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(button, spec.Title);
        button.Click += (_, _) => RunAction(spec.ActionKey ?? string.Empty);
        return button;
    }

    private FrameworkElement BuildInfo(FieldSpec spec)
    {
        return new TextBlock
        {
            Text = spec.Value ?? string.Empty,
            FontSize = 13,
            Foreground = new SolidColorBrush(Theme.UiColors.FgSecondary),
            VerticalAlignment = VerticalAlignment.Center,
        };
    }

    /// 「发现新版」提示行:提示文案 + 打开 Release 页按钮(默认隐藏)。
}
