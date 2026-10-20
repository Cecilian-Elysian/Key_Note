using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace KeyNote.App;

/// 应用根:强制 dark + 全局异常熔断;OnArgs 接收 Program 透传的启动参数(P1 接静默/最小化)。
public partial class App : Application
{
    public static App Instance { get; private set; } = null!;
    public string[] StartupArgs { get; private set; } = [];

    public App()
    {
        Instance = this;
        InitializeComponent();
        RequestedTheme = ApplicationTheme.Dark;
        UnhandledException += OnUnhandledException;
    }

    public void OnArgs(string[] args) => StartupArgs = args;

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        var window = new MainWindow();
        WindowService.Current = window;
        window.Activate();
    }

    private void OnUnhandledException(object sender, Microsoft.UI.Xaml.UnhandledExceptionEventArgs e)
    {
        // P1 落 keynote.crash.log;P0 先吞掉避免闪退无从排查
        e.Handled = true;
    }
}

/// 主窗口全局引用(托盘/设置回调唤起用,P1 起扩展)。
public static class WindowService
{
    public static Window? Current { get; set; }
}
