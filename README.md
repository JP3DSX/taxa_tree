# taxa_tree.py

生物分類 汎用系統図ジェネレーター **v6**

Wikidata SPARQL API から任意の分類群を BFS（幅優先探索）で取得し、
インタラクティブ HTML 系統図を生成します。

---

## 目次

1. [概要](#概要)
2. [ファイル構成](#ファイル構成)
3. [インストール](#インストール)
4. [使い方](#使い方)
5. [出力モード](#出力モード)
6. [出力ファイルの構成](#出力ファイルの構成)
7. [HTML の操作方法](#html-の操作方法)
8. [コード構成](#コード構成)
9. [バージョン履歴](#バージョン履歴)
10. [既知の制約と改善候補](#既知の制約と改善候補)
11. [参考文献](#参考文献)

---

## 概要

- **対応範囲**: 鳥類・哺乳類・植物・昆虫・魚類・菌類など生物分類全般
- **データソース**: [Wikidata](https://www.wikidata.org/) / [Wikimedia Commons](https://commons.wikimedia.org/)
- **出力**: `result/` フォルダに HTML + キャッシュ JSON + SPA ランディングページ
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
│   ├── taxa_fetch.py               データ取得・モデル構築（FETCH_VERSION = 1.7）
│   └── taxa_html.py                HTML生成・UI（HTML_VERSION = 1.5）
└── result/                         出力先（実行時に自動作成）
    ├── taxa_cache_Q25341.json       キャッシュ JSON
    ├── taxa_スズメ目_Q25341.html    系統図 HTML（standalone モードのみ）
    └── index.html                   SPA（ランディング + ビューワー統合）
```

### 各ファイルの責務

| ファイル | 行数 | 責務 |
|---|---|---|
| `taxa_tree.py` | 724行 | 引数解析・モード切替・キャッシュ管理・HTML保存・一括処理 |
| `module/taxa_fetch.py` | 1,078行 | SPARQL・BFS・子補完・進捗バー・接続診断 |
| `module/taxa_html.py` | 1,360行 | HTML テンプレート・SPA生成・`make_html()` 等 |

**UI 変更時は `module/taxa_html.py` のみを編集すればよく、`module/taxa_fetch.py` のレビューは不要です。**

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

:: 通常取得
python taxa_tree.py --qid Q25341          # スズメ目
python taxa_tree.py --qid Q10908          # 哺乳綱
python taxa_tree.py --taxon "カラス科"    # 名前で検索

:: web モード（GitHub Pages 用・JSON 分離）
python taxa_tree.py --qid Q25341 --web

:: HTML のみ再生成（fetch をスキップ）
python taxa_tree.py --qid Q25341 --render
python taxa_tree.py --qid Q25341 --render --web

:: 一括再生成
python taxa_tree.py --render-all           # standalone: 全キャッシュを HTML に再変換
python taxa_tree.py --render-all --web     # web: 余分な HTML を削除 + index.html 再生成

:: 連絡先メールを User-Agent に設定（Wikimedia 推奨）
python taxa_tree.py --email you@example.com --qid Q25341
set TAXA_CONTACT_EMAIL=you@example.com
```

### オプション一覧

| 引数 | デフォルト | 説明 |
|---|---|---|
| `--qid QID` | — | Wikidata QID を直接指定 |
| `--taxon NAME` | — | 学名・和名で検索（排他グループ） |
| `--render` | — | fetch をスキップし HTML のみ再生成。`--qid` で対象キャッシュを指定可（排他グループ） |
| `--render-all` | — | 一括再生成（排他グループ。`--qid`/`--taxon` と同時使用不可） |
| `--cached` | — | `--render` の後方互換エイリアス（排他グループ） |
| `--test` | — | 接続診断のみ実行（排他グループ） |
| `--web` | false | web モード: JSON を外部ファイルに分離（GitHub Pages 用） |
| `--split RANK` | `family` | Phase 1/2 の分割ランク |
| `--stop RANK` | `species` | 取得の終端ランク |
| `--fast` | false | Phase 1（`--split` まで）で終了 |
| `--output FILE` | 自動生成 | 出力 HTML ファイルパスを明示指定 |
| `--proxy URL` | 環境変数 | プロキシ URL |
| `--email EMAIL` | 環境変数 | User-Agent に埋め込む連絡先メール（`TAXA_CONTACT_EMAIL` 環境変数でも可） |

### 動作モード一覧

| モード | コマンド例 | fetch | HTML生成 |
|---|---|---|---|
| 新規取得 | `--qid Q25341` | ✅ | ✅ 単体 |
| HTML 再生成 | `--qid Q25341 --render` | スキップ | ✅ 単体 |
| **一括再生成（standalone）** | `--render-all` | スキップ | ✅ **全件** |
| **一括再生成（web）** | `--render-all --web` | スキップ | index.html のみ再生成 |
| 高速取得 | `--qid Q25341 --fast` | ✅ Phase1のみ | ✅ 単体 |
| 接続診断 | `--test` | スキップ | スキップ |

---

## 出力モード

HTML の生成方式を2つから選択できます。

### standalone モード（デフォルト）

JSON データを HTML に直接埋め込みます。

```bat
python taxa_tree.py --qid Q25341
```

```
result/
  taxa_スズメ目_Q25341.html   ← JSON 埋め込み（数MB）
  index.html                   ← SPA（カード一覧 + ビューワー）
```

| 項目 | 内容 |
|---|---|
| ローカル動作 | ✅ `file://` で直接開ける・オフライン可 |
| GitHub Pages | ✅ |
| ファイルサイズ | 大（JSON + HTML 混在） |
| UI 更新 | `--render` または `--render-all` が必要 |

### web モード（GitHub Pages 推奨）

JSON を外部ファイルとして分離し、HTML は軽量な描画エンジンのみにします。

```bat
python taxa_tree.py --qid Q25341 --web
```

```
result/
  taxa_cache_Q25341.json       ← JSON（既存・追加取得不要）
  index.html                   ← SPA（カード一覧 + ビューワー）
  ※ taxa_*.html は生成されない（または自動削除される）
```

| 項目 | 内容 |
|---|---|
| ローカル動作 | ❌ CORS のため `file://` では動作しない |
| GitHub Pages | ✅ |
| ファイルサイズ | 小（HTML は SPA の index.html のみ） |
| UI 更新 | `--render-all --web` のみで即反映（JSON 再取得不要） |

web モードでは、ブラウザが JSON を読み込む間**プログレスバー付きローディング画面**が表示されます。

### SPA ランディングページ（index.html）

どちらのモードでも `index.html` は自動生成・更新されます。

```
URL                  表示
index.html        →  カード一覧（全キャッシュのサムネイル）
index.html#Q25341 →  スズメ目の系統図ビューワー
index.html#Q10908 →  哺乳綱の系統図ビューワー
```

カードをクリックするとページ遷移なしで系統図ビューワーに切り替わります。ブラウザの「戻る」ボタンで一覧に戻れます。

---

## 出力ファイルの構成

### 出力フォルダの変更

`taxa_tree.py` **L62** の `OUTPUT_DIR` を変更するだけで全出力先が変わります。

```python
OUTPUT_DIR = "result"   # ← ここを変更するだけ
OUTPUT_DIR = "docs"     # GitHub Pages 標準構成
```

### キャッシュの _meta フィールド

取得時に自動記録されます。`--render` 実行時にコンソールで確認できます。

```json
{
  "_meta": {
    "fetch_version": "1.7",
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

Settings → Pages → Source を **「GitHub Actions」** に設定。

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
| ドラッグ / ピンチ | 移動 / ズーム |

### ヘッダーボタン

| ボタン | 機能 | 設定保存 |
|---|---|---|
| 🌙 / ☀️ | ダーク / ライトテーマ | `localStorage` |
| JA / EN | 日本語 / 英語優先 | `localStorage` |
| LR / TB | 左→右 / 上→下レイアウト | `localStorage` |
| 🖼 | 種ノード画像アイコン ON/OFF | `localStorage` |
| 科まで / 属まで / 全展開 / 折りたたむ | ツリー操作 | — |
| 全体表示 | ズームリセット | — |

### 検索

検索ボックスに入力後、**🔍 ボタン**または **Enter キー**で実行します（リアルタイム検索は無効・大量データでのクラッシュ防止）。✕ ボタンでクリア。折りたたまれた状態でも全ノードを対象に検索し、ヒット時は自動展開・自動フィットします。

### Wikipedia リンク

すべてのランク（属・科・目など）のツールチップに「Wikipedia で開く ↗」ボタンが表示されます。JA モードで和名がある場合、日本語版の存在を確認してから開きます（存在しない場合は英語版にフォールバック）。

### 凡例

| 凡例色 | 意味 |
|---|---|
| 通常色 | Wikidata P171 で取得 |
| 橙リング 🔤 | P171+ 推移的補完（亜属経由を捕捉） |
| 赤破線 ⚠ | データ不完全（全手段失敗） |

---

## コード構成

### taxa_tree.py（724行）

```
OUTPUT_DIR = "result"  ← 出力先の唯一の設定箇所（L62）

_print_meta(tree)               キャッシュ _meta を表示
_load_cache(qid)                キャッシュ読み込み（QID指定 or 最新自動選択）
_cleanup_html(output_dir)       taxa_*.html を全削除（web モード用）
_save_html(tree, out, web)      HTML生成・保存・index.html 自動更新
                                web=True のとき _cleanup_html() も実行
_render_all(web_mode)           一括再生成
  web=False: 全キャッシュ → make_html() → taxa_*.html + index.html
  web=True:  _cleanup_html() → make_index_html() → index.html のみ

main()
  排他グループ: --taxon / --render / --render-all / --cached / --test
  ├── --test       → init_session → run_test()
  ├── --render-all → _render_all(web=args.web)
  ├── --render     → _load_cache() → _save_html(web=args.web)
  └── 新規取得     → init_session → fetch_root_info
                  → fetch_phase1 → fetch_phase2 → キャッシュ保存
                  → _save_html(web=args.web)
```

### module/taxa_fetch.py（1,078行）

```
FETCH_VERSION = "1.7"

init_session(proxy, email)
  User-Agent: "TaxaTreeBot/1.0 (you@example.com)"
  環境変数 TAXA_CONTACT_EMAIL でも設定可

resolve_image_url(filename, width)
  MD5計算のみ（HTTP リクエストなし）・SVG/TIF → .png

子ノード補完（属ノードの子が0件のとき自動適用）
  get_children_with_supplement(parent_node, visited, stop_rank)
  ① Wikidata P171 直接
  ② P171+ 推移的閉包（亜属経由の種を一括捕捉）
  ③ 全手段失敗 → STRATEGY_INCOMPLETE

  重複防止:
    visited |= nodes_dict.keys()  ← 科をまたいだ重複を排除
    node["id"] in nodes_dict チェック（二重ガード）

fetch_phase2 進捗バー:
  バー・%: 科数ベース（確定値）
  右側:    種数（参考表示）
```

### module/taxa_html.py（1,360行）

```
HTML_VERSION = "1.5"

make_html(tree, root_qid)
  standalone モード: const DATA={...JSON...}; を HTML に埋め込む

make_web_viewer(tree, root_qid, json_filename)
  web モード: fetch(json_filename) → init() を HTML に埋め込む

make_index_html(output_dir)
  SPA 版 index.html を生成する。

  URL ルーティング:
    index.html        → ランディング（カード一覧）
    index.html#QXXX   → 系統図ビューワー（fetch で JSON を読み込み描画）

  動作:
    - カードデータはビルド時に Python が JSON を走査して TAXA_LIST に埋め込む
    - ハッシュ変化イベント（hashchange）でビューを切り替え
    - ビューワー部分は taxa_html.py の HTML テンプレートを再利用

画像レイジーロード（3段制御）
  段1: scale < IMG_ZOOM_MIN(0.35) → ロードしない
  段2: デバウンス IMG_DEBOUNCE_MS(1500ms)
  段3: レートキュー IMG_RATE_PER_SEC(4件/秒)
  Wikimedia 標準サイズ: 120px（ノード）/ 250px（ツールチップ）

検索 doSrch()
  🔍 ボタン / Enter キーで実行（リアルタイム検索は無効）
  walkAll() で _children 含む全走査 → 自動展開 → fitV()
```

---

## バージョン履歴

### v6.0（現バージョン / ベースライン）

**確定日: 2026-03 / 合計 3,162行（taxa_tree: 724 / taxa_fetch: 1,078 / taxa_html: 1,360）**

#### taxa_tree.py の主な変更

| 変更 | 内容 |
|---|---|
| `--render-all` フラグ | 一括再生成モード。`--qid`/`--taxon` と排他。standalone は全キャッシュを HTML 再変換、web は余分な HTML を削除して index.html のみ再生成 |
| `_cleanup_html()` | web モード時に `taxa_*.html` を削除するヘルパー。`_save_html()` と `_render_all()` から呼ばれる |
| `--web` 自動クリーンアップ | `_save_html(web=True)` 実行時に余分な HTML を自動削除 |
| SPA 対応（`_render_all` web） | `taxa_*.html` なしで `index.html` だけで系統図が閲覧できる構成を一括適用 |

#### module/taxa_html.py の主な変更

| 変更 | 内容 |
|---|---|
| `make_index_html()` → SPA | `index.html` をランディング + ビューワーの統合 SPA に刷新。`index.html#QID` で直接系統図を開ける |
| ルーティング | `location.hash` + `hashchange` イベントでページ遷移なしにビューを切り替え |
| ビューワー再利用 | `HTML` テンプレートの CSS・JS を SPA 内に埋め込み、コードの重複を排除 |

---

#### FETCH_VERSION 変遷

| Ver | 主な変更 |
|---|---|
| 1.0 | ファイル分割時の初版 |
| 1.2 | プログレスバー科ベース化・バージョン定数・_meta キャッシュ記録 |
| 1.3 | SPARQL に P18 再追加（脱落バグ修正） |
| 1.4 | resolve_image_url を MD5方式に変更（API 呼び出し廃止） |
| 1.5 | 子ノード補完（A+B）・`--email`・User-Agent メール埋め込み |
| 1.6 | P171+ 推移的閉包による補完（GBIF・プレフィックス方式を廃止） |
| **1.7** | 科をまたいだ重複ノードを排除（visited ガード強化・ランクフィルタ修正） |

#### HTML_VERSION 変遷

| Ver | 主な変更 |
|---|---|
| 1.0 | ファイル分割時の初版 |
| 1.2 | 画像アイコン・モバイル対応・Wikipedia リンク |
| 1.3 | ツールチップ pointer-events 修正 |
| 1.4 | crossOrigin・250px・Wikipedia 全ランク・JA存在チェック |
| **1.5** | レイジーロード3段制御・補完ノード色分け・検索ボタン式・standalone/web モード・SPA ランディング |

---

### 旧バージョン（v1〜v5）

| バージョン | 行数 | 主な内容 |
|---|---|---|
| v5.0 | 2,639行 | 3ファイル構成確立。FETCH 1.5〜1.7 / HTML 1.5 |
| v4.0 | 1,698行 | 単一ファイル。画像URL・Wikipedia リンク・モバイル対応 |
| v3.0 | 1,529行 | OUTPUT_DIR = "result" 定数新設 |
| v2.0 | 1,515行 | Wikimedia Commons 画像表示（P18取得） |
| v1.0 | 1,131行 | passeriformes_tree.py v7 を汎用化。全生物界対応 |

---

## 既知の制約と改善候補

| # | 項目 | 詳細 |
|---|------|------|
| 1 | P171+ 平坦化 | P171+ 取得時、亜属が子なしノードになる場合がある（取りこぼしはなし） |
| 2 | 画像取得漏れ | P18 未登録の種は画像なし |
| 3 | オフライン閲覧 | 画像表示にインターネット接続が必要 |
| 4 | web モードのローカル動作 | CORS のため `file://` では動作しない |
| 5 | 取得速度 | `time.sleep(0.8)` 固定。動的スリープで改善余地あり |
| 6 | HTML サイズ（standalone） | 全種取得時に数十 MB になりうる |

---

## 参考文献

1. Vrandečić, D., & Krötzsch, M. (2014). Wikidata. *CACM*, 57(10). https://doi.org/10.1145/2629489
2. Gill, F., et al. (2024). IOC World Bird List v14.1. https://doi.org/10.14344/IOC.ML.14.1
3. Oliveros, C. H., et al. (2019). PNAS, 116(16). https://doi.org/10.1073/pnas.1813206116
4. Bostock, M. (2023). D3.js v7. https://d3js.org/
5. Wikimedia Foundation. Wikimedia Commons. https://commons.wikimedia.org/
6. GBIF Secretariat (2024). GBIF Backbone Taxonomy. https://doi.org/10.15468/39omei