# XMUCS Check-in

厦门大学畅课（TronClass）签到 CLI，支持电脑和 iPhone a-Shell mini。

本项目基于 [KrsMt-0113/XMU-Rollcall-Bot](https://github.com/KrsMt-0113/XMU-Rollcall-Bot) 的 CLI 3.4.1 修改，并参考 [alkali210/XMU-Rollcall-Bot](https://github.com/alkali210/XMU-Rollcall-Bot) 的接口更新和适配工作。感谢两个上游项目及其贡献者。原作者的 MIT 许可证和版权声明均予以保留；本仓库独立维护，不代表上游项目。

## 本项目的调整

- 数字签到从课表接口取得同一次签到的数字码，严格匹配签到 ID。
- 按签到创建时间的 **UTC 日期**查询课表，修复北京时间早上 8 点前查不到数字码的问题。
- 雷达签到使用可配置的 1～5 个地点；只有明确返回超出范围时才尝试下一个地点，成功后停止并核对本人签到状态。
- 提供包含依赖的完整运行包，无需 pip 安装。登录加密采用纯 Python AES-CBC，适配 a-Shell mini 缺失 Crypto 原生框架的情况。
- 保留多账号、本地会话缓存和五处教学楼的坐标模板。

## 直接运行：电脑与 iPhone

本次完整包在 Python 3.13 下验证。电脑需已安装 Python；iPhone 使用 a-Shell mini 自带的 Python。

1. 下载本仓库的 ZIP（Code → Download ZIP），解压。
2. 电脑在解压后的仓库目录打开终端；iPhone 在 a-Shell mini 输入 `pickFolder`，选择该目录。
3. 运行：

```sh
python3 run.py
```

Windows 也可以用 `python run.py`。首次使用按提示配置自己的统一身份认证账号；以后仍使用同一命令启动。

```sh
python3 run.py --check  # 检查完整性、依赖和地点配置，不访问网络
python3 run.py config  # 管理账号
python3 run.py switch  # 切换账号
python3 run.py refresh # 清除当前账号的缓存会话
```

启动时显示 `Local patch: 2026-10-23 (UTC timetable date fix)`，表明已包含早课日期修复。

### 更新已有安装

停止旧脚本，在新解压的文件夹中启动。程序会尝试读取已有的 `.xmu_rollcall` 配置目录；需要自定义时，可设置环境变量 `XMU_ROLLCALL_CONFIG_DIR`。不要把账号或 Cookie 放入仓库。

已有手机配置会尽量复用；若找不到原配置，程序会进入账号配置。首次应用坐标模板时会保留已有设备 ID，并备份旧地点配置。详见 [完整包说明](portable/README.md)。

## 地点配置与限制

`portable/radar_locations.json` 是五处教学楼的公共坐标模板：学武楼、坤銮楼、文宣楼、西部片区 2 号楼、西部片区 4 号楼，坐标系为 WGS-84。首次启动后，实际使用的配置位于本地账号配置目录的 `radar_locations.json`；后续手动调整该文件即可。

需要现场蓝牙信号的雷达活动无法仅靠地点坐标完成；未知错误、超时或认证异常会停止本轮提交。二维码签到尚未支持。服务端接口变化仍可能导致功能失效，具体以平台实际返回和个人签到状态为准。

## 源码与验证

- `xmu-rollcall-cli/`：CLI 源码与测试。
- `portable/`：包含依赖的完整包及对应依赖许可证。
- `run.py`：仓库根目录统一入口。
- `docs/UPSTREAM_README.md`：原项目 README 存档，安装和接口说明以本页为准。

运行已有的数字签到与雷达回归测试：

```sh
cd xmu-rollcall-cli
PYTHONPATH=../portable/lib python3 -m unittest discover -s tests -v
```

也可直接运行跨平台测试入口：

```sh
python3 tools/check_project.py
```

已通过 34 项回归测试，覆盖 UTC 日期边界、签到 ID 匹配、数字码为空时不提交、雷达有限重试、蓝牙限制和状态确认。2026-10-23 对真实早课签到做了只读核对，修复后的函数取得有效四位码；该核对未提交真实签到。完整包已在隔离环境检查实际 CLI 导入、纯 Python 依赖与配置保留；未据此声称所有活动都能成功。

## 来源与许可证

- 原项目：[KrsMt-0113/XMU-Rollcall-Bot](https://github.com/KrsMt-0113/XMU-Rollcall-Bot)。本地修改所基于的上游提交：`c7de02b11da3433a047bab29dbbbbbb4c855a484`。
- 参考项目：[alkali210/XMU-Rollcall-Bot](https://github.com/alkali210/XMU-Rollcall-Bot)，参考其数字取码接口更新与雷达接口适配信息。
- 本项目维护：[XHHarvey/XMUCS-Check-in](https://github.com/XHHarvey/XMUCS-Check-in)。

项目沿用 [MIT License](LICENSE)，保留原作者 `Copyright (c) 2025 KrsMt.`。完整包内第三方依赖分别遵循各自许可证，见 [portable/licenses](portable/licenses)；依赖版本及固定来源见 [portable/versions.json](portable/versions.json)。
