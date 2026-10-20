using KeyNote.Core.Input;
using KeyNote.Core.Settings;
using KeyNote.Core.Storage;
using KeyNote.Core.Utils;
using KeyNote.App.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace KeyNote.App;

/// 应用根:加载设置 → 初始化 DB → 起钩子 → 起托盘 → 按配置隐藏窗口;全局异常落 crash log。
public partial class App : Application
{
    public static App Instance { get; private set; } = null!;
    public string[] StartupArgs { get; private set; } = [];

    public AppSettings Settings { get; private set; } = null!;
    public InputHookService Hooks { get; private set; } = null!;
    public TrayService Tray { get; private set; } = null!;

    private bool _quitting;

    public bool IsQuitting => _quitting;

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
        Settings = AppSettings.Load();

        try
        {
            KeyNoteDb.Init(Settings);
        }
        catch (Exception ex)
        {
            CrashLog.Write("db.init", ex);
        }

        var window = new MainWindow();
        WindowService.Current = window;
        window.Activate();

        // 钩子:全局键鼠监听
        Hooks = new InputHookService();
        if (Settings.ListenerEnabled) Hooks.Start();

        // 托盘
        Tray = new TrayService
        {
            UiMarshal = action => window.DispatcherQueue.TryEnqueue(() => action()),
            IsPaused = () => Hooks.IsPaused,
            OnShowWindow = () => window.ShowMainWindow(),
            OnOpenSettings = () => window.NavigateTo("settings"),
            OnTogglePause = () =>
            {
                if (Hooks.IsPaused) Hooks.Resume(); else Hooks.Pause();
                window.UpdateStatus(!Hooks.IsPaused);
            },
            OnBackup = () => window.RunBackup(),
            OnVacuum = () => window.RunVacuum(),
            OnSetRetention = days =>
            {
                Settings.Set("db_retention_days", days);
                Settings.Save();
                KeyNoteDb.SetRetentionDays(days);
            },
            OnQuit = () => Quit(),
        };
        Tray.Start();
        if (Settings.HideTrayIcon) Tray.SetVisible(false);

        // 状态胶囊
        window.UpdateStatus(!Hooks.IsPaused);

        // 静默/最小化启动
        var silent = HasArg("--silent") || Settings.SilentStart;
        var minimized = HasArg("--minimized") || Settings.StartMinimized;
        if (silent || minimized)
        {
            window.AppWindow.Hide();
            if (!silent && !Settings.AutoStart)
            {
                Tray.Notify("KeyNote 已启动,窗口已最小化到托盘");
            }
        }
    }

    private bool HasArg(string name)
    {
        foreach (var a in StartupArgs)
        {
            if (string.Equals(a, name, StringComparison.OrdinalIgnoreCase)) return true;
        }
        return false;
    }

    /// 退出流程:排空 DB → 停托盘 → 退进程
    public void Quit()
    {
        if (_quitting) return;
        _quitting = true;
        try { KeyNoteDb.Close(); } catch (Exception ex) { CrashLog.Write("db.close", ex); }
        try { Tray.Stop(); } catch { /* 忽略 */ }
        try { Hooks.Dispose(); } catch { /* 忽略 */ }
        try { WindowService.Current?.Close(); } catch { /* 忽略 */ }
        Exit();
    }

    private void OnUnhandledException(object sender, Microsoft.UI.Xaml.UnhandledExceptionEventArgs e)
    {
        CrashLog.Write("unhandled", e.Exception);
        // 交由系统处理(保持原语义)
        e.Handled = false;
    }
}

/// 主窗口全局引用(托盘/设置回调唤起用)。
public static class WindowService
{
    public static Window? Current { get; set; }
}
