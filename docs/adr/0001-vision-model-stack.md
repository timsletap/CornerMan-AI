# ADR 0001: Vision model stack

| | |
|---|---|
| Status | Proposed (owner decides the two license questions at the end) |
| Date | 2026-11-13 |
| Decides | Which detection, pose, 3D, tracking, and action models the product is built on, and which datasets may be used for what |
| Spec | FRD Section 25 |

## Context

The owner supplied a 16-step build plan naming GVHMR, YOLO26, RTMW, SAM 3, MMAction2, the BoxingVI dataset, and the Olympic boxing dataset, and asked for the best models with freedom to change them. The product is meant to be sold, so "best" has to mean best among the models that can legally ship.

## What was checked

Licenses were read from each project's own LICENSE file or README on 2026-11-13.

| Component | License | Can it ship in a paid, closed product? |
|---|---|---|
| Ultralytics YOLO (v8 today, v11, YOLO26) | AGPL-3.0 or paid Enterprise License | Not without the Enterprise License |
| GVHMR | "educational, research and non-profit purposes only"; commercial use by request to the authors | No |
| SMPL body model (GVHMR's output format) | Non-commercial research; commercial license sold by Meshcapade | No |
| RTMW, RTMPose, RTMW3D via `rtmlib` | Apache-2.0 code; weights trained on mixed public datasets | Yes for the code; weights need a lawyer's read |
| YOLOX | Apache-2.0 | Yes |
| RF-DETR Nano to Large | Apache-2.0 | Yes |
| ByteTrack | MIT | Yes |
| MMAction2 | Apache-2.0 | Yes |
| SAM 3 | SAM License (custom, royalty-free, restrictions, gated checkpoints) | Probably; needs a lawyer's read |
| BoxingVI | None stated | Measurement only |
| Olympic boxing dataset | Non-commercial per the derivative copy; original not yet read | Measurement only |

The largest finding is about the code that already exists: the pose model the app runs today is AGPL. That is fine for a portfolio project and a problem for a paid product.

## Decision

1. **Default pose stack: YOLOX detector, RTMW 2D whole-body pose, ByteTrack, all through ONNX Runtime.** It is permissive, it adds hand and foot keypoints the current model lacks, and it runs on the same runtime in the cloud and (later) on device.
2. **3D: RTMW3D first, a 2D-to-3D lifting model second. Not GVHMR.** GVHMR may be run locally as a research yardstick, never in the product.
3. **Ultralytics stays as a selectable backend** until the new stack matches it on the eval set, then leaves the default path.
4. **SAM 3 is optional and late.** Re-identification starts with an appearance embedding of the fighter crop, which is cheap; SAM 3 masks are a fallback to evaluate if that is not enough.
5. **Public datasets measure; they do not train what ships.** Training data is the owner's own footage and opt-in user footage.
6. **No swap on argument alone.** Each change lands with its eval delta.

## Evidence gathered so far

### Label-free pose comparison

`python -m perf.pose_compare` on five clips (four licensed Wikimedia clips and the golden clip, up to 450 frames each). Raw numbers: `docs/reports/pose_compare.json`.

| Backend | Device | fps | Person found | Wrist jitter on a still body (shoulder widths) |
|---|---|---|---|---|
| yolov8m-pose | CPU | 4.8 | 100% | 0.007 |
| rtmpose-m (17 keypoints) | GPU | 16.0 | 100% | 0.072 |
| rtmw-l (133 keypoints) | GPU | 10.6 | 100% | 0.109 |
| rtmw-x (133 keypoints) | GPU | 9.9 | 100% | 0.088 |

How to read it, and how not to:
- **Speed is not comparable across rows.** YOLO ran on CPU because the project environment had a CPU-only torch build at the time (now fixed). The RTM rows include a separate detector pass and one pose pass per person; the golden clip has four people in frame. Measured separately on the GPU: detector 27 ms per frame, RTMW-l 12 ms per person. Batching and TensorRT (PERF-01) are untested.
- **RTMW's raw keypoints shake about ten times more than YOLO's on a still body.** This is the one clear signal, and it is against the new stack. The likely cause is that a top-down model re-crops the person every frame from a detector box that itself moves. It must be handled in VIS-26 (smooth the box, or track and crop from the track) and re-measured, because strike detection runs on wrist speed.
- **Confidence columns are left out on purpose.** The two model families score keypoints on different scales, so "share of frames with confident wrists" is not a fair comparison.
- **None of this says which model finds punches better.** That needs labels.

### First labeled baseline (BoxingVI)

The ten published BoxingVI videos were fetched from their YouTube links, the annotations converted (`eval/public_sets/boxingvi.py`), and the first three annotated minutes of each scored with the current pipeline. Report: `data/public/boxingvi_180s.json` (git_sha `605b559`, ±150 ms match window).

**1,288 annotated punches** across the ten clips.

| Metric | Value |
|---|---|
| Strike detection | P 0.247, R 0.204, F1 0.223 (TP 263, FP 803, FN 1025) |
| Strike type, macro-F1 | 0.483 |
| — jab | F1 0.729 (n=111) |
| — cross | F1 0.659 (n=45) |
| — hook | F1 0.253 (n=48) |
| — uppercut | F1 0.293 (n=59) |
| — body_shot | F1 0.0 (n=0) |
| dropped_guard | F1 0.0 (TP 0, FP 876) |
| chicken_wing | F1 0.0 (TP 0, FP 632) |
| Identity switches | 0 across all ten clips |
| Throughput | stage 1: 1.86× real time; stages 2–3: 542.89× real time (RTX 5070 Laptop GPU) |

Two findings stand out:
- **Error detection is completely broken on this data.** Both error types have zero true positives (dropped_guard TP 0 / FP 876, chicken_wing TP 0 / FP 632): the detector fires constantly but never lands on a labeled error. Either the error labels are too sparse to match, or the error logic is wrong. This is a separate investigation from strike detection.
- **Strike type is dominated by jab/cross.** Hooks and uppercuts are detected at roughly a quarter of the F1 of jabs, and body shots never appear in the labels (n=0).

Caveats that apply to every BoxingVI number:
- Stance is assumed orthodox for all ten videos, because the dataset says lead or rear and gives no stance. Detection requires the same hand, so a southpaw boxer scores badly for a reason that has nothing to do with the model. A per-clip diagnosis (`data/boxingvi_diagnose.py`) flags v4, v6, and v10 as southpaw, but the evidence is mixed (v6 scores better orthodox, 0.25 vs 0.0), so the owner still needs to look at each video once.
- The annotation frame numbers are assumed to index the same frames as the files downloaded here. That is unverified.
- Videos are solo work (shadow, bag, instruction), not sparring. They say nothing about two-fighter tracking or about landed versus missed.
- The dataset has no license, so the report and excerpts stay under `data/` and are not committed.

## Consequences

- VIS-26 (pose backend interface and standalone tracker) is the next vision task; it is what lets RTMW be scored on the same baseline.
- The repo's on-device plan (RT-01) gets simpler: RTMPose and RTMW already ship as ONNX.
- If the new stack cannot match the current one after the jitter fix, the fallback is the Ultralytics Enterprise License. That is a cost decision for the owner, not a technical dead end.

## Open questions for the owner

1. Buy the Ultralytics Enterprise License, or migrate? (Default: migrate.)
2. Email the BoxingVI authors for training rights?
3. Confirm stance in the ten BoxingVI videos.
