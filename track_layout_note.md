# MagneMotion LITE Track Layout — Full Loop

**Date recorded:** 2026-08-07
**Source:** Thad freehand CAD/sketch with grid overlay

## Layout Notes
- Track is a single continuous LITE pallet conveyor loop with two cooling U-turns.
- Red guide line indicates the pallet travel path.
- Grid coordinates (X 0-1550, Y 0-650) give approximate relative positions; not all dimensions are precise because the sketch is freehand.

## Stations (read clockwise from lower-right U-turn)

| # | Station Name | Color / Region | Approx Grid Area |
|---|---|---|---|
| 6 | Mold 1 Cooling | Blue U-turn, bottom-right | X 1300-1550, Y 250-600 |
| 30 | Mold Direction Check | Curve exiting blue U-turn | X 1150-1450, Y 250-300 |
| 26 | Roller Test 6 | Straight section | X 900-1200, Y 150-250 |
| 18 | Insp Pin 1 | Straight section | X 750-900, Y 100-200 |
| 16 | Load Pin | Straight section | X 650-800, Y 100-200 |
| 14 | Load Roller | Straight section | X 500-700, Y 50-150 |
| 13 | Pre-Load Roller | Straight section | X 400-600, Y 50-150 |
| 33 | HOME / Cold Start | Straight section after merge | X 300-500, Y 100-250 |
| 34 | Cleanout | Merge/diverge area | X 350-450, Y 150-250 |
| 12 | Mold 2 Cooling | Purple U-turn, left side | X 100-350, Y 200-500 |

## Operational Observations
- Two cooling stations: Mold 1 (right/blue) and Mold 2 (left/purple).
- Load sequence is at top straight: Pre-Load Roller → Load Roller → Load Pin → Insp Pin 1.
- HOME / Cold Start and Cleanout are near the merge between the purple cooling loop and the main straight.
- Direction check after Mold 1 cooling ensures pallets are oriented correctly before re-entering the load section.

## For Monitor UI
- Use this layout as the basis for a schematic station map.
- Pallet position can be plotted roughly using the grid coordinates until exact encoder/segment distances are available from the PLC.
- Need to confirm whether station numbering in the PLC matches these labels exactly or uses different tag names.
