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

    /// 待确认的更新(每日静默检查发现新版时暂存,点气泡或手动检查时消费)
    private UpdateService.UpdateInfo? _pendingUpdate;

    /// 更新确认框同一次更新只弹一个
    private int _updatePromptVisible;

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
        Hooks.HookReady += () => window.DispatcherQueue.TryEnqueue(() => window.UpdateStatus(!Hooks.IsPaused, Hooks.IsRunning));
        if (Settings.ListenerEnabled) Hooks.Start();
        if (!Settings.MouseListenerEnabled) Hooks.PauseMouse();
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
            OnBalloonClicked = () => OnUpdateBalloonClicked(window),
            OnTogglePause = () =>
            {
                if (!Hooks.IsRunning) Hooks.Start();
                else if (Hooks.IsPaused) Hooks.Resume();
                else Hooks.Pause();
                window.UpdateStatus(!Hooks.IsPaused, Hooks.IsRunning);
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
        window.UpdateStatus(!Hooks.IsPaused, Hooks.IsRunning);
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
    /// 启动后每日静默检查一次(距上次检查不足 24h 则跳过);发现新版发托盘气泡。
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
                    // 仅成功才记每日时间戳:网络失败不该被 24h 静默窗吞掉
                    if (info.Ok) RecordUpdateCheckTime();
                    if (!info.HasUpdate) return;
                    _pendingUpdate = info;
                    var version = info.Latest?.ToString(3) ?? "";
                    queue.TryEnqueue(() => Tray.Notify($"发现 KeyNote 新版本 v{version},点此可下载安装"));
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

    /// 手动检查更新(托盘菜单 / 设置页):结果走托盘气泡,发现新版则直接弹确认框。
    private void CheckUpdateManually(MainWindow window, bool interactive = true)
    {
        try
        {
            var queue = window.DispatcherQueue;
            _ = Task.Run(async () =>
            {
                try
                {
                    var info = await UpdateService.CheckAsync();
                    if (info.Ok) RecordUpdateCheckTime();
                    if (!info.HasUpdate)
                    {
                        queue.TryEnqueue(() => Tray.Notify(info.Message));
                        return;
                    }
                    _pendingUpdate = info;
                    queue.TryEnqueue(() => Tray.Notify($"发现新版本 v{info.Latest?.ToString(3)},点此可下载安装"));
                    if (interactive) queue.TryEnqueue(() => _ = ShowPendingUpdate(window));
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

    /// 托盘气泡被点击:拉起主窗口并弹更新确认框。
    private void OnUpdateBalloonClicked(MainWindow window)
    {
        window.ShowMainWindow();
        if (_pendingUpdate is not null)
        {
            _ = ShowPendingUpdate(window);
        }
    }

    /// 弹更新确认框并按用户选择执行下载安装。
    /// XamlRoot 时序兜底:启动瞬间窗口未 Loaded 时 XamlRoot 为 null,弹框必失败,
    /// 而窗口若已处于激活态就不会再触发 Loaded → 退到等根元素 Loaded 再补弹。
    private async Task ShowPendingUpdate(MainWindow window)
    {
        if (_pendingUpdate is not { } info) return;
        if (Interlocked.Exchange(ref _updatePromptVisible, 1) != 0) return;

        try
        {
            var root = window.Content as FrameworkElement;
            if (root?.XamlRoot is null)
            {
                _pendingUpdate = info;
                if (root is not null)
                {
                    root.Loaded += RetryUpdatePrompt;
                }
                return;
            }

            var accepted = await UpdatePrompt.ShowAsync(info, root.XamlRoot);
            if (accepted)
            {
                await RunUpdateInstall(window, info);
            }
            else
            {
                UpdateService.SetStatus("已选择稍后安装");
            }
        }
        catch (Exception ex)
        {
            CrashLog.Write("app.update.prompt", ex);
        }
        finally
        {
            Interlocked.Exchange(ref _updatePromptVisible, 0);
        }
    }

    private void RetryUpdatePrompt(object sender, RoutedEventArgs e)
    {
        if (sender is FrameworkElement fe) fe.Loaded -= RetryUpdatePrompt;
        if (WindowService.Current is MainWindow mw) _ = ShowPendingUpdate(mw);
    }

    /// 应用内下载 + 拉起安装器(自动替换 + 重启)。
    private async Task RunUpdateInstall(MainWindow window, UpdateService.UpdateInfo info)
    {
        var root = window.Content as FrameworkElement;
        if (root?.XamlRoot is null) return;

        var launched = await UpdateServiceApp.InstallAsync(info, root.XamlRoot);
        if (launched)
        {
            // 安装器会用 Restart Manager 关掉我们并替换文件,装完自动重启
            Quit();
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
        CrashLog.Write("app.unhandled", e.Exception);
        // 交由系统处理(保持原语义)
        e.Handled = false;
    }
}

/// 主窗口全局引用(托盘/设置回调唤起用)。
public static class WindowService
{
    public static Window? Current { get; set; }
}
