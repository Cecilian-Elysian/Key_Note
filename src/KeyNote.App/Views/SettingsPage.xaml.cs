using KeyNote.App.Services;
using KeyNote.Core.Settings;
using KeyNote.Core.Storage;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace KeyNote.App.Views;

/// 设置页(Page 5):声明式字段表(分组 / 行式布局 / 常驻说明 / 搜索 / 固定底栏)。
public sealed partial class SettingsPage : Page
{

    private readonly Dictionary<string, object> _editors = [];
    private readonly List<FrameworkElement> _rows = [];
    private readonly List<(StackPanel Host, TextBlock Chevron)> _advSections = [];
    private readonly List<bool> _advOpen = [];
    private AppSettings _cfg = null!;
    private Border? _updateRow;
    private TextBlock? _updateText;

    public SettingsPage()
    {
        InitializeComponent();
        Loaded += (_, _) =>
        {
            UpdateService.Completed += OnUpdateCompleted;
            Build();
        };
        Unloaded += (_, _) => UpdateService.Completed -= OnUpdateCompleted;
        SearchBox.TextChanged += (_, _) => ApplyFilter();
    }

    private void Build()
    {
        _cfg = App.Instance.Settings;
        Header.ShowRefresh = false;
        GroupsHost.Children.Clear();
        _editors.Clear();
        _rows.Clear();
        _advSections.Clear();
        _advOpen.Clear();
        _updateRow = null;
        _updateText = null;

        foreach (var (groupName, fields) in Groups)
        {
            var normal = fields.Where(f => !f.Advanced).ToArray();
            var advanced = fields.Where(f => f.Advanced).ToArray();

            var card = new Border
            {
                Style = (Style)Application.Current.Resources["AppCardStyle"],
                Padding = new Thickness(0),
            };
            var stack = new StackPanel();

            // 分组标题:强调色竖条 + 15px SemiBold
            var titleRow = new Grid
            {
                Padding = new Thickness(14, 12, 14, 8),
            };
            titleRow.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            titleRow.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            var bar = new Border
            {
                Width = 3,
                Height = 14,
                Background = new SolidColorBrush(Services.UiPalette.Accent),
                CornerRadius = new CornerRadius(2),
                VerticalAlignment = VerticalAlignment.Center,
                Margin = new Thickness(0, 0, 8, 0),
            };
            Grid.SetColumn(bar, 0);
            var title = new TextBlock
            {
                Text = groupName,
                FontSize = 15,
                FontWeight = Microsoft.UI.Text.FontWeights.SemiBold,
                Foreground = new SolidColorBrush(Theme.UiColors.FgPrimary),
                VerticalAlignment = VerticalAlignment.Center,
            };
            Grid.SetColumn(title, 1);
            titleRow.Children.Add(bar);
            titleRow.Children.Add(title);
            stack.Children.Add(titleRow);

            AppendRows(stack, normal, trailingSeparator: advanced.Length > 0);

            // 高级设置折叠区(默认折叠)
            if (advanced.Length > 0)
            {
                var advHost = new StackPanel { Visibility = Visibility.Collapsed };
                AppendRows(advHost, advanced, trailingSeparator: false);

                var chevron = new TextBlock
                {
                    FontFamily = new FontFamily("Segoe Fluent Icons"),
                    Text = "\uE76C", // ChevronRight
                    FontSize = 12,
                    Foreground = new SolidColorBrush(Theme.UiColors.FgMuted),
                    VerticalAlignment = VerticalAlignment.Center,
                };
                var advTitle = new StackPanel
                {
                    Orientation = Orientation.Horizontal,
                    Spacing = 8,
                    VerticalAlignment = VerticalAlignment.Center,
                };
                advTitle.Children.Add(chevron);
                advTitle.Children.Add(new TextBlock
                {
                    Text = "高级设置",
                    FontSize = 13,
                    Foreground = new SolidColorBrush(Theme.UiColors.FgSecondary),
                    VerticalAlignment = VerticalAlignment.Center,
                });
                advTitle.Children.Add(new TextBlock
                {
                    Text = $"{advanced.Length} 项",
                    FontSize = 11,
                    Foreground = new SolidColorBrush(Theme.UiColors.FgMuted),
                    VerticalAlignment = VerticalAlignment.Center,
                });
                var advHeader = new Grid
                {
                    Padding = new Thickness(14, 10, 14, 10),
                    Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent),
                };
                advHeader.Children.Add(advTitle);
                advHeader.PointerPressed += (_, _) =>
                {
                    var idx = _advSections.FindIndex(s => s.Host == advHost);
                    _advOpen[idx] = !_advOpen[idx];
                    ApplyAdvState(idx);
                };

                stack.Children.Add(advHeader);
                stack.Children.Add(advHost);

                var idx = _advSections.Count;
                _advSections.Add((advHost, chevron));
                _advOpen.Add(false);
                ApplyAdvState(idx);
            }

            // 关于组:追加「发现新版」提示行(默认隐藏,检查到新版才显示)
            if (groupName == "关于")
            {
                stack.Children.Add(new Border
                {
                    Height = 1,
                    Background = new SolidColorBrush(Theme.UiColors.Divider),
                    Margin = new Thickness(14, 0, 14, 0),
                });
                stack.Children.Add(BuildUpdateRow());
            }

            card.Child = stack;
            GroupsHost.Children.Add(card);
        }

        if (UpdateService.LastResult is { } last) ApplyUpdateResult(last);
    }

    /// 高级区展开/折叠状态 → chevron 方向 + host 可见性
    private void ApplyAdvState(int idx)
    {
        var (host, chevron) = _advSections[idx];
        var open = _advOpen[idx];
        host.Visibility = open ? Visibility.Visible : Visibility.Collapsed;
        chevron.Text = open ? "\uE70D" : "\uE76C"; // ChevronDown / ChevronRight
    }

    /// 行 + 1px 分隔符追加;trailingSeparator = 末尾补一条(衔接后续区块)
    private void AppendRows(StackPanel host, FieldSpec[] fields, bool trailingSeparator)
    {
        for (var i = 0; i < fields.Length; i++)
        {
            host.Children.Add(BuildRow(fields[i]));
            if (i < fields.Length - 1 || trailingSeparator)
            {
                host.Children.Add(new Border
                {
                    Height = 1,
                    Background = new SolidColorBrush(Theme.UiColors.Divider),
                    Margin = new Thickness(14, 0, 14, 0),
                });
            }
        }
    }

    private FrameworkElement BuildRow(FieldSpec spec)
    {
        var grid = new Grid
        {
            Padding = new Thickness(14, 10, 14, 10),
        };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

        var left = new StackPanel { Spacing = 2, VerticalAlignment = VerticalAlignment.Center };
        left.Children.Add(new TextBlock
        {
            Text = spec.Title,
            FontSize = 14,
            Foreground = new SolidColorBrush(Theme.UiColors.FgPrimary),
        });
        var desc = new TextBlock
        {
            Text = spec.Desc,
            FontSize = 11,
            Foreground = new SolidColorBrush(Theme.UiColors.FgMuted),
            TextWrapping = TextWrapping.Wrap,
            MaxWidth = 460,
        };
        left.Children.Add(desc);
        Grid.SetColumn(left, 0);
        grid.Children.Add(left);

        FrameworkElement control = spec.Kind switch
        {
            FieldKind.Switch => BuildSwitch(spec),
            FieldKind.Slider => BuildSlider(spec),
            FieldKind.Combo => BuildCombo(spec),
            FieldKind.Number => BuildNumber(spec),
            FieldKind.Path => BuildPath(spec),
            FieldKind.Info => BuildInfo(spec),
            _ => BuildAction(spec),
        };
        Grid.SetColumn(control, 1);
        control.VerticalAlignment = VerticalAlignment.Center;
        grid.Children.Add(control);

        grid.Tag = spec.Title + " " + spec.Desc;
        _rows.Add(grid);
        return grid;
    }

    private void ApplyFilter()
    {
        var q = SearchBox.Text.Trim();
        // 搜索时强制展开所有高级区,清空后恢复折叠状态
        for (var i = 0; i < _advSections.Count; i++)
        {
            _advOpen[i] = q.Length > 0;
            ApplyAdvState(i);
        }
        foreach (var row in _rows)
        {
            var hit = q.Length == 0 || (row.Tag as string ?? string.Empty).Contains(q, StringComparison.OrdinalIgnoreCase);
            row.Visibility = hit ? Visibility.Visible : Visibility.Collapsed;
        }
    }

    // ──── 保存 / 恢复默认 ────
    private void SaveButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var cfg = App.Instance.Settings;
            foreach (var (key, value) in _editors)
            {
                switch (value)
                {
                    case bool b: cfg.Set(key, b); break;
                    case int i: cfg.Set(key, i); break;
                    case double d: cfg.Set(key, d); break;
                    case string s: cfg.Set(key, s); break;
                }
            }
            cfg.Save();

            // 立即生效
            AutostartService.SetEnabled(cfg.AutoStart);
            App.Instance.Tray.SetVisible(!cfg.HideTrayIcon);
            if (cfg.ListenerEnabled) App.Instance.Hooks.Resume(); else App.Instance.Hooks.Pause();
            if (cfg.MouseListenerEnabled) App.Instance.Hooks.ResumeMouse(); else App.Instance.Hooks.PauseMouse();
            KeyNoteDb.SetRetentionDays(cfg.RetentionDays);
            App.Instance.ApplyWindowAlpha(cfg.GetDouble("window_alpha", 1.0));
            App.Instance.ApplyHotkeySettings();
            App.Instance.ApplyIdlePause(cfg.GetInt("idle_pause_min", 0));
            if (WindowService.Current is MainWindow mw)
            {
                mw.UpdateStatus(!App.Instance.Hooks.IsPaused, App.Instance.Hooks.IsRunning);
            }

            StatusText.Text = "已保存";
        }
        catch (Exception ex)
        {
            Core.Utils.CrashLog.Write("settings.save", ex);
            StatusText.Text = "保存失败";
        }
    }

    private void ResetButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var cfg = App.Instance.Settings;
            cfg.Set("auto_start", false);
            cfg.Set("silent_start", false);
            cfg.Set("hide_tray_icon", false);
            cfg.Set("start_minimized", false);
            cfg.Set("close_to_tray", true);
            cfg.Set("listener_enabled", true);
            cfg.Set("mouse_listener_enabled", true);
            cfg.Set("idle_pause_min", 0);
            cfg.Set("window_alpha", 1.0);
            cfg.Set("remember_window_pos", true);
            cfg.Set("heatmap_days", 365);
            cfg.Set("refresh_interval_sec", 5);
            cfg.Set("db_retention_days", 365);
            cfg.Set("backup_dir", "");
            cfg.Save();

            AutostartService.SetEnabled(false);
            App.Instance.Hooks.Resume();
            App.Instance.Hooks.ResumeMouse();
            KeyNoteDb.SetRetentionDays(365);
            App.Instance.ApplyWindowAlpha(1.0);
            // 恢复默认必须同步运行时状态,否则旧值继续生效(如闲置暂停仍按旧分钟数)
            App.Instance.ApplyIdlePause(0);
            App.Instance.Tray.SetVisible(true);
            if (WindowService.Current is MainWindow mw)
            {
                mw.UpdateStatus(!App.Instance.Hooks.IsPaused, App.Instance.Hooks.IsRunning);
            }

            Build();
            StatusText.Text = "已恢复默认";
        }
        catch (Exception ex)
        {
            Core.Utils.CrashLog.Write("settings.reset", ex);
            StatusText.Text = "恢复失败";
        }
    }
}
