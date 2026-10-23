# iPhone a-Shell mini 完整版

## 使用

1. 将 XMU-iPhone-complete.zip 传到手机，保存到“文件”并解压。
2. 在 a-Shell mini 输入 `pickFolder`，选择解压后的 XMU-iPhone-complete 文件夹。
3. 运行一个命令：

```sh
python3 run.py
```

无需 pip 安装依赖，无需运行安装脚本，无需合并旧文件。完整包可放在独立文件夹里，旧版文件夹可以保留。

手机已有账号会优先从原配置目录读取，也会尝试读取旁边旧 xmu-iphone-sync 文件夹的安装记录。若没有找到完整账号，程序会进入账号配置，再启动监控。

以后进入这个文件夹后仍运行 `python3 run.py`。可选操作：`python3 run.py config` 管理账号，`python3 run.py switch` 切换账号，`python3 run.py --check` 仅检查本地环境。

## 内容

- 本地修复的 CLI 3.4.1 及数字取码 API 修复。
- 五地点雷达逻辑：学武楼、坤銮楼、文宣楼、西部片区 2 号楼、西部片区 4 号楼。
- 用户截图中的五处 WGS-84 坐标，加载后按已核验公式转换。
- requests、urllib3、certifi、idna、click、charset-normalizer、pyaes、xmulogin 等纯 Python 依赖。
- 登录 SDK 采用经过兼容性核验的纯 Python AES-CBC，不需要 a-Shell mini 缺失的 Crypto 原生框架。
- TLS 验证保持开启，缺少字符检测依赖的问题由包内依赖处理。
- 请求默认连接超时 5 秒、读取超时 20 秒，具体签到请求原有更短超时保持生效。

不修改手机 site-packages，不复制电脑账号、Cookie 或设备 ID。首次同步地点配置时保留手机已有设备 ID，必要时备份旧地点配置；以后保留用户手动调整的坐标。运行时选择的配置路径存放在本文件夹 .runtime.json 中。

## 验证

已使用实际 CLI 验证所有依赖从包内加载、禁止任何 Crypto 原生导入时仍可启动、AES 标准向量、读取原手机配置、五地点、账号及会话保留、重复启动、手动配置保留，以及完整性校验失败时不改手机配置。

实际监控流程使用模拟网络响应，验证可恢复缓存会话并进入轮询，未向真实服务器提交登录或签到请求。另通过 34 项数字签到与雷达回归测试。

尚未直接在用户 iPhone 执行完整包；手机系统文件权限和真实服务器响应仍以实际运行结果为准。需要现场蓝牙信号的雷达活动不能仅靠预设坐标完成，二维码签到仍未加入。

## 许可证与来源

各依赖许可证保留在 licenses 目录，版本在 versions.json，文件校验值在 manifest.json。

pyaes 官方来源：https://github.com/ricmoo/pyaes，固定提交 23a1b4c0488bd38e03a48120dfda98913f4c87d2。charset-normalizer 为 PyPI 官方纯 Python wheel 3.5.2。a-Shell 文件夹访问说明：https://github.com/holzschu/a-shell#sandbox-and-bookmarks
## 2026-10-23 修复

数字签到课表接口需要 UTC 日期。旧补丁按北京时间查询，会导致早上 8 点前的签到查不到。已用同一次真实签到只读核对：UTC 日期返回匹配记录和有效四位码，北京日期返回空列表。未提交真实签到。更新包仍使用 `python3 run.py` 启动，启动时显示本次补丁日期。
