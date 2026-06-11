# Locke Tools

> 基于 YOLO11 的两阶段识别工具（盒子定位 + 属性识别）
---

## 功能特性

| 功能 | 说明 |
|------|------|
| 两阶段检测 | 先定位盒子位置，再识别盒子属性（上/中/下三区域） |
| 实时截屏 | 支持自定义截屏识别区域，全屏或指定范围 |
| 半透明浮窗 | 检测结果以浮窗形式叠加显示，锁定后自动隐藏 |
| 模型管理 | 内置模型导入/选择界面，支持切换不同训练模型 |
| 数据集制作 | 快捷的截屏-标注流程，一键导出训练数据用于自训练 |

> 注：当前仅使用 250 张图片训练属性识别，属性准确率偏低；盒子定位准确率约 90%+。

---

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 运行
python main.py
```

---

## 使用说明

1. **加载模型** — 点击「设置」→ 选择盒子/属性模型，或导入自定义 `.pt` 模型
2. **编辑识别区域** — 在设置中点击「编辑识别区域」，拖拽蓝色区域框调整截屏范围
3. **开始识别** — 点击「开始识别」，主窗口自动最小化，检测结果通过浮窗显示
4. **锁定浮窗** — 识别开始后浮窗自动锁定，点击「解锁浮窗」可拖拽调整位置

---

## 项目结构

```
loke_tools/
├── main.py                 # 程序入口
├── main.spec               # PyInstaller 打包配置
├── config.json             # 用户配置
├── requirements.txt        # Python 依赖
├── icon.ico                # 程序图标
├── app/
│   ├── main_window.py      # 主窗口
│   ├── settings_window.py  # 设置窗口
│   ├── dataset_window.py   # 数据集管理窗口
│   ├── core/
│   │   ├── capture.py      # 屏幕捕获
│   │   └── detector.py     # 两阶段检测器
│   ├── widgets/
│   │   ├── result_overlay.py   # 浮窗显示
│   │   ├── detect_thread.py    # 检测线程
│   │   ├── region_editor.py    # 区域编辑器
│   │   └── styles.py           # 样式表
│   └── utils/
│       ├── config.py       # 配置管理器
│       ├── paths.py        # 路径解析
│       └── logger.py       # 日志
├── models/                 # 模型文件
└── data/                   # 数据集
```

---

## 依赖

- **Python** 3.10+
- **PyTorch** 2.8.0
- **Ultralytics** >= 8.0
- **PyQt5** >= 5.15.9
- **OpenCV** >= 4.8

## 软件链接
通过网盘分享的文件：洛克工具
链接: https://pan.baidu.com/s/1k8JcvQTnClJgCkzvKTvKPw 提取码: 65my 
--来自百度网盘超级会员v1的分享
