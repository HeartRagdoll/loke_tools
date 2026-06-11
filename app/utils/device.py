"""自动设备检测 — CUDA / CPU 自动适配"""

import os
from typing import Tuple

_CUDA_STATE: Tuple[bool, str] = (False, "cpu")


def get_device() -> str:
    """返回 YOLO 训练/推理可用的 device 字符串

    - 有 CUDA: 返回 "0"（GPU 0）
    - 无 CUDA: 返回 "cpu"
    """
    global _CUDA_STATE
    return _CUDA_STATE[1]


def has_cuda() -> bool:
    """返回是否有可用的 CUDA 设备"""
    global _CUDA_STATE
    return _CUDA_STATE[0]


def init_device() -> None:
    """程序启动时调用一次，检测并缓存 CUDA 状态

    放在 try/except 中处理打包后 torch CUDA 版本在无 GPU 环境的情况。
    """
    global _CUDA_STATE

    try:
        import torch
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            cuda_count = torch.cuda.device_count()
            _CUDA_STATE = (True, "0")
            return f"CUDA 可用 (GPU 数量: {cuda_count})"
        else:
            _CUDA_STATE = (False, "cpu")
            return "CUDA 不可用，使用 CPU"
    except ImportError:
        _CUDA_STATE = (False, "cpu")
        return "torch 未安装，使用 CPU"
    except Exception as e:
        # 打包环境可能抛出 DLL 加载异常
        os.environ.pop("CUDA_VISIBLE_DEVICES", None)
        try:
            import torch
            cuda_available = torch.cuda.is_available()
            if cuda_available:
                _CUDA_STATE = (True, "0")
                return f"CUDA 可用 (重试成功)"
        except Exception:
            pass
        _CUDA_STATE = (False, "cpu")
        return f"CUDA 检测异常 ({e})，降级 CPU"
