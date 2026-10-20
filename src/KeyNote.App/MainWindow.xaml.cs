using System;
using System.Runtime.InteropServices;
using KeyNote.Core.Storage;
using KeyNote.App.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Windows.Graphics;

namespace KeyNote.App;

/// 主窗口:800×600 + ExtendsContentIntoTitleBar + Mica 三级回退 + NavigationView 5 页。
public sealed partial class MainWindow : Window
{
    private const int LogicalWidth = 800;
    private const int LogicalHeight = 600;

    public MainWindow()
    {
        InitializeComponent();

        ExtendsContentIntoTitleBar = true;
        SetTitleBar(AppTitleBar);

        ApplyBackdrop();
        ApplyIcon();
        ResizeForDpi();

        ContentFrame.Navigate(typeof(Views.StatsPage));
        Nav.SelectedItem = Nav.MenuItems[0];

        // 自动刷新:只刷当前页(设置页不实现 IRefreshable,自然跳过)
        _refreshTimer = Microsoft.UI.Dispatching.DispatcherQueue.GetForCurrentThread().CreateTimer();
        _refreshTimer.Interval = TimeSpan.FromSeconds(Math.Max(1, App.Instance.Settings.RefreshIntervalSec));
        _refreshTimer.Tick += (_, _) => RefreshCurrentPage();
        _refreshTimer.Start();

        // 关闭窗口 → 最小化到托盘
        AppWindow.Closing += (_, args) =>
        {
            if (App.Instance.Settings.CloseToTray && !App.Instance.IsQuitting)
            {
                args.Cancel = true;
                AppWindow.Hide();
            }
        };
    }

    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer? _refreshTimer;

    private void RefreshCurrentPage()
    {
        try
        {
            if (ContentFrame.Content is Views.IRefreshable r) r.RefreshData();
        }
        catch (Exception ex)
        {
            Core.Utils.CrashLog.Write("window.autorefresh", ex);
        }
    }

    // ──── 材质:Mica → Acrylic → 纯色(有材质时 Root 必须无底色,否则盖住) ────
    private void ApplyBackdrop()
    {
        try
        {
            var backdrop = Services.WindowBackdrop.Create();
            if (backdrop is not null)
            {
                SystemBackdrop = backdrop;
                Root.Background = null;
            }
            else
            {
                Root.Background = new SolidColorBrush(Windows.UI.Color.FromArgb(0xFF, 0x1C, 0x1C, 0x1C));
            }
        }
        catch
        {
            Root.Background = new SolidColorBrush(Windows.UI.Color.FromArgb(0xFF, 0x1C, 0x1C, 0x1C));
        }
    }

    private void ApplyIcon()
    {
        try
        {
            AppWindow.SetIcon(System.IO.Path.Combine(AppContext.BaseDirectory, "icon.ico"));
        }
        catch
        {
            // 图标缺失不致命
        }
    }

    private void ResizeForDpi()
    {
        try
        {
            var hwnd = WinRT.Interop.WindowNative.GetWindowHandle(this);
            double scale = GetDpiForWindow(hwnd) / 96.0;
            AppWindow.Resize(new SizeInt32(
                (int)(LogicalWidth * scale),
                (int)(LogicalHeight * scale)));
        }
        catch
        {
            // DPI 查询失败保持默认尺寸
        }
    }

    // ──── 导航 ────
    private void Nav_SelectionChanged(NavigationView sender, NavigationViewSelectionChangedEventArgs args)
    {
        if (args.SelectedItem is not NavigationViewItem item || item.Tag is not string tag)
        {
            return;
        }

        var page = tag switch
        {
            "keyboard" => typeof(Views.KeyboardPage),
            "heatmap" => typeof(Views.HeatmapPage),
            "topkeys" => typeof(Views.TopKeysPage),
            "settings" => typeof(Views.SettingsPage),
            _ => typeof(Views.StatsPage),
        };

        if (ContentFrame.CurrentSourcePageType != page)
        {
            ContentFrame.Navigate(page);
        }
        RefreshCurrentPage();
    }

    /// 切到指定页(托盘⚙入口用)
    public void NavigateTo(string tag)
    {
        foreach (var item in Nav.MenuItems)
        {
            if (item is NavigationViewItem nvi && nvi.Tag is string t && t == tag)
            {
                Nav.SelectedItem = nvi;
                return;
            }
        }
    }

    /// 唤起主窗口(托盘点击)
    public void ShowMainWindow()
    {
        try
        {
            AppWindow.Show();
            Activate();
        }
        catch (Exception ex)
        {
            Core.Utils.CrashLog.Write("window.show", ex);
        }
    }

    /// 标题栏状态胶囊:记录中 / 已暂停
    public void UpdateStatus(bool recording)
    {
        try
        {
            var color = recording ? UiPalette.Good : UiPalette.Offline;
            StatusPill.Visibility = Visibility.Visible;
            StatusPill.Background = new SolidColorBrush(UiPalette.Tint(color));
            StatusPillText.Text = recording ? "记录中" : "已暂停";
            StatusPillText.Foreground = new SolidColorBrush(color);
            StatusDot.Fill = new SolidColorBrush(color);
        }
        catch (Exception ex)
        {
            Core.Utils.CrashLog.Write("window.status", ex);
        }
    }

    public void RunBackup()
    {
        try
        {
            var path = KeyNoteDb.Backup(App.Instance.Settings);
            App.Instance.Tray.Notify(path is null ? "备份失败" : $"已备份: {System.IO.Path.GetFileName(path)}");
        }
        catch (Exception ex)
        {
            Core.Utils.CrashLog.Write("window.backup", ex);
        }
    }

    public void RunVacuum()
    {
        try
        {
            var ok = KeyNoteDb.Vacuum();
            App.Instance.Tray.Notify(ok ? "VACUUM 完成" : "VACUUM 失败");
        }
        catch (Exception ex)
        {
            Core.Utils.CrashLog.Write("window.vacuum", ex);
        }
    }

    [DllImport("user32.dll")]
    private static extern int GetDpiForWindow(nint hwnd);
}
