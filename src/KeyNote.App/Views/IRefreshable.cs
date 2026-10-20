namespace KeyNote.App.Views;

/// 可刷新页面(自动刷新定时器只刷当前页)
public interface IRefreshable
{
    void RefreshData();
}
