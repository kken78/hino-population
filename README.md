# 地区別人口（日野町データポータル・非公式）

https://kken78.github.io/hino-population/

滋賀県日野町が毎月公表している「人口情報」（住民基本台帳にもとづく行政区ごとの世帯数・男・女・計）のうち、7地区の「地区合計」欄と最下段の「合計」欄を月ごとに並べたページです。

出典：日野町「[日野町人口情報の詳細](https://www.town.shiga-hino.lg.jp/0000002185.html)」の各月末の PDF

## ファイル

| ファイル | 中身 |
|---|---|
| `index.html` | 画面。`data.js` を読むだけで、外部の CSS・JavaScript・フォントは読み込まない |
| `data/population.json` | 転記した値（正本）。月は `months`、地区ごとに `hh`（世帯数）・`m`（男）・`f`（女）・`t`（計） |
| `data/sources.tsv` | 出典の台帳（月・PDF の URL・バイト数・sha256・取得日） |
| `data.js` | `data/population.json` から作る画面用のファイル。直接編集しない |
| `tools/build_data.py` | 検算して `data.js` を作る（標準ライブラリのみ） |

## 毎月の更新

1. 町のページから新しい月の PDF を取得し、`data/sources.tsv` に1行足す（URL・バイト数・sha256・取得日）。
2. `data/population.json` の `months` と `labels` に月を足し、各地区と `total` の `hh`・`m`・`f`・`t` に値を足す。
3. `python3 tools/build_data.py` を実行する。次の検算がすべて合ったときだけ `data.js` が書き出される。
   - 各地区・町全体で 男 ＋ 女 ＝ 計
   - 7地区の合計 ＝ 町全体の合計（世帯数・男・女・計）
   - 値のある月がすべて `data/sources.tsv` に載っている

値を確認できない月は、配列に `null` を入れ、`missing` に理由を書く（画面では点線でつなぎ、理由を表示する）。

町のページには直近およそ1年分しか載らないため、古い月は取得できなくなる。

## 未確認の月

- 令和8年5月末：町のページで「R8.5.pdf」のリンク先が令和8年6月末の PDF になっている（2026年11月5日時点）。

## ライセンス

コードは MIT License（[LICENSE](LICENSE)）。`data/` の構造は CC BY 4.0（表示は https://github.com/kken78/hino-population ）。転記した数値は日野町の公表資料によるもので、このリポジトリのライセンスの対象外。
