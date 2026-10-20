#!/usr/bin/env python3
"""Inspect/promote translations; optionally update missing drafts via Google Translation."""
from pathlib import Path
import os
import sys
from importlib.util import find_spec
ROOT=Path(__file__).resolve().parent.parent
if any(find_spec(m) is None for m in ('bs4','yaml','markdown')):
    python=ROOT/'.venv/bin/python'
    if python.exists() and Path(sys.prefix)!=ROOT/'.venv':os.execv(str(python),[str(python),__file__,*sys.argv[1:]])
    raise SystemExit('Install requirements.txt in .venv first.')
import argparse
import json
from html import unescape
import subprocess
import urllib.request
import urllib.error
from urllib.parse import urlencode
import yaml
from i18n import read_json, load_mapping, dump_json, valid_translation, thaw


def google_translate(texts, locale, api_key):
    language={'zh-Hans':'zh-CN','zh-Hant':'zh-TW'}.get(locale,locale)
    payload=json.dumps({'q':texts,'source':'en','target':language,'format':'text'},ensure_ascii=False).encode()
    request=urllib.request.Request('https://translation.googleapis.com/language/translate/v2?'+urlencode({'key':api_key}),data=payload,headers={'Content-Type':'application/json; charset=utf-8'},method='POST')
    try:
        with urllib.request.urlopen(request,timeout=45) as response:
            rows=json.load(response)['data']['translations']
    except urllib.error.HTTPError as error:
        # Never log the request URL: it contains the API key.
        raise RuntimeError(f'Translation service returned HTTP {error.code}. Check API access, billing and quota.') from None
    except (urllib.error.URLError,TimeoutError):
        raise RuntimeError('Translation service could not be reached; existing drafts are unchanged.') from None
    if len(rows)!=len(texts):raise RuntimeError('Translation service returned an unexpected number of results.')
    return [unescape(row['translatedText']) for row in rows]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language',default='zh-Hans')
    action=parser.add_mutually_exclusive_group()
    action.add_argument('--translate',action='store_true',help='Send only missing/stale machine translations to Google (requires GOOGLE_TRANSLATE_API_KEY).')
    action.add_argument('--promote',metavar='KEY',help='Copy an automatic draft into your editable authored file.')
    action.add_argument('--accept',metavar='KEY',help='Mark your authored translation reviewed against the current English source.')
    parser.add_argument('--limit',type=int,default=0,help='Maximum units to translate (0 means all missing units).')
    args=parser.parse_args()
    languages=read_json(ROOT/'translations/languages.json',[])
    if args.language not in {l['code'] for l in languages if l['code']!='en'}:parser.error('Language must be enabled in translations/languages.json.')
    if args.limit<0:parser.error('--limit must be nonnegative')
    subprocess.run([sys.executable,str(ROOT/'scripts/build_site.py')],check=True,cwd=ROOT)
    source=read_json(ROOT/f'translations/source/{args.language}.json',{})
    cache_path=ROOT/f'translations/automatic/{args.language}.json'
    cache=read_json(cache_path,{})
    manual_path=ROOT/f'translations/{args.language}.yaml';manual=load_mapping(manual_path)
    if args.promote or args.accept:
        key=args.promote or args.accept
        if key not in source:parser.error(f'Unknown key: {key}')
        if args.promote:
            if key in manual:parser.error('An authored translation already exists; edit it directly or use --accept.')
            entry=cache.get(key,{})
            if entry.get('source_hash')!=source[key]['source_hash'] or not valid_translation(source[key]['source'],entry.get('text')):parser.error('No current automatic draft for that key.')
            manual[key]={'html':thaw(entry['text'],source[key]['replacements']),'source_hash':source[key]['source_hash']}
        else:
            if key not in manual:parser.error('No authored translation for that key.')
            if isinstance(manual[key],str):manual[key]={'text':manual[key]}
            manual[key]['source_hash']=source[key]['source_hash']
        manual_path.write_text(yaml.safe_dump(manual,allow_unicode=True,sort_keys=False,width=1000))
    elif args.translate:
        missing=[k for k,v in source.items() if k not in manual and (cache.get(k,{}).get('source_hash')!=v['source_hash'] or not valid_translation(v['source'],cache.get(k,{}).get('text')))]
        if args.limit:missing=missing[:args.limit]
        if missing:
            api_key=os.environ.get('GOOGLE_TRANSLATE_API_KEY')
            if not api_key:parser.error('Set GOOGLE_TRANSLATE_API_KEY in your environment. No API request was made; offline drafts remain available.')
            # Small batches keep requests bounded. Persist each successful batch to permit resumption.
            for start in range(0,len(missing),8):
                keys=missing[start:start+8];texts=[source[k]['source'] for k in keys]
                translated=google_translate(texts,args.language,api_key)
                for key,text in zip(keys,translated):
                    if not valid_translation(source[key]['source'],text):raise ValueError(f'Provider changed protected placeholders for {key}; that result was not saved.')
                    cache[key]={'text':text,'source_hash':source[key]['source_hash'],'provider':'google-cloud-translation'}
                dump_json(cache_path,cache)
                print(f'Translated {min(start+8,len(missing))}/{len(missing)} units.')
        else:print('All machine translations are current; no API request needed.')
    else:
        report=read_json(ROOT/f'translations/reports/{args.language}.json',{})
        for status,keys in report.items():
            print(f'{status}: {len(keys)}')
            for key in keys:print('  '+key)
        return
    subprocess.run([sys.executable,str(ROOT/'scripts/build_site.py')],check=True,cwd=ROOT)

if __name__=='__main__':
    try:main()
    except (RuntimeError,ValueError) as error:raise SystemExit(str(error))
