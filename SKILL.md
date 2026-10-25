---
name: video-bilingual-degap-navigation
description: "Process spoken video in one pass with pause removal, Chinese-English subtitles, chapter navigation, and a moving progress line. Use for finished subtitled videos, and preserve source resolution, frame rate, and video quality by default."
---

# Video Bilingual Degap Navigation

Use this skill for a complete spoken-video finishing pass. The expected input is one local video file. Preserve the original file and write new files beside the current task outputs.

Requires macOS Apple Silicon, ffmpeg-full, and the existing mlx-whisper environment. The persistent venv should also have `silero-vad` and `onnxruntime` for speech-activity detection; if they are unavailable, stop and say so rather than silently falling back to aggressive volume-only editing.

## What it produces

- A new MP4 with speech pauses and reviewed repetitions/stutters compressed, burned-in white Chinese-English subtitles, and a navigation bar directly below the subtitles.
- A standalone bilingual SRT file with the same post-cut timing.
- A JSON report containing original duration, final duration, removed pause time, and chapter metadata.

The navigation bar follows the supplied reference style: a thin full-width translucent black rail flush with the bottom edge, white chapter labels centered horizontally and vertically in their source-time sections, thin separators, and a translucent neutral-gray played portion that advances continuously with playback. At 1080p the rail is approximately 54 px high, about 5% of the frame height. Render rail/fill/separator shapes from a top-left anchor so their dimensions stay inside the frame; use centered positioning only for labels. Keep it below both subtitle lines with a visible gap. Do not use yellow text, red active blocks, multicolor cards, a tall bottom panel, or place the bar above the subtitles.

## Workflow

1. Inspect the source with `ffprobe` and confirm it has video and audio.
2. Extract Chinese speech timestamps with the persistent environment:
   `/Users/pengfanao/Downloads/bilingual-subtitle-skill-main/.venv/bin/python`
   and this skill's `scripts/transcribe_srt.py`, using `-l zh -m medium` unless the user asks for another language/model.
3. Run the same transcription with `--words-json words.json` when possible. Word-level timestamps protect soft consonants and low-volume word starts from being cut. WhisperX is a useful alternative when its forced-alignment model supports the language; do not claim word-level accuracy from segment timestamps alone.
4. Read the resulting SRT and correct obvious recognition errors in technical names, people names, and product names. Translate each subtitle into concise natural English. Keep the original timing. For clear duplicated words or stutters, write reviewed source-time ranges in `extra-cuts.json`; never infer these from a single ASR typo.
5. Summarize the SRT into 3-8 chapter titles. Prefer semantic boundaries from the spoken content; use short labels such as `03  Java 后端与风控经历`. Never invent details absent from the subtitles. Pass the titles and original source-time boundaries to `scripts/process_video.py` as JSON.
6. Run `scripts/process_video.py` with the corrected bilingual entries, `--words-json`, and optional `--extra-cuts`. It combines FFmpeg silence detection with Silero VAD, keeps asymmetric tail/head buffers, protects word boundaries, remaps subtitle times, renders the white subtitles and reference-style gray progress rail, and encodes the final MP4. Use `--plan-only` before rendering to inspect proposed cuts.
7. Validate with `ffprobe` and extract representative frames near the start, a chapter transition, and the end. Confirm audio/video durations match, the bar is below both subtitle lines, chapter labels fit, and the gray played portion advances. Check fine text and screen-recording details at native resolution.

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

Optional word timestamps are a JSON array of `{ "start": 1.2, "end": 1.5, "word": "文本" }`. Generate them with:

```bash
python scripts/transcribe_srt.py input.mp4 -o bilingual.srt --words-json words.json -m small
```

Then run:

```bash
python3 /Users/pengfanao/.codex/skills/video-bilingual-degap-navigation/scripts/process_video.py \
  input.mp4 --entries-json bilingual.json --words-json words.json --output-dir outputs
```

For reviewed repetitions or stutters, add a JSON file such as `[[4.76, 5.94], [35.08, 36.54]]` and pass `--extra-cuts reviewed_cuts.json`.

Optional controls: `--threshold` (default `-35` dB), `--min-gap` (default `0.25` seconds), `--tail` (default `0.06`), `--pre` (default `0.12`), and `--extra-cuts` for a JSON array of source-time `[start, end]` ranges. The processor combines `silencedetect` with Silero VAD; use `--plan-only` to review cuts before encoding. Increase `--pre` if a following word is clipped; increase `--min-gap` if the edit feels too aggressive. The default deliberately does not cut short breaths.

For a style-only rerender of the same source, pass a previously validated chapters report with `--cut-plan`. This reuses its exact `cuts` and skips speech analysis, preventing visual revisions from changing editorial timing.

## Preserve source quality

The user does not want video quality reduced. Keep the source resolution and frame rate, and never apply a low fixed bitrate. The script targets at least 130% of the source video bitrate (or a resolution and frame-rate based fallback) and verifies the actual output. If automatic output bitrate falls below the source, it retries at a higher target; if dimensions or frame rate change, it fails. Use `--video-bitrate` only when the user explicitly requests a different quality/size tradeoff. Use `--output` for a separate comparison version. Burning subtitles and cutting frames require re-encoding, so the MP4 cannot be byte-for-byte lossless; inspect representative native-resolution frames before delivery.

## Output naming

Use `<stem>_bilingual_degapped_navigation.mp4`, `<stem>_bilingual.srt`, and `<stem>_chapters.json` unless the user specifies another location.

## Important limits

This skill is for spoken videos with a reasonably clean voice track. Background music or constant noise reduces silence detection accuracy. Do not delete the source. Do not claim a chapter summary was generated from the SRT unless the chapter titles were actually derived from the subtitle text. The default subtitle treatment is white Chinese/English text with a restrained black outline and a larger Chinese line, using approximately 43/29 logical px before source-resolution scaling. The default progress rail is black with white labels and a gray elapsed fill, matching the supplied visual reference.
