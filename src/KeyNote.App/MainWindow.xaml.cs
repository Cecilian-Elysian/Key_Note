using System;
using System.Runtime.InteropServices;
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
    }

    [DllImport("user32.dll")]
    private static extern int GetDpiForWindow(nint hwnd);
}
