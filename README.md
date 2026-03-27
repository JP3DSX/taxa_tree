# 🌿 生物分類 汎用系統図ジェネレーター

Wikidata から任意の生物分類群を取得し、インタラクティブな系統図 HTML を生成するツールです。

## バージョン情報

| モジュール | バージョン | 主な変更内容 |
|---|---|---|
| taxa_fetch.py | 2.0 | P171+ ワンショット取得・バッチ取得・GBIF IUCN 補完 |
| taxa_html.py  | 1.7 | 円形レイアウト（RD）・IUCN stat 表示・RD 半径スライダー |

## 必要環境

```
Python 3.10 以上
pip install requests
```

## ファイル構成

```
taxa_tree.py          エントリポイント
module/
  __init__.py
  taxa_fetch.py       Wikidata 取得・モデル構築
  taxa_html.py        HTML 生成・UI
result/               出力先（自動作成）
  taxa_cache_*.json   取得キャッシュ
  index.html          一覧ページ（SPA）
```

## 使い方

```bash
# 通常取得
python taxa_tree.py --qid Q25341          # スズメ目
python taxa_tree.py --qid Q7380           # サル目
python taxa_tree.py --taxon "カラス科"    # 名前で検索
python taxa_tree.py --qid Q25341 --fast   # 科まで（高速）

# HTML のみ再生成（fetch をスキップ）
python taxa_tree.py --qid Q25341 --render
python taxa_tree.py --render              # 最新キャッシュを自動選択

# 一括再生成
python taxa_tree.py --render-all          # standalone: 全キャッシュを再生成
python taxa_tree.py --render-all --web    # web: index.html を再生成

# GitHub Pages 用（JSON と HTML を分離）
python taxa_tree.py --qid Q25341 --web

# 接続診断
python taxa_tree.py --test

# プロキシ / 連絡先設定
python taxa_tree.py --qid Q25341 --proxy http://proxy:8080
python taxa_tree.py --qid Q25341 --email you@example.com
```

## UI 機能

| 機能 | 操作 |
|---|---|
| 展開・折りたたみ | ノードをクリック |
| 詳細表示 | マウスオーバー（デスクトップ） / 長押し（モバイル） |
| Wikipedia を開く | 種ノードをクリック / ツールチップのボタン |
| 言語切り替え | JA / EN ボタン |
| レイアウト | LR（左→右）/ TB（上→下）/ RD（円形） |
| 円形の密度調整 | ⊙ R スライダー（RD モード時のみ表示） |
| 画像アイコン | 🖼 ボタンで ON/OFF |
| 絶滅危惧フィルター | 全 / 絶滅除外 / 絶滅のみ |
| 検索 | 検索ボックスに学名・和名を入力 |
| テーマ | 🌙 / ☀️ ボタン |

## IUCN 保全状況

ノードの外枠色で IUCN レッドリストのステータスを表示します。

| 色 | コード | 意味 |
|---|---|---|
| 赤（太線） | CR | 深刻な危機 |
| 橙 | EN | 危機 |
| 黄橙 | VU | 危急 |
| 黄緑 | NT | 準危急 |
| 灰（破線） | EX | 絶滅 |
| 薄灰（破線） | EW | 野生絶滅 |

データソース: Wikidata P141（一次）/ GBIF iucnRedListCategory（補完）

## 取得速度について

v2.0 からワンショット取得（P171+ 一括）を実装。サル目（27科・72種）での計測例：

| バージョン | 合計時間 | 総クエリ数 |
|---|---|---|
| 旧版（逐次） | ~234秒 | — |
| v1.9（バッチ） | 159秒 | 125回 |
| v2.0（ワンショット） | **33秒** | **43回** |

取得完了後に統計ログが表示されます（`print_stats()`）。

## 調整可能な定数

```python
# taxa_fetch.py
OUTPUT_DIR       = "result"   # 出力先フォルダ
BATCH_PARENT_SIZE = 20        # バッチ取得のまとめ件数
ONESHOT_LIMIT    = 5000       # ワンショット1クエリの取得上限行数
ONESHOT_TIMEOUT  = 55         # ワンショットのタイムアウト秒数
DEFAULT_SPLIT    = "family"   # Phase1/2 の分割ランク
```

## GitHub Pages 運用

```bash
# 取得 → コミット → 公開
python taxa_tree.py --qid Q7380 --web
git add result/
git commit -m "Add Q7380 Primates"
git push
```

公開 URL 例: `https://username.github.io/taxa_tree/`

## 開発クレジット

- データソース: [Wikidata](https://www.wikidata.org/) / [GBIF](https://www.gbif.org/) / [Wikimedia Commons](https://commons.wikimedia.org/)
- 可視化: [D3.js](https://d3js.org/) v7
- 開発: Claude Sonnet 4.6 (Anthropic) との対話型ノーコード開発
- 人間の担当: 要件定義・動作確認・方針決定# 🌿 生物分類 汎用系統図ジェネレーター

Wikidata から任意の生物分類群を取得し、インタラクティブな系統図 HTML を生成するツールです。

## バージョン情報

| モジュール | バージョン | 主な変更内容 |
|---|---|---|
| taxa_fetch.py | 2.0 | P171+ ワンショット取得・バッチ取得・GBIF IUCN 補完 |
| taxa_html.py  | 1.7 | 円形レイアウト（RD）・IUCN stat 表示・RD 半径スライダー |

## 必要環境

```
Python 3.10 以上
pip install requests
```

## ファイル構成

```
taxa_tree.py          エントリポイント
module/
  __init__.py
  taxa_fetch.py       Wikidata 取得・モデル構築
  taxa_html.py        HTML 生成・UI
result/               出力先（自動作成）
  taxa_cache_*.json   取得キャッシュ
  index.html          一覧ページ（SPA）
```

## 使い方

```bash
# 通常取得
python taxa_tree.py --qid Q25341          # スズメ目
python taxa_tree.py --qid Q7380           # サル目
python taxa_tree.py --taxon "カラス科"    # 名前で検索
python taxa_tree.py --qid Q25341 --fast   # 科まで（高速）

# HTML のみ再生成（fetch をスキップ）
python taxa_tree.py --qid Q25341 --render
python taxa_tree.py --render              # 最新キャッシュを自動選択

# 一括再生成
python taxa_tree.py --render-all          # standalone: 全キャッシュを再生成
python taxa_tree.py --render-all --web    # web: index.html を再生成

# GitHub Pages 用（JSON と HTML を分離）
python taxa_tree.py --qid Q25341 --web

# 接続診断
python taxa_tree.py --test

# プロキシ / 連絡先設定
python taxa_tree.py --qid Q25341 --proxy http://proxy:8080
python taxa_tree.py --qid Q25341 --email you@example.com
```

## UI 機能

| 機能 | 操作 |
|---|---|
| 展開・折りたたみ | ノードをクリック |
| 詳細表示 | マウスオーバー（デスクトップ） / 長押し（モバイル） |
| Wikipedia を開く | 種ノードをクリック / ツールチップのボタン |
| 言語切り替え | JA / EN ボタン |
| レイアウト | LR（左→右）/ TB（上→下）/ RD（円形） |
| 円形の密度調整 | ⊙ R スライダー（RD モード時のみ表示） |
| 画像アイコン | 🖼 ボタンで ON/OFF |
| 絶滅危惧フィルター | 全 / 絶滅除外 / 絶滅のみ |
| 検索 | 検索ボックスに学名・和名を入力 |
| テーマ | 🌙 / ☀️ ボタン |

## IUCN 保全状況

ノードの外枠色で IUCN レッドリストのステータスを表示します。

| 色 | コード | 意味 |
|---|---|---|
| 赤（太線） | CR | 深刻な危機 |
| 橙 | EN | 危機 |
| 黄橙 | VU | 危急 |
| 黄緑 | NT | 準危急 |
| 灰（破線） | EX | 絶滅 |
| 薄灰（破線） | EW | 野生絶滅 |

データソース: Wikidata P141（一次）/ GBIF iucnRedListCategory（補完）

## 取得速度について

v2.0 からワンショット取得（P171+ 一括）を実装。サル目（27科・72種）での計測例：

| バージョン | 合計時間 | 総クエリ数 |
|---|---|---|
| 旧版（逐次） | ~234秒 | — |
| v1.9（バッチ） | 159秒 | 125回 |
| v2.0（ワンショット） | **33秒** | **43回** |

取得完了後に統計ログが表示されます（`print_stats()`）。

## 調整可能な定数

```python
# taxa_fetch.py
OUTPUT_DIR       = "result"   # 出力先フォルダ
BATCH_PARENT_SIZE = 20        # バッチ取得のまとめ件数
ONESHOT_LIMIT    = 5000       # ワンショット1クエリの取得上限行数
ONESHOT_TIMEOUT  = 55         # ワンショットのタイムアウト秒数
DEFAULT_SPLIT    = "family"   # Phase1/2 の分割ランク
```

## GitHub Pages 運用

```bash
# 取得 → コミット → 公開
python taxa_tree.py --qid Q7380 --web
git add result/
git commit -m "Add Q7380 Primates"
git push
```

公開 URL 例: `https://username.github.io/taxa_tree/`

## 開発クレジット

- データソース: [Wikidata](https://www.wikidata.org/) / [GBIF](https://www.gbif.org/) / [Wikimedia Commons](https://commons.wikimedia.org/)
- 可視化: [D3.js](https://d3js.org/) v7
- 開発: Claude Sonnet 4.6 (Anthropic) との対話型ノーコード開発
- 人間の担当: 要件定義・動作確認・方針決定# 🌿 生物分類 汎用系統図ジェネレーター

Wikidata から任意の生物分類群を取得し、インタラクティブな系統図 HTML を生成するツールです。

## バージョン情報

| モジュール | バージョン | 主な変更内容 |
|---|---|---|
| taxa_fetch.py | 2.0 | P171+ ワンショット取得・バッチ取得・GBIF IUCN 補完 |
| taxa_html.py  | 1.7 | 円形レイアウト（RD）・IUCN stat 表示・RD 半径スライダー |

## 必要環境

```
Python 3.10 以上
pip install requests
```

## ファイル構成

```
taxa_tree.py          エントリポイント
module/
  __init__.py
  taxa_fetch.py       Wikidata 取得・モデル構築
  taxa_html.py        HTML 生成・UI
result/               出力先（自動作成）
  taxa_cache_*.json   取得キャッシュ
  index.html          一覧ページ（SPA）
```

## 使い方

```bash
# 通常取得
python taxa_tree.py --qid Q25341          # スズメ目
python taxa_tree.py --qid Q7380           # サル目
python taxa_tree.py --taxon "カラス科"    # 名前で検索
python taxa_tree.py --qid Q25341 --fast   # 科まで（高速）

# HTML のみ再生成（fetch をスキップ）
python taxa_tree.py --qid Q25341 --render
python taxa_tree.py --render              # 最新キャッシュを自動選択

# 一括再生成
python taxa_tree.py --render-all          # standalone: 全キャッシュを再生成
python taxa_tree.py --render-all --web    # web: index.html を再生成

# GitHub Pages 用（JSON と HTML を分離）
python taxa_tree.py --qid Q25341 --web

# 接続診断
python taxa_tree.py --test

# プロキシ / 連絡先設定
python taxa_tree.py --qid Q25341 --proxy http://proxy:8080
python taxa_tree.py --qid Q25341 --email you@example.com
```

## UI 機能

| 機能 | 操作 |
|---|---|
| 展開・折りたたみ | ノードをクリック |
| 詳細表示 | マウスオーバー（デスクトップ） / 長押し（モバイル） |
| Wikipedia を開く | 種ノードをクリック / ツールチップのボタン |
| 言語切り替え | JA / EN ボタン |
| レイアウト | LR（左→右）/ TB（上→下）/ RD（円形） |
| 円形の密度調整 | ⊙ R スライダー（RD モード時のみ表示） |
| 画像アイコン | 🖼 ボタンで ON/OFF |
| 絶滅危惧フィルター | 全 / 絶滅除外 / 絶滅のみ |
| 検索 | 検索ボックスに学名・和名を入力 |
| テーマ | 🌙 / ☀️ ボタン |

## IUCN 保全状況

ノードの外枠色で IUCN レッドリストのステータスを表示します。

| 色 | コード | 意味 |
|---|---|---|
| 赤（太線） | CR | 深刻な危機 |
| 橙 | EN | 危機 |
| 黄橙 | VU | 危急 |
| 黄緑 | NT | 準危急 |
| 灰（破線） | EX | 絶滅 |
| 薄灰（破線） | EW | 野生絶滅 |

データソース: Wikidata P141（一次）/ GBIF iucnRedListCategory（補完）

## 取得速度について

v2.0 からワンショット取得（P171+ 一括）を実装。サル目（27科・72種）での計測例：

| バージョン | 合計時間 | 総クエリ数 |
|---|---|---|
| 旧版（逐次） | ~234秒 | — |
| v1.9（バッチ） | 159秒 | 125回 |
| v2.0（ワンショット） | **33秒** | **43回** |

取得完了後に統計ログが表示されます（`print_stats()`）。

## 調整可能な定数

```python
# taxa_fetch.py
OUTPUT_DIR       = "result"   # 出力先フォルダ
BATCH_PARENT_SIZE = 20        # バッチ取得のまとめ件数
ONESHOT_LIMIT    = 5000       # ワンショット1クエリの取得上限行数
ONESHOT_TIMEOUT  = 55         # ワンショットのタイムアウト秒数
DEFAULT_SPLIT    = "family"   # Phase1/2 の分割ランク
```

## GitHub Pages 運用

```bash
# 取得 → コミット → 公開
python taxa_tree.py --qid Q7380 --web
git add result/
git commit -m "Add Q7380 Primates"
git push
```

公開 URL 例: `https://username.github.io/taxa_tree/`

## 開発クレジット

- データソース: [Wikidata](https://www.wikidata.org/) / [GBIF](https://www.gbif.org/) / [Wikimedia Commons](https://commons.wikimedia.org/)
- 可視化: [D3.js](https://d3js.org/) v7
- 開発: Claude Sonnet 4.6 (Anthropic) との対話型ノーコード開発
- 人間の担当: 要件定義・動作確認・方針決定