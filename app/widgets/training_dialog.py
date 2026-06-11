"""
训练配置弹窗 — 非模态，允许边训练边操作数据集
"""
from datetime import datetime

from PyQt5.QtCore import Qt, pyqtSignal, QMetaObject, Q_ARG
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QSpinBox, QDoubleSpinBox, QComboBox,
    QLabel, QLineEdit, QTextEdit, QProgressBar, QGroupBox, QMessageBox,
)
from PyQt5.QtGui import QFont

from app.widgets.styles import MAIN_STYLE


class TrainingDialog(QDialog):
    """训练配置 & 进度弹窗（非模态）"""

    start_requested = pyqtSignal(dict)
    stop_requested = pyqtSignal()
    _done_signal = pyqtSignal(bool, str)  # 线程安全回调

    def __init__(self, dtype: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("训练配置")
        self.setMinimumWidth(620)
        self.setStyleSheet(MAIN_STYLE)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setModal(False)

        self._dtype = dtype
        self._started = False

        self._init_ui()
        self._done_signal.connect(self._on_done_slot)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)

        # ---- 参数区（左右双列） ----
        param_group = QGroupBox("训练参数")
        param_root = QHBoxLayout(param_group)

        # --- 左列：数值参数 ---
        left_form = QFormLayout()

        self.name_edit = QLineEdit(
            f"{self._dtype}_model_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        self.name_edit.setStyleSheet(
            "QLineEdit { color: #89b4fa; font-weight: bold; background-color: #313244;"
            "border: 1px solid #45475a; border-radius: 4px; padding: 4px 8px; }"
        )
        left_form.addRow("模型名称:", self.name_edit)

        self.epochs_spin = QSpinBox()
        self.epochs_spin.setRange(1, 2000)
        self.epochs_spin.setValue(20)
        self.epochs_spin.setToolTip("训练轮数，建议 50-300")
        left_form.addRow("Epochs:", self.epochs_spin)

        self.imgsz_spin = QSpinBox()
        self.imgsz_spin.setRange(320, 1920)
        self.imgsz_spin.setSingleStep(32)
        self.imgsz_spin.setValue(640)
        self.imgsz_spin.setToolTip("输入图像尺寸，需为 32 的倍数")
        left_form.addRow("Image Size:", self.imgsz_spin)

        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(1, 128)
        self.batch_spin.setValue(16)
        self.batch_spin.setToolTip("批次大小，显存不足请调小")
        left_form.addRow("Batch Size:", self.batch_spin)

        self.lr_spin = QDoubleSpinBox()
        self.lr_spin.setRange(0.0001, 0.1)
        self.lr_spin.setDecimals(5)
        self.lr_spin.setSingleStep(0.001)
        self.lr_spin.setValue(0.005)
        self.lr_spin.setToolTip("初始学习率")
        left_form.addRow("Learning Rate:", self.lr_spin)

        param_root.addLayout(left_form)

        # --- 分隔线 ---
        sep = QLabel("")
        sep.setFixedWidth(1)
        sep.setStyleSheet("background-color: #45475a;")
        sep.setSizePolicy(sep.sizePolicy().horizontalPolicy(),
                          sep.sizePolicy().Expanding)
        param_root.addWidget(sep)

        # --- 右列：下拉选择 ---
        right_form = QFormLayout()

        self.optimizer_combo = QComboBox()
        optimizers = ["auto", "SGD", "Adam", "AdamW", "Adamax", "NAdam", "RAdam", "RMSProp"]
        self.optimizer_combo.addItems(optimizers)
        self.optimizer_combo.setCurrentText("auto")
        self.optimizer_combo.setToolTip("优化器，auto 会自动选择")
        right_form.addRow("Optimizer:", self.optimizer_combo)

        self.pretrain_combo = QComboBox()
        pretrains = ["yolo11n.pt", "yolo11s.pt", "yolo11m.pt", "yolo11l.pt", "yolo11x.pt"]
        self.pretrain_combo.addItems(pretrains)
        self.pretrain_combo.setCurrentText("yolo11n.pt")
        self.pretrain_combo.setToolTip("预训练模型（n/s/m/l/x 从小到大）")
        right_form.addRow("Pretrained:", self.pretrain_combo)

        self.val_split_spin = QSpinBox()
        self.val_split_spin.setRange(0, 50)
        self.val_split_spin.setSuffix("%")
        self.val_split_spin.setValue(20)
        self.val_split_spin.setToolTip("验证集占比（0% 则 train/val 使用同一数据）")
        right_form.addRow("Val Split:", self.val_split_spin)

        param_root.addLayout(right_form)

        layout.addWidget(param_group)

        # ---- 进度区 ----
        progress_group = QGroupBox("训练进度")
        progress_layout = QVBoxLayout(progress_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(0)
        self.progress_bar.setVisible(False)
        progress_layout.addWidget(self.progress_bar)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 11))
        self.log_text.setMaximumHeight(200)
        self.log_text.setStyleSheet(
            "QTextEdit { background-color: #11111b; color: #a6adc8; border: 1px solid #313244; }"
        )
        progress_layout.addWidget(self.log_text)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setVisible(False)
        progress_layout.addWidget(self.result_label)

        layout.addWidget(progress_group)

        # ---- 按钮 ----
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("开始训练")
        self.start_btn.setObjectName("primary_btn")
        self.start_btn.clicked.connect(self._on_start)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("停止训练")
        self.stop_btn.setObjectName("danger_btn")
        self.stop_btn.setVisible(False)
        self.stop_btn.clicked.connect(self._on_stop)
        btn_layout.addWidget(self.stop_btn)

        btn_layout.addStretch()
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self._on_close)
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)

    # ---- 对外接口 ----

    @property
    def model_name(self) -> str:
        return self.name_edit.text().strip()

    def get_params(self) -> dict:
        return {
            "name": self.model_name,
            "epochs": self.epochs_spin.value(),
            "imgsz": self.imgsz_spin.value(),
            "batch": self.batch_spin.value(),
            "lr0": self.lr_spin.value(),
            "optimizer": self.optimizer_combo.currentText(),
            "val_split": self.val_split_spin.value() / 100,
            "pretrained": self.pretrain_combo.currentText(),
        }

    def set_params_enabled(self, enabled: bool) -> None:
        self.name_edit.setEnabled(enabled)
        self.epochs_spin.setEnabled(enabled)
        self.imgsz_spin.setEnabled(enabled)
        self.batch_spin.setEnabled(enabled)
        self.lr_spin.setEnabled(enabled)
        self.optimizer_combo.setEnabled(enabled)
        self.val_split_spin.setEnabled(enabled)
        self.pretrain_combo.setEnabled(enabled)

    def append_log(self, msg: str) -> None:
        """线程安全地追加日志（从训练线程调用）"""
        QMetaObject.invokeMethod(
            self.log_text, "append", Qt.QueuedConnection,
            Q_ARG(str, msg)
        )

    def set_done(self, success: bool, msg: str) -> None:
        """线程安全 — 从任意线程调用"""
        self._done_signal.emit(success, msg)

    def _on_done_slot(self, success: bool, msg: str) -> None:
        """在主线程中执行 UI 更新"""
        self.progress_bar.setVisible(False)
        self._started = False
        self.set_params_enabled(True)
        self.start_btn.setEnabled(True)
        self.start_btn.setText("重新训练")
        self.stop_btn.setVisible(False)
        if success:
            self.result_label.setStyleSheet(
                "color: #a6e3a1; font-weight: bold; font-size: 14px;"
            )
        else:
            self.result_label.setStyleSheet(
                "color: #f38ba8; font-weight: bold; font-size: 14px;"
            )
        self.result_label.setText(msg)
        self.result_label.setVisible(True)

    # ---- 内部 ----

    def _on_start(self) -> None:
        self._started = True
        self.start_btn.setEnabled(False)
        self.stop_btn.setVisible(True)
        self.set_params_enabled(False)
        self.progress_bar.setVisible(True)
        self.log_text.clear()
        self.result_label.setVisible(False)
        self.start_requested.emit(self.get_params())

    def _on_stop(self) -> None:
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("停止中...")
        self.stop_requested.emit()

    def _on_close(self) -> None:
        if self._started:
            QMessageBox.warning(self, "提示", "训练进行中，请先停止训练再关闭")
            return
        super().close()

    def closeEvent(self, event) -> None:
        if self._started:
            QMessageBox.warning(self, "提示", "训练进行中，请先停止训练再关闭")
            event.ignore()
        else:
            event.accept()
