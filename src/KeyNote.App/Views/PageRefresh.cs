using KeyNote.App.Controls;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace KeyNote.App.Views;

/// 页面刷新接线:统一「页头刷新 + 首次加载 + 异常落盘」模板。
/// 用组合而非继承(XAML 生成的页面分部类固定以 Page 为基类,无法换基类)。
public static class PageRefresh
{
    /// 接线:页头刷新钮 + 页面 Loaded → 触发 load;异常统一落 crash log。
    public static void Wire(Page page, PageHeader? header, Action load)
    {
        EventHandler<RoutedEventArgs>? headerHandler = null;
        RoutedEventHandler? loadedHandler = null;

        void Safe()
        {
            try
            {
                load();
            }
            catch (Exception ex)
            {
                Core.Utils.CrashLog.Write($"{page.GetType().Name}.refresh", ex);
            }
        }

        if (header is not null)
        {
            headerHandler = (_, _) => Safe();
            header.RefreshRequested += headerHandler;
        }
        loadedHandler = (_, _) => Safe();
        page.Loaded += loadedHandler;
        page.Unloaded += (_, _) =>
        {
            if (header is not null && headerHandler is not null) header.RefreshRequested -= headerHandler;
            page.Loaded -= loadedHandler;
        };
    }
}
