using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;

namespace KeyNote.App.Controls;

/// 图表无障碍摘要:为纯绘制的 Canvas 提供读屏文本(否则读屏只会念出空白)。
public static class ChartAccessibility
{
    /// 设置图表的无障碍名称与摘要描述。
    public static void Apply(FrameworkElement? element, string name, string description)
    {
        if (element is null) return;
        AutomationProperties.SetName(element, name);
        AutomationProperties.SetHelpText(element, description);
    }
}
