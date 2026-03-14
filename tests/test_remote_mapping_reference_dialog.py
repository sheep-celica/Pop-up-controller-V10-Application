from __future__ import annotations

from PySide6.QtGui import QImage

from popup_controller.ui.remote_mapping_reference_dialog import RemoteMappingReferenceDialog


def test_remote_mapping_reference_dialog_scales_image_and_fixes_window_size(qtbot, tmp_path) -> None:
    image_path = tmp_path / "remote_mapping.png"
    image = QImage(200, 100, QImage.Format.Format_ARGB32)
    image.fill(0xFF336699)
    assert image.save(str(image_path)) is True

    dialog = RemoteMappingReferenceDialog(image_path)
    qtbot.addWidget(dialog)

    pixmap = dialog.image_label.pixmap()
    assert pixmap is not None
    assert pixmap.width() == 100
    assert pixmap.height() == 50
    assert dialog.minimumWidth() == dialog.maximumWidth()
    assert dialog.minimumHeight() == dialog.maximumHeight()
