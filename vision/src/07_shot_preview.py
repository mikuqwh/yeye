# 开跑 -> 几秒现场预览让你对准 -> 自动拍一张 -> 预览里冻结显示这张
# 跑完自动退出；想再拍一张就再跑一次。
import time, os
from media.sensor import *
from media.display import *
from media.media import *

RES = "hd"          # "hd" = 1280x960 看对焦和视野；"qv" = 320x240
COLOR = True        # True = RGB565 彩色；False = 灰度（算法真正吃的输入）
AIM_S = 4           # 拍之前的现场预览秒数（用来对准/摆位）
HOLD_S = 8          # 拍完之后冻结展示秒数
LOCK_AE = False     # True = 冻结曝光后再拍
OUT_DIR = "/data/captures/quick"

W, H = (1280, 960) if RES == "hd" else (320, 240)
FS = 24 if W >= 1280 else 14
FMT = Sensor.RGB565 if COLOR else Sensor.GRAYSCALE
TAGC = "rgb" if COLOR else "gray"
# RGB565 的 get_statistics() 是 LAB，mean 是 L 通道（0-100）；灰度是 0-255。两套数不能直接比。
LBL = "Lmean" if COLOR else "mean"


def bar(img, caption):
    h0 = int(FS * 2.4)
    img.draw_rectangle(0, H - h0, W, h0, color=(255, 255, 255), fill=True)
    img.draw_string_advanced(4, H - h0 + 2, FS, caption, color=(0, 0, 0))
    return img


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
    Display.init(Display.VIRT, width=W, height=H, fps=30, to_ide=True)

    for _ in range(25):
        img = sensor.snapshot()
    if LOCK_AE:
        sensor.auto_exposure(False)

    t0 = time.ticks_ms()
    while True:
        left = AIM_S - time.ticks_diff(time.ticks_ms(), t0) // 1000
        if left <= 0:
            break
        Display.show_image(bar(sensor.snapshot(), "现场预览，%d 秒后拍摄" % left))
        os.exitpoint()
        time.sleep_ms(80)

    img = sensor.snapshot()
    st = img.get_statistics()
    name = "shot_%s_%s_%d.jpg" % (RES, TAGC, time.ticks_ms())
    path = OUT_DIR + "/" + name
    img.save(path, quality=85)
    size = os.stat(path)[6]
    print("SAVED %s bytes=%d color=%s %s=%d min=%d max=%d median=%d exposure=%s" % (
        path, size, TAGC, LBL, st.mean(), st.min(), st.max(), st.median(), sensor.exposure()))

    bar(img, "%s  %dx%d  %dKB" % (name, W, H, size // 1024))
    img.draw_string_advanced(4, H - int(FS * 1.2), FS,
                             "%s=%d min=%d max=%d expo=%s" % (
                                 LBL, st.mean(), st.min(), st.max(), sensor.exposure()),
                             color=(0, 0, 0))
    print("PREVIEW %ds  冻结的就是刚存的这张" % HOLD_S)
    t0 = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t0) < HOLD_S * 1000:
        Display.show_image(img)
        os.exitpoint()
        time.sleep_ms(60)
except BaseException as e:
    print("ERROR:", e)
    raise
finally:
    if isinstance(sensor, Sensor):
        sensor.stop()
    Display.deinit()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
