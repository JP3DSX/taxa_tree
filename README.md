# taxa_tree.py — リリースノート

---

## v2.0（現バージョン / ベースライン）

**確定日: 2026-03**
**ファイル: `taxa_tree.py`（1,515行）**
**前バージョン: v1.0**

### 追加機能

#### Wikimedia Commons 画像表示（A方式・URL参照）

**Python 側（データ取得）:**

| 変更箇所 | 内容 |
|---|---|
| `get_direct_children()` SPARQL | `OPTIONAL { ?child wdt:P18 ?img }` を追加。P18（画像）を同時取得 |
| `_parse_child_row()` | `img` フィールドから `Special:FilePath/` を解析し `image_url` を生成 |
| `commons_thumb_url(filename, width)` | **新規追加。** ファイル名から Wikimedia Commons サムネイル URL を構築。MD5ハッシュによる CDN パス規則に準拠 |

```
P18 の値: "http://commons.wikimedia.org/wiki/Special:FilePath/Corvus_corax.jpg"
          ↓ commons_thumb_url()
image_url: "https://upload.wikimedia.org/wikipedia/commons/thumb/b/be/Corvus_corax.jpg/120px-Corvus_corax.jpg"
```

画像のない種ノードはこれまで通りの通常ノードとして表示される。

**HTML 側（表示）:**

| UI 要素 | 内容 |
|---|---|
| **ノードアイコン** | `<clipPath>` + `<image>` で円形切り抜き（半径 11px）。カラーリング付き |
| **マウスオーバー** | 220px 拡大画像をツールチップ上部に表示。`© Wikimedia Commons` 表記付き |
| **読み込み失敗時** | `onerror` で絵文字プレースホルダーに自動フォールバック（🐦 / 🔬 / 🌿） |
| **🖼 ボタン** | アイコン表示の ON/OFF 切り替え。OFF 時は通常ノードに戻る（アニメーション付き） |
| **ステータスバー** | 画像付きノード数を `📷N` で表示 |

**設計上の制約（A方式の特性）:**
- 閲覧時にインターネット接続が必要（Wikimedia Commons へのリクエスト）
- `file://` で開いた場合も CORS 対応済みのため画像表示は可能
- HTML ファイル自体のサイズ増加なし（URL 文字列のみ格納）

#### localStorage への画像設定保存

ブラウザを閉じて再度開いても画像表示の ON/OFF 設定（`taxa_icons`）が維持される。

---

## v1.0（前バージョン）

**確定日: 2026-03**
**ファイル: `taxa_tree.py`（1,131行）**
**前身: `passeriformes_tree.py` v7（スズメ目専用）**

`passeriformes_tree.py`（スズメ目専用）を汎用化。
Wikidata SPARQL API から**任意の分類群**を BFS で取得し、
単体配布可能なインタラクティブ HTML 系統図を生成する。

| 機能 | 詳細 |
|---|---|
| `--qid` / `--taxon` | QID 直接指定 or 学名・和名で検索 |
| `--split` / `--stop` | Phase 分割ランク・終端ランクを指定 |
| RANK_ORD[24] | domain → form の24階層対応 |
| テーマ切り替え | 🌙ダーク / ☀️ライト |
| 言語切り替え | JA / EN |
| レイアウト切り替え | LR（左→右）/ TB（上→下・縦書き / rotate） |
| キャッシュ | `taxa_cache_<QID>.json` で QID ごとに分離 |

---

## 実行方法（v2.0）

```bat
pip install requests

python taxa_tree.py --test                         # 接続診断
python taxa_tree.py --qid Q25341                   # スズメ目
python taxa_tree.py --qid Q10908                   # 哺乳綱
python taxa_tree.py --taxon "カラス科"              # 名前で検索
python taxa_tree.py --qid Q25341 --fast            # 科まで高速取得
python taxa_tree.py --qid Q25341 --cached          # キャッシュ再利用
python taxa_tree.py --proxy http://proxy.com:8080 --qid Q25341
```

---

## コード構成（v2.0 / 1,515行）

```
taxa_tree.py
├── 定数・ランクマップ（55–129行）  RANK_ORD[24] / RANK_MAP[25]
├── ランクユーティリティ（130–163行）  infer_rank / is_leaf_rank
├── ANSI 進捗バー（164–230行）  always-on 設計 / fmt_node
├── Session / SSL（232–275行）  SSL自動検出・プロキシ対応
├── SPARQL（276–305行）  リトライ4回・429対応
├── タクソン検索（306–390行）  wbsearchentities / pick_taxon
├── ルートノード取得（391–450行）  fetch_root_info
├── 子ノード取得（451–560行）  ← v2: P18追加・image_url生成
├── Wikimedia URL生成（561–600行）  ← v2: commons_thumb_url 新規
├── 種数推定（601–624行）  P171+ COUNT・25秒タイムアウト
├── Phase 1 BFS（625–674行）  ルート〜split_rank
├── Phase 2 BFS（675–759行）  split_rank 以下・進捗バー付き
├── ユーティリティ（760–770行）  _sort_children / _walk
├── 接続診断（771–815行）  run_test
├── HTML テンプレート（816–1359行）  ← v2: 画像UI全面更新
│   ├── ノードアイコン  clipPath + image（円形切り抜き・半径11px）
│   ├── img-ring       ランク色のリング
│   ├── ツールチップ   220px画像 + フォールバック絵文字
│   ├── 🖼ボタン       画像ON/OFF（localStorage保存）
│   ├── テーマ/言語/レイアウト切り替え（全localStorage保存）
│   └── ステータスバー  📷N で画像付きノード数表示
└── メイン（1368–1515行）  引数解析 → 取得 → HTML生成
```

---

## 既知の制約・今後の改善候補

| # | 項目 | 詳細 |
|---|------|------|
| 1 | 画像取得漏れ | P18 未登録の種は画像なし。P373 経由で補完できる可能性あり |
| 2 | オフライン閲覧 | A方式のため画像表示にインターネット接続が必要 |
| 3 | `infer_rank` 1語問題 | 1語学名は rank 推定不能 → `unknown` |
| 4 | 取得速度 | `time.sleep(0.8)` 固定。動的スリープで改善余地あり |
| 5 | HTML サイズ | 全種取得時に JSON が数十 MB になりうる |

---

## 参考文献

1. Vrandečić, D., & Krötzsch, M. (2014). Wikidata. *CACM*, 57(10). https://doi.org/10.1145/2629489
2. Gill, F., et al. (2024). IOC World Bird List v14.1. https://doi.org/10.14344/IOC.ML.14.1
3. Oliveros, C. H., et al. (2019). PNAS, 116(16). https://doi.org/10.1073/pnas.1813206116
4. Bostock, M. (2023). D3.js v7. https://d3js.org/
5. Wikimedia Foundation. Wikimedia Commons. https://commons.wikimedia.org/