"""Run the cup tracker on a Linux V4L2 capture device."""
import argparse
import time
from pathlib import Path

import cv2

from export_video import render
from tracker import SLOTS, track_stream


def list_devices():
    aliases = {}
    for path in sorted(Path("/dev/v4l/by-id").glob("*")):
        aliases[path.resolve()] = path
    nodes = sorted(Path("/sys/class/video4linux").glob("video*"))
    if not nodes:
        print("No V4L2 nodes found.")
    for node in nodes:
        device = Path("/dev") / node.name
        print(device, (node / "name").read_text().strip(), aliases.get(device, ""))


def run(camera, initial, headless):
    device = int(camera) if camera.isdecimal() else str(Path(camera).resolve())
    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    if not cap.isOpened():
        raise SystemExit(f"Cannot open {camera}. Check V4L2 capture capability, permissions and other camera users.")
    rgb = None
    running = True
    restart = False
    origin = None
    elapsed = 0.0

    def samples():
        nonlocal rgb, origin, elapsed
        while running and not restart:
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError(f"No image from {camera}. Select a node with an RGB capture format.")
            now = time.monotonic()
            if origin is None:
                origin = now
                print(f"Receiving {frame.shape[1]}x{frame.shape[0]} from {camera}", flush=True)
            elapsed = now - origin
            rgb = cv2.cvtColor(cv2.resize(frame, (640, 480)), cv2.COLOR_BGR2RGB)
            yield cv2.resize(rgb, (320, 240), interpolation=cv2.INTER_AREA), elapsed

    def display(i, points, good, cubes, target, still, decision):
        nonlocal running, restart
        if decision and decision["frame"] == i:
            print(f'{elapsed:.3f}s  Decision: {decision["slot"].upper()}', flush=True)
        if not headless:
            overlay = render(rgb, elapsed, i, points, good, cubes, target, still, decision)
            cv2.imshow("Swap cups | R: new round | Q: quit", overlay)
            key = cv2.waitKey(1) & 255
            running = key not in (27, ord("q"))
            restart = key == ord("r")

    try:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        while running:
            origin = None
            restart = False
            track_stream(samples(), initial, display)
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        if not headless:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--list", action="store_true")
    source.add_argument("--camera", help="V4L2 number, device path or /dev/v4l/by-id symlink")
    parser.add_argument("--initial", choices=SLOTS)
    parser.add_argument("--headless", action="store_true", help="Print decisions without opening a window")
    args = parser.parse_args()
    if args.list:
        list_devices()
    else:
        run(args.camera, args.initial, args.headless)
