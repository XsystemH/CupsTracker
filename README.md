# 三杯方块跟踪

固定外部相机的 CPU 基线。读取 HDF5 的 sensorMessages/externalCameraRGB 和 timestamp，将画面缩到 320×240。用绿色连通域定位方块，在遮盖时把方块绑定到对应杯子。用金属杯底缘模板、匀速预测和一对一分配维护三个初始杯子的身份。左右均以外部相机画面为准。

三杯移动后，只有三个底缘都匹配、方块被遮住，且三个位置相对静止参考帧都在 3 像素容差内，才会在连续满 3 秒时输出位置。轨迹失配或超出容差会重置计时。输出 JSON 中 decisions 是正式判断；last_slot 仅记录目标杯在末帧的方位。每段停顿至多触发一次。

## 运行

Python 3.10+，Linux 或 macOS CPU。当前已在 macOS CPU 验证。原始 HDF5 文件放在仓库外。

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python tracker.py ~/Downloads/swap_cups/episode_001.hdf5 --tracks /tmp/001.csv
python tracker.py ~/Downloads/swap_cups/episode_002.hdf5
python tracker.py ~/Downloads/swap_cups/episode_000.hdf5 --initial middle
```

CSV 每帧三行。initial_slot 是杯子的初始身份，x、y 为当前底缘位置，rim_matched=0 表示该帧使用运动预测。时间以每段第一帧为零，帧号从 0 起。

## 本次回放

| 片段 | 帧数 | 时长（秒） | 初始目标 | 停稳起点（秒） | 判断（帧 / 秒） | 揭杯核对 |
| --- | ---: | ---: | --- | ---: | --- | --- |
| 001 | 647 | 22.151 | 中 | 14.809 | 518 / 17.810，中 | 中，[画面](examples/episode_001.jpg) |
| 002 | 842 | 29.117 | 右 | 23.250 | 760 / 26.283，左 | 左，[画面](examples/episode_002.jpg) |
| 000 | 583 | 19.417 | 中（假设） | 17.278 | 结尾仅静止 2.139 秒 | 轨迹末帧在右侧，初始位置和终点均无揭杯真值 |

001、002 只回放至判断帧也得到相同输出。首次重新检测到方块分别在 19.850 秒、26.416 秒。示例图依次展示开头方块、判断帧、末尾揭杯结果。颜色、桌面区域、杯沿模板和关联参数均针对这个机位调试；两条带揭杯的视频同时用于调试与核对，尚无独立测试集。

## 完整回放视频

[001 跟踪视频](examples/episode_001_tracking.mp4) · [002 跟踪视频](examples/episode_002_tracking.mp4)

A/B/C 是开场从左到右的杯子身份。黄框标目标杯，橙框及问号表示运动预测，绿圈标可见方块。底部显示采集时间、帧号和三杯停稳计时，作答后锁定计时与答案直到片尾。视频以各片段平均帧率编码，保留每个原始帧。导出器将 RGB 转为 OpenCV 编码所需的 BGR。

```sh
python export_video.py ~/Downloads/swap_cups/episode_001.hdf5 examples/episode_001_tracking.mp4
```

## Linux 相机实时测试

在接相机的 Ubuntu 桌面终端运行（Python 3.10+，CPU）。仓库设为私有，克隆时请用有访问权的 GitHub 账号。

```sh
sudo apt update
sudo apt install -y git python3-venv v4l-utils libgl1 libglib2.0-0
git clone https://github.com/XsystemH/cups.git
cd cups
python3 -m venv .venv-live
source .venv-live/bin/activate
python -m pip install -r requirements-live.txt
python live.py --list
v4l2-ctl --list-devices
```

选对着整张桌子的固定外部 RGB 相机。同一台相机可能列出多个节点；下面以 /dev/video2 为例。查看其格式，选有 YUYV 或 MJPG 等彩色采集格式的节点，再启动：

```sh
v4l2-ctl -d /dev/video2 --list-formats-ext
python live.py --camera /dev/video2
```

也可把 --list 打印的 /dev/v4l/by-id/... 路径直接传给 --camera，避免重新插拔后编号变化。程序请求 640×480、30 FPS，启动时打印实际收到的分辨率。画面中让三杯横向排开、位于下半幅，杯高约占画面高度的五分之一，参照上方示例图调整相机角度和距离。先摆好三杯、露出绿色方块，按 R 重新初始化。确认 A/B/C 分别贴在三个杯底，方块有绿圈，盖住它后应在对应杯上出现黄框。交换后让全部杯子静止三秒，观察决定和揭杯是否一致。橙框表示运动预测。按 R 开新一轮，Q 或 Esc 退出。

纯 SSH 终端可运行 `python live.py --camera /dev/video2 --headless`，答案输出到终端，Ctrl+C 结束。权限不足时用 `ls -l /dev/video2` 和 `id` 检查设备访问权限；若所属组为 video，可用 `sudo usermod -aG video "$USER"` 并重新登录。若无法采图，先关闭占用相机的程序，并确认节点支持彩色采集。若能采图但三杯编号错位，先对照示例调整构图，再按 R 重置。
