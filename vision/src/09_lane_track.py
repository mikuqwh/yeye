import time, os, gc
from media.sensor import *

# Lane black-border tracker for the K230D, ported from the PC calibration in
# sim_track/lane_calib.py (see vault 02-视觉感知 for the measured rationale).
#
# The wall band behind the track is dark too, and it merges with the tape at the
# frame edges, so a whole-frame blob search cannot separate them. Two things do:
# a per-tile adaptive threshold (a tile dominated by the wall has a low mean, so
# the wall stops being binarised) and a per-frame horizon line fitted with tilt,
# because the wall/mat boundary is never level once the camera is rolled.
#
# Run MODE="calib" first at the venue: it prints the per-tile numbers for a few
# frames so OFF can be retuned for that lighting, then switch to MODE="live".

W, H = 320, 240
MODE = "calib"          # "calib" | "live"
N_FRAMES = 400 if MODE == "live" else 8

TILE_TOP, TILE_H, TILES = 40, 22, 9
OFF = 22                # thr = tile_mean - OFF
DARK_FRAC_MAX = 0.45
MIN_AREA, MIN_H, MAX_W, MAX_DENSITY = 60, 10, 130, 0.75
LINK_TOL = 38
HZ_MARGIN = 6
HZ_STRIPS = 8           # probe columns used to fit the tilted horizon
Y_REF = 200             # row where lane offset is read out
DEBUG = "/data/captures/lane_dbg.jpg"


def med(vals):
    s = sorted(vals)
    n = len(s)
    if n == 0:
        return 0.0
    return float(s[n // 2]) if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def pctl(vals, q):
    s = sorted(vals)
    if not s:
        return 0.0
    i = int(q * (len(s) - 1))
    return float(s[i])


def strip_mean(img, x, y0, h):
    return img.get_statistics(roi=(max(0, x - 12), y0, 24, h)).mean()


def horizon_line(img):
    """hz(x) = k*x + b from the first dark->bright transition in each strip."""
    pts = []
    w = W // HZ_STRIPS
    for s in range(HZ_STRIPS):
        x = s * w + w // 2
        prof = [strip_mean(img, x, y, 6) for y in range(4, 170, 6)]
        lo = min(prof)
        hi = max(prof)
        if hi - lo < 25:
            continue
        thr = lo + 0.55 * (hi - lo)
        for i in range(len(prof) - 2):
            if prof[i] < thr and (prof[i + 1] + prof[i + 2]) / 2.0 > thr:
                pts.append((x, 4 + (i + 1) * 6))
                break
    if len(pts) < 3:
        return None
    n = float(len(pts))
    sx = sum(p[0] for p in pts)
    sy = sum(p[1] for p in pts)
    sxx = sum(p[0] * p[0] for p in pts)
    sxy = sum(p[0] * p[1] for p in pts)
    den = n * sxx - sx * sx
    if abs(den) < 1e-6:
        return None
    k = (n * sxy - sx * sy) / den
    return (k, (sy - k * sx) / n)


def tile_cands(img, y, hz):
    roi = (0, y, W, TILE_H)
    thr = img.get_statistics(roi=roi).mean() - OFF
    if thr <= 0:
        return []
    dark = 0
    blobs = img.find_blobs([(0, int(thr))], roi=roi, x_stride=1, y_stride=1,
                           pixels_threshold=MIN_AREA, area_threshold=MIN_AREA,
                           merge=True, margin=2)
    for b in blobs:
        dark += b.pixels()
    if dark > DARK_FRAC_MAX * W * TILE_H:
        return []
    out = []
    for b in blobs:
        if b.w() > MAX_W or b.h() < MIN_H:
            continue
        den = b.density() if hasattr(b, "density") else b.pixels() / float(b.w() * b.h())
        if den > MAX_DENSITY:
            continue
        cx = b.cx()
        cy = b.cy()
        if hz is not None and cy < hz[0] * cx + hz[1] + HZ_MARGIN:
            continue
        out.append((float(cy), float(cx), b.w(), b.h(), b.pixels()))
    return out


def fit_line(pts):
    n = float(len(pts))
    sy = sum(p[0] for p in pts)
    sx = sum(p[1] for p in pts)
    syy = sum(p[0] * p[0] for p in pts)
    sxy = sum(p[0] * p[1] for p in pts)
    den = n * syy - sy * sy
    if abs(den) < 1e-6:
        return None
    k = (n * sxy - sy * sx) / den
    return (k, (sx - k * sy) / n)


def refit(pts, tol=LINK_TOL):
    f = fit_line(pts)
    if f is None or len(pts) < 3:
        return f, pts
    keep = [p for p in pts if abs(p[1] - (f[0] * p[0] + f[1])) <= tol]
    return (fit_line(keep) if len(keep) >= 2 else f), keep


def predict(f, y):
    return f[0] * y + f[1] if f else None


def track(img, hz):
    acc = [[], []]
    mdl = [None, None]
    for i in range(TILES - 1, -1, -1):
        y = TILE_TOP + i * TILE_H
        c = tile_cands(img, y, hz)
        if not c:
            continue
        used = [False] * len(c)
        ymid = y + TILE_H / 2.0
        for k in (0, 1):
            if mdl[k] is not None:
                py, tol = predict(mdl[k], ymid), LINK_TOL
            elif acc[k]:
                py, tol = acc[k][-1][1], int(LINK_TOL * 1.6)
            else:
                py = None
            if py is None:
                av = [j for j in range(len(c)) if not used[j]]
                if not av:
                    continue
                j = max(av, key=lambda q: c[q][4])
            else:
                j, bd = -1, tol
                for q, p in enumerate(c):
                    if not used[q] and abs(p[1] - py) < bd:
                        bd, j = abs(p[1] - py), q
                if j < 0:
                    continue
            acc[k].append(c[j])
            used[j] = True
    for k in (0, 1):
        if len(acc[k]) >= 3:
            mdl[k], acc[k] = refit(acc[k])
    return acc, mdl


sensor = None
try:
    try:
        os.mkdir("/data/captures")
    except OSError:
        pass
    sensor = Sensor(width=1280, height=960, fps=90)
    sensor.reset()
    sensor.set_framesize(width=W, height=H)
    sensor.set_pixformat(Sensor.GRAYSCALE)
    sensor.run()
    for _ in range(30):
        img = sensor.snapshot()

    print("LANE_TRACK mode=%s OFF=%d tiles=%dx%d from y=%d" % (
        MODE, OFF, TILES, TILE_H, TILE_TOP))
    t_hz = t_tl = t_all = 0
    prim, secd, resid, xref, slope = [], [], [], [], []
    saved = False
    for i in range(N_FRAMES):
        img = sensor.snapshot()
        t0 = time.ticks_ms()
        hz = horizon_line(img)
        t1 = time.ticks_ms()
        acc, mdl = track(img, hz)
        t2 = time.ticks_ms()
        if len(acc[0]) < len(acc[1]):
            acc = [acc[1], acc[0]]
            mdl = [mdl[1], mdl[0]]
        t_all += time.ticks_diff(t2, t0)
        t_hz += time.ticks_diff(t1, t0)
        t_tl += time.ticks_diff(t2, t1)
        prim.append(len(acc[0]))
        secd.append(len(acc[1]))
        if mdl[0] is not None and len(acc[0]) >= 3:
            err = [abs(p[1] - predict(mdl[0], p[0])) for p in acc[0]]
            resid.append(med(err))
            slope.append(mdl[0][0])
            xref.append(predict(mdl[0], Y_REF))
        if MODE == "calib":
            print("F%d hz=%s pts=%d/%d x@%d=%s slope=%s ms(hz=%d tile=%d tot=%d)" % (
                i, ("%.2f,%.0f" % hz) if hz else "none", len(acc[0]), len(acc[1]),
                Y_REF, "%.0f" % xref[-1] if xref else "-",
                "%.2f" % slope[-1] if slope else "-",
                time.ticks_diff(t1, t0), time.ticks_diff(t2, t1), time.ticks_diff(t2, t0)))
            for k, col in ((0, 255), (1, 180)):
                for p in acc[k]:
                    img.draw_cross(int(p[1]), int(p[0]), color=col, size=4, thickness=1)
                if mdl[k] is not None and len(acc[k]) >= 2:
                    img.draw_line(int(predict(mdl[k], TILE_TOP)), TILE_TOP,
                                  int(predict(mdl[k], H - 3)), H - 3, color=col, thickness=1)
            if hz:
                img.draw_line(0, int(hz[1]), W - 1, int(hz[0] * (W - 1) + hz[1]),
                              color=120, thickness=1)
            for n in range(TILES + 1):
                y = TILE_TOP + n * TILE_H
                if y < H:
                    img.draw_line(0, y, W - 1, y, color=60, thickness=1)
            if not saved and i >= 3:
                img.save(DEBUG, quality=90)
                print("DEBUG_IMAGE", DEBUG, os.stat(DEBUG)[6])
                saved = True

    n = len(prim)
    print("RESULT frames=%d primary>=4pts=%.0f%% second>=4pts=%.0f%%" % (
        n, 100.0 * sum(1 for v in prim if v >= 4) / n,
        100.0 * sum(1 for v in secd if v >= 4) / n))
    print("pts/frame p10/50/90 = %d/%d/%d" % (pctl(prim, 0.1), med(prim), pctl(prim, 0.9)))
    if resid:
        print("residual p50/p90 = %.1f/%.1f px" % (med(resid), pctl(resid, 0.9)))
        print("x@%d p5/50/95 = %.0f/%.0f/%.0f px" % (
            Y_REF, pctl(xref, 0.05), med(xref), pctl(xref, 0.95)))
        print("slope p5/50/95 = %.2f/%.2f/%.2f" % (
            pctl(slope, 0.05), med(slope), pctl(slope, 0.95)))
    print("TIMING ms/frame total=%.1f horizon=%.1f tiles=%.1f  -> %.1f fps" % (
        t_all / n, t_hz / n, t_tl / n, 1000.0 / (t_all / n) if t_all else 0))
    print("MEM_FREE", gc.mem_free())
    print("LANE_OK")
except BaseException as e:
    print("ERROR:", e)
    raise
finally:
    if isinstance(sensor, Sensor):
        sensor.stop()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
