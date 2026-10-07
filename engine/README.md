# Revv Engine

The core of Revv: turns an EV battery's raw data into one independent
**State-of-Health (SoH) score** and a shareable certificate.

This is the product's moat. The UI, the OBD app, and any partner integration
all sit on top of this engine.

## Run it

From this `engine/` folder:

```bash
python demo.py                          # score 3 sample EVs, print certificates
python -m unittest discover -s tests    # run the test suite
```

No external libraries needed (pure Python 3.11+).

## How it works (v1)

A battery reading goes through five steps in `revv_engine/scoring.py`:

1. **Capacity-based SoH** — if we measured current full-charge capacity:
   `measured / rated`. The most direct truth.
2. **Model-based SoH** — an independent estimate from calendar age + usage
   cycles. This is our cross-check on what the car claims.
3. **Blend** — lean on the measurement, but let the model pull it if they
   disagree badly (a car can report its capacity optimistically).
4. **Health penalties** — subtract for real warning signs: cell imbalance,
   high internal resistance, heavy DC fast-charging, hot climate.
5. **Derive outputs** — range retained, remaining life, verdict, confidence.

### Honest caveat
v1 uses **published lithium-ion ageing numbers, not Revv's own measured data**
(we don't have that yet). Every constant lives in `AgeingParams` and the
threshold block in `scoring.py` — calibrating the engine later is a one-file
job. Confidence drops automatically when fewer real measurements are available.

## Layout

```
engine/
  revv_engine/
    models.py        # BatteryReading (input) + SoHResult (output)
    scoring.py       # the algorithm + all tunable constants
    certificate.py   # SoHResult -> certificate dict + pretty printout
  demo.py            # runnable end-to-end example
  tests/             # unittest suite
```

## Next on the engine

- Define the exact OBD data fields we can realistically read per car model.
- Collect real readings to calibrate `AgeingParams` and thresholds.
- Wrap `score_battery` in a small API so the app/dashboard can call it.
