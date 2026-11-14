# Datasets and footage

Where the footage and labels come from, what each source may be used for, and how to fetch it. Nothing listed here is committed to the repository: clips, excerpts, labels, and reports derived from unlicensed data stay under `data/` or `eval/clips/`, both gitignored.

The rule (FRD Section 25.1): a source may **train** a shipped model only if the owner has the rights; any published research set may be used to **measure**, locally.

| Source | What it gives | License | Train a shipped model? | Measure locally? | Status |
|---|---|---|---|---|---|
| Owner's own footage, with written consent from everyone in it | Everything, including two-fighter sparring and outcomes | Owner's | Yes | Yes | **Not started. This is the footage that matters most** |
| Opt-in user uploads (ML-04) | Phone footage as real users film it | Per consent | Yes, for consenting users | Yes | After M8 |
| Licensed clip collector (`python -m tools.collect`, COLLECT-01) | Public-domain and Creative Commons clips | Per clip, recorded in `eval/clips/manifest.jsonl` | Depends on the clip (CC-BY and CC0 yes; SA and NC need care) | Yes | 18 clips; see the note below |
| BoxingVI (arXiv 2511.16524) | 10 videos of solo boxing with punch start, end, and one of six classes; about 5,500 punches | **None stated** | No, unless the authors grant it | Yes | Fetched and converted |
| Olympic Boxing Punch Classification (Stefański et al., Kaggle) | Competition bouts from a fixed camera; hit, miss, block by hand | Non-commercial per a derivative copy; original terms not yet read | No | Yes, after reading the terms | Not fetched |

## Collector clips: most are not useful

The 18 clips the collector accepted include five recordings of the video game Super Street Fighter II (matched on the word "sparring" in a player's name), a conference talk, a 1901 film, and two "punchball" clips. Four are real striking footage and usable for smoke tests:

- `wikimedia_boxer_pekka_kokkonen_training_9a4c6665` (solo training)
- `wikimedia_day_of_the_town_2017_09_09_kickboxing_00_91d03884`
- `wikimedia_muay_thai_in_lamai_e46cea44`
- `wikimedia_boxing_match_yrj_piitulainen_vs_jean_wan_54e247af` (1947 bout, low quality)

The collector needs a relevance check (a person in a fighting stance for most of the clip) before it is run again.

## BoxingVI: fetch, convert, score

```bash
# 1. Annotations and the list of YouTube links (about 50 MB, from the Drive folder in the dataset's README)
#    into data/public/boxingvi_drive/
# 2. The ten source videos at 720p (about 800 MB) into data/public/boxingvi_videos/V1.mp4 ... V10.mp4
# 3. Labels and excerpts in the project's format
python -m eval.public_sets.boxingvi convert \
    --annotations data/public/boxingvi_drive/Annotation_files \
    --videos data/public/boxingvi_videos \
    --out data/public/boxingvi_eval --max-seconds 180        # 0 = full length
# 4. Score the current pipeline
PYTHONPATH=backend python -m eval.run --split dir \
    --labels-dir data/public/boxingvi_eval --name boxingvi_180s \
    --out data/public/boxingvi_180s.json
```

Known limits, all of which the converter's docstring repeats:
- The dataset's README claims 20 videos; the published folder has 10.
- It labels lead or rear, not left or right, and gives no stance. Pass `--stance V3=southpaw` once someone has looked at each video; until then every boxer is assumed orthodox and hand agreement is unreliable.
- No target, no technique errors, no landed or missed.
- Solo work only, so it cannot test two-fighter tracking.
- Downloading the source videos from YouTube is for local evaluation only. Do not redistribute them or the excerpts.

## What to film (owner)

The fastest way to unblock measurement and training at once is 30 to 60 minutes of the owner's own gym footage:

| Need | Footage | Why |
|---|---|---|
| Strike and technique labels the project can train on | 10 clips, 4 or more fighters, bag and shadow, side and three-quarter angle | DATA-00; replaces BoxingVI as the gate |
| Two-fighter tracking | 5 or more sparring rounds, whole ring in frame, fixed phone | VIS-17 |
| Landed, missed, blocked | The same sparring rounds, labeled per strike | VIS-24; no public set can train this for a shipped model |
| Hard cases | Clinches, a coach walking through frame, poor light, phone on the floor | Abstention and re-identification |

Everyone in frame signs the consent form (`tools/collect/consent.example.yaml` has the fields). Film at 60 fps where the phone allows; punches are 0.2 to 0.6 s long.
