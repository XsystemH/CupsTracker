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
