# 設計の決定

このリポジトリ（地区別人口のページ）の設計の決定を、決めた順に書く。ポータル全体の決まりは hino-portal の DESIGN.md にあり、このリポジトリはそれに従う。

## ADR-1 共通の部品は hino-portal の正本を写す（2026-11-07）

### 状況

hino-portal の DESIGN.md 2章で、ポータルの下のページの構造（共通の見出し、ページの見出し、分野の中のページの一覧、フッター）が決まった。9.1 で、共通の部品は hino-portal に1つだけ置き、各リポジトリはそれを写して、同じであることを CI で確かめると決まった。9.2 の段階1で、各ページの見出し・ナビ・フッター・位置づけの文・`<title>` をそろえる。

### 決定

- 共通の部品（見出し・分野のナビ・ページの一覧・フッター）は、hino-portal の `shared/` の正本（shell.css・header.html・siblings-stat.html・footer.html）を index.html に写す。写した箇所は `<!-- portal-shared:〈名前〉 start -->` と `<!-- portal-shared:〈名前〉 end -->` で囲む。
- ページの構造は hino-portal DESIGN.md 2章による。分野は統計とくらし、ページの題は「地区別人口」とする。
- 写した部品は手で変えない。変えるときは、hino-portal の正本を先に変えてから写し直す。
- CI（`.github/workflows/check.yml`）で、hino-portal を浅く取ってきて `shared/check.py index.html` を走らせ、写したものが正本と同じかを確かめる。

### この段階で変えないもの

ページの色・文字の大きさ・グラフは、hino-portal DESIGN.md 9.2 の段階2以降で直す。
