import time, os, gc
from media.sensor import *
from media.display import *
from media.media import *

# Rough static-lane probe: black borders in 8 horizontal bands.
W, H = 320, 240
N_FRAMES = 120
THRESH = (0, 95)
BANDS = ((60, 75), (80, 95), (100, 115), (120, 135),
         (140, 155), (160, 175), (180, 195), (200, 215))
LANE_MM = 500.0
OUT_DIR = "/data/captures/probe"
DEBUG = OUT_DIR + "/lane_debug.jpg"


def med(vals):
    s = sorted(vals)
    n = len(s)
    if n == 0:
        return 0.0
    if n % 2:
        return float(s[n // 2])
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


sensor = None
try:
    try:
        os.mkdir(OUT_DIR)
    except OSError:
        pass

    sensor = Sensor(width=1280, height=960, fps=90)
    sensor.reset()
    sensor.set_framesize(width=W, height=H)
    sensor.set_pixformat(Sensor.GRAYSCALE)
    sensor.run()

    for _ in range(20):
        img = sensor.snapshot()

    print("LANE_PROBE %dx%d threshold=%s bands=%d" % (
        W, H, THRESH, len(BANDS)))
    print("EXPOSURE", sensor.exposure(), "AUTO", sensor.auto_exposure())

    valid_n = 0
    widths = []
    offs = []
    saved = False
    t0 = time.ticks_ms()
    n = 0
    for i in range(N_FRAMES):
        img = sensor.snapshot()
        n += 1
        found = []
        for (y0, y1) in BANDS:
            blobs = img.find_blobs([THRESH], roi=(0, y0, W, y1 - y0),
                                   x_stride=1, y_stride=1,
                                   pixels_threshold=4, area_threshold=4,
                                   merge=True)
            if not blobs:
                continue
            left = min(blobs, key=lambda b: b.x())
            right = max(blobs, key=lambda b: b.x() + b.w())
            if right.x() < left.x() + left.w():
                continue
            lx = left.x() + left.w() / 2.0
            rx = right.x() + right.w() / 2.0
            if 20.0 < rx - lx < 300.0:
                found.append(((y0 + y1) / 2.0, lx, rx, left, right))

        if found:
            valid_n += 1
            y_b, lx_b, rx_b, lb_b, rb_b = found[-1]
            width_px = rx_b - lx_b
            cx = (lx_b + rx_b) / 2.0
            off_px = cx - W / 2.0
            widths.append(width_px)
            offs.append(off_px * LANE_MM / width_px)
            if i % 20 == 0:
                print("F%d valid bands=%d width=%.1fpx off=%+.0fmm off=%.2f lane" % (
                    i, len(found), width_px, off_px * LANE_MM / width_px,
                    off_px / width_px))

            if not saved:
                for (ym, lx, rx, lb, rb) in found:
                    img.draw_rectangle(lb.rect(), color=255, thickness=2)
                    img.draw_rectangle(rb.rect(), color=255, thickness=2)
                    img.draw_cross(int(lx), int(ym), color=255, size=3, thickness=1)
                    img.draw_cross(int(rx), int(ym), color=255, size=3, thickness=1)
                img.draw_line(W // 2, 0, W // 2, H - 1, color=140, thickness=1)
                img.draw_line(int(cx), int(y_b), int(cx), H - 1, color=220, thickness=2)
                img.save(DEBUG, quality=90)
                print("DEBUG_IMAGE", DEBUG, os.stat(DEBUG)[6], "bands", len(found))
                saved = True
        else:
            if i % 20 == 0:
                print("F%d LOST" % i)

    dt = time.ticks_diff(time.ticks_ms(), t0)
    print("LANE_RESULT valid=%d/%d fps=%.1f width_med=%.1fpx off_med=%+.0fmm" % (
        valid_n, n, n * 1000.0 / dt, med(widths), med(offs)))
    print("MEM_FREE", gc.mem_free())
    print("LANE_OK")
except BaseException as e:
    print("ERROR:", e)
    raise
finally:
    if isinstance(sensor, Sensor):
        sensor.stop()
    Display.deinit()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
