import time, os, gc
from media.sensor import *
from media.display import *
from media.media import *

W, H = 320, 240
OUT_DIR = "/sdcard/photos"
OUT = OUT_DIR + "/check.jpg"

sensor = None
try:
    try:
        u = os.uname()
        print("BOARD", u.machine, u.version)
    except Exception as e:
        print("UNAME_ERR", e)
    try:
        vfs = os.statvfs("/sdcard")
        total_mb = vfs[0] * vfs[2] / 1048576.0
        free_mb = vfs[0] * vfs[3] / 1048576.0
        print("SD_TOTAL_MB %.1f SD_FREE_MB %.1f" % (total_mb, free_mb))
    except Exception as e:
        print("STATVFS_ERR", e)
    print("MEM_FREE", gc.mem_free())

    try:
        os.mkdir(OUT_DIR)
    except OSError:
        pass

    sensor = Sensor(width=1280, height=960, fps=90)
    sensor.reset()
    sensor.set_framesize(width=W, height=H)
    sensor.set_pixformat(Sensor.GRAYSCALE)
    sensor.run()
    time.sleep(0.8)
    for _ in range(20):
        img = sensor.snapshot()

    st = img.get_statistics()
    print("CAMERA_OK %dx%d mean=%d min=%d max=%d median=%d" % (
        img.width(), img.height(), st.mean(), st.min(), st.max(), st.median()))
    print("EXPOSURE", sensor.exposure(), "AUTO", sensor.auto_exposure())

    img.save(OUT, quality=85)
    print("CHECK_IMAGE", OUT, os.stat(OUT)[6])
    print("CHECK_OK")
except BaseException as e:
    print("ERROR:", e)
    raise
finally:
    if isinstance(sensor, Sensor):
        sensor.stop()
    Display.deinit()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
