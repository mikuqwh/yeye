import time, os, gc
from media.sensor import *
from media.display import *
from media.media import *

# Two ways to run this:
#   A) WITH a PC (recommended): SHOW = True, just run the script. Ctrl-C stops it
#      at once and meta.txt is closed. No /sdcard/main.py needed.
#   B) WITHOUT a PC: SHOW = False, copy to /sdcard/main.py, power from a 5V power
#      bank. It waits WAIT_S, shoots N_FRAMES, stops by itself. Afterwards get the
#      files back (MTP / card reader) and REMOVE /sdcard/main.py.
#      If a card reader only shows the 500MB partition, set OUT_DIR to /sdcard/track.
# Default: 320x240 gray, 10 fps -> use these frames to tune the QVGA detector.
# For HD stills set W,H = 1280,960 and PERIOD_MS = 400 (about 45 KB/frame), but the
# 100ms period and the IDE preview both fall behind at HD, so keep HD for 07_shot_preview.
W, H = 320, 240
QUALITY = 85
OUT_DIR = "/data/captures/track"
WAIT_S = 15
PERIOD_MS = 100
N_FRAMES = 2000
LOCK_AE = False
MIN_FREE_MB = 20.0
SHOW = True           # True = live preview in the IDE, only useful with a PC
COLOR = False         # False = grayscale, what the detector actually eats.
                      # True = RGB565 color stills (bigger files, same period).
FMT = Sensor.RGB565 if COLOR else Sensor.GRAYSCALE
TAGC = "rgb" if COLOR else "gray"
LBL = "Lmean" if COLOR else "mean"   # RGB565 stats are LAB (L is 0-100)

sensor = None
meta = None
saved = 0
try:
    try:
        os.mkdir(OUT_DIR)
    except OSError:
        pass

    start = 1
    try:
        for nm in os.listdir(OUT_DIR):
            if nm.startswith("track_") and nm.endswith(".jpg"):
                n = int(nm[6:-4])
                if n >= start:
                    start = n + 1
    except Exception as e:
        print("SCAN_ERR", e)

    sensor = Sensor(width=1280, height=960, fps=90)
    sensor.reset()
    sensor.set_framesize(width=W, height=H)
    sensor.set_pixformat(FMT)
    sensor.run()
    if SHOW:
        Display.init(Display.VIRT, width=W, height=H, fps=30, to_ide=True)

    for _ in range(20):
        img = sensor.snapshot()

    if LOCK_AE:
        sensor.auto_exposure(False)
    expo = sensor.exposure()
    print("AUTO_CAPTURE %dx%d frames=%d period=%dms wait=%ds start=%d exposure=%s" % (
        W, H, N_FRAMES, PERIOD_MS, WAIT_S, start, expo))

    meta = open(OUT_DIR + "/meta.txt", "a")
    meta.write("# AUTO_CAPTURE %dx%d frames=%d period_ms=%d color=%s exposure=%s lock_ae=%s start=%d\n" % (
        W, H, N_FRAMES, PERIOD_MS, TAGC, expo, LOCK_AE, start))
    meta.write("# name,ticks_ms,mean,exposure,bytes\n")

    left = WAIT_S
    while left > 0:
        print("START_IN %ds" % left)
        if SHOW:
            Display.show_image(sensor.snapshot())
        os.exitpoint()
        time.sleep(1)
        left -= 1

    saved = 0
    t_next = time.ticks_ms() + PERIOD_MS
    for i in range(N_FRAMES):
        # SDK calls poll the exitpoint too, so an interrupt can still land between
        # save and meta.write: expect at most one frame without a log row.
        os.exitpoint()
        img = sensor.snapshot()
        if SHOW:
            Display.show_image(img)
        st = img.get_statistics()
        name = "track_%04d.jpg" % (start + i)
        path = OUT_DIR + "/" + name
        img.save(path, quality=QUALITY)
        size = os.stat(path)[6]
        expo = sensor.exposure()
        meta.write("%s,%d,%d,%s,%d\n" % (
            name, time.ticks_ms(), st.mean(), expo, size))
        meta.flush()
        saved += 1

        if saved % 100 == 0:
            try:
                vfs = os.statvfs(OUT_DIR)
                free_mb = vfs[0] * vfs[3] / 1048576.0
            except Exception:
                free_mb = -1.0
            print("CAPTURED %d/%d free_mb=%.1f %s=%d" % (
                saved, N_FRAMES, free_mb, LBL, st.mean()))
            if 0.0 <= free_mb < MIN_FREE_MB:
                print("STOP_LOW_SPACE free_mb=%.1f" % free_mb)
                break

        d = time.ticks_diff(t_next, time.ticks_ms())
        if d > 0:
            time.sleep_ms(d)
        t_next = time.ticks_ms() + PERIOD_MS

    print("AUTO_CAPTURE_DONE saved=%d last=%04d" % (saved, start + saved - 1))
except BaseException as e:
    print("ERROR:", e)
    print("STOPPED saved=%d dir=%s" % (saved, OUT_DIR))
    raise
finally:
    if meta is not None:
        meta.close()
    if isinstance(sensor, Sensor):
        sensor.stop()
    Display.deinit()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
