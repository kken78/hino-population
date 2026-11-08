# 地区別人口（日野町データポータル・非公式）

https://kken78.github.io/hino-population/

滋賀県日野町が毎月公表している「人口情報」（住民基本台帳にもとづく行政区ごとの世帯数・男・女・計）のうち、7地区の「地区合計」欄と最下段の「合計」欄を月ごとに並べたページです。

出典：日野町「[日野町人口情報の詳細](https://www.town.shiga-hino.lg.jp/0000002185.html)」の各月末の PDF

## ファイル

| ファイル | 中身 |
|---|---|
| `index.html` | 画面。`data.js` を読むだけで、外部の CSS・JavaScript・フォントは読み込まない |
| `DESIGN.md` | 設計の決定（ADR） |
| `og.png` | SNS で共有したときに出る画像（OGP 画像、1200×630） |
| `assets/og.svg` | OGP 画像の編集元 |
| `data/population.json` | 転記した値（正本）。月は `months`、地区ごとに `hh`（世帯数）・`m`（男）・`f`（女）・`t`（計） |
| `data/sources.tsv` | 出典の台帳（月・PDF の URL・バイト数・sha256・取得日） |
| `sources/<年月>.pdf` | 出典の PDF の写し（例 `sources/2026-09.pdf`）。町のページから消えた後も原典を残すため、台帳と一緒にコミットする |
| `data.js` | `data/population.json` から作る画面用のファイル。直接編集しない |
| `tools/build_data.py` | 検算して `data.js` を作る（標準ライブラリのみ） |
| `tools/crawl.py` | 町のページを巡回し、新しい月を取り込む（標準ライブラリと pdfplumber） |
| `tools/requirements.txt` | `tools/crawl.py` が使う pdfplumber のバージョン |
| `.github/workflows/update-data.yml` | 毎月5日・20日に `tools/crawl.py` を実行し、PR か Issue を作る |
| `.github/workflows/keepalive.yml` | 定期実行が止まらないようにする（毎月1日） |
| `.github/workflows/check.yml` | PR と main への push のたびに検算し、`data.js` がコミットされたものと一致するかと、共通の部品が hino-portal の正本と同じかを確かめる |

## 共通の部品

`index.html` の見出し・分野のナビ・ページの一覧・フッターと、その CSS（`<!-- portal-shared:〈名前〉 start/end -->` で囲んだ箇所）は、[hino-portal](https://github.com/kken78/hino-portal) の `shared/` の正本の写し（DESIGN.md ADR-1）。手元では `python3 <hino-portal>/shared/check.py index.html` で、正本と同じかを確かめる（CI でも同じ検査を行う）。

## 自動更新の仕組み

GitHub Actions（`.github/workflows/update-data.yml`）が、毎月5日と20日の 7:00（日本時間）に `tools/crawl.py` を実行する。Actions の画面から手で実行することもできる（workflow_dispatch）。

### 巡回するページ

- 日野町「日野町人口情報の詳細」 https://www.town.shiga-hino.lg.jp/0000002185.html
- 上のページにリンクされている各月末の PDF（`https://www.town.shiga-hino.lg.jp/cmsfiles/contents/0000002/2185/R{令和の年}.{月}.pdf`）

町のサイトに robots.txt は無い（2026年11月6日に確認。`/robots.txt` は 404）。取得は1秒に1件以内で、1回の巡回でページ1件と、ページに載っている PDF（直近およそ1年分、いま12件）を取得する。

### tools/crawl.py がすること

1. ページから「令和N年M月末現在」の見出しと PDF のリンクの組を読む。
2. 台帳にある月は、PDF を取り直して sha256 を台帳と比べる。sha256 が違う（差し替え）か、リンクの URL が台帳と違えば、取り込まずに「要確認」とする。
3. 台帳に無い月（値が `null` の月を含む）は PDF を取得し、次の3つの月が一致し、ほかの月と同じ PDF でなければ取り込む。一致しなければ取り込まずに「要確認」とする。
   - ページの見出しの月（令和N年M月末現在）
   - リンク先のファイル名の月（R{N}.{M}.pdf）
   - PDF の中の表記の月（人口情報 令和N年M月末現在）
4. 取り込む月は、PDF を `sources/<年月>.pdf` に保存し、`data/sources.tsv` に1行足し、PDF の7地区の「地区合計」欄と最下段の「合計」欄の値（世帯数・男・女・計）を `data/population.json` に足す。値が `null` だった月は値で置き換え、`missing` から消す。
5. 取り込んだ月より前で、まだ `months` に無い月（町のページに載らなかった月）は `null` とし、`missing` に「○年○月○日の巡回の時点で、町のページに掲載がなかった」と書く。`null` の月は以後の巡回でも毎回ページを確かめ、正しい PDF が載れば4のとおり取り込む。
6. `tools/build_data.py` を実行する。検算が合わなければ、変更を元に戻して終了コード 2 で止まる。

ページの作りが変わって見出しやリンクが読めないとき、PDF から地区合計と合計の8行を1行ずつ取り出せないとき、取得できないときも、終了コード 2 で止まる。

### ワークフローが作るもの

- 取り込んだ月があれば、`update/population-<年月>` ブランチに commit し、PR を作る。本文には、足した月、取り出した値の表、PDF の URL・保存先・sha256、検算の結果、要確認の事項を載せる。同じブランチの PR が開いていれば本文を更新する。前の月の自動取り込みの PR が開いたままなら、新しい PR に含めたことを書いて閉じる。自動ではマージしない。
- 取り込む月が無く、新しい要確認の事項だけがあれば、事項ごとに Issue（題「人口情報の要確認：<年月> <種類>」）を作る。同じ題の Issue が開いていれば作らない。`missing` に理由が書いてある月の要確認は、実行の記録に出すだけにする。
- 巡回に失敗したら、ジョブを失敗させ、Issue「人口情報の巡回に失敗した」を作る。同じ題の Issue が開いていれば作らない。
- `keepalive.yml` は毎月1日に定期実行のワークフローを有効にし直し、main の最終コミットから45日以上空いていれば `keepalive` ブランチに空のコミットを送る（60日間動きが無いと GitHub が定期実行を止めるため）。

GITHUB_TOKEN で作った PR では `check.yml` が自動では動かない。検算は `update-data.yml` の中で行い、結果を PR 本文に載せている。

### 必要な設定

Settings → Actions → General → Workflow permissions を「Read and write permissions」にし、「Allow GitHub Actions to create and approve pull requests」をオンにする。

### 人が確かめること

- PR が来たら、本文の表の値を `sources/<年月>.pdf` の各地区の「地区合計」欄と最下段の「合計」欄と見比べ、PDF の上の「人口情報 令和○年○月末現在」が足した月と一致していることを確かめてからマージする。
- PR に「null にした月」があれば、町のページで掲載が無いことを確かめ、下の「未確認の月」に書く。後の巡回で取り込まれたら、「未確認の月」から消す。
- 要確認の Issue が来たら、次のように扱う。
  - 差し替え：台帳の版（`sources/<年月>.pdf`）と町のページの新しい版を見比べる。値が変わっていれば、下の「毎月の更新」の手順で `sources/`・台帳・`data/population.json` を新しい版に直す。
  - リンクの変更・月の不一致：町のページのリンク先が正しい月の PDF かを確かめる。確かめられない月は `null` にし、`missing` に理由を書き、下の「未確認の月」に書く。町が直せば、次の巡回で取り込まれる。
- 巡回に失敗した Issue が来たら、実行の記録で理由を確かめる。町のサイトの作りが変わったときは `tools/crawl.py` を直し、それまでは下の「毎月の更新」の手順で手で取り込む。町のページには直近およそ1年分しか載らないので、早めに対応する。

### 手元で実行する

```
python3 -m pip install -r tools/requirements.txt
python3 tools/crawl.py
```

新しい月が無ければ「変更なし」と出て終わる。

## 毎月の更新

手で取り込む場合の手順。

1. 町のページから新しい月の PDF を取得し、`sources/<年月>.pdf` に保存して、`data/sources.tsv` に1行足す（URL・バイト数・sha256・取得日）。
2. `data/population.json` の `months` と `labels` に月を足し、各地区と `total` の `hh`・`m`・`f`・`t` に値を足す。
3. `python3 tools/build_data.py` を実行する。次の検算がすべて合ったときだけ `data.js` が書き出される。
   - 各地区・町全体で 男 ＋ 女 ＝ 計
   - 7地区の合計 ＝ 町全体の合計（世帯数・男・女・計）
   - 値のある月がすべて `data/sources.tsv` に載っている
   - `data/sources.tsv` の各月の PDF が `sources/<年月>.pdf` にあり、バイト数と sha256 が台帳と一致する

値を確認できない月は、配列に `null` を入れ、`missing` に理由を書く（画面では点線でつなぎ、理由を表示する）。

町のページには直近およそ1年分しか載らないため、古い月は取得できなくなる。取得した PDF は `sources/` に残す。

## 未確認の月

- 令和8年5月末：町のページで「R8.5.pdf」のリンク先が令和8年6月末の PDF になっている（2026年11月5日時点。11月6日の巡回でも同じ）。

## ライセンス

コードは MIT License（[LICENSE](LICENSE)）。`data/` の構造は CC BY 4.0（表示は https://github.com/kken78/hino-population ）。転記した数値と `sources/` の PDF は日野町の公表資料によるもので、このリポジトリのライセンスの対象外。
