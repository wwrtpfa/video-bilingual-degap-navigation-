---
name: video-bilingual-degap-navigation
description: Finish an existing spoken video by preserving its original voice, removing reviewed pauses and stutters, adding yellow Chinese-English subtitles without a background panel, and placing chapter progress in a top band outside the source picture. Use for recorded speech, screen recordings, and talking-head footage.
---

# Bilingual Video Finishing

This skill starts with a recorded video that already has usable speech. Keep its original voice and edit the same source-time ranges from picture and audio. Do not synthesize or layer a new voiceover. For a video generated from a written script, derive captions from that script in its renderer instead of transcribing it again.

## Inputs and tools

- One local video with a video stream and an audio stream; keep the source file untouched.
- `ffprobe` and FFmpeg with the `ass` filter. The processor defaults to `/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg`; set `FFMPEG` to another compatible binary when needed.
- For automatic cut planning, a Python environment with `silero-vad`, `onnxruntime`, `numpy`, and `torch`. `transcribe_srt.py` additionally needs `mlx-whisper` on supported macOS hardware. Check imports in the selected interpreter before starting. If VAD is unavailable, explain the blocker or use a previously reviewed `--cut-plan`; do not silently switch to volume-only cuts.

## Output style

The processor adds a slim band **above the original picture**. The source image remains at its original pixel size and begins immediately below that band; the progress line sits on the band's lower edge, touching the source boundary without covering source pixels. The band contains the current chapter title and chapter number. Its default height scales from `56 px` for a `1080 px` high source (`112 px` for a `2160 px` high source), and `--top-band-height` can override it.

Chinese and English subtitles are centered in the lower part of the picture. Both lines are yellow (`#FFE348`) with a restrained dark outline and **no opaque background panel**. At a `2160 px` source height, the ASS renderer uses `130 px` Chinese and `73 px` English. These were calibrated against the visible size of the approved Remotion captions (`94 px` / `62 px` in CSS); ASS and CSS font sizes do not produce equal glyph sizes. Scale the ASS values proportionally for other source heights. Inspect the actual footage and adjust position if a face, button, demonstration, or platform UI occupies that region. Do not put a navigation rail at the bottom or cover the source's top menu/title bar.

The output is an H.264/AAC MP4, a post-cut bilingual SRT, an ASS render file, and a JSON report with cuts, chapter boundaries, source size, output canvas size, and band height. The canvas height grows by the band height; source content itself is neither scaled nor cropped. Preserve the source frame rate and use a video bitrate at least as high as the source's when available.

## Workflow

1. Probe the source and listen to representative portions. Transcribe its speech with `scripts/transcribe_srt.py`; request `--words-json` when possible. Correct product names, technical terms, speaker errors, and punctuation, then translate each caption into concise English.
2. Review the source-time transcript and video together. Derive short chapter titles from what is actually said. Mark obvious repeated words or stutters in an optional `extra-cuts.json`; do not infer a cut from one ASR error.
3. Use `scripts/process_video.py --plan-only` to review proposed cuts before rendering. It combines FFmpeg silence detection with Silero VAD and protects word boundaries with asymmetric tail/head buffers. Preserve natural breaths and the first consonant of each sentence. Increase `--pre` if a following word is clipped; increase `--min-gap` if the edit feels too aggressive.
4. Render with the reviewed plan. For layout-only revisions, pass the prior report as `--cut-plan` so the edit timing remains identical. Subtitles, chapters, and the moving progress line all use the post-cut timeline.
5. Check frames at the start, a chapter change, a bright background, the longest subtitle, and the end. Confirm the line is entirely outside the original picture, both yellow subtitle lines have no black panel, chapter text fits, and progress advances. Watch and listen across every cut; verify audio/video duration, source frame rate, output dimensions, and full decode.

When a larger Remotion composition is also requested, use this output as its finished footage layer or reuse the cut report to composite from the original. Add content-specific motion graphics around the footage without duplicating its captions, progress line, or audio.

## Run

Entries use source-time seconds:

```json
{
  "subtitles": [
    {"start": 0.0, "end": 2.4, "zh": "中文", "en": "English"}
  ],
  "chapters": [
    {"start": 0.0, "end": 8.5, "title": "01 开场与目标"}
  ]
}
```

Optional word timestamps are an array of `{ "start": 1.2, "end": 1.5, "word": "文本" }`. A reviewed cut file is an array of source-time pairs, such as `[[4.76, 5.94]]`.

```bash
python scripts/transcribe_srt.py input.mp4 -o source.srt --words-json words.json -l zh -m medium
python scripts/process_video.py input.mp4 --entries-json bilingual.json \
  --words-json words.json --plan-only
python scripts/process_video.py input.mp4 --entries-json bilingual.json \
  --words-json words.json --cut-plan outputs/input_chapters.json --output-dir outputs
```

`--extra-cuts` is optional. The first command produces raw Chinese timestamps; proofread and create `bilingual.json` before processing. Use `--threshold` (default `-35 dB`), `--min-gap` (`0.25 s`), `--tail` (`0.06 s`), and `--pre` (`0.12 s`) only when the recording calls for different cut behavior.

Default filenames are `<stem>_bilingual_degapped_navigation.mp4`, `<stem>_bilingual.srt`, `<stem>_navigation.ass`, and `<stem>_chapters.json` in `--output-dir` (`outputs` by default). Use `--output` for a separate comparison version. Burning subtitles and adding a top band require video re-encoding, so inspect fine source details at native resolution before delivery.
