# XMUCS Check-in

厦门大学畅课（TronClass）签到 CLI，支持 Windows、macOS、Linux 和 iPhone a-Shell mini。

本项目基于 [KrsMt-0113/XMU-Rollcall-Bot](https://github.com/KrsMt-0113/XMU-Rollcall-Bot) 修改，参考 [alkali210/XMU-Rollcall-Bot](https://github.com/alkali210/XMU-Rollcall-Bot) 的接口适配工作，并根据厦门大学信息学院常用教学楼位置优化签到地点配置。

## 功能

- **数字签到**：自动获取课程对应的签到数字码，匹配签到 ID 后提交。
- **雷达签到**：支持多个预设地点，超出签到范围时自动切换，成功后核对签到状态。
- **多账号管理**：支持账号配置、快速切换及本地会话缓存。
- **跨平台运行**：内置所需依赖，无需额外 `pip install`，兼容电脑和 iPhone a-Shell mini。
- **签到地点配置**：内置厦门大学五处教学楼的 WGS-84 坐标，支持根据实际需要自行修改或更换签到地点。
## 快速开始

1. 点击 [Code → Download ZIP](https://github.com/XHHarvey/XMUCS-Check-in/archive/refs/heads/main.zip) 下载并解压项目。
2. 电脑在项目目录打开终端；iPhone 在 a-Shell mini 中运行 `pickFolder` 并选择项目目录。
3. 执行：

```bash
python3 run.py
```

Windows 也可以使用 `python run.py`。

首次运行按照提示配置厦门大学统一身份认证账号，后续直接启动即可。

### 常用命令

```bash
python3 run.py            # 启动签到
python3 run.py config     # 管理账号
python3 run.py switch     # 切换账号
python3 run.py refresh    # 刷新登录会话
python3 run.py --check    # 检查运行环境与配置
```

## 雷达签到地点

内置以下五处厦门大学教学楼坐标，采用 **WGS-84** 坐标系：

| 教学楼 | 纬度 | 经度 |
|---|---|---|
| 学武楼 | 24.6083073 | 118.3090821 |
| 坤銮楼 | 24.6084008 | 118.3080402 |
| 文宣楼 | 24.6080642 | 118.3053024 |
| 西部2号楼（学信楼） | 24.6070605 | 118.2951940 |
| 西部4号楼（启信楼） | 24.6081345 | 118.2954988 |

坐标模板位于 `portable/radar_locations.json`。

首次启动后，实际使用的配置保存在本地账号配置目录的 `radar_locations.json` 中，可以根据需要自行修改。

雷达签到仅在明确超出范围时尝试下一个地点，签到成功后自动停止。

## 兼容性与限制

- 已在 Python 3.13 环境下验证。
- 支持数字签到和基于位置的雷达签到。
- 暂不支持二维码签到。

## 项目结构

```text
XMUCS-Check-in/
├── run.py                 # 统一启动入口
├── portable/              # 完整运行包与依赖
│   └── radar_locations.json
├── xmu-rollcall-cli/      # CLI 源码及测试
└── docs/                  # 上游文档存档
```

## 来源与许可证

- [KrsMt-0113/XMU-Rollcall-Bot](https://github.com/KrsMt-0113/XMU-Rollcall-Bot)：原始项目
- [alkali210/XMU-Rollcall-Bot](https://github.com/alkali210/XMU-Rollcall-Bot)：接口适配参考
- [XHHarvey/XMUCS-Check-in](https://github.com/XHHarvey/XMUCS-Check-in)：本项目

本项目采用 [MIT License](LICENSE)，保留原作者 `Copyright (c) 2025 KrsMt.` 及相关版权声明。第三方依赖许可证见 [portable/licenses](portable/licenses)。
