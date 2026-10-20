using KeyNote.App.Controls;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace KeyNote.App.Views;

/// 热力图页(Page 3):GitHub 风格年度热力图。
public sealed partial class HeatmapPage : Page, IRefreshable
{
    public HeatmapPage()
    {
        InitializeComponent();
        Header.RefreshRequested += (_, _) => RefreshData();
        Loaded += (_, _) => RefreshData();
    }

    public void RefreshData()
    {
        try
        {
            var days = App.Instance.Settings.HeatmapDays;
            Header.Subtitle = $"最近 {days} 天的按键分布";

            Heatmap.Days = days;
            Heatmap.Refresh();
            YearTitle.Text = $"过去 {days} 天 · 每日贡献";
            YearSummary.Text = Heatmap.Summary;
        }
        catch (Exception ex)
        {
            Core.Utils.CrashLog.Write("heatmap.refresh", ex);
        }
    }
}
