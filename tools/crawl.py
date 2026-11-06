#!/usr/bin/env python3
"""町の「日野町人口情報の詳細」のページを巡回し、新しい月の PDF を取り込む。

標準ライブラリと pdfplumber（tools/requirements.txt）を使う。町のサイトへの取得は1秒に1件以内。

  1. ページから「令和N年M月末現在」の見出しと PDF のリンクの組を読む。
  2. 台帳（data/sources.tsv）にある月は、PDF を取り直して sha256 を比べる。
     sha256 が違う（差し替え）か、リンクの URL が台帳と違えば、取り込まずに要確認とする。
  3. 台帳に無い月（値が null の月を含む）は PDF を取得し、ページの見出し・ファイル名・
     PDF の中の「令和N年M月末現在」の3つの月が一致し、ほかの月と同じ PDF でなければ、
     sources/<年月>.pdf に保存し、台帳と data/population.json に足す（null の月は値で置き換え、
     missing から消す）。一致しなければ取り込まずに要確認とする。
  4. 足した月より前で、まだ months に無い月は null とし、missing に理由を書く。
  5. tools/build_data.py を実行する。検算が合わなければ、変更を元に戻して止まる。

終了コード: 0 = 正常（変更の有無によらない）、
            2 = 巡回の失敗（ページや PDF の作りが変わった、取得できない、検算が合わない）。
"""
import argparse, bisect, csv, datetime, hashlib, io, json, pathlib, re, subprocess, sys
import time, unicodedata, urllib.error, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE = 'https://www.town.shiga-hino.lg.jp/0000002185.html'
UA = 'hino-population-crawler (+https://github.com/kken78/hino-population)'
INTERVAL = 1.0  # 取得の間隔（秒）
KEYS = ('hh', 'm', 'f', 't')
FIELDS = ('month', 'title', 'url', 'bytes', 'sha256', 'retrieved')
JST = datetime.timezone(datetime.timedelta(hours=9))
RE_ASOF = re.compile(r'令和\s*(\d+|元)\s*年\s*(\d+)\s*月末現在')
RE_FILE = re.compile(r'/R(\d+)\.(\d+)\.pdf$')
NUM = r'([\d,]+)'


class Failure(Exception):
    pass


def wareki(month):
    y, m = map(int, month.split('-'))
    return f'令和{y - 2018}年{m}月'


def label(month):
    y, m = map(int, month.split('-'))
    return f'R{y - 2018}.{m}'


def to_month(reiwa, m):
    return f'{2018 + (1 if reiwa == "元" else int(reiwa))}-{int(m):02d}'


def next_month(month):
    y, m = map(int, month.split('-'))
    return f'{y + m // 12}-{m % 12 + 1:02d}'


_last = [0.0]


def fetch(url):
    err = None
    for attempt in range(3):
        wait = _last[0] + INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except (urllib.error.URLError, TimeoutError) as e:
            err = e
            time.sleep(5 * (attempt + 1))
    raise Failure(f'{url} を取得できない（{err}）')


def parse_page(html):
    """ページの各月の見出しと PDF のリンクを [(月, URL)] で返す。"""
    entries = []
    for block in re.findall(r'<div class="mol_attachfileblock[^"]*">(.*?)</div>', html, re.S):
        t = re.search(r'<p class="mol_attachfileblock_title">(.*?)</p>', block, re.S)
        if not t:
            continue
        m = RE_ASOF.search(unicodedata.normalize('NFKC', re.sub(r'<[^>]+>', '', t.group(1))))
        if not m:
            continue
        hrefs = re.findall(r'href="([^"]+\.pdf)"', block, re.I)
        month = to_month(*m.groups())
        if len(hrefs) != 1:
            raise Failure(f'{wareki(month)}末の見出しに PDF のリンクが {len(hrefs)} 件ある（1件のはず）')
        entries.append((month, urllib.parse.urljoin(PAGE, hrefs[0])))
    if not entries:
        raise Failure('ページに「令和N年M月末現在」の見出しと PDF のリンクが見つからない（ページの作りが変わった可能性）')
    months = [m for m, _ in entries]
    dup = sorted({m for m in months if months.count(m) > 1})
    if dup:
        raise Failure(f'ページに同じ月の見出しが複数ある：{", ".join(dup)}')
    return entries


def extract(data, names, url):
    """PDF から「令和N年M月末現在」の月と、7地区の地区合計・最下段の合計を取り出す。"""
    import pdfplumber
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        text = unicodedata.normalize('NFKC', '\n'.join(p.extract_text() or '' for p in pdf.pages))
    m = RE_ASOF.search(text)
    if not m:
        raise Failure(f'{url}：PDF に「令和N年M月末現在」の表記が見つからない')
    rows = {}
    for name, *nums in re.findall(r'(\S+?)地区合計\s+' + r'\s+'.join([NUM] * 4), text):
        rows.setdefault(name, []).append([int(x.replace(',', '')) for x in nums])
    rows['total'] = [[int(x.replace(',', '')) for x in t]
                     for t in re.findall(r'(?<!地区)合計\s+' + r'\s+'.join([NUM] * 4), text)]
    want = set(names) | {'total'}
    bad = [k for k in want if len(rows.get(k, [])) != 1] + sorted(set(rows) - want)
    if bad:
        raise Failure(f'{url}：地区合計・合計の行を1行ずつ取り出せない（{", ".join(bad)}）')
    return to_month(*m.groups()), {k: rows[k][0] for k in names + ['total']}


def set_month(pop, month, vals):
    """month の値を vals（{地区名・'total': [世帯数, 男, 女, 計]}、None なら null）にする。"""
    if month in pop['months']:
        i, insert = pop['months'].index(month), False
    else:
        i, insert = bisect.bisect(pop['months'], month), True
        pop['months'].insert(i, month)
        pop['labels'].insert(i, label(month))
    for key, rec in [(d['name'], d) for d in pop['districts']] + [('total', pop['total'])]:
        for j, k in enumerate(KEYS):
            v = None if vals is None else vals[key][j]
            if insert:
                rec[k].insert(i, v)
            else:
                rec[k][i] = v


def crawl():
    today = datetime.datetime.now(JST).date().isoformat()
    pop_path, src_path = ROOT / 'data/population.json', ROOT / 'data/sources.tsv'
    pop_text, src_text = pop_path.read_text(encoding='utf-8'), src_path.read_text(encoding='utf-8')
    pop = json.loads(pop_text)
    ledger = list(csv.DictReader(src_text.splitlines(), delimiter='\t'))
    by_month = {r['month']: r for r in ledger}
    names = [d['name'] for d in pop['districts']]
    rep = {'checked': today, 'page': PAGE, 'added': [], 'nulls': [], 'review': [], 'log': [],
           'build': '', 'changed': False}

    def log(s):
        rep['log'].append(s)
        print(s)

    def review(month, kind, detail):
        known = month in pop.get('missing', {})
        rep['review'].append({'month': month, 'kind': kind, 'detail': detail, 'known': known})
        print(f'要確認{"（既知）" if known else ""} {month} {kind}：{detail}')

    entries = parse_page(fetch(PAGE).decode('utf-8', 'replace'))
    page = dict(entries)
    log(f'ページの月：{len(entries)}件（{min(page)}〜{max(page)}）')
    cache = {}

    def get(url):
        if url not in cache:
            cache[url] = fetch(url)
        return cache[url]

    # 2. 台帳にある月：差し替えとリンクの変更
    for r in ledger:
        m = r['month']
        if m not in page:
            log(f'{m}：ページに載っていない（掲載が終わった）')
            continue
        if page[m] != r['url']:
            review(m, 'リンクの変更', f'台帳の URL {r["url"]} ／ ページの URL {page[m]}')
            continue
        data = get(r['url'])
        sha = hashlib.sha256(data).hexdigest()
        if sha != r['sha256'] or len(data) != int(r['bytes']):
            review(m, '差し替え', f'台帳 {r["bytes"]} バイト sha256 {r["sha256"]} ／ '
                   f'今 {len(data)} バイト sha256 {sha}（{r["url"]}）')
            continue
        local = ROOT / 'sources' / f'{m}.pdf'
        if not local.exists():
            local.parent.mkdir(exist_ok=True)
            local.write_bytes(data)
            log(f'{m}：sources/{local.name} が無かったので、取り直した PDF（sha256 が台帳と一致）を置いた')

    # 3. 台帳に無い月：3つの月の一致と、ほかの月と同じ PDF でないか
    ledger_sha = {r['sha256']: r['month'] for r in ledger}
    adds, mismatch = {}, {}
    for m, url in entries:
        if m in by_month:
            continue
        data = get(url)
        sha = hashlib.sha256(data).hexdigest()
        f = RE_FILE.search(url)
        fmonth = to_month(*f.groups()) if f else None
        pmonth, vals = extract(data, names, url)
        problems = []
        if fmonth != m:
            problems.append(f'リンク先のファイル名は {url.rsplit("/", 1)[1]}'
                            + (f'（{wareki(fmonth)}）' if fmonth else ''))
        if pmonth != m:
            problems.append(f'PDF の中の表記は{wareki(pmonth)}末現在')
        same = ledger_sha.get(sha) or next((a for a, x in adds.items() if x['sha256'] == sha), None)
        if same:
            problems.append(f'{same} と同じ PDF（sha256 {sha}）')
        if problems:
            detail = f'ページの見出しは{wareki(m)}末現在、' + '、'.join(problems)
            mismatch[m] = detail
            review(m, '月の不一致', detail)
            continue
        adds[m] = {'month': m, 'label': label(m), 'title': f'人口情報 {wareki(m)}末現在', 'url': url,
                   'bytes': len(data), 'sha256': sha, 'path': f'sources/{m}.pdf',
                   'filled': m in pop['months'], 'values': vals, 'data': data}
        log(f'{m}：取り込む（{url}、{len(data)} バイト）')

    # 値が null のままの月で、ページに載っていないもの
    for m in pop.get('missing', {}):
        if m not in page and m not in adds:
            log(f'{m}：値は null のまま（ページに載っていない）')

    if not adds:
        print('変更なし')
        return rep

    # 4. 足した月より前で、まだ months に無い月は null にする
    nulls = {}
    m, hi = min(pop['months'] + list(adds)), max(pop['months'] + list(adds))
    while m < hi:
        if m not in pop['months'] and m not in adds:
            if m in mismatch:
                reason = f'町のページで{wareki(m)}末の資料を確認できないため空けています（{today} 時点。{mismatch[m]}）。'
            else:
                reason = f'{today} の巡回の時点で、町のページに{wareki(m)}末の掲載がなかったため空けています。'
                review(m, '掲載がない', f'{wareki(m)}末の見出しがページに無い。値を null とした')
            nulls[m] = reason
        m = next_month(m)

    # 5. 書き込みと検算
    written = []
    try:
        for m, a in sorted(adds.items()):
            p = ROOT / a['path']
            p.parent.mkdir(exist_ok=True)
            p.write_bytes(a['data'])
            written.append(p)
            ledger.append({'month': m, 'title': a['title'], 'url': a['url'], 'bytes': str(a['bytes']),
                           'sha256': a['sha256'], 'retrieved': today})
            set_month(pop, m, a['values'])
            pop.get('missing', {}).pop(m, None)
        for m, reason in sorted(nulls.items()):
            set_month(pop, m, None)
            pop.setdefault('missing', {})[m] = reason
        ledger.sort(key=lambda r: r['month'])
        pop['missing'] = dict(sorted(pop.get('missing', {}).items()))
        pop_path.write_text(json.dumps(pop, ensure_ascii=False, indent=1), encoding='utf-8')
        with open(src_path, 'w', encoding='utf-8', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS, delimiter='\t', lineterminator='\n')
            w.writeheader()
            w.writerows(ledger)
        res = subprocess.run([sys.executable, str(ROOT / 'tools/build_data.py')],
                             capture_output=True, text=True)
        rep['build'] = (res.stdout + res.stderr).strip()
        print(rep['build'])
        if res.returncode != 0:
            raise Failure('取り出した値で検算が合わない：\n' + rep['build'])
    except BaseException:
        pop_path.write_text(pop_text, encoding='utf-8')
        src_path.write_text(src_text, encoding='utf-8')
        for p in written:
            p.unlink()
        print('変更を元に戻しました。')
        raise

    for a in adds.values():
        del a['data']
    rep['added'] = [adds[m] for m in sorted(adds)]
    rep['nulls'] = [{'month': m, 'reason': r} for m, r in sorted(nulls.items())]
    rep['changed'] = True
    rep['branch_month'] = max(list(adds) + list(nulls))
    print('変更あり：' + '、'.join(f'{m} を取り込んだ' for m in sorted(adds))
          + ''.join(f'、{m} を null にした' for m in sorted(nulls)))
    return rep


def render(rep):
    """PR の本文・実行の記録に載せる Markdown。"""
    out = [f'町のページ（{rep["page"]}）を {rep["checked"]} に巡回した結果。', '']
    if rep['added']:
        out.append('## 足した月')
        for a in rep['added']:
            out += ['', f'### {a["title"]}' + ('（null を値で置き換えた）' if a['filled'] else ''), '',
                    f'- PDF：{a["url"]}', f'- 保存先：`{a["path"]}`（{a["bytes"]} バイト）',
                    f'- sha256：`{a["sha256"]}`', '',
                    '| 地区 | 世帯数 | 男 | 女 | 計 |', '|---|--:|--:|--:|--:|']
            for k, v in a['values'].items():
                out.append(f'| {"町全体（合計）" if k == "total" else k} | ' + ' | '.join(f'{x:,}' for x in v) + ' |')
        out.append('')
    if rep['nulls']:
        out += ['## null にした月', ''] + [f'- {n["month"]}：{n["reason"]}' for n in rep['nulls']] + ['']
    if rep['build']:
        out += ['## 検算の結果（tools/build_data.py）', '', '```', rep['build'], '```', '']
    new = [r for r in rep['review'] if not r['known']]
    known = [r for r in rep['review'] if r['known']]
    out += ['## 要確認の事項', '']
    out += [f'- {r["month"]} {r["kind"]}：{r["detail"]}' for r in new] or ['- なし']
    if known:
        out += ['', '値を null にして missing に理由を書いてある月（以前からの要確認）：', '']
        out += [f'- {r["month"]} {r["kind"]}：{r["detail"]}' for r in known]
    out += ['', '## 巡回の記録', ''] + [f'- {s}' for s in rep['log']]
    return '\n'.join(out) + '\n'


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--report', help='結果の JSON を書き出す先')
    ap.add_argument('--summary', help='結果の Markdown を書き出す先')
    args = ap.parse_args()
    try:
        rep = crawl()
    except Failure as e:
        print(f'巡回に失敗した：{e}', file=sys.stderr)
        sys.exit(2)
    if args.report:
        pathlib.Path(args.report).write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding='utf-8')
    if args.summary:
        pathlib.Path(args.summary).write_text(render(rep), encoding='utf-8')


if __name__ == '__main__':
    main()
