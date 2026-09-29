#!/usr/bin/env python3
import argparse, json, os, re, subprocess

FFMPEG = os.environ.get('FFMPEG', '/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg')

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=True)

def duration(path):
    return float(run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',path]).stdout.strip())

def video_size(path):
    out = run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','csv=p=0:s=x',path]).stdout.strip()
    return tuple(int(v) for v in out.split('x'))

def ts(x):
    return f'{int(x//3600):02}:{int(x%3600//60):02}:{x%60:06.3f}'.replace('.', ',')

def ass_ts(x):
    return f'{int(x//3600)}:{int(x%3600//60):02}:{x%60:05.2f}'

def silence_keeps(path, threshold, min_gap, tail, pre):
    p = subprocess.run([FFMPEG,'-hide_banner','-i',path,'-af',f'silencedetect=noise={threshold}dB:d={min_gap}','-f','null','-'],capture_output=True,text=True)
    total = duration(path); pairs=[]; start=None
    for m in re.finditer(r'silence_(start|end): ([0-9.]+)', p.stderr):
        if m.group(1) == 'start': start=float(m.group(2))
        elif start is not None: pairs.append((start,float(m.group(2)))); start=None
    if start is not None: pairs.append((start,total))
    cuts=[]
    for s,e in pairs:
        a = 0.0 if s < 0.05 else s + tail
        b = total if e > total - 0.05 else e - pre
        if b-a > 0.02: cuts.append((a,b))
    keeps=[]; pos=0.0
    for a,b in cuts:
        if a > pos: keeps.append((pos,a))
        pos=b
    if pos < total: keeps.append((pos,total))
    return total, pairs, cuts, keeps

def map_time(t, keeps):
    out=0.0
    for s,e in keeps:
        if t >= e: out += e-s
        elif t > s: return out+t-s
        else: return out
    return out

def rebuild_keeps(cuts, total):
    cuts=sorted((max(0.0,a), min(total,b)) for a,b in cuts if b-a>0.02)
    merged=[]
    for a,b in cuts:
        if merged and a <= merged[-1][1] + 0.01: merged[-1]=(merged[-1][0], max(merged[-1][1],b))
        else: merged.append((a,b))
    keeps=[]; pos=0.0
    for a,b in merged:
        if a>pos: keeps.append((pos,a))
        pos=b
    if pos<total: keeps.append((pos,total))
    return merged,keeps

def protect_speech(cuts, protected):
    out=[]
    for a,b in cuts:
        spans=[(a,b)]
        for ps,pe in protected:
            next_spans=[]
            for x,y in spans:
                if pe<=x or ps>=y: next_spans.append((x,y)); continue
                if x<ps: next_spans.append((x,min(ps,y)))
                if pe<y: next_spans.append((max(pe,x),y))
            spans=next_spans
        out.extend(spans)
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('video'); ap.add_argument('--entries-json', required=True)
    ap.add_argument('--output-dir', default='outputs'); ap.add_argument('--threshold', type=float, default=-26)
    ap.add_argument('--min-gap', type=float, default=.2); ap.add_argument('--tail', type=float, default=.08); ap.add_argument('--pre', type=float, default=.15)
    ap.add_argument('--extra-cuts', help='JSON array of source-time [start,end] ranges for repeated words/stutters')
    args=ap.parse_args(); os.makedirs(args.output_dir, exist_ok=True)
    stem=os.path.splitext(os.path.basename(args.video))[0]
    data=json.load(open(args.entries_json, encoding='utf-8'))
    total,pairs,cuts,keeps=silence_keeps(args.video,args.threshold,args.min_gap,args.tail,args.pre)
    protected=[(max(0,float(r['start'])-.04), min(total,float(r['end'])+.04)) for r in data.get('subtitles',[])]
    cuts=protect_speech(cuts, protected)
    # Add transcript-reviewed cuts for duplicated words and obvious stutters.
    # Merge with silence cuts so one timeline is used for video, audio, and SRT.
    if args.extra_cuts:
        extras = json.load(open(args.extra_cuts, encoding='utf-8'))
        cuts.extend((float(a), float(b)) for a,b in extras if float(b) > float(a))
    cuts,keeps=rebuild_keeps(cuts,total)
    final_total=sum(e-s for s,e in keeps)
    entries=[]
    for row in data['subtitles']:
        s,e=map_time(float(row['start']),keeps),map_time(float(row['end']),keeps)
        if e-s>.05: entries.append((s,e,row.get('zh',''),row.get('en','')))
    chapters=[]
    for row in data.get('chapters',[]):
        s,e=map_time(float(row['start']),keeps),map_time(float(row['end']),keeps)
        if e>s: chapters.append((s,e,row['title']))
    if not chapters: chapters=[(0,final_total,'01  全片')]
    srt_path=os.path.join(args.output_dir,stem+'_bilingual.srt')
    with open(srt_path,'w',encoding='utf-8') as f:
        for i,(s,e,zh,en) in enumerate(entries,1): f.write(f'{i}\n{ts(s)} --> {ts(e)}\n{zh}\n{en}\n\n')
    W,H=video_size(args.video); scale=H/1080.0
    bar_x,bar_y,bar_w,bar_h=int(28*scale),int(H-80*scale),W-int(56*scale),int(58*scale)
    ass=['[Script Info]','ScriptType: v4.00+','PlayResX: '+str(W),'PlayResY: '+str(H),'', '[V4+ Styles]',
      'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
      f'Style: Zh,Arial,{int(32*scale)},&H0000FFFF,&H0000FFFF,&H00101010,&H99000000,0,0,0,0,100,100,0,0,1,3,1,2,{int(60*scale)},{int(60*scale)},{int(120*scale)},1',
      f'Style: En,Arial,{int(24*scale)},&H0000FFFF,&H0000FFFF,&H00101010,&H99000000,0,0,0,0,100,100,0,0,1,3,1,2,{int(60*scale)},{int(60*scale)},{int(82*scale)},1',
      f'Style: Bar,Arial,{int(17*scale)},&H00F4F4F4,&H00F4F4F4,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1','[Events]','Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
    for s,e,zh,en in entries:
        if zh: ass.append(f'Dialogue: 0,{ass_ts(s)},{ass_ts(e)},Zh,,0,0,0,,{zh}')
        if en: ass.append(f'Dialogue: 0,{ass_ts(s)},{ass_ts(e)},En,,0,0,0,,{en}')
    ass.append(f'Dialogue: 0,0:00:00.00,{ass_ts(final_total)},Bar,,0,0,0,,{{\\p1\\pos({bar_x},{bar_y})\\c&H00202020&}}m 0 0 l {bar_w} 0 l {bar_w} {bar_h} l 0 {bar_h}')
    cursor=bar_x
    for i,(s,e,title) in enumerate(chapters):
        width=bar_w*(e-s)/final_total; x=cursor
        ass.append(f'Dialogue: 1,{ass_ts(s)},{ass_ts(e)},Bar,,0,0,0,,{{\\p1\\pos({x:.1f},{bar_y})\\c&H001B155C&}}m 0 0 l {width:.1f} 0 l {width:.1f} {bar_h} l 0 {bar_h}')
        if i: ass.append(f'Dialogue: 2,0:00:00.00,{ass_ts(final_total)},Bar,,0,0,0,,{{\\p1\\pos({x:.1f},{bar_y+8})\\c&H00757575&}}m 0 0 l 2 0 l 2 {bar_h-16} l 0 {bar_h-16}')
        ass.append(f'Dialogue: 3,0:00:00.00,{ass_ts(final_total)},Bar,,0,0,0,,{{\\an8\\fs{int(17*scale)}\\bord0\\shad0\\pos({x+width/2:.1f},{bar_y+int(12*scale)})}}{title}')
        cursor += width
    for j in range(int(final_total/.1)+1):
        s=j*.1; e=min(final_total,s+.12); pw=max(2,bar_w*s/final_total)
        line_h=max(3,int(5*scale))
        ass.append(f'Dialogue: 5,{ass_ts(s)},{ass_ts(e)},Bar,,0,0,0,,{{\\p1\\pos({bar_x},{bar_y+bar_h-line_h})\\c&H002B2BD8&}}m 0 0 l {pw:.1f} 0 l {pw:.1f} {line_h} l 0 {line_h}')
    ass_path=os.path.join(args.output_dir,stem+'_navigation.ass'); open(ass_path,'w',encoding='utf-8').write('\n'.join(ass))
    parts=[]
    for i,(s,e) in enumerate(keeps): parts += [f'[0:v]trim=start={s:.4f}:end={e:.4f},setpts=PTS-STARTPTS[v{i}]',f'[0:a]atrim=start={s:.4f}:end={e:.4f},asetpts=PTS-STARTPTS[a{i}]']
    parts.append(''.join(f'[v{i}][a{i}]' for i in range(len(keeps)))+f'concat=n={len(keeps)}:v=1:a=1[v][a]'); parts.append(f'[v]ass={ass_path}[vo]')
    out=os.path.join(args.output_dir,stem+'_bilingual_degapped_navigation.mp4')
    run([FFMPEG,'-hide_banner','-y','-i',args.video,'-filter_complex',';'.join(parts),'-map','[vo]','-map','[a]','-c:v','h264_videotoolbox','-b:v','8M','-c:a','aac','-b:a','192k','-movflags','+faststart',out])
    report={'input':os.path.abspath(args.video),'output':os.path.abspath(out),'srt':os.path.abspath(srt_path),'original_duration':total,'final_duration':final_total,'removed_seconds':total-final_total,'silences_detected':len(pairs),'silences_cut':len(cuts),'chapters':[{'start':s,'end':e,'title':t} for s,e,t in chapters]}
    open(os.path.join(args.output_dir,stem+'_chapters.json'),'w',encoding='utf-8').write(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__': main()
