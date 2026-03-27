#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
taxa_tree.py  ─  生物分類 汎用系統図ジェネレーター v6
====================================================================
エントリポイント。引数を解析し、取得・HTML生成・保存を制御する。

  データ取得・モデル:  module/taxa_fetch.py
  HTML生成・UI:        module/taxa_html.py

【使い方】
  pip install requests

  # 通常取得
  python taxa_tree.py --qid Q25341          # スズメ目
  python taxa_tree.py --qid Q10908          # 哺乳綱
  python taxa_tree.py --taxon "カラス科"    # 名前で検索
  python taxa_tree.py --qid Q25341 --fast   # 科まで（高速）

  # HTML のみ再生成（fetch をスキップ）
  python taxa_tree.py --qid Q25341 --render # 指定 QID のキャッシュを使用
  python taxa_tree.py --render              # 最新キャッシュを自動選択

  # 一括再生成
  python taxa_tree.py --render-all          # standalone: 全キャッシュを再生成
  python taxa_tree.py --render-all --web    # web: 余分なHTMLを削除 + index.html 再生成

  # その他
  python taxa_tree.py --test                # 接続診断
  python taxa_tree.py --email you@example.com --qid Q25341

【出力フォルダの変更】
  OUTPUT_DIR = "result"  # ← ここを変更するだけ
"""

import argparse
import json
import sys
import time
from pathlib import Path

from module.taxa_fetch import (
    DEFAULT_SPLIT,
    FETCH_VERSION,
    RANK_ORD,
    _elapsed,
    _walk,
    estimate_species_count,
    fetch_phase1,
    fetch_phase2,
    fetch_root_info,
    init_session,
    pick_taxon,
    rank_index,
    run_test,
    sanitize_filename,
)
from module.taxa_html import HTML_VERSION, make_html, make_index_html

# ─────────────────────────────────────────────────────────────────
#  設定
# ─────────────────────────────────────────────────────────────────

# 出力先ディレクトリ（キャッシュ JSON と HTML の両方をここに保存する）
# ここを変更するだけでキャッシュ・HTML すべての出力先が変わる
OUTPUT_DIR = "result"


# ─────────────────────────────────────────────────────────────────
#  ヘルパー関数
# ─────────────────────────────────────────────────────────────────

def _print_meta(tree: dict) -> None:
    """キャッシュの _meta 情報をコンソールに表示する。"""
    meta = tree.get("_meta")
    if meta:
        fv = meta.get("fetch_version", "?")
        fa = meta.get("fetched_at",    "?")
        sr = meta.get("split_rank",    "?")
        st = meta.get("stop_rank",     "?")
        print(f"   fetch_version: {fv}  |  取得日時: {fa}")
        print(f"   split_rank: {sr}  |  stop_rank: {st}")
    else:
        print("   ⚠  _meta なし（旧バージョンのキャッシュ）")


def _load_cache(qid: str | None) -> tuple[dict, Path]:
    """
    キャッシュ JSON を読み込んでツリー辞書とファイルパスを返す。

    qid が指定されている場合: OUTPUT_DIR/taxa_cache_<qid>.json を優先し、
                             なければカレントディレクトリも検索する。
    qid が None の場合:       更新日時が最新のキャッシュを自動選択する。
    """
    if qid:
        candidates = [
            Path(OUTPUT_DIR) / f"taxa_cache_{qid}.json",
            Path(f"taxa_cache_{qid}.json"),
        ]
        for p in candidates:
            if p.exists():
                print(f"\n📂 キャッシュ読み込み: {p}  (QID: {qid})")
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
                _print_meta(data)
                return data, p
        print(f"❌  QID {qid} のキャッシュが見つかりません。")
        print(f"   先に python taxa_tree.py --qid {qid} で取得してください。")
        sys.exit(1)
    else:
        caches = sorted(
            list(Path(OUTPUT_DIR).glob("taxa_cache_*.json"))
            + list(Path(".").glob("taxa_cache_*.json")),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ) if Path(OUTPUT_DIR).exists() else sorted(
            Path(".").glob("taxa_cache_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not caches:
            print("❌  キャッシュが見つかりません。")
            print("   まず --qid または --taxon で取得してください。")
            sys.exit(1)
        p = caches[0]
        print(f"\n📂 キャッシュ読み込み（最新）: {p}")
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        _print_meta(data)
        return data, p


def _cleanup_html(output_dir: Path) -> int:
    """
    web モード用クリーンアップ。

    output_dir 内の taxa_*.html を削除する。
    web モードでは個別 HTML は不要（SPA の index.html + JSON で完結するため）。
    index.html は削除しない。
    削除したファイル数を返す。
    """
    removed = 0
    for p in output_dir.glob("taxa_*.html"):
        try:
            p.unlink()
            print(f"  🗑  削除: {p.name}")
            removed += 1
        except OSError as e:
            print(f"  ⚠  削除失敗: {p.name} ({e})")
    return removed


def _save_html(tree: dict, output_arg: str | None,
               web_mode: bool = False) -> None:
    """
    HTML を生成してファイルに書き出す。

    web_mode=True:
        個別 HTML は生成しない（SPA の index.html + JSON で完結するため）。
        余分な taxa_*.html を削除して index.html を更新する。
    web_mode=False:
        JSON を HTML に埋め込んだ standalone ファイルを生成する。
    """
    out_dir = Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    if web_mode:
        print("\n🌐 web モード: 個別 HTML は生成しません（SPA + JSON で完結）")
        n = _cleanup_html(out_dir)
        if n:
            print(f"  ✅ {n} 件の余分な HTML を削除しました")
    else:
        print("\n📄 HTML生成中… [standalone モード: JSON 埋め込み]")
        html = make_html(tree, tree["id"])
        if output_arg:
            out = Path(output_arg)
        else:
            label = sanitize_filename(
                tree.get("ja") or tree.get("name") or tree["id"]
            )
            out = out_dir / f"taxa_{label}_{tree['id']}.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        mb = out.stat().st_size / 1024 / 1024
        print(f"\n✅  完了!  →  {out}  ({mb:.1f} MB)  総時間: {_elapsed()}")
        print(f"🔗  file://{out.resolve()}")

    # ── index.html を OUTPUT_DIR に自動更新 ──────────────────────
    index_out  = out_dir / "index.html"
    index_html = make_index_html(out_dir)
    index_out.write_text(index_html, encoding="utf-8")
    print(f"📋  一覧更新  →  {index_out}")

    if not web_mode:
        print("\n📬  HTML ファイル1つを共有するだけでOK（インターネット不要）")


def _render_all(web_mode: bool) -> None:
    """
    --render-all の処理。

    web モード:
        1. OUTPUT_DIR 内の taxa_*.html を削除
        2. index.html を再生成

    standalone モード:
        OUTPUT_DIR 内の全キャッシュ JSON に対して HTML を再生成し、
        最後に index.html を更新する。
    """
    out_dir = Path(OUTPUT_DIR)
    if not out_dir.exists():
        print(f"❌  出力フォルダが見つかりません: {OUTPUT_DIR}")
        print("   まず --qid で取得してください。")
        sys.exit(1)

    if web_mode:
        # ── web モード: 余分な HTML 削除 + index.html 再生成 ──────
        print("\n🌐 --render-all [web モード]")
        n = _cleanup_html(out_dir)
        print(f"\n  ✅ {n} 件の taxa_*.html を削除しました" if n else "  ℹ  削除対象の HTML はありませんでした")
        print("\n📋 index.html を再生成中…")
        index_html = make_index_html(out_dir)
        index_out  = out_dir / "index.html"
        index_out.write_text(index_html, encoding="utf-8")
        print(f"  ✅ 完了  →  {index_out}")

    else:
        # ── standalone モード: 全キャッシュを HTML に変換 ────────
        caches = sorted(
            out_dir.glob("taxa_cache_Q*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not caches:
            print("❌  キャッシュが見つかりません。")
            print("   まず --qid で取得してください。")
            sys.exit(1)

        print(f"\n📄 --render-all [standalone モード]: {len(caches)} 件を処理します")
        for i, cache_path in enumerate(caches, 1):
            print(f"\n[{i}/{len(caches)}] {cache_path.name}")
            with open(cache_path, encoding="utf-8") as f:
                tree = json.load(f)
            _print_meta(tree)
            html  = make_html(tree, tree["id"])
            label = sanitize_filename(
                tree.get("ja") or tree.get("name") or tree["id"]
            )
            out = out_dir / f"taxa_{label}_{tree['id']}.html"
            out.write_text(html, encoding="utf-8")
            mb = out.stat().st_size / 1024 / 1024
            print(f"  ✅  →  {out.name}  ({mb:.1f} MB)")

        # 全件処理後に index.html を一括更新
        print("\n📋 index.html を更新中…")
        index_out = out_dir / "index.html"
        index_out.write_text(make_index_html(out_dir), encoding="utf-8")
        print(f"  ✅ 完了  →  {index_out}")
        print(f"\n✅  render-all 完了: {len(caches)} 件  総時間: {_elapsed()}")


def main() -> None:
    import module.taxa_fetch as _fetch
    _fetch._t0 = time.time()

    ap = argparse.ArgumentParser(
        description="生物分類 汎用系統図ジェネレーター v6",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # ── 動作モード（排他グループ） ────────────────────────────────
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--taxon", metavar="NAME",
                      help="学名または和名で検索して取得（例: カラス科）")
    mode.add_argument("--render", action="store_true",
                      help="fetch をスキップし HTML のみ再生成する。"
                           "--qid で対象キャッシュを指定可（省略時は最新を自動選択）")
    mode.add_argument("--render-all", action="store_true",
                      help="[web] 余分なHTMLを削除して index.html を再生成 / "
                           "[standalone] 全キャッシュの HTML を再生成。"
                           "--qid / --taxon と同時使用不可")
    mode.add_argument("--cached", action="store_true",
                      help="--render の別名（後方互換）")
    mode.add_argument("--test",   action="store_true",
                      help="接続診断のみ実行")

    # ── 共通オプション ────────────────────────────────────────────
    ap.add_argument("--qid",    metavar="QID",
                    help="Wikidata QID（例: Q25341）。"
                         "--render と組み合わせて対象キャッシュを指定できる")
    ap.add_argument("--split",  default=DEFAULT_SPLIT, metavar="RANK",
                    help=f"Phase 1/2 の分割ランク（デフォルト: {DEFAULT_SPLIT}）")
    ap.add_argument("--stop",   default="species", metavar="RANK",
                    help="取得の終端ランク（デフォルト: species）")
    ap.add_argument("--fast",   action="store_true",
                    help="Phase 1 のみ（--split まで）で終了")
    ap.add_argument("--web",    action="store_true",
                    help="web モード: JSON を外部ファイルに分離（GitHub Pages 用）。"
                         "standalone モード（デフォルト）は JSON を HTML に埋め込む")
    ap.add_argument("--output", default=None, metavar="FILE",
                    help="出力 HTML ファイル名（省略時は自動生成）")
    ap.add_argument("--proxy",  default=None, metavar="URL",
                    help="プロキシ URL（例: http://proxy.example.com:8080）")
    ap.add_argument("--email", default=None, metavar="EMAIL",
                    help="連絡先メールアドレス（User-Agent に埋め込む。"
                         "環境変数 TAXA_CONTACT_EMAIL でも設定可）")
    args = ap.parse_args()

    print("\n╔═══════════════════════════════════════════════╗")
    print("║  🌿  生物分類 汎用系統図ジェネレーター  v6   ║")
    print("╚═══════════════════════════════════════════════╝")
    print(f"   fetch: v{FETCH_VERSION}  │  html: v{HTML_VERSION}")

    # ── 接続診断 ─────────────────────────────────────────────────
    if args.test:
        init_session(args.proxy, getattr(args, "email", None))
        run_test(args.proxy)
        return

    # ── 一括再生成モード（--render-all）─────────────────────────
    if getattr(args, "render_all", False):
        if args.qid:
            print("⚠  --render-all と --qid は同時に使用できません。")
            sys.exit(1)
        _render_all(web_mode=args.web)
        return

    # ── HTML 再生成モード（--render / --cached）──────────────────
    if args.render or args.cached:
        if args.fast or args.split != DEFAULT_SPLIT or args.stop != "species":
            print("ℹ  --render モードでは --fast / --split / --stop は無視されます。")
        tree, _ = _load_cache(args.qid)
        _save_html(tree, args.output, getattr(args, "web", False))
        return

    # ── 引数バリデーション（新規取得モード） ─────────────────────
    if not args.qid and not args.taxon:
        ap.print_help()
        print("\n⚠  --qid または --taxon を指定してください。")
        print("   例: python taxa_tree.py --qid Q25341")
        print("   例: python taxa_tree.py --taxon \"Passeriformes\"")
        print("   HTML のみ再生成: python taxa_tree.py --render [--qid QID]")
        sys.exit(1)

    init_session(args.proxy, getattr(args, "email", None))

    # ── 新規取得モード ────────────────────────────────────────────
    if args.taxon:
        root_qid, label = pick_taxon(args.taxon)
        print(f"\n  → QID: {root_qid}  ({label})")
    else:
        root_qid = args.qid.strip()

    cache_file = Path(OUTPUT_DIR) / f"taxa_cache_{root_qid}.json"

    print(f"\n  🌱 ルート情報を取得中 [{root_qid}]…")
    root_node = fetch_root_info(root_qid)
    print(
        f"  → {root_node['name']}"
        + (f" / {root_node['ja']}" if root_node.get("ja") else "")
        + f"  ({root_node['rank']})"
    )

    split_rank = args.split
    stop_rank  = args.stop
    root_ri    = rank_index(root_node["rank"])
    split_ri   = rank_index(split_rank)
    stop_ri    = rank_index(stop_rank)

    if root_ri >= split_ri:
        new_split = (
            RANK_ORD[min(root_ri + 1, stop_ri - 1)]
            if root_ri + 1 < stop_ri
            else stop_rank
        )
        print(
            f"  ℹ  ルートが split_rank ({split_rank}) 以下のため、"
            f"split を '{new_split}' に自動調整"
        )
        split_rank = new_split

    print(f"\n{'─'*50}")
    print(f"  Phase 1: {root_node['rank']} → {split_rank} まで BFS")
    print(f"{'─'*50}\n")
    tree, nodes = fetch_phase1(root_node, split_rank)

    split_count = sum(1 for n in nodes.values() if n["rank"] == split_rank)
    print(f"\n  ✅ Phase 1 完了: {split_count} {split_rank} ノードを取得  ({_elapsed()})")

    if not args.fast:
        total_sp = estimate_species_count(root_qid)
        print(f"\n{'─'*50}")
        print(f"  Phase 2: {split_rank} → {stop_rank} まで BFS（進捗バー付き）")
        print(f"{'─'*50}")
        fetch_phase2(tree, nodes, split_rank, stop_rank, total_sp)
    else:
        print("  （--fast: Phase 2 をスキップ）")

    from datetime import datetime as _dt
    tree["_meta"] = {
        "fetch_version": FETCH_VERSION,
        "fetched_at":    _dt.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "split_rank":    split_rank,
        "stop_rank":     stop_rank,
    }
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(tree, f, ensure_ascii=False)

    all_nd: list[dict] = []
    _walk(tree, all_nd.append)
    sp = sum(1 for n in all_nd if n["rank"] == "species")
    ge = sum(1 for n in all_nd if n["rank"] == "genus")
    fa = sum(1 for n in all_nd if n["rank"] == "family")
    print(f"\n💾 キャッシュ保存: {cache_file}")
    print(f"   ノード:{len(all_nd):,}  種:{sp:,}  属:{ge:,}  科:{fa:,}")

    _save_html(tree, args.output, getattr(args, "web", False))


if __name__ == "__main__":
    main()