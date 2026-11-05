#!/usr/bin/env python3
"""data/population.json を検算し、画面が読む data.js を作る（標準ライブラリのみ）。

検算:
  1. 各地区・総計で 男 + 女 = 計
  2. 7地区の合計 = 総計（世帯数・男・女・計のそれぞれ）
  3. data/sources.tsv に、値のある月がすべて載っている
どれかが合わなければ data.js を書かずに終了コード 1 で止まる。
"""
import csv, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
pop = json.loads((ROOT / 'data/population.json').read_text(encoding='utf-8'))
with open(ROOT / 'data/sources.tsv', encoding='utf-8') as fh:
    src_months = {r['month'] for r in csv.DictReader(fh, delimiter='\t')}

errors = []
months = pop['months']
for i, m in enumerate(months):
    tot = {k: pop['total'][k][i] for k in ('hh', 'm', 'f', 't')}
    if tot['t'] is None:
        if m not in pop.get('missing', {}):
            errors.append(f'{m}: 値がないのに missing に理由がない')
        continue
    if m not in src_months:
        errors.append(f'{m}: data/sources.tsv に出典がない')
    if tot['m'] + tot['f'] != tot['t']:
        errors.append(f'{m} 総計: 男+女≠計')
    for d in pop['districts']:
        if d['m'][i] + d['f'][i] != d['t'][i]:
            errors.append(f"{m} {d['name']}: 男+女≠計")
    for k in ('hh', 'm', 'f', 't'):
        s = sum(d[k][i] for d in pop['districts'])
        if s != tot[k]:
            errors.append(f'{m} {k}: 7地区の合計 {s} ≠ 総計 {tot[k]}')

if errors:
    print('\n'.join(errors))
    sys.exit(1)

(ROOT / 'data.js').write_text(
    '/* data/population.json から tools/build_data.py で生成。直接編集しない。 */\n'
    'const POP = ' + json.dumps(pop, ensure_ascii=False) + ';\n', encoding='utf-8')
print(f'検算 OK（{sum(1 for v in pop["total"]["t"] if v is not None)}か月）。data.js を書き出しました。')
