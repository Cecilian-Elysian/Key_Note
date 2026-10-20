using KeyNote.App.Controls;
using KeyNote.Core.Storage;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace KeyNote.App.Views;

/// 常用按键页(Page 4):Top 10 按键次数横向条形图。
public sealed partial class TopKeysPage : Page, IRefreshable
{
    public TopKeysPage()
    {
        InitializeComponent();
        Header.RefreshRequested += (_, _) => RefreshData();
        Loaded += (_, _) => RefreshData();
    }

    public void RefreshData()
    {
        try
        {
            var data = KeyNoteDb.TopKeys(10);
            Chart.SetData(data);
            Summary.Text = data.Count > 0 ? $"最高 {data[0].Key} × {data[0].Count:N0}" : "";
        }
        catch (Exception ex)
        {
            Core.Utils.CrashLog.Write("topkeys.refresh", ex);
        }
    }
}
