# V-01 相机标定：一套假车道，只拍 3 张（正中 / 左 10cm / 右 10cm）
# 一张照片里已经同时有 20/40/60cm 的地面，所以不用按距离连拍。
# 跑法：RES="hd" 跑一遍，再把 RES 改成 "qv" 跑一遍。
import time, os
from media.sensor import *
from media.display import *
from media.media import *

RES = "hd"          # "hd" = 1280x960，"qv" = 320x240
COLOR = False       # 标定默认灰度＝算法真正吃的输入；想看彩色改 True
HOLD_S = 8          # 每张之前给你几秒摆位置
LOCK_AE = False     # True = 预热后冻结曝光，三张亮度一致
OUT_DIR = "/data/captures/v01"

# 模型里 20/40/60cm 落在 320x240 的第几行，只用来在预览里画参考线
REF_ROWS = ((155, "20cm"), (100, "40cm"), (78, "60cm"))
SHOTS = (("c", "1/3 车（或相机）正对车道中线"),
         ("l", "2/3 整体左移 10cm，方向不要转"),
         ("r", "3/3 回中间，再整体右移 10cm"))

if RES == "hd":
    W, H = 1280, 960
else:
    W, H = 320, 240
FS = 24 if W >= 1280 else 14
FMT = Sensor.RGB565 if COLOR else Sensor.GRAYSCALE
TAGC = "rgb" if COLOR else "gray"
# RGB565 的 get_statistics() 是 LAB，mean 是 L 通道（0-100）；灰度是 0-255。
LBL = "Lmean" if COLOR else "mean"


def annotate(img, caption):
    bar = int(FS * 2.4)
    img.draw_rectangle(0, H - bar, W, bar, color=(255, 255, 255), fill=True)
    img.draw_string_advanced(4, H - bar + 2, FS, caption, color=(0, 0, 0))
    return img


sensor = None
log = None
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

    for _ in range(25):
        img = sensor.snapshot()

    if LOCK_AE:
        sensor.auto_exposure(False)
    expo = sensor.exposure()
    print("V01_START res=%s %dx%d hold=%ds lock_ae=%s exposure=%s" % (
        RES, W, H, HOLD_S, LOCK_AE, expo))

    log_path = OUT_DIR + "/v01_%s_log.txt" % RES
    log = open(log_path, "w")
    log.write("# V01 res=%s %dx%d color=%s exposure=%s lock_ae=%s\n" % (RES, W, H, TAGC, expo, LOCK_AE))
    log.write("# name,pos,mean,min,max,median,exposure,bytes\n")
    print("LOG", log_path)

    Display.init(Display.VIRT, width=W, height=H, fps=30, to_ide=True)

    for pos, tip in SHOTS:
        print("SHOT %s  -- %s" % (pos, tip))
        for left in range(HOLD_S, 0, -1):
            frame = annotate(sensor.snapshot(), "%s  拍摄倒计时 %ds" % (tip, left))
            Display.show_image(frame)
            os.exitpoint()
            time.sleep_ms(1000)

        img = sensor.snapshot()
        st = img.get_statistics()
        name = "v01_%s_%s_%s" % (RES, TAGC, pos)
        path = "%s/%s.jpg" % (OUT_DIR, name)
        img.save(path, quality=85)
        size = os.stat(path)[6]
        expo = sensor.exposure()
        log.write("%s,%s,%d,%d,%d,%d,%s,%d\n" % (
            name, pos, st.mean(), st.min(), st.max(), st.median(), expo, size))
        log.flush()
        print("SAVED %s bytes=%d %s=%d min=%d max=%d median=%d exposure=%s" % (
            path, size, LBL, st.mean(), st.min(), st.max(), st.median(), expo))

        for row, lab in REF_ROWS:
            y = int(row * H / 240)
            img.draw_line(0, y, W, y, color=(0, 0, 0), thickness=2)
            img.draw_string_advanced(6, y - FS, FS, "约 " + lab, color=(0, 0, 0))
        annotate(img, "%s  %s=%d min=%d max=%d expo=%s" % (
            name, LBL, st.mean(), st.min(), st.max(), expo))
        for _ in range(30):
            Display.show_image(img)
            os.exitpoint()
            time.sleep_ms(20)
        print("  看：60cm 参考线处两条黑边是否都在画面里；白区有没有过曝")

    print("V01_DONE 3 shots -> %s" % OUT_DIR)
except BaseException as e:
    print("ERROR:", e)
    raise
finally:
    if log is not None:
        log.close()
    if isinstance(sensor, Sensor):
        sensor.stop()
    Display.deinit()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
