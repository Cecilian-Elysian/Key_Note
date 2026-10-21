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
        PageRefresh.Wire(this, Header, RefreshData);
    }

    public void RefreshData()
    {
        // 合并大小写:与键盘热力图同口径,两页数字才对得上
        var data = KeyNoteDb.TopKeysMergedCase(10);
        Chart.SetData(data);
        Summary.Text = data.Count > 0 ? $"最高 {data[0].Key.ToUpperInvariant()} × {data[0].Count:N0}" : "";
    }
}
