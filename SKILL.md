---
name: video-bilingual-degap-navigation
description: Process a spoken video in one pass: remove long speech pauses, create Chinese-English bilingual subtitles, summarize subtitle content into chapter titles, and burn a reference-style dark chapter navigation bar below the subtitles with a moving red progress line. Trigger whenever the user asks to add bilingual subtitles, remove pauses/breath gaps, create chapter navigation, or produce a finished subtitled video in one operation.
compatibility: macOS Apple Silicon with ffmpeg-full and the bundled mlx-whisper environment.
---

# Video Bilingual Degap Navigation

Use this skill for a complete spoken-video finishing pass. The expected input is one local video file. Preserve the original file and write new files beside the current task outputs.

## What it produces

- A new MP4 with speech pauses and reviewed repetitions/stutters compressed, burned-in yellow Chinese-English subtitles, and a navigation bar directly below the subtitles.
- A standalone bilingual SRT file with the same post-cut timing.
- A JSON report containing original duration, final duration, removed pause time, and chapter metadata.

The navigation bar uses a continuous dark strip, numbered chapter labels, vertical separators, a dark red active chapter, and a thin red overall progress line that advances with playback. Do not use unrelated multicolor blocks or place the bar above the subtitles.

## Workflow

1. Inspect the source with `ffprobe` and confirm it has video and audio.
2. Extract Chinese speech timestamps with the persistent environment:
   `/Users/pengfanao/Downloads/bilingual-subtitle-skill-main/.venv/bin/python`
   and this skill's `scripts/transcribe_srt.py`, using `-l zh -m medium` unless the user asks for another language/model.
3. Read the resulting SRT and correct obvious recognition errors in technical names, people names, and product names. Translate each subtitle into concise natural English. Keep the original timing.
4. Summarize the SRT into 3-8 chapter titles. Prefer semantic boundaries from the spoken content; use short labels such as `03  Java 后端与风控经历`. Never invent details absent from the subtitles. Pass the titles and original source-time boundaries to `scripts/process_video.py` as JSON.
5. Run `scripts/process_video.py` with the corrected bilingual entries and chapters. It detects long silences, protects subtitle-backed speech from false silence cuts, applies optional transcript-reviewed cuts for duplicated words/stutters, remaps subtitle times, renders the yellow subtitles and bar, and encodes the final MP4.
6. Validate with `ffprobe` and extract representative frames near the start, a chapter transition, and the end. Confirm audio/video durations match, the bar is below both subtitle lines, chapter labels fit, and the red progress line moves.

## Script interface

Create a JSON file with this shape:

```json
{
  "subtitles": [
    {"start": 0.0, "end": 2.4, "zh": "中文", "en": "English"}
  ],
  "chapters": [
    {"start": 0.0, "end": 8.5, "title": "01  开场与目标"}
  ]
}
```

Then run:

```bash
python3 /Users/pengfanao/.codex/skills/video-bilingual-degap-navigation/scripts/process_video.py \
  input.mp4 --entries-json bilingual.json --output-dir outputs
```

For reviewed repetitions or stutters, add a JSON file such as `[[4.76, 5.94], [35.08, 36.54]]` and pass `--extra-cuts reviewed_cuts.json`.

Optional controls: `--threshold` (default `-26` dB), `--min-gap` (default `0.2` seconds), `--tail` (default `0.08`), `--pre` (default `0.15`), and `--extra-cuts` for a JSON array of source-time `[start, end]` ranges. For quiet screen recordings, use `--threshold -35 --min-gap .25`; the script now protects speech ranges from false silence detection. Increase `--pre` if a following word is clipped; increase `--min-gap` if the edit feels too aggressive.

## Output naming

Use `<stem>_bilingual_degapped_navigation.mp4`, `<stem>_bilingual.srt`, and `<stem>_chapters.json` unless the user specifies another location.

## Important limits

This skill is for spoken videos with a reasonably clean voice track. Background music or constant noise reduces silence detection accuracy. Do not delete the source. Do not claim a chapter summary was generated from the SRT unless the chapter titles were actually derived from the subtitle text. The default subtitle treatment is bold yellow text with a black outline, using approximately 36/27 logical px for Chinese/English before source-resolution scaling so screen recordings and ordinary 1080p videos remain readable.
