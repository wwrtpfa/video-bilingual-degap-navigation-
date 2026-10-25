#!/usr/bin/env python3
import argparse
import json
import mlx_whisper

def ts(x):
    return f'{int(x//3600):02}:{int(x%3600//60):02}:{x%60:06.3f}'.replace('.', ',')

ap=argparse.ArgumentParser()
ap.add_argument('video')
ap.add_argument('-o','--output',required=True)
ap.add_argument('-l','--language',default='zh')
ap.add_argument('-m','--model',default='medium')
ap.add_argument('--words-json', help='Optional word timestamps for speech-safe cutting')
a=ap.parse_args()
r=mlx_whisper.transcribe(a.video,path_or_hf_repo=f'mlx-community/whisper-{a.model}-mlx',language=a.language,word_timestamps=bool(a.words_json))
with open(a.output,'w',encoding='utf-8') as f:
    for i,s in enumerate(r['segments'],1):
        f.write(f'{i}\n{ts(s["start"])} --> {ts(s["end"])}\n{s["text"].strip()}\n\n')
if a.words_json:
    words=[{'start':float(w['start']),'end':float(w['end']),'word':w['word'].strip()}
           for s in r['segments'] for w in s.get('words',[]) if w.get('end',0)>w.get('start',0)]
    with open(a.words_json,'w',encoding='utf-8') as f:
        json.dump(words,f,ensure_ascii=False,indent=2)
