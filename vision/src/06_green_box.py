import time, os, gc
from media.sensor import *
from media.display import *
from media.media import *

# Real-time green-object detection with IDE preview.
# Run in CanMV IDE / VS Code CanMV and open the frame buffer.
W, H = 640, 480
OUT_DIR = "/data/captures/probe"
SAVE_FIRST = True
RUN_S = 0                  # 0 = run forever; e.g. 10 = stop after 10 s

# LAB threshold (L_min, L_max, A_min, A_max, B_min, B_max).
# Too few detections: widen A/B. Too many false hits: raise L_min.
GREEN = (15, 100, -110, -10, -20, 90)
MIN_PIXELS = 250
MIN_AREA = 250
MAX_OBJECTS = 8
TEXT_SIZE = 16

sensor = None
img = None
try:
    try:
        os.mkdir(OUT_DIR)
    except OSError:
        pass

    sensor = Sensor(width=1280, height=960, fps=90)
    sensor.reset()
    sensor.set_framesize(width=W, height=H)
    sensor.set_pixformat(Sensor.RGB565)
    Display.init(Display.VIRT, width=W, height=H, fps=60, to_ide=True)
    sensor.run()

    for _ in range(20):
        img = sensor.snapshot()

    print("GREEN_BOX %dx%d RGB565 threshold=%s" % (W, H, GREEN))

    saved = False
    fps = 0.0
    last_t = time.ticks_ms()
    print_t0 = last_t
    run_t0 = last_t
    frame_n = 0

    while True:
        os.exitpoint()
        img = sensor.snapshot()
        frame_n += 1

        now = time.ticks_ms()
        dt_frame = time.ticks_diff(now, last_t)
        last_t = now
        if dt_frame > 0:
            inst = 1000.0 / dt_frame
            fps = inst if fps <= 0.0 else fps * 0.85 + inst * 0.15

        blobs = img.find_blobs([GREEN], pixels_threshold=MIN_PIXELS,
                               area_threshold=MIN_AREA, merge=True, margin=15,
                               x_stride=2, y_stride=2)
        found = []
        for b in blobs:
            bw, bh = b.w(), b.h()
            if bw < 12 or bh < 12:
                continue
            ratio = bw / float(bh)
            if ratio < 0.2 or ratio > 5.0:
                continue
            found.append(b)
        found.sort(key=lambda b: b.area(), reverse=True)
        found = found[:MAX_OBJECTS]

        for i, b in enumerate(found):
            x, y, bw, bh = b.rect()
            extent = b.extent()
            kind = "FRAME" if extent < 0.50 else "BLOCK"
            short_kind = "FRM" if kind == "FRAME" else "BLK"
            color = (255, 60, 60) if kind == "FRAME" else (0, 255, 0)
            img.draw_rectangle(x, y, bw, bh, color=color, thickness=2)
            img.draw_cross(b.cx(), b.cy(), color=(255, 255, 0), size=8, thickness=2)
            label = "#%d %s %dx%d" % (i + 1, short_kind, bw, bh)
            tw = 9 * len(label) + 6
            ty = y - 20
            if ty < 0:
                ty = y + 2
            img.draw_rectangle(x, ty, tw, 20, color=(0, 0, 0), fill=True)
            img.draw_string_advanced(x + 3, ty + 2, TEXT_SIZE, label,
                                     color=(255, 255, 255))

        if fps > 0.0:
            hud = "GREEN %d  FPS %.1f" % (len(found), fps)
        else:
            hud = "GREEN %d  FPS --" % len(found)
        img.draw_rectangle(0, 0, 9 * len(hud) + 8, 22,
                           color=(0, 0, 0), fill=True)
        img.draw_string_advanced(4, 2, TEXT_SIZE, hud, color=(0, 255, 0))

        if SAVE_FIRST and found and not saved:
            path = OUT_DIR + "/green_detect.jpg"
            img.save(path, quality=90)
            print("SAVED", path, os.stat(path)[6])
            saved = True

        Display.show_image(img)
        img = None

        if time.ticks_diff(now, print_t0) >= 1000:
            print_t0 = now
            print("FPS %.1f COUNT %d" % (fps, len(found)))
            for i, b in enumerate(found):
                print("  #%d %s c=(%d,%d) %dx%d area=%d extent=%.2f rot=%ddeg" % (
                    i + 1, "FRAME" if b.extent() < 0.50 else "BLOCK",
                    b.cx(), b.cy(), b.w(), b.h(), b.area(), b.extent(),
                    b.rotation_deg()))

        if frame_n % 30 == 0:
            gc.collect()

        if RUN_S > 0 and time.ticks_diff(now, run_t0) >= RUN_S * 1000:
            print("RUN_DONE frames=%d" % frame_n)
            break

    print("GREEN_BOX_DONE")
except BaseException as e:
    print("ERROR:", e)
    raise
finally:
    if isinstance(sensor, Sensor):
        sensor.stop()
    Display.deinit()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
