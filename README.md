# taxa_tree.py

生物分類 汎用系統図ジェネレーター

Wikidata SPARQL API から任意の分類群を BFS（幅優先探索）で取得し、
単体配布可能なインタラクティブ HTML 系統図を生成します。

---

## 目次

1. [概要](#概要)
2. [ファイル構成](#ファイル構成)
3. [インストール](#インストール)
4. [使い方](#使い方)
5. [出力ファイルの構成](#出力ファイルの構成)
6. [HTML の操作方法](#html-の操作方法)
7. [コード構成](#コード構成)
8. [バージョン履歴](#バージョン履歴)
9. [既知の制約と改善候補](#既知の制約と改善候補)
10. [参考文献](#参考文献)

---

## 概要

- **対応範囲**: 鳥類・哺乳類・植物・昆虫・魚類・菌類など生物分類全般
- **データソース**: [Wikidata](https://www.wikidata.org/) / [Wikimedia Commons](https://commons.wikimedia.org/)
- **出力**: `result/taxa_<和名>_<QID>.html`（画像表示にはインターネット接続が必要）
- **依存ライブラリ**: `requests`（`pip install requests`）のみ

---

## ファイル構成

```
プロジェクトフォルダ/
├── taxa_tree.py                    エントリポイント（引数解析・保存制御）
├── README.md                       このファイル
├── .github/
│   └── workflows/
│       └── pages.yml               GitHub Pages 自動デプロイ
├── module/
│   ├── __init__.py                 パッケージ宣言
│   ├── taxa_fetch.py               データ取得・モデル構築
│   └── taxa_html.py                HTML生成・UI
└── result/                         出力先（実行時に自動作成）
    ├── taxa_cache_Q25341.json       キャッシュ（JSON）
    └── taxa_スズメ目_Q25341.html    系統図 HTML
```

### 各ファイルの責務

| ファイル | 行数 | 責務 |
|---|---|---|
| `taxa_tree.py` | 227行 | 引数解析・QID解決・キャッシュ管理・HTML保存 |
| `module/taxa_fetch.py` | 755行 | SPARQL・BFS・進捗バー・接続診断 |
| `module/taxa_html.py` | 784行 | HTML テンプレート・`make_html()` |
| `module/__init__.py` | 1行 | パッケージ宣言 |

**UI を変更する場合は `module/taxa_html.py` のみを編集すればよく、`module/taxa_fetch.py` のレビューは不要です。**

---

## インストール

```bat
pip install requests
```

---

## 使い方

```bat
:: 接続診断（初回・社内プロキシ環境では必須）
python taxa_tree.py --test

:: QID で直接指定
python taxa_tree.py --qid Q25341          # スズメ目
python taxa_tree.py --qid Q23038          # タカ目
python taxa_tree.py --qid Q10908          # 哺乳綱
python taxa_tree.py --qid Q756            # バラ属

:: 学名・和名で検索（候補一覧から番号を選択）
python taxa_tree.py --taxon "Passeriformes"
python taxa_tree.py --taxon "カラス科"
python taxa_tree.py --taxon "Rosa"
```

### オプション一覧

| 引数 | デフォルト | 説明 |
|---|---|---|
| `--qid QID` | — | Wikidata QID を直接指定 |
| `--taxon NAME` | — | 学名・和名で検索（`--qid` と排他） |
| `--split RANK` | `family` | Phase 1/2 の分割ランク |
| `--stop RANK` | `species` | 取得の終端ランク |
| `--fast` | false | Phase 1（`--split` まで）で終了 |
| `--cached` | false | `result/` のキャッシュを再利用して HTML のみ再生成 |
| `--output FILE` | 自動生成 | 出力 HTML ファイルパスを明示指定 |
| `--proxy URL` | 環境変数 | プロキシ URL |
| `--test` | — | 接続診断のみ実行 |

```bat
:: オプション組み合わせ例
python taxa_tree.py --qid Q25341 --fast                    # 科まで高速取得
python taxa_tree.py --qid Q25341 --split genus             # 属レベルで Phase 分割
python taxa_tree.py --qid Q25341 --cached                  # キャッシュ再利用
python taxa_tree.py --qid Q25341 --output docs/index.html  # 出力先を指定

:: 社内プロキシ環境
python taxa_tree.py --proxy http://proxy.example.com:8080 --qid Q25341
set HTTPS_PROXY=http://proxy.example.com:8080
```

---

## 出力ファイルの構成

### 出力フォルダの変更

`taxa_tree.py` **L54** の `OUTPUT_DIR` を変更するだけで、キャッシュと HTML の両方の出力先が変わります。

```python
# taxa_tree.py L54
OUTPUT_DIR = "result"   # ← ここを変更するだけ

# 変更例
OUTPUT_DIR = "docs"            # GitHub Pages 標準構成
OUTPUT_DIR = "D:/bird_data"    # 絶対パスも指定可能
```

### GitHub Pages 自動デプロイ（GitHub Actions）

```yaml
# .github/workflows/pages.yml
name: Deploy result/ to GitHub Pages
on:
  push:
    branches: ["main"]
    paths: ["result/**"]
permissions:
  contents: read
  pages: write
  id-token: write
jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/upload-pages-artifact@v3
        with:
          path: result
      - id: deployment
        uses: actions/deploy-pages@v4
```

Settings → Pages → Source を **「GitHub Actions」** に設定。

---

## HTML の操作方法

### PC（マウス）

| 操作 | 動作 |
|---|---|
| ノードにマウスオーバー | ツールチップ表示（画像・学名・種数） |
| 種ノードのクリック | Wikipedia を新しいタブで開く |
| 属・科など上位ノードのクリック | 展開 / 折りたたみ |
| ドラッグ | 画面移動 |
| ホイール | ズームイン・アウト |

### スマートフォン（タッチ）

| 操作 | 動作 |
|---|---|
| ノードを**長押し**（約0.5秒） | ツールチップ表示（画面下部中央に固定） |
| 種ノードを**短タップ** | Wikipedia を新しいタブで開く |
| 属・科など上位ノードを**短タップ** | 展開 / 折りたたみ |
| ツールチップの **✕** または背景タップ | ツールチップを閉じる |
| ドラッグ | 画面移動 |
| ピンチ | ズームイン・アウト |

### ヘッダーボタン

| ボタン | 機能 | 設定保存 |
|---|---|---|
| 🌙 / ☀️ | ダーク / ライトテーマ | `localStorage` |
| JA / EN | 日本語 / 英語優先 | `localStorage` |
| LR / TB | 左→右 / 上→下レイアウト | `localStorage` |
| 🖼 | 種ノード画像アイコン ON/OFF | `localStorage` |
| 科まで / 属まで / 全展開 | ツリー展開レベル | — |
| 折りたたむ | 全ノードを折りたたむ | — |
| 全体表示 | ズームリセット | — |

---

## コード構成

### taxa_tree.py（227行） ─ エントリポイント

```
taxa_tree.py
├── 設定（L54）
│   └── OUTPUT_DIR = "result"  ← 出力先の唯一の設定箇所
│
├── import
│   ├── module.taxa_fetch  （取得・モデル関連の関数・定数）
│   └── module.taxa_html   （make_html）
│
└── main()
    ├── 引数解析（argparse）
    ├── --test   → run_test()
    ├── --cached → キャッシュ検索・読み込み
    └── 新規取得フロー
        ├── pick_taxon() or --qid
        ├── fetch_root_info()
        ├── split_rank 自動調整
        ├── fetch_phase1()
        ├── fetch_phase2()  （--fast でスキップ）
        ├── キャッシュ保存（OUTPUT_DIR/taxa_cache_<QID>.json）
        └── make_html() → HTML保存（OUTPUT_DIR/taxa_<和名>_<QID>.html）
```

---

### module/taxa_fetch.py（755行） ─ データ取得・モデル構築

```
taxa_fetch.py
├── 定数・設定（〜L135）
│   ├── RANK_ORD[24]      全生物界共通の階層順（domain → form）
│   ├── RANK_MAP[25]      Wikidata P105 QID → rank 文字列
│   └── DEFAULT_SPLIT     "family"
│
├── ランクユーティリティ（〜L166）
│   ├── rank_index()      RANK_ORD 上の位置（未知ランクは末尾）
│   ├── is_leaf_rank()    亜種・変種・品種はリーフ扱い
│   ├── infer_rank()      P105 未登録ノードの rank を学名語数から推定
│   └── sanitize_filename()  ファイル名安全化
│
├── ANSI 進捗バー（〜L233）
│   ├── _bar_state{}      グローバルバー状態（always-on 設計）
│   ├── bar_update()      状態更新 + 再描画
│   ├── pprint()          ログ出力（\n）+ バーを即座に再描画
│   ├── bar_done()        Phase 2 完了時の確定改行
│   └── fmt_node()        [QID(10桁)] 📁/🐦 英語名 / 日本語名  (rank)
│
├── Session / SSL（〜L278）
│   └── init_session()    SSL自動検出（True→False）・プロキシ対応
│
├── SPARQL（〜L308）
│   └── sparql()          リトライ4回・429対応・silent モード
│
├── タクソン検索（〜L393）
│   ├── search_taxon()    wbsearchentities API（日英両方で検索）
│   └── pick_taxon()      候補表示 → ユーザー選択 → (qid, label)
│
├── ルートノード取得（〜L453）
│   └── fetch_root_info() Entity API → SPARQL フォールバック
│
├── 子ノード取得（〜L531）
│   ├── get_direct_children()  P171 + P18（画像）+ P1843（和名）
│   └── _parse_child_row()     image_url・wiki_url フィールドを生成
│                              Special:FilePath?width=120 方式
│
├── 種数推定（〜L558）
│   └── estimate_species_count()  P171+ COUNT・25秒タイムアウト
│
├── Phase 1 BFS（〜L608）
│   └── fetch_phase1(root_node, split_rank) → (tree, nodes)
│
├── Phase 2 BFS（〜L695）
│   ├── _bfs_subtree()    1ノード分のサブBFS
│   └── fetch_phase2()    進捗バー付きサブBFS
│
└── ユーティリティ（〜L755）
    ├── _sort_children()  rank 順 → 学名順でソート（再帰）
    ├── _walk()           ツリー全ノードに関数を適用
    ├── run_test()        4ステップ接続診断
    └── _elapsed()        経過時間文字列
```

**公開 API（`taxa_tree.py` から利用）：**

```python
from module.taxa_fetch import (
    DEFAULT_SPLIT, RANK_ORD,
    init_session, run_test,
    pick_taxon, fetch_root_info,
    fetch_phase1, fetch_phase2,
    estimate_species_count,
    rank_index, sanitize_filename,
    _walk, _elapsed,
)
```

---

### module/taxa_html.py（784行） ─ HTML 生成・UI

```
taxa_html.py
├── import（json, datetime のみ）
│
├── HTML = r"""..."""（〜L780）
│   ├── CSS
│   │   ├── ダーク / ライトテーマ（:root / [data-theme="light"]）
│   │   └── @media (pointer: coarse)  モバイル専用スタイル
│   │       ├── ツールチップを画面下部中央に固定
│   │       ├── 閉じるボタン（#tt-close）を表示
│   │       └── 長押しフィードバック（.pressing クラス）
│   │
│   ├── HTML 構造
│   │   ├── ヘッダー（🌙 JA/EN LR/TB 🖼 各ボタン）
│   │   ├── ツールチップ（#tt）
│   │   │   ├── 画像エリア（#tt-img / #tt-ph フォールバック）
│   │   │   ├── テキストエリア（ランク・学名・和名・種数）
│   │   │   ├── #tt-wiki（Wikipedia ボタン・種のみ表示）
│   │   │   └── #tt-close（✕ボタン・モバイルのみ表示）
│   │   └── SVG ツリー
│   │
│   └── JavaScript
│       ├── isTouchDev = matchMedia('pointer: coarse')
│       ├── テーマ / 言語 / レイアウト / 画像 ON/OFF（localStorage 保存）
│       ├── D3.js ツリー（nodeSize・linkPath・nodeTransform）
│       ├── イベントハンドラ
│       │   ├── PC:    mouseover → ツールチップ / click → 展開 or Wikipedia
│       │   └── Touch: touchstart → 長押し / touchend → 短タップ
│       ├── 長押し  startLongPress / cancelLongPress / endTouch（LP_MS=480ms）
│       ├── ツールチップ  showTT / showTTTouch / schedulHide / cancelHide
│       ├── Wikipedia  openWiki（JA/EN 連動）
│       └── 検索  doSrch（学名・和名両方）
│
└── make_html(tree: dict, root_qid: str) -> str（〜L784）
    __TITLE__ / __QID__ / __DATE__ / __DATA__ を置換して返す
```

**公開 API（`taxa_tree.py` から利用）：**

```python
from module.taxa_html import make_html
```

---

## バージョン履歴

### v5.0（現バージョン / ベースライン）

**確定日: 2026-03 / 合計1,766行（taxa_tree: 227 / taxa_fetch: 755 / taxa_html: 784）**

#### 変更内容: ロジック・UI・エントリポイントを分離

単一ファイル（1,698行）を3ファイルに分割。

| 変更 | 内容 |
|---|---|
| `taxa_tree.py` | エントリポイントのみに縮小（227行）。`OUTPUT_DIR` の唯一の設定箇所 |
| `module/taxa_fetch.py` | データ取得・BFS・進捗バー・診断を集約 |
| `module/taxa_html.py` | HTML テンプレート・`make_html()` を集約 |
| `module/__init__.py` | パッケージ宣言（1行） |

UI 変更時は `module/taxa_html.py` のみを編集すれば、`module/taxa_fetch.py` のレビューは不要。

---

### v4.0（2026-03 / 1,698行）

| 変更 | 内容 |
|---|---|
| 画像URL修正 | MD5方式を廃止し `Special:FilePath?width=120` に統一。SVG 画像が表示されなかった問題を解消 |
| Wikipedia リンク | 種クリックで Wikipedia を開く。ツールチップに「Wikipedia で開く ↗」ボタン |
| ツールチップ修正 | `pointer-events: auto`・遅延非表示（220ms）・ホバー中はキャンセル |
| モバイル対応 | `pointer: coarse` で検出。長押し→ツールチップ、短タップ→展開/Wikipedia |

---

### v3.0（2026-03 / 1,529行）

`OUTPUT_DIR = "result"` 定数新設。`result/` フォルダに出力を統一。

---

### v2.0（2026-03 / 1,515行）

Wikimedia Commons 画像表示（P18 取得・clipPath 円形アイコン・🖼 ボタン）。

---

### v1.0（2026-03 / 1,131行）

`passeriformes_tree.py` v7 を汎用化。RANK_ORD[24]・テーマ/言語/レイアウト切り替え。

---

## 既知の制約と改善候補

| # | 項目 | 詳細 |
|---|------|------|
| 1 | 画像取得漏れ | P18 未登録の種は画像なし。P373 で補完できる可能性あり |
| 2 | オフライン閲覧 | 画像表示にインターネット接続が必要 |
| 3 | `infer_rank` 1語問題 | 1語学名は rank 推定不能 → `unknown` になる場合あり |
| 4 | 取得速度 | `time.sleep(0.8)` 固定。動的スリープで改善余地あり |
| 5 | HTML サイズ | 全種（~6,000件）取得時に JSON が数十 MB になりうる |

---

## 参考文献

1. Vrandečić, D., & Krötzsch, M. (2014). Wikidata: A free collaborative knowledgebase.
   *Communications of the ACM*, 57(10), 78–85. https://doi.org/10.1145/2629489

2. Gill, F., Donsker, D., & Rasmussen, P. (Eds.) (2024). *IOC World Bird List* (v14.1).
   https://doi.org/10.14344/IOC.ML.14.1

3. Oliveros, C. H., et al. (2019). Earth history and the passerine superradiation.
   *PNAS*, 116(16), 7916–7925. https://doi.org/10.1073/pnas.1813206116

4. Bostock, M. (2023). D3.js v7. https://d3js.org/

5. Wikimedia Foundation. Wikimedia Commons. https://commons.wikimedia.org/