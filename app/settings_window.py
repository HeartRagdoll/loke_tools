"""
设置窗口 — 盒子模型 & 属性模型选择与导入 & 截屏区域编辑
"""
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QPushButton, QSpinBox, QDoubleSpinBox,
    QFileDialog, QMessageBox,
)

from app.utils.config import ConfigManager
from app.utils.paths import get_models_dir
from app.widgets.styles import MAIN_STYLE
from app.utils.logger import logger


class SettingsWindow(QDialog):
    """模型设置对话框

    用法:
        dialog = SettingsWindow(config=config_manager, overlay=result_overlay, parent=self)
        if dialog.exec_() == SettingsWindow.Accepted:
            box_path = dialog.selected_model_box
            attr_path = dialog.selected_model_attr
    """

    def __init__(self, config: ConfigManager = None, overlay: "ResultOverlay" = None,
                 capture=None, detector=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置 - 模型管理")
        self.setMinimumSize(520, 450)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet(MAIN_STYLE)

        self._config = config or ConfigManager()
        self._overlay = overlay
        self._capture = capture
        self._detector = detector
        self._models_dir = get_models_dir()
        self._selected_box: str = ""
        self._selected_attr: str = ""
        self._region_editor = None
        self._want_dataset = False  # 用户点击了"模型训练"按钮

        self._init_ui()

    @property
    def selected_model_box(self) -> str:
        return self._selected_box

    @property
    def selected_model_attr(self) -> str:
        return self._selected_attr

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(16)
        root.setContentsMargins(24, 20, 24, 20)

        # ---- 盒子识别模型 ----
        box_label = QLabel("盒子识别模型")
        box_label.setObjectName("title")
        root.addWidget(box_label)

        box_row = QHBoxLayout()
        box_row.setSpacing(8)
        self.box_combo = QComboBox()
        self.box_combo.setMinimumWidth(300)
        box_row.addWidget(self.box_combo, 1)

        import_box_btn = QPushButton("导入模型")
        import_box_btn.setObjectName("primary_btn")
        import_box_btn.clicked.connect(lambda: self._import_model("box"))
        box_row.addWidget(import_box_btn)

        box_row.addWidget(QLabel("阈值"))
        self._box_conf_spin = QDoubleSpinBox()
        self._box_conf_spin.setRange(0.1, 1.0)
        self._box_conf_spin.setSingleStep(0.05)
        self._box_conf_spin.setDecimals(2)
        self._box_conf_spin.setValue(self._config.box_conf_threshold)
        self._box_conf_spin.setFixedWidth(70)
        box_row.addWidget(self._box_conf_spin)
        root.addLayout(box_row)

        # ---- 属性识别模型 ----
        attr_label = QLabel("属性识别模型（可选）")
        attr_label.setObjectName("title")
        root.addWidget(attr_label)

        attr_row = QHBoxLayout()
        attr_row.setSpacing(8)
        self.attr_combo = QComboBox()
        self.attr_combo.setMinimumWidth(300)
        attr_row.addWidget(self.attr_combo, 1)

        import_attr_btn = QPushButton("导入模型")
        import_attr_btn.setObjectName("primary_btn")
        import_attr_btn.clicked.connect(lambda: self._import_model("attr"))
        attr_row.addWidget(import_attr_btn)

        attr_row.addWidget(QLabel("阈值"))
        self._attr_conf_spin = QDoubleSpinBox()
        self._attr_conf_spin.setRange(0.1, 1.0)
        self._attr_conf_spin.setSingleStep(0.05)
        self._attr_conf_spin.setDecimals(2)
        self._attr_conf_spin.setValue(self._config.attr_conf_threshold)
        self._attr_conf_spin.setFixedWidth(70)
        attr_row.addWidget(self._attr_conf_spin)
        root.addLayout(attr_row)

        # ---- 截屏识别区域 ----
        region_label = QLabel("截屏识别区域")
        region_label.setObjectName("title")
        root.addWidget(region_label)

        region_row = QHBoxLayout()
        region_row.setSpacing(8)

        self.region_status = QLabel("全屏")
        self.region_status.setStyleSheet("color: #6c7086;")
        region_row.addWidget(self.region_status)

        region_row.addStretch()

        self.edit_region_btn = QPushButton("编辑识别区域")
        self.edit_region_btn.setToolTip("拖拽蓝色区域框来调整截屏范围")
        self.edit_region_btn.clicked.connect(self._on_edit_region)
        region_row.addWidget(self.edit_region_btn)

        self.clear_region_btn = QPushButton("重置全屏")
        self.clear_region_btn.clicked.connect(self._on_clear_region)
        region_row.addWidget(self.clear_region_btn)

        root.addLayout(region_row)
        self._update_region_status()

        # ---- 检测间隔 ----
        detect_label = QLabel("检测频率")
        detect_label.setObjectName("title")
        root.addWidget(detect_label)

        detect_row = QHBoxLayout()
        detect_row.setSpacing(8)
        detect_row.addWidget(QLabel("每隔"))
        self._detect_spin = QSpinBox()
        self._detect_spin.setRange(100, 10000)
        self._detect_spin.setSingleStep(100)
        self._detect_spin.setSuffix(" ms")
        self._detect_spin.setValue(self._config.detect_interval_ms)
        detect_row.addWidget(self._detect_spin)
        detect_row.addWidget(QLabel("检测一次"))
        detect_row.addStretch()
        root.addLayout(detect_row)

        # ---- 隐藏延迟 ----
        hide_label = QLabel("浮窗隐藏延迟")
        hide_label.setObjectName("title")
        root.addWidget(hide_label)

        hide_row = QHBoxLayout()
        hide_row.setSpacing(8)
        hide_row.addWidget(QLabel("显示"))
        self._hide_spin = QSpinBox()
        self._hide_spin.setRange(1000, 120000)
        self._hide_spin.setSingleStep(1000)
        self._hide_spin.setSuffix(" ms")
        self._hide_spin.setValue(self._config.hide_interval_ms)
        hide_row.addWidget(self._hide_spin)
        hide_row.addWidget(QLabel("后自动隐藏"))
        hide_row.addStretch()
        root.addLayout(hide_row)

        # 弹性空间
        root.addStretch()

        # ---- 底部按钮 ----
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        train_btn = QPushButton("模型训练")
        train_btn.setToolTip("打开数据集管理与训练窗口")
        train_btn.clicked.connect(self._on_train)
        btn_row.addWidget(train_btn)

        btn_row.addStretch()

        save_btn = QPushButton("保存")
        save_btn.setObjectName("primary_btn")
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        root.addLayout(btn_row)

        # 刷新下拉框
        self._refresh_combos()
        self._record_initial_values()

    # ---- 内部 -----------------------------------------------------

    def _record_initial_values(self) -> None:
        """记录打开时的初始值，用于判断是否有修改"""
        self._initial_box_idx = self.box_combo.currentIndex()
        self._initial_attr_idx = self.attr_combo.currentIndex()
        self._initial_detect_ms = self._detect_spin.value()
        self._initial_hide_ms = self._hide_spin.value()
        self._initial_box_conf = self._box_conf_spin.value()
        self._initial_attr_conf = self._attr_conf_spin.value()

    def _is_dirty(self) -> bool:
        """判断用户是否修改了任何设置"""
        return (
            self.box_combo.currentIndex() != self._initial_box_idx
            or self.attr_combo.currentIndex() != self._initial_attr_idx
            or self._detect_spin.value() != self._initial_detect_ms
            or self._hide_spin.value() != self._initial_hide_ms
            or self._box_conf_spin.value() != self._initial_box_conf
            or self._attr_conf_spin.value() != self._initial_attr_conf
        )

    def closeEvent(self, event) -> None:
        """关闭窗口时，如有修改则提示保存"""
        if self._is_dirty():
            reply = QMessageBox.question(
                self, "未保存的修改",
                "设置有修改，是否保存？",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self._on_save()
                event.accept()
                return
            else:
                self.reject()
                return
        self.reject()
        event.accept()

    def _refresh_combos(self) -> None:
        """刷新模型下拉框，选中上次使用的模型"""
        models_dir = get_models_dir()

        # 盒子模型
        box_dir = models_dir / "box"
        box_dir.mkdir(parents=True, exist_ok=True)
        self.box_combo.blockSignals(True)
        self.box_combo.clear()
        self.box_combo.addItem("-- 选择盒子模型 --")
        for pt_file in sorted(box_dir.rglob("*.pt")):
            self.box_combo.addItem(pt_file.name, str(pt_file))
        last_box = self._config.last_model_box
        if last_box:
            idx = self.box_combo.findText(last_box)
            if idx >= 0:
                self.box_combo.setCurrentIndex(idx)
        self.box_combo.blockSignals(False)

        # 属性模型
        attr_dir = models_dir / "attr"
        attr_dir.mkdir(parents=True, exist_ok=True)
        self.attr_combo.blockSignals(True)
        self.attr_combo.clear()
        self.attr_combo.addItem("-- 选择属性模型 --")
        for pt_file in sorted(attr_dir.rglob("*.pt")):
            self.attr_combo.addItem(pt_file.name, str(pt_file))
        last_attr = self._config.last_model_attr
        if last_attr:
            idx = self.attr_combo.findText(last_attr)
            if idx >= 0:
                self.attr_combo.setCurrentIndex(idx)
        self.attr_combo.blockSignals(False)

    def _import_model(self, mtype: str) -> None:
        """导入模型文件到 models/{mtype}/ 目录"""
        path, _ = QFileDialog.getOpenFileName(
            self, f"导入{mtype}模型", "",
            "PyTorch 模型 (*.pt *.pth);;所有文件 (*)",
        )
        if not path:
            return

        src = Path(path)
        dst_dir = self._models_dir / mtype
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / src.name

        if dst.exists():
            reply = QMessageBox.question(
                self, "文件已存在",
                f"模型 '{src.name}' 已存在，是否覆盖？",
            )
            if reply != QMessageBox.Yes:
                return

        try:
            import shutil
            shutil.copy2(str(src), str(dst))
            self._refresh_combos()
            # 自动选中刚导入的模型
            combo = self.box_combo if mtype == "box" else self.attr_combo
            idx = combo.findText(dst.name)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            QMessageBox.information(self, "导入成功", f"模型已导入: {dst.name}")
        except Exception as e:
            QMessageBox.warning(self, "导入失败", str(e))

    # ---- 截屏区域 -------------------------------------------------

    def _update_region_status(self) -> None:
        region = self._config.capture_region
        if region and all(k in region for k in ("x", "y", "w", "h")):
            self.region_status.setText(
                f"({region['x']}, {region['y']}) {region['w']}x{region['h']}"
            )
        else:
            self.region_status.setText("全屏")

    def _on_edit_region(self) -> None:
        """打开截屏区域编辑器"""
        from app.widgets.region_editor import RegionEditor

        # 隐藏设置窗口，显示浮窗和区域编辑器
        self.hide()
        if self._overlay and self._overlay.isVisible():
            pass  # 浮窗已显示
        elif self._overlay:
            self._overlay.show_placeholder()

        # 解锁浮窗，允许拖拽调整位置
        if self._overlay:
            self._overlay.set_locked(False)

        self._region_editor = RegionEditor(
            region=self._config.capture_region,
            overlay=self._overlay,
        )
        self._region_editor.confirmed.connect(self._on_region_confirmed)
        self._region_editor.cancelled.connect(self._on_region_cancelled)
        self._region_editor.show()

    def _on_clear_region(self) -> None:
        self._config.capture_region = None
        self._update_region_status()

    def _on_region_confirmed(self, region: dict) -> None:
        self._config.capture_region = region
        # 锁定浮窗并保存位置
        if self._overlay:
            self._overlay.set_locked(True)
            if self._overlay.isVisible():
                pos = self._overlay.pos()
                sz = self._overlay.size()
                self._config.overlay_geometry = {
                    "x": pos.x(), "y": pos.y(),
                    "w": sz.width(), "h": sz.height(),
                    "locked": True,
                }
        self._update_region_status()
        self._region_editor = None
        self.show()
        self.raise_()

    def _on_region_cancelled(self) -> None:
        # 恢复浮窗锁定状态
        if self._overlay:
            self._overlay.set_locked(True)
        self._region_editor = None
        self.show()
        self.raise_()

    def _on_train(self) -> None:
        """打开数据集管理窗口 — 先保存配置再跳转"""
        self._want_dataset = True
        self._on_save()

    def _on_save(self) -> None:
        """保存选中的模型路径和间隔配置"""
        box_idx = self.box_combo.currentIndex()
        if box_idx > 0:
            self._selected_box = self.box_combo.itemData(box_idx)
        else:
            self._selected_box = ""

        attr_idx = self.attr_combo.currentIndex()
        if attr_idx > 0:
            self._selected_attr = self.attr_combo.itemData(attr_idx)
        else:
            self._selected_attr = ""

        # 保存并应用检测 / 隐藏间隔
        detect_ms = self._detect_spin.value()
        hide_ms = self._hide_spin.value()
        self._config.detect_interval_ms = detect_ms
        self._config.hide_interval_ms = hide_ms

        if self._capture:
            self._capture.set_interval(detect_ms / 1000.0)
        if self._overlay:
            self._overlay.set_hide_delay(hide_ms)

        # 保存并应用置信度阈值
        box_conf = self._box_conf_spin.value()
        attr_conf = self._attr_conf_spin.value()
        self._config.box_conf_threshold = box_conf
        self._config.attr_conf_threshold = attr_conf

        if self._detector:
            self._detector.box_conf = box_conf
            self._detector.attr_conf = attr_conf

        self.accept()
