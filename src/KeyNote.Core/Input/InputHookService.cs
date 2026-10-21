using System.Runtime.InteropServices;
using System.Text;
using KeyNote.Core.Storage;
using KeyNote.Core.Utils;

namespace KeyNote.Core.Input;

/// 全局键盘 + 鼠标钩子(WH_KEYBOARD_LL / WH_MOUSE_LL)。
/// 语义与 Python listener.py 对齐:修饰键只触发活动不记录、80ms 同名去重、
/// 键型五分类(letter/digit/symbol/modifier/function)、支持暂停/恢复。
public sealed class InputHookService : IDisposable
{
    private const int WhKeyboardLl = 13;
    private const int WhMouseLl = 14;
    private const int WmKeyDown = 0x0100;
    private const int WmKeyUp = 0x0101;
    private const int WmSysKeyDown = 0x0104;
    private const int WmSysKeyUp = 0x0105;
    private const uint LlkhfExtended = 0x01;
    private const int WmMouseMove = 0x0200;
    private const int WmLButtonDown = 0x0201;
    private const int WmRButtonDown = 0x0204;
    private const int WmMButtonDown = 0x0207;
    private const int WmXButtonDown = 0x020B;

    private Thread? _kbThread;
    private Thread? _msThread;
    private uint _kbThreadId;
    private uint _msThreadId;
    private nint _kbHook;
    private nint _msHook;

    private volatile bool _recording = true;
    private volatile bool _mouseRecording = true;
    private string _lastKeyName = "";
    private long _lastKeyStamp; // Stopwatch ticks

    // 修饰键状态(仅钩子线程访问):用于还原大小写 / CapsLock / AltGr
    private bool _lShift;
    private bool _rShift;
    private bool _lCtrl;
    private bool _rCtrl;
    private bool _lAlt;
    private bool _rAlt;
    private bool _capsLock;

    /// 任意键盘/鼠标活动(闲置检测用)。
    public event Action? ActivityFired;

    public bool IsPaused => !_recording;
    public bool IsMousePaused => !_mouseRecording;

    public void Start()
    {
        _kbThread = new Thread(KbLoop) { IsBackground = true, Name = "hook-kb" };
        _kbThread.SetApartmentState(ApartmentState.STA);
        _kbThread.Start();
        _msThread = new Thread(MsLoop) { IsBackground = true, Name = "hook-ms" };
        _msThread.SetApartmentState(ApartmentState.STA);
        _msThread.Start();
    }

    public void Pause() => _recording = false;
    public void Resume() => _recording = true;
    public void PauseMouse() => _mouseRecording = false;
    public void ResumeMouse() => _mouseRecording = true;

    public void Dispose()
    {
        StopThread(_kbThreadId, ref _kbHook);
        StopThread(_msThreadId, ref _msHook);
    }

    private void StopThread(uint threadId, ref nint hook)
    {
        if (threadId != 0) PostThreadMessage(threadId, 0x0012 /* WM_QUIT */, 0, 0);
        if (hook != 0) UnhookWindowsHookEx(hook);
        hook = 0;
    }

    // ──── 键盘线程 ────
    private void KbLoop()
    {
        _kbThreadId = GetCurrentThreadId();
        var ctor = new HookDelegate(KbProc);
        _kbHook = SetWindowsHookExW(WhKeyboardLl, ctor, GetModuleHandleW(null), 0);
        if (_kbHook == 0) CrashLog.Write("hook.keyboard", message: $"SetWindowsHookEx failed: {Marshal.GetLastWin32Error()}");
        while (GetMessageW(out _, 0, 0, 0) > 0) { }
        if (_kbHook != 0) UnhookWindowsHookEx(_kbHook);
        GC.KeepAlive(ctor);
    }

    private nint KbProc(int nCode, nint wParam, nint lParam)
    {
        if (nCode >= 0)
        {
            try
            {
                var msg = (int)(wParam & 0xFFFF);
                var isDown = msg is WmKeyDown or WmSysKeyDown;
                var isUp = msg is WmKeyUp or WmSysKeyUp;
                if (isDown || isUp)
                {
                    var info = Marshal.PtrToStructure<KbdLlHookStruct>(lParam);
                    HandleKey(info.vkCode, info.scanCode, info.flags, isDown);
                }
            }
            catch (Exception ex)
            {
                CrashLog.Write("hook.keyboard.proc", ex);
            }
        }
        return CallNextHookEx(0, nCode, wParam, lParam);
    }

    private void HandleKey(uint vk, uint scan, uint flags, bool isDown)
    {
        UpdateModifierState(vk, isDown);

        if (IsModifier(vk))
        {
            FireActivity();
            return;
        }
        if (!isDown) return;

        var name = KeyName(vk, scan, flags);
        if (string.IsNullOrEmpty(name)) return;

        var stamp = System.Diagnostics.Stopwatch.GetTimestamp();
        if (name == _lastKeyName && (stamp - _lastKeyStamp) < StopwatchFrequency * 0.08)
        {
            return;
        }
        _lastKeyName = name;
        _lastKeyStamp = stamp;

        FireActivity();
        if (!_recording) return;

        var type = IsFunction(vk) ? "function" : Classify(name);
        KeyNoteDb.Enqueue(name, type);
    }

    private void FireActivity()
    {
        try { ActivityFired?.Invoke(); } catch { /* 忽略 */ }
    }

    // ──── 鼠标线程 ────
    private void MsLoop()
    {
        _msThreadId = GetCurrentThreadId();
        var ctor = new HookDelegate(MsProc);
        _msHook = SetWindowsHookExW(WhMouseLl, ctor, GetModuleHandleW(null), 0);
        if (_msHook == 0) CrashLog.Write("hook.mouse", message: $"SetWindowsHookEx failed: {Marshal.GetLastWin32Error()}");
        while (GetMessageW(out _, 0, 0, 0) > 0) { }
        if (_msHook != 0) UnhookWindowsHookEx(_msHook);
        GC.KeepAlive(ctor);
    }

    private nint MsProc(int nCode, nint wParam, nint lParam)
    {
        if (nCode >= 0)
        {
            try
            {
                var msg = (int)(wParam & 0xFFFF);
                if (msg == WmMouseMove)
                {
                    // 移动只计活动(闲置检测),不记录点击
                    FireActivity();
                }
                else if (msg is WmLButtonDown or WmRButtonDown or WmMButtonDown or WmXButtonDown)
                {
                    var info = Marshal.PtrToStructure<MouseLlHookStruct>(lParam);
                    var button = MapMouseButton(msg, info.mouseData);
                    if (button is not null)
                    {
                        FireActivity();
                        if (_mouseRecording) KeyNoteDb.EnqueueMouse(button);
                    }
                }
            }
            catch (Exception ex)
            {
                CrashLog.Write("hook.mouse.proc", ex);
            }
        }
        return CallNextHookEx(0, nCode, wParam, lParam);
    }

    /// 鼠标按钮映射:左/右/中由消息判定,侧键取 mouseData 高字(1=x1,2=x2)。
    private static string? MapMouseButton(int msg, int mouseData)
    {
        if (msg == WmLButtonDown) return "left";
        if (msg == WmRButtonDown) return "right";
        if (msg == WmMButtonDown) return "middle";
        var which = (uint)((mouseData >> 16) & 0xFFFF);
        return which switch
        {
            1 => "x1",
            2 => "x2",
            _ => null,
        };
    }

    // ──── 按键名与分类(与 pynput 语义一致) ────
    private static readonly Dictionary<uint, string> NamedKeys = new()
    {
        [0x08] = "backspace", [0x09] = "tab", [0x0D] = "enter", [0x13] = "pause",
        [0x14] = "caps_lock", [0x1B] = "esc", [0x20] = "space", [0x21] = "page_up",
        [0x22] = "page_down", [0x23] = "end", [0x24] = "home", [0x25] = "left",
        [0x26] = "up", [0x27] = "right", [0x28] = "down", [0x2C] = "print_screen",
        [0x2D] = "insert", [0x2E] = "delete", [0x5D] = "menu", [0x90] = "num_lock",
        [0x91] = "scroll_lock",
    };

    private static readonly HashSet<uint> ModifierVks = new()
    {
        0x10, 0xA0, 0xA1,   // shift
        0x11, 0xA2, 0xA3,   // ctrl
        0x12, 0xA4, 0xA5,   // alt
        0x14,                // caps_lock
        0x90,                // num_lock
        0x91,                // scroll_lock
    };

    private static readonly HashSet<uint> FunctionVks = new()
    {
        0x0D, 0x20, 0x09, 0x08, 0x2E, 0x1B,
        0x26, 0x28, 0x25, 0x27, 0x24, 0x23, 0x21, 0x22, 0x2D,
        0x70, 0x71, 0x72, 0x73, 0x74, 0x75, 0x76, 0x77, 0x78, 0x79, 0x7A, 0x7B,
        0x7C, 0x7D, 0x7E, 0x7F, 0x80, 0x81, 0x82, 0x83,
        0x2C, 0x91, 0x13, 0x5D,
    };

    private const string LetterChars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";
    private const string DigitChars = "0123456789";
    private const string SymbolChars = "!@#$%^&*()_+-=[]{}|;:'\\\",.<>?/`~ ";

    private static bool IsModifier(uint vk) => ModifierVks.Contains(vk);

    private static bool IsFunction(uint vk) => FunctionVks.Contains(vk);

    private static string Classify(string name)
    {
        if (string.IsNullOrEmpty(name)) return "symbol";
        if (LetterChars.Contains(name[0])) return "letter";
        if (DigitChars.Contains(name[0])) return "digit";
        if (SymbolChars.Contains(name[0])) return "symbol";
        return "function";
    }

    private string KeyName(uint vk, uint scan, uint flags)
    {
        if (NamedKeys.TryGetValue(vk, out var named)) return named;
        if (vk is >= 0x70 and <= 0x83) return "f" + (vk - 0x6F);
        if (vk is >= 0x84 and <= 0x93) return "f" + (vk - 0x6F);
        var ch = CharFromVk(vk, scan, flags);
        return ch ?? "";
    }

    /// 键名 → 字符:键盘状态由钩子线程自维护(钩子线程不消费键盘消息,GetKeyboardState 拿不到真实状态)。
    private string? CharFromVk(uint vk, uint scan, uint flags)
    {
        try
        {
            var state = new byte[256];
            BuildKeyState(state);
            // 扩展键(方向键/小键盘 Enter/右 Ctrl 等)扫描码需带扩展位
            var scanCode = (flags & LlkhfExtended) != 0 ? scan | 0x100 : scan;
            var layout = GetKeyboardLayout(0);
            var sb = new StringBuilder(8);
            var len = ToUnicodeEx(vk, scanCode, state, sb, sb.Capacity, 0, layout);
            if (len < 0)
            {
                // 死键:再调一次清掉死键状态,否则下一次会拿到上一次的组合结果
                ToUnicodeEx(vk, scanCode, state, sb, sb.Capacity, 0, layout);
                return null;
            }
            if (len < 1) return null;
            var ch = sb.ToString(0, 1);
            // ToUnicodeEx 不认 lpKeyState 的 CapsLock 位(传了还会翻转系统 CapsLock 状态),
            // 故 CapsLock 由钩子自行跟踪,拿到字符后反相大小写
            if (_capsLock) ch = InvertCase(ch);
            return ch;
        }
        catch
        {
            return null;
        }
    }

    /// 大小写反相(仅字母)。
    private static string InvertCase(string ch)
    {
        if (ch.Length != 1) return ch;
        var c = ch[0];
        if (char.IsLower(c)) return char.ToUpperInvariant(c).ToString();
        if (char.IsUpper(c)) return char.ToLowerInvariant(c).ToString();
        return ch;
    }

    /// 组装键盘状态数组:高位置 1 表示该键按下(ToUnicodeEx 据此还原 Shift / AltGr)。
    /// 只放 Shift/Ctrl/Alt:开关键位(Caps/Num)传给 ToUnicodeEx 会翻转系统状态,不可用。
    private void BuildKeyState(byte[] state)
    {
        Array.Clear(state);
        if (_lShift || _rShift)
        {
            state[0x10] = 0x80;
            state[0xA0] = 0x80;
            state[0xA1] = 0x80;
        }
        if (_lCtrl || _rCtrl)
        {
            state[0x11] = 0x80;
            state[0xA2] = 0x80;
            state[0xA3] = 0x80;
        }
        if (_lAlt || _rAlt)
        {
            state[0x12] = 0x80;
            state[0xA4] = 0x80;
            state[0xA5] = 0x80;
        }
    }

    /// 维护修饰键状态(仅钩子线程访问)。
    /// 通用码(0x10/0x11/0x12)无法区分左右,按下与松开都同步到两侧。
    private void UpdateModifierState(uint vk, bool isDown)
    {
        switch (vk)
        {
            case 0x10: _lShift = isDown; _rShift = isDown; break;
            case 0xA0: _lShift = isDown; break;
            case 0xA1: _rShift = isDown; break;
            case 0x11: _lCtrl = isDown; _rCtrl = isDown; break;
            case 0xA2: _lCtrl = isDown; break;
            case 0xA3: _rCtrl = isDown; break;
            case 0x12: _lAlt = isDown; _rAlt = isDown; break;
            case 0xA4: _lAlt = isDown; break;
            case 0xA5: _rAlt = isDown; break;
            case 0x14: if (isDown) _capsLock = !_capsLock; break;
        }
    }

    private static readonly double StopwatchFrequency = System.Diagnostics.Stopwatch.Frequency;

    // ──── Win32 ────
    private delegate nint HookDelegate(int nCode, nint wParam, nint lParam);

    [StructLayout(LayoutKind.Sequential)]
    private struct KbdLlHookStruct
    {
        public uint vkCode;
        public uint scanCode;
        public uint flags;
        public uint time;
        public nint dwExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MouseLlHookStruct
    {
        public int ptX;
        public int ptY;
        public int mouseData;
        public uint flags;
        public uint time;
        public nint dwExtraInfo;
    }

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern nint SetWindowsHookExW(int idHook, HookDelegate lpfn, nint hMod, uint dwThreadId);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool UnhookWindowsHookEx(nint hhk);

    [DllImport("user32.dll")]
    private static extern nint CallNextHookEx(nint hhk, int nCode, nint wParam, nint lParam);

    [DllImport("user32.dll")]
    private static extern int GetMessageW(out Msg lpMsg, nint hWnd, uint wMsgFilterMin, uint wMsgFilterMax);

    [DllImport("user32.dll")]
    private static extern bool PostThreadMessage(uint idThread, uint msg, nint wParam, nint lParam);

    [DllImport("kernel32.dll")]
    private static extern uint GetCurrentThreadId();

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    private static extern nint GetModuleHandleW(string? lpModuleName);

    [DllImport("user32.dll")]
    private static extern nint GetKeyboardLayout(uint idThread);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int ToUnicodeEx(uint wVirtKey, uint wScanCode, byte[] lpKeyState,
        StringBuilder lpCharBuffer, int nCharCount, uint wFlags, nint lpKeyLayout);

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
