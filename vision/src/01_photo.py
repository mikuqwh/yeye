import time, os, gc
from media.sensor import *
from media.display import *
from media.media import *

# 1280x960 = 4:3 HD (recommended for V-01), 320x240 = fast small shot
W, H = 1280, 960
QUALITY = 85
COLOR = True             # True = RGB565 彩色；False = 灰度（算法输入）
OUT_DIR = "/data/captures/photo"
TAG = "shot"
WARMUP = 25
FMT = Sensor.RGB565 if COLOR else Sensor.GRAYSCALE
TAGC = "rgb" if COLOR else "gray"

sensor = None
try:
    try:
        os.mkdir(OUT_DIR)
    except OSError:
        pass

    sensor = Sensor(width=1280, height=960, fps=90)
    sensor.reset()
    sensor.set_framesize(width=W, height=H)
    sensor.set_pixformat(FMT)
    sensor.run()

    for _ in range(WARMUP):
        img = sensor.snapshot()

    st = img.get_statistics()
    print("STATS mean=%d min=%d max=%d median=%d" % (
        st.mean(), st.min(), st.max(), st.median()))
    print("EXPOSURE", sensor.exposure(), "AUTO", sensor.auto_exposure())

    path = "%s/%s_%s_%dx%d_%d.jpg" % (OUT_DIR, TAG, TAGC, W, H, time.ticks_ms())
    img.save(path, quality=QUALITY)
    print("PHOTO", path, os.stat(path)[6])
    print("PHOTO_OK")
except BaseException as e:
    print("ERROR:", e)
    raise
finally:
    if isinstance(sensor, Sensor):
        sensor.stop()
    Display.deinit()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
