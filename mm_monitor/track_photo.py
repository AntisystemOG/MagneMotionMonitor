"""Pixel-space calibration for the rendered S7000 track layout.

Background: mm_monitor/data/track_photo.png is a cleaned render of the user's
freehand full_track_grid.png. The red grid overlay was removed and the image
white-balanced/levelled so the background is neutral and the rails are clear.

Waypoints: PATH_WAYPOINTS_PX was manually traced along the top edge of each
rail extrusion so carts/pallets ride on the top of the track. The six PLC
paths are split at the real rail junctions:
  Path 6 (Process)         -> full top rail incl. both end curves
  Path 3 (unnamed connector)-> long straight lower rail (HOME / Cleanout)
  Path 4 (Mold 2)           -> LEFT U-shaped spur
  Path 2 (Mold 1)           -> RIGHT U-shaped spur
  Path 1 (Mold 1 Entry/Exit)-> tiny right junction connector
  Path 5 (Mold 2 Entry/Exit)-> tiny left junction connector / Cleanout stub

REAL_TO_PIXEL_BREAKPOINTS are identity for paths 2 and 4 in this render; the
waypoints already encode the U-turn geometry. If cart pacing through the mold
loops looks wrong compared to the real machine, recalibrate from
track_geometry's real segment lengths.
"""
from __future__ import annotations
import csv
import math
from pathlib import Path

# Native pixel size of mm_monitor/data/track_photo.png. The renderer scales this
# (uniformly, letterboxed) to fit whatever widget size it's drawn into.
PHOTO_SIZE = (1584, 672)

# Per-path waypoints in PHOTO-NATIVE pixel space, IN THE SAME ORDER the vehicle
# travels that path (arc-length order). A cart's fractional position along its
# real path (pos_m / path_length_m) is mapped to the same fraction of distance
# along this pixel polyline — so absolute pixel spacing doesn't need to exactly
# match real-world scale, only the relative shape/order needs to be right.
PATH_WAYPOINTS_PX: dict[int, list[tuple[float, float]]] = {
    1: [
        (1504.6, 159.1), (1504.6, 159.1), (1504.7, 165.1),
        (1504.9, 171.1), (1505.0, 177.1), (1505.2, 183.1),
        (1505.3, 189.1), (1505.5, 195.1), (1505.6, 201.1),
        (1505.8, 207.1), (1505.8, 208.1),
    ],
    2: [
        (1505.8, 208.1), (1505.8, 208.1), (1506.1, 214.1),
        (1506.4, 220.1), (1506.8, 226.1), (1507.1, 232.1),
        (1507.4, 238.1), (1507.7, 244.0), (1508.0, 250.0),
        (1508.4, 256.0), (1508.7, 262.0), (1509.0, 268.0),
        (1509.3, 274.0), (1509.6, 280.0), (1510.0, 286.0),
        (1510.3, 292.0), (1510.6, 298.0), (1510.4, 304.0),
        (1510.2, 310.0), (1510.0, 316.0), (1509.7, 322.0),
        (1509.5, 328.0), (1509.3, 333.9), (1509.1, 339.9),
        (1508.9, 345.9), (1508.7, 351.9), (1508.4, 357.9),
        (1508.2, 363.9), (1508.0, 369.9), (1507.8, 375.9),
        (1507.6, 381.9), (1507.4, 387.9), (1507.2, 393.9),
        (1506.9, 399.9), (1506.7, 405.9), (1506.5, 411.9),
        (1506.3, 417.9), (1506.1, 423.9), (1505.9, 429.9),
        (1505.6, 435.9), (1505.4, 441.9), (1505.2, 447.9),
        (1505.0, 453.9), (1504.8, 459.9), (1504.6, 465.9),
        (1504.3, 471.9), (1504.1, 477.9), (1503.9, 483.9),
        (1503.7, 489.8), (1503.5, 495.8), (1503.3, 501.8),
        (1503.1, 507.8), (1502.8, 513.8), (1502.6, 519.8),
        (1502.4, 525.8), (1502.2, 531.8), (1502.0, 537.8),
        (1501.8, 543.8), (1501.5, 549.8), (1501.3, 555.8),
        (1501.1, 561.8), (1500.9, 567.8), (1500.7, 573.8),
        (1500.5, 579.8), (1500.2, 585.8), (1500.0, 591.8),
        (1499.8, 597.8), (1499.6, 603.8), (1498.4, 609.4),
        (1492.5, 610.4), (1486.6, 611.5), (1480.7, 612.6),
        (1474.8, 613.6), (1468.9, 614.7), (1463.0, 615.7),
        (1457.1, 616.8), (1451.7, 616.9), (1449.3, 611.4),
        (1447.0, 605.8), (1444.7, 600.3), (1442.4, 594.8),
        (1440.1, 589.2), (1437.7, 583.7), (1435.4, 578.2),
        (1433.5, 572.6), (1433.5, 566.6), (1433.5, 560.6),
        (1433.6, 554.6), (1433.6, 548.6), (1433.6, 542.6),
        (1433.6, 536.6), (1433.6, 530.6), (1433.7, 524.6),
        (1433.7, 518.6), (1433.7, 512.6), (1433.7, 506.6),
        (1433.7, 500.6), (1433.8, 494.6), (1433.8, 488.6),
        (1433.8, 482.6), (1433.8, 476.6), (1433.8, 470.6),
        (1433.8, 464.6), (1433.9, 458.6), (1433.9, 452.6),
        (1433.9, 446.6), (1433.9, 440.6), (1433.9, 434.6),
        (1434.0, 428.6), (1434.0, 422.6), (1434.0, 416.6),
        (1434.0, 410.6), (1434.0, 404.6), (1434.1, 398.6),
        (1434.1, 392.6), (1434.1, 386.6), (1434.1, 380.6),
        (1434.1, 374.6), (1434.2, 368.6), (1434.2, 362.6),
        (1434.2, 356.6), (1434.2, 350.6), (1434.2, 344.6),
        (1434.3, 338.6), (1434.3, 332.6), (1434.3, 326.6),
        (1434.3, 320.6), (1434.3, 314.6), (1434.3, 308.6),
        (1434.4, 302.6), (1434.4, 296.6), (1434.4, 290.6),
        (1434.4, 284.6), (1434.4, 278.6), (1434.5, 272.6),
        (1434.5, 266.6), (1434.5, 260.6), (1434.5, 254.6),
        (1434.5, 248.6), (1434.6, 242.6), (1434.6, 236.6),
        (1434.6, 230.6), (1434.6, 224.6), (1434.6, 218.6),
        (1434.7, 212.6), (1434.7, 206.6), (1434.7, 200.6),
        (1434.7, 194.6), (1434.7, 188.6), (1434.8, 182.6),
        (1434.8, 176.6), (1434.8, 170.6), (1434.8, 168.0),
    ],
    3: [
        (1434.8, 168.0), (1434.8, 168.0), (1428.8, 167.9),
        (1422.8, 167.9), (1416.8, 167.8), (1410.8, 167.7),
        (1404.8, 167.6), (1398.8, 167.6), (1392.8, 167.5),
        (1386.8, 167.4), (1380.8, 167.4), (1374.8, 167.3),
        (1368.8, 167.2), (1362.8, 167.2), (1356.8, 167.1),
        (1350.8, 167.0), (1344.8, 166.9), (1338.8, 166.9),
        (1332.8, 166.8), (1326.8, 166.7), (1320.8, 166.7),
        (1314.8, 166.6), (1308.8, 166.5), (1302.8, 166.4),
        (1296.8, 166.4), (1290.8, 166.3), (1284.8, 166.2),
        (1278.8, 166.2), (1272.8, 166.1), (1266.8, 166.0),
        (1260.8, 166.0), (1254.8, 165.9), (1248.8, 165.8),
        (1242.8, 165.7), (1236.8, 165.7), (1230.8, 165.6),
        (1224.8, 165.5), (1218.8, 165.5), (1212.8, 165.4),
        (1206.8, 165.3), (1200.8, 165.3), (1194.8, 165.2),
        (1188.8, 165.1), (1182.8, 165.0), (1176.8, 165.0),
        (1170.8, 164.9), (1164.8, 164.8), (1158.8, 164.8),
        (1152.8, 164.7), (1146.8, 164.6), (1140.8, 164.5),
        (1134.8, 164.5), (1128.8, 164.4), (1122.8, 164.3),
        (1116.8, 164.3), (1110.8, 164.2), (1104.8, 164.1),
        (1098.8, 164.1), (1092.8, 164.0), (1086.8, 163.9),
        (1080.8, 163.8), (1074.8, 163.8), (1068.8, 163.7),
        (1062.8, 163.6), (1056.8, 163.6), (1050.8, 163.5),
        (1044.8, 163.4), (1038.8, 163.3), (1032.8, 163.3),
        (1026.8, 163.2), (1020.8, 163.1), (1014.8, 163.1),
        (1008.8, 163.0), (1002.8, 162.9), (996.8, 162.9),
        (990.8, 162.8), (984.8, 162.7), (978.8, 162.6),
        (972.8, 162.6), (966.8, 162.5), (960.8, 162.4),
        (954.8, 162.4), (948.8, 162.3), (942.8, 162.2),
        (936.8, 162.1), (930.8, 162.1), (924.8, 162.0),
        (918.8, 161.9), (912.8, 161.9), (906.8, 161.8),
        (900.8, 161.7), (894.8, 161.7), (888.8, 161.6),
        (882.8, 161.5), (876.8, 161.4), (870.8, 161.4),
        (864.8, 161.3), (858.8, 161.2), (852.8, 161.2),
        (846.8, 161.1), (840.8, 161.0), (834.8, 160.9),
        (828.8, 160.9), (822.8, 160.8), (816.8, 160.7),
        (810.8, 160.7), (804.8, 160.6), (798.8, 160.5),
        (792.8, 160.5), (786.8, 160.4), (780.8, 160.3),
        (774.8, 160.2), (768.8, 160.2), (762.8, 160.1),
        (756.8, 160.0), (750.8, 160.0), (744.8, 159.9),
        (738.8, 159.8), (732.8, 159.8), (726.8, 159.7),
        (720.8, 159.6), (714.8, 159.5), (708.9, 159.5),
        (702.9, 159.4), (696.9, 159.3), (690.9, 159.3),
        (684.9, 159.2), (678.9, 159.1), (672.9, 159.0),
        (666.9, 159.0), (660.9, 158.9), (654.9, 158.8),
        (648.9, 158.8), (642.9, 158.7), (636.9, 158.6),
        (630.9, 158.6), (624.9, 158.5), (618.9, 158.4),
        (612.9, 158.3), (606.9, 158.3), (600.9, 158.2),
        (594.9, 158.1), (588.9, 158.1), (582.9, 158.0),
        (576.9, 157.9), (570.9, 157.8), (564.9, 157.8),
        (558.9, 157.7), (552.9, 157.6), (546.9, 157.6),
        (540.9, 157.5), (534.9, 157.4), (528.9, 157.4),
        (522.9, 157.3), (516.9, 157.2), (510.9, 157.1),
        (504.9, 157.1), (498.9, 157.0), (492.9, 156.9),
        (486.9, 156.9), (480.9, 156.8), (474.9, 156.7),
        (473.2, 156.7),
    ],
    4: [
        (473.2, 156.7), (473.2, 156.7), (473.2, 162.7),
        (473.2, 168.7), (473.2, 174.7), (473.1, 180.7),
        (473.1, 186.7), (473.1, 192.7), (473.1, 198.7),
        (473.1, 204.7), (473.1, 210.7), (473.1, 216.7),
        (473.1, 222.7), (473.0, 228.7), (473.0, 234.7),
        (473.0, 240.7), (473.0, 246.7), (473.0, 252.7),
        (473.0, 258.7), (473.0, 264.7), (473.0, 270.7),
        (472.9, 276.7), (472.9, 282.7), (472.9, 288.7),
        (472.9, 294.7), (472.9, 300.7), (472.9, 306.7),
        (472.9, 312.7), (472.8, 318.7), (472.8, 324.7),
        (472.8, 330.7), (472.8, 336.7), (472.8, 342.7),
        (472.8, 348.7), (472.8, 354.7), (472.8, 360.7),
        (472.7, 366.7), (472.7, 372.7), (472.7, 378.7),
        (472.7, 384.7), (472.7, 390.7), (472.7, 396.7),
        (472.7, 402.7), (472.6, 408.7), (472.6, 414.7),
        (472.6, 420.7), (472.6, 426.7), (472.6, 432.7),
        (472.6, 438.7), (472.6, 444.7), (472.6, 450.7),
        (472.5, 456.7), (472.5, 462.7), (472.5, 468.7),
        (472.5, 474.7), (472.5, 480.7), (472.5, 486.7),
        (472.5, 492.7), (472.5, 498.7), (472.4, 504.7),
        (472.4, 510.7), (472.4, 516.7), (472.4, 522.7),
        (472.4, 528.7), (472.4, 534.7), (472.4, 540.7),
        (472.3, 546.7), (472.3, 552.7), (472.3, 558.7),
        (472.3, 564.7), (472.3, 570.7), (472.3, 576.7),
        (472.3, 582.7), (472.3, 588.7), (472.2, 594.7),
        (472.2, 600.7), (472.2, 606.7), (472.2, 612.7),
        (477.9, 614.5), (483.6, 616.3), (489.3, 618.2),
        (495.1, 620.0), (500.8, 621.8), (506.5, 623.6),
        (511.6, 623.1), (515.5, 618.6), (519.4, 614.1),
        (523.3, 609.5), (527.3, 605.0), (531.2, 600.5),
        (535.1, 595.9), (536.8, 590.5), (536.9, 584.5),
        (536.9, 578.5), (537.0, 572.5), (537.1, 566.5),
        (537.1, 560.5), (537.2, 554.5), (537.2, 548.5),
        (537.3, 542.5), (537.3, 536.6), (537.4, 530.6),
        (537.5, 524.6), (537.5, 518.6), (537.6, 512.6),
        (537.6, 506.6), (537.7, 500.6), (537.7, 494.6),
        (537.8, 488.6), (537.9, 482.6), (537.9, 476.6),
        (538.0, 470.6), (538.0, 464.6), (538.1, 458.6),
        (538.1, 452.6), (538.2, 446.6), (538.3, 440.6),
        (538.3, 434.6), (538.4, 428.6), (538.4, 422.6),
        (538.5, 416.6), (538.5, 410.6), (538.6, 404.6),
        (538.6, 398.6), (538.7, 392.6), (538.8, 386.6),
        (538.8, 380.6), (538.9, 374.6), (538.9, 368.6),
        (539.0, 362.6), (539.0, 356.6), (539.1, 350.6),
        (539.2, 344.6), (539.2, 338.6), (539.3, 332.6),
        (539.3, 326.6), (539.4, 320.6), (539.4, 314.6),
        (539.5, 308.6), (539.6, 302.6), (539.6, 296.6),
        (539.7, 290.6), (539.7, 284.6), (539.8, 278.6),
        (539.8, 272.6), (539.9, 266.6), (540.0, 260.6),
        (540.0, 254.6), (540.1, 248.6), (540.1, 242.6),
        (540.2, 236.6), (540.2, 230.6), (540.3, 224.6),
        (540.3, 218.6), (540.4, 212.6), (540.5, 206.6),
        (540.5, 200.6), (540.6, 194.6), (543.1, 189.6),
        (547.4, 185.5), (551.7, 181.3), (556.0, 177.1),
        (560.4, 173.0), (564.7, 168.8), (569.0, 164.7),
        (569.8, 159.3),
    ],
    5: [
        (569.8, 159.3), (569.8, 159.3), (563.8, 159.7),
        (557.8, 160.1), (551.9, 159.8), (546.0, 158.5),
        (540.2, 157.1), (537.9, 156.5),
    ],
    6: [
        (537.9, 156.5), (537.9, 156.5), (531.9, 156.5),
        (525.9, 156.4), (519.9, 156.4), (513.9, 156.3),
        (507.9, 156.3), (501.9, 156.2), (495.9, 156.2),
        (489.9, 156.1), (483.9, 156.1), (477.9, 156.0),
        (471.9, 155.9), (465.9, 155.9), (459.9, 155.8),
        (453.9, 155.8), (447.9, 155.7), (441.9, 155.7),
        (435.9, 155.6), (429.9, 155.6), (423.9, 155.5),
        (417.9, 155.5), (411.9, 155.4), (405.9, 155.3),
        (399.9, 155.3), (393.9, 155.2), (387.9, 155.2),
        (381.9, 155.1), (375.9, 155.1), (369.9, 155.0),
        (363.9, 155.0), (357.9, 154.9), (351.9, 154.8),
        (345.9, 154.8), (339.9, 154.7), (333.9, 154.7),
        (327.9, 154.6), (321.9, 154.6), (315.9, 154.5),
        (309.9, 154.5), (303.9, 154.4), (297.9, 154.4),
        (291.9, 154.3), (285.9, 154.2), (279.9, 154.2),
        (273.9, 154.1), (267.9, 154.1), (261.9, 154.0),
        (255.9, 154.0), (249.9, 153.9), (243.9, 153.9),
        (237.9, 153.8), (231.9, 153.8), (225.9, 153.7),
        (219.9, 153.6), (213.9, 153.6), (207.9, 153.5),
        (201.9, 153.5), (195.9, 153.4), (189.9, 153.4),
        (183.9, 153.3), (177.9, 153.3), (171.9, 153.2),
        (165.9, 153.2), (159.9, 153.1), (153.9, 153.0),
        (147.9, 153.0), (141.9, 152.9), (135.9, 152.9),
        (129.9, 152.8), (123.9, 152.8), (117.9, 152.7),
        (111.9, 152.7), (105.9, 152.6), (99.9, 152.6),
        (93.9, 152.5), (87.9, 152.4), (82.0, 152.1),
        (76.3, 150.2), (70.6, 148.3), (64.9, 146.4),
        (59.2, 144.6), (53.5, 142.7), (48.9, 140.0),
        (48.8, 134.0), (48.8, 128.0), (48.7, 122.0),
        (48.7, 116.0), (48.6, 110.0), (48.5, 104.0),
        (49.8, 98.9), (55.3, 96.4), (60.8, 93.9),
        (66.2, 91.4), (71.7, 88.9), (77.1, 86.4),
        (82.6, 84.0), (88.3, 82.4), (94.3, 82.5),
        (100.3, 82.5), (106.3, 82.6), (112.3, 82.6),
        (118.3, 82.7), (124.3, 82.8), (130.3, 82.8),
        (136.3, 82.9), (142.3, 82.9), (148.3, 83.0),
        (154.3, 83.0), (160.3, 83.1), (166.3, 83.1),
        (172.3, 83.2), (178.3, 83.3), (184.3, 83.3),
        (190.3, 83.4), (196.3, 83.4), (202.3, 83.5),
        (208.3, 83.5), (214.3, 83.6), (220.3, 83.6),
        (226.3, 83.7), (232.3, 83.8), (238.3, 83.8),
        (244.3, 83.9), (250.3, 83.9), (256.3, 84.0),
        (262.3, 84.0), (268.3, 84.1), (274.3, 84.1),
        (280.3, 84.2), (286.3, 84.3), (292.3, 84.3),
        (298.3, 84.4), (304.3, 84.4), (310.3, 84.5),
        (316.3, 84.5), (322.3, 84.6), (328.3, 84.6),
        (334.3, 84.7), (340.3, 84.8), (346.2, 84.8),
        (352.2, 84.9), (358.2, 84.9), (364.2, 85.0),
        (370.2, 85.0), (376.2, 85.1), (382.2, 85.1),
        (388.2, 85.2), (394.2, 85.3), (400.2, 85.3),
        (406.2, 85.4), (412.2, 85.4), (418.2, 85.5),
        (424.2, 85.5), (430.2, 85.6), (436.2, 85.6),
        (442.2, 85.7), (448.2, 85.8), (454.2, 85.8),
        (460.2, 85.9), (466.2, 85.9), (472.2, 86.0),
        (478.2, 86.0), (484.2, 86.1), (490.2, 86.1),
        (496.2, 86.2), (502.2, 86.3), (508.2, 86.3),
        (514.2, 86.4), (520.2, 86.4), (526.2, 86.5),
        (532.2, 86.5), (538.2, 86.6), (544.2, 86.6),
        (550.2, 86.7), (556.2, 86.8), (562.2, 86.8),
        (568.2, 86.9), (574.2, 86.9), (580.2, 87.0),
        (586.2, 87.0), (592.2, 87.1), (598.2, 87.1),
        (604.2, 87.2), (610.2, 87.3), (616.2, 87.3),
        (622.2, 87.4), (628.2, 87.4), (634.2, 87.5),
        (640.2, 87.5), (646.2, 87.6), (652.2, 87.6),
        (658.2, 87.7), (664.2, 87.8), (670.2, 87.8),
        (676.2, 87.9), (682.2, 87.9), (688.2, 88.0),
        (694.2, 88.0), (700.2, 88.1), (706.2, 88.1),
        (712.2, 88.2), (718.2, 88.3), (724.2, 88.3),
        (730.2, 88.4), (736.2, 88.4), (742.2, 88.5),
        (748.2, 88.5), (754.2, 88.6), (760.2, 88.6),
        (766.2, 88.7), (772.2, 88.8), (778.2, 88.8),
        (784.2, 88.9), (790.2, 88.9), (796.2, 89.0),
        (802.2, 89.0), (808.2, 89.1), (814.2, 89.1),
        (820.2, 89.2), (826.2, 89.3), (832.2, 89.3),
        (838.2, 89.4), (844.2, 89.4), (850.2, 89.5),
        (856.2, 89.5), (862.2, 89.6), (868.2, 89.6),
        (874.2, 89.7), (880.2, 89.8), (886.2, 89.8),
        (892.2, 89.9), (898.2, 89.9), (904.2, 90.0),
        (910.2, 90.0), (916.2, 90.1), (922.2, 90.1),
        (928.2, 90.2), (934.2, 90.3), (940.2, 90.3),
        (946.2, 90.4), (952.2, 90.4), (958.2, 90.5),
        (964.2, 90.5), (970.2, 90.6), (976.2, 90.6),
        (982.2, 90.7), (988.2, 90.8), (994.2, 90.8),
        (1000.2, 90.9), (1006.2, 90.9), (1012.2, 91.0),
        (1018.2, 91.0), (1024.2, 91.1), (1030.2, 91.2),
        (1036.2, 91.2), (1042.2, 91.3), (1048.2, 91.3),
        (1054.2, 91.4), (1060.2, 91.4), (1066.2, 91.5),
        (1072.2, 91.5), (1078.2, 91.6), (1084.2, 91.7),
        (1090.2, 91.7), (1096.2, 91.8), (1102.2, 91.8),
        (1108.2, 91.9), (1114.2, 91.9), (1120.2, 92.0),
        (1126.2, 92.0), (1132.2, 92.1), (1138.2, 92.2),
        (1144.2, 92.2), (1150.2, 92.3), (1156.2, 92.3),
        (1162.2, 92.4), (1168.2, 92.4), (1174.2, 92.5),
        (1180.2, 92.5), (1186.2, 92.6), (1192.2, 92.7),
        (1198.2, 92.7), (1204.2, 92.8), (1210.2, 92.8),
        (1216.2, 92.9), (1222.2, 92.9), (1228.2, 93.0),
        (1234.2, 93.0), (1240.2, 93.1), (1246.2, 93.2),
        (1252.2, 93.2), (1258.2, 93.3), (1264.2, 93.3),
        (1270.2, 93.4), (1276.2, 93.4), (1282.2, 93.5),
        (1288.2, 93.5), (1294.2, 93.6), (1300.2, 93.7),
        (1306.2, 93.7), (1312.2, 93.8), (1318.2, 93.8),
        (1324.2, 93.9), (1330.2, 93.9), (1336.2, 94.0),
        (1342.2, 94.0), (1348.2, 94.1), (1354.2, 94.2),
        (1360.2, 94.2), (1366.2, 94.3), (1372.2, 94.3),
        (1378.2, 94.4), (1384.2, 94.4), (1390.2, 94.5),
        (1396.2, 94.5), (1402.2, 94.6), (1408.2, 94.7),
        (1414.2, 94.7), (1420.2, 94.8), (1426.2, 94.8),
        (1432.2, 94.9), (1438.2, 94.9), (1444.2, 95.0),
        (1450.2, 95.0), (1456.2, 95.1), (1462.2, 95.2),
        (1468.2, 95.2), (1474.2, 95.3), (1479.6, 96.8),
        (1483.9, 101.0), (1488.3, 105.1), (1492.6, 109.2),
        (1497.0, 113.4), (1501.3, 117.5), (1505.6, 121.7),
        (1506.4, 127.2), (1506.1, 133.2), (1505.7, 139.2),
        (1505.4, 145.2), (1505.1, 151.2), (1504.7, 157.2),
        (1504.6, 159.1),
    ],
}


def _cumulative_lengths(pts: list[tuple[float, float]]) -> list[float]:
    s = [0.0]
    for a, b in zip(pts, pts[1:]):
        s.append(s[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    return s


# Mold spurs (paths 2 & 4): the real path is leg → U-turn → leg, and the
# U-turn is a genuinely SHORT slice of the real length (the two 90° curves
# that make up the 180° turn are only ~8% of the path — see
# track_geometry.build_track()'s segment lengths). But the PHOTOGRAPHED curve's
# pixel-arc-length share is much larger (measured ~19-21%), because the real
# curve is a tight radius while the physical rail's visible turn spans a much
# wider arc in the photo. Mapping "real fraction" straight onto "pixel
# fraction" 1:1 therefore put anything past the turn (e.g. a mold's Load 2
# station, or a cart mid-transit) noticeably further along the pixel path than
# it should be — reported as "the label should be higher up" and "carts take
# a weird route around the bend".
#
# REAL_TO_PIXEL_BREAKPOINTS: previous photos needed a piecewise correction
# because the traced U-turn on paths 2/4 occupied a much larger share of
# pixel arc-length than of real length. In the current full_track_grid.png
# render the waypoints are dense enough that the U-turn is encoded directly,
# so identity mapping (no correction) is correct. If future photos need the
# correction again, recompute anchors from the measured pixel arc-length of
# the leg/curve transitions versus track_geometry's real segment lengths.
REAL_TO_PIXEL_BREAKPOINTS: dict[int, list[tuple[float, float]]] = {
    2: [(0.0, 0.0), (1.0, 1.0)],
    4: [(0.0, 0.0), (1.0, 1.0)],
}


def _remap_fraction(frac: float, breakpoints: list[tuple[float, float]]) -> float:
    """Piecewise-linear remap of a real-position fraction to the pixel-arc-length
    fraction it should correspond to, given known (real, pixel) anchor points."""
    if frac <= breakpoints[0][0]:
        return breakpoints[0][1]
    if frac >= breakpoints[-1][0]:
        return breakpoints[-1][1]
    for (r0, p0), (r1, p1) in zip(breakpoints, breakpoints[1:]):
        if r0 <= frac <= r1:
            t = 0.0 if r1 <= r0 else (frac - r0) / (r1 - r0)
            return p0 + (p1 - p0) * t
    return frac   # unreachable given the bounds checks above


def load_adjusted_station_pixels(
    photo_path: Path | None = None,
    csv_path: Path | None = None,
) -> dict[str, tuple[float, float]]:
    """Load hand-adjusted station pixel positions from the alignment tool output.

    The Track Alignment tool writes track_points_adjusted.csv with Station +
    PixelX + PixelY. If that file exists, the main app uses those exact pixel
    positions for station markers instead of deriving them from the waypoint
    polyline, because the CSV represents the user's final visual placement.

    Search order:
      1. Explicit csv_path if provided.
      2. Same directory as the track photo: <photo_dir>/track_points_adjusted.csv
      3. The Track Alignment program folder next to the project.
    Returns an empty dict if no CSV is found or it has no usable rows.
    """
    candidates: list[Path] = []
    if csv_path is not None:
        candidates.append(csv_path)
    if photo_path is not None:
        candidates.append(photo_path.parent / "track_points_adjusted.csv")
    project_dir = Path(r"C:\AI Projects\MagneMotionMonitor")
    candidates.append(project_dir / "Track Alignment program" / "track_points_adjusted.csv")

    for path in candidates:
        if not path.exists():
            continue
        out: dict[str, tuple[float, float]] = {}
        try:
            with open(path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = row.get("Station", "").strip()
                    if not name:
                        continue
                    try:
                        x = float(row.get("PixelX", ""))
                        y = float(row.get("PixelY", ""))
                    except ValueError:
                        continue
                    out[name] = (x, y)
        except Exception:
            continue
        if out:
            return out
    return {}


# Cached adjusted station positions, loaded lazily.
_adjusted_station_pixels: dict[str, tuple[float, float]] | None = None


def get_adjusted_station_pixels(
    photo_path: Path | None = None,
    csv_path: Path | None = None,
) -> dict[str, tuple[float, float]]:
    """Cached wrapper for load_adjusted_station_pixels."""
    global _adjusted_station_pixels
    if _adjusted_station_pixels is None:
        _adjusted_station_pixels = load_adjusted_station_pixels(photo_path, csv_path)
    return _adjusted_station_pixels


class PhotoTrackModel:
    """Same query shape as track_geometry.TrackModel (point_at(path, pos_m)) but
    returns photo-native pixel coordinates instead of schematic meter-coordinates,
    using the hand-calibrated waypoints above."""

    def __init__(self, real_lengths: dict[int, float]):
        # real_lengths: path_id -> real length in meters (from track_geometry's
        # already-correct, motor-derived path lengths) — used only to convert a
        # cart's real position into a 0..1 fraction; see module docstring.
        self._real_lengths = real_lengths
        self._pts: dict[int, list[tuple[float, float]]] = {}
        self._s: dict[int, list[float]] = {}
        for pid, waypoints in PATH_WAYPOINTS_PX.items():
            self._pts[pid] = waypoints
            self._s[pid] = _cumulative_lengths(waypoints)

    def pixel_length(self, path_id: int) -> float:
        """Total pixel arc-length of a path's waypoint polyline (0 if unknown)."""
        s = self._s.get(path_id)
        return s[-1] if s else 0.0

    def pixel_s_at(self, path_id: int, pos_m: float) -> float | None:
        """Map a real meter-position to its position along the pixel polyline,
        measured as PIXEL arc-length (0 .. pixel_length). This is the same
        quantity `point_at` walks to — exposed so the pallet-spacing resolver
        (see track_panel.resolve_pallet_spacing) can enforce a minimum on-screen
        gap between carts in real pixel distance, not in meters (a fixed meter
        gap would be a wildly different pixel gap on the tight U-turn vs. a
        straight leg)."""
        s = self._s.get(path_id)
        if not s or s[-1] <= 0:
            return None
        real_len = self._real_lengths.get(path_id, 0.0)
        frac = 0.0 if real_len <= 0 else max(0.0, min(1.0, pos_m / real_len))
        breakpoints = REAL_TO_PIXEL_BREAKPOINTS.get(path_id)
        if breakpoints:
            frac = _remap_fraction(frac, breakpoints)
        return frac * s[-1]

    def point_at_pixel_s(self, path_id: int, pix_s: float) -> tuple[float, float] | None:
        """Return (x, y) for a given PIXEL arc-length along a path's polyline.
        The inverse of pixel_s_at for rendering: the spacing resolver adjusts a
        cart's pix_s to avoid overlap, then this places it back on the rail."""
        pts = self._pts.get(path_id)
        s = self._s.get(path_id)
        if not pts or not s or s[-1] <= 0:
            return None
        target = max(0.0, min(pix_s, s[-1]))
        lo, hi = 0, len(s) - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if s[mid] <= target:
                lo = mid
            else:
                hi = mid
        seg_len = s[hi] - s[lo]
        t = 0.0 if seg_len <= 0 else (target - s[lo]) / seg_len
        a, b = pts[lo], pts[hi]
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    def point_at(self, path_id: int, pos_m: float) -> tuple[float, float] | None:
        pix_s = self.pixel_s_at(path_id, pos_m)
        if pix_s is None:
            return None
        return self.point_at_pixel_s(path_id, pix_s)


_cached_model: PhotoTrackModel | None = None


def build_photo_track_model() -> PhotoTrackModel:
    """Build (and cache) the photo track model, using real path lengths from the
    authoritative schematic geometry so fractional positioning is correct."""
    global _cached_model
    if _cached_model is None:
        from .track_geometry import build_track
        track = build_track()
        real_lengths = {pid: pg.length for pid, pg in track.paths.items()}
        _cached_model = PhotoTrackModel(real_lengths)
    return _cached_model
