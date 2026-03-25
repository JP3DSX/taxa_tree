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
- **データソース**: [Wikidata](https://www.wikidata.org/) / [Wikimedia Commons](https://commons.wikimedia.org/) / [GBIF](https://www.gbif.org/)
- **出力**: `result/taxa_<和名>_<QID>.html`（画像表示にはインターネット接続が必要）
- **依存ライブラリ**: `requests`（`pip install requests`）のみ

---

## ファイル構成

```
プロジェクトフォルダ/
├── taxa_tree.py                    エントリポイント（引数解析・保存制御）
├── README.md                       このファイル
├── .github/workflows/pages.yml     GitHub Pages 自動デプロイ
├── module/
│   ├── __init__.py                 パッケージ宣言
│   ├── taxa_fetch.py               データ取得・モデル構築（FETCH_VERSION = 1.5）
│   └── taxa_html.py                HTML生成・UI（HTML_VERSION = 1.5）
└── result/                         出力先（実行時に自動作成）
    ├── taxa_cache_Q25341.json       キャッシュ JSON
    ├── taxa_スズメ目_Q25341.html    系統図 HTML
    └── index.html                   ランディングページ（自動更新）
```

### 各ファイルの責務

| ファイル | 行数 | 責務 |
|---|---|---|
| `taxa_tree.py` | 313行 | 引数解析・モード切替・キャッシュ管理・HTML保存 |
| `module/taxa_fetch.py` | 1,018行 | SPARQL・BFS・子補完・進捗バー・接続診断 |
| `module/taxa_html.py` | 1,151行 | HTML テンプレート・`make_html()` |

**UI 変更時は `module/taxa_html.py` のみ編集すればよく、`module/taxa_fetch.py` のレビューは不要です。**

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
python taxa_tree.py --qid Q10908          # 哺乳綱
python taxa_tree.py --taxon "カラス科"    # 名前で検索

:: 連絡先メールを User-Agent に設定（Wikimedia 推奨）
python taxa_tree.py --email you@example.com --qid Q25341
set TAXA_CONTACT_EMAIL=you@example.com   # 環境変数でも設定可
```

### オプション一覧

| 引数 | デフォルト | 説明 |
|---|---|---|
| `--qid QID` | — | Wikidata QID を直接指定 |
| `--taxon NAME` | — | 学名・和名で検索（`--render`/`--cached`/`--test` と排他） |
| `--render` | — | fetch をスキップし HTML のみ再生成。`--qid` で対象キャッシュを指定可 |
| `--cached` | — | `--render` の後方互換エイリアス |
| `--test` | — | 接続診断のみ実行 |
| `--split RANK` | `family` | Phase 1/2 の分割ランク |
| `--stop RANK` | `species` | 取得の終端ランク |
| `--fast` | false | Phase 1（`--split` まで）で終了 |
| `--output FILE` | 自動生成 | 出力 HTML ファイルパスを明示指定 |
| `--proxy URL` | 環境変数 | プロキシ URL |
| `--email EMAIL` | 環境変数 | User-Agent に埋め込む連絡先メール（`TAXA_CONTACT_EMAIL` 環境変数でも設定可） |

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

`taxa_tree.py` **L54** の `OUTPUT_DIR` を変更するだけで全出力先が変わります。

```python
OUTPUT_DIR = "result"   # ← ここを変更するだけ
OUTPUT_DIR = "docs"     # GitHub Pages 標準構成
```

### キャッシュの _meta フィールド

取得時に自動記録されます。`--render` 実行時にコンソールで確認できます。

```json
{
  "_meta": {
    "fetch_version": "1.5",
    "fetched_at":    "2026-03-25T10:00:00",
    "split_rank":    "family",
    "stop_rank":     "species"
  }
}
```

`fetch_version` が `1.4` 未満のキャッシュは `image_url` が含まれていないため再取得を推奨します。

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

---

## HTML の操作方法

### PC（マウス）

| 操作 | 動作 |
|---|---|
| ノードにマウスオーバー | ツールチップ表示（画像・学名・種数） |
| 種ノードのクリック | Wikipedia を新しいタブで開く |
| 属・科など上位ノードのクリック | 展開 / 折りたたみ |
| ドラッグ / ホイール | 移動 / ズーム |

### スマートフォン（タッチ）

| 操作 | 動作 |
|---|---|
| ノードを**長押し**（約0.5秒） | ツールチップ表示（画面下部中央固定） |
| 種ノードを**短タップ** | Wikipedia を新しいタブで開く |
| 属・科など上位ノードを**短タップ** | 展開 / 折りたたみ |
| ✕ または背景タップ | ツールチップを閉じる |

### ヘッダーボタン

| ボタン | 機能 | 設定保存 |
|---|---|---|
| 🌙 / ☀️ | ダーク / ライトテーマ | `localStorage` |
| JA / EN | 日本語 / 英語優先 | `localStorage` |
| LR / TB | 左→右 / 上→下レイアウト | `localStorage` |
| 🖼 | 種ノード画像アイコン ON/OFF | `localStorage` |
| 科まで / 属まで / 全展開 / 折りたたむ | ツリー操作 | — |
| 全体表示 | ズームリセット | — |

### 検索・凡例

検索ボックスは折りたたみ状態でも全ノードを対象にし、ヒット時は自動展開・自動フィットします。

| 凡例色 | 意味 |
|---|---|
| 通常色 | Wikidata P171 で取得 |
| 橙リング 🔤 | A補完（学名プレフィックス） |
| 青リング 🌐 | B補完（GBIF API） |
| 赤破線 ⚠ | データ不完全（全手段失敗） |

---

## コード構成

### taxa_tree.py（313行）

```
OUTPUT_DIR = "result"  ← 出力先の唯一の設定箇所（L54）

_print_meta(tree)       キャッシュ _meta を表示
_load_cache(qid)        キャッシュ読み込み（QID指定 or 最新自動選択）
_save_html(tree, out)   HTML生成・保存・index.html 自動更新

main()
  ├── バナー: fetch: vX.X  │  html: vX.X
  ├── --test   → init_session(proxy, email) → run_test()
  ├── --render → _load_cache() → _save_html()
  └── 新規取得 → init_session → fetch_root_info
              → fetch_phase1 → fetch_phase2 → キャッシュ保存 → _save_html
```

### module/taxa_fetch.py（1,018行）

```
FETCH_VERSION = "1.5"

init_session(proxy, email)
  User-Agent: "TaxaTreeBot/1.0 (you@example.com)"
  環境変数 TAXA_CONTACT_EMAIL でも設定可

resolve_image_url(filename, width)
  MD5計算のみ（HTTPリクエストなし）
  SVG/TIF/WEBP は .png サムネイルを要求

子ノード補完（属ノードの子が0件のとき自動適用）
  get_children_with_supplement(parent_node, visited, stop_rank)
  ① Wikidata P171 → ② 学名プレフィックスA → ③ GBIF API B → ④ 全失敗

  _supplement_by_prefix: STRSTARTS で二項名を Wikidata から直接取得
  _supplement_by_gbif:
    P846 → GBIF ID → /v1/species/{id}/children
    canonicalName → Wikidata QID 逆引き（バッチSPARQL）
    QID なし → GBIF:キー の仮ノード（gbif.org リンク）

fetch_phase2 進捗バー:
  バー・%: 科数ベース（確定値）
  右側:    種数（参考表示）
```

### module/taxa_html.py（1,151行）

```
HTML_VERSION = "1.5"

画像レイジーロード（3段制御）
  段1: scale < IMG_ZOOM_MIN(0.35) → ロードしない
  段2: デバウンス IMG_DEBOUNCE_MS(1500ms)
  段3: レートキュー IMG_RATE_PER_SEC(4件/秒)

Wikipedia openWiki()
  JA + 和名あり: API で日本語版の存在確認 → なければ EN
  JA + 和名なし / EN: 英語版を直接開く
  全ランクのツールチップにボタン表示

補完ノード色分け
  .strategy-prefix:     橙リング
  .strategy-gbif:       青リング
  .strategy-incomplete: 赤破線
  ツールチップに 🔤[A補完] / 🌐[B補完] / ⚠[不完全] バッジ

検索 doSrch()
  walkAll() で _children 含む全走査 → 自動展開 → fitV()
```

---

## バージョン履歴

### v5.0（現バージョン / ベースライン）

**確定日: 2026-03 / 合計 2,482行（taxa_tree: 313 / taxa_fetch: 1,018 / taxa_html: 1,151）**

#### FETCH_VERSION 変遷

| Ver | 主な変更 |
|---|---|
| 1.0 | ファイル分割時の初版 |
| 1.2 | プログレスバー科ベース化・バージョン定数追加・_meta キャッシュ記録 |
| 1.3 | SPARQL に P18 再追加（脱落バグ修正） |
| 1.4 | resolve_image_url を MD5方式に変更（API呼び出し廃止） |
| **1.5** | 子ノード補完（A+B）・`--email` 引数・User-Agent メール埋め込み |

#### HTML_VERSION 変遷

| Ver | 主な変更 |
|---|---|
| 1.0 | ファイル分割時の初版 |
| 1.2 | 画像アイコン・モバイル対応・Wikipedia リンク |
| 1.3 | ツールチップ pointer-events 修正 |
| 1.4 | crossOrigin・250px・Wikipedia 全ランク対応・JA存在チェック |
| **1.5** | 補完ノード色分け・バッジ・レイジーロード3段制御 |

---

### 旧バージョン（v1〜v4）

| バージョン | 行数 | 主な内容 |
|---|---|---|
| v4.0 | 1,698行 | 単一ファイル。画像URL・Wikipedia リンク・モバイル対応 |
| v3.0 | 1,529行 | OUTPUT_DIR = "result" 定数新設 |
| v2.0 | 1,515行 | Wikimedia Commons 画像表示（P18取得） |
| v1.0 | 1,131行 | passeriformes_tree.py v7 を汎用化。全生物界対応 |

---

## 既知の制約と改善候補

| # | 項目 | 詳細 |
|---|------|------|
| 1 | A補完の精度 | 単型属・亜属が多い場合に誤マッチが起きる可能性あり |
| 2 | GBIF 仮ノード | Wikidata に存在しない種は `GBIF:キー` 仮QID になり Wikipedia リンクが GBIF になる |
| 3 | 画像取得漏れ | P18 未登録の種は画像なし |
| 4 | オフライン閲覧 | 画像表示にインターネット接続が必要 |
| 5 | 取得速度 | `time.sleep(0.8)` 固定。動的スリープで改善余地あり |
| 6 | HTML サイズ | 全種取得時に JSON が数十 MB になりうる |

---

## 参考文献

1. Vrandečić, D., & Krötzsch, M. (2014). Wikidata. *CACM*, 57(10). https://doi.org/10.1145/2629489
2. Gill, F., et al. (2024). IOC World Bird List v14.1. https://doi.org/10.14344/IOC.ML.14.1
3. Oliveros, C. H., et al. (2019). PNAS, 116(16). https://doi.org/10.1073/pnas.1813206116
4. Bostock, M. (2023). D3.js v7. https://d3js.org/
5. Wikimedia Foundation. Wikimedia Commons. https://commons.wikimedia.org/
6. GBIF Secretariat (2024). GBIF Backbone Taxonomy. https://doi.org/10.15468/39omei