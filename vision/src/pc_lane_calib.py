"""Lane black-border (赛道黑边) detector calibration over the curated frame set.

【中文说明】PC 端离线标定与指标复现脚本，不在板子上运行，需要 Python + OpenCV + NumPy。

- 输入：`vision/data/lane_2026-11-02_full/` 下的 320x240 灰度 JPEG，文件名形如
  `data_0001.jpg`。这份完整帧集约 3.6MB，按仓库约定不入库（见 .gitignore），
  需要复现指标时先向视觉索取或按 `08_collect.py` 重采。
- 处理：与板端 `09_lane_track.py` 同一套算法——ROI 横向分块 → 每块相对阈值
  `thr = mean(tile) - OFF` → 连通域 → 面积/高度/宽度/密度形状过滤 → 带倾斜的地平线
  拟合剔除墙面暗带 → 自下而上贪心关联成两条边界 → 直线拟合。
- 输出：终端打印覆盖率和拟合质量（帧数、主/副边界出现率、拟合残差分位数、斜率与
  地平线分布）；同时在数据集目录写出 `overlay_lane.png`（把每条检测到的边界画回原图）
  和 `track_lane.json`（逐帧点位与拟合系数）。目视叠加图是判断检测锁到了什么的唯一可靠
  手段，只看数字会误判。
- 单位与量纲：本脚本只在像素域工作，像素→`error`/`heading`/`bend` 的换算见
  `../PROTOCOL_ADOPTION.md`，帧格式以 `../../../control/docs/protocol_v1_draft.md` 为准。
- 参数调整：改 `PARAMS` 后重跑即可；换场地通常只需要改 `OFF`（场馆经验区间 18-30）。
  `vision_params.py` 里的 PARAMS 是同一组数值的快照，改动要同步。
- 边界与已知限制：结果来自桌面室内数据，含走廊、显示器、盒子等房间杂波，覆盖率不代表
  场地表现；当前镜头位下第二条边界出现率仅 2%，见 `../PROGRESS_2026-11-02.md` 第 4 节。

Reads the 320x240 grayscale mirror in vision/data/lane_2026-11-02_full/ and reports
coverage / fit quality for the parameter block below. Run:

    python vision/src/pc_lane_calib.py [IMG_DIR]

Retuning is a matter of editing PARAMS and re-running; overlay_lane.png shows
what each detection actually locked onto, which is the only check that matters.
"""
import os
import sys
import glob
import json

import numpy as np
import cv2

sys.stdout.reconfigure(encoding="utf-8")

PARAMS = dict(
    TILE_TOP=40,        # first analysis tile (rows above are ceiling/poster)
    TILE_H=22,          # tile height; a tile is wide enough to hold one border crossing
    TILES=9,            # 40 + 9*22 = 238 rows covered
    OFF=22,             # thr = tile_mean - OFF  (relative threshold, survives AE drift)
    DARK_FRAC_MAX=0.45,  # a tile darker than this overall is the wall band -> skip
    MIN_AREA=60,
    MIN_H=10,           # a real border crossing spans most of the tile height
    MAX_W=130,          # wider -> full-width band, not a 50cm-lane tape
    MAX_DENSITY=0.75,   # area / bbox area; solid blocks (people, furniture) are ~1.0
    LINK_TOL=38,        # px, greedy association tolerance between tiles
    HORIZON_MARGIN=6,   # px below the horizon line a blob must be
)

# Frames #0601-#0663 are a neck/shoulder in front of the lens, not the track.
JUNK = set(range(601, 664))


def horizon_line(a, p):
    """Tilted wall/mat boundary as hz(x) = k*x + b, probed in 8 column strips.

    Scanning down each strip, the boundary is the first dark->bright transition
    that holds for 6 rows. Returns None when the scene has no wall band.
    """
    pts = []
    for x in range(20, 320, 40):
        col = a[4:170, max(0, x - 12):x + 12].mean(axis=1)
        hi, lo = float(np.percentile(col, 85)), float(np.percentile(col, 15))
        if hi - lo < 25:
            continue
        thr = lo + 0.55 * (hi - lo)
        for i in range(len(col) - 12):
            if col[i] < thr and col[i + 6:i + 12].mean() > thr:
                pts.append((x, i + 10))
                break
    if len(pts) < 3:
        return None
    q = np.array(pts, dtype=float)
    k, b = np.polyfit(q[:, 0], q[:, 1], 1)
    return (float(k), float(b))


def tile_blobs(a, y, hz, p):
    t = a[y:y + p["TILE_H"]]
    thr = float(t.mean()) - p["OFF"]
    m = (t < thr).astype(np.uint8)
    if m.mean() > p["DARK_FRAC_MAX"]:
        return thr, []
    n, _, st, _ = cv2.connectedComponentsWithStats(m, 8)
    out = []
    for i in range(1, n):
        x, yy, w, h, area = (int(v) for v in st[i])
        if (area < p["MIN_AREA"] or h < p["MIN_H"] or w > p["MAX_W"]
                or area / float(w * h) > p["MAX_DENSITY"]):
            continue
        cy, cx = y + yy + h / 2.0, x + w / 2.0
        if hz is not None and cy < hz[0] * cx + hz[1] + p["HORIZON_MARGIN"]:
            continue
        out.append((cy, cx, w, h, area))
    return thr, out


def _fit(pts):
    return None if len(pts) < 2 else np.polyfit([q[0] for q in pts], [q[1] for q in pts], 1)


def _refit(pts, tol):
    f = _fit(pts)
    if f is None or len(pts) < 3:
        return f, list(pts)
    keep = [q for q in pts if abs(q[1] - np.polyval(f, q[0])) <= tol]
    return (_fit(keep) if len(keep) >= 2 else f), keep


def track(a, p=PARAMS):
    """Two borders, tracked bottom-up: each tile contributes <=1 point per border."""
    hz = horizon_line(a, p)
    acc, mdl = [[], []], [None, None]
    for y in range(p["TILE_TOP"] + (p["TILES"] - 1) * p["TILE_H"], p["TILE_TOP"] - 1, -p["TILE_H"]):
        _, c = tile_blobs(a, y, hz, p)
        if not c:
            continue
        used = [False] * len(c)
        for k in (0, 1):
            if mdl[k] is not None:
                py, tol = float(np.polyval(mdl[k], y + p["TILE_H"] / 2.0)), p["LINK_TOL"]
            elif acc[k]:
                py, tol = float(acc[k][-1][1]), int(p["LINK_TOL"] * 1.6)
            else:
                py = None
            if py is None:
                av = [j for j in range(len(c)) if not used[j]]
                if not av:
                    continue
                j = max(av, key=lambda q: c[q][4])
            else:
                j, bd = -1, tol
                for q, pt in enumerate(c):
                    if not used[q] and abs(pt[1] - py) < bd:
                        bd, j = abs(pt[1] - py), q
                if j < 0:
                    continue
            acc[k].append(c[j])
            used[j] = True
    for k in (0, 1):
        if len(acc[k]) >= 3:
            mdl[k], acc[k] = _refit(acc[k], p["LINK_TOL"])
    return acc, mdl, hz


def main(img_dir):
    files = sorted(glob.glob(os.path.join(img_dir, "data_*.jpg")))
    if not files:
        print("no data_*.jpg in", img_dir)
        return 1
    imgs = {int(os.path.basename(f)[5:9]): cv2.imread(f, cv2.IMREAD_GRAYSCALE) for f in files}
    road = [i for i in sorted(imgs) if i not in JUNK]
    n1, n2, both, res, slope, xref, hz_k, hz_b = 0, 0, 0, [], [], [], [], []
    per = {}
    for i in sorted(imgs):
        acc, mdl, hz = track(imgs[i])
        o = np.argsort([-len(q) for q in acc])
        acc = [acc[j] for j in o]
        mdl = [mdl[j] for j in o]
        per[i] = (acc, mdl, hz)
        if hz is not None:
            hz_k.append(hz[0])
            hz_b.append(hz[1])
        if i in JUNK:
            continue
        n1 += len(acc[0]) >= 4
        n2 += len(acc[1]) >= 4
        both += len(acc[0]) >= 4 and len(acc[1]) >= 4
        for s, m in zip(acc, mdl):
            if m is not None and len(s) >= 4:
                yy = np.array([q[0] for q in s])
                xx = np.array([q[1] for q in s])
                res.append(float(np.abs(np.polyval(m, yy) - xx).mean()))
                slope.append(float(m[0]))
                xref.append(float(np.polyval(m, 200)))
    print("frames=%d  road=%d  junk=%d" % (len(imgs), len(road), len(imgs) - len(road)))
    print("primary border >=4 pts : %d/%d (%.0f%%)" % (n1, len(road), 100.0 * n1 / len(road)))
    print("second  border >=4 pts : %d/%d (%.0f%%)" % (n2, len(road), 100.0 * n2 / len(road)))
    print("both borders           : %d/%d (%.0f%%)" % (both, len(road), 100.0 * both / len(road)))
    print("fit residual p25/50/75 : %s px" % np.round(np.percentile(res, [25, 50, 75]), 1))
    print("slope dx/dy p5/50/95   : %s" % np.round(np.percentile(slope, [5, 50, 95]), 2))
    print("border x@y=200 p5/50/95: %s px" % np.round(np.percentile(xref, [5, 50, 95]), 1))
    print("horizon k p5/50/95     : %s   b p5/50/95: %s" % (
        np.round(np.percentile(hz_k, [5, 50, 95]), 3), np.round(np.percentile(hz_b, [5, 50, 95]), 1)))

    sel = [1, 26, 64, 94, 138, 201, 310, 340, 52, 196, 590, 500]
    tiles = []
    for i in sel:
        im = cv2.cvtColor(imgs[i], cv2.COLOR_GRAY2BGR)
        acc, mdl, hz = per[i]
        if hz is not None:
            cv2.line(im, (0, int(hz[1])), (319, int(hz[0] * 319 + hz[1])), (255, 0, 255), 1)
        for k, col in ((0, (0, 255, 0)), (1, (0, 165, 255))):
            for q in acc[k]:
                cv2.circle(im, (int(q[1]), int(q[0])), 4, col, -1)
            if mdl[k] is not None and len(acc[k]) >= 2:
                cv2.line(im, (int(np.polyval(mdl[k], 40)), 40),
                         (int(np.polyval(mdl[k], 237)), 237), col, 1)
        cv2.putText(im, "#%04d A=%d B=%d" % (i, len(acc[0]), len(acc[1])), (4, 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1, cv2.LINE_AA)
        tiles.append(im)
    rows = [tiles[j:j + 4] for j in range(0, len(tiles), 4)]
    grid = [np.hstack(r + [np.zeros((240, 320, 3))] * (4 - len(r))) for r in rows]
    out_png = os.path.join(os.path.abspath(img_dir), "overlay_lane.png")
    cv2.imwrite(out_png, np.vstack(grid))
    json.dump({str(k): dict(a0=[list(q) for q in per[k][0][0]],
                            a1=[list(q) for q in per[k][0][1]],
                            hz=list(per[k][2]) if per[k][2] else []) for k in per},
              open(out_png[:-len("overlay_lane.png")] + "track_lane.json", "w"))
    print("WROTE", out_png, "(magenta = horizon line)")
    return 0


if __name__ == "__main__":
    default = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "data", "lane_2026-11-02_full")
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else default))
