"""车道黑边检测参数快照与 CanMV v1.8 固件缺口清单（视觉侧）。

用途说明：
- PARAMS 是 2026-11-02 桌面 328 帧标定所用的参数快照。
- 当前 `09_lane_track.py`（板端）和 `pc_lane_calib.py`（PC 端）各自内联同一组数值，
  本模块不被它们 import；改参数时必须同步修改那两处，并在队内说明。
- FW_LIMITS 记录庐山派 Lite-K230D 固件 v1.8 实测不支持的 API，避免按文档硬写。
- 换场地通常只需要调 OFF（场馆经验区间 18-30）。
"""

PARAMS = dict(
    TILE_TOP=40,         # 第一个分析块（更上面是墙/海报，不是路面）
    TILE_H=22,           # 块高；一块宽到只可能容纳一条边界穿过
    TILES=9,             # 覆盖到 40 + 9*22 = 238 行
    OFF=22,              # thr = mean(tile) - OFF；相对阈值，抗自动曝光漂移（场馆实测 18-30）
    DARK_FRAC_MAX=0.45,  # 整块比这更暗 = 墙上暗带，跳过
    MIN_AREA=60,
    MIN_H=10,            # 真实边界穿过要占块高的大部分
    MAX_W=130,           # 更宽 = 满幅暗带，不是 50cm 车道的胶带
    MAX_DENSITY=0.75,    # area / bbox；实心块（人、家具）接近 1.0
    LINK_TOL=38,         # px，块间贪心关联容差
    HORIZON_MARGIN=6,    # px，连通域中心必须在地平线下方这么多
)

# 输出字段与主控 20 字节结果包的对应关系。
# 帧格式的唯一依据是 ../control/docs/protocol_v1_draft.md；此处只写视觉侧如何填。
# 符号是几何定义（图像坐标系，向右/向右转为正），不是电机转向定义。
OUTPUT = dict(
    error="int16 LE，-1000..1000，归一化：中线相对图像中心偏差 / 图像半宽 * 1000，右为正，限幅；320宽图半宽取160px",
    heading="int16 LE，-9000..9000，单位 0.01 度，右转为正（deg * 100）；主控当前不使用该字段",
    bend="uint16 LE，0..1000，视觉定义的弯道强度，不是物理曲率 1/R；>500 对应主控演示降速档",
    confidence="uint8 0-100，丢线时填 0 并仍发新序号的无效包",
    processing_ms="uint16 LE，0..1000，本帧处理耗时；START 与保持运行要求 <=100，视觉侧尚未实测",
    sequence="每种 type 独立计数，只接受向前 1..127 的增量；静默 200ms 后主控可重建基线",
)

# 上板前必须确认的固件缺口（CanMV v1.8 实测不支持，别按文档硬写）
FW_LIMITS = (
    "Sensor.list_mode(lane_pref=)  -> unexpected keyword argument",
    "Sensor.get_id()               -> not support get_id now",
    "Sensor.get_framerate()        -> not support get_framerate now",
    "Sensor.focus_caps()           -> can't get sensor fd",
    "Sensor.set_colorbar()         -> not support set_colorbar now",
    "VICAP_MIPI_ANY/2LANE/4LANE    -> 未导出，用整数 0/1/2",
    "image.draw_string()           -> 已废弃，用 draw_string_advanced",
    "os.path                       -> MicroPython 侧不可用，用 listdir()/stat() 判断存在性",
)

# 本次标定数据集说明：320x240 灰度 JPEG，桌面赛道，已剔除人身遮挡帧
DATASET = dict(frames=328, id_range="1..600", missing=[597, 598, 628],
               rejected_frames=62, format="320x240 grayscale JPEG",
               note="桌面室内，含房间杂波，命中率不代表场地表现；完整帧集未入库")
