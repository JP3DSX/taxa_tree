#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
module/taxa_fetch.py  ─  データ取得・モデル構築モジュール
================================================================
Wikidata SPARQL から任意の分類群を BFS で取得し、
ツリー辞書（dict）を返す。出力先・ファイル名は呼び出し元が管理する。

公開 API:
    init_session(proxy)        セッション初期化（SSL自動検出）
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
        "cur": "", "active": False, "unit": "種"}

def _bar_line():
    b = _bar
    cols   = shutil.get_terminal_size((100, 24)).columns
    pct    = b["done"] / b["total"] if b["total"] > 0 else 0
    bw     = max(10, min(35, cols - 60))
    filled = int(bw * pct)
    bar    = "█" * filled + "░" * (bw - filled)
    tot_s  = f"~{b['total']:,}" if b["total"] > 0 else "?"
    line   = (f"  [{bar}] {b['done']:,}/{tot_s}{b['unit']}  "
              f"P:{b['done_p']}/{b['total_p']}  {pct*100:.1f}%  {_elapsed()}")
    if b["cur"]:
        avail = cols - len(line) - 5
        if avail > 4:
            line += f"  ← {b['cur'][:avail]}"
    return line[:cols - 1]

def _redraw():
    if _bar["active"]:
        sys.stdout.write(f"\r\033[K{_bar_line()}")
        sys.stdout.flush()

def bar_update(done, total, done_p, total_p, cur="", unit="種"):
    _bar.update(done=done, total=total, done_p=done_p, total_p=total_p,
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

def init_session(proxy=None):
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

    verify = True
    for v in [True, False]:
        try:
            r = requests.get("https://www.wikidata.org/", headers=HEADERS,
                             timeout=12, verify=v, proxies=proxy_dict)
            if r.status_code < 500:
                verify = v; break
        except requests.exceptions.SSLError:
            if v: continue
        except Exception:
            pass

    s = requests.Session()
    s.verify  = verify
    s.headers.update(HEADERS)
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
    records = []
    offset  = 0
    while True:
        q = f"""
SELECT DISTINCT ?child ?childLabel ?name ?rank ?jaName WHERE {{
  ?child wdt:P171 wd:{parent_qid} ;
         wdt:P225 ?name .
  OPTIONAL {{ ?child wdt:P105 ?rank }}
  OPTIONAL {{ ?child wdt:P1843 ?jaName . FILTER(LANG(?jaName) = "ja") }}
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
        time.sleep(1.0)
    return records

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
    return node

# ─────────────────────────────────────────────────────────────────
#  Wikimedia Commons 画像 URL 解決
# ─────────────────────────────────────────────────────────────────

def resolve_image_url(filename: str, width: int = 120) -> str:
    """
    Wikimedia Thumbnail API でファイル名から直接の CDN URL を取得する。
    Special:FilePath はリダイレクトのため SVG <image> で動作しない場合があり、
    API で thumb URL を直接取得することで確実に表示できる。

    API: https://commons.wikimedia.org/w/api.php
         action=query & titles=File:xxx & prop=imageinfo & iiprop=url
         & iiurlwidth=120
    """
    if not filename:
        return ""
    # "File:" プレフィックスを正規化
    name = filename
    if name.lower().startswith("file:"):
        name = name[5:]
    name = name.replace(" ", "_")
    title = f"File:{name}"
    try:
        r = get_session().get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action":    "query",
                "titles":    title,
                "prop":      "imageinfo",
                "iiprop":    "url",
                "iiurlwidth": str(width),
                "format":    "json",
            },
            timeout=10,
        )
        pages = r.json().get("query", {}).get("pages", {})
        for page in pages.values():
            ii = page.get("imageinfo", [])
            if ii and ii[0].get("thumburl"):
                return ii[0]["thumburl"]
    except Exception:
        pass
    # API 失敗時のフォールバック: Special:FilePath
    encoded = urllib.parse.quote(name, safe="")
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{encoded}?width={width}"


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
    root_node を起点に split_rank まで BFS する。
    戻り値: (root_node（子を埋めた状態）, nodes_dict)
    """
    stop_idx = rank_index(split_rank)
    root_qid = root_node["id"]
    nodes    = {root_qid: root_node}
    queue    = deque([root_qid])
    visited  = {root_qid}

    while queue:
        parent_qid  = queue.popleft()
        parent_node = nodes[parent_qid]
        parent_rank = parent_node["rank"]
        parent_idx  = rank_index(parent_rank)

        if parent_idx >= stop_idx:
            continue

        indent = "  " * min(parent_idx + 1, 6)
        pja    = parent_node.get("ja", "")
        pprint(fmt_node(indent, parent_qid, parent_node["name"], pja, parent_rank)
               + "  ▶取得中…")

        rows = get_direct_children(parent_qid)
        pprint(f"{indent}{'':12}   → {len(rows)}件")

        for row in rows:
            node = _parse_child_row(row, parent_rank)
            if not node or node["id"] in visited: continue
            visited.add(node["id"])
            nodes[node["id"]] = node
            parent_node["children"].append(node)

            ci = rank_index(node["rank"])
            pprint(fmt_node("  " * min(ci + 2, 8), node["id"],
                            node["name"], node["ja"], node["rank"]))
            if ci < stop_idx:
                queue.append(node["id"])

        time.sleep(0.8)

    _sort_children(root_node)
    return root_node, nodes

# ─────────────────────────────────────────────────────────────────
#  Phase 2: split_rank ノードごとにサブBFS（進捗バー付き）
# ─────────────────────────────────────────────────────────────────

def _bfs_subtree(root_node: dict, nodes_dict: dict, stop_rank: str) -> int:
    """root_node 以下を stop_rank まで BFS。取得した末端ノード数を返す。"""
    stop_idx  = rank_index(stop_rank)
    root_ridx = rank_index(root_node["rank"])
    queue     = deque([(root_node["id"], root_ridx)])
    visited   = {root_node["id"]}
    count     = 0

    while queue:
        parent_qid, parent_depth = queue.popleft()
        parent_node = nodes_dict[parent_qid]
        parent_rank = parent_node["rank"]
        parent_idx  = rank_index(parent_rank)
        if parent_idx >= stop_idx: continue

        rows = get_direct_children(parent_qid)
        for row in rows:
            node = _parse_child_row(row, parent_rank)
            if not node or node["id"] in visited: continue
            visited.add(node["id"])

            ci    = rank_index(node["rank"])
            depth = parent_depth + 1
            nodes_dict[node["id"]] = node
            parent_node["children"].append(node)

            pprint(fmt_node("  " * min(depth + 1, 8), node["id"],
                            node["name"], node["ja"], node["rank"]))

            if is_leaf_rank(node["rank"]):
                count += 1
            elif ci < stop_idx:
                queue.append((node["id"], depth))
            else:
                count += 1   # stop_rank に到達

        time.sleep(0.8)

    return count

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
    unit    = "種" if stop_rank == "species" else "件"

    pprint(f"\n  📋 Phase 2: {total_p}ノード の子孫を取得します"
           f"  （{split_rank} → {stop_rank}）")
    if total_sp > 0:
        pprint(f"  📊 推定総種数: ~{total_sp:,}種\n")

    for nd in split_nodes:
        bar_update(done_sp, total_sp, done_p, total_p,
                   f"{nd['name']} [{nd['id']}] 取得開始…", unit)

        n = _bfs_subtree(nd, nodes_dict, stop_rank)
        done_p  += 1
        done_sp += n

        pprint(
            f"  ✓  [{nd['id']}] {nd['name']}"
            + (f" / {nd['ja']}" if nd.get("ja") else "")
            + f"  {n:,}{unit}  ({_elapsed()})"
        )
        bar_update(done_sp, total_sp, done_p, total_p, nd["name"], unit)

    bar_done()
    pprint(f"\n  📊 Phase 2 完了: {done_sp:,}{unit} / {done_p}ノード  ({_elapsed()})")
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

# ─────────────────────────────────────────────────────────────────
#  HTML テンプレート
# ─────────────────────────────────────────────────────────────────