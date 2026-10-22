using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using KeyNote.App.Helpers;
using KeyNote.App.Theme;
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

    /// explorer 重启后需要重新挂载托盘图标
    private static readonly uint TaskbarCreatedMsg = TrayNative.RegisterWindowMessageW("TaskbarCreated");

    private Thread? _thread;
    private uint _threadId;
    private nint _wnd;
    private nint _icon;
    private bool _visible;

    /// 图标期望可见性(UI 线程写,托盘线程读):解决启动时序竞态
    /// —— 此前 UI 线程在托盘线程挂图标之前就调 SetVisible(false),判断"已经是这个状态"直接返回,
    /// 结果托盘线程随后照常把图标加上,「隐藏托盘图标」在启动时失效。
    private volatile bool _desiredVisible = true;

    /// 待发气泡(图标就绪前收到的通知,挂好图标后补发)
    private string? _pendingBalloon;

    // ──── 回调(由 App 层接到 UI 线程) ────
    public Action<Action>? UiMarshal { get; set; }
    public Func<bool>? IsPaused { get; set; }
    public Action? OnShowWindow { get; set; }
    public Action? OnOpenSettings { get; set; }
    public Action? OnCheckUpdate { get; set; }
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

    /// 设置图标可见性(立即生效;与托盘线程的挂/摘操作解耦,避免启动竞态)
    public void SetVisible(bool visible)
    {
        _desiredVisible = visible;
        if (visible == _visible) return;
        if (visible) AddIcon();
        else RemoveIcon();
    }

    /// 托盘气泡通知(图标尚未就绪时先排队,挂好图标后补发)
    public void Notify(string message)
    {
        if (!_visible)
        {
            if (_desiredVisible) _pendingBalloon = message;
            return;
        }
        ShowBalloon(message);
    }

    private void ShowBalloon(string message)
    {
        try
        {
            var data = NotifyIconData();
            data.szInfo = message;
            data.szInfoTitle = "KeyNote";
            data.uFlags = 0x10 /* NIF_INFO */;
            TrayNative.Shell_NotifyIconW(0x01 /* NIM_MODIFY */, ref data);
        }
        catch
        {
            // 通知失败忽略
        }
    }

    public void Stop()
    {
        RemoveIcon();
        if (_threadId != 0) TrayNative.PostThreadMessage(_threadId, 0x0012 /* WM_QUIT */, 0, 0);
    }

    public void Dispose() => Stop();

    // ──── 托盘线程 ────
    private void TrayLoop()
    {
        _threadId = TrayNative.GetCurrentThreadId();

        _wndProcKeepAlive = WndProc;
        var wc = new TrayNative.WndClassEx
        {
            cbSize = (uint)System.Runtime.InteropServices.Marshal.SizeOf<TrayNative.WndClassEx>(),
            lpfnWndProc = System.Runtime.InteropServices.Marshal.GetFunctionPointerForDelegate(_wndProcKeepAlive),
            hInstance = TrayNative.GetModuleHandleW(null),
            lpszClassName = "KeyNoteTrayWindow",
        };
        if (TrayNative.RegisterClassExW(ref wc) == 0)
        {
            CrashLog.Write("tray", message: "RegisterClassExW failed");
            return;
        }

        _wnd = TrayNative.CreateWindowExW(0, "KeyNoteTrayWindow", "KeyNote", 0, 0, 0, 0, 0, IntPtr.Zero, IntPtr.Zero, wc.hInstance, IntPtr.Zero);
        if (_wnd == IntPtr.Zero)
        {
            CrashLog.Write("tray", message: "CreateWindowExW failed");
            return;
        }

        // 托盘线程起来后按期望态挂图标(「隐藏托盘图标」时启动就不挂)
        if (_desiredVisible) AddIcon();

        while (TrayNative.GetMessageW(out var msg, IntPtr.Zero, 0, 0) > 0)
        {
            // 托盘回调已在 WndProc 处理,这里只维持消息泵
        }
    }

    private TrayNative.NotifyIconDataW NotifyIconData() => new()
    {
        cbSize = Marshal.SizeOf<TrayNative.NotifyIconDataW>(),
        hWnd = _wnd,
        uID = 1,
        szTip = "KeyNote 键盘记录",
        szInfo = string.Empty,
        szInfoTitle = string.Empty,
    };

    private void AddIcon()
    {
        try
        {
            var data = NotifyIconData();
            data.uFlags = 0x01 /* NIF_MESSAGE */ | 0x02 /* NIF_ICON */ | 0x04 /* NIF_TIP */;
            data.uCallbackMessage = WmTray;
            data.hIcon = LoadTrayIcon();
            data.szTip = "KeyNote 键盘记录";
            var ok = TrayNative.Shell_NotifyIconW(0x00 /* NIM_ADD */, ref data);
            if (ok)
            {
                if (_icon != IntPtr.Zero) TrayNative.DestroyIcon(_icon);
                _icon = data.hIcon;
                _visible = true;
                // 图标就绪:补发之前排队的通知(否则启动提示会永久丢失)
                if (_pendingBalloon is { } pending)
                {
                    _pendingBalloon = null;
                    ShowBalloon(pending);
                }
            }
            else
            {
                if (data.hIcon != IntPtr.Zero) TrayNative.DestroyIcon(data.hIcon);
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
                TrayNative.Shell_NotifyIconW(0x02 /* NIM_DELETE */, ref data);
            }
            catch
            {
                // 忽略
            }
            TrayNative.DestroyIcon(_icon);
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
            return TrayNative.LoadImageW(IntPtr.Zero, path, 1 /* IMAGE_ICON */, 0, 0, 0x10 /* LR_DEFAULTSIZE */);
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

        var menu = TrayMenuBuilder.Build(IsPaused?.Invoke() ?? false);
        if (menu == IntPtr.Zero) return;
        TrayNative.SetForegroundWindow(_wnd);
        TrayNative.GetCursorPos(out var pos);
        var cmd = TrayNative.TrackPopupMenuEx(menu, TrayNative.TpmReturnCmd | TrayNative.TpmRightButton, pos.X, pos.Y, _wnd, IntPtr.Zero);
        TrayNative.PostMessageW(_wnd, 0, 0, 0);
        TrayNative.DestroyMenu(menu);
        DispatchCommand((int)cmd);
    }

    private void DispatchCommand(int id)
    {
        if (id == 0) return;
        if (id == TrayMenuBuilder.IdShow) Run(() => OnShowWindow?.Invoke());
        else if (id == TrayMenuBuilder.IdPause) Run(() => OnTogglePause?.Invoke());
        else if (id == TrayMenuBuilder.IdSettings) Run(() => OnOpenSettings?.Invoke());
        else if (id == TrayMenuBuilder.IdUpdateCheck) Run(() => OnCheckUpdate?.Invoke());
        else if (id == TrayMenuBuilder.IdBackup) Run(() => OnBackup?.Invoke());
        else if (id == TrayMenuBuilder.IdVacuum) Run(() => OnVacuum?.Invoke());
        else if (id == TrayMenuBuilder.IdQuit) Run(() => OnQuit?.Invoke());
        else if (id >= TrayMenuBuilder.IdRetentionBase && id < TrayMenuBuilder.IdRetentionBase + TrayMenuBuilder.RetentionCount)
        {
            var days = TrayMenuBuilder.RetentionDays(id - TrayMenuBuilder.IdRetentionBase);
            Run(() => OnSetRetention?.Invoke(days));
        }
    }

    private void Run(Action action)
    {
        if (UiMarshal is not null) UiMarshal(action);
        else action();
    }

    // ──── 窗口过程 ────
    private delegate nint WndProcDelegate(nint hWnd, uint msg, nint wParam, nint lParam);

    /// 委托需保持强引用,否则可能被 GC 回收导致钩子回调失效
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
            // explorer 重启后按期望态决定是否重新挂图标(此前无条件 AddIcon,会破坏「隐藏托盘图标」)
            if (_desiredVisible) AddIcon();
            return IntPtr.Zero;
        }
        return TrayNative.DefWindowProcW(hWnd, msg, wParam, lParam);
    }
}
