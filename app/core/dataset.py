"""
数据集管理模块 - YOLO 格式标签读写、数据集生成
"""
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

from app.utils.logger import logger
from app.utils.paths import get_data_dir


class LabelIO:
    """YOLO 标签文件读写（归一化坐标）"""

    @staticmethod
    def read(path: Path) -> list:
        """读取 YOLO 标签文件，返回 [(class_id, x_center, y_center, w, h), ...]"""
        items = []
        try:
            if not path.exists():
                return items
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split()
                    if len(parts) >= 5:
                        items.append((
                            int(parts[0]),
                            float(parts[1]), float(parts[2]),
                            float(parts[3]), float(parts[4]),
                        ))
        except Exception as e:
            logger.error(f"读取标签失败 {path}: {e}")
        return items

    @staticmethod
    def write(path: Path, items: list) -> None:
        """写入 YOLO 标签文件 items: [(class_id, x_center, y_center, w, h), ...]"""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                lines = [
                    f"{int(item[0])} {item[1]:.6f} {item[2]:.6f} {item[3]:.6f} {item[4]:.6f}"
                    for item in items
                ]
                f.write("\n".join(lines) + "\n")
        except Exception as e:
            logger.error(f"写入标签失败 {path}: {e}")

    @staticmethod
    def xyxy_to_yolo(x1, y1, x2, y2, img_w, img_h) -> tuple:
        """像素坐标 (x1,y1,x2,y2) → YOLO 归一化 (cx,cy,w,h)"""
        w = x2 - x1
        h = y2 - y1
        return ((x1 + w / 2) / img_w, (y1 + h / 2) / img_h,
                w / img_w, h / img_h)

    @staticmethod
    def yolo_to_xyxy(cx, cy, w, h, img_w, img_h) -> tuple:
        """YOLO (cx,cy,w,h) → 像素坐标 (x1,y1,x2,y2)"""
        x1 = int((cx - w / 2) * img_w)
        y1 = int((cy - h / 2) * img_h)
        x2 = int((cx + w / 2) * img_w)
        y2 = int((cy + h / 2) * img_h)
        return (x1, y1, x2, y2)


class DatasetManager:
    """数据集管理器"""

    def __init__(self, base_dir: str = ""):
        if not base_dir:
            base_dir = str(get_data_dir())
        self.base_dir = Path(base_dir)
        self._datasets: dict = {}
        self._refresh()

    def _refresh(self) -> None:
        self._datasets = {"box": {}, "attr": {}}
        for dtype in ("box", "attr"):
            dpath = self.base_dir / dtype / "images"
            if not dpath.exists():
                continue
            for img_file in sorted(dpath.glob("*")):
                if img_file.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp"):
                    name = img_file.stem
                    label_path = self.base_dir / dtype / "labels" / f"{name}.txt"
                    self._datasets[dtype][name] = {
                        "image": str(img_file),
                        "label": str(label_path) if label_path.exists() else "",
                        "dtype": dtype,
                    }

    def get_datasets(self, dtype: str) -> dict:
        return self._datasets.get(dtype, {})

    def delete_dataset(self, name: str) -> bool:
        """删除数据集（同时清理 box 和 attr 中的图片和标签）"""
        try:
            deleted = False
            for dtype in ("box", "attr"):
                for ext in (".jpg", ".jpeg", ".png", ".bmp"):
                    img_path = self.base_dir / dtype / "images" / f"{name}{ext}"
                    if img_path.exists():
                        img_path.unlink()
                        deleted = True
                        break
                label_path = self.base_dir / dtype / "labels" / f"{name}.txt"
                if label_path.exists():
                    label_path.unlink()
                    deleted = True
            self._refresh()
            return deleted
        except Exception as e:
            logger.error(f"删除数据集失败 {name}: {e}")
            return False

    def save_labels(self, dtype: str, name: str, labels: list) -> bool:
        """保存标签文件 labels: [(class_id, cx, cy, w, h), ...]"""
        try:
            label_dir = self.base_dir / dtype / "labels"
            label_dir.mkdir(parents=True, exist_ok=True)
            LabelIO.write(label_dir / f"{name}.txt", labels)
            self._refresh()
            return True
        except Exception as e:
            logger.error(f"保存标签失败: {e}")
            return False

    def generate_yaml(self, dtype: str, class_names: list, val_split: float = 0.2) -> Optional[str]:
        """生成 YOLO 训练用的 data.yaml，按比例划分 train/val 目录

        Args:
            dtype: "box" | "attr"
            class_names: 类别名列表
            val_split: 验证集比例 (0.0-1.0)，0 表示不划分
        """
        import random

        if not class_names:
            return None

        data_dir = self.base_dir / dtype
        yaml_path = data_dir / "data.yaml"

        images_dir = data_dir / "images"
        labels_dir = data_dir / "labels"

        # 收集所有 image-label 对
        pairs = []
        for img_file in sorted(images_dir.glob("*")):
            if img_file.suffix.lower() not in (".jpg", ".jpeg", ".png", ".bmp"):
                continue
            name = img_file.stem
            label_file = labels_dir / f"{name}.txt"
            if label_file.exists():
                pairs.append((img_file, label_file))

        if not pairs:
            logger.warning("没有带标签的图片，无法生成 data.yaml")
            return None

        if val_split <= 0 or len(pairs) < 2:
            # 不分验证集：train/val 都指向同一目录（YOLO 会自动随机划分）
            content = {
                "path": str(data_dir.absolute()),
                "train": "images",
                "val": "images",
                "nc": len(class_names),
                "names": {i: name for i, name in enumerate(class_names)},
            }
            self._write_yaml(yaml_path, content)
            return str(yaml_path)

        # 随机打乱并划分
        random.seed(42)
        random.shuffle(pairs)
        split_idx = max(1, int(len(pairs) * (1 - val_split)))
        train_pairs = pairs[:split_idx]
        val_pairs = pairs[split_idx:]

        # 创建 split 目录结构（不影响原始 images/labels）
        split_dir = data_dir / "split"
        if split_dir.exists():
            shutil.rmtree(split_dir)

        self._copy_pairs(split_dir / "train", train_pairs)
        self._copy_pairs(split_dir / "val", val_pairs)

        content = {
            "path": str(split_dir.absolute()),
            "train": "train/images",
            "val": "val/images",
            "nc": len(class_names),
            "names": {i: name for i, name in enumerate(class_names)},
        }
        self._write_yaml(yaml_path, content)

        logger.info(
            f"生成 data.yaml: train={len(train_pairs)}, val={len(val_pairs)}, "
            f"split_ratio={1 - val_split:.0%}/{val_split:.0%}"
        )
        return str(yaml_path)

    @staticmethod
    def _copy_pairs(out_dir: Path, pairs: list) -> None:
        """将 image-label 对复制到目标目录"""
        img_out = out_dir / "images"
        lbl_out = out_dir / "labels"
        img_out.mkdir(parents=True, exist_ok=True)
        lbl_out.mkdir(parents=True, exist_ok=True)
        for img_path, lbl_path in pairs:
            dst_img = img_out / img_path.name
            dst_lbl = lbl_out / lbl_path.name
            if not dst_img.exists():
                shutil.copy2(str(img_path), str(dst_img))
            if not dst_lbl.exists():
                shutil.copy2(str(lbl_path), str(dst_lbl))

    @staticmethod
    def _write_yaml(yaml_path: Path, content: dict) -> None:
        try:
            import yaml
            with open(yaml_path, "w", encoding="utf-8") as f:
                yaml.dump(content, f, allow_unicode=True, default_flow_style=False)
        except ImportError:
            lines = [
                f"path: {content['path']}",
                f"train: {content['train']}",
                f"val: {content['val']}",
                f"nc: {content['nc']}",
                "names:",
            ]
            for i, name in content["names"].items():
                lines.append(f"  {i}: {name}")
            with open(yaml_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
