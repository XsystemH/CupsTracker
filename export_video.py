"""Export the full external camera stream and online tracking state to H.264."""
import argparse
from pathlib import Path

import cv2
import h5py
import numpy as np

from tracker import analyze

YELLOW = (30, 220, 255)
ORANGE = (0, 145, 255)
WHITE = (240, 240, 240)


def caption(image, text, xy, color=WHITE):
    cv2.putText(image, text, xy, cv2.FONT_HERSHEY_SIMPLEX, .57, color, 1, cv2.LINE_AA)


def render(rgb, time, index, points, good, cubes, target, elapsed, decision):
    image = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    for cup, (px, py) in enumerate(points):
        x, y = int(round(px * 2)), int(round(py * 2))
        color = YELLOW if cup == target else WHITE
        if not good[cup]:
            color = ORANGE
        if cup == target:
            # Open corners keep the cup and neighbouring hands visible.
            for side in (-1, 1):
                for height, direction in ((-93, 1), (4, -1)):
                    cx, cy = x + side * 28, y + height
                    cv2.line(image, (cx, cy), (cx-side*10, cy), color, 2)
                    cv2.line(image, (cx, cy), (cx, cy+direction*10), color, 2)
        label = 'ABC'[cup] + ('?' if not good[cup] else '')
        cv2.putText(image, label, (x-8,y+21), 0, .55, (10,10,10), 3, cv2.LINE_AA)
        caption(image, label, (x-8,y+21), color)
    for center in cubes:
        cv2.circle(image, tuple(np.rint(center*2).astype(int)), 13, (80,240,100), 2)
    panel = np.full((94, image.shape[1], 3), (36,31,28), np.uint8)
    state = "Cube visible" if cubes else "Waiting for cover"
    if target is not None and not cubes:
        state = f"Target {'ABC'[target]}  /  " + ("rim matched" if good[target] else "estimated")
    caption(panel, f"{time:06.3f}s   frame {index}", (14,23))
    caption(panel, state, (287,23), ORANGE if target is not None and not good[target] else YELLOW)
    seconds = min(elapsed, 3) if decision is None else 3
    caption(panel, f"Still   {seconds:.2f} / 3.00 s", (14,53))
    caption(panel, "Decision   " + (decision["slot"].upper() if decision else "pending"), (287,53))
    cv2.rectangle(panel,(14,68),(624,77),(68,68,68),-1)
    if seconds > 0:
        cv2.rectangle(panel,(14,68),(14+round(610*seconds/3),77),YELLOW,-1)
    return np.vstack((image, panel))


def export(source, output):
    with h5py.File(source) as f:
        group = f["sensorMessages"]
        data = group["externalCameraRGB"]
        times = group["timestamp"][:]
        times -= times[0]
        if len(times) != len(data) or len(times) < 2 or not np.all(np.diff(times) > 0):
            raise ValueError("Expected one increasing timestamp per frame")
        fps = (len(times)-1) / times[-1]
        writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"avc1"), fps, (640,574))
        if not writer.isOpened():
            raise RuntimeError("OpenCV requires an H.264 encoder for this export")
        def inputs():
            nonlocal rgb
            step = data.chunks[0] if data.chunks else 16
            for start in range(0,len(data),step):
                for rgb in data[start:start+step]:
                    yield cv2.resize(rgb,(320,240),interpolation=cv2.INTER_AREA)

        def record(index, *state):
            writer.write(render(rgb,times[index],index,*state))

        rgb = None
        try:
            result, history = analyze(inputs(), times, on_frame=record)
        finally:
            writer.release()
        print(result)
        target = ("left","middle","right").index(result["initial"])
        gaps = [i for i, (_,good,_) in enumerate(history) if not good[target]]
        print("Target prediction-only intervals (relative seconds):")
        for interval in np.split(gaps, np.where(np.diff(gaps) != 1)[0]+1):
            if len(interval):
                print(f"{times[interval[0]]:.2f}-{times[interval[-1]]:.2f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    export(args.source, args.output)
