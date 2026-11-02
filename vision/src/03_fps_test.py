import time, os, gc
from media.sensor import *
from media.display import *
from media.media import *

W, H = 320, 240
RAW_S = 3
STAT_S = 2

sensor = None
try:
    sensor = Sensor(width=1280, height=960, fps=90)
    sensor.reset()
    sensor.set_framesize(width=W, height=H)
    sensor.set_pixformat(Sensor.GRAYSCALE)
    sensor.run()

    for _ in range(20):
        img = sensor.snapshot()

    print("FPS_TEST %dx%d gray" % (W, H))
    print("EXPOSURE", sensor.exposure(), "AUTO", sensor.auto_exposure())

    t0 = time.ticks_ms()
    n = 0
    while time.ticks_diff(time.ticks_ms(), t0) < RAW_S * 1000:
        img = sensor.snapshot()
        n += 1
    dt = time.ticks_diff(time.ticks_ms(), t0)
    raw_fps = n * 1000.0 / dt
    print("RAW snapshot: frames=%d ms=%d fps=%.1f avg_ms=%.1f" % (
        n, dt, raw_fps, dt / float(n)))

    t0 = time.ticks_ms()
    n = 0
    while time.ticks_diff(time.ticks_ms(), t0) < STAT_S * 1000:
        img = sensor.snapshot()
        st = img.get_statistics()
        m = st.mean()
        n += 1
    dt = time.ticks_diff(time.ticks_ms(), t0)
    print("WITH statistics: frames=%d ms=%d fps=%.1f avg_ms=%.1f last_mean=%d" % (
        n, dt, n * 1000.0 / dt, dt / float(n), m))

    print("MEM_FREE", gc.mem_free())
    print("FPS_OK")
except BaseException as e:
    print("ERROR:", e)
    raise
finally:
    if isinstance(sensor, Sensor):
        sensor.stop()
    Display.deinit()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
