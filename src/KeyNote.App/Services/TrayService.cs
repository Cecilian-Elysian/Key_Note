using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Text;
using KeyNote.App.Theme;
using KeyNote.Core.Storage;
using KeyNote.Core.Utils;

namespace KeyNote.App.Services;

/// 纯 Win32 托盘:Shell_NotifyIconW + 隐藏消息窗口 + TrackPopupMenuEx。
/// 菜单结构对齐 Python tray.py(实时统计 / 最近活动 / 数据管理 / 保留策略 / 退出)。
public sealed class TrayService : IDisposable
{
    private const int WmApp = 0x8000;
    private const int WmTray = WmApp + 1;
    private const int WmLButtonUp = 0x0202;
    private const int WmLButtonDblClk = 0x0203;
    private const int WmRButtonUp = 0x0205;

    private const uint MfString = 0x0000;
    private const uint MfGrayed = 0x0001;
    private const uint MfPopup = 0x0010;
    private const uint MfSeparator = 0x0800;
    private const uint MfChecked = 0x0008;
    private const uint MfDefault = 0x0400;
    private const uint TpmReturnCmd = 0x0100;
    private const uint TpmRightButton = 0x0002;

    private const int IdShow = 1;
    private const int IdPause = 2;
    private const int IdSettings = 3;
    private const int IdBackup = 10;
    private const int IdVacuum = 11;
    private const int IdRetentionBase = 20;
    private const int IdQuit = 99;

    private static readonly (string Label, int Days)[] RetentionOptions =
    {
        ("永久", 0), ("7 天", 7), ("180 天", 180), ("365 天", 365), ("730 天", 730),
    };

    /// explorer 重启后需要重新挂载托盘图标
    private static readonly uint TaskbarCreatedMsg = RegisterWindowMessageW("TaskbarCreated");

    private Thread? _thread;
    private uint _threadId;
    private nint _wnd;
    private nint _icon;
    private bool _visible;

    // ──── 回调(由 App 层接到 UI 线程) ────
    public Action<Action>? UiMarshal { get; set; }
    public Func<bool>? IsPaused { get; set; }
    public Action? OnShowWindow { get; set; }
    public Action? OnOpenSettings { get; set; }
    public Action? OnTogglePause { get; set; }
    public Action? OnBackup { get; set; }
    public Action? OnVacuum { get; set; }
    public Action<int>? OnSetRetention { get; set; }
    public Action? OnQuit { get; set; }

    public void Start()
    {
        if (_thread is not null) return;
        _thread = new Thread(TrayLoop) { IsBackground = true, Name = "tray" };
        _thread.SetApartmentState(ApartmentState.STA);
        _thread.Start();
    }

    public void SetVisible(bool visible)
    {
        if (visible == _visible) return;
        if (visible) AddIcon();
        else RemoveIcon();
        _visible = visible;
    }

    public void Notify(string message)
    {
        if (!_visible) return;
        try
        {
            var data = NotifyIconData();
            data.szInfo = message;
            data.szInfoTitle = "KeyNote";
            data.uFlags = 0x10 /* NIF_INFO */;
            Shell_NotifyIconW(0x01 /* NIM_MODIFY */, ref data);
        }
        catch
        {
            // 通知失败忽略
        }
    }

    public void Stop()
    {
        RemoveIcon();
        if (_threadId != 0) PostThreadMessage(_threadId, 0x0012 /* WM_QUIT */, 0, 0);
    }

    public void Dispose() => Stop();

    // ──── 托盘线程 ────
    private void TrayLoop()
    {
        _threadId = GetCurrentThreadId();

        _wndProcKeepAlive = WndProc;
        var wc = new WndClassEx
        {
            cbSize = (uint)System.Runtime.InteropServices.Marshal.SizeOf<WndClassEx>(),
            lpfnWndProc = System.Runtime.InteropServices.Marshal.GetFunctionPointerForDelegate(_wndProcKeepAlive),
            hInstance = GetModuleHandleW(null),
            lpszClassName = "KeyNoteTrayWindow",
        };
        if (RegisterClassExW(ref wc) == 0)
        {
            CrashLog.Write("tray", message: "RegisterClassExW failed");
            return;
        }

        _wnd = CreateWindowExW(0, "KeyNoteTrayWindow", "KeyNote", 0, 0, 0, 0, 0, IntPtr.Zero, IntPtr.Zero, wc.hInstance, IntPtr.Zero);
        if (_wnd == IntPtr.Zero)
        {
            CrashLog.Write("tray", message: "CreateWindowExW failed");
            return;
        }

        AddIcon();

        while (GetMessageW(out var msg, IntPtr.Zero, 0, 0) > 0)
        {
            // 托盘回调已在 WndProc 处理,这里只维持消息泵
        }
    }

    private void AddIcon()
    {
        try
        {
            var data = NotifyIconData();
            data.uFlags = 0x01 /* NIF_MESSAGE */ | 0x02 /* NIF_ICON */ | 0x04 /* NIF_TIP */;
            data.uCallbackMessage = WmTray;
            data.hIcon = LoadTrayIcon();
            data.szTip = "KeyNote 键盘记录";
            var ok = Shell_NotifyIconW(0x00 /* NIM_ADD */, ref data);
            if (ok)
            {
                if (_icon != IntPtr.Zero) DestroyIcon(_icon);
                _icon = data.hIcon;
                _visible = true;
            }
            else
            {
                if (data.hIcon != IntPtr.Zero) DestroyIcon(data.hIcon);
                _visible = false;
                CrashLog.Write("tray.add", message:
                    $"NIM_ADD failed err={Marshal.GetLastWin32Error()} wnd=0x{_wnd.ToInt64():X}");
            }
        }
        catch (Exception ex)
        {
            CrashLog.Write("tray.add", ex);
        }
    }

    private void RemoveIcon()
    {
        if (_icon != IntPtr.Zero)
        {
            try
            {
                var data = NotifyIconData();
                Shell_NotifyIconW(0x02 /* NIM_DELETE */, ref data);
            }
            catch
            {
                // 忽略
            }
            DestroyIcon(_icon);
            _icon = IntPtr.Zero;
        }
        _visible = false;
    }

    private nint LoadTrayIcon()
    {
        var path = Path.Combine(AppPaths.ExeDir, "icon.ico");
        if (!File.Exists(path)) path = Path.Combine(AppContext.BaseDirectory, "icon.ico");
        if (!File.Exists(path)) return IntPtr.Zero;
        try
        {
            return CreateTintedIcon(path);
        }
        catch (Exception ex)
        {
            CrashLog.Write("tray.icon", ex);
            return LoadImageW(IntPtr.Zero, path, 1 /* IMAGE_ICON */, 0, 0, 0x10 /* LR_DEFAULTSIZE */);
        }
    }

    // 30% accent tint:dst = 0.7*src + 0.3*accent(#0A84FF),alpha 保留(对齐 Python 版托盘图标观感)
    private static nint CreateTintedIcon(string path)
    {
        using var icon = new Icon(path, 32, 32);
        using var src = icon.ToBitmap();
        var a = UiColors.Accent;
        var matrix = new ColorMatrix
        {
            Matrix00 = 0.7f, Matrix04 = 0.3f * a.R / 255f,
            Matrix11 = 0.7f, Matrix14 = 0.3f * a.G / 255f,
            Matrix22 = 0.7f, Matrix24 = 0.3f * a.B / 255f,
            Matrix33 = 1f,
        };
        using var dst = new Bitmap(src.Width, src.Height, PixelFormat.Format32bppArgb);
        using (var g = Graphics.FromImage(dst))
        {
            using var attr = new ImageAttributes();
            attr.SetColorMatrix(matrix);
            var rect = new Rectangle(0, 0, src.Width, src.Height);
            g.DrawImage(src, rect, 0, 0, src.Width, src.Height, GraphicsUnit.Pixel, attr);
        }
        return dst.GetHicon();
    }

    private void HandleTrayClick(nint lParam)
    {
        var msg = (int)(lParam & 0xFFFF);
        if (msg is WmLButtonUp or WmLButtonDblClk)
        {
            Run(() => OnShowWindow?.Invoke());
            return;
        }
        if (msg != WmRButtonUp) return;

        var menu = BuildMenu();
        if (menu == IntPtr.Zero) return;
        SetForegroundWindow(_wnd);
        GetCursorPos(out var pos);
        var cmd = TrackPopupMenuEx(menu, TpmReturnCmd | TpmRightButton, pos.X, pos.Y, _wnd, IntPtr.Zero);
        PostMessageW(_wnd, 0, 0, 0);
        DestroyMenu(menu);
        DispatchCommand((int)cmd);
    }

    private void DispatchCommand(int id)
    {
        if (id == 0) return;
        if (id == IdShow) Run(() => OnShowWindow?.Invoke());
        else if (id == IdPause) Run(() => OnTogglePause?.Invoke());
        else if (id == IdSettings) Run(() => OnOpenSettings?.Invoke());
        else if (id == IdBackup) Run(() => OnBackup?.Invoke());
        else if (id == IdVacuum) Run(() => OnVacuum?.Invoke());
        else if (id == IdQuit) Run(() => OnQuit?.Invoke());
        else if (id >= IdRetentionBase && id < IdRetentionBase + RetentionOptions.Length)
        {
            var days = RetentionOptions[id - IdRetentionBase].Days;
            Run(() => OnSetRetention?.Invoke(days));
        }
    }

    private void Run(Action action)
    {
        if (UiMarshal is not null) UiMarshal(action);
        else action();
    }

    // ──── 菜单构建(每次右键实时取数) ────
    private nint BuildMenu()
    {
        var menu = CreatePopupMenu();
        if (menu == IntPtr.Zero) return IntPtr.Zero;

        var paused = IsPaused?.Invoke() ?? false;
        var health = KeyNoteDb.Health();
        var sizeMb = health.SizeBytes / (1024.0 * 1024.0);
        var lastBackup = health.LastBackupTs > 0
            ? DateTimeOffset.FromUnixTimeSeconds(health.LastBackupTs).LocalDateTime.ToString("MM-dd HH:mm")
            : "从未";

        Append(menu, MfString | MfDefault, IdShow, "显示主窗口");
        Append(menu, MfString, IdPause, paused ? "▶ 继续" : "⏸ 暂停");
        Append(menu, MfString, IdSettings, "⚙ 设置...");
        Append(menu, MfSeparator, 0, null);

        var realtime = CreatePopupMenu();
        Append(realtime, MfString | MfGrayed, 0, $"总按键: {KeyNoteDb.CountTotal():N0}");
        Append(realtime, MfString | MfGrayed, 0, $"今日: {KeyNoteDb.CountToday():N0}");
        Append(realtime, MfString | MfGrayed, 0, $"连续打卡: {KeyNoteDb.StreakDays(365)} 天");
        Append(realtime, MfString | MfGrayed, 0, $"近 1h 平均: {Rate1h():F1}/分钟");
        Append(menu, MfPopup, (uint)realtime, "📈 实时统计");

        var recent = CreatePopupMenu();
        Append(recent, MfString | MfGrayed, 0, $"最近 5 分钟: {RecentBars()}");
        Append(recent, MfString | MfGrayed, 0, paused ? "当前状态: ⏸ 暂停" : "当前状态: ● 记录中");
        Append(menu, MfPopup, (uint)recent, "🕐 最近活动");

        var data = CreatePopupMenu();
        Append(data, MfString | MfGrayed, 0, $"总按键: {KeyNoteDb.CountTotal():N0}");
        Append(data, MfString | MfGrayed, 0, $"原始记录: {health.RawCount:N0}");
        Append(data, MfString | MfGrayed, 0, $"数据库: {sizeMb:F1} MB");
        Append(data, MfString | MfGrayed, 0, $"上次备份: {lastBackup}");
        Append(data, MfSeparator, 0, null);
        Append(data, MfString, IdBackup, "💾 立即备份");
        Append(data, MfString, IdVacuum, "🗜 立即 VACUUM");
        Append(data, MfSeparator, 0, null);

        var retention = CreatePopupMenu();
        var current = KeyNoteDb.Health().RetentionDays;
        for (var i = 0; i < RetentionOptions.Length; i++)
        {
            var (label, days) = RetentionOptions[i];
            var flags = MfString | (days == current ? MfChecked : 0);
            Append(retention, flags, (uint)(IdRetentionBase + i), label);
        }
        Append(data, MfPopup, (uint)retention, "保留 raw 数据");
        Append(menu, MfPopup, (uint)data, "📊 数据管理");

        Append(menu, MfSeparator, 0, null);
        Append(menu, MfString, IdQuit, "退出");
        return menu;
    }

    private static void Append(nint menu, uint flags, uint id, string? text)
    {
        AppendMenuW(menu, flags, id, text ?? string.Empty);
    }

    private static double Rate1h()
    {
        var rows = KeyNoteDb.RateSeries(1);
        if (rows.Count == 0) return 0;
        double total = 0;
        foreach (var (_, c) in rows) total += c;
        return total / rows.Count;
    }

    private static string RecentBars()
    {
        var rows = KeyNoteDb.RateSeries(1);
        var bucket = new long[5];
        var now = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        var cutoff = now - 5 * 60 * 1000;
        foreach (var (ts, c) in rows)
        {
            if (ts < cutoff) continue;
            var idx = (int)Math.Min(4, Math.Max(0, (ts - cutoff) / 60000));
            bucket[4 - idx] += c;
        }
        var peak = Math.Max(1, bucket.Max());
        const string glyphs = " ▁▂▃▄▅▆▇█";
        var sb = new StringBuilder();
        foreach (var v in bucket)
        {
            sb.Append(glyphs[Math.Min(8, (int)(v / (double)peak * 8))]);
        }
        return sb.ToString();
    }

    // ──── Win32 ────
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct NotifyIconDataW
    {
        public int cbSize;
        public nint hWnd;
        public uint uID;
        public uint uFlags;
        public uint uCallbackMessage;
        public nint hIcon;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string szTip;
        public uint dwState;
        public uint dwStateMask;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] public string szInfo;
        public uint uTimeoutOrVersion;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 64)] public string szInfoTitle;
        public uint dwInfoFlags;
        public Guid guidItem;
        public nint hBalloonIcon;
    }

    private NotifyIconDataW NotifyIconData() => new()
    {
        cbSize = Marshal.SizeOf<NotifyIconDataW>(),
        hWnd = _wnd,
        uID = 1,
        szTip = "KeyNote 键盘记录",
        szInfo = string.Empty,
        szInfoTitle = string.Empty,
    };

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct WndClassEx
    {
        public uint cbSize;
        public uint style;
        public nint lpfnWndProc;
        public int cbClsExtra;
        public int cbWndExtra;
        public nint hInstance;
        public nint hIcon;
        public nint hCursor;
        public nint hbrBackground;
        [MarshalAs(UnmanagedType.LPWStr)] public string? lpszMenuName;
        [MarshalAs(UnmanagedType.LPWStr)] public string lpszClassName;
        public nint hIconSm;
    }

    private delegate nint WndProcDelegate(nint hWnd, uint msg, nint wParam, nint lParam);

    private static WndProcDelegate? _wndProcKeepAlive;

    private nint WndProc(nint hWnd, uint msg, nint wParam, nint lParam)
    {
        // 托盘回调是 SendMessage 直达窗口过程,不走消息队列
        if (msg == WmTray)
        {
            try
            {
                HandleTrayClick(lParam);
            }
            catch (Exception ex)
            {
                CrashLog.Write("tray.click", ex);
            }
            return IntPtr.Zero;
        }
        if (msg == TaskbarCreatedMsg)
        {
            AddIcon();
            return IntPtr.Zero;
        }
        return DefWindowProcW(hWnd, msg, wParam, lParam);
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct Point
    {
        public int X;
        public int Y;
    }

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern uint RegisterWindowMessageW(string lpString);

    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    private static extern bool Shell_NotifyIconW(uint dwMessage, ref NotifyIconDataW lpData);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern ushort RegisterClassExW(ref WndClassEx lpwcx);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern nint CreateWindowExW(uint exStyle, string lpClassName, string? lpWindowName,
        uint dwStyle, int x, int y, int nWidth, int nHeight, nint hWndParent, nint hMenu, nint hInstance, nint lpParam);

    [DllImport("user32.dll")]
    private static extern nint DefWindowProcW(nint hWnd, uint msg, nint wParam, nint lParam);

    [DllImport("user32.dll")]
    private static extern bool PostMessageW(nint hWnd, uint msg, nint wParam, nint lParam);

    [DllImport("user32.dll")]
    private static extern bool PostThreadMessage(uint idThread, uint msg, nint wParam, nint lParam);

    [DllImport("user32.dll")]
    private static extern int GetMessageW(out Msg lpMsg, nint hWnd, uint wMsgFilterMin, uint wMsgFilterMax);

    [DllImport("user32.dll")]
    private static extern nint CreatePopupMenu();

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern bool AppendMenuW(nint hMenu, uint uFlags, uint uIDNewItem, string lpNewItem);

    [DllImport("user32.dll")]
    private static extern uint TrackPopupMenuEx(nint hmenu, uint fuFlags, int x, int y, nint hWnd, nint lptpm);

    [DllImport("user32.dll")]
    private static extern bool DestroyMenu(nint hMenu);

    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(nint hWnd);

    [DllImport("user32.dll")]
    private static extern bool GetCursorPos(out Point lpPoint);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern nint LoadImageW(nint hinst, string lpszName, uint uType, int cxDesired, int cyDesired, uint fuLoad);

    [DllImport("user32.dll")]
    private static extern bool DestroyIcon(nint hIcon);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    private static extern nint GetModuleHandleW(string? lpModuleName);

    [DllImport("kernel32.dll")]
    private static extern uint GetCurrentThreadId();

    [StructLayout(LayoutKind.Sequential)]
    private struct Msg
    {
        public nint hwnd;
        public uint message;
        public nint wParam;
        public nint lParam;
        public uint time;
        public int pt_x;
        public int pt_y;
    }
}
