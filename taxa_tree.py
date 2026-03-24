#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
taxa_tree.py  ─  生物分類 汎用系統図ジェネレーター v3
====================================================================
Wikidata SPARQL から任意の分類群を BFS で取得し、
単体配布可能なインタラクティブ HTML 系統図を生成します。

【対応範囲】
  鳥類・哺乳類・植物・昆虫・魚類・菌類など生物分類全般

【使い方】
  pip install requests

  # QID で直接指定
  python taxa_tree.py --qid Q25341          # スズメ目
  python taxa_tree.py --qid Q23038          # タカ目
  python taxa_tree.py --qid Q5113           # スズメ科
  python taxa_tree.py --qid Q10908          # 哺乳綱
  python taxa_tree.py --qid Q756            # バラ科

  # 学名または和名で検索（候補一覧から選択）
  python taxa_tree.py --taxon "Passeriformes"
  python taxa_tree.py --taxon "カラス科"
  python taxa_tree.py --taxon "Rosa"

  # オプション
  python taxa_tree.py --qid Q25341 --fast          # 科レベルまで（高速）
  python taxa_tree.py --qid Q25341 --split genus   # 属レベルで2Phase分割
  python taxa_tree.py --qid Q25341 --cached        # キャッシュ再利用
  python taxa_tree.py --qid Q25341 --output my.html
  python taxa_tree.py --qid Q25341 --proxy http://proxy.example.com:8080
  python taxa_tree.py --test                       # 接続診断

【環境変数（Windows プロキシ環境）】
  set HTTPS_PROXY=http://proxy.example.com:8080
"""

import argparse
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
    "User-Agent": "TaxaTreeBot/1.0 (yamamoto.yutaka@jp.panasonic.com)",
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
OUTPUT_DIR = "result"

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

    # P18（画像）→ Wikimedia Commons サムネイル URL を生成
    image_url = ""
    img_val   = row.get("img", {}).get("value", "")
    if img_val:
        # Wikidata P18 は "http://commons.wikimedia.org/wiki/Special:FilePath/Xxx.jpg"
        # または単純に "File:Xxx.jpg" 形式で返ることがある
        if "Special:FilePath/" in img_val:
            filename = img_val.split("Special:FilePath/")[-1]
            filename = urllib.parse.unquote(filename)
            image_url = commons_thumb_url(filename, width=120)
        elif img_val.startswith("File:") or img_val.startswith("file:"):
            image_url = commons_thumb_url(img_val, width=120)

    node = {
        "id":       child_qid,
        "name":     sci,
        "ja":       ja if ja != sci else "",
        "rank":     child_rank,
        "children": [],
    }
    if image_url:
        node["image_url"] = image_url
    return node

# ─────────────────────────────────────────────────────────────────
#  Wikimedia Commons 画像 URL 生成
# ─────────────────────────────────────────────────────────────────

def commons_thumb_url(filename: str, width: int = 120) -> str:
    """
    Wikimedia Commons のファイル名からサムネイル URL を生成する。
    P18 の値は "File:Corvus_corax.jpg" 形式で返ってくる。
    Thumb URL 形式:
      https://upload.wikimedia.org/wikipedia/commons/thumb/<md5[0]>/<md5[0:2]>/<encoded>/<width>px-<encoded>
    ただし md5 計算は不要で Special:FilePath 経由でリダイレクトさせる方が確実。
    ここでは API 経由でサムネイル URL を取得するのではなく、
    commons の URL 規則を直接構築する（実績のある方式）。
    """
    # "File:" プレフィックスを除去し、スペースを _ に統一
    name = filename
    if name.startswith("File:") or name.startswith("file:"):
        name = name[5:]
    name = name.replace(" ", "_")
    # URL エンコード（スラッシュは変換しない）
    encoded = urllib.parse.quote(name, safe="")
    # MD5 ハッシュで CDN パスを決定
    md5 = hashlib.md5(name.encode("utf-8")).hexdigest()
    a, ab = md5[0], md5[0:2]
    return (f"https://upload.wikimedia.org/wikipedia/commons/thumb"
            f"/{a}/{ab}/{encoded}/{width}px-{encoded}")

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

HTML = r"""<!DOCTYPE html>
<html lang="ja" data-theme="dark"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ 系統図</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d1117;--bg2:#161b22;--bg3:#21262d;
  --txt:#e6edf3;--txt2:#8b949e;--txt3:#555d6b;
  --brd:#30363d;--hl:#f0b429;--foot-bg:rgba(13,17,23,.88);
  --c-domain:#f472b6;--c-kingdom:#e879f9;--c-phylum:#c084fc;
  --c-class:#a78bfa;--c-order:#818cf8;--c-suborder:#34d399;
  --c-infraorder:#fb923c;--c-superfamily:#f87171;--c-family:#60a5fa;
  --c-subfamily:#38bdf8;--c-tribe:#4ade80;--c-genus:#a78bfa;
  --c-species:#86efac;--c-subspecies:#6ee7b7;--c-variety:#d9f99d;
  --c-unknown:#6b7280;
}
[data-theme="light"]{
  --bg:#ffffff;--bg2:#f6f8fa;--bg3:#eaeef2;
  --txt:#1f2328;--txt2:#444c56;--txt3:#768390;
  --brd:#d0d7de;--hl:#b45309;--foot-bg:rgba(246,248,250,.92);
  --c-domain:#9d174d;--c-kingdom:#86198f;--c-phylum:#7e22ce;
  --c-class:#6d28d9;--c-order:#4338ca;--c-suborder:#065f46;
  --c-infraorder:#9a3412;--c-superfamily:#991b1b;--c-family:#1d4ed8;
  --c-subfamily:#0369a1;--c-tribe:#166534;--c-genus:#6d28d9;
  --c-species:#15803d;--c-subspecies:#047857;--c-variety:#3f6212;
  --c-unknown:#374151;
}
html,body{height:100%;overflow:hidden;background:var(--bg);color:var(--txt);
  font-family:'Hiragino Sans','Yu Gothic',Meiryo,'Noto Sans JP',system-ui,sans-serif;
  transition:background .2s,color .2s}
#hdr{display:flex;align-items:center;gap:6px;padding:6px 10px;
  background:var(--bg2);border-bottom:1px solid var(--brd);flex-wrap:wrap}
#ttl{font-size:13px;font-weight:600;white-space:nowrap}
#ttl em{font-style:italic;color:var(--txt2);font-size:11px;font-weight:400;margin-left:4px}
#srch{background:var(--bg3);border:1px solid var(--brd);color:var(--txt);
  border-radius:18px;padding:4px 11px;font-size:11px;width:140px;outline:none;
  transition:background .2s,border-color .15s}
#srch:focus{border-color:var(--hl)}#srch::placeholder{color:var(--txt3)}
.hb,.tb{background:transparent;border:1px solid var(--brd);color:var(--txt2);
  border-radius:13px;padding:3px 9px;font-size:11px;cursor:pointer;
  white-space:nowrap;transition:border-color .15s,color .15s,background .15s}
.hb:hover,.tb:hover{border-color:var(--txt2);color:var(--txt)}
.tb.active{border-color:var(--hl);color:var(--hl);background:rgba(240,180,41,.08)}
.ctrl{display:flex;gap:4px;padding-left:7px;border-left:1px solid var(--brd)}
#stat{font-size:11px;color:var(--txt3);margin-left:auto;white-space:nowrap;display:flex;gap:9px}
.sd{width:7px;height:7px;border-radius:50%;display:inline-block;margin-right:2px}
#leg{display:flex;gap:6px;flex-wrap:wrap;align-items:center;padding:3px 10px;
  background:var(--bg2);border-bottom:1px solid var(--brd);font-size:10px;color:var(--txt3)}
.li{display:flex;align-items:center;gap:3px}
.ld{width:7px;height:7px;border-radius:50%}
#main{overflow:hidden;height:calc(100vh - 64px);position:relative}
svg{width:100%;height:100%}
.lk{fill:none;stroke:var(--brd);stroke-width:.7}
.nd{cursor:pointer}
.nd circle.bg{stroke-width:1.5;transition:r .12s,opacity .15s}
.nd:hover circle.bg{filter:brightness(1.3)}
.nd .img-ring{fill:none;stroke-width:2;transition:stroke-width .12s,r .12s}
.nd:hover .img-ring{stroke-width:2.8}
.nd text{font-size:11px;fill:var(--txt);pointer-events:none;dominant-baseline:central}
.primary-lbl{font-style:italic;fill:var(--txt2)!important}
.secondary-lbl{font-size:9px;fill:var(--txt3)!important}
.nh circle.bg,.nh .img-ring{stroke:var(--hl)!important;stroke-width:2.5!important}
.nh text{fill:var(--hl)!important}
.nm{opacity:.1}
/* ツールチップ */
#tt{position:absolute;background:var(--bg2);border:1px solid var(--brd);
  border-radius:10px;padding:0;pointer-events:none;display:none;
  width:220px;z-index:50;overflow:hidden;box-shadow:0 8px 28px rgba(0,0,0,.35)}
#tt-img{width:220px;height:136px;object-fit:cover;display:block;background:var(--bg3)}
#tt-img.hidden{display:none}
#tt-ph{width:220px;height:136px;display:flex;align-items:center;justify-content:center;
  font-size:30px;background:var(--bg3)}
#tt-ph.hidden{display:none}
#tt-body{padding:9px 12px}
#tt-rank{font-size:10px;color:var(--txt3)}
#tt-name{font-weight:600;font-size:12px;font-style:italic;
  word-break:break-all;margin-top:1px}
#tt-ja{color:var(--txt2);font-size:11px;margin-top:1px}
#tt-meta{font-size:10px;color:var(--txt3);margin-top:5px;
  padding-top:5px;border-top:1px solid var(--brd);
  display:flex;justify-content:space-between;align-items:flex-end}
#tt-cnt{white-space:nowrap}
#tt-credit{font-size:9px;color:var(--txt3);overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap;max-width:130px;text-align:right}
#foot{position:absolute;bottom:7px;left:9px;font-size:10px;color:var(--txt3);
  background:var(--foot-bg);padding:4px 8px;border-radius:5px;
  border:1px solid var(--brd);line-height:1.8;pointer-events:none}
#ov{position:fixed;inset:0;background:rgba(13,17,23,.97);display:flex;
  flex-direction:column;align-items:center;justify-content:center;gap:11px;z-index:999}
#ov h2{font-size:16px}
#ov p{font-size:12px;color:var(--txt2);text-align:center;max-width:320px}
.pb{width:240px;height:3px;background:var(--bg3);border-radius:2px;overflow:hidden}
.pi{height:100%;background:var(--hl);border-radius:2px;width:0;transition:width .3s}
</style></head>
<body style="display:flex;flex-direction:column">
<div id="ov"><h2>🌿 系統図を準備中…</h2>
  <p id="om">データ解析中</p>
  <div class="pb"><div class="pi" id="pi"></div></div></div>
<div id="hdr">
  <div id="ttl"><em>__TITLE__</em> 系統図</div>
  <input id="srch" placeholder="検索…" oninput="doSrch(this.value)">
  <button class="hb" onclick="expandTo('family')">科まで</button>
  <button class="hb" onclick="expandTo('genus')">属まで</button>
  <button class="hb" onclick="expandTo('species')">全展開</button>
  <button class="hb" onclick="collapseAll()">折りたたむ</button>
  <button class="hb" onclick="fitV(false)">全体表示</button>
  <div class="ctrl">
    <button class="tb" id="btn-theme" onclick="toggleTheme()" title="テーマ切り替え">🌙</button>
  </div>
  <div class="ctrl">
    <button class="tb active" id="btn-ja" onclick="setLang('ja')" title="日本語優先">JA</button>
    <button class="tb"        id="btn-en" onclick="setLang('en')" title="英語優先">EN</button>
  </div>
  <div class="ctrl">
    <button class="tb active" id="btn-lr" onclick="setLayout('lr')" title="左→右">LR</button>
    <button class="tb"        id="btn-tb" onclick="setLayout('tb')" title="上→下">TB</button>
  </div>
  <div class="ctrl">
    <button class="tb active" id="btn-icon" onclick="toggleIcons()" title="画像アイコン ON/OFF">🖼</button>
  </div>
  <div id="stat"></div>
</div>
<div id="leg">
  <span>凡例：</span>
  <div class="li"><div class="ld" style="background:var(--c-order)"></div>目</div>
  <div class="li"><div class="ld" style="background:var(--c-family)"></div>科</div>
  <div class="li"><div class="ld" style="background:var(--c-genus)"></div>属</div>
  <div class="li"><div class="ld" style="background:var(--c-species)"></div>種</div>
  <div class="li"><div class="ld" style="background:var(--c-subspecies)"></div>亜種</div>
  <span style="margin-left:7px">▶クリックで展開 ／ ドラッグ・ホイールでナビ</span>
</div>
<div id="main">
  <svg id="tree"></svg>
  <div id="tt">
    <img id="tt-img" src="" alt=""
         onerror="this.classList.add('hidden');document.getElementById('tt-ph').classList.remove('hidden')">
    <div id="tt-ph" class="hidden">🌿</div>
    <div id="tt-body">
      <div id="tt-rank"></div>
      <div id="tt-name"></div>
      <div id="tt-ja"></div>
      <div id="tt-meta">
        <span id="tt-cnt"></span>
        <span id="tt-credit"></span>
      </div>
    </div>
  </div>
  <div id="foot">QID: __QID__ &nbsp;|&nbsp; 画像: Wikimedia Commons &nbsp;|&nbsp; 生成: __DATE__</div>
</div>
<script>
const DATA=__DATA__;
const RANK_ORD=["domain","kingdom","subkingdom","phylum","subphylum","superclass",
  "class","subclass","infraclass","superorder","order","suborder","infraorder",
  "superfamily","family","subfamily","tribe","subtribe","genus","subgenus",
  "species","subspecies","variety","form"];
const RC={domain:"var(--c-domain)",kingdom:"var(--c-kingdom)",phylum:"var(--c-phylum)",
  subphylum:"var(--c-phylum)",superclass:"var(--c-class)",class:"var(--c-class)",
  subclass:"var(--c-class)",infraclass:"var(--c-class)",
  superorder:"var(--c-order)",order:"var(--c-order)",suborder:"var(--c-suborder)",
  infraorder:"var(--c-infraorder)",superfamily:"var(--c-superfamily)",
  family:"var(--c-family)",subfamily:"var(--c-subfamily)",
  tribe:"var(--c-tribe)",subtribe:"var(--c-tribe)",
  genus:"var(--c-genus)",subgenus:"var(--c-genus)",
  species:"var(--c-species)",subspecies:"var(--c-subspecies)",
  variety:"var(--c-variety)",form:"var(--c-variety)",unknown:"var(--c-unknown)"};
const RR_BASE={domain:10,kingdom:9,phylum:8,subphylum:7,superclass:7,class:7,
  subclass:6,infraclass:6,superorder:6,order:6,suborder:5,infraorder:5,
  superfamily:5,family:4.5,subfamily:4,tribe:3.5,subtribe:3.5,
  genus:3,subgenus:3,species:2,subspecies:1.8,variety:1.8,form:1.8,unknown:2};
const IMG_R = 11;   // 画像アイコン半径(px)
const RJ={domain:"域",kingdom:"界",subkingdom:"亜界",phylum:"門",subphylum:"亜門",
  superclass:"上綱",class:"綱",subclass:"亜綱",infraclass:"下綱",
  superorder:"上目",order:"目",suborder:"亜目",infraorder:"下目",
  superfamily:"上科",family:"科",subfamily:"亜科",tribe:"族",subtribe:"亜族",
  genus:"属",subgenus:"亜属",species:"種",subspecies:"亜種",
  variety:"変種",form:"品種",unknown:"?"};

// ─── 状態 ────────────────────────────────────────────────────────
let langMode   = localStorage.getItem("taxa_lang")   || "ja";
let layoutMode = localStorage.getItem("taxa_layout") || "lr";
let showIcons  = localStorage.getItem("taxa_icons")  !== "0";

// 画像ありの種ノードに使う実効半径
function nodeR(d) {
  if (showIcons && d.data.image_url &&
      ["species","subspecies","variety","form"].includes(d.data.rank))
    return IMG_R;
  return RR_BASE[d.data.rank] || 2;
}
// テキスト X オフセット（画像ノードは半径が大きい分ずらす）
function textX(d) {
  const r  = nodeR(d);
  const lx = hk(d) ? -(r + 5) : (r + 5);
  return lx;
}

// ─── 言語ヘルパー ─────────────────────────────────────────────────
function getLabels(d) {
  const sci = d.data.name || "";
  const ja  = d.data.ja   || "";
  return langMode === "ja"
    ? { primary: ja || sci, secondary: ja ? sci : "" }
    : { primary: sci,       secondary: ja };
}

// ─── テキスト属性（LR / TB 共通ヘルパー） ─────────────────────────
function applyPrimaryAttrs(sel) {
  sel.attr("transform",    d => tbEnTransform(d, false))
     .attr("writing-mode", () => tbJaWritingMode())
     .attr("x",            d => layoutMode === "lr" ? textX(d) : (langMode === "ja" ? (hk(d) ? -4 : 4) : 0))
     .attr("y",            d => layoutMode !== "tb" ? null : (langMode === "ja" ? (hk(d) ? -nodeR(d)-3 : nodeR(d)+3) : nodeR(d)+2))
     .attr("dy",           () => layoutMode === "lr" ? "0em" : null)
     .attr("text-anchor",  d => primaryAnchor(d));
}
function applySecondaryAttrs(sel) {
  sel.attr("transform",    d => tbEnTransform(d, true))
     .attr("writing-mode", () => tbJaWritingMode())
     .attr("x",            d => layoutMode === "lr" ? textX(d) : (langMode === "ja" ? (hk(d) ? -14 : 14) : 0))
     .attr("y",            d => layoutMode !== "tb" ? null : (langMode === "ja" ? (hk(d) ? -nodeR(d)-3 : nodeR(d)+3) : nodeR(d)+14))
     .attr("dy",           () => layoutMode === "lr" ? "1.5em" : null)
     .attr("text-anchor",  d => primaryAnchor(d));
}
function tbEnTransform(d, isSec) {
  if (layoutMode !== "tb" || langMode !== "en") return null;
  return `rotate(-90,0,${isSec ? nodeR(d)+14 : nodeR(d)+2})`;
}
function tbJaWritingMode() {
  return (layoutMode === "tb" && langMode === "ja") ? "vertical-rl" : null;
}
function primaryAnchor(d) {
  if (layoutMode === "lr") return hk(d) ? "end" : "start";
  if (langMode === "ja")   return hk(d) ? "end" : "start";
  return hk(d) ? "start" : "end";
}

// ─── テーマ切り替え ───────────────────────────────────────────────
function toggleTheme() {
  const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  document.getElementById("btn-theme").textContent = next === "dark" ? "🌙" : "☀️";
  localStorage.setItem("taxa_theme", next);
}

// ─── 言語切り替え ─────────────────────────────────────────────────
function setLang(mode) {
  langMode = mode;
  localStorage.setItem("taxa_lang", mode);
  document.getElementById("btn-ja").classList.toggle("active", mode === "ja");
  document.getElementById("btn-en").classList.toggle("active", mode === "en");
  document.getElementById("srch").placeholder = mode === "ja" ? "検索…" : "Search…";
  if (layoutMode === "tb") update(root); else applyLangOnly();
}
function applyLangOnly() {
  g.selectAll(".nd").each(function(d) {
    const lb = getLabels(d);
    d3.select(this).select(".primary-lbl").text(lb.primary);
    d3.select(this).select(".secondary-lbl").text(lb.secondary);
  });
}

// ─── レイアウト切り替え ───────────────────────────────────────────
function setLayout(mode) {
  layoutMode = mode;
  localStorage.setItem("taxa_layout", mode);
  document.getElementById("btn-lr").classList.toggle("active", mode === "lr");
  document.getElementById("btn-tb").classList.toggle("active", mode === "tb");
  lay.nodeSize(layoutNodeSize());
  update(root);
  setTimeout(() => fitV(false), 260);
}
function layoutNodeSize() {
  return layoutMode === "lr" ? [18, 200] : [110, 75];
}

// ─── 画像アイコン切り替え ────────────────────────────────────────
function toggleIcons() {
  showIcons = !showIcons;
  localStorage.setItem("taxa_icons", showIcons ? "1" : "0");
  document.getElementById("btn-icon").classList.toggle("active", showIcons);
  update(root);
}

// ─── D3 セットアップ ─────────────────────────────────────────────
const svg    = d3.select("#tree");
const mainEl = document.getElementById("main");
const zm     = d3.zoom().scaleExtent([0.01, 5])
                 .on("zoom", e => g.attr("transform", e.transform));
svg.call(zm).on("dblclick.zoom", null);
const g    = svg.append("g");
const defs = svg.append("defs");
defs.append("marker").attr("id","arr").attr("viewBox","0 -3 7 6")
  .attr("refX",7).attr("markerWidth",5).attr("markerHeight",5).attr("orient","auto")
  .append("path").attr("d","M0,-3L7,0L0,3").attr("fill","var(--brd)");
const lay  = d3.tree().nodeSize(layoutNodeSize());
let root;

const prog = (p, m) => {
  document.getElementById("pi").style.width = p + "%";
  if (m) document.getElementById("om").textContent = m;
};

// ─── 初期化 ─────────────────────────────────────────────────────
function init() {
  const savedTheme  = localStorage.getItem("taxa_theme")  || "dark";
  const savedLayout = localStorage.getItem("taxa_layout") || "lr";
  langMode   = localStorage.getItem("taxa_lang")   || "ja";
  layoutMode = savedLayout;
  showIcons  = localStorage.getItem("taxa_icons")  !== "0";

  document.documentElement.setAttribute("data-theme", savedTheme);
  document.getElementById("btn-theme").textContent = savedTheme === "dark" ? "🌙" : "☀️";
  document.getElementById("btn-ja").classList.toggle("active", langMode === "ja");
  document.getElementById("btn-en").classList.toggle("active", langMode === "en");
  document.getElementById("btn-lr").classList.toggle("active", layoutMode === "lr");
  document.getElementById("btn-tb").classList.toggle("active", layoutMode === "tb");
  document.getElementById("btn-icon").classList.toggle("active", showIcons);
  document.getElementById("srch").placeholder = langMode === "ja" ? "検索…" : "Search…";
  lay.nodeSize(layoutNodeSize());

  prog(20, "ツリー解析中…");
  root = d3.hierarchy(DATA); root.x0 = 0; root.y0 = 0;
  const genusIdx = RANK_ORD.indexOf("genus");
  root.descendants().forEach(d => {
    const ri = RANK_ORD.indexOf(d.data.rank);
    if (ri >= genusIdx && d.children) { d._children = d.children; d.children = null; }
  });
  prog(50, "描画中…"); update(root); prog(85, "調整中…");
  setTimeout(() => {
    fitV(true); prog(100, "完了");
    setTimeout(() => document.getElementById("ov").style.display = "none", 250);
    updStat();
  }, 80);
}

// ─── clipPath プール（種ごとに1つ、再生成しない） ─────────────────
const _clipCreated = new Set();
function ensureClip(qid) {
  const cid = `clip-${qid}`;
  if (_clipCreated.has(cid)) return cid;
  _clipCreated.add(cid);
  defs.append("clipPath").attr("id", cid)
      .append("circle").attr("r", IMG_R);
  return cid;
}

// ─── ツリー更新 ─────────────────────────────────────────────────
function update(src) {
  const W = mainEl.clientWidth, H = mainEl.clientHeight;
  svg.attr("width", W).attr("height", H);
  lay(root);
  const dur = 220, tr = d3.transition().duration(dur).ease(d3.easeCubicOut);

  const [sy, sx] = layoutMode === "lr"
    ? [src.y0 ?? src.y, src.x0 ?? src.x]
    : [src.x0 ?? src.x, src.y0 ?? src.y];

  // リンク
  const lk = g.selectAll(".lk").data(root.links(), d => d.target.data.id);
  lk.enter().append("path").attr("class","lk").attr("d", _ => dO(sy, sx))
    .merge(lk).transition(tr).attr("d", d => linkPath(d.source, d.target));
  lk.exit().transition(tr)
    .attr("d", _ => dO(layoutMode==="lr"?src.y:src.x, layoutMode==="lr"?src.x:src.y))
    .remove();

  // ノード
  const nd = g.selectAll(".nd").data(root.descendants(), d => d.data.id);
  const ne = nd.enter().append("g").attr("class","nd")
    .attr("transform", _ => `translate(${sy},${sx})`)
    .on("click",     (e, d) => { tog(d); update(d); e.stopPropagation(); })
    .on("mouseover", showTT).on("mousemove", movTT)
    .on("mouseout",  () => document.getElementById("tt").style.display = "none");

  // 背景円
  ne.append("circle").attr("class","bg").attr("r", 0)
    .attr("fill",         d => RC[d.data.rank] || RC.unknown)
    .attr("stroke",       d => RC[d.data.rank] || RC.unknown)
    .attr("fill-opacity", d => d._children ? .35 : 1);

  // 画像要素（種 + image_url があるノード）
  ne.each(function(d) {
    if (!d.data.image_url) return;
    const sel = d3.select(this);
    const cid = ensureClip(d.data.id);
    sel.append("image").attr("class","species-img")
      .attr("href", d.data.image_url)
      .attr("x", -IMG_R).attr("y", -IMG_R)
      .attr("width", IMG_R*2).attr("height", IMG_R*2)
      .attr("clip-path", `url(#${cid})`)
      .attr("preserveAspectRatio","xMidYMid slice")
      .attr("opacity", 0);
    sel.append("circle").attr("class","img-ring")
      .attr("r", 0).attr("fill","none")
      .attr("stroke", RC[d.data.rank] || RC.unknown);
  });

  // テキスト
  const nePri = ne.append("text").attr("class","primary-lbl")
    .text(d => getLabels(d).primary);
  applyPrimaryAttrs(nePri);
  const neSec = ne.filter(d => RANK_ORD.indexOf(d.data.rank) <= RANK_ORD.indexOf("family"))
    .append("text").attr("class","secondary-lbl")
    .text(d => getLabels(d).secondary);
  applySecondaryAttrs(neSec);

  // マージ
  const nm = ne.merge(nd);
  nm.transition(tr).attr("transform", d => nodeTransform(d));

  // 背景円（画像ありのとき r=0 に縮小して隠す）
  nm.select("circle.bg").transition(tr)
    .attr("r", d => (showIcons && d.data.image_url) ? 0 : (RR_BASE[d.data.rank] || 2))
    .attr("fill",   d => RC[d.data.rank] || RC.unknown)
    .attr("stroke", d => RC[d.data.rank] || RC.unknown)
    .attr("fill-opacity", d => d._children ? .35 : 1);

  // 画像フェードイン / アウト
  nm.select("image.species-img").transition(tr)
    .attr("opacity", d => (showIcons && d.data.image_url) ? 1 : 0);
  nm.select("circle.img-ring").transition(tr)
    .attr("r",       d => (showIcons && d.data.image_url) ? IMG_R + 1.5 : 0)
    .attr("opacity", d => (showIcons && d.data.image_url) ? 0.9 : 0);

  // テキスト更新
  applyPrimaryAttrs(nm.select(".primary-lbl").text(d => getLabels(d).primary));
  applySecondaryAttrs(nm.select(".secondary-lbl").text(d => getLabels(d).secondary));

  nd.exit().transition(tr)
    .attr("transform", _ => `translate(${layoutMode==="lr"?src.y:src.x},${layoutMode==="lr"?src.x:src.y})`)
    .style("opacity", 0).remove();
  root.descendants().forEach(d => { d.x0 = d.x; d.y0 = d.y; });
}

// ─── レイアウト補助 ───────────────────────────────────────────────
function nodeTransform(d) {
  return layoutMode === "lr" ? `translate(${d.y},${d.x})` : `translate(${d.x},${d.y})`;
}
function linkPath(s, t) {
  if (layoutMode === "lr") {
    const m = (s.y + t.y) / 2;
    return `M${s.y},${s.x}C${m},${s.x} ${m},${t.x} ${t.y},${t.x}`;
  }
  const m = (s.y + t.y) / 2;
  return `M${s.x},${s.y}C${s.x},${m} ${t.x},${m} ${t.x},${t.y}`;
}
function dO(a, b) {
  return layoutMode === "lr"
    ? `M${a},${b}C${a},${b} ${a},${b} ${a},${b}`
    : `M${b},${a}C${b},${a} ${b},${a} ${b},${a}`;
}
const hk  = d => d.children || d._children;
const tog = d => {
  if (d.children) { d._children = d.children;  d.children  = null; }
  else            { d.children  = d._children;  d._children = null; }
};
function expandTo(rank) {
  const ti = RANK_ORD.indexOf(rank); if (ti < 0) return;
  root.descendants().forEach(d => {
    const di = RANK_ORD.indexOf(d.data.rank);
    if (di < ti && d._children) { d.children  = d._children; d._children = null; }
    if (di >= ti && d.children) { d._children = d.children;  d.children  = null; }
  });
  update(root); updStat();
}
function collapseAll() {
  root.descendants().forEach(d => {
    if (d.depth > 0 && d.children) { d._children = d.children; d.children = null; }
  });
  update(root);
}
function fitV(instant) {
  const W = mainEl.clientWidth, H = mainEl.clientHeight;
  const bb = g.node().getBBox();
  if (!bb.width || !bb.height) return;
  const sc = Math.min(W / (bb.width + 80), H / (bb.height + 80), 1.2);
  const t  = d3.zoomIdentity
    .translate(W/2 - sc*(bb.x + bb.width/2), H/2 - sc*(bb.y + bb.height/2)).scale(sc);
  if (instant) svg.call(zm.transform, t);
  else         svg.transition().duration(500).call(zm.transform, t);
}
function updStat() {
  const d  = root.descendants();
  const sp = d.filter(x => x.data.rank === "species").length;
  const ge = d.filter(x => x.data.rank === "genus").length;
  const fa = d.filter(x => x.data.rank === "family").length;
  const im = d.filter(x => x.data.image_url).length;
  document.getElementById("stat").innerHTML =
    `<span><span class="sd" style="background:var(--c-species)"></span>${sp.toLocaleString()}種</span>`+
    `<span><span class="sd" style="background:var(--c-genus)"></span>${ge.toLocaleString()}属</span>`+
    `<span><span class="sd" style="background:var(--c-family)"></span>${fa.toLocaleString()}科</span>`+
    (im ? `<span style="color:var(--txt3);font-size:10px">📷${im.toLocaleString()}</span>` : "");
}
const cntSp = d => {
  if (!d.children && !d._children)
    return ["species","subspecies","variety","form"].includes(d.data.rank) ? 1 : 0;
  return (d.children ?? d._children ?? []).reduce((s, c) => s + cntSp(c), 0);
};

// ─── 検索 ─────────────────────────────────────────────────────────
function doSrch(q) {
  const v = q.trim().toLowerCase();
  g.selectAll(".nd").classed("nh", false).classed("nm", false);
  if (!v) return;
  const hit = new Set();
  root.descendants().forEach(d => {
    if ((d.data.name||"").toLowerCase().includes(v) ||
        (d.data.ja  ||"").toLowerCase().includes(v)) {
      hit.add(d.data.id);
      let p = d.parent;
      while (p) {
        hit.add(p.data.id);
        if (p._children) { p.children = p._children; p._children = null; }
        p = p.parent;
      }
    }
  });
  if (hit.size) update(root);
  g.selectAll(".nd")
    .classed("nh", d => (d.data.name||"").toLowerCase().includes(v) ||
                        (d.data.ja  ||"").toLowerCase().includes(v))
    .classed("nm", d => !hit.has(d.data.id));
}

// ─── ツールチップ（画像対応） ─────────────────────────────────────
const tt = document.getElementById("tt");
function showTT(e, d) {
  const lb = getLabels(d);
  const ch = (d.children ?? d._children ?? []).length;
  document.getElementById("tt-rank").textContent = RJ[d.data.rank] || d.data.rank;
  document.getElementById("tt-name").textContent = lb.primary;
  document.getElementById("tt-ja").textContent   = lb.secondary;
  document.getElementById("tt-cnt").textContent  = ch ? `直下: ${ch}件` : "";

  const imgEl    = document.getElementById("tt-img");
  const phEl     = document.getElementById("tt-ph");
  const creditEl = document.getElementById("tt-credit");

  if (d.data.image_url) {
    // サムネイルURLの解像度を220pxに差し替え
    const large = d.data.image_url.replace(/\/(\d+)px-/, "/220px-");
    imgEl.src = large;
    imgEl.classList.remove("hidden");
    phEl.classList.add("hidden");
    creditEl.textContent = "© Wikimedia Commons";
  } else {
    imgEl.classList.add("hidden");
    phEl.classList.remove("hidden");
    phEl.textContent = ["species","subspecies"].includes(d.data.rank) ? "🐦"
                     : d.data.rank === "genus" ? "🔬" : "🌿";
    creditEl.textContent = "";
  }
  tt.style.display = "block";
  movTT(e);
}
function movTT(e) {
  const r  = mainEl.getBoundingClientRect();
  const tx = e.clientX - r.left;
  const ty = e.clientY - r.top;
  const left = (tx + 235 > r.width) ? tx - 238 : tx + 14;
  tt.style.left = left + "px";
  tt.style.top  = Math.min(ty - 10, r.height - 270) + "px";
}

let rsz;
window.addEventListener("resize", () => {
  clearTimeout(rsz);
  rsz = setTimeout(() => {
    svg.attr("width", mainEl.clientWidth).attr("height", mainEl.clientHeight);
  }, 200);
});
window.addEventListener("load", init);
</script></body></html>"""

def make_html(tree: dict, root_qid: str) -> str:
    title = tree.get("name", root_qid)
    if tree.get("ja"):
        title = f"{tree['ja']} ({title})"
    date  = datetime.now().strftime("%Y-%m-%d")
    js    = json.dumps(tree, ensure_ascii=False, separators=(",", ":"))
    return (HTML
            .replace("__TITLE__", title)
            .replace("__QID__",   root_qid)
            .replace("__DATE__",  date)
            .replace("__DATA__",  js))

# ─────────────────────────────────────────────────────────────────
#  メイン
# ─────────────────────────────────────────────────────────────────

def main():
    global _t0
    _t0 = time.time()

    ap = argparse.ArgumentParser(
        description="生物分類 汎用系統図ジェネレーター v3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--qid",   metavar="QID",
                     help="Wikidata QID（例: Q25341）")
    grp.add_argument("--taxon", metavar="NAME",
                     help="学名または和名で検索（例: Passeriformes, カラス科）")
    ap.add_argument("--split",  default=DEFAULT_SPLIT, metavar="RANK",
                    help=f"Phase 1/2 の分割ランク（デフォルト: {DEFAULT_SPLIT}）")
    ap.add_argument("--stop",   default="species", metavar="RANK",
                    help="取得の終端ランク（デフォルト: species）")
    ap.add_argument("--fast",   action="store_true",
                    help="Phase 1 のみ（split_rank まで）で終了")
    ap.add_argument("--cached", action="store_true",
                    help="キャッシュ再利用（HTMLのみ再生成）")
    ap.add_argument("--output", default=None, metavar="FILE",
                    help="出力HTMLファイル名（省略時は自動生成）")
    ap.add_argument("--proxy",  default=None, metavar="URL",
                    help="プロキシURL（例: http://proxy.example.com:8080）")
    ap.add_argument("--test",   action="store_true",
                    help="接続診断")
    args = ap.parse_args()

    print("\n╔═══════════════════════════════════════════════╗")
    print("║  🌿  生物分類 汎用系統図ジェネレーター  v3   ║")
    print("╚═══════════════════════════════════════════════╝")

    if args.test:
        init_session(args.proxy)
        run_test(args.proxy); return

    # ── QID の解決 ───────────────────────────────────────────────
    if not args.qid and not args.taxon and not args.cached:
        ap.print_help()
        print("\n⚠  --qid または --taxon を指定してください。")
        print("   例: python taxa_tree.py --qid Q25341")
        print("   例: python taxa_tree.py --taxon \"Passeriformes\"")
        sys.exit(1)

    init_session(args.proxy)

    # キャッシュ再利用モード: QID 不要
    if args.cached:
        # 直近のキャッシュ（taxa_cache_*.json）を探す
        # OUTPUT_DIR 内を優先し、なければカレントも検索
        caches = sorted(
            list(Path(OUTPUT_DIR).glob("taxa_cache_*.json"))
            + list(Path(".").glob("taxa_cache_*.json")),
            key=lambda p: p.stat().st_mtime, reverse=True
        ) if Path(OUTPUT_DIR).exists() else sorted(
            Path(".").glob("taxa_cache_*.json"),
            key=lambda p: p.stat().st_mtime, reverse=True
        )
        if not caches:
            print("❌  キャッシュが見つかりません。まず --qid または --taxon で取得してください。")
            sys.exit(1)
        cache_file = caches[0]
        print(f"\n📂 キャッシュ読み込み: {cache_file}")
        with open(cache_file, encoding="utf-8") as f:
            tree = json.load(f)
        root_qid = tree["id"]
    else:
        if args.taxon:
            root_qid, label = pick_taxon(args.taxon)
            print(f"\n  → QID: {root_qid}  ({label})")
        else:
            root_qid = args.qid.strip()

        # キャッシュファイル名（QID 込み）
        cache_file = Path(OUTPUT_DIR) / f"taxa_cache_{root_qid}.json"

        # ── ルート情報取得 ─────────────────────────────────────
        print(f"\n  🌱 ルート情報を取得中 [{root_qid}]…")
        root_node = fetch_root_info(root_qid)
        print(f"  → {root_node['name']}"
              + (f" / {root_node['ja']}" if root_node.get("ja") else "")
              + f"  ({root_node['rank']})")

        # split_rank の自動調整（ルートが split_rank 以下の場合）
        split_rank = args.split
        stop_rank  = args.stop
        root_ri    = rank_index(root_node["rank"])
        split_ri   = rank_index(split_rank)
        stop_ri    = rank_index(stop_rank)

        if root_ri >= split_ri:
            # ルートが split_rank 以下 → split を root より1つ下に自動調整
            new_split = RANK_ORD[min(root_ri + 1, stop_ri - 1)] if root_ri + 1 < stop_ri else stop_rank
            print(f"  ℹ  ルートが split_rank ({split_rank}) 以下のため、"
                  f"split を '{new_split}' に自動調整")
            split_rank = new_split

        # ── Phase 1 ─────────────────────────────────────────────
        print(f"\n{'─'*50}")
        print(f"  Phase 1: {root_node['rank']} → {split_rank} まで BFS")
        print(f"{'─'*50}\n")
        tree, nodes = fetch_phase1(root_node, split_rank)

        split_count = sum(1 for n in nodes.values() if n["rank"] == split_rank)
        print(f"\n  ✅ Phase 1 完了: {split_count} {split_rank} ノードを取得  ({_elapsed()})")

        if not args.fast:
            # ── 総種数推定 ────────────────────────────────────────
            total_sp = estimate_species_count(root_qid)

            # ── Phase 2 ─────────────────────────────────────────
            print(f"\n{'─'*50}")
            print(f"  Phase 2: {split_rank} → {stop_rank} まで BFS（進捗バー付き）")
            print(f"{'─'*50}")
            fetch_phase2(tree, nodes, split_rank, stop_rank, total_sp)
        else:
            print("  （--fast: Phase 2 をスキップ）")

        # ── キャッシュ保存 ────────────────────────────────────────
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(tree, f, ensure_ascii=False)

        # 統計
        all_nd: list[dict] = []
        _walk(tree, all_nd.append)
        sp = sum(1 for n in all_nd if n["rank"] == "species")
        ge = sum(1 for n in all_nd if n["rank"] == "genus")
        fa = sum(1 for n in all_nd if n["rank"] == "family")
        print(f"\n💾 キャッシュ保存: {cache_file}")
        print(f"   ノード:{len(all_nd):,}  種:{sp:,}  属:{ge:,}  科:{fa:,}")

    # ── HTML 生成 ────────────────────────────────────────────────
    print("\n📄 HTML生成中…")
    html = make_html(tree, tree["id"])

    if args.output:
        out = Path(args.output)
    else:
        label = sanitize_filename(
            tree.get("ja") or tree.get("name") or tree["id"]
        )
        out = Path(OUTPUT_DIR) / f"taxa_{label}_{tree['id']}.html"

    # 出力先ディレクトリが存在しない場合は自動作成
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    mb = out.stat().st_size / 1024 / 1024
    print(f"\n✅  完了!  →  {out}  ({mb:.1f} MB)  総時間: {_elapsed()}")
    print(f"🔗  file://{out.resolve()}")
    print("\n📬  HTML ファイル1つを共有するだけでOK（インターネット不要）")
    prx = f" --proxy {args.proxy}" if getattr(args, "proxy", None) else ""
    print(f"🔄  更新: python {Path(__file__).name} --qid {tree['id']}{prx}")

if __name__ == "__main__":
    main()