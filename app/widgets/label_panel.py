"""
右侧标签编辑面板 - 三个区域的标签下拉 + 添加/删除 + 底部保存按钮
"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QComboBox,
    QPushButton, QLabel, QMessageBox, QInputDialog, QScrollArea,
)
from PyQt5.QtGui import QColor

from app.utils.config import ConfigManager

REGION_COLORS = {
    "top": QColor(243, 139, 168),
    "middle": QColor(249, 226, 175),
    "bottom": QColor(166, 227, 161),
}

REGION_NAMES = {"top": "上部区域", "middle": "中部区域", "bottom": "下部区域"}


class RegionEditGroup(QGroupBox):
    """单个区域的标签选择组（不含编辑按钮，编辑统一由顶部栏控制）"""

    add_label_request = pyqtSignal(str)  # region
    del_label_request = pyqtSignal(str)  # region

    def __init__(self, region: str, parent=None):
        self._region = region
        super().__init__(REGION_NAMES.get(region, region), parent)
        self.setStyleSheet(
            f"QGroupBox {{ color: {REGION_COLORS.get(region, QColor('#cdd6f4')).name()}; }}"
        )

        layout = QVBoxLayout(self)

        # 标签下拉框
        top_row = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.setMinimumWidth(80)
        top_row.addWidget(self.combo, 1)
        layout.addLayout(top_row)

        # 添加 / 删除
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        small_btn_style = (
            "QPushButton { background-color: #45475a; color: #cdd6f4; border: none;"
            "border-radius: 4px; padding: 0px; font-size: 16px; font-weight: bold; }"
            "QPushButton:hover { background-color: #585b70; }"
        )
        self.add_btn = QPushButton("+")
        self.add_btn.setFixedSize(28, 28)
        self.add_btn.setStyleSheet(small_btn_style)
        self.add_btn.setToolTip(f"添加{REGION_NAMES.get(region, region)}标签")
        self.add_btn.clicked.connect(lambda: self.add_label_request.emit(region))
        btn_row.addWidget(self.add_btn)

        self.del_btn = QPushButton("-")
        self.del_btn.setFixedSize(28, 28)
        self.del_btn.setStyleSheet(small_btn_style)
        self.del_btn.setToolTip(f"删除当前{REGION_NAMES.get(region, region)}标签")
        self.del_btn.clicked.connect(lambda: self.del_label_request.emit(region))
        btn_row.addWidget(self.del_btn)
        layout.addLayout(btn_row)

    def set_labels(self, labels: list) -> None:
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItems(labels)
        self.combo.blockSignals(False)

    @property
    def current_label(self) -> str:
        return self.combo.currentText()

    def set_current(self, label: str, block_signal: bool = False) -> None:
        if not label:
            self.combo.setCurrentIndex(-1)  # 清空选中
            return
        if block_signal:
            self.combo.blockSignals(True)
        idx = self.combo.findText(label)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)
        if block_signal:
            self.combo.blockSignals(False)

    def set_editable(self, enabled: bool) -> None:
        """控制下拉框的启用/禁用"""
        self.combo.setEnabled(enabled)

    def set_buttons_visible(self, visible: bool) -> None:
        """控制 +/- 按钮的显隐"""
        self.add_btn.setVisible(visible)
        self.del_btn.setVisible(visible)


class LabelPanel(QWidget):
    """数据集标注标签面板 — 三区域标签选择 + 底部保存按钮"""

    label_changed = pyqtSignal(str, str)  # region, label_name
    save_clicked = pyqtSignal()
    next_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panel")
        self._config = ConfigManager()
        self._regions_visible = True

        self._build_ui()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # 标题
        title = QLabel("标注管理")
        title.setObjectName("title")
        main_layout.addWidget(title)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background: transparent;")
        self._scroll_layout = QVBoxLayout(scroll_widget)

        # 三个区域编辑组
        self._region_groups = {}
        for region in ["top", "middle", "bottom"]:
            group = RegionEditGroup(region)
            group.set_labels(self._config.attr_labels.get(region, []))
            group.add_label_request.connect(self._on_add_label)
            group.del_label_request.connect(self._on_del_label)
            group.combo.currentTextChanged.connect(
                lambda text, r=region: self.label_changed.emit(r, text)
            )
            self._region_groups[region] = group
            self._scroll_layout.addWidget(group)

        self._scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll, 1)

        # 底部保存按钮 + 下一张
        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("保存标签")
        self.save_btn.setObjectName("success_btn")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save_clicked.emit)
        btn_row.addWidget(self.save_btn, 1)

        self.next_btn = QPushButton("下一张")
        self.next_btn.setObjectName("primary_btn")
        self.next_btn.clicked.connect(self.next_clicked.emit)
        btn_row.addWidget(self.next_btn)
        main_layout.addLayout(btn_row)

    def set_mode(self, mode: str) -> None:
        """切换模式 box/attr — box 时显示标签下拉（只读、隐藏按钮），attr 时可编辑"""
        self._mode = mode
        editable = (mode == "attr")
        self._regions_visible = True
        for group in self._region_groups.values():
            group.setVisible(True)
            group.set_editable(editable)
            group.set_buttons_visible(editable)
        self.save_btn.setVisible(editable)
        self.next_btn.setVisible(editable)

    def set_regions_visible(self, visible: bool) -> None:
        """手动控制区域标签面板的显隐"""
        self._regions_visible = visible
        for group in self._region_groups.values():
            group.setVisible(visible)

    def get_labels(self) -> dict:
        return {
            region: [self._region_groups[region].combo.itemText(i)
                     for i in range(self._region_groups[region].combo.count())]
            for region in self._region_groups
        }

    def set_current_selections(self, selections: dict, block_signal: bool = False) -> None:
        """设置各区域当前选中标签"""
        for region, label in selections.items():
            if region in self._region_groups:
                self._region_groups[region].set_current(label, block_signal=block_signal)

    @property
    def regions_visible(self) -> bool:
        return self._regions_visible

    # ---- 添加 / 删除标签 ----

    def _on_add_label(self, region: str) -> None:
        text, ok = QInputDialog.getText(
            self, f"添加{REGION_NAMES.get(region, region)}标签", "请输入标签名称:"
        )
        if ok and text.strip():
            label = text.strip()
            group = self._region_groups[region]
            items = [group.combo.itemText(i) for i in range(group.combo.count())]
            if label not in items:
                items.append(label)
                group.set_labels(items)
                group.set_current(label)
                self._persist_labels()

    def _on_del_label(self, region: str) -> None:
        group = self._region_groups[region]
        label = group.current_label
        if not label:
            return
        reply = QMessageBox.question(
            self, "确认删除", f"确定要删除标签 '{label}' 吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            items = [group.combo.itemText(i) for i in range(group.combo.count())]
            if label in items:
                items.remove(label)
                group.set_labels(items)
                self._persist_labels()

    def _persist_labels(self) -> None:
        """持久化当前所有标签到 config.json"""
        self._config.attr_labels = self.get_labels()
