# 08_collect.py — 专门采数据集：调参 200-300 张 + 难图回归集
# 每帧存两份：
#   data_XXXX.jpg  干净原图，就是算法真正吃的输入（无任何叠加）
#   dbg_XXXX.jpg   调试图：参考线 + 中线 + 统计条，给人看/对号用
# 日志 collect_log.csv 每帧一行，含真实 ticks_ms；实际间隔以日志为准，不以 PERIOD_MS 为准。
#
# MODE="burst"  推车走圈连拍，N_FRAMES 张后自停，也可随时打断
# MODE="spot"   停在一个位置（弯心/阴影边）倒数 SPOT_HOLD_S 秒后连拍 SPOT_BURST 张，
#               然后继续预览等你挪到下一个位置，循环直到打断 —— 专门用来制造难图
#
# 分辨率：默认 qv=320x240，就是算法运行分辨率。现在没有模型训练；
# 将来上 KPU 时输入尺寸由模型定（常见 224x224/320x320），届时再按模型尺寸采。
import time, os
from media.sensor import *
from media.display import *
from media.media import *

MODE = "burst"        # "burst" | "spot"
RES = "qv"            # "qv" = 320x240（算法分辨率）；"hd" = 1280x960（只当母版存档）
COLOR = False         # False = 灰度（算法输入）；True = RGB565 彩色（给人看）
SHOW = True           # IDE 实时预览，带电脑才有用
OUT_DIR = "/data/captures/dataset"
PERIOD_MS = 200       # burst 目标间隔；双份存图留了余量，实际间隔看日志
N_FRAMES = 300
SPOT_HOLD_S = 6       # spot 每轮给你几秒摆位
SPOT_BURST = 5        # spot 每轮连拍几张
LOCK_AE = False

# 参考线：(320x240 下的行号, 标签)。这只是模型默认值，换成你实测的任意距离都行：
# 在地上从 0 点量一个已知距离贴胶带，拍一张看它落在第几行，把 (行号, 距离) 填进来。
REF_MARKS = ((155, "20cm"), (100, "40cm"), (78, "60cm"))

W, H = (1280, 960) if RES == "hd" else (320, 240)
FS = 24 if W >= 1280 else 14
FMT = Sensor.RGB565 if COLOR else Sensor.GRAYSCALE
TAGC = "rgb" if COLOR else "gray"
LBL = "Lmean" if COLOR else "mean"   # RGB565 统计是 LAB，L 为 0-100；灰度 0-255


def annotate(img, idx, ticks, st, expo):
    for row, lab in REF_MARKS:
        y = int(row * H / 240)
        img.draw_line(0, y, W - 1, y, color=(255, 0, 0) if COLOR else 90, thickness=1)
        img.draw_string_advanced(4, y - FS - 2, FS, lab,
                                 color=(255, 0, 0) if COLOR else 60)
    img.draw_line(W // 2, 0, W // 2, H - 1,
                  color=(0, 200, 0) if COLOR else 150, thickness=1)
    bar = int(FS * 3.4)
    img.draw_rectangle(0, H - bar, W, bar, color=(255, 255, 255), fill=True)
    img.draw_string_advanced(4, H - bar + 2, FS,
                             "#%04d %s %s t=%d" % (idx, MODE, TAGC, ticks),
                             color=(0, 0, 0))
    img.draw_string_advanced(4, H - bar + FS + 4, FS,
                             "%s=%d min=%d max=%d expo=%s" % (
                                 LBL, st.mean(), st.min(), st.max(), expo),
                             color=(0, 0, 0))
    return img


sensor = None
log = None
saved = 0
try:
    try:
        os.mkdir(OUT_DIR)
    except OSError:
        pass

    start = 1
    for nm in os.listdir(OUT_DIR):
        if nm.startswith("data_") and nm.endswith(".jpg"):
            n = int(nm[5:-4])
            if n >= start:
                start = n + 1

    sensor = Sensor(width=1280, height=960, fps=90)
    sensor.reset()
    sensor.set_framesize(width=W, height=H)
    sensor.set_pixformat(FMT)
    sensor.run()
    if SHOW:
        Display.init(Display.VIRT, width=W, height=H, fps=30, to_ide=True)

    for _ in range(25):
        img = sensor.snapshot()
    if LOCK_AE:
        sensor.auto_exposure(False)
    expo = sensor.exposure()

    log_path = OUT_DIR + "/collect_log.csv"
    fresh = True
    try:
        os.stat(log_path)
        fresh = False
    except OSError:
        pass
    log = open(log_path, "a")
    log.write("# SESSION mode=%s res=%s %dx%d color=%s period_ms=%d lock_ae=%s start=%d\n" % (
        MODE, RES, W, H, TAGC, PERIOD_MS, LOCK_AE, start))
    log.write("# ref_marks=%s\n" % (REF_MARKS,))
    if fresh:
        log.write("idx,name,ticks_ms,mode,mean,min,max,median,exposure,clean_bytes,debug_bytes\n")
    log.flush()
    print("COLLECT mode=%s res=%s %dx%d color=%s start=%d exposure=%s" % (
        MODE, RES, W, H, TAGC, start, expo))
    print("LOG", log_path)

    def shoot():
        global saved
        os.exitpoint()
        img = sensor.snapshot()
        st = img.get_statistics()
        ticks = time.ticks_ms()
        idx = start + saved
        clean = "%s/data_%04d.jpg" % (OUT_DIR, idx)
        img.save(clean, quality=90)          # 先存干净原图，再画叠加
        cb = os.stat(clean)[6]
        ex = sensor.exposure()
        annotate(img, idx, ticks, st, ex)
        dbg = "%s/dbg_%04d.jpg" % (OUT_DIR, idx)
        img.save(dbg, quality=85)
        db = os.stat(dbg)[6]
        log.write("%d,data_%04d.jpg,%d,%s,%d,%d,%d,%d,%s,%d,%d\n" % (
            idx, idx, ticks, MODE, st.mean(), st.min(), st.max(), st.median(), ex, cb, db))
        log.flush()
        saved += 1
        if SHOW:
            Display.show_image(img)
        if saved % 25 == 0:
            print("COLLECTED %d last=#%04d %s=%d" % (saved, idx, LBL, st.mean()))
        return img

    if MODE == "burst":
        t_next = time.ticks_ms() + PERIOD_MS
        for i in range(N_FRAMES):
            shoot()
            d = time.ticks_diff(t_next, time.ticks_ms())
            if d > 0:
                time.sleep_ms(d)
            t_next = time.ticks_ms() + PERIOD_MS
    else:
        while True:
            for left in range(SPOT_HOLD_S, 0, -1):
                os.exitpoint()
                frame = sensor.snapshot()
                st = frame.get_statistics()
                annotate(frame, start + saved, time.ticks_ms(), st, sensor.exposure())
                frame.draw_string_advanced(W // 2 - 60, 6, FS,
                                           "摆位 %ds" % left,
                                           color=(255, 0, 0) if COLOR else 30)
                if SHOW:
                    Display.show_image(frame)
                time.sleep_ms(1000)
            for k in range(SPOT_BURST):
                shoot()
                time.sleep_ms(60)
            print("SPOT_DONE saved=%d  挪到下一个位置，或打断结束" % saved)

    print("COLLECT_DONE saved=%d last=#%04d dir=%s" % (saved, start + saved - 1, OUT_DIR))
except BaseException as e:
    print("ERROR:", e)
    print("STOPPED saved=%d dir=%s" % (saved, OUT_DIR))
    raise
finally:
    if log is not None:
        log.close()
    if isinstance(sensor, Sensor):
        sensor.stop()
    Display.deinit()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
