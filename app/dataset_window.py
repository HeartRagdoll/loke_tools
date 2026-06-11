"""
数据集管理与训练窗口 — 两阶段标注：盒子定位 → 属性标注
"""
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QMainWindow, QPushButton, QComboBox, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QSplitter, QMessageBox, QFileDialog,
    QProgressBar, QStatusBar, QApplication, QSizePolicy,
)

from app.core.dataset import DatasetManager, LabelIO
from app.core.detector import TwoStageDetector
from app.core.trainer import YOLOTrainer
from app.widgets.image_canvas import ImageCanvas
from app.widgets.label_panel import LabelPanel
from app.widgets.styles import MAIN_STYLE, DATASET_WINDOW_STYLE
from app.utils.config import ConfigManager
from app.utils.paths import get_models_dir
from app.utils.logger import logger


# ---- OpenCV 中文路径安全读写 ----

def _imread(path: str) -> Optional[np.ndarray]:
    """cv2.imread 替代，支持中文路径"""
    try:
        data = np.fromfile(path, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        return img
    except Exception:
        return None


def _imwrite(path: str, img: np.ndarray) -> bool:
    """cv2.imwrite 替代，支持中文路径"""
    try:
        _, buf = cv2.imencode(Path(path).suffix, img)
        buf.tofile(path)
        return True
    except Exception:
        return False


class PredictThread(QThread):
    """预测线程 — 属性模型可选"""
    result_ready = pyqtSignal(dict)

    def __init__(self, image: np.ndarray, box_model_path: str,
                 attr_model_path: str = None,
                 box_conf: float = 0.8, attr_conf: float = 0.8):
        super().__init__()
        self.image = image
        self.box_model_path = box_model_path
        self.attr_model_path = attr_model_path
        self._box_conf = box_conf
        self._attr_conf = attr_conf

    def run(self) -> None:
        try:
            detector = TwoStageDetector(
                box_conf=self._box_conf, attr_conf=self._attr_conf)
            if not detector.load_box_model(self.box_model_path):
                self.result_ready.emit({"error": "盒子模型加载失败"})
                return
            if self.attr_model_path:
                if not detector.load_attr_model(self.attr_model_path):
                    self.result_ready.emit({"error": "属性模型加载失败"})
                    return
            result, _ = detector.process_image(self.image)
            self.result_ready.emit(result or {"error": "未检测到结果"})
        except Exception as e:
            self.result_ready.emit({"error": str(e)})


def _cleanup_training_artifacts(yaml_path: str) -> None:
    """清理训练生成的中间文件：data.yaml、split/ 目录、labels.cache"""
    yaml_file = Path(yaml_path)
    data_dir = yaml_file.parent

    # 删除 data.yaml
    if yaml_file.exists():
        yaml_file.unlink()

    # 删除 split/ 目录
    split_dir = data_dir / "split"
    if split_dir.exists():
        shutil.rmtree(split_dir)

    # 删除 labels.cache（可能在 data_dir 或子目录）
    for cache_file in data_dir.rglob("*.cache"):
        if cache_file.is_file():
            cache_file.unlink()

    logger.info("训练中间文件已清理")


class DatasetWindow(QMainWindow):
    """数据集管理与训练窗口

    标注流程：
      截屏 → [盒子阶段] 调整盒子 → 确定 → 自动保存盒子数据 → 切换裁剪图
      → [属性阶段] 调整三个区域框 → 选择标签 → 保存标签
    """

    def __init__(self, main_window=None):
        super().__init__()
        self.setWindowTitle("模型管理 - 数据集 & 训练")
        self.setMinimumSize(1200, 750)

        self._main_window = main_window
        self._config = ConfigManager()
        self._dataset = DatasetManager()

        # ---- 状态 ----
        self._current_mode = "annotate"       # "annotate" | "predict"
        self._current_dtype = "box"            # 训练类型下拉框选择的值
        self._annotation_phase: Optional[str] = None  # None | "box" | "attr"
        self._current_dataset_name: str = ""
        self._current_image: Optional[np.ndarray] = None
        self._full_screenshot: Optional[np.ndarray] = None   # 完整截图
        self._box_crop: Optional[np.ndarray] = None          # 盒子裁剪图
        self._imported_unlabeled = False  # 当前图片是否导入且未标注

        self._init_ui()
        self._restore_geometry()
        self._refresh_ai_model_combo()
        self._refresh_datasets()

    # ----------------------------------------------------------------
    #  UI 构建
    # ----------------------------------------------------------------

    def _restore_geometry(self) -> None:
        geo = self._config.window_geometry.get("dataset")
        if isinstance(geo, dict):
            try:
                self.setGeometry(geo.get("x", 355), geo.get("y", 175),
                                 geo.get("width", 1200), geo.get("height", 750))
            except Exception:
                pass

    def _init_ui(self) -> None:
        self.setStyleSheet(MAIN_STYLE + DATASET_WINDOW_STYLE)

        # ---- 顶部工具栏 ----
        toolbar = self.addToolBar("工具栏")
        toolbar.setMovable(False)

        self.screenshot_btn = QPushButton("截屏")
        self.screenshot_btn.setToolTip("隐藏窗口后截取全屏")
        self.screenshot_btn.clicked.connect(self._on_screenshot)
        toolbar.addWidget(self.screenshot_btn)
        toolbar.addSeparator()

        toolbar.addWidget(QLabel("训练类型:"))
        self.dtype_combo = QComboBox()
        self.dtype_combo.addItems(["盒子识别模型", "属性识别模型"])
        self.dtype_combo.currentIndexChanged.connect(self._on_dtype_changed)
        toolbar.addWidget(self.dtype_combo)
        toolbar.addSeparator()

        self.train_btn = QPushButton("训练")
        self.train_btn.setObjectName("primary_btn")
        self.train_btn.clicked.connect(self._on_train)
        toolbar.addWidget(self.train_btn)

        self.reset_defaults_btn = QPushButton("恢复默认框")
        self.reset_defaults_btn.setToolTip("重置标注框位置为默认值")
        self.reset_defaults_btn.clicked.connect(self._on_reset_defaults)
        toolbar.addWidget(self.reset_defaults_btn)

        self.predict_btn = QPushButton("预测")
        self.predict_btn.setObjectName("primary_btn")
        self.predict_btn.clicked.connect(self._on_predict_mode)
        toolbar.addWidget(self.predict_btn)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        # "编辑" 按钮 — 根据阶段变化文案
        self.edit_btn = QPushButton("编辑")
        self.edit_btn.setObjectName("edit_btn")
        self.edit_btn.setCheckable(True)
        self.edit_btn.clicked.connect(self._on_edit_toggle)
        toolbar.addWidget(self.edit_btn)

        # "取消" 按钮 — 截屏/编辑状态下可用
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setObjectName("danger_btn")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._on_cancel_annotation)
        toolbar.addWidget(self.cancel_btn)

        # ---- 中央区域 ----
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Horizontal)

        # 左侧 — 数据集列表
        self.left_widget = QWidget()
        left_layout = QVBoxLayout(self.left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # 标题行：数据集列表 + 导入按钮
        title_row = QHBoxLayout()
        left_title = QLabel("数据集列表")
        left_title.setObjectName("title")
        title_row.addWidget(left_title)
        title_row.addStretch()
        self.import_btn = QPushButton("导入图片")
        self.import_btn.setToolTip("批量导入图片到数据集")
        self.import_btn.clicked.connect(self._on_import_images)
        title_row.addWidget(self.import_btn)
        self.check_btn = QPushButton("检测")
        self.check_btn.setToolTip("检测列表中图片的标签状态")
        self.check_btn.clicked.connect(self._on_check_labels)
        title_row.addWidget(self.check_btn)
        left_layout.addLayout(title_row)
        self.dataset_list = QListWidget()
        self.dataset_list.setMinimumWidth(200)
        self.dataset_list.itemClicked.connect(self._on_dataset_clicked)
        left_layout.addWidget(self.dataset_list)

        del_btn = QPushButton("删除选中")
        del_btn.setObjectName("danger_btn")
        del_btn.clicked.connect(self._on_delete_dataset)
        left_layout.addWidget(del_btn)
        splitter.addWidget(self.left_widget)

        # 中间 — 画布
        self.canvas = ImageCanvas()
        splitter.addWidget(self.canvas)

        # 右侧面板
        self.right_widget = QWidget()
        self.right_layout = QVBoxLayout(self.right_widget)
        self.right_layout.setContentsMargins(0, 0, 0, 0)

        # 标注面板
        self.annotate_panel = QWidget()
        annotate_layout = QVBoxLayout(self.annotate_panel)
        annotate_layout.setContentsMargins(0, 0, 0, 0)

        self.label_panel = LabelPanel()
        self.label_panel.label_changed.connect(self._on_label_changed)
        self.label_panel.save_clicked.connect(self._on_save_labels)
        self.label_panel.next_clicked.connect(self._on_next_image)
        annotate_layout.addWidget(self.label_panel)

        # AI 辅助面板
        ai_group = QWidget()
        ai_group.setObjectName("panel")
        ai_layout = QVBoxLayout(ai_group)
        ai_title = QLabel("AI 辅助标注")
        ai_title.setObjectName("title")
        ai_layout.addWidget(ai_title)

        ai_layout.addWidget(QLabel("选择模型:"))
        self.ai_model_combo = QComboBox()
        self.ai_model_combo.setToolTip("选择用于辅助标注的模型")
        ai_layout.addWidget(self.ai_model_combo)

        self.ai_predict_btn = QPushButton("预测")
        self.ai_predict_btn.setObjectName("primary_btn")
        self.ai_predict_btn.setToolTip("用模型自动标注当前图片")
        self.ai_predict_btn.clicked.connect(self._on_ai_predict)
        ai_layout.addWidget(self.ai_predict_btn)

        self.ai_status = QLabel("")
        self.ai_status.setStyleSheet("color: #6c7086; font-size: 11px;")
        ai_layout.addWidget(self.ai_status)
        annotate_layout.addWidget(ai_group)

        # 预测面板
        self.predict_panel = QWidget()
        predict_layout = QVBoxLayout(self.predict_panel)
        predict_layout.setContentsMargins(8, 8, 8, 8)

        result_group = QWidget()
        result_group.setObjectName("panel")
        result_layout = QVBoxLayout(result_group)
        result_title = QLabel("预测结果")
        result_title.setObjectName("result_title")
        result_layout.addWidget(result_title)
        self.predict_result_text = QLabel("等待预测...")
        self.predict_result_text.setObjectName("attr_result")
        self.predict_result_text.setWordWrap(True)
        self.predict_result_text.setAlignment(Qt.AlignTop)
        result_layout.addWidget(self.predict_result_text)
        predict_layout.addWidget(result_group, 3)

        model_group = QWidget()
        model_group.setObjectName("panel")
        model_layout = QVBoxLayout(model_group)

        model_layout.addWidget(QLabel("盒子识别模型:"))
        self.predict_box_combo = QComboBox()
        self._refresh_model_combo(self.predict_box_combo, "box")
        self.predict_box_combo.currentIndexChanged.connect(self._update_predict_btn)
        model_layout.addWidget(self.predict_box_combo)

        model_layout.addWidget(QLabel("属性识别模型 (可选):"))
        self.predict_attr_combo = QComboBox()
        self._refresh_model_combo(self.predict_attr_combo, "attr")
        model_layout.addWidget(self.predict_attr_combo)

        self.predict_run_btn = QPushButton("执行预测")
        self.predict_run_btn.setObjectName("success_btn")
        self.predict_run_btn.setEnabled(False)
        self.predict_run_btn.clicked.connect(self._on_predict_run)
        model_layout.addWidget(self.predict_run_btn)

        self.predict_progress = QProgressBar()
        self.predict_progress.setMaximum(0)
        self.predict_progress.setVisible(False)
        model_layout.addWidget(self.predict_progress)

        predict_layout.addWidget(model_group, 7)

        back_layout = QHBoxLayout()
        self.back_btn = QPushButton("← 返回标注模式")
        self.back_btn.clicked.connect(self._on_back_to_annotate)
        back_layout.addWidget(self.back_btn)
        back_layout.addStretch()
        predict_layout.addLayout(back_layout)

        self.right_layout.addWidget(self.annotate_panel)
        splitter.addWidget(self.right_widget)
        splitter.setSizes([240, 690, 270])
        main_layout.addWidget(splitter)

        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet(
            "QStatusBar { background-color: #181825; color: #6c7086; }"
        )
        self.setStatusBar(self.status_bar)

    def _refresh_model_combo(self, combo: QComboBox, mtype: str) -> None:
        combo.blockSignals(True)
        combo.clear()
        model_dir = get_models_dir() / mtype
        model_dir.mkdir(parents=True, exist_ok=True)
        combo.addItem(f"-- 选择{mtype}模型 --")
        for pt_file in sorted(model_dir.rglob("*.pt")):
            combo.addItem(pt_file.name, str(pt_file))
        combo.blockSignals(False)

    # ----------------------------------------------------------------
    #  状态管理辅助方法
    # ----------------------------------------------------------------

    def _set_edit_btn_mode(self, checked: bool, text: str) -> None:
        """统一设置编辑按钮样式"""
        self.edit_btn.setChecked(checked)
        self.edit_btn.setText(text)
        self.edit_btn.setProperty("editing", checked)
        self.edit_btn.style().unpolish(self.edit_btn)
        self.edit_btn.style().polish(self.edit_btn)

    def _reset_annotation_state(self) -> None:
        """重置标注状态到空闲"""
        self._annotation_phase = None
        self._full_screenshot = None
        self._box_crop = None
        self._imported_unlabeled = False
        self._current_img_name = ""
        self._current_image = None
        self.canvas.clear_rects()
        self.canvas.disable_all_editing()
        self.label_panel.set_mode("box")  # 回到只读默认状态
        self._set_edit_btn_mode(False, "编辑")
        self.cancel_btn.setVisible(False)

    def _load_attr_labels_for_box(self, name: str) -> None:
        """盒子模式下加载对应属性标签到下拉框（只读显示）

        检查 data/attr/labels/{name}.txt，解析 YOLO 标签，
        按 center_y 归入 top/middle/bottom 区域，设置下拉框选中项。
        无标签时清空下拉框。
        """
        attr_label_path = self._dataset.base_dir / "attr" / "labels" / f"{name}.txt"

        selections = {"top": "", "middle": "", "bottom": ""}

        if attr_label_path.exists():
            items = LabelIO.read(attr_label_path)
            if items and len(items) >= 3:
                id_to_label = self._build_attr_id_map()
                # 转为伪像素坐标（仅 cy 有效），按 cy 排序分配区域
                pseudo_items = []
                for item in items:
                    cls_id, cx, cy, bw, bh = item
                    label = id_to_label.get(cls_id, f"class_{cls_id}")
                    pseudo_items.append((0, int(cy * 1000), 1, int(cy * 1000), label, 0))
                assigned = self._assign_regions_by_cy(pseudo_items, 1000)
                for tag, ri in assigned.items():
                    selections[tag] = ri[4]  # label

        self.label_panel.set_current_selections(selections, block_signal=True)

    def _setup_box_annotation(self, img: np.ndarray, is_unlabeled: bool = False,
                               box_color: QColor = None) -> None:
        """进入盒子标注阶段 — 设置画布、默认框、编辑模式"""
        self._annotation_phase = "box"
        self._current_image = img
        if is_unlabeled:
            self._full_screenshot = img
        self._box_crop = None

        self.canvas.set_image(img)
        self.canvas.clear_rects()
        h, w = img.shape[:2]

        # 盒子位置：优先上次像素坐标，否则默认中央 2/3
        last = self._config.get_last_rects()
        last_box = last.get("box")
        if last_box and all(k in last_box for k in ("x", "y", "w", "h")):
            bx1 = last_box["x"]
            by1 = last_box["y"]
            bw = last_box["w"]
            bh = last_box["h"]
        else:
            bx1 = int(w / 6)
            by1 = int(h / 6)
            bw = int(w * 2 / 3)
            bh = int(h * 2 / 3)

        # 钳制到图片范围内
        bx1 = max(0, min(bx1, w - 1))
        by1 = max(0, min(by1, h - 1))
        bw = max(10, min(bw, w - bx1))
        bh = max(10, min(bh, h - by1))

        if box_color is None:
            box_color = QColor(243, 139, 168) if is_unlabeled else QColor(137, 180, 250)

        self.canvas.add_rect("box", bx1, by1, bx1 + bw, by1 + bh,
                             self._config.default_box_label, box_color)

        self.label_panel.set_mode("box")

        self.canvas.set_all_editable(True)
        self._set_edit_btn_mode(True, "确定")
        self.cancel_btn.setVisible(True)

    # ----------------------------------------------------------------
    #  AI 辅助标注
    # ----------------------------------------------------------------

    def _refresh_ai_model_combo(self) -> None:
        """刷新 AI 辅助面板的模型下拉框，仅显示当前 dtype 的模型"""
        self.ai_model_combo.blockSignals(True)
        self.ai_model_combo.clear()
        model_dir = get_models_dir() / self._current_dtype
        model_dir.mkdir(parents=True, exist_ok=True)
        self.ai_model_combo.addItem(f"-- 选择模型 --")
        for pt_file in sorted(model_dir.rglob("*.pt")):
            self.ai_model_combo.addItem(pt_file.name, str(pt_file))
        self.ai_model_combo.blockSignals(False)

    def _on_ai_predict(self) -> None:
        """AI 辅助预测：用选中模型自动标注当前图片"""
        idx = self.ai_model_combo.currentIndex()
        if idx <= 0:
            self.ai_status.setText("请先选择模型")
            return
        model_path = self.ai_model_combo.itemData(idx)
        if not model_path or not Path(model_path).exists():
            self.ai_status.setText("模型文件不存在")
            return
        if self._current_image is None:
            self.ai_status.setText("请先加载图片")
            return

        self.ai_predict_btn.setEnabled(False)
        self.ai_status.setText("预测中...")
        QApplication.processEvents()

        try:
            from app.core.detector import YOLODetector
            detector = YOLODetector(model_path)
            if not detector.is_loaded:
                self.ai_status.setText("模型加载失败")
                self.ai_predict_btn.setEnabled(True)
                return

            results = detector.predict(
                self._current_image,
                conf=self._config.box_conf_threshold if self._current_dtype == "box"
                     else self._config.attr_conf_threshold)
            boxes = YOLODetector.extract_boxes(results)

            if not boxes:
                self.ai_status.setText("未检测到目标")
                self.ai_predict_btn.setEnabled(True)
                return

            if self._current_dtype == "box":
                # 盒子模式：取面积最大的框
                boxes.sort(key=lambda b: (b[2] - b[0]) * (b[3] - b[1]), reverse=True)
                best = boxes[0]
                bx1, by1, bx2, by2 = best[0], best[1], best[2], best[3]
                # 移除旧 box 框，添加新框
                self.canvas.remove_rect("box")
                self.canvas.add_rect("box", bx1, by1, bx2, by2,
                                     self._config.default_box_label,
                                     QColor(137, 180, 250),
                                     editable=True)
                self.ai_status.setText(f"已检测到盒子: ({bx1},{by1})-({bx2},{by2})")

            elif self._current_dtype == "attr":
                # 属性模式：按 cy 排序后分配到上中下区域，每区取置信度最高
                roi_h = self._current_image.shape[0]
                names = detector._model.names if detector._model else {}

                # 转格式: (x1,y1,x2,y2,label,conf)
                labeled = [
                    (b[0], b[1], b[2], b[3],
                     names.get(int(b[5]), f"class_{int(b[5])}"),
                     float(b[4]))
                    for b in boxes
                ]
                assigned = self._assign_regions_by_cy(labeled, roi_h)

                selections = {}
                for tag in ("top", "middle", "bottom"):
                    self.canvas.remove_rect(tag)
                    ai = assigned.get(tag)
                    if ai:
                        self.canvas.add_rect(tag, ai[0], ai[1], ai[2], ai[3],
                                             ai[4], self._ATTR_COLORS[tag])
                        selections[tag] = ai[4]
                    else:
                        selections[tag] = ""

                self.label_panel.set_current_selections(selections)
                count = len(assigned)
                self.ai_status.setText(f"已检测到 {count} 个区域")

            self.ai_predict_btn.setEnabled(True)
        except Exception as e:
            logger.error(f"AI 预测失败: {e}")
            self.ai_status.setText(f"预测失败: {e}")
            self.ai_predict_btn.setEnabled(True)

    # ----------------------------------------------------------------
    #  辅助：标签映射
    # ----------------------------------------------------------------

    def _build_attr_id_map(self) -> dict:
        """从 config.attr_labels 构建 {class_id: label_name} 映射"""
        attr_meta = self._config.attr_labels
        all_names = []
        for region_labels in attr_meta.values():
            for lb in region_labels:
                if lb not in all_names:
                    all_names.append(lb)
        return {i: name for i, name in enumerate(all_names)}

    # ----------------------------------------------------------------
    #  辅助：属性区域矩形
    # ----------------------------------------------------------------

    _ATTR_COLORS = {
        "top": QColor(243, 139, 168),
        "middle": QColor(249, 226, 175),
        "bottom": QColor(166, 227, 161),
    }

    @staticmethod
    def _assign_regions_by_cy(items: list, roi_h: float) -> dict:
        """按 center_y 排序后分配到 top/middle/bottom 区域

        items: [(x1, y1, x2, y2, label/score/...), ...]
        返回: {"top": (x1,y1,x2,y2,...), "middle": ..., "bottom": ...}

        三个属性固定对应上中下三个区域。按 center_y 升序排列后，
        依次分配 top → middle → bottom。多余项按归入最近区域。
        """
        if not items:
            return {}

        # 按 center_y 排序
        sorted_items = sorted(items, key=lambda r: (r[1] + r[3]) / 2)

        result = {}
        regions = ["top", "middle", "bottom"]
        if len(sorted_items) <= 3:
            for i, item in enumerate(sorted_items):
                result[regions[i]] = item
        else:
            # 多于 3 个：三等分高度，每区取最优
            band_h = roi_h / 3
            bands = {
                "top": (0, band_h),
                "middle": (band_h, band_h * 2),
                "bottom": (band_h * 2, roi_h),
            }
            for tag, (lo, hi) in bands.items():
                candidates = [
                    it for it in sorted_items if lo <= (it[1] + it[3]) / 2 < hi
                ]
                if candidates:
                    # 取面积最大的
                    result[tag] = max(
                        candidates,
                        key=lambda r: (r[2] - r[0]) * (r[3] - r[1])
                    )
        return result

    def _load_attr_rects_from_config(self, img_w: int, img_h: int) -> None:
        """从 config last_rects.attr 恢复上/中/下区域框位置"""
        last = self._config.get_last_rects()
        attr_ratio = last.get("attr") if last else None
        if not attr_ratio:
            return
        for region in ("top", "middle", "bottom"):
            r = attr_ratio.get(region)
            if r:
                ax1 = int(r["rx"] * img_w)
                ay1 = int(r["ry"] * img_h)
                ax2 = ax1 + int(r["rw"] * img_w)
                ay2 = ay1 + int(r["rh"] * img_h)
            else:
                # 默认三等分
                ax1 = 0
                ay1 = {"top": 0, "middle": img_h // 3, "bottom": img_h * 2 // 3}[region]
                ax2 = img_w
                ay2 = {"top": img_h // 3, "middle": img_h * 2 // 3, "bottom": img_h}[region]
            self.canvas.add_rect(region, ax1, ay1, ax2, ay2,
                                 "", self._ATTR_COLORS[region])

    def _refresh_datasets(self) -> None:
        # 保存当前选中项名称以便恢复
        current = self.dataset_list.currentItem()
        selected_name = current.data(Qt.UserRole) if current else None

        self._dataset._refresh()
        self.dataset_list.blockSignals(True)
        self.dataset_list.clear()
        datasets = self._dataset.get_datasets(self._current_dtype)
        for i, name in enumerate(sorted(datasets.keys()), 1):
            item = QListWidgetItem(f"{i}. {name}")
            item.setData(Qt.UserRole, name)
            self.dataset_list.addItem(item)
        self.dataset_list.blockSignals(False)

        # 恢复选中高亮（仅当 itemClicked 设置过 _current_dataset_name 时）
        if selected_name:
            for row in range(self.dataset_list.count()):
                item = self.dataset_list.item(row)
                if item.data(Qt.UserRole) == selected_name:
                    self.dataset_list.setCurrentItem(item)
                    break

    def _on_import_images(self) -> None:
        """批量导入图片到当前 dtype 的 images 目录"""
        paths, _ = QFileDialog.getOpenFileNames(
            self, "导入图片", "",
            "图片文件 (*.jpg *.jpeg *.png *.bmp);;所有文件 (*)",
        )
        if not paths:
            return

        img_dir = self._dataset.base_dir / self._current_dtype / "images"
        img_dir.mkdir(parents=True, exist_ok=True)

        imported_count = 0
        for src_path in paths:
            try:
                src = Path(src_path)
                if not src.exists() or src.suffix.lower() not in (".jpg", ".jpeg", ".png", ".bmp"):
                    continue
                # 使用原文件名，重名加时间戳
                stem = src.stem
                dst = img_dir / f"{stem}{src.suffix.lower()}"
                if dst.exists():
                    ts = datetime.now().strftime("%H%M%S%f")
                    dst = img_dir / f"{stem}_{ts}{src.suffix.lower()}"
                shutil.copy2(str(src), str(dst))
                imported_count += 1
            except Exception as e:
                logger.error(f"导入图片失败 {src_path}: {e}")

        self._refresh_datasets()
        self.status_bar.showMessage(f"已导入 {imported_count} 张图片")

    def _on_check_labels(self) -> None:
        """检测列表图片的标签状态：有标签绿色文字，无标签红色文字"""
        dtype = self._current_dtype
        for row in range(self.dataset_list.count()):
            item = self.dataset_list.item(row)
            name = item.data(Qt.UserRole)
            label_path = self._dataset.base_dir / dtype / "labels" / f"{name}.txt"
            if label_path.exists() and label_path.stat().st_size > 0:
                item.setForeground(QColor("#a6e3a1"))  # 绿色
            else:
                item.setForeground(QColor("#f38ba8"))  # 红色
        self.status_bar.showMessage("标签状态检测完成")

    def _mark_item_labeled(self, name: str) -> None:
        """将指定数据集项标记为已标注（绿色）"""
        for row in range(self.dataset_list.count()):
            item = self.dataset_list.item(row)
            if item.data(Qt.UserRole) == name:
                item.setForeground(QColor("#a6e3a1"))
                break

    def _on_dtype_changed(self, idx: int) -> None:
        new_dtype = "box" if idx == 0 else "attr"
        if new_dtype == self._current_dtype:
            return
        self._current_dtype = new_dtype
        self._current_dataset_name = ""
        self._current_image = None
        self._reset_annotation_state()
        self.dataset_list.clear()
        self._refresh_datasets()
        self.label_panel.set_mode(self._current_dtype)
        self._refresh_ai_model_combo()

    def _on_dataset_clicked(self, item: QListWidgetItem) -> None:
        if item is None:
            return
        name = item.data(Qt.UserRole)
        self._current_dataset_name = name
        self._load_dataset_image(name)

    def _on_next_image(self) -> None:
        """跳转到数据集中下一张图片"""
        row = self.dataset_list.currentRow()
        if row < 0 or row >= self.dataset_list.count() - 1:
            self.status_bar.showMessage("已是最后一张")
            return
        self.dataset_list.setCurrentRow(row + 1)
        item = self.dataset_list.currentItem()
        if item:
            self._on_dataset_clicked(item)

    def _load_dataset_image(self, name: str) -> None:
        """加载数据集图像及标签"""
        self._dataset._refresh()
        datasets = self._dataset.get_datasets(self._current_dtype)
        info = datasets.get(name)
        if info is None:
            self.status_bar.showMessage(f"未找到数据集: {name}")
            return

        img_path = info["image"]
        self.status_bar.showMessage(f"加载: {img_path}")
        try:
            img = _imread(img_path)
            if img is None:
                logger.warning(f"_imread 返回 None: {img_path}")
                self.status_bar.showMessage(f"无法读取图片: {img_path}")
                return
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            self._current_image = img
            self._full_screenshot = None
            self._box_crop = None
            self.canvas.set_image(img)
            h, w = img.shape[:2]
        except Exception as e:
            logger.error(f"加载图像失败 {img_path}: {e}")
            self.status_bar.showMessage(f"加载失败: {e}")
            return

        label_path = info.get("label")
        items = LabelIO.read(Path(label_path)) if label_path else []

        self.canvas.clear_rects()

        # 无标签文件 → 导入的未标注图片，用红色框标记并自动进入编辑模式
        has_labels = bool(label_path)
        if not has_labels and self._current_dtype == "box":
            self._imported_unlabeled = True
            self._setup_box_annotation(img, is_unlabeled=True)
            self._load_attr_labels_for_box(name)  # 未标注也检查属性标签
            self.status_bar.showMessage(f"已加载: {name}")
            return

        self.label_panel.set_mode(self._current_dtype)
        self._set_edit_btn_mode(False, "编辑")

        if self._current_dtype == "box":
            # 清空属性下拉框（后续有标签则填充）
            self.label_panel.set_current_selections({"top": "", "middle": "", "bottom": ""})

        if self._current_dtype == "box" and items:
            self._annotation_phase = "box"
            self._full_screenshot = img  # 编辑已有盒子时需要
            for item in items:
                _, cx, cy, bw, bh = item
                x1, y1, x2, y2 = LabelIO.yolo_to_xyxy(cx, cy, bw, bh, w, h)
                self.canvas.add_rect("box", x1, y1, x2, y2,
                                     self._config.default_box_label,
                                     QColor(137, 180, 250))
            # 加载该图片对应的属性标签到下拉框（只读显示）
            self._load_attr_labels_for_box(name)
        elif self._current_dtype == "attr" and items:
            self._load_attr_from_labels(name, img, items, label_path, w, h)
        elif self._current_dtype == "attr":
            # 无标签 → 使用上次框选位置
            self._annotation_phase = "attr"
            self._current_img_name = name
            self._box_crop = img
            self._load_attr_rects_from_config(w, h)
            self.label_panel.set_regions_visible(True)
            self.label_panel.set_current_selections(
                {"top": "", "middle": "", "bottom": ""}, block_signal=True)
        else:
            # box 模式无标签 → 已在上方处理
            pass
        self.status_bar.showMessage(f"已加载: {name}")

    def _load_attr_from_labels(self, name: str, img: np.ndarray, items: list,
                                label_path: str, w: int, h: int) -> None:
        """从标签文件加载属性标注：框选 + 下拉框选中项

        按 center_y 排序后依次分配到 top/middle/bottom。
        不足 3 条则删除标签文件，回退到 config 默认位置。
        """
        if len(items) < 3:
            try:
                Path(label_path).unlink()
                self.status_bar.showMessage(f"标签不完整已删除: {label_path}")
            except Exception:
                pass
            self._annotation_phase = "attr"
            self._current_img_name = name
            self._box_crop = img
            self._load_attr_rects_from_config(w, h)
            self.label_panel.set_regions_visible(True)
            self.label_panel.set_current_selections(
                {"top": "", "middle": "", "bottom": ""}, block_signal=True)
            return

        self._annotation_phase = "attr"
        self._current_img_name = name
        self._box_crop = img

        id_to_label = self._build_attr_id_map()

        # 转换为 (x1,y1,x2,y2,label,area) 并按 cy 排序分配区域
        labeled_items = []
        for item in items:
            cls_id, cx, cy, bw, bh = item
            x1, y1, x2, y2 = LabelIO.yolo_to_xyxy(cx, cy, bw, bh, w, h)
            label_name = id_to_label.get(cls_id, f"class_{cls_id}")
            area = (x2 - x1) * (y2 - y1)
            labeled_items.append((x1, y1, x2, y2, label_name, area))

        assigned = self._assign_regions_by_cy(labeled_items, h)

        # 绘制框选 + 设置下拉
        selections = {"top": "", "middle": "", "bottom": ""}
        for tag in ("top", "middle", "bottom"):
            ai = assigned.get(tag)
            if ai:
                x1, y1, x2, y2, label_name, _ = ai
                selections[tag] = label_name
                self.canvas.add_rect(tag, x1, y1, x2, y2, label_name,
                                     self._ATTR_COLORS[tag])

        self.label_panel.set_regions_visible(True)
        self.label_panel.set_current_selections(selections, block_signal=True)

    # ----------------------------------------------------------------
    #  截屏
    # ----------------------------------------------------------------

    def _on_screenshot(self) -> None:
        """截取全屏，进入盒子标注阶段"""
        from app.core.capture import ScreenCapture

        self.hide()
        if self._main_window:
            self._main_window.hide()
        QApplication.processEvents()
        time.sleep(0.3)
        cap = ScreenCapture()
        img = cap.capture_once()
        self.show()
        if self._main_window:
            self._main_window.show()

        if img is None:
            QMessageBox.warning(self, "错误", "截屏失败")
            return

        self._full_screenshot = img
        self._current_dataset_name = ""
        self._setup_box_annotation(img)
    # ----------------------------------------------------------------
    #  编辑按钮 — 根据阶段切换行为
    # ----------------------------------------------------------------

    def _on_edit_toggle(self, checked: bool) -> None:
        """编辑按钮：盒子阶段编辑盒子，属性阶段编辑三个区域"""
        if self._annotation_phase == "box":
            if checked:
                self.canvas.set_edit_mode("box", True)
                self._set_edit_btn_mode(True, "确定")
                self.cancel_btn.setVisible(True)
            else:
                self.canvas.disable_all_editing()
                self.cancel_btn.setVisible(False)
                self._confirm_box()

        elif self._annotation_phase == "attr":
            if checked:
                self.canvas.set_all_editable(True)
                self._set_edit_btn_mode(True, "确定")
                self.cancel_btn.setVisible(True)
            else:
                self.canvas.disable_all_editing()
                self._set_edit_btn_mode(False, "编辑框选")
                self.cancel_btn.setVisible(False)
                self._on_save_labels()  # 确定后自动保存
        else:
            self._set_edit_btn_mode(False, "编辑")

    # ----------------------------------------------------------------
    #  取消标注
    # ----------------------------------------------------------------

    def _on_cancel_annotation(self) -> None:
        """取消当前标注操作，回到空闲状态"""
        self._reset_annotation_state()       
        self.status_bar.showMessage("标注已取消")

    # ----------------------------------------------------------------
    #  盒子确认 → 保存盒子数据 → 切换到属性阶段
    # ----------------------------------------------------------------

    def _confirm_box(self) -> None:
        """确认盒子：保存/更新盒子标签，裁剪，切换到属性阶段

        两种情况：
          - 新截图：_full_screenshot 已设置 → 保存图片 + 标签（时间戳命名）
          - 编辑已有：_current_dataset_name 已设置 → 仅更新标签（复用原名）
        """
        box_rect = self.canvas.get_rect("box")
        full_img = self._full_screenshot if self._full_screenshot is not None else self._current_image
        if box_rect is None or full_img is None:
            return

        self._imported_unlabeled = False

        bx1, by1, bx2, by2 = box_rect
        if bx2 <= bx1 or by2 <= by1:
            return

        full_w, full_h = full_img.shape[1], full_img.shape[0]

        # 命名：编辑已有图片时复用原名，新截图用时间戳
        if self._current_dataset_name:
            img_name = self._current_dataset_name
        else:
            img_name = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self._current_img_name = img_name

        # 1) 保存盒子图片 — 仅新截图需要保存文件，编辑已有图片已存在
        if self._full_screenshot is not None or self._current_dataset_name:
            self._save_image_to(full_img, "box", img_name)

        # 2) 保存盒子标签 → data/box/labels/
        yolo = LabelIO.xyxy_to_yolo(*box_rect, full_w, full_h)
        self._dataset.save_labels("box", img_name, [(0,) + yolo])

        # 3) 保存盒子像素坐标 → config
        self._config.set_last_rects(
            box={
                "x": bx1, "y": by1,
                "w": bx2 - bx1, "h": by2 - by1,
            },
            attr=self._config.get_last_rects().get("attr"),
        )

        # 4) 裁剪盒子区域
        h_img, w_img = full_img.shape[:2]
        bx1_c = max(0, bx1)
        by1_c = max(0, by1)
        bx2_c = min(w_img, bx2)
        by2_c = min(h_img, by2)
        crop = full_img[by1_c:by2_c, bx1_c:bx2_c].copy()
        self._box_crop = crop

        # 5) 切换到属性标注阶段
        self._annotation_phase = "attr"
        self._current_image = crop
        self.canvas.set_image(crop)
        self.canvas.clear_rects()

        # 6) 添加三个属性区域框（比例相对盒子）
        self._add_attr_rects()

        # 7) 显示标签面板（可编辑）
        self.label_panel.set_mode("attr")

        # 8) 进入属性编辑模式
        self._on_edit_toggle(True)

        self._refresh_datasets()
        self._mark_item_labeled(img_name)

    def _save_image_to(self, image: np.ndarray, dtype: str, name: str) -> str:
        """保存图片到指定 dtype 的 images 目录"""
        img_dir = self._dataset.base_dir / dtype / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        img_path = img_dir / f"{name}.jpg"
        bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        _imwrite(str(img_path), bgr)
        self._dataset._refresh()
        return str(img_path)

    def _add_attr_rects(self) -> None:
        """根据当前盒子裁剪图尺寸，按比例添加上中下区域框"""
        if self._box_crop is None:
            return
        crop_h, crop_w = self._box_crop.shape[:2]
        if crop_w <= 0 or crop_h <= 0:
            return

        last = self._config.get_last_rects()
        attr_ratios = last.get("attr") or {
            "top":    {"rx": 0.0, "ry": 0.0,  "rw": 1.0, "rh": 1 / 3},
            "middle": {"rx": 0.0, "ry": 1 / 3, "rw": 1.0, "rh": 1 / 3},
            "bottom": {"rx": 0.0, "ry": 2 / 3, "rw": 1.0, "rh": 1 / 3},
        }
        colors = {
            "top": QColor(243, 139, 168),
            "middle": QColor(249, 226, 175),
            "bottom": QColor(166, 227, 161),
        }
        for region in ("top", "middle", "bottom"):
            ar = attr_ratios[region]
            ax1 = int(ar["rx"] * crop_w)
            ay1 = int(ar["ry"] * crop_h)
            ax2 = int((ar["rx"] + ar["rw"]) * crop_w)
            ay2 = int((ar["ry"] + ar["rh"]) * crop_h)
            self.canvas.add_rect(region, ax1, ay1, ax2, ay2, region, colors[region])

    def _save_attr_rects_ratio(self) -> None:
        """将属性区域框位置转为比例（相对盒子裁剪图）并持久化"""
        if self._box_crop is None:
            return
        crop_h, crop_w = self._box_crop.shape[:2]
        if crop_w <= 0 or crop_h <= 0:
            return

        attr_ratio = {}
        for region in ("top", "middle", "bottom"):
            ar = self.canvas.get_rect(region)
            if ar is None:
                continue
            ax1, ay1, ax2, ay2 = ar
            attr_ratio[region] = {
                "rx": ax1 / crop_w,
                "ry": ay1 / crop_h,
                "rw": (ax2 - ax1) / crop_w,
                "rh": (ay2 - ay1) / crop_h,
            }

        self._config.set_last_rects(
            box=self._config.get_last_rects().get("box"),
            attr=attr_ratio if attr_ratio else None,
        )

    # ----------------------------------------------------------------
    #  标签变更
    # ----------------------------------------------------------------

    def _on_label_changed(self, region: str, label: str) -> None:
        """下拉框标签变更 — 更新画布标签，重新启用保存按钮"""
        item = self.canvas._rects.get(region)
        if item:
            item.label = label
        self.label_panel.save_btn.setEnabled(True)

    # ----------------------------------------------------------------
    #  保存属性标签
    # ----------------------------------------------------------------

    def _on_save_labels(self) -> None:
        """保存属性标签：裁剪图 → data/attr/images/ + 标签 → data/attr/labels/"""
        if self._annotation_phase != "attr":
            QMessageBox.warning(self, "提示", "请先确定盒子后进入属性标注阶段")
            return
        if self._box_crop is None:
            QMessageBox.warning(self, "提示", "没有可保存的裁剪图")
            return

        name = self._current_img_name
        if not name:
            name = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            self._current_img_name = name

        crop_h, crop_w = self._box_crop.shape[:2]

        # 保存裁剪图到 data/attr/images/
        self._save_image_to(self._box_crop, "attr", name)

        # 收集类名映射（全局）
        id_to_label = self._build_attr_id_map()
        # 反向映射：label → cls_id
        label_to_id = {v: k for k, v in id_to_label.items()}

        items = []
        for region in ("top", "middle", "bottom"):
            rect = self.canvas.get_rect(region)
            if rect is None:
                continue
            label = self.label_panel._region_groups[region].current_label
            if not label:
                continue
            cls_id = label_to_id.get(label, 0)
            yolo = LabelIO.xyxy_to_yolo(*rect, crop_w, crop_h)
            items.append((cls_id,) + yolo)

        if not items:
            QMessageBox.warning(self, "提示", "未选择属性标签")
            return

        self._dataset.save_labels("attr", name, items)

        # 持久化属性框位置
        self._save_attr_rects_ratio()

        self._refresh_datasets()
        self._mark_item_labeled(name)
        self.status_bar.showMessage("属性标签已保存")
        self.label_panel.save_btn.setEnabled(False)

        # 保存后自动退出编辑状态（如当前正在编辑中）
        if self.edit_btn.isChecked():
            self.canvas.disable_all_editing()
            self._set_edit_btn_mode(False, "编辑框选")
            self.cancel_btn.setVisible(False)

    # ----------------------------------------------------------------
    #  删除
    # ----------------------------------------------------------------

    def _on_delete_dataset(self) -> None:
        current = self.dataset_list.currentItem()
        if current is None:
            return
        name = current.data(Qt.UserRole)
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除数据集 '{name}' 吗？\n（将同时清理 box 和 attr 中的图片及标签）",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            if self._dataset.delete_dataset(name):
                self._refresh_datasets()
                self.canvas.clear_rects()            
            else:
                QMessageBox.warning(self, "错误", "删除失败")

    def _on_reset_defaults(self) -> None:
        reply = QMessageBox.question(
            self, "恢复默认",
            "将重置盒子及属性区域的框选位置为默认值，是否继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._config.reset_last_rects()
    # ----------------------------------------------------------------
    #  训练
    # ----------------------------------------------------------------

    def _on_train(self) -> None:
        trainer = getattr(self, '_trainer', None)
        if trainer and trainer.is_training:
            QMessageBox.warning(self, "提示", "已有训练任务运行中")
            return

        dtype = self._current_dtype  # 捕获当前选择

        class_names = [self._config.default_box_label]
        if dtype == "attr":
            # 与 _on_save_labels 使用相同的映射，保证 class_id 一致且无重复
            class_names = list(self._build_attr_id_map().values())
            if not class_names:
                QMessageBox.warning(self, "提示", "属性标签列表为空，请先在标签面板中设置标签类别")
                return

        # 先检查是否有标签数据（快速检查，完整生成在 _do_train）
        probe_path = self._dataset.generate_yaml(dtype, class_names, val_split=0)
        if probe_path is None:
            QMessageBox.warning(self, "提示", "没有标签数据，请先标注并保存数据集")
            return

        from app.widgets.training_dialog import TrainingDialog
        self._train_dlg = TrainingDialog(
            dtype=dtype,
            parent=self,
        )
        self._train_dlg.start_requested.connect(
            lambda params: self._do_train(class_names, {**params, "_dtype": dtype})
        )
        self._train_dlg.stop_requested.connect(self._on_stop_train)
        self._train_dlg.finished.connect(self._on_train_dlg_closed)
        self._train_dlg.show()  # 非模态，不阻塞

    def _on_train_dlg_closed(self) -> None:
        self._train_dlg = None

    def _on_stop_train(self) -> None:
        trainer = getattr(self, '_trainer', None)
        if trainer:
            trainer.stop()

    def _do_train(self, class_names: list, params: dict) -> None:
        """实际启动训练"""
        dlg = self._train_dlg
        dtype = params.pop("_dtype", self._current_dtype)
        self._trainer = YOLOTrainer()
        name = params["name"]
        if not name:
            QMessageBox.warning(self, "提示", "请输入模型名称")
            dlg.set_done(False, "模型名称为空")
            return

        # 按用户设定的验证集比例生成 data.yaml
        val_split = params.get("val_split", 0.2)
        yaml_path = self._dataset.generate_yaml(
            dtype, class_names, val_split=val_split
        )
        if yaml_path is None:
            QMessageBox.warning(self, "提示", "没有标签数据，请先标注并保存数据集")
            dlg.set_done(False, "无标签数据")
            return

        model_dir = get_models_dir() / dtype
        out_dir = model_dir / name
        if out_dir.exists():
            QMessageBox.warning(self, "名称冲突", f"模型名称 '{name}' 已存在，请更换")
            dlg.set_done(False, f"名称冲突: {name}")
            return

        self.train_btn.setEnabled(False)

        def on_progress(msg: str) -> None:
            if dlg:
                dlg.append_log(msg)

        def on_done(success: bool, msg: str) -> None:
            self.train_btn.setEnabled(True)
            # 训练完成后清理 split/、data.yaml、labels.cache
            _cleanup_training_artifacts(yaml_path)
            if dlg:
                dlg.set_done(success, msg)
            if success:
                self._refresh_model_combo(self.predict_box_combo, "box")
                self._refresh_model_combo(self.predict_attr_combo, "attr")
                self._refresh_ai_model_combo()

        self._trainer.set_callbacks(on_progress, on_done)
        self._trainer.train(
            data_yaml=yaml_path,
            model_type=dtype,
            model_dir=str(model_dir),
            model_name=name,
            epochs=params["epochs"],
            imgsz=params["imgsz"],
            batch=params["batch"],
            lr0=params["lr0"],
            optimizer=params["optimizer"],
            pretrained=params["pretrained"],
        )

    # ----------------------------------------------------------------
    #  预测模式
    # ----------------------------------------------------------------

    def _on_predict_mode(self) -> None:
        self._current_mode = "predict"
        self.left_widget.setVisible(False)
        self.annotate_panel.setVisible(False)
        self.predict_panel.setVisible(False)
        self.right_layout.removeWidget(self.annotate_panel)
        self.right_layout.addWidget(self.predict_panel)
        self.predict_panel.setVisible(True)
        self._refresh_model_combo(self.predict_box_combo, "box")
        self._refresh_model_combo(self.predict_attr_combo, "attr")
        self._update_predict_btn()

    def _on_back_to_annotate(self) -> None:
        self._current_mode = "annotate"
        self.left_widget.setVisible(True)
        self.predict_panel.setVisible(False)
        self.annotate_panel.setVisible(False)
        self.right_layout.removeWidget(self.predict_panel)
        self.right_layout.addWidget(self.annotate_panel)
        self.annotate_panel.setVisible(True)

    def _update_predict_btn(self) -> None:
        """盒子模型选中后才使能预测按钮"""
        self.predict_run_btn.setEnabled(self.predict_box_combo.currentIndex() > 0)

    def _on_predict_run(self) -> None:
        box_idx = self.predict_box_combo.currentIndex()
        if box_idx <= 0:
            QMessageBox.warning(self, "提示", "请选择盒子识别模型")
            return

        from app.core.capture import ScreenCapture

        self.hide()
        QApplication.processEvents()
        time.sleep(0.3)
        cap = ScreenCapture()
        img = cap.capture_once()
        self.show()

        if img is None:
            QMessageBox.warning(self, "错误", "截屏失败")
            return

        self.canvas.set_image(img)
        self.canvas.clear_rects()
        self._current_image = img

        self.predict_progress.setVisible(True)
        self.predict_run_btn.setEnabled(False)
        self.predict_result_text.setText("正在预测...")

        box_path = self.predict_box_combo.itemData(box_idx)
        attr_idx = self.predict_attr_combo.currentIndex()
        attr_path = self.predict_attr_combo.itemData(attr_idx) if attr_idx > 0 else None
        self._predict_thread = PredictThread(
            img, box_path, attr_path,
            box_conf=self._config.box_conf_threshold,
            attr_conf=self._config.attr_conf_threshold,
        )
        self._predict_thread.result_ready.connect(self._on_predict_result)
        self._predict_thread.start()

    def _on_predict_result(self, result: dict) -> None:
        self.predict_progress.setVisible(False)
        self._update_predict_btn()

        if "error" in result:
            self.predict_result_text.setText(f"预测失败: {result['error']}")
            return

        box = result.get("box")
        attrs = result.get("attrs", {})

        lines = []
        if box:
            x1, y1, x2, y2 = box
            lines.append(f"盒子: ({x1},{y1}) - ({x2},{y2})")
            self.canvas.add_rect("box", x1, y1, x2, y2, "box", QColor(137, 180, 250))
            for region in ("top", "middle", "bottom"):
                label = attrs.get(region)
                lines.append(f"  {region}: {label or '--'}")
        else:
            lines.append("未检测到盒子")

        self.predict_result_text.setText("\n".join(lines))
    def closeEvent(self, event) -> None:
        g = self.geometry()
        self._config.set("window_geometry", {
            **self._config.window_geometry,
            "dataset": {
                "x": g.x(), "y": g.y(), "width": g.width(), "height": g.height(),
            },
        })
        event.accept()
