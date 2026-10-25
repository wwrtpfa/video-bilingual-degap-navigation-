# Open-source implementation notes

These projects were checked while revising the skill. Stars are a snapshot and should not be treated as a quality score.

| Project | What it contributes | Applied here |
| --- | --- | --- |
| [Auto-Editor](https://github.com/WyattBlue/auto-editor) | Labels active/silent regions and uses configurable margins before cutting. | Keep asymmetric `tail` and `pre` buffers rather than cutting exactly at a threshold. |
| [Silero VAD](https://github.com/snakers4/silero-vad) | Speech activity timestamps that are less dependent on a fixed loudness level; supports 8/16 kHz and many languages. | Combine VAD with FFmpeg `silencedetect` so a quiet breath and a noisy background are not handled by one rule. |
| [WhisperX](https://github.com/m-bain/whisperX) | Word-level timestamps through forced alignment and VAD-based batching. | Accept optional word timestamps to protect soft word starts and expose a path to a future forced-alignment backend. |
| [VideoCaptioner](https://github.com/WEIFENG2333/VideoCaptioner) | A practical subtitle workflow: recognition, segmentation, correction, translation and export. | Keep recognition separate from human correction and translation before burn-in. |
| [OpenCut](https://github.com/OpenCut-app/OpenCut) | Open-source timeline editing model for visual review. | Treat generated cuts as a plan first; require representative-frame review before final export. |

## Decisions

- `silencedetect` alone is too brittle for screen recordings with low-level noise; VAD alone can merge natural pauses. The processor takes the union of both candidate non-speech regions and then protects word boundaries when supplied.
- Automatic detection may remove pauses, but repeated words and stutters are editorial decisions. They must be passed as reviewed source-time ranges through `--extra-cuts`.
- The progress rail is deliberately a subtitle-layer graphic: a black full-width rail, white chapter labels, separators, and a gray played fill. It is generated per frame so the fill advances with playback and does not depend on a separate player UI.
- Burning subtitles and cutting video require re-encoding. The skill preserves dimensions, source frame cadence as reported by `avg_frame_rate`, and at least the source video bitrate by default; it does not claim byte-for-byte losslessness.
