#!/usr/bin/env python3
"""Finish spoken video with conservative cuts, bilingual captions, and chapter progress."""

import argparse
import json
import math
import os
import re
import subprocess
from fractions import Fraction
from pathlib import Path

FFMPEG = os.environ.get("FFMPEG", "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def probe(path):
    return json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]).stdout)


def timecode(value, ass=False):
    hours, minutes, seconds = int(value // 3600), int(value % 3600 // 60), value % 60
    return f"{hours}:{minutes:02}:{seconds:05.2f}" if ass else f"{hours:02}:{minutes:02}:{seconds:06.3f}".replace(".", ",")


def merge(intervals, tolerance=0.02):
    result = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if result and start <= result[-1][1] + tolerance:
            result[-1] = (result[-1][0], max(end, result[-1][1]))
        else:
            result.append((start, end))
    return result


def complement(intervals, total):
    result, cursor = [], 0.0
    for start, end in merge(intervals):
        if start > cursor:
            result.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < total:
        result.append((cursor, total))
    return result


def subtract(intervals, protected):
    spans = list(intervals)
    for guard_start, guard_end in merge(protected):
        next_spans = []
        for start, end in spans:
            if guard_end <= start or guard_start >= end:
                next_spans.append((start, end))
            else:
                if start < guard_start:
                    next_spans.append((start, guard_start))
                if guard_end < end:
                    next_spans.append((guard_end, end))
        spans = next_spans
    return spans


def silence_intervals(path, total, threshold, minimum):
    result = subprocess.run(
        [FFMPEG, "-hide_banner", "-i", str(path), "-af", f"silencedetect=noise={threshold}dB:d={minimum}", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:])
    intervals, start = [], None
    for match in re.finditer(r"silence_(start|end): ([0-9.]+)", result.stderr):
        if match.group(1) == "start":
            start = float(match.group(2))
        elif start is not None:
            intervals.append((start, float(match.group(2))))
            start = None
    if start is not None:
        intervals.append((start, total))
    return intervals


def vad_intervals(path):
    import numpy as np
    import torch
    from silero_vad import get_speech_timestamps, load_silero_vad

    audio = subprocess.run(
        [FFMPEG, "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
        capture_output=True, check=True,
    )
    samples = torch.from_numpy(np.frombuffer(audio.stdout, dtype="<f4").copy())
    speech = get_speech_timestamps(
        samples, load_silero_vad(onnx=True), sampling_rate=16000,
        min_silence_duration_ms=80, min_speech_duration_ms=100,
        speech_pad_ms=40, return_seconds=True,
    )
    return [(float(item["start"]), float(item["end"])) for item in speech]


def build_cuts(total, silence, speech, words, min_gap, tail, pre, extra):
    # Word boundaries protect soft consonants that VAD and volume gates may miss.
    candidates = merge(silence + complement(speech, total), tolerance=.08)
    protected = [(max(0, float(w["start"]) - .04), min(total, float(w["end"]) + .04)) for w in words]
    candidates = subtract(candidates, protected)
    cuts = []
    for start, end in candidates:
        if end - start < min_gap:
            continue
        if start < .06:
            cut = (0.0, end - pre)
        elif end > total - .06:
            cut = (start + max(tail, .22), total)
        else:
            cut = (start + tail, end - pre)
        if cut[1] - cut[0] >= .06:
            cuts.append(cut)
    for start, end in extra:
        start, end = float(start), float(end)
        if not 0 <= start < end <= total:
            raise ValueError(f"Reviewed cut outside source duration: {start}-{end}")
        cuts.append((start, end))
    cuts = merge(cuts)
    return cuts, complement(cuts, total)


def map_time(value, keeps):
    elapsed = 0.0
    for start, end in keeps:
        if value >= end:
            elapsed += end - start
        elif value > start:
            return elapsed + value - start
        else:
            return elapsed
    return elapsed


def ass_text(value):
    return str(value).replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


def make_ass(path, entries, chapters, final_total, width, height, fps):
    scale = height / 1080
    # Match the reference: a thin chapter strip flush with the bottom edge.
    # Captions remain in a separate area above the strip.
    bar_h, font_zh, font_en, font_bar = (round(v * scale) for v in (54, 43, 29, 21))
    bar_y = height - bar_h
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Zh,PingFang SC,{font_zh},&H00FFFFFF,&H00FFFFFF,&H00000000,&H70000000,1,0,0,0,100,100,0,0,1,3,1,2,{round(80*scale)},{round(80*scale)},{round(136*scale)},1",
        f"Style: En,Arial,{font_en},&H00FFFFFF,&H00FFFFFF,&H00000000,&H70000000,0,0,0,0,100,100,0,0,1,2,1,2,{round(80*scale)},{round(80*scale)},{round(92*scale)},1",
        f"Style: Bar,PingFang SC,{font_bar},&H00FFFFFF,&H00FFFFFF,&H00141414,&H00000000,0,0,0,0,100,100,0,0,1,1,0,5,0,0,0,1",
        "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    end_time = timecode(final_total, True)
    for start, end, zh, en in entries:
        if zh:
            lines.append(f"Dialogue: 5,{timecode(start, True)},{timecode(end, True)},Zh,,0,0,0,,{ass_text(zh)}")
        if en:
            lines.append(f"Dialogue: 5,{timecode(start, True)},{timecode(end, True)},En,,0,0,0,,{ass_text(en)}")
    # Shapes use a top-left anchor so their full width stays inside the frame.
    # The rail is slightly transparent; labels use their own centered anchor.
    lines.append(f"Dialogue: 0,0:00:00.00,{end_time},Bar,,0,0,0,,{{\\an7\\p1\\pos(0,{bar_y})\\bord0\\c&H00060606&\\1a&H50&}}m 0 0 l {width} 0 l {width} {bar_h} l 0 {bar_h}")
    for frame in range(math.ceil(final_total * fps)):
        start, end = frame / fps, min(final_total, (frame + 1) / fps)
        fill = max(1, round(width * end / final_total))
        lines.append(f"Dialogue: 1,{timecode(start, True)},{timecode(end, True)},Bar,,0,0,0,,{{\\an7\\p1\\pos(0,{bar_y})\\bord0\\c&H00808080&\\1a&H38&}}m 0 0 l {fill} 0 l {fill} {bar_h} l 0 {bar_h}")
    for index, (start, end, title) in enumerate(chapters):
        x, x_end = round(width * start / final_total), round(width * end / final_total)
        if index:
            lines.append(f"Dialogue: 2,0:00:00.00,{end_time},Bar,,0,0,0,,{{\\an7\\p1\\pos({x},{bar_y})\\bord0\\c&H00606060&\\1a&H28&}}m 0 0 l 2 0 l 2 {bar_h} l 0 {bar_h}")
        lines.append(f"Dialogue: 3,0:00:00.00,{end_time},Bar,,0,0,0,,{{\\an5\\pos({(x+x_end)/2:.1f},{bar_y+bar_h/2:.1f})\\fs{font_bar}\\bord1}}{ass_text(title)}")
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--entries-json", type=Path, required=True)
    parser.add_argument("--words-json", type=Path, help="Optional word timestamps from transcribe_srt.py")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--threshold", type=float, default=-35)
    parser.add_argument("--min-gap", type=float, default=.25)
    parser.add_argument("--tail", type=float, default=.06)
    parser.add_argument("--pre", type=float, default=.12)
    parser.add_argument("--extra-cuts", type=Path, help="Reviewed source-time [start,end] ranges")
    parser.add_argument("--cut-plan", type=Path, help="Reuse cuts from a prior chapters report for style-only rerenders")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--video-bitrate", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    data = json.loads(args.entries_json.read_text(encoding="utf-8"))
    if args.words_json:
        data["words"] = json.loads(args.words_json.read_text(encoding="utf-8"))
    metadata = probe(args.video)
    video = next(stream for stream in metadata["streams"] if stream["codec_type"] == "video")
    if not any(stream["codec_type"] == "audio" for stream in metadata["streams"]):
        raise ValueError("Input has no audio track")
    total = float(metadata["format"]["duration"])
    width, height = video["width"], video["height"]
    fps = float(Fraction(video["avg_frame_rate"]))
    if args.cut_plan:
        plan = json.loads(args.cut_plan.read_text(encoding="utf-8"))
        planned_cuts = plan.get("cuts", plan) if isinstance(plan, dict) else plan
        cuts = merge((float(item["start"]), float(item["end"])) if isinstance(item, dict)
                     else (float(item[0]), float(item[1])) for item in planned_cuts)
        if any(start < 0 or end > total for start, end in cuts):
            raise ValueError("Reused cut plan contains an interval outside the source duration")
        keeps = complement(cuts, total)
        silence_count = int(plan.get("silences_detected", 0)) if isinstance(plan, dict) else 0
        vad_count = int(plan.get("vad_speech_segments", 0)) if isinstance(plan, dict) else 0
        extra = plan.get("reviewed_cuts", []) if isinstance(plan, dict) else []
    else:
        silence = silence_intervals(args.video, total, args.threshold, min(.12, args.min_gap / 2))
        speech = vad_intervals(args.video)
        extra = json.loads(args.extra_cuts.read_text(encoding="utf-8")) if args.extra_cuts else []
        cuts, keeps = build_cuts(total, silence, speech, data.get("words", []), args.min_gap, args.tail, args.pre, extra)
        silence_count, vad_count = len(silence), len(speech)
    final_total = sum(end - start for start, end in keeps)
    if final_total < .5:
        raise ValueError("Cut plan would remove nearly all video")
    stem = args.video.stem
    report_path = args.output_dir / f"{stem}_chapters.json"
    report = {"input": str(args.video.resolve()), "original_duration": total, "final_duration": final_total,
              "removed_seconds": total-final_total, "silences_detected": silence_count, "vad_speech_segments": vad_count,
              "cuts": [{"start": a, "end": b} for a, b in cuts], "reviewed_cuts": extra}
    if args.cut_plan:
        report["reused_cut_plan"] = str(args.cut_plan.resolve())
    if args.plan_only:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        return
    entries = []
    for row in data["subtitles"]:
        start, end = map_time(float(row["start"]), keeps), map_time(float(row["end"]), keeps)
        if end-start > .05:
            entries.append((start, end, row.get("zh", ""), row.get("en", "")))
    chapters = []
    for row in data.get("chapters", []):
        start, end = map_time(float(row["start"]), keeps), map_time(float(row["end"]), keeps)
        if end > start:
            chapters.append((start, end, row["title"]))
    if not chapters:
        chapters = [(0, final_total, "全片")]
    srt = args.output_dir / f"{stem}_bilingual.srt"
    srt.write_text("".join(f"{i}\n{timecode(a)} --> {timecode(b)}\n{zh}\n{en}\n\n" for i, (a,b,zh,en) in enumerate(entries, 1)), encoding="utf-8")
    ass = args.output_dir / f"{stem}_navigation.ass"
    make_ass(ass, entries, chapters, final_total, width, height, fps)
    parts = []
    for i, (start, end) in enumerate(keeps):
        parts += [f"[0:v]trim=start={start:.4f}:end={end:.4f},setpts=PTS-STARTPTS[v{i}]",
                  f"[0:a]atrim=start={start:.4f}:end={end:.4f},asetpts=PTS-STARTPTS[a{i}]"]
    parts.append("".join(f"[v{i}][a{i}]" for i in range(len(keeps))) + f"concat=n={len(keeps)}:v=1:a=1[v][a]")
    # Concat may otherwise emit a variable frame rate after cuts. Reassert the
    # source rate before subtitle burn-in so screen recordings keep their cadence.
    parts.append(f"[v]fps=fps={fps:.6f},ass={str(ass.resolve())}[vo]")
    output = args.output or args.output_dir / f"{stem}_bilingual_degapped_navigation.mp4"
    source_bitrate = int(video.get("bit_rate") or 0)
    target = args.video_bitrate or max(10_000_000, int(width*height*fps*.08), int(source_bitrate*1.3))
    for attempt in range(3):
        run([FFMPEG, "-hide_banner", "-y", "-i", str(args.video), "-filter_complex", ";".join(parts),
             "-map", "[vo]", "-map", "[a]", "-c:v", "h264_videotoolbox", "-b:v", str(target),
             "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output)])
        rendered = next(stream for stream in probe(output)["streams"] if stream["codec_type"] == "video")
        output_fps = float(Fraction(rendered["avg_frame_rate"]))
        output_bitrate = int(rendered.get("bit_rate") or 0)
        if (rendered["width"],rendered["height"]) != (width,height) or abs(output_fps-fps) > max(.1, fps*.002):
            raise RuntimeError("Rendered resolution or frame rate differs from source")
        if args.video_bitrate or not source_bitrate or output_bitrate >= source_bitrate:
            break
        target = int(target*1.5)
    else:
        raise RuntimeError(f"Output bitrate {output_bitrate} is below source {source_bitrate}")
    report.update({"output": str(output.resolve()), "srt": str(srt.resolve()),
                   "chapters": [{"start": a, "end": b, "title": title} for a,b,title in chapters],
                   "source_resolution": [width,height], "output_resolution": [rendered["width"],rendered["height"]],
                   "source_fps": fps, "output_fps": output_fps, "source_video_bitrate": source_bitrate,
                   "target_video_bitrate": target, "actual_video_bitrate": output_bitrate})
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
