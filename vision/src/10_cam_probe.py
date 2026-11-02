import time, os, gc
from media.sensor import *
from media.display import *
from media.media import *

# CSI camera bring-up probe -- run this right after swapping the camera module.
# It separates the three things that all look like "no picture":
#   1. is there a driver on this CSI bus    -> Sensor.list_mode(id=..)
#   2. does I2C actually reach the chip     -> the "find sensor ... type N" line
#   3. does it deliver usable pixels        -> snapshot stats + sensor colorbar
# It walks every CSI id, because the Lite-K230D's default socket is wired to
# CSI 2: a module in a different connector stays invisible unless you ask by id.
# Every step is printed, so a partial run still shows where it stopped.
#
# fw v1.8 notes (measured, so do not "fix" these back):
#   Sensor.list_mode(lane_pref=..) -> unexpected keyword argument
#   get_id()      -> "not support get_id now..."
#   get_framerate() -> "not support get_framerate now..."
#   focus_caps()  -> "can't get sensor fd"
# Anything that still raises is wrapped, and nothing important is placed after a
# call that might raise.

W, H = 320, 240
N_FRAMES = 20
FMT = Sensor.GRAYSCALE       # Sensor.RGB565 to eyeball a colour module
CSI_IDS = (0, 1, 2)          # K230 has three CSI sensor inputs; 2 is the default socket
OUT_DIR = "/data/captures/cam"


def say(label, fn):
    """Call fn() but never let an unsupported accessor abort the probe."""
    try:
        print(label, fn())
    except Exception as e:
        print(label, "-> ERR", e)


def probe_modes():
    """Return the CSI ids whose list_mode() answered with at least one mode."""
    alive = []
    for cid in CSI_IDS:
        modes = None
        try:
            modes = Sensor.list_mode(id=cid)
        except Exception as e:
            print("LIST_MODE id=%s -> ERR %s" % (cid, e))
            continue
        n = len(modes or ())
        print("LIST_MODE id=%s -> %d item(s)" % (cid, n))
        for i, m in enumerate(tuple(modes or ())[:8]):
            print("    [%d] %s" % (i, m))
        if n:
            alive.append(cid)
    return alive


def stream_once(cid, hint):
    tag = "csi%s" % cid
    shot = OUT_DIR + "/live_csi%s_%s.jpg" % (cid, "dflt" if not hint else "hint90")
    sensor = None
    try:
        kw = {"id": cid} if cid is not None else {}
        kw.update(hint)
        sensor = Sensor(**kw)
        sensor.reset()
        # The "find sensor <name>, type N" line the driver prints during reset() is
        # the I2C read of the chip: it is the real evidence a module is present.
        say("SENSOR_TYPE", sensor.get_type)
        sensor.set_framesize(width=W, height=H)
        sensor.set_pixformat(FMT)
        sensor.run()
        time.sleep(0.6)

        t0 = time.ticks_ms()
        n = 0
        img = None
        while n < N_FRAMES:
            img = sensor.snapshot()
            n += 1
        dt = time.ticks_diff(time.ticks_ms(), t0)
        st = img.get_statistics()
        print("%s_LIVE %dx%d frames=%d rate=%.1f mean=%d min=%d max=%d median=%d stdev=%d" % (
            tag, img.width(), img.height(), n, (n * 1000.0 / dt) if dt else 0.0,
            st.mean(), st.min(), st.max(), st.median(), st.stdev()))
        if st.max() - st.min() < 8:
            print("%s_FLAT: frames arrive but are uniform -- lens covered, scene black, "
                  "or the module is not really streaming." % tag)
        say("%s_EXPOSURE" % tag, sensor.exposure)
        say("%s_AUTO_EXPOSURE" % tag, sensor.auto_exposure)
        img.save(shot, quality=90)
        print("%s_IMAGE %s %d" % (tag, shot, os.stat(shot)[6]))

        # The colour bar is generated inside the sensor, so it proves the CSI link
        # even when the scene itself is blank white or pitch black. fw v1.8 reports
        # "not support set_colorbar now...", so this is wrapped and only a bonus.
        try:
            sensor.set_colorbar(True)
            time.sleep(0.3)
            bar = None
            for _ in range(5):
                bar = sensor.snapshot()
            bs = bar.get_statistics()
            print("%s_COLORBAR mean=%d min=%d max=%d stdev=%d -> %s" % (
                tag, bs.mean(), bs.min(), bs.max(), bs.stdev(),
                "LINK OK" if bs.stdev() > 10 else "FLAT, suspect wiring"))
        except Exception as e:
            print("%s_COLORBAR -> ERR (module may not support it)" % tag, e)
        print("%s_STREAM_OK %s" % (tag, hint or "default-mode-hint"))
        return True
    except Exception as e:
        print("%s_STREAM_FAIL hint=%s -> %s" % (tag, hint or "default-mode-hint", e))
        return False
    finally:
        if sensor is not None:
            try:
                sensor.stop()
            except Exception as e:
                print("STOP_ERR", e)
        try:
            Sensor.deinit()
        except Exception as e:
            print("DEINIT_ERR", e)
        time.sleep_ms(200)


def probe_streams(ids):
    # Sensor() selects its mode-table row from these hints, so a module with no
    # 1920x1080@60 row can be missed by the default hint. Run BOTH hints on
    # every live bus rather than stopping at the first success, because the
    # existing scripts 00-09 all pass the GC2093 hint (1280x960@90) and that row
    # is what decides whether they keep working after a module swap.
    out = []
    for hint in (None, {"width": 1280, "height": 960, "fps": 90}):
        label = "default-1920x1080@60" if hint is None else "hint-1280x960@90"
        for cid in ids:
            out.append((label, cid, stream_once(cid, hint or {})))
    print("---- summary ----")
    for label, cid, ok in out:
        print("RESULT csi%s %-22s -> %s" % (cid, label, "OK" if ok else "FAIL"))
    return [r[1] for r in out if r[2]]


try:
    u = os.uname()
    print("BOARD", u.machine, u.version)
    print("MEM_FREE", gc.mem_free())
    for d in ("/data/captures", OUT_DIR):
        try:
            os.mkdir(d)
        except OSError:
            pass
    print("---- 1. which CSI bus has a driver ----")
    alive = probe_modes()
    print("ANSWER drivers_on=%s" % (alive,))
    print("---- 2/3. link + pixels ----")
    if not alive:
        print("NO_DRIVER_MATCH: no sensor answered on CSI %s." % (CSI_IDS,))
        print("Re-seat the FPC (contacts down, latch up) and rerun. If it still lists")
        print("nothing, this module is not in this firmware's supported list -> flash a")
        print("build that carries its driver.")
    else:
        won = probe_streams(alive)
        if not won:
            print("NO_STREAM: a driver listed modes but no frames arrived.")
        else:
            print("PROBE_OK live on csi %s -- one frame each saved under %s "
                  "(probe_live_csiN.jpg, no colorbar: unsupported on fw v1.8)." % (
                      won, OUT_DIR))
except BaseException as e:
    print("ERROR:", e)
    raise
finally:
    Display.deinit()
    os.exitpoint(os.EXITPOINT_ENABLE_SLEEP)
    time.sleep_ms(100)
