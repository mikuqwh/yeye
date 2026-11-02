# 实时预览，不存任何文件。用来确认新摄像头装好后：能不能出图、清不清楚、视野够不够、曝光稳不稳。
# 停止：IDE 的停止按钮或 Ctrl-C（循环里有 os.exitpoint()，随时可打断）。
import time, os, gc
from media.sensor import *
from media.display import *
from media.media import *

CSI = 2             # 2 = 现在的座子（也是固件默认）；1 = 另一个 FPC 座；None = 固件默认
RES = "qv"          # "qv" = 320x240（算法分辨率）；"hd" = 1280x960（看对焦和视野）
COLOR = True        # True = RGB565 彩色，给人眼看；False = 灰度，算法真正吃的输入
MAX_S = 120         # 自动收工秒数，0 = 不限时（一直跑到你手动停）
MIRROR = None       # True/False 覆盖水平镜像；None = 不动
VFLIP = None        # True/False 覆盖上下翻转；None = 不动（新模组装倒了才需要改）

W, H = (1280, 960) if RES == "hd" else (320, 240)
FS = 24 if W >= 1280 else 14
FMT = Sensor.RGB565 if COLOR else Sensor.GRAYSCALE
# RGB565 的 get_statistics() 是 LAB，mean 是 L 通道（0-100）；灰度是 0-255。两套数不能直接比。
LBL = "Lmean" if COLOR else "mean"
INFO_EVERY = 15     # 每多少帧重新算一次统计并刷新信息条（统计本身要花时间）
GC_EVERY = 60       # 每多少帧主动回收一次，约 1 秒一次

# 灰度图不能喂 RGB 三元组（04 那份踩过），两种格式各用一套色值。
BGC = (255, 255, 255) if COLOR else 255
TXC = (0, 0, 0) if COLOR else 0
XHC = (255, 0, 0) if COLOR else 255


def caption(n, fps, st):
    return "%s csi%s %dx%d %.1ffps(%d) %s=%d min=%d max=%d" % (
        RES, CSI if CSI is not None else "-", W, H, fps, n, LBL,
        st.mean(), st.min(), st.max())


def overlay(img, text):
    h0 = int(FS * 1.4)
    img.draw_rectangle(0, H - h0, W, h0, color=BGC, fill=True)
    img.draw_string_advanced(4, H - h0 + 2, FS, text, color=TXC)
    img.draw_cross(W // 2, H // 2, color=XHC, size=8, thickness=1)
    return img


sensor = None
try:
    kw = {} if CSI is None else {"id": CSI}
    # 不传 width/height/fps：让固件用默认模式（1920x1080@60），由 set_framesize 缩放。
    # CSI1 的模式表封顶 60fps，传 fps=90 的提示在这个口上找不到对应模式。
    sensor = Sensor(**kw)
    sensor.reset()
    print("SENSOR_TYPE", sensor.get_type())
    sensor.set_framesize(width=W, height=H)
    sensor.set_pixformat(FMT)
    if MIRROR is not None:
        sensor.set_hmirror(MIRROR)
    if VFLIP is not None:
        sensor.set_vflip(VFLIP)
    sensor.run()
    Display.init(Display.VIRT, width=W, height=H, fps=30, to_ide=True)

    for _ in range(25):          # 丢掉开机头几帧：自动曝光还没来得及收敛
        img = sensor.snapshot()
    for label, fn in (("MIRROR", sensor.get_hmirror), ("VFLIP", sensor.get_vflip)):
        try:
            print(label, fn())
        except Exception as e:
            print(label, "-> ERR", e)

    n = 0
    st = img.get_statistics()
    txt = caption(0, 0.0, st)
    t0 = time.ticks_ms()
    tlast = t0
    nlast = 0
    fps = 0.0
    while True:
        img = sensor.snapshot()
        n += 1
        if (n - 1) % INFO_EVERY == 0:
            now = time.ticks_ms()
            dt = time.ticks_diff(now, tlast)
            if dt >= 250:        # 窗口太短算出来的 fps 会虚高，等凑够再更新
                fps = (n - nlast) * 1000.0 / dt
                tlast = now
                nlast = n
            st = img.get_statistics()
            txt = caption(n, fps, st)
            if n == 1 or (n - 1) % (INFO_EVERY * 8) == 0:
                print("PREVIEW %s exposure=%s ae=%s mem=%d" % (
                    txt, sensor.exposure(), sensor.auto_exposure(), gc.mem_free()))
        Display.show_image(overlay(img, txt))
        if n % GC_EVERY == 0:
            # 实测每帧约 1.1KB 垃圾（跟画图/推流无关，bare 也一样）。不主动收的话
            # 堆攒满会突然来一次 full GC，帧间隔当场抖一下。
            gc.collect()
        os.exitpoint()
        if MAX_S and time.ticks_diff(time.ticks_ms(), t0) >= MAX_S * 1000:
            print("TIMEOUT %ds" % MAX_S)
            break
    print("STOPPED frames=%d avg_fps=%.1f" % (
        n, n * 1000.0 / max(1, time.ticks_diff(time.ticks_ms(), t0))))
except BaseException as e:
    print("ERROR:", e)
    raise
finally:
    if isinstance(sensor, Sensor):
        sensor.stop()
    Display.deinit()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
