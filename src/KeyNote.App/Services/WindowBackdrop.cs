using Microsoft.UI.Composition.SystemBackdrops;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media;

namespace KeyNote.App.Services;

/// 背景材质:Mica(Win11)→ Acrylic(Win10 1809+)→ 纯色,能力探测进程内缓存。
internal static class WindowBackdrop
{
    private static readonly bool _mica = Query(() => MicaController.IsSupported());
    private static readonly bool _acrylic = Query(() => DesktopAcrylicController.IsSupported());

    public static bool HasMaterial => _mica || _acrylic;

    /// 返回可挂到 Window.SystemBackdrop 的材质;null 表示回退纯色。
    public static SystemBackdrop? Create()
    {
        try
        {
            if (_mica) return new MicaBackdrop { Kind = MicaKind.Base };
            if (_acrylic) return new DesktopAcrylicBackdrop();
        }
        catch
        {
            // 探测通过但创建失败(驱动/会话异常):回退纯色
        }
        return null;
    }

    private static bool Query(Func<bool> probe)
    {
        try { return probe(); }
        catch { return false; }
    }
}
