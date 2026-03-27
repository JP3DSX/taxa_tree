#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
module/taxa_fetch.py  ─  データ取得・モデル構築モジュール
================================================================
Wikidata SPARQL から任意の分類群を BFS で取得し、
ツリー辞書（dict）を返す。出力先・ファイル名は呼び出し元が管理する。

公開 API:
    init_session(proxy, email) セッション初期化（SSL自動検出・UA設定）
    run_test(proxy)            接続診断
    pick_taxon(query)          学名・和名 → (qid, label)
    fetch_root_info(qid)       ルートノード情報取得
    fetch_phase1(root, split)  Phase1 BFS (ルート〜split_rank)
    fetch_phase2(root, nodes, split, stop, total_sp)  Phase2 BFS
    estimate_species_count(qid)  総種数推定
    rank_index(rank)           ランクの階層インデックス
    sanitize_filename(name)    ファイル名安全化
    _walk(node, fn)            ツリー全走査
    RANK_ORD                   ランク順リスト
    DEFAULT_SPLIT              デフォルト分割ランク
    FETCH_VERSION              フェッチモジュールのバージョン文字列
    _elapsed()                 経過時間文字列
"""
import ctypes
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from collections import deque
import hashlib
import urllib.parse

try:
    import requests
except ImportError:
    print("❌  pip install requests")
    sys.exit(1)

try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

# ─────────────────────────────────────────────────────────────────
#  定数・ランクマップ
# ─────────────────────────────────────────────────────────────────

ENDPOINT = "https://query.wikidata.org/sparql"
HEADERS  = {
    "User-Agent": "TaxaTreeBot/1.0 (educational; Python/requests)",
    "Accept":     "application/sparql-results+json",
}

# フェッチモジュールのバージョン
# SPARQL クエリ・BFS・画像URL方式など取得機能に変更があるたびにインクリメントする
FETCH_VERSION = "2.0"

# IUCN 保全状況 QID → コード
IUCN_MAP = {
    "Q219127":  "EX",   # Extinct（絶滅）
    "Q239509":  "EW",   # Extinct in the Wild（野生絶滅）
    "Q219159":  "CR",   # Critically Endangered（深刻な危機）
    "Q11394":   "EN",   # Endangered（危機）
    "Q278113":  "VU",   # Vulnerable（危急）
    "Q719675":  "NT",   # Near Threatened（準危急）
    "Q211005":  "LC",   # Least Concern（低危険）
    "Q3245245": "DD",   # Data Deficient（情報不足）
}

# GBIF iucnRedListCategory 文字列 → IUCN コード
GBIF_IUCN_MAP = {
    "EXTINCT":             "EX",
    "EXTINCT_IN_THE_WILD": "EW",
    "CRITICALLY_ENDANGERED": "CR",
    "ENDANGERED":          "EN",
    "VULNERABLE":          "VU",
    "NEAR_THREATENED":     "NT",
    "LEAST_CONCERN":       "LC",
    "DATA_DEFICIENT":      "DD",
}

# 全生物界に対応した階層順（上位→下位）
RANK_ORD = [
    "domain",        # 域
    "kingdom",       # 界
    "subkingdom",    # 亜界
    "phylum",        # 門
    "subphylum",     # 亜門
    "superclass",    # 上綱
    "class",         # 綱
    "subclass",      # 亜綱
    "infraclass",    # 下綱
    "superorder",    # 上目
    "order",         # 目
    "suborder",      # 亜目
    "infraorder",    # 下目
    "superfamily",   # 上科
    "family",        # 科
    "subfamily",     # 亜科
    "tribe",         # 族
    "subtribe",      # 亜族
    "genus",         # 属
    "subgenus",      # 亜属
    "species",       # 種
    "subspecies",    # 亜種
    "variety",       # 変種
    "form",          # 品種
]

# Wikidata P105 の値（QID）→ ランク文字列
RANK_MAP = {
    # 上位ランク
    "Q146481":   "domain",
    "Q36732":    "kingdom",
    "Q2136103":  "superfamily",   # ※ 動物の上科（既存）
    "Q2884736":  "subkingdom",
    "Q38348":    "phylum",
    "Q1153785":  "subphylum",
    "Q3491996":  "superclass",
    "Q37517":    "class",
    "Q5867959":  "subclass",
    "Q2007442":  "infraclass",    # ※ 旧コードで亜目に使っていたが infraclass が正確
    "Q5868144":  "superorder",
    "Q36602":    "order",
    "Q5867051":  "suborder",
    "Q2361141":  "infraorder",
    # 科周辺
    "Q35409":    "family",
    "Q164280":   "subfamily",
    "Q227936":   "tribe",
    "Q2111306":  "subtribe",
    # 属周辺
    "Q34740":    "genus",
    "Q5390130":  "subgenus",
    # 種周辺
    "Q7432":     "species",
    "Q68947":    "subspecies",
    "Q3504061":  "variety",
    "Q279749":   "form",
    # よく使われる別 QID
    "Q2007": "suborder",          # 別 suborder QID
}

# 「以下の子を取得する」Phase 1 のデフォルト打ち切りランク
DEFAULT_SPLIT = "family"

# 出力先ディレクトリ（キャッシュ JSON と HTML の両方をここに保存する）

# ─────────────────────────────────────────────────────────────────
#  ランクユーティリティ
# ─────────────────────────────────────────────────────────────────

def rank_index(rank: str) -> int:
    """RANK_ORD 上の位置。未知ランクは末尾扱い。"""
    try:
        return RANK_ORD.index(rank)
    except ValueError:
        return len(RANK_ORD)

def is_leaf_rank(rank: str) -> bool:
    """亜種・変種・品種は通常子を持たない"""
    return rank in ("subspecies", "variety", "form")

def infer_rank(sci: str, parent_rank: str) -> str:
    """P105 未登録ノードの rank を学名の語数から推定する。
    ・3語以上 → subspecies
    ・2語（二項名）→ species
    ・1語 → 推定不能（unknown）。BFS は続けるが子の存在に依存する
    """
    parts = sci.strip().split()
    if len(parts) >= 3:
        return "subspecies"
    if len(parts) == 2:
        return "species"
    # 1語は推定不能 → unknown のまま返す
    # （fetch_phase1 / bfs_subtree 内で BFS キューへ積むかどうかは呼び側が判断）
    return "unknown"

def sanitize_filename(name: str) -> str:
    """ファイル名に使えない文字を除去する。"""
    return re.sub(r'[\\/*?:"<>|\'　\s]+', "_", name).strip("_")[:60]

# ─────────────────────────────────────────────────────────────────
#  ANSI 進捗バー
# ─────────────────────────────────────────────────────────────────

def _enable_ansi():
    if sys.platform == "win32":
        try:
            k = ctypes.windll.kernel32
            h = k.GetStdHandle(-11)
            m = ctypes.c_ulong()
            k.GetConsoleMode(h, ctypes.byref(m))
            k.SetConsoleMode(h, m.value | 0x0004)
        except Exception:
            pass

_enable_ansi()
_t0 = time.time()

def _elapsed():
    s = int(time.time() - _t0)
    return f"{s//60:02d}:{s%60:02d}"

_bar = {"done": 0, "total": 0, "done_p": 0, "total_p": 0,
        "done_sp": 0, "total_sp": 0,
        "cur": "", "active": False, "unit": "種"}

# ─── 取得統計（効果測定用） ────────────────────────────────────
_stats: dict = {
    "queries":         0,   # SPARQL クエリ発行回数
    "batch_queries":   0,   # バッチクエリ発行回数
    "oneshot_queries": 0,   # P171+ ワンショットクエリ発行回数
    "oneshot_hits":    0,   # ワンショットで取得できた科の数
    "oneshot_miss":    0,   # フォールバックした科の数
    "single_queries":  0,   # 単体クエリ発行回数（補完など）
    "rows_fetched":   0,    # 取得行数合計
    "sleep_total":    0.0,  # sleep 合計秒数
    "phase1_start":   0.0,
    "phase2_start":   0.0,
    "phase1_elapsed": 0.0,
    "phase2_elapsed": 0.0,
}

def print_stats() -> None:
    """取得統計をコンソールに出力する（効果測定用）。"""
    s = _stats
    total = s["phase1_elapsed"] + s["phase2_elapsed"]
    pprint(f"\n  ┌─ 取得統計 ───────────────────────────────────")
    pprint(f"  │  総クエリ数    : {s['queries']:>6} 回")
    pprint(f"  │    バッチ      : {s['batch_queries']:>6} 回")
    pprint(f"  │    ワンショット: {s['oneshot_queries']:>6} 回  (成功:{s['oneshot_hits']} / FB:{s['oneshot_miss']})")
    pprint(f"  │    単体（補完）: {s['single_queries']:>6} 回")
    pprint(f"  │  取得行数合計  : {s['rows_fetched']:>6,} 件")
    pprint(f"  │  sleep 合計    : {s['sleep_total']:>6.1f} 秒")
    pprint(f"  │  Phase1 時間   : {s['phase1_elapsed']:>6.1f} 秒")
    pprint(f"  │  Phase2 時間   : {s['phase2_elapsed']:>6.1f} 秒")
    pprint(f"  │  合計時間      : {total:>6.1f} 秒")
    pprint(f"  └────────────────────────────────────────────────")



def _bar_line():
    b = _bar
    cols   = shutil.get_terminal_size((100, 24)).columns
    # バー・% は科数ベース（確定値）
    pct    = b["done_p"] / b["total_p"] if b["total_p"] > 0 else 0
    bw     = max(10, min(30, cols - 70))
    filled = int(bw * pct)
    bar    = "█" * filled + "░" * (bw - filled)
    # 科数表示
    fam_s  = f"{b['done_p']}/{b['total_p']}科"
    # 種数表示（参考値）
    sp_tot = f"~{b['total_sp']:,}" if b["total_sp"] > 0 else "?"
    sp_s   = f"  {b['done_sp']:,}/{sp_tot}種" if b["total_sp"] > 0 or b["done_sp"] > 0 else ""
    line   = (f"  [{bar}] {fam_s}{sp_s}  {pct*100:.1f}%  {_elapsed()}")
    if b["cur"]:
        avail = cols - len(line) - 5
        if avail > 4:
            line += f"  ← {b['cur'][:avail]}"
    return line[:cols - 1]

def _redraw():
    if _bar["active"]:
        sys.stdout.write(f"\r\033[K{_bar_line()}")
        sys.stdout.flush()

def bar_update(done_p, total_p, done_sp=0, total_sp=0, cur="", unit="種"):
    """バー状態を更新して再描画する。
    バーの塗り・% は科数（done_p/total_p）、種数は参考表示（done_sp/total_sp）。
    """
    _bar.update(done_p=done_p, total_p=total_p,
                done_sp=done_sp, total_sp=total_sp,
                done=done_p, total=total_p,
                cur=cur, unit=unit, active=True)
    _redraw()

def pprint(msg):
    """ログ1行を流し、直後にバーを再描画する。"""
    sys.stdout.write(f"\r\033[K{msg}\n")
    _redraw()
    sys.stdout.flush()

def bar_done():
    _bar["active"] = False
    sys.stdout.write("\n")
    sys.stdout.flush()

def fmt_node(indent, qid, sci, ja, rank):
    """統一表示フォーマット: [QID(10桁)] 📁/🐦 英語名 / 日本語名  (rank)"""
    icon = "🐦" if rank in ("species", "subspecies", "variety", "form") else "📁"
    name = sci + (f" / {ja}" if ja and ja != sci else "")
    return f"{indent}[{qid:<10}] {icon} {name}  ({rank})"

# ─────────────────────────────────────────────────────────────────
#  Session（SSL自動検出 / プロキシ対応）
# ─────────────────────────────────────────────────────────────────

_sess = None

def init_session(proxy=None, email=None):
    """セッション初期化。email を指定すると User-Agent に埋め込まれる。
    Wikimedia のポリシー上、連絡先メールを UA に含めることが推奨されている。
    """
    global _sess
    proxy_dict = None
    if proxy:
        proxy_dict = {"http": proxy, "https": proxy}
    else:
        for k in ("HTTPS_PROXY","https_proxy","HTTP_PROXY","http_proxy"):
            v = os.environ.get(k)
            if v:
                proxy_dict = {"http": v, "https": v}
                break

    # User-Agent: email が指定されていれば埋め込む
    contact = email or os.environ.get("TAXA_CONTACT_EMAIL", "")
    ua = (f"TaxaTreeBot/1.0 ({contact})"
          if contact
          else "TaxaTreeBot/1.0 (educational; Python/requests)")
    session_headers = dict(HEADERS)
    session_headers["User-Agent"] = ua
    if contact:
        print(f"  ℹ  User-Agent: {ua}")

    verify = True
    for v in [True, False]:
        try:
            r = requests.get("https://www.wikidata.org/", headers=session_headers,
                             timeout=12, verify=v, proxies=proxy_dict)
            if r.status_code < 500:
                verify = v; break
        except requests.exceptions.SSLError:
            if v: continue
        except Exception:
            pass

    s = requests.Session()
    s.verify  = verify
    s.headers.update(session_headers)
    if proxy_dict:
        s.proxies.update(proxy_dict)
        print(f"  ℹ  プロキシ: {list(proxy_dict.values())[0]}")
    if not verify:
        print("  ℹ  SSL検証スキップ（社内プロキシ対応）")
    _sess = s
    return s

def get_session():
    return _sess or init_session()

# ─────────────────────────────────────────────────────────────────
#  SPARQL
# ─────────────────────────────────────────────────────────────────

def sparql(query, label="", retries=4, timeout=45, silent=False):
    sess = get_session()
    for attempt in range(retries):
        try:
            r = sess.get(ENDPOINT,
                         params={"query": query, "format": "json"},
                         timeout=timeout)
            if r.status_code == 429:
                w = int(r.headers.get("Retry-After", 30))
                pprint(f"    ⏳ レート制限 → {w}秒待機…"); time.sleep(w); continue
            if r.status_code != 200:
                if not silent: pprint(f"    ⚠  HTTP {r.status_code}: {r.text[:100]}")
                time.sleep(8 * (attempt + 1)); continue
            rows = r.json().get("results", {}).get("bindings", [])
            _stats["queries"]     += 1
            _stats["rows_fetched"] += len(rows)
            if label and not silent: pprint(f"    ✓  {label}: {len(rows)}件")
            return rows
        except requests.exceptions.Timeout:
            if not silent: pprint(f"    ⚠  タイムアウト ({attempt+1}/{retries})")
        except Exception as e:
            if not silent: pprint(f"    ⚠  {type(e).__name__}: {e}")
        if attempt < retries - 1:
            w = 8 * (attempt + 1)
            if not silent: pprint(f"    ↩  {w}秒後再試行…")
            time.sleep(w)
    return []

# ─────────────────────────────────────────────────────────────────
#  タクソン検索（--taxon 用）
# ─────────────────────────────────────────────────────────────────

def search_taxon(query: str, limit: int = 10) -> list[dict]:
    """
    Wikidata wbsearchentities API で分類群を検索する。
    返り値: [{"qid": "Q...", "label": "...", "desc": "...", "sci": "..."}, ...]
    """
    results = []
    # 日本語・英語の両方で検索
    for lang in ("ja", "en"):
        try:
            r = get_session().get(
                "https://www.wikidata.org/w/api.php",
                params={
                    "action":   "wbsearchentities",
                    "search":   query,
                    "language": lang,
                    "type":     "item",
                    "limit":    limit,
                    "format":   "json",
                },
                timeout=15,
            )
            for item in r.json().get("search", []):
                qid = item.get("id", "")
                if not qid or any(x["qid"] == qid for x in results):
                    continue
                results.append({
                    "qid":   qid,
                    "label": item.get("label", ""),
                    "desc":  item.get("description", ""),
                    "alias": ", ".join(item.get("aliases", [])),
                })
        except Exception:
            pass
    return results[:limit]

def pick_taxon(query: str) -> tuple[str, str]:
    """
    検索結果を表示してユーザーに選ばせ、(qid, label) を返す。
    1件しかない場合は自動選択。
    """
    print(f"\n  🔍 「{query}」を検索中…")
    candidates = search_taxon(query)
    if not candidates:
        print("  ❌ 検索結果が0件です。学名または和名を確認してください。")
        sys.exit(1)

    # 分類群らしいもの（P105 を持つか、説明に taxon / 分類 を含む）を優先
    def is_taxon(c):
        d = c["desc"].lower()
        return any(kw in d for kw in (
            "taxon","genus","species","family","order","class","phylum",
            "分類","綱","目","科","属","種","門","界"
        ))
    taxa    = [c for c in candidates if is_taxon(c)]
    others  = [c for c in candidates if not is_taxon(c)]
    ranked  = taxa + others

    if len(ranked) == 1:
        c = ranked[0]
        print(f"  ✓  自動選択: [{c['qid']}] {c['label']}  —  {c['desc']}")
        return c["qid"], c["label"]

    print(f"\n  候補 {len(ranked)} 件（分類群と思われるものを上位表示）:\n")
    for i, c in enumerate(ranked, 1):
        mark  = "🌿 " if is_taxon(c) else "   "
        alias = f"  ({c['alias']})" if c["alias"] else ""
        print(f"  {mark}{i:2d}. [{c['qid']:12s}] {c['label']}{alias}")
        print(f"           {c['desc'][:70]}")
    print()

    while True:
        try:
            s = input("  番号を入力してください（1–{0}）: ".format(len(ranked))).strip()
            n = int(s)
            if 1 <= n <= len(ranked):
                c = ranked[n - 1]
                return c["qid"], c["label"]
        except (ValueError, KeyboardInterrupt):
            pass
        print(f"  1〜{len(ranked)} の数字を入力してください。")

# ─────────────────────────────────────────────────────────────────
#  ルートノード情報の取得
# ─────────────────────────────────────────────────────────────────

def fetch_root_info(qid: str) -> dict:
    """
    指定 QID の分類群情報（学名・日本語ラベル・ランク）を取得する。
    """
    # Entity API（確実に日本語ラベルが取れる）
    try:
        r = get_session().get(
            f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json",
            timeout=15)
        entity  = r.json().get("entities", {}).get(qid, {})
        ja      = entity.get("labels", {}).get("ja", {}).get("value", "")
        en      = entity.get("labels", {}).get("en", {}).get("value", "")
        # P225（学名）
        sci     = ""
        for st in entity.get("claims", {}).get("P225", []):
            v = st.get("mainsnak", {}).get("datavalue", {}).get("value", "")
            if v: sci = v; break
        # P105（ランク QID）
        rank    = "unknown"
        for st in entity.get("claims", {}).get("P105", []):
            rqid = st.get("mainsnak", {}).get("datavalue", {}).get("value", {})
            if isinstance(rqid, dict):
                rqid = rqid.get("id", "")
            rank = RANK_MAP.get(rqid, "unknown"); break
        return {
            "id":   qid,
            "name": sci or en or qid,
            "ja":   ja,
            "rank": rank,
            "children": [],
        }
    except Exception as e:
        pprint(f"  ⚠  Entity API 失敗 ({e})、SPARQL にフォールバック…")

    # SPARQL フォールバック
    q = f"""
SELECT ?name ?label ?rank WHERE {{
  OPTIONAL {{ wd:{qid} wdt:P225 ?name }}
  OPTIONAL {{ wd:{qid} wdt:P105 ?rank }}
  SERVICE wikibase:label {{
    bd:serviceParam wikibase:language "ja,en" .
    wd:{qid} schema:name ?label .
  }}
}} LIMIT 1"""
    rows = sparql(q, timeout=20)
    sci  = rows[0].get("name",  {}).get("value", qid) if rows else qid
    ja   = rows[0].get("label", {}).get("value", "")   if rows else ""
    rqid = rows[0].get("rank",  {}).get("value", "").rsplit("/", 1)[-1] if rows else ""
    return {
        "id":       qid,
        "name":     sci,
        "ja":       ja if ja != sci else "",
        "rank":     RANK_MAP.get(rqid, "unknown"),
        "children": [],
    }

# ─────────────────────────────────────────────────────────────────
#  直接の子ノード取得
# ─────────────────────────────────────────────────────────────────

def get_direct_children(parent_qid: str, batch_size: int = 200) -> list:
    """
    P171（直接の親）で子ノードを取得する。
    呼び出し元は必要に応じて get_children_with_supplement を使うこと。
    """
    records = []
    offset  = 0
    while True:
        q = f"""
SELECT DISTINCT ?child ?childLabel ?name ?rank ?jaName ?img ?iucn WHERE {{
  ?child wdt:P171 wd:{parent_qid} ;
         wdt:P225 ?name .
  OPTIONAL {{ ?child wdt:P105 ?rank }}
  OPTIONAL {{ ?child wdt:P1843 ?jaName . FILTER(LANG(?jaName) = "ja") }}
  OPTIONAL {{ ?child wdt:P18  ?img }}
  OPTIONAL {{ ?child wdt:P141 ?iucn }}
  SERVICE wikibase:label {{
    bd:serviceParam wikibase:language "ja,en" .
  }}
}} ORDER BY ?name
LIMIT {batch_size} OFFSET {offset}
"""
        batch = sparql(q, timeout=45, silent=True)
        if not batch: break
        records.extend(batch)
        if len(batch) < batch_size: break
        offset += batch_size
        _stats["sleep_total"] += 1.0; time.sleep(1.0)
    return records



# バッチ取得のデフォルトサイズ（Wikidata の安定動作実績から 20 を推奨）
BATCH_PARENT_SIZE = 20

def get_batch_children(parent_qids: list[str]) -> dict[str, list]:
    """
    VALUES ?parent {{ wd:Q1 wd:Q2 ... }} で複数の親を1クエリで一括取得する。

    戻り値: {parent_qid: [row, ...]} の辞書
    """
    if not parent_qids:
        return {}

    values = " ".join(f"wd:{q}" for q in parent_qids)
    q = f"""
SELECT DISTINCT ?parent ?child ?childLabel ?name ?rank ?jaName ?img ?iucn WHERE {{
  VALUES ?parent {{ {values} }}
  ?child wdt:P171 ?parent ;
         wdt:P225 ?name .
  OPTIONAL {{ ?child wdt:P105  ?rank }}
  OPTIONAL {{ ?child wdt:P1843 ?jaName . FILTER(LANG(?jaName) = "ja") }}
  OPTIONAL {{ ?child wdt:P18   ?img }}
  OPTIONAL {{ ?child wdt:P141  ?iucn }}
  SERVICE wikibase:label {{
    bd:serviceParam wikibase:language "ja,en" .
  }}
}} ORDER BY ?parent ?name
"""
    rows = sparql(q, timeout=60, silent=True)
    _stats["batch_queries"] += 1

    # 親ごとにグループ化
    result: dict[str, list] = {q: [] for q in parent_qids}
    for row in rows:
        p = row.get("parent", {}).get("value", "").rsplit("/", 1)[-1]
        if p in result:
            result[p].append(row)
    return result


def get_transitive_children(parent_qid: str,
                             stop_rank: str,
                             batch_size: int = 500) -> list:
    """
    P171+（推移的閉包）で stop_rank までの全子孫を一括取得する。

    P171 が亜属・亜科などを経由していても漏れなく取得できる。
    直接クエリで0件だった属に対してフォールバックとして使用する。

    注意: P171+ は Wikidata SPARQL で最適化されており高速。
    """
    # RANK_MAP は複数QIDが同一ランクに対応するため全QIDを収集
    stop_qids = [q for q, r in RANK_MAP.items() if r == stop_rank]
    records   = []
    offset    = 0
    if stop_qids:
        qid_values = " ".join(f"wd:{q}" for q in stop_qids)
        rank_filter = f"  ?child wdt:P105 ?stopRank . FILTER(?stopRank IN ({qid_values}))\n"
    else:
        rank_filter = ""
    while True:
        q = f"""
SELECT DISTINCT ?child ?childLabel ?name ?rank ?jaName ?img ?iucn WHERE {{
  ?child wdt:P171+ wd:{parent_qid} ;
         wdt:P225 ?name .
{rank_filter}  OPTIONAL {{ ?child wdt:P105 ?rank }}
  OPTIONAL {{ ?child wdt:P1843 ?jaName . FILTER(LANG(?jaName) = "ja") }}
  OPTIONAL {{ ?child wdt:P18  ?img }}
  OPTIONAL {{ ?child wdt:P141 ?iucn }}
  SERVICE wikibase:label {{
    bd:serviceParam wikibase:language "ja,en" .
  }}
}} ORDER BY ?name
LIMIT {batch_size} OFFSET {offset}
"""
        batch = sparql(q, timeout=60, silent=True)
        if not batch: break
        records.extend(batch)
        if len(batch) < batch_size: break
        offset += batch_size
        time.sleep(0.8)
    return records

# ─────────────────────────────────────────────────────────────────
#  P171+ ワンショット取得（案A）
# ─────────────────────────────────────────────────────────────────

# ワンショット1回あたりの取得上限（Wikidata の行数制限に合わせて調整）
ONESHOT_LIMIT  = 5000
# ワンショットのタイムアウト秒数（大きい分類群では時間がかかる）
ONESHOT_TIMEOUT = 55

def fetch_subtree_oneshot(
    root_node: dict,
    nodes_dict: dict,
    stop_rank: str,
) -> bool:
    """
    P171+（推移的閉包）で root_node の全子孫を一括取得してツリーに追加する。

    設計上のポイント:
    - SPARQL クエリは最小限（P171+ + P225 + OPTIONAL フィールドのみ）
    - rank_filter は使わない → Wikidata の最適化を妨げるため
    - 親子関係は P225 学名の階層（属名プレフィックス）で推定する
    - stop_rank を超えるノードは Python 側でフィルタ

    戻り値: True=成功（1件以上取得）/ False=失敗（フォールバック要）
    """
    root_qid = root_node["id"]
    stop_idx = rank_index(stop_rank)

    records: list = []
    offset = 0
    while True:
        q = f"""
SELECT DISTINCT ?child ?childLabel ?name ?rank ?jaName ?img ?iucn WHERE {{
  ?child wdt:P171+ wd:{root_qid} ;
         wdt:P225  ?name .
  OPTIONAL {{ ?child wdt:P105  ?rank }}
  OPTIONAL {{ ?child wdt:P1843 ?jaName . FILTER(LANG(?jaName) = "ja") }}
  OPTIONAL {{ ?child wdt:P18   ?img }}
  OPTIONAL {{ ?child wdt:P141  ?iucn }}
  SERVICE wikibase:label {{
    bd:serviceParam wikibase:language "ja,en" .
  }}
}} ORDER BY ?name
LIMIT {ONESHOT_LIMIT} OFFSET {offset}
"""
        rows = sparql(q, timeout=ONESHOT_TIMEOUT, silent=True)
        _stats["oneshot_queries"] += 1
        if not rows:
            break
        records.extend(rows)
        if len(rows) < ONESHOT_LIMIT:
            break
        offset += ONESHOT_LIMIT
        _stats["sleep_total"] += 0.8
        time.sleep(0.8)

    if not records:
        return False

    # ── 新規ノードを nodes_dict に登録 ──────────────────────────
    # stop_rank を超えるノードはスキップ
    new_nodes: dict[str, dict] = {}
    for row in records:
        node = _parse_child_row(row, "")
        if not node:
            continue
        if rank_index(node["rank"]) > stop_idx:
            continue
        qid = node["id"]
        if qid not in nodes_dict and qid not in new_nodes:
            new_nodes[qid] = node

    if not new_nodes:
        return False

    nodes_dict.update(new_nodes)

    # ── 親子関係を復元（学名プレフィックスで推定）──────────────
    # 例: "Corvus corax" の親は nodes_dict の中で "Corvus" という名の属ノード
    # まず全ノードを sci名 → node の辞書に変換
    name_to_node: dict[str, dict] = {nd["name"]: nd for nd in nodes_dict.values()
                                      if nd.get("name")}

    for qid, node in new_nodes.items():
        sci   = node.get("name", "")
        parts = sci.split()
        # 学名2語以上の場合: "Corvus corax" → 親候補は "Corvus"
        # 学名1語（属名）の場合: root_node を親とする
        if len(parts) >= 2:
            parent_name = parts[0]
            parent_node = name_to_node.get(parent_name, root_node)
        else:
            parent_node = root_node

        # 重複追加を防ぐ
        existing_ids = {c["id"] for c in parent_node["children"]}
        if qid not in existing_ids:
            parent_node["children"].append(node)

    pprint(f"    ✅  ワンショット取得: {len(new_nodes)}件 [{root_qid}] {root_node['name']}")
    return True


def _parse_child_row(row: dict, parent_rank: str) -> dict | None:
    """SPARQL 結果1行をノード辞書に変換する。rank 推定も行う。"""
    child_uri = row.get("child",  {}).get("value", "")
    child_qid = child_uri.rsplit("/", 1)[-1]
    rank_uri  = row.get("rank",   {}).get("value", "")
    rank_qid  = rank_uri.rsplit("/", 1)[-1] if rank_uri else ""
    child_rank = RANK_MAP.get(rank_qid, "")
    sci       = row.get("name",       {}).get("value", "?")
    ja_p1843  = row.get("jaName",     {}).get("value", "")
    ja_label  = row.get("childLabel", {}).get("value", "")
    ja        = ja_p1843 if ja_p1843 else ja_label

    if not child_qid: return None
    if not child_rank or child_rank == "unknown":
        child_rank = infer_rank(sci, parent_rank)

    # P18（画像）→ Wikimedia Thumbnail API で直接 CDN URL を取得
    image_url = ""
    img_val   = row.get("img", {}).get("value", "")
    if img_val:
        # ファイル名を抽出（Special:FilePath 形式または File: 形式）
        if "Special:FilePath/" in img_val:
            filename = urllib.parse.unquote(
                img_val.split("Special:FilePath/")[-1].split("?")[0]
            )
        elif img_val.lower().startswith("file:"):
            filename = img_val[5:]
        else:
            filename = ""
        if filename:
            image_url = resolve_image_url(filename, width=120)

    # IUCN 保全状況
    iucn_qid    = row.get("iucn", {}).get("value", "").rsplit("/", 1)[-1]
    iucn_status = IUCN_MAP.get(iucn_qid, "")

    # Wikidata エンティティページ URL（QIDから常に生成可能）
    wiki_url = f"https://www.wikidata.org/wiki/{child_qid}"

    node = {
        "id":       child_qid,
        "name":     sci,
        "ja":       ja if ja != sci else "",
        "rank":     child_rank,
        "wiki_url": wiki_url,
        "children": [],
    }
    if image_url:
        node["image_url"] = image_url
    if iucn_status:
        node["iucn"] = iucn_status
    return node

# ─────────────────────────────────────────────────────────────────
#  Wikimedia Commons 画像 URL 解決
# ─────────────────────────────────────────────────────────────────

def resolve_image_url(filename: str, width: int = 120) -> str:
    """
    Wikimedia Commons のファイル名から CDN サムネイル URL を生成する。

    HTTP リクエストは一切行わず、MD5 ハッシュから CDN パスを直接計算する。
    ・標準サムネイルサイズ（20/40/60/120/250/330/500px 等）を使うこと
    ・SVG/TIF/WEBP は末尾に .png を付けてラスタライズ版を要求する
    """
    if not filename:
        return ""
    # "File:" プレフィックスを除去してスペースを _ に統一
    name = filename
    if name.lower().startswith("file:"):
        name = name[5:]
    name = name.replace(" ", "_")

    encoded = urllib.parse.quote(name, safe="")
    md5     = hashlib.md5(name.encode("utf-8")).hexdigest()
    a, ab   = md5[0], md5[0:2]
    ext     = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    base    = (f"https://upload.wikimedia.org/wikipedia/commons/thumb"
               f"/{a}/{ab}/{encoded}/{width}px-{encoded}")
    # SVG・TIF・WEBP はラスタライズ済み PNG サムネイルを要求
    if ext in ("svg", "tif", "tiff", "webp"):
        return base + ".png"
    return base


# ─────────────────────────────────────────────────────────────────
#  種数の事前推定
# ─────────────────────────────────────────────────────────────────

def estimate_species_count(root_qid: str) -> int:
    """P171+ COUNT（タイムアウト25秒）で総種数を推定する。"""
    pprint("  🔢 総種数を推定中（最大25秒）…")
    q = f"""
SELECT (COUNT(?sp) AS ?c) WHERE {{
  ?sp wdt:P171+ wd:{root_qid} ;
      wdt:P105  wd:Q7432 .
}}"""
    rows = sparql(q, timeout=25, silent=True)
    if rows:
        try:
            n = int(rows[0]["c"]["value"])
            if n > 0:
                pprint(f"  ✓  推定総種数: {n:,}種")
                return n
        except Exception:
            pass
    pprint("  ℹ  種数推定タイムアウト → 進捗は件数ベースで表示します")
    return 0

# ─────────────────────────────────────────────────────────────────
#  Phase 1: ルート〜split_rank まで BFS
# ─────────────────────────────────────────────────────────────────

def fetch_phase1(root_node: dict, split_rank: str) -> tuple[dict, dict]:
    """
    root_node を起点に split_rank まで BFS する（バッチ取得対応）。
    キューから最大 BATCH_PARENT_SIZE 件をまとめて1クエリで取得する。
    戻り値: (root_node（子を埋めた状態）, nodes_dict)
    """
    _stats["phase1_start"] = time.time()
    stop_idx = rank_index(split_rank)
    root_qid = root_node["id"]
    nodes    = {root_qid: root_node}
    queue    = deque([root_qid])
    visited  = {root_qid}

    while queue:
        # キューから stop_idx 未満のノードを最大 BATCH_PARENT_SIZE 件取り出す
        batch_qids = []
        while queue and len(batch_qids) < BATCH_PARENT_SIZE:
            qid = queue.popleft()
            if rank_index(nodes[qid]["rank"]) < stop_idx:
                batch_qids.append(qid)
            # stop_idx 以上のノードはスキップ（子を取る必要がない）

        if not batch_qids:
            continue

        pprint(f"  📦 バッチ取得: {len(batch_qids)} ノード")
        batch_result = get_batch_children(batch_qids)
        _stats["sleep_total"] += 0.8
        time.sleep(0.8)

        for parent_qid in batch_qids:
            parent_node = nodes[parent_qid]
            parent_rank = parent_node["rank"]
            rows        = batch_result.get(parent_qid, [])
            indent      = "  " * min(rank_index(parent_rank) + 1, 6)
            pprint(fmt_node(indent, parent_qid, parent_node["name"],
                            parent_node.get("ja", ""), parent_rank)
                   + f"  → {len(rows)}件")

            for row in rows:
                node = _parse_child_row(row, parent_rank)
                if not node or node["id"] in visited:
                    continue
                visited.add(node["id"])
                nodes[node["id"]] = node
                parent_node["children"].append(node)

                ci = rank_index(node["rank"])
                pprint(fmt_node("  " * min(ci + 2, 8), node["id"],
                                node["name"], node["ja"], node["rank"]))
                if ci < stop_idx:
                    queue.append(node["id"])

    _stats["phase1_elapsed"] = time.time() - _stats["phase1_start"]
    _sort_children(root_node)
    return root_node, nodes


# ─────────────────────────────────────────────────────────────────
#  子ノード補完: 学名プレフィックス（A）+ GBIF API（B）
# ─────────────────────────────────────────────────────────────────

# 補完戦略の記録値（ノードの fetch_strategy フィールドに格納）
STRATEGY_P171       = "p171"         # 通常取得（Wikidata P171）
STRATEGY_PREFIX     = "prefix"       # A補完: 学名プレフィックス
STRATEGY_GBIF       = "gbif"         # B補完: GBIF API
STRATEGY_INCOMPLETE = "incomplete"   # 全手段失敗

# 属レベルより下のランクを補完対象とする
_SUPPLEMENT_RANKS = {"genus", "subgenus"}


def _supplement_by_prefix(
    parent_qid: str,
    parent_name: str,
    parent_rank: str,
    visited: set,
) -> list[dict]:
    """
    アプローチA: 学名プレフィックスで子を補完する。
    属名 "Corvus" → STRSTARTS(?name, "Corvus ") で二項名を取得。
    P171 未登録の種を Wikidata から直接探す。
    """
    genus_name = parent_name.strip()
    if not genus_name:
        return []
    prefix = genus_name + " "
    q = f"""
SELECT DISTINCT ?child ?name ?rank ?jaName ?img WHERE {{
  ?child wdt:P225 ?name .
  FILTER(STRSTARTS(?name, "{prefix}"))
  OPTIONAL {{ ?child wdt:P105 ?rank }}
  OPTIONAL {{ ?child wdt:P1843 ?jaName . FILTER(LANG(?jaName) = "ja") }}
  OPTIONAL {{ ?child wdt:P18  ?img }}
}}
LIMIT 300
"""
    rows = sparql(q, timeout=30, silent=True)
    nodes = []
    for row in rows:
        node = _parse_child_row(row, parent_rank)
        if not node or node["id"] in visited:
            continue
        node["fetch_strategy"] = STRATEGY_PREFIX
        nodes.append(node)
    return nodes


def _supplement_by_gbif(
    parent_qid: str,
    parent_name: str,
    parent_rank: str,
    visited: set,
) -> list[dict]:
    """
    アプローチB: GBIF API から子を補完する。

    手順:
      1. Wikidata P846（GBIF taxon ID）を取得
      2. GBIF /v1/species/{key}/children を呼ぶ
      3. 各子の canonicalName で Wikidata QID を逆引き（wdt:P846）
      4. QID が取れれば通常ノードとして追加、取れなければ GBIF 情報のみで仮ノードを作成
    """
    # 1. Wikidata から GBIF ID を取得
    q_gbif = f"""
SELECT ?gbifId WHERE {{
  wd:{parent_qid} wdt:P846 ?gbifId .
}} LIMIT 1
"""
    rows = sparql(q_gbif, timeout=15, silent=True)
    if not rows:
        return []
    gbif_id = rows[0].get("gbifId", {}).get("value", "")
    if not gbif_id:
        return []

    # 2. GBIF API で子ノードを取得
    try:
        r = get_session().get(
            f"https://api.gbif.org/v1/species/{gbif_id}/children",
            params={"limit": 300},
            timeout=20,
        )
        if r.status_code != 200:
            return []
        gbif_children = r.json().get("results", [])
    except Exception as e:
        pprint(f"    ⚠  GBIF API エラー ({e})")
        return []

    if not gbif_children:
        return []

    # 3. 各 GBIF 子の canonicalName で Wikidata QID を逆引き
    #    まとめて1クエリにする（UNION で最大20件ずつ）
    nodes = []
    BATCH = 20
    for i in range(0, len(gbif_children), BATCH):
        batch = gbif_children[i : i + BATCH]
        # canonicalName → Wikidata QID を一括検索
        name_filter = " ".join(
            f'"{c["canonicalName"]}"' for c in batch if c.get("canonicalName")
        )
        if not name_filter:
            continue
        q_wikidata = f"""
SELECT ?child ?name ?rank ?jaName ?img ?gbifId ?iucn WHERE {{
  ?child wdt:P225 ?name .
  FILTER(?name IN ({", ".join(f'"{c["canonicalName"]}"'
                              for c in batch if c.get("canonicalName"))}))
  OPTIONAL {{ ?child wdt:P105 ?rank }}
  OPTIONAL {{ ?child wdt:P1843 ?jaName . FILTER(LANG(?jaName) = "ja") }}
  OPTIONAL {{ ?child wdt:P18  ?img }}
  OPTIONAL {{ ?child wdt:P846 ?gbifId }}
  OPTIONAL {{ ?child wdt:P141 ?iucn }}
}}
"""
        wikidata_rows = sparql(q_wikidata, timeout=30, silent=True)
        # canonicalName → Wikidata ノード の辞書
        wd_by_name: dict[str, dict] = {}
        for row in wikidata_rows:
            node = _parse_child_row(row, parent_rank)
            if node:
                node["fetch_strategy"] = STRATEGY_GBIF
                wd_by_name[node["name"]] = node

        # Wikidata に存在しないものは GBIF 情報のみで仮ノードを作成
        for gc in batch:
            cname = gc.get("canonicalName", "")
            if not cname:
                continue
            if cname in wd_by_name:
                node = wd_by_name[cname]
                # Wikidata P141 がなければ GBIF の iucn で補完
                if not node.get("iucn"):
                    gbif_iucn = GBIF_IUCN_MAP.get(
                        gc.get("iucnRedListCategory", ""), "")
                    if gbif_iucn:
                        node["iucn"] = gbif_iucn
            else:
                # Wikidata QID なし → GBIF キーを ID として仮ノード
                gbif_key = str(gc.get("key", ""))
                if not gbif_key:
                    continue
                fake_qid  = f"GBIF:{gbif_key}"
                child_rank = gc.get("rank", "SPECIES").lower()
                child_rank = RANK_MAP.get(child_rank, child_rank)
                gbif_iucn = GBIF_IUCN_MAP.get(
                    gc.get("iucnRedListCategory", ""), "")
                node = {
                    "id":             fake_qid,
                    "name":           cname,
                    "ja":             "",
                    "rank":           child_rank,
                    "wiki_url":       f"https://www.gbif.org/species/{gbif_key}",
                    "fetch_strategy": STRATEGY_GBIF,
                    "children":       [],
                }
                if gbif_iucn:
                    node["iucn"] = gbif_iucn
            if node["id"] not in visited:
                nodes.append(node)

    return nodes


def get_children_with_supplement(
    parent_node: dict,
    visited: set,
    stop_rank: str,
) -> tuple[list[dict], str]:
    """
    P171 直接 → P171+ 推移的閉包 の順に子を取得する。

    P171+ は亜属・亜科など中間ノードを経由する場合でも全子孫を取得できる。
    P171 と P171+ で重複した場合は visited で除外される。

    戻り値: (nodes, strategy)
    """
    parent_qid  = parent_node["id"]
    parent_name = parent_node["name"]
    parent_rank = parent_node["rank"]

    # ── ① Wikidata P171 直接（単体クエリ：補完フロー用）─────────────
    _stats["single_queries"] += 1
    rows = get_direct_children(parent_qid)
    nodes_p171 = []
    if rows:
        for row in rows:
            node = _parse_child_row(row, parent_rank)
            if node and node["id"] not in visited:
                node.setdefault("fetch_strategy", STRATEGY_P171)
                nodes_p171.append(node)

    if nodes_p171:
        return nodes_p171, STRATEGY_P171

    # P171 で子が0件かつ補完対象ランクのみ P171+ を試みる
    if parent_rank not in _SUPPLEMENT_RANKS:
        return [], STRATEGY_P171

    # ── ② P171+ 推移的閉包（亜属経由などを捕捉）────────────────────
    rows_t = get_transitive_children(parent_qid, stop_rank)
    nodes_t = []
    if rows_t:
        for row in rows_t:
            node = _parse_child_row(row, parent_rank)
            if node and node["id"] not in visited:
                node["fetch_strategy"] = STRATEGY_PREFIX  # 推移的補完
                nodes_t.append(node)

    if nodes_t:
        pprint(f"    ✅  P171+ 推移補完: {len(nodes_t)}件 [{parent_qid}] {parent_name}")
        return nodes_t, STRATEGY_PREFIX

    # ── ③ 全手段失敗 ──────────────────────────────────────────────
    pprint(f"    ⚠  取得失敗 [{parent_qid}] {parent_name} — データ不完全")
    parent_node["fetch_strategy"] = STRATEGY_INCOMPLETE
    return [], STRATEGY_INCOMPLETE

# ─────────────────────────────────────────────────────────────────
#  Phase 2: split_rank ノードごとにサブBFS（進捗バー付き）
# ─────────────────────────────────────────────────────────────────

def _register_children(
    child_rows: list, parent_node: dict, depth: int,
    nodes_dict: dict, visited: set, stop_idx: int,
    queue: deque, count_ref: list, strategy: str = STRATEGY_P171,
) -> None:
    """取得済み行リストをノード辞書へ登録してキューに積む（共通処理）。"""
    parent_rank = parent_node["rank"]
    for row in child_rows:
        node = _parse_child_row(row, parent_rank)
        if not node or node["id"] in nodes_dict or node["id"] in visited:
            continue
        node.setdefault("fetch_strategy", strategy)
        visited.add(node["id"])
        nodes_dict[node["id"]] = node
        parent_node["children"].append(node)
        ci = rank_index(node["rank"])
        mark = (
            "  [A]" if node.get("fetch_strategy") == STRATEGY_PREFIX
            else "  [B]" if node.get("fetch_strategy") == STRATEGY_GBIF
            else ""
        )
        pprint(fmt_node("  " * min(depth + 1, 8), node["id"],
                        node["name"], node["ja"], node["rank"]) + mark)
        if is_leaf_rank(node["rank"]) or ci >= stop_idx:
            count_ref[0] += 1
        else:
            queue.append((node["id"], depth))


def _bfs_subtree(root_node: dict, nodes_dict: dict, stop_rank: str) -> int:
    """
    root_node 以下を stop_rank まで BFS（バッチ取得対応）。

    ① キューから最大 BATCH_PARENT_SIZE 件をまとめてバッチ取得
    ② バッチで 0件だった属のみ get_children_with_supplement() で補完
    取得した末端ノード数を返す。
    """
    stop_idx = rank_index(stop_rank)
    queue    = deque([(root_node["id"], rank_index(root_node["rank"]))])
    visited  = {root_node["id"]}
    count    = [0]   # list で参照渡し

    while queue:
        visited |= nodes_dict.keys()

        # stop_idx 未満のノードを最大 BATCH_PARENT_SIZE 件取り出す
        batch: list[tuple[str, int]] = []
        while queue and len(batch) < BATCH_PARENT_SIZE:
            qid, depth = queue.popleft()
            nd = nodes_dict.get(qid)
            if nd and rank_index(nd["rank"]) < stop_idx:
                batch.append((qid, depth))

        if not batch:
            continue

        # ── ① バッチ取得 ────────────────────────────────────────
        batch_qids   = [qid for qid, _ in batch]
        batch_result = get_batch_children(batch_qids)
        _stats["sleep_total"] += 0.8
        time.sleep(0.8)

        need_supplement: list[tuple[str, int]] = []

        for parent_qid, depth in batch:
            parent_node = nodes_dict[parent_qid]
            rows        = batch_result.get(parent_qid, [])

            if rows:
                _register_children(rows, parent_node, depth,
                                   nodes_dict, visited, stop_idx,
                                   queue, count)
            else:
                # バッチで 0件 → 補完候補としてスタック
                need_supplement.append((parent_qid, depth))

        # ── ② 補完フロー（0件だった属のみ）────────────────────
        for parent_qid, depth in need_supplement:
            parent_node = nodes_dict[parent_qid]
            child_nodes, strategy = get_children_with_supplement(
                parent_node, visited, stop_rank
            )
            if child_nodes:
                for node in child_nodes:
                    if node["id"] in nodes_dict or node["id"] in visited:
                        continue
                    visited.add(node["id"])
                    nodes_dict[node["id"]] = node
                    parent_node["children"].append(node)
                    ci = rank_index(node["rank"])
                    mark = (
                        "  [A]" if node.get("fetch_strategy") == STRATEGY_PREFIX
                        else "  [B]" if node.get("fetch_strategy") == STRATEGY_GBIF
                        else ""
                    )
                    pprint(fmt_node("  " * min(depth + 1, 8), node["id"],
                                    node["name"], node["ja"], node["rank"]) + mark)
                    if is_leaf_rank(node["rank"]) or ci >= stop_idx:
                        count[0] += 1
                    else:
                        queue.append((node["id"], depth))
            _stats["sleep_total"] += 0.8
            time.sleep(0.8)

    return count[0]

def fetch_phase2(root_node: dict, nodes_dict: dict,
                 split_rank: str, stop_rank: str,
                 total_sp: int) -> None:
    """
    Phase 1 で取得した split_rank ノードを列挙し、
    それぞれ stop_rank までサブBFS する。進捗バーを表示。
    """
    # split_rank のノードを収集
    split_nodes: list[dict] = []
    def _collect(nd: dict):
        if nd["rank"] == split_rank:
            split_nodes.append(nd)
        for c in nd["children"]:
            _collect(c)
    _collect(root_node)

    # split_rank ノードが0件 = root 自体が split_rank 以下
    # → root を直接サブBFS する
    if not split_nodes:
        split_nodes = [root_node]

    total_p = len(split_nodes)
    done_p  = 0
    done_sp = 0
    unit_sp = "種" if stop_rank == "species" else "件"

    _stats["phase2_start"] = time.time()
    visited_before = set(nodes_dict.keys())  # ワンショット差分計算用の初期値
    pprint(f"\n  📋 Phase 2: {total_p} {split_rank} の子孫を取得します"
           f"  （→ {stop_rank}）")
    if total_sp > 0:
        pprint(f"  📊 参考: 推定総種数 ~{total_sp:,}種  ※バーは科の進捗を表示\n")

    for nd in split_nodes:
        bar_update(done_p, total_p, done_sp, total_sp,
                   f"{nd['name']} [{nd['id']}] 取得開始…")

        # ── ① P171+ ワンショット試行 ──────────────────────────
        before = len(nodes_dict)
        ok = fetch_subtree_oneshot(nd, nodes_dict, stop_rank)
        if ok:
            _stats["oneshot_hits"] += 1
            n = sum(
                1 for qid, node in nodes_dict.items()
                if qid not in visited_before
                and (is_leaf_rank(node["rank"])
                     or rank_index(node["rank"]) >= rank_index(stop_rank))
            )
        else:
            # ── ② フォールバック: バッチBFS ───────────────────
            _stats["oneshot_miss"] += 1
            pprint(f"  ↩  ワンショット失敗 → バッチBFS にフォールバック [{nd['id']}]")
            n = _bfs_subtree(nd, nodes_dict, stop_rank)

        visited_before = set(nodes_dict.keys())  # 次の科の差分計算用
        done_p  += 1
        done_sp += n

        pprint(
            f"  ✓  [{nd['id']}] {nd['name']}"
            + (f" / {nd['ja']}" if nd.get("ja") else "")
            + f"  {n:,}{unit_sp}  ({_elapsed()})"
        )
        bar_update(done_p, total_p, done_sp, total_sp, nd["name"])

    _stats["phase2_elapsed"] = time.time() - _stats.get("phase2_start", time.time())
    bar_done()
    pprint(f"\n  📊 Phase 2 完了: {done_sp:,}{unit_sp} / {done_p}{split_rank}  ({_elapsed()})")
    print_stats()
    _sort_children(root_node)

# ─────────────────────────────────────────────────────────────────
#  ユーティリティ
# ─────────────────────────────────────────────────────────────────

def _sort_children(nd: dict):
    nd["children"].sort(key=lambda x: (rank_index(x["rank"]), x["name"]))
    for c in nd["children"]:
        _sort_children(c)

def _walk(nd: dict, fn):
    fn(nd)
    for c in nd.get("children", []): _walk(c, fn)

# ─────────────────────────────────────────────────────────────────
#  接続診断
# ─────────────────────────────────────────────────────────────────

def run_test(proxy=None):
    print("\n🔬 接続診断\n")
    print("1️⃣  SSL設定の自動検出…")
    init_session(proxy)

    print("\n2️⃣  Wikidata Entity API 疎通確認（Passeriformes = Q25341）…")
    try:
        r = get_session().get(
            "https://www.wikidata.org/wiki/Special:EntityData/Q25341.json",
            timeout=15)
        e  = r.json().get("entities", {}).get("Q25341", {})
        ja = e.get("labels", {}).get("ja", {}).get("value", "?")
        en = e.get("labels", {}).get("en", {}).get("value", "?")
        print(f"   Q25341 = 「{ja}」/ {en} ✓")
    except Exception as ex:
        print(f"   ❌ {ex}"); return

    print("\n3️⃣  SPARQL：Passeriformes の直接の子を取得…")
    q = """
SELECT ?child ?childLabel ?name ?rank WHERE {
  ?child wdt:P171 wd:Q25341 ; wdt:P225 ?name .
  OPTIONAL { ?child wdt:P105 ?rank }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ja,en" }
} LIMIT 8"""
    rows = sparql(q, "直接の子", timeout=45)
    if not rows:
        print("   ❌ 子ノードが取得できません"); return
    for row in rows:
        n  = row.get("name",       {}).get("value", "?")
        ja = row.get("childLabel", {}).get("value", "")
        rq = row.get("rank",       {}).get("value", "").rsplit("/", 1)[-1]
        print(f"   [{rq:12s}] {n:<35} {ja}")

    print("\n4️⃣  taxon 検索テスト（Corvidae）…")
    hits = search_taxon("Corvidae", limit=3)
    for h in hits:
        print(f"   [{h['qid']:12s}] {h['label']:<25}  {h['desc'][:50]}")

    print("\n✅  診断完了 — python taxa_tree.py --qid Q25341 --fast で実行できます")