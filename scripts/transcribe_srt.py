#!/usr/bin/env python3
import argparse
import mlx_whisper

def ts(x):
    return f'{int(x//3600):02}:{int(x%3600//60):02}:{x%60:06.3f}'.replace('.', ',')

ap=argparse.ArgumentParser()
ap.add_argument('video')
ap.add_argument('-o','--output',required=True)
ap.add_argument('-l','--language',default='zh')
ap.add_argument('-m','--model',default='medium')
a=ap.parse_args()
r=mlx_whisper.transcribe(a.video,path_or_hf_repo=f'mlx-community/whisper-{a.model}-mlx')
with open(a.output,'w',encoding='utf-8') as f:
    for i,s in enumerate(r['segments'],1):
        f.write(f'{i}\n{ts(s["start"])} --> {ts(s["end"])}\n{s["text"].strip()}\n\n')
