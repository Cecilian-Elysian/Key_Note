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
    private enum FieldKind { Switch, Slider, Combo, Number, Path, Action }

    private sealed record FieldSpec(
        FieldKind Kind,
        string Key,
        string Title,
        string Desc,
        double Lo = 0,
        double Hi = 0,
        double Step = 0,
        string[]? Options = null,
        string? ActionKey = null,
        bool Advanced = false);

    private static readonly (string Name, FieldSpec[] Fields)[] Groups =
    {
        ("启动与常规", new[]
        {
            new FieldSpec(FieldKind.Switch, "auto_start", "开机自启动", "系统登录时自动启动 KeyNote,持续后台记录按键。"),
            new FieldSpec(FieldKind.Switch, "silent_start", "静默启动", "完全静默启动,无窗口、无托盘通知(适合后台常驻)。"),
            new FieldSpec(FieldKind.Switch, "start_minimized", "启动时最小化", "开机后直接驻留托盘,不弹出主窗口。"),
            new FieldSpec(FieldKind.Switch, "close_to_tray", "关闭窗口到托盘", "点关闭按钮时最小化到托盘而不是退出程序。"),
            new FieldSpec(FieldKind.Switch, "hide_tray_icon", "隐藏托盘图标", "隐藏系统托盘图标(极致隐身),仅靠热键/重启恢复。", Advanced: true),
            new FieldSpec(FieldKind.Switch, "listener_enabled", "启动时启动监听", "启动时开启全局键盘监听,关闭后不再记录按键。", Advanced: true),
            new FieldSpec(FieldKind.Switch, "mouse_listener_enabled", "记录鼠标点击", "后台记录鼠标左/右/中键与侧键(X1/X2)点击次数。", Advanced: true),
            new FieldSpec(FieldKind.Number, "idle_pause_min", "闲置自动暂停(分钟)", "无键盘/鼠标活动超过该时长后自动暂停记录,0 = 不暂停。", 0, 240, 1, Advanced: true),
        }),
        ("界面", new[]
        {
            new FieldSpec(FieldKind.Switch, "remember_window_pos", "记住窗口位置", "记住主窗口位置,下次启动恢复。"),
            new FieldSpec(FieldKind.Slider, "window_alpha", "内容透明度", "WinUI3 非打包窗口不支持整窗透明,该滑块调节内容与卡片的不透明度。", 0.6, 1.0, 0.05, Advanced: true),
            new FieldSpec(FieldKind.Number, "heatmap_days", "热力图天数", "年度热力图统计的天数范围。", 30, 730, 1, Advanced: true),
            new FieldSpec(FieldKind.Number, "refresh_interval_sec", "自动刷新间隔(秒)", "当前页数据的自动刷新间隔。", 2, 120, 1, Advanced: true),
        }),
        ("数据", new[]
        {
            new FieldSpec(FieldKind.Action, "backup_now", "立即备份", "对当前数据库做一致性快照。", ActionKey: "backup"),
            new FieldSpec(FieldKind.Action, "export_csv", "导出 CSV", "导出最近 30 天原始按键记录到数据目录。", ActionKey: "csv"),
            new FieldSpec(FieldKind.Combo, "db_retention_days", "保留 raw 数据", "原始按键记录的保留时长,到期自动清理(聚合表永久保留)。",
                Options: ["永久", "7 天", "180 天", "365 天", "730 天"], Advanced: true),
            new FieldSpec(FieldKind.Path, "backup_dir", "备份目录", "备份 .db 文件的目标目录,空 = 使用数据目录下的 backups/。", Advanced: true),
            new FieldSpec(FieldKind.Action, "vacuum_now", "立即 VACUUM", "重建数据库回收空间。", ActionKey: "vacuum", Advanced: true),
        }),
    };

    private static readonly int[] RetentionValues = [0, 7, 180, 365, 730];

    private readonly Dictionary<string, object> _editors = [];
    private readonly List<FrameworkElement> _rows = [];
    private readonly List<(StackPanel Host, TextBlock Chevron)> _advSections = [];
    private readonly List<bool> _advOpen = [];
    private AppSettings _cfg = null!;

    public SettingsPage()
    {
        InitializeComponent();
        Loaded += (_, _) => Build();
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

            card.Child = stack;
            GroupsHost.Children.Add(card);
        }
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
            _ => BuildAction(spec),
        };
        Grid.SetColumn(control, 1);
        control.VerticalAlignment = VerticalAlignment.Center;
        grid.Children.Add(control);

        grid.Tag = spec.Title + " " + spec.Desc;
        _rows.Add(grid);
        return grid;
    }

    private FrameworkElement BuildSwitch(FieldSpec spec)
    {
        var toggle = new ToggleSwitch
        {
            IsOn = _cfg.GetBool(spec.Key),
            OnContent = "",
            OffContent = "",
        };
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
        button.Click += (_, _) => RunAction(spec.ActionKey ?? string.Empty);
        return button;
    }

    private void RunAction(string action)
    {
        try
        {
            switch (action)
            {
                case "backup":
                {
                    var path = KeyNoteDb.Backup(_cfg);
                    StatusText.Text = path is null ? "备份失败" : $"已备份:{Path.GetFileName(path)}";
                    break;
                }
                case "vacuum":
                    StatusText.Text = KeyNoteDb.Vacuum() ? "VACUUM 完成" : "VACUUM 失败";
                    break;
                case "csv":
                {
                    var dir = Core.Utils.AppPaths.DataDir();
                    var file = Path.Combine(dir, $"keynote-export-{DateTime.Now:yyyyMMdd-HHmmss}.csv");
                    var rows = KeyNoteDb.ExportCsv(file, 30);
                    StatusText.Text = $"已导出 {rows:N0} 行 → {Path.GetFileName(file)}";
                    break;
                }
            }
        }
        catch (Exception ex)
        {
            Core.Utils.CrashLog.Write("settings.action", ex);
            StatusText.Text = "操作失败";
        }
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
