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
    ├── taxa_スズメ目_Q25341.html    系統図 HTML
    ├── taxa_哺乳綱_Q10908.html      系統図 HTML（複数生成可）
    └── index.html                   ランディングページ（系統図一覧・自動更新）
```

### 各ファイルの責務

| ファイル | 行数 | 責務 |
|---|---|---|
| `taxa_tree.py` | 281行 | 引数解析・モード切替・キャッシュ管理・HTML保存 |
| `module/taxa_fetch.py` | 797行 | SPARQL・BFS・画像URL解決・進捗バー・接続診断 |
| `module/taxa_html.py` | 1,020行 | HTML テンプレート・`make_html()` |
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
```

### オプション一覧

| 引数 | デフォルト | 説明 |
|---|---|---|
| `--qid QID` | — | Wikidata QID を直接指定 |
| `--taxon NAME` | — | 学名・和名で検索（`--render` / `--cached` / `--test` と排他） |
| `--render` | — | **fetch をスキップし HTML のみ再生成**。`--qid` で対象キャッシュを指定可（省略時は最新を自動選択） |
| `--cached` | — | `--render` の後方互換エイリアス |
| `--test` | — | 接続診断のみ実行 |
| `--split RANK` | `family` | Phase 1/2 の分割ランク |
| `--stop RANK` | `species` | 取得の終端ランク |
| `--fast` | false | Phase 1（`--split` まで）で終了 |
| `--output FILE` | 自動生成 | 出力 HTML ファイルパスを明示指定 |
| `--proxy URL` | 環境変数 | プロキシ URL |

### 実行例

```bat
:: 通常取得
python taxa_tree.py --qid Q25341 --fast                    # 科まで高速取得
python taxa_tree.py --qid Q25341 --split genus             # 属レベルで Phase 分割
python taxa_tree.py --qid Q25341 --output docs/index.html  # 出力先を指定

:: HTML のみ再生成（UI 変更後に fetch をスキップして再利用）
python taxa_tree.py --qid Q25341 --render    # 指定 QID のキャッシュを使用
python taxa_tree.py --render                 # 最新キャッシュを自動選択

:: 社内プロキシ環境
python taxa_tree.py --proxy http://proxy.example.com:8080 --qid Q25341
set HTTPS_PROXY=http://proxy.example.com:8080
```

### 動作モード一覧

| モード | コマンド例 | fetch | HTML生成 |
|---|---|---|---|
| 新規取得 | `--qid Q25341` | ✅ | ✅ |
| HTML 再生成（QID指定） | `--qid Q25341 --render` | スキップ | ✅ |
| HTML 再生成（自動選択） | `--render` | スキップ | ✅ |
| 高速取得（科まで） | `--qid Q25341 --fast` | ✅（Phase1のみ） | ✅ |
| 接続診断 | `--test` | スキップ | スキップ |

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

### 検索ボックス

折りたたまれた状態でも全ノードを対象に検索します。ヒットしたノードは自動展開・ハイライト表示され、画面が自動フィットします。空文字で検索するとリセットされます。

---

## コード構成

### taxa_tree.py（281行） ─ エントリポイント

```
taxa_tree.py
├── 設定（L54）
│   └── OUTPUT_DIR = "result"  ← 出力先の唯一の設定箇所
│
├── import
│   ├── module.taxa_fetch  （取得・モデル関連の関数・定数）
│   └── module.taxa_html   （make_html）
│
├── _load_cache(qid) → (tree, path)  ★ v5追加
│   ├── qid 指定時: OUTPUT_DIR/taxa_cache_<qid>.json を優先検索
│   └── qid 省略時: 更新日時が最新のキャッシュを自動選択
│
├── _save_html(tree, output_arg)  ★ v5追加
│   ├── make_html() → HTML生成 → ファイル書き出し（ディレクトリ自動作成）
│   └── make_index_html() → result/index.html を自動更新（系統図一覧ページ）
│
└── main()
    ├── --test     → run_test() して終了
    ├── --render   → _load_cache() → _save_html() して終了  ★ v5追加
    ├── --cached   → --render の後方互換エイリアス
    └── 新規取得フロー
        ├── --taxon → pick_taxon() / --qid → QID 直接使用
        ├── fetch_root_info()
        ├── split_rank 自動調整
        ├── fetch_phase1()
        ├── fetch_phase2()  （--fast でスキップ）
        ├── キャッシュ保存（OUTPUT_DIR/taxa_cache_<QID>.json）
        └── _save_html()
```

---

### module/taxa_fetch.py（797行） ─ データ取得・モデル構築

```
taxa_fetch.py
├── 定数・設定（〜L135）
│   ├── RANK_ORD[24] / RANK_MAP[25] / DEFAULT_SPLIT
│
├── ランクユーティリティ（〜L166）
│   ├── rank_index / is_leaf_rank / infer_rank / sanitize_filename
│
├── ANSI 進捗バー（〜L233）
│   └── _bar_state / bar_update / pprint / bar_done / fmt_node
│
├── Session / SSL（〜L278）
│   └── init_session（SSL自動検出・プロキシ対応）
│
├── SPARQL（〜L308）
│   └── sparql（リトライ4回・429対応）
│
├── タクソン検索（〜L393）
│   └── search_taxon / pick_taxon
│
├── ルートノード取得（〜L453）
│   └── fetch_root_info（Entity API → SPARQL フォールバック）
│
├── 子ノード取得（〜L531）
│   ├── get_direct_children（P171 + P18 + P1843）
│   ├── _parse_child_row（image_url・wiki_url 生成）
│   └── resolve_image_url()  ★ v5追加
│       Wikimedia Thumbnail API で直接 CDN URL を取得
│       失敗時は Special:FilePath にフォールバック
│
├── 種数推定（〜L558）
├── Phase 1 BFS（〜L608）
├── Phase 2 BFS（〜L695）
└── ユーティリティ・診断（〜L797）
    └── _sort_children / _walk / _elapsed / run_test
```

---

### module/taxa_html.py（1,020行） ─ HTML 生成・UI

```
taxa_html.py
├── import（json, datetime のみ）
│
├── HTML = r"""..."""（〜L1016）
│   ├── CSS
│   │   ├── ダーク / ライトテーマ
│   │   └── @media (pointer: coarse) モバイル専用
│   ├── HTML 構造
│   │   ├── ヘッダー / ツールチップ / SVG ツリー
│   └── JavaScript
│       ├── isTouchDev = matchMedia('pointer: coarse')
│       ├── テーマ / 言語 / レイアウト / 画像 ON/OFF（localStorage）
│       ├── D3.js ツリー
│       ├── PC: mouseover → ツールチップ / click → 展開 or Wikipedia
│       ├── Touch: 長押し → ツールチップ / 短タップ → 展開 or Wikipedia
│       ├── Wikipedia: openWiki（JA/EN 連動）
│       └── 検索: doSrch  ★ v5修正
│           ├── walkAll() で _children を含む全ノード走査
│           ├── ヒット時に祖先パスを自動展開
│           └── fitV() で自動フィット（260ms後）
│
└── make_html(tree, root_qid) → str
└── make_index_html(output_dir) → str
    result/ 内の taxa_*.html を走査してランディングページ HTML を生成
    対応する taxa_cache_<QID>.json が存在すれば種数・科数・ノード数も表示
```

---

## バージョン履歴

### v5.0（現バージョン / ベースライン）

**確定日: 2026-03 / 合計 2,098行（taxa_tree: 281 / taxa_fetch: 797 / taxa_html: 1,020）**

| 変更 | 内容 |
|---|---|
| **ファイル分割** | 単一ファイル（1,698行）を3ファイルに分割。UI変更時は `taxa_html.py` のみ編集でよい |
| **`--render` フラグ** | fetch をスキップして HTML のみ再生成するモードを追加。`--qid` で対象キャッシュを指定可 |
| **`_load_cache()` / `_save_html()`** | HTML再生成ロジックを独立関数として切り出し。`main()` の可読性を改善 |
| **`make_index_html()`** | `result/` 内の系統図一覧をランディングページ（`index.html`）として自動生成。HTML 生成のたびに自動更新 |
| **検索の全ノード走査** | `walkAll()` を追加。折りたたみ状態でも全ノードを検索可能に。ヒット時に自動展開・自動フィット |
| **画像 URL の API 対応** | `resolve_image_url()` を新設。Wikimedia Thumbnail API で CDN URL を直接取得し、SVG 等の表示問題を解消 |

> **画像修正の注意:** `--render` での再生成では旧 URL が使われます。`--qid` での再取得が必要です。

---

### v4.0（2026-03 / 1,698行）

画像URL修正（MD5→Special:FilePath）・Wikipedia リンク・ツールチップ操作性改善・モバイル対応（長押し/短タップ分離）。

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