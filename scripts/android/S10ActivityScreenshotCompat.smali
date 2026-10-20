# The removed Samsung API retains the existing preview-screenshot policy semantics.
.method public semSetDisablePreviewScreenshots(Z)V
    .registers 2

    invoke-virtual {p0, p1}, Landroid/app/Activity;->setDisablePreviewScreenshots(Z)V

    return-void
.end method
