# SimTimedInd — Timed Induction Saturation Simulator (Python)

SimTimedInd is a **discrete-time simulation** to analyze **saturation, blocking (wait time), and throughput** when multiple preparation stations (tables) attempt to **induct items onto a lower conveyor belt that never stops**.

It was built to answer a real sizing question:

> The customer has **14 tables** and does not meet the target. They want to expand to **22 tables**.  
> We need to demonstrate whether adding tables improves throughput, or if the bottleneck is the belt/spacing.

---

## ✅ What this project answers

For a given number of stations (e.g., **14 vs 22**), the simulation helps quantify:

- **Real throughput** (items/hour)
- **Per-station blocking** (who gets stuck and for how long)
- **Visual saturation near the end of the line** (tail view)
- Whether adding stations helps or if the **belt + spacing is the real constraint**
- How often operators need to **“squeeze”** (insert with reduced gap) to keep flow

---

## System model (high level)

### Items
Two item types flow on the belt:

- **Box / package** (blue)
- **Empty tote** (orange)

The belt moves at constant speed. Items occupy physical length on the belt.

### Stations (tables)
Each station has a fixed induction point on the belt.

Operational behavior:
- All stations start at the beginning of the simulation, but **not perfectly synchronized**:
  - Each station starts at a random time in a window (e.g. 0–20s).
- Each station repeats an infinite cycle (backlog is infinite):
  1. Prepare an order (**35s** total)
  2. When finished → produce **1 box** and sometimes **1 tote**
  3. Attempt to induct pending outputs onto the belt
     - If belt has space → induct
     - If not → **wait** (station becomes red, HUD shows `wait=...s`)
  4. **Only after all pending outputs are inducted** does the station start the next 35s order

### Ratio (totes vs boxes)
The intended flow ratio approximates:
- **1500 boxes/h**
- **1200 totes/h**
- Tote-to-box ratio ≈ **0.8**

The simulation enforces this deterministically over time (not random bursts), so long-run counts converge and boxes remain ≥ totes.

---

## Fixed customer constraints (DO NOT change in model)

These are considered fixed by the customer and should be treated as constants:

### Conveyor
- **Lower belt speed:** `22 m/min` (constant)
- Belt never stops

### Target demand (reference)
- **Total target:** `2700 items/h`
  - `1500 boxes/h`
  - `1200 totes/h`

### Operator timing
- Pick tote: `5s`
- Prepare: `25s`
- Close: `5s`
- **Total:** `35s` per order

### Minimum nominal gap
- **Nominal gap:** `100 mm` between items

### Item lengths
- **Tote:** `600 mm`
- **Box:** variable length, sampled from a normal distribution:
  - mean `366 mm`
  - stdev `70 mm`
  - clipped to `[200 mm, 550 mm]`

> Note: The meaning of the box mean value must be consistent with your spacing assumptions.
> If a previous calculation already embedded spacing into the “effective length”, avoid double-counting.

### Layout (stations in pairs)
Stations are arranged in pairs along the belt:

- M1–M2 together, then a longer gap, then M3–M4 together, etc.
- Distances used in code:
  - **Within pair:** `1.15 m`
  - **Between pairs:** `2.60 m`

---

## “Squeeze” rule (extra operational behavior)

When a station tries to induct but cannot respect the nominal gap of `100mm`:

1. Try inserting with `gap=100mm`
2. If it doesn’t fit → re-try with `gap=0mm` (no overlap, just no spacing)
3. If it still doesn’t fit (physical collision) → station must **wait**

The HUD counts how many insertions required a squeeze.

This is critical for sensitivity:
- If the simulation reaches target only with squeeze ON, it suggests real operation may frequently work with reduced spacing (or the gap assumption is not strict).

---

## Implementation overview

### Current state
The project currently runs as a single script:

- **`sim2d.py`**
  - Python + Tkinter 2D visualization
  - Discrete time-step simulation (DT = 0.05s)
  - Visual belt with moving rectangles:
    - **Blue** = box
    - **Orange** = tote
  - Induction posts per station
  - Station becomes **red** when blocked and shows `wait=...s`
  - HUD shows constants, targets, real throughput, counters (including squeeze usage)

### What the visualization represents
- The belt is a horizontal line
- Items move to the right at constant speed
- Each station inducts at its fixed x-position
- Tail view shows the last part of the conveyor to observe saturation

---

## How to run

### Requirements
- Python 3.10+ recommended
- Tkinter installed (usually bundled on Windows Python)

### Basic run (default = 22 stations, 1 hour simulation, real-time speed)
```bash
python sim2d.py --stations 22 --duration 3600 --speed 1.0 --view full --start_stagger 20
```
aster-than-real-time (simulate 1 hour in ~minutes for demos)
```bash
python sim2d.py --stations 22 --duration 3600 --speed 10 --view full --start_stagger 20
```
Compare 14 vs 22 stations
```bash
python sim2d.py --stations 14 --duration 3600 --speed 10 --view full --start_stagger 20
python sim2d.py --stations 22 --duration 3600 --speed 10 --view full --start_stagger 20
```
View only the tail (end of line saturation)
```bash
python sim2d.py --stations 22 --duration 3600 --speed 10 --view tail --start_stagger 20
```
---
## CLI arguments

| Argument          |            Type | Default | Description                                  |
| ----------------- | --------------: | ------: | -------------------------------------------- |
| `--stations`      |             int |      22 | number of preparation tables                 |
| `--duration`      |           float |    3600 | simulation duration in seconds               |
| `--speed`         |           float |     1.0 | simulation speed multiplier (UI runs faster) |
| `--view`          | `full` / `tail` |  `full` | full belt view or end-only view              |
| `--seed`          |             int |      42 | random seed (startup stagger + box lengths)  |
| `--start_stagger` |           float |    20.0 | random start window `[0..N]` seconds         |

---

## What “good” looks like

The expected diagnostic outcomes are:

14 stations

Often production-limited (operators can’t create enough items/h)

Lower congestion, but may still fail to hit 2700/h

22 stations

Production capacity is higher, so:

If belt/spacing is the bottleneck → tail saturates, stations near the end block heavily

If belt can handle it (gap effectively reduced) → throughput may improve

---

## Known past issues (fixed)

✅ Orders were finite per station → line “emptied” near the end
Fixed by using infinite backlog (continuous work).

✅ out_queue could be None and broke type checking
Fixed using field(default_factory=list).

✅ Layout was incorrect / inverted
Corrected to pair spacing: 1.15m within, 2.60m between.

✅ UI text overlap for wait labels
Mitigated using pair offsets + white background tags.

---

## Limitations (current)

The belt model is 1D in physics (x-axis only). The UI is 2D purely for visualization.

The simulation currently prioritizes correct operational logic over perfect physical fidelity.

No CSV export yet in the current script (planned).

No headless mode yet (planned) to run parameter sweeps without UI.

---

## Repo / environment

Developed on Windows using VS Code and Git Bash

Repo name: SimTimedInd

---

## License

Add your preferred license (MIT/Apache-2.0/etc.) if you plan to share publicly.
Otherwise leave as internal/private.

---
