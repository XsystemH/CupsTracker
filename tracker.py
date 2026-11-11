"""Three-cup tracker calibrated for the fixed external camera."""
import argparse
import csv
import itertools
import json
from pathlib import Path

import cv2
import h5py
import numpy as np

SLOTS = ("left", "middle", "right")


def features(frame):
    # Work in the recorded channel order. Neutral metal is darker than the table.
    red, g, blue = cv2.split(frame.astype(np.int16))
    metal = ((g < 134) & (red - blue < 20) & (g - blue < 23)).astype(np.float32)
    metal[:118] = 0
    metal[:, :25] = metal[:, 300:] = 0
    # Match the bottom rim, usually visible even when a glove covers the top.
    template = np.zeros((22, 37), np.float32)
    template[:14, 6:31] = 1
    template[14:16, 9:28] = 1
    score = cv2.matchTemplate(metal, template, cv2.TM_CCOEFF_NORMED)
    score = np.pad(score, ((15, 6), (18, 18)), constant_values=-1)
    score[:125] = -1
    score[221:] = -1
    green = ((g - blue > 16) & (g - red > 10) & (g < 175)).astype(np.uint8)
    green[:130] = 0
    green[:, :30] = green[:, 300:] = 0
    _, _, stats, centers = cv2.connectedComponentsWithStats(green)
    cubes = [c for s, c in zip(stats[1:], centers[1:])
             if 32 <= s[4] <= 260 and 5 <= s[2] <= 20 and 5 <= s[3] <= 20]
    return score, cubes


def detections(score, count=3):
    work = score.copy()
    points = []
    for _ in range(count):
        y, x = np.unravel_index(work.argmax(), work.shape)
        points.append((x, y))
        work[max(0,y-17):y+18, max(0,x-21):x+22] = -1
    return np.array(points, dtype=float)


# Injective assignments, with the last column representing a missed detection.
OPTIONS = np.array([ids for ids in itertools.product(range(7), repeat=3)
                    if len(set(k for k in ids if k < 6)) == sum(k < 6 for k in ids)])
ROWS = np.arange(3)


def update(points, velocity, score):
    predicted = np.clip(points + velocity, [22, 120], [298, 225])
    candidates = detections(score, 6)
    quality = np.array([score[int(y), int(x)] for x, y in candidates])
    distance = np.linalg.norm(predicted[:, None] - candidates[None, :], axis=2)
    cost = distance + 24 * (1 - quality[None, :])
    cost = np.column_stack((cost, np.full(3, 20)))
    choices = OPTIONS[cost[ROWS, OPTIONS].sum(axis=1).argmin()]
    new = predicted.copy()
    good = choices < 6
    new[good] = candidates[choices[good]]
    # Reassociate exposed, separated rims after a long overlapping passage.
    clear = (quality[:3].min() > .70 and np.diff(np.sort(candidates[:3,0])).min() > 30)
    if clear and (not good.all() or set(choices) != {0,1,2}):
        new = np.array(min(itertools.permutations(candidates[:3]),
                           key=lambda perm: np.linalg.norm(predicted - perm, axis=1).sum()))
        good[:] = True
    speed = np.clip(velocity * .5 + (new - points) * .5, -10, 10)
    return new, speed * np.where(good[:, None], 1, .85), good


def frames(dataset):
    step = dataset.chunks[0] if dataset.chunks else 16
    for start in range(0, len(dataset), step):
        for image in dataset[start:start + step]:
            yield cv2.resize(image, (320, 240), interpolation=cv2.INTER_AREA)


def analyze(images, times, initial=None, on_frame=None):
    return track_stream(zip(images, times), initial, on_frame, keep_history=True)


def track_stream(samples, initial=None, on_frame=None, keep_history=False):
    previous_time = None
    target = SLOTS.index(initial) if initial else None
    last_cube = None
    anchor = None
    was_visible = False
    moved = False
    decisions = []
    history = []
    for i, (frame, t) in enumerate(samples):
        score, cubes = features(frame)
        if i == 0:
            points = np.array(sorted(detections(score), key=lambda p: p[0]))
            velocity = np.zeros_like(points)
            origin = points.copy()
            good = np.ones(3, bool)
        else:
            points, velocity, good = update(points, velocity, score)
        if target is None:
            if cubes:
                last_cube = cubes[0]
            elif last_cube is not None:
                delta = points - last_cube
                nearest = int(np.argmin(np.linalg.norm(delta, axis=1)))
                if abs(delta[nearest,0]) < 14 and abs(delta[nearest,1]) < 18:
                    target = nearest
        moved |= np.max(np.linalg.norm(points - origin, axis=1)) > 20
        if anchor is None or not good.all() or not was_visible or t - previous_time > 0.15 or np.max(np.linalg.norm(points - anchor, axis=1)) > 3:
            anchor, start, fired = points.copy(), t, False
        was_visible = good.all()
        if moved and good.all() and not fired and t - start >= 3 and target is not None and not cubes:
            rank = list(np.argsort(points[:,0])).index(target)
            decisions.append(dict(frame=i, time=round(float(t),3), still_from=round(float(start),3), slot=SLOTS[rank]))
            fired = True
        if on_frame is not None:
            elapsed = float(t - start) if moved and good.all() and target is not None and not cubes else 0.0
            on_frame(i, points, good, cubes, target, elapsed, decisions[-1] if decisions else None)
        previous_time = t
        if keep_history:
            history.append((points.copy(), good.copy(), cubes))
    if previous_time is None:
        raise ValueError("No frames received")
    return dict(initial=SLOTS[target] if target is not None else None,
                initial_source="assumed" if initial else "observed cover" if target is not None else "unknown",
                decisions=decisions,
                last_slot=SLOTS[list(np.argsort(points[:, 0])).index(target)] if target is not None else None,
                ending_still_seconds=round(float(previous_time - start), 3) if was_visible else 0), history


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("episode", type=Path)
    parser.add_argument("--initial", choices=SLOTS)
    parser.add_argument("--tracks", type=Path, help="Write per-frame pixel coordinates at 320x240")
    args = parser.parse_args()
    with h5py.File(args.episode) as f:
        group = f["sensorMessages"]
        times = group["timestamp"][:]
        if len(times) == 0:
            raise ValueError("Empty episode")
        times -= times[0]
        if not np.isfinite(times).all() or (np.diff(times) <= 0).any() or len(times) != len(group["externalCameraRGB"]):
            raise ValueError("Invalid timestamps or frame count")
        result, history = analyze(frames(group["externalCameraRGB"]), times, args.initial)
    if args.tracks:
        with args.tracks.open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["frame", "seconds", "initial_slot", "x", "y", "rim_matched"])
            for i, (points, good, _) in enumerate(history):
                for slot, (x, y), matched in zip(SLOTS, points, good):
                    writer.writerow([i, round(float(times[i]), 3), slot, round(x, 2), round(y, 2), int(matched)])
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
