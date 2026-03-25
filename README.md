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
6. [HTML の操作方法](#html-の操作方法)
7. [調整項目リファレンス](#調整項目リファレンス)
8. [コード構成](#コード構成)
9. [バージョン履歴](#バージョン履歴)
10. [既知の制約](#既知の制約)
11. [参考文献](#参考文献)

---

## 概要

- **対応範囲**: 鳥類・哺乳類・植物・昆虫・魚類・菌類など生物分類全般
- **データソース**: [Wikidata](https://www.wikidata.org/) / [Wikimedia Commons](https://commons.wikimedia.org/)
- **出力**: `result/` フォルダに SPA (`index.html`) + キャッシュ JSON
- **依存ライブラリ**: `requests`（`pip install requests`）のみ

---

## ファイル構成

```
プロジェクトフォルダ/
├── taxa_tree.py                    エントリポイント
├── README.md                       このファイル
├── .github/workflows/pages.yml     GitHub Pages 自動デプロイ
├── module/
│   ├── __init__.py
│   ├── taxa_fetch.py               データ取得（FETCH_VERSION = 1.7）
│   └── taxa_html.py                HTML生成・UI（HTML_VERSION = 1.5）
└── result/
    ├── taxa_cache_Q25341.json       キャッシュ JSON
    └── index.html                   SPA（ランディング + ビューワー統合）
```

| ファイル | 行数 | 責務 |
|---|---|---|
| `taxa_tree.py` | 724行 | 引数解析・モード切替・キャッシュ管理 |
| `module/taxa_fetch.py` | 1,078行 | SPARQL・BFS・子補完・接続診断 |
| `module/taxa_html.py` | 1,195行 | HTML テンプレート・SPA生成 |

---

## インストール

```bat
pip install requests
```

---

## 使い方

```bat
:: 接続診断（初回・プロキシ環境では必須）
python taxa_tree.py --test

:: 通常取得
python taxa_tree.py --qid Q25341          # スズメ目
python taxa_tree.py --qid Q10908          # 哺乳綱
python taxa_tree.py --taxon "カラス科"    # 名前で検索

:: web モード（GitHub Pages 用・JSON 分離）
python taxa_tree.py --qid Q25341 --web

:: HTML のみ再生成
python taxa_tree.py --qid Q25341 --render
python taxa_tree.py --render              # 最新キャッシュを自動選択

:: 一括再生成
python taxa_tree.py --render-all          # standalone: 全キャッシュを HTML 変換
python taxa_tree.py --render-all --web    # web: 余分 HTML 削除 + index.html 再生成

:: Wikimedia 推奨: 連絡先メールを User-Agent に設定
python taxa_tree.py --email you@example.com --qid Q25341
set TAXA_CONTACT_EMAIL=you@example.com
```

### オプション一覧

| 引数 | デフォルト | 説明 |
|---|---|---|
| `--qid QID` | — | Wikidata QID（例: Q25341） |
| `--taxon NAME` | — | 学名・和名で検索（排他グループ） |
| `--render` | — | HTML のみ再生成。`--qid` で対象指定可（排他グループ） |
| `--render-all` | — | 一括再生成（`--qid`/`--taxon` と同時使用不可） |
| `--cached` | — | `--render` の後方互換エイリアス |
| `--test` | — | 接続診断のみ実行 |
| `--web` | false | web モード: JSON を外部ファイルに分離（GitHub Pages 用） |
| `--split RANK` | `family` | Phase 1/2 の分割ランク |
| `--stop RANK` | `species` | 取得の終端ランク |
| `--fast` | false | Phase 1（`--split` まで）で終了 |
| `--output FILE` | 自動生成 | 出力 HTML ファイルパス |
| `--proxy URL` | 環境変数 | プロキシ URL |
| `--email EMAIL` | 環境変数 | User-Agent に埋め込む連絡先（`TAXA_CONTACT_EMAIL` でも可） |

---

## 出力モード

### standalone モード（デフォルト）

JSON を HTML に埋め込む。`file://` でローカル動作可・オフライン閲覧可。

```bat
python taxa_tree.py --qid Q25341
```

### web モード（GitHub Pages 推奨）

JSON を外部ファイルに分離。HTML は ~45KB の SPA のみ。`file://` では CORS のため動作不可。

```bat
python taxa_tree.py --qid Q25341 --web
```

### SPA ランディングページ（index.html）

```
URL                  表示
index.html        →  カード一覧
index.html#Q25341 →  スズメ目の系統図ビューワー
```

カードをクリックするとページ遷移なしでビューワーに切り替わります。「← 一覧」ボタンまたはブラウザの戻るボタンで一覧に戻れます。

---

## HTML の操作方法

### PC（マウス）

| 操作 | 動作 |
|---|---|
| ノードにマウスオーバー | ツールチップ表示（画像・学名・種数） |
| 種ノードをクリック | Wikipedia を新しいタブで開く |
| 上位ノードをクリック | 展開 / 折りたたみ |
| ドラッグ / ホイール | 移動 / ズーム |

### スマートフォン（タッチ）

| 操作 | 動作 |
|---|---|
| ノードを長押し（約0.5秒） | ツールチップ表示 |
| 種ノードを短タップ | Wikipedia を開く |
| 上位ノードを短タップ | 展開 / 折りたたみ |
| ✕ または背景タップ | ツールチップを閉じる |

### ヘッダーボタン

| ボタン | 機能 | 設定保存 |
|---|---|---|
| 🌙 / ☀️ | テーマ切り替え | localStorage |
| JA / EN | 言語切り替え | localStorage |
| LR / TB | レイアウト切り替え | localStorage |
| 🖼 | 画像アイコン ON/OFF | localStorage |
| 科まで / 属まで / 全展開 / 折りたたむ | ツリー操作 | — |
| 全体表示 | ズームリセット | — |

### 検索

🔍 ボタンまたは Enter で実行（リアルタイム検索は無効）。折りたたみ状態でも全ノードを走査し、ヒット時は自動展開・自動フィットします。✕ ボタンでクリア。

### 凡例バー

| 表示 | 意味 |
|---|---|
| 通常色 | Wikidata P171 で取得 |
| 橙リング | P171+ 推移的補完（亜属経由） |
| 赤破線 | データ不完全（全手段失敗） |
| 凡例右端スライダー `↔ TT` | ツールチップ幅を調整（localStorage に保存） |

### Wikipedia リンク

すべてのランクのツールチップに「Wikipedia で開く ↗」ボタンが表示されます。JA モードで和名がある場合は日本語版の存在を API で確認し、なければ英語版を開きます。

---

## 調整項目リファレンス

`module/taxa_html.py` の定数と設定項目の一覧です。

---

### 画像レイジーロード（`taxa_html.py` L744–746）

```javascript
const IMG_ZOOM_MIN     = 0.35;   // この倍率未満では画像ロードしない
const IMG_DEBOUNCE_MS  = 1500;   // ズーム操作停止後に待つ時間 (ms)
const IMG_RATE_PER_SEC = 4;      // 1秒あたりの最大リクエスト数
```

| 定数 | デフォルト | 調整のヒント |
|---|---|---|
| `IMG_ZOOM_MIN` | `0.35` | 小さくすると俯瞰時も画像表示（通信量増） |
| `IMG_DEBOUNCE_MS` | `1500` ms | 小さくすると素早く表示（サーバー負荷増） |
| `IMG_RATE_PER_SEC` | `4` 件/秒 | 大きくすると速い（Wikimedia 429 エラーのリスク増） |

---

### ツールチップ挙動（`taxa_html.py` L882–897）

```javascript
// ノードを離れてからツールチップが消えるまでの猶予
_hideTimer = setTimeout(() => { tt.style.display = "none"; }, 300);

// ツールチップ近傍（この px 以内を移動中は hide をキャンセル）
const margin = 10;
```

| 設定 | デフォルト | 調整のヒント |
|---|---|---|
| hide delay | `450` ms | 大きくすると消えにくい（ツールチップに移りやすい）、小さくすると素早く消える |
| 近傍マージン | `15` px | 大きくすると消えにくい。小さくすると意図しないキャンセルが減る |

---

### ツールチップサイズ（ブラウザ UI / `taxa_html.py` L230・L859）

凡例バー右端の `↔ TT` スライダーで操作します。設定は localStorage に保存されます。

| 設定 | デフォルト | 範囲 |
|---|---|---|
| ツールチップ幅 | `280` px | `180`〜`420` px（10 px 刻み） |

コードで初期値を変更したい場合:

```javascript
// L859: JavaScript 側の初期値
let _ttW = parseInt(localStorage.getItem("taxa_tt_w") || "280");

// L230: スライダーの HTML 属性
min="180" max="420" step="10" value="280"
```

---

### タッチ長押し判定（`taxa_html.py` L908）

```javascript
const LP_MS = 480;    // 長押しとして認識するまでの時間 (ms)
```

| 定数 | デフォルト | 調整のヒント |
|---|---|---|
| `LP_MS` | `480` ms | 短くすると反応が早い。長くすると誤タップが減る |

---

### 取得速度（`taxa_fetch.py` L684 付近）

```python
time.sleep(0.8)   # SPARQL リクエスト間の待機時間（秒）
```

Wikidata の負荷軽減のための固定値。短くすると取得が速くなりますがレートリミットに引っかかる可能性があります。

---

### 出力フォルダ（`taxa_tree.py` L62）

```python
OUTPUT_DIR = "result"   # ← ここを変更するだけで全出力先が変わる
```

---

## コード構成

### taxa_tree.py（724行）

```
OUTPUT_DIR = "result"  ← 出力先の唯一の設定箇所（L62）

_print_meta(tree)           キャッシュ _meta を表示
_load_cache(qid)            キャッシュ読み込み（QID指定 or 最新自動選択）
_cleanup_html(output_dir)   taxa_*.html を全削除（web モード用）
_save_html(tree, out, web)  HTML生成・保存・index.html 自動更新
_render_all(web_mode)       一括再生成

main()
  排他グループ: --taxon / --render / --render-all / --cached / --test
  --render-all + --web: _cleanup_html → make_index_html
  --render-all        : 全キャッシュ → make_html × N → make_index_html
```

### module/taxa_fetch.py（1,078行）

```
FETCH_VERSION = "1.7"

init_session(proxy, email)
  User-Agent: "TaxaTreeBot/1.0 (you@example.com)"
  環境変数 TAXA_CONTACT_EMAIL でも設定可

resolve_image_url(filename, width)
  MD5計算のみ（HTTP リクエストなし）
  SVG/TIF/WEBP → .png サムネイルを要求

子ノード補完（属ノードの子が0件のとき自動適用）:
  ① Wikidata P171 直接
  ② P171+ 推移的閉包（亜属経由の種を一括捕捉）
  ③ 全手段失敗 → STRATEGY_INCOMPLETE（赤破線）

重複防止:
  visited |= nodes_dict.keys()  ← 科をまたいだ重複を排除

進捗バー:
  バー・%: 科数ベース（確定値）
  右側:    種数（参考表示）
```

### module/taxa_html.py（1,195行）

```
HTML_VERSION = "1.5"

make_html(tree, root_qid)             standalone: const DATA={...JSON...};
make_web_viewer(tree, qid, json_file) web: fetch(json) → init()
make_index_html(output_dir)           SPA index.html 生成
  DOM 構造は _SPA_HEAD 定数で直接定義
  テンプレートから CSS・JS のみを抽出して再利用
  プレースホルダは __KEY__ 形式で .replace() で差し込む

URL ルーティング:
  index.html        → ランディング（hashchange イベント）
  index.html#QXXX   → ビューワー（taxa_cache_QXXX.json を fetch）

画像レイジーロード（3段制御）:
  段1: IMG_ZOOM_MIN 未満 → スキップ
  段2: IMG_DEBOUNCE_MS ms デバウンス
  段3: IMG_RATE_PER_SEC 件/秒 レートキュー

ツールチップ:
  hide delay 300ms + 近傍ガード 10px
  幅は CSS 変数 --tt-w（凡例バーのスライダーで操作）
  localStorage["taxa_tt_w"] に保存

Wikipedia openWiki():
  JA + 和名あり → API で日本語版存在確認 → なければ EN
```

---

## キャッシュの `_meta` フィールド

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

`fetch_version` が `1.4` 未満のキャッシュは `image_url` が含まれないため再取得を推奨します。

---

## バージョン履歴

### v6.0（現バージョン）

**確定日: 2026-03 / 合計 2,997行（taxa_tree: 724 / taxa_fetch: 1,078 / taxa_html: 1,195）**

#### FETCH_VERSION 変遷

| Ver | 主な変更 |
|---|---|
| 1.0 | ファイル分割初版 |
| 1.3 | P18 再追加（脱落バグ修正） |
| 1.4 | `resolve_image_url` MD5方式（API廃止） |
| 1.5 | 子補完（A+B）・`--email`・UA メール埋め込み |
| 1.6 | P171+ 推移的閉包（GBIF・プレフィックス方式廃止） |
| **1.7** | 科またぎ重複排除・ランクフィルタ修正 |

#### HTML_VERSION 変遷

| Ver | 主な変更 |
|---|---|
| 1.0 | 分割初版 |
| 1.2 | 画像・モバイル・Wikipedia リンク |
| 1.4 | crossOrigin・250px・JA存在チェック・全ランク Wiki ボタン |
| **1.5** | SPA 統合・補完色分け・レイジーロード3段・ツールチップ UX・サイズスライダー |

### 旧バージョン

| Ver | 行数 | 内容 |
|---|---|---|
| v5.0 | 2,639行 | 3ファイル構成確立 |
| v4.0 | 1,698行 | 単一ファイル・画像・Wikipedia |
| v1.0 | 1,131行 | passeriformes_tree.py を汎用化 |

---

## 既知の制約

| # | 項目 | 詳細 |
|---|---|---|
| 1 | P171+ 平坦化 | 亜属が子なしノードになることがある（取りこぼしはなし） |
| 2 | 画像取得漏れ | P18 未登録の種は画像なし |
| 3 | オフライン閲覧 | 画像表示にインターネット接続が必要 |
| 4 | web モードのローカル動作 | CORS のため `file://` では動作しない |
| 5 | 取得速度 | `time.sleep(0.8)` 固定 |

---

## AI 開発クレジット

本プロジェクトは **ノーコード開発** の事例として、Claude AI との対話のみによってコードを生成・改良しました。

### 使用 AI

| 項目 | 内容 |
|---|---|
| AI サービス | [Claude](https://claude.ai/) by Anthropic |
| モデル | **Claude Sonnet 4.6**（claude-sonnet-4-6） |
| 開発期間 | 2026年3月 |
| 開発手法 | 対話型ノーコード開発（プロンプトエンジニアリング） |

人間が担当したのは **要件定義・動作確認・微調整の指示** のみです。コードの実装・デバッグ・リファクタリングはすべて Claude AI が行いました。

---

## 要件定義（生成プロンプト）

同等のツールを再生成する場合の参考として、開発で使用した主要なプロンプト要件を記載します。

### 基本要件

```
Wikidata SPARQL API から生物分類データを取得し、
D3.js でインタラクティブな系統図 HTML を生成する Python スクリプトを作成してください。

要件:
- 対応範囲: 全生物界（鳥類・哺乳類・植物・昆虫・魚類・菌類など）
- データソース: Wikidata（無料・認証不要）
- 出力: 単体で動作する HTML ファイル（外部依存なし）
- 依存ライブラリ: requests のみ（pip install requests）
- Python 3.10 以上で動作
```

### データ取得要件

```
- Wikidata QID または学名・和名での検索に対応
- BFS（幅優先探索）で目→科→属→種まで再帰的に取得
- Phase 1（目〜科）と Phase 2（科以下）に分けて取得し進捗バーを表示
- キャッシュ JSON を保存し、--render オプションで再取得なしに HTML を再生成できる
- P171（親タクソン）が未登録の属は P171+（推移的閉包）で補完取得
- 取得ノードに fetch_strategy フィールドを記録し補完経路を可視化
- 画像 URL は Wikimedia Commons の MD5 CDN URL を計算で生成（API 呼び出し不要）
- User-Agent に連絡先メールを埋め込む（--email オプション）
```

### HTML・UI 要件

```
D3.js v7 を使用したインタラクティブ系統図:
- ノードの展開/折りたたみ（クリック）
- ズーム・パン（ホイール・ドラッグ）
- LR（左→右）/ TB（上→下）レイアウト切り替え
- ダーク / ライトテーマ切り替え（localStorage 保存）
- 日本語 / 英語優先モード切り替え（localStorage 保存）
- 種ノードに Wikimedia 画像アイコン表示（レイジーロード・レート制限付き）
- マウスオーバーでツールチップ表示（画像・学名・和名・Wikipedia リンク）
- ツールチップ幅のスライダー調整（凡例バー右端・localStorage 保存）
- Wikipedia リンク: JA モードで日本語版の存在を API 確認し、なければ英語版
- 検索ボックス（🔍ボタン/Enter で実行・折りたたみ状態でも全ノード走査）
- スマートフォン対応（長押し→ツールチップ、短タップ→展開/Wikipedia）
- 補完ノードの色分け（橙: P171+補完、赤破線: データ不完全）
```

### SPA 要件

```
GitHub Pages で動作する SPA（Single Page Application）として構成:

ファイル構成:
  result/index.html              SPA（ランディング + ビューワー統合）
  result/taxa_cache_Q*.json      データ（JSON 分離 web モード）

URL ルーティング（ハッシュベース）:
  index.html        → カード一覧（ランディングページ）
  index.html#Q25341 → 系統図ビューワー

機能:
- ページ遷移なしでカード一覧 ↔ 系統図ビューワーを切り替え
- ブラウザの戻る/進むボタンに対応（hashchange イベント）
- JSON をストリーミング fetch してプログレスバーを表示
- standalone モード（JSON 埋め込み HTML・file:// でローカル動作可）も維持

コマンド:
  --web         web モード（JSON 分離・GitHub Pages 用）
  --render-all --web  余分な HTML を削除して index.html を再生成
```

### 非機能要件

```
- Wikimedia サーバーへの配慮:
    画像リクエストは標準サイズ（120px / 250px）のみ使用（429 エラー対策）
    レートリミット: 4 件/秒（IMG_RATE_PER_SEC）
    ズーム閾値 0.35 未満では画像ロードしない（IMG_ZOOM_MIN）
    デバウンス 1500ms（IMG_DEBOUNCE_MS）

- コード品質:
    3ファイル構成（taxa_tree.py / taxa_fetch.py / taxa_html.py）
    UI 変更は taxa_html.py のみ、データロジックは taxa_fetch.py のみに閉じる
    モジュールバージョン定数（FETCH_VERSION / HTML_VERSION）で変更を追跡
    キャッシュに _meta フィールドでバージョン・取得日時を記録
```


---

## 参考文献

1. Vrandečić, D., & Krötzsch, M. (2014). Wikidata. *CACM*, 57(10). https://doi.org/10.1145/2629489
2. Gill, F., et al. (2024). IOC World Bird List v14.1. https://doi.org/10.14344/IOC.ML.14.1
3. Oliveros, C. H., et al. (2019). PNAS, 116(16). https://doi.org/10.1073/pnas.1813206116
4. Bostock, M. (2023). D3.js v7. https://d3js.org/
5. Wikimedia Foundation. Wikimedia Commons. https://commons.wikimedia.org/