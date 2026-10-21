using KeyNote.Core.Input;
using KeyNote.Core.Settings;
using KeyNote.Core.Storage;
using KeyNote.Core.Utils;
using KeyNote.App.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Globalization;

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
    private int _idlePauseMin;
    private DateTime _lastActivity = DateTime.Now;
    private bool _idlePaused;

    public bool IsQuitting => _quitting;

    /// 内容区不透明度(WinUI3 非打包窗口不支持整窗透明,退化为内容透明度)
    public void ApplyWindowAlpha(double alpha)
    {
        try
        {
            if (WindowService.Current is MainWindow mw) mw.SetContentOpacity(alpha);
        }
        catch (Exception ex)
        {
            CrashLog.Write("app.alpha", ex);
        }
    }

    /// Alt+1~5 快捷键(页内切换)
    public void ApplyHotkeySettings()
    {
        // 快捷键在 MainWindow 构造时注册,此处仅保留钩子以便设置变更时刷新
    }

    /// 闲置自动暂停
    public void ApplyIdlePause(int minutes)
    {
        _idlePauseMin = Math.Max(0, minutes);
        _lastActivity = DateTime.Now;
    }

    private void OnActivity()
    {
        _lastActivity = DateTime.Now;
        if (_idlePaused && _idlePauseMin > 0)
        {
            _idlePaused = false;
            Hooks.Resume();
            // 活动事件来自钩子线程,UI 更新必须切回 UI 线程
            if (WindowService.Current is MainWindow mw)
            {
                mw.DispatcherQueue.TryEnqueue(() => mw.UpdateStatus(true));
            }
        }
    }

    private void CheckIdle()
    {
        try
        {
            if (_idlePauseMin <= 0) return;
            var idle = DateTime.Now - _lastActivity;
            if (idle.TotalMinutes >= _idlePauseMin && !_idlePaused && !Hooks.IsPaused)
            {
                _idlePaused = true;
                Hooks.Pause();
                if (WindowService.Current is MainWindow mw) mw.UpdateStatus(false);
            }
        }
        catch (Exception ex)
        {
            CrashLog.Write("app.idle", ex);
        }
    }

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
        Hooks.ActivityFired += OnActivity;
        if (Settings.ListenerEnabled) Hooks.Start();
        ApplyIdlePause(Settings.GetInt("idle_pause_min", 0));

        // 闲置检测定时器
        var idleTimer = Microsoft.UI.Dispatching.DispatcherQueue.GetForCurrentThread().CreateTimer();
        idleTimer.Interval = TimeSpan.FromSeconds(30);
        idleTimer.Tick += (_, _) => CheckIdle();
        idleTimer.Start();

        // 托盘
        Tray = new TrayService
        {
            UiMarshal = action => window.DispatcherQueue.TryEnqueue(() => action()),
            IsPaused = () => Hooks.IsPaused,
            OnShowWindow = () => window.ShowMainWindow(),
            OnOpenSettings = () => window.NavigateTo("settings"),
            OnCheckUpdate = () => CheckUpdateManually(window),
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

        // 更新检查:启动后每日静默一次
        StartDailyUpdateCheck(window);

        // 状态胶囊
        window.UpdateStatus(!Hooks.IsPaused);
        window.SetContentOpacity(Settings.GetDouble("window_alpha", 1.0));

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

    // ──── 更新检查 ────
    /// 启动后每日静默检查一次(距上次检查不足 24h 则跳过);仅在发现新版时发托盘气泡。
    private void StartDailyUpdateCheck(MainWindow window)
    {
        try
        {
            var last = Settings.GetString("_last_update_check");
            if (DateTime.TryParse(last, CultureInfo.InvariantCulture, DateTimeStyles.None, out var lastTime)
                && (DateTime.Now - lastTime).TotalHours < 24) return;

            var queue = window.DispatcherQueue;
            _ = Task.Run(async () =>
            {
                try
                {
                    var info = await UpdateService.CheckAsync();
                    RecordUpdateCheckTime();
                    if (!info.HasUpdate) return;
                    queue.TryEnqueue(() => Tray.Notify($"发现新版本 v{info.Latest?.ToString(3)},可在设置页打开下载页"));
                }
                catch (Exception ex)
                {
                    CrashLog.Write("app.update", ex);
                }
            });
        }
        catch (Exception ex)
        {
            CrashLog.Write("app.update", ex);
        }
    }

    /// 手动检查更新(托盘菜单):结果走托盘气泡。
    private void CheckUpdateManually(MainWindow window)
    {
        try
        {
            var queue = window.DispatcherQueue;
            _ = Task.Run(async () =>
            {
                try
                {
                    var info = await UpdateService.CheckAsync();
                    RecordUpdateCheckTime();
                    queue.TryEnqueue(() => Tray.Notify(info.Message));
                }
                catch (Exception ex)
                {
                    CrashLog.Write("app.update", ex);
                }
            });
        }
        catch (Exception ex)
        {
            CrashLog.Write("app.update", ex);
        }
    }

    /// 记录检查时间(供每日静默检查判重)。
    private void RecordUpdateCheckTime()
    {
        Settings.Set("_last_update_check", DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture));
        Settings.Save();
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
