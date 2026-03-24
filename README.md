# taxa_tree.py

生物分類 汎用系統図ジェネレーター

Wikidata SPARQL API から任意の分類群を BFS（幅優先探索）で取得し、
単体配布可能なインタラクティブ HTML 系統図を生成します。

---

## 目次

1. [概要](#概要)
2. [インストール](#インストール)
3. [使い方](#使い方)
4. [出力ファイルの構成](#出力ファイルの構成)
5. [コード構成](#コード構成)
6. [バージョン履歴](#バージョン履歴)
7. [既知の制約と改善候補](#既知の制約と改善候補)
8. [参考文献](#参考文献)

---

## 概要

- **対応範囲**: 鳥類・哺乳類・植物・昆虫・魚類・菌類など生物分類全般
- **データソース**: [Wikidata](https://www.wikidata.org/) / [Wikimedia Commons](https://commons.wikimedia.org/)
- **出力**: `result/taxa_<和名>_<QID>.html`（ブラウザで動作・インターネット不要）
- **依存ライブラリ**: `requests`（`pip install requests`）のみ

### HTML の機能

| ボタン | 機能 |
|---|---|
| 🌙 / ☀️ | ダーク / ライトテーマ切り替え |
| JA / EN | 日本語優先 / 英語優先切り替え |
| LR / TB | 左→右 / 上→下レイアウト切り替え |
| 🖼 | 種ノードへの画像アイコン ON/OFF |
| 科まで / 属まで / 全展開 | ツリーの展開レベル変更 |
| 全体表示 | ズームをリセットしてツリー全体を表示 |

すべての設定はブラウザの `localStorage` に保存され、次回も維持されます。

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
python taxa_tree.py --qid Q5113           # スズメ科

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
:: 実行例（オプション組み合わせ）
python taxa_tree.py --qid Q25341 --fast            # 科まで高速取得
python taxa_tree.py --qid Q25341 --split genus     # 属レベルで Phase 分割
python taxa_tree.py --qid Q25341 --stop subspecies # 亜種まで取得
python taxa_tree.py --qid Q25341 --cached          # キャッシュ再利用
python taxa_tree.py --qid Q25341 --output docs/index.html  # 出力先を指定

:: 社内プロキシ環境
python taxa_tree.py --proxy http://proxy.example.com:8080 --qid Q25341
set HTTPS_PROXY=http://proxy.example.com:8080      # 環境変数でも設定可能
```

---

## 出力ファイルの構成

```
プロジェクトフォルダ/
├── taxa_tree.py            ← スクリプト本体
└── result/                 ← ★ すべての出力先（自動作成）
    ├── taxa_cache_Q25341.json       キャッシュ（JSON）
    ├── taxa_cache_Q10908.json       キャッシュ（別分類群）
    ├── taxa_スズメ目_Q25341.html    系統図 HTML
    └── taxa_哺乳綱_Q10908.html      系統図 HTML
```

### 設定箇所

**出力フォルダを変更したい場合** → スクリプト **L131** の `OUTPUT_DIR` を編集：

```python
# L131
OUTPUT_DIR = "result"          # ← ここを変更するだけで全出力先が変わる

# 変更例
OUTPUT_DIR = "docs"            # GitHub Pages の標準構成
OUTPUT_DIR = "output"          # 任意の名前
OUTPUT_DIR = "D:/bird_data"    # 絶対パスも指定可能
```

**`--output` 引数で HTML のみ個別指定した場合**、`OUTPUT_DIR` は無視され
指定パスに直接保存されます（親ディレクトリも自動作成）。

---

## コード構成（v3 / 1,520行）

```
taxa_tree.py
├── 定数・設定（55–132行）
│   ├── RANK_ORD[24]      全生物界共通の階層順（domain → form）
│   ├── RANK_MAP[25]      Wikidata P105 QID → rank 文字列
│   ├── DEFAULT_SPLIT     Phase 1/2 デフォルト分割ランク = "family"
│   └── OUTPUT_DIR        出力先フォルダ = "result"  ★ v3 追加
│
├── ランクユーティリティ（133–166行）
│   ├── rank_index()      RANK_ORD 上の位置（未知ランクは末尾）
│   ├── is_leaf_rank()    亜種・変種・品種は子を持たない
│   ├── infer_rank()      P105 未登録ノードの rank を学名語数から推定
│   └── sanitize_filename() ファイル名用に記号・空白を除去
│
├── ANSI 進捗バー（167–233行）
│   ├── _bar_state{}      グローバルバー状態（always-on 設計）
│   ├── _bar_line()       バー文字列生成（ターミナル幅自動適応）
│   ├── bar_update()      状態更新 + 再描画
│   ├── pprint()          ログ出力（\n）+ バーを即座に再描画
│   └── fmt_node()        [QID(10桁)] 📁/🐦 英語名 / 日本語名  (rank)
│
├── Session / SSL（235–278行）
│   ├── init_session()    SSL 自動検出（True→False フォールバック）
│   │                     プロキシ: 引数 or 環境変数 HTTPS_PROXY
│   └── get_session()     シングルトン取得
│
├── SPARQL（280–308行）
│   └── sparql()          単一クエリ（リトライ4回・429対応・silent モード）
│
├── タクソン検索（310–393行）
│   ├── search_taxon()    wbsearchentities API（日本語・英語両方で検索）
│   └── pick_taxon()      候補表示 → ユーザー番号選択 → (qid, label) 返却
│                         1件なら自動選択
│
├── ルートノード取得（395–453行）
│   └── fetch_root_info() Entity API（確実）→ SPARQL（フォールバック）
│                         学名・日本語ラベル・ランクを取得
│
├── 子ノード取得（455–565行）
│   ├── get_direct_children()  P171 + P18（画像）+ P1843（和名）を同時取得
│   │                          ※ P171+（推移クエリ）は使用しない
│   └── _parse_child_row()     SPARQL 1行 → ノード辞書変換 + infer_rank 適用
│                              image_url フィールドを commons_thumb_url() で生成
│
├── Wikimedia Commons URL 生成（567–603行）
│   └── commons_thumb_url()    MD5ハッシュで CDN サムネイル URL を構築
│
├── 種数推定（605–628行）
│   └── estimate_species_count()  P171+ COUNT（25秒タイムアウト）
│                                 失敗時は 0 を返してバーを件数ベースに切替
│
├── Phase 1: ルート〜split_rank BFS（630–678行）
│   └── fetch_phase1()    任意ランクのルートから split_rank まで BFS
│
├── Phase 2: split_rank ごとサブBFS（680–765行）
│   ├── _bfs_subtree()    1ノード分のサブBFS（葉ノード数を返す）
│   │                     BFS 深さを Queue に持ち回してインデント計算
│   └── fetch_phase2()    split_rank ノードを列挙してサブBFS
│                         進捗バーを unit（"種" or "件"）付きで表示
│
├── ユーティリティ（767–777行）
│   ├── _sort_children()  rank 順 → 学名順でソート（再帰）
│   └── _walk()           ツリー全ノードに関数を適用
│
├── 接続診断（779–820行）
│   └── run_test()        4ステップ診断
│                         SSL検出 / Entity API / SPARQL / taxon検索
│
├── HTML テンプレート（822–1364行）
│   ├── ノードアイコン    SVG <clipPath> + <image>（円形切り抜き・半径11px）
│   ├── img-ring          ランク色のリング枠
│   ├── ツールチップ      220px 画像 + 絵文字フォールバック（🐦/🔬/🌿）
│   ├── 🖼 ボタン         画像アイコン ON/OFF（localStorage 保存）
│   ├── 🌙/☀️ ボタン      テーマ切り替え（localStorage 保存）
│   ├── JA/EN ボタン      言語切り替え（localStorage 保存）
│   ├── LR/TB ボタン      レイアウト切り替え（localStorage 保存）
│   │                     TB+JA: writing-mode="vertical-rl"（縦書き）
│   │                     TB+EN: rotate(-90°)
│   └── ステータスバー    種数 / 属数 / 科数 / 📷画像付きノード数
│
└── メイン（1370–1520行）
    ├── 引数解析          --qid / --taxon / --split / --stop / --fast
    │                     --cached / --output / --proxy / --test
    ├── QID 解決          --taxon なら pick_taxon() → QID に変換
    ├── キャッシュ        result/taxa_cache_<QID>.json  ★ v3 変更
    │                     --cached 時は result/ 優先でキャッシュを探索
    ├── fetch_root_info → fetch_phase1 → fetch_phase2
    └── HTML 保存         result/taxa_<和名>_<QID>.html  ★ v3 変更
                          out.parent.mkdir(parents=True, exist_ok=True) で自動作成
```

---

## バージョン履歴

### v3.0（現バージョン）

**確定日: 2026-03 / 1,520行**

#### 変更内容

| 変更箇所 | 内容 |
|---|---|
| **L131** `OUTPUT_DIR = "result"` | 出力先フォルダを定数で一元管理できるよう新設 |
| **L1448** キャッシュパス | `Path(OUTPUT_DIR) / f"taxa_cache_{root_qid}.json"` |
| **L1493** キャッシュ保存前 | `cache_file.parent.mkdir(parents=True, exist_ok=True)` を追加 |
| **L1516** HTML 出力パス | `Path(OUTPUT_DIR) / f"taxa_{label}_{tree['id']}.html"` |
| **L1519** HTML 保存前 | `out.parent.mkdir(parents=True, exist_ok=True)` を追加 |
| **L1423–1431** `--cached` 検索 | `result/` 配下を優先し、なければカレントも探索 |

#### 出力先の変化

```
v2 まで: taxa_スズメ目_Q25341.html       （スクリプトと同じ場所）
v3 から: result/taxa_スズメ目_Q25341.html （result/ フォルダに集約）
```

---

### v2.0

**確定日: 2026-03 / 1,515行 / 前バージョン: v1.0**

#### 追加機能: Wikimedia Commons 画像表示

**Python 側:**
- `get_direct_children()` SPARQL に `wdt:P18`（画像）を追加
- `_parse_child_row()` で `image_url` を自動生成
- `commons_thumb_url(filename, width)` 新設（MD5ハッシュによる CDN URL 構築）

**HTML 側:**
- SVG `<clipPath>` + `<image>` による円形アイコン（半径 11px）
- ツールチップに 220px 拡大画像・`© Wikimedia Commons` 表記
- 読み込み失敗時の絵文字フォールバック（`onerror` ハンドラ）
- `🖼` ボタンで画像 ON/OFF（`localStorage` 保存）
- ステータスバーに `📷N` で画像付きノード数を表示

---

### v1.0

**確定日: 2026-03 / 1,131行 / 前身: passeriformes_tree.py v7**

`passeriformes_tree.py`（スズメ目専用）を汎用化。

| 機能 | 内容 |
|---|---|
| `--qid` / `--taxon` | QID 直接指定 or 学名・和名で検索 |
| `--split` / `--stop` | Phase 分割ランク・終端ランクを柔軟に指定 |
| RANK_ORD[24] | domain → form の24階層対応 |
| RANK_MAP[25] | 亜種・変種・品種など25種の Wikidata QID に対応 |
| テーマ切り替え | 🌙ダーク / ☀️ライト（CSS 変数） |
| 言語切り替え | JA（日本語優先） / EN（英語優先） |
| レイアウト切り替え | LR（左→右） / TB（上→下）・縦書き対応 |
| キャッシュ | QID ごとに `taxa_cache_<QID>.json` で分離 |
| 自動命名 | `taxa_<和名>_<QID>.html` |

---

## 既知の制約と改善候補

| # | 項目 | 詳細 |
|---|------|------|
| 1 | 画像取得漏れ | P18 が Wikidata 未登録の種は `image_url` なし。P373 経由で補完できる可能性あり |
| 2 | オフライン閲覧 | A方式（URL参照）のため画像表示にインターネット接続が必要 |
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