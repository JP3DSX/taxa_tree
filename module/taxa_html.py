#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
module/taxa_html.py  ─  HTML生成・UI モジュール
================================================================
インタラクティブ系統図 HTML のテンプレートと生成関数を提供する。
データロジックには依存しない。

公開 API:
    make_html(tree, root_qid) -> str
        standalone モード: JSON を HTML に埋め込む（単体ファイル動作）
    make_web_viewer(tree, root_qid, json_filename) -> str
        web モード: JSON を外部 fetch で読み込む（GitHub Pages 用）
    make_index_html(output_dir) -> str
        SPA index.html を生成する（ランディング + ビューワー統合）

【バージョン管理】
    SPARQL・BFS など取得機能の変更 → taxa_fetch.py の FETCH_VERSION を更新
    CSS・DOM・JS など表示・UI の変更 → HTML_VERSION を更新
"""

import json as _json
import re as _re
from datetime import datetime
from pathlib import Path

HTML_VERSION = "1.6"

# ─────────────────────────────────────────────────────────────────
#  HTML テンプレート（standalone / web 共通）
#  プレースホルダ: __TITLE__ / __QID__ / __DATE__ / __DATA_BLOCK__
#
#  make_html():       const DATA={...json...};
#  make_web_viewer(): fetch(json) → DATA → init()
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
  touch-action:manipulation;
  font-family:'Hiragino Sans','Yu Gothic',Meiryo,'Noto Sans JP',system-ui,sans-serif;
  transition:background .2s,color .2s}
/* ── ヘッダー ── */
#hdr{display:flex;align-items:center;gap:6px;padding:6px 10px;
  background:var(--bg2);border-bottom:1px solid var(--brd);flex-wrap:wrap}
#ttl{font-size:13px;font-weight:600;white-space:nowrap}
#ttl em{font-style:italic;color:var(--txt2);font-size:11px;font-weight:400;margin-left:4px}
#srch{background:var(--bg3);border:1px solid var(--brd);color:var(--txt);
  border-radius:18px;padding:4px 11px;font-size:11px;width:140px;outline:none;
  transition:background .2s,border-color .15s}
#srch:focus{border-color:var(--hl)}
#srch::placeholder{color:var(--txt3)}
#srch-btn{background:var(--hl);border:none;color:#000;border-radius:18px;
  padding:4px 10px;font-size:11px;cursor:pointer;font-weight:600;transition:opacity .15s}
#srch-btn:hover{opacity:.85}
#srch-clr{background:transparent;border:1px solid var(--brd);color:var(--txt3);
  border-radius:18px;padding:4px 8px;font-size:11px;cursor:pointer;display:none}
#srch-clr:hover{border-color:var(--txt2);color:var(--txt)}
.hb,.tb{background:transparent;border:1px solid var(--brd);color:var(--txt2);
  border-radius:13px;padding:3px 9px;font-size:11px;cursor:pointer;
  white-space:nowrap;transition:border-color .15s,color .15s,background .15s}
.hb:hover,.tb:hover{border-color:var(--txt2);color:var(--txt)}
.tb.active{border-color:var(--hl);color:var(--hl);background:rgba(240,180,41,.08)}
.ctrl{display:flex;gap:4px;padding-left:7px;border-left:1px solid var(--brd)}
#stat{font-size:11px;color:var(--txt3);margin-left:auto;white-space:nowrap;
  display:flex;gap:9px}
.sd{width:7px;height:7px;border-radius:50%;display:inline-block;margin-right:2px}
/* ── 凡例バー ── */
#leg{display:flex;gap:6px;flex-wrap:wrap;align-items:center;padding:3px 10px;
  background:var(--bg2);border-bottom:1px solid var(--brd);font-size:10px;color:var(--txt3)}
.li{display:flex;align-items:center;gap:3px}
.ld{width:7px;height:7px;border-radius:50%}
/* IUCN 凡例（折りたたみ式） */
#iucn-leg{display:none;gap:6px;flex-wrap:wrap;align-items:center}
/* ツールチップ幅スライダー */
#leg-sizer{display:flex;align-items:center;gap:5px;margin-left:auto}
#leg-sizer label{font-size:9px;color:var(--txt3);white-space:nowrap}
#leg-sizer input[type=range]{width:80px;height:3px;accent-color:var(--hl);cursor:pointer}
/* ── メインエリア ── */
#main{overflow:hidden;height:calc(100vh - 64px);position:relative}
svg{width:100%;height:100%}
.lk{fill:none;stroke:var(--brd);stroke-width:.7}
/* ── ノード ── */
.nd{cursor:pointer}
.nd circle.bg{stroke-width:1.5;transition:r .12s,opacity .15s}
.nd:hover circle.bg{filter:brightness(1.3)}
.nd .img-ring{fill:none;stroke-width:2;transition:stroke-width .12s,r .12s}
.nd:hover .img-ring{stroke-width:2.8}
.nd text{font-size:11px;fill:var(--txt);pointer-events:none;dominant-baseline:central}
.primary-lbl{font-style:italic;fill:var(--txt2)!important}
.secondary-lbl{font-size:9px;fill:var(--txt3)!important}
/* ハイライト / ディム */
.nh circle.bg,.nh .img-ring{stroke:var(--hl)!important;stroke-width:2.5!important}
.nh text{fill:var(--hl)!important}
.nm{opacity:.1}
/* 補完ノード外枠 */
.nd.strategy-prefix .bg,.nd.strategy-prefix .img-ring{stroke:#f59e0b!important}
.nd.strategy-gbif    .bg,.nd.strategy-gbif    .img-ring{stroke:#3b82f6!important}
.nd.strategy-incomplete .bg{stroke:#ef4444!important;stroke-dasharray:3,2}
/* IUCN 保全状況: ノード外枠 */
.nd.iucn-EX .bg,.nd.iucn-EX .img-ring{stroke:#6b7280!important;stroke-dasharray:4,2}
.nd.iucn-EW .bg,.nd.iucn-EW .img-ring{stroke:#9ca3af!important;stroke-dasharray:4,2}
.nd.iucn-CR .bg,.nd.iucn-CR .img-ring{stroke:#dc2626!important;stroke-width:2.5!important}
.nd.iucn-EN .bg,.nd.iucn-EN .img-ring{stroke:#ea580c!important;stroke-width:2!important}
.nd.iucn-VU .bg,.nd.iucn-VU .img-ring{stroke:#d97706!important}
.nd.iucn-NT .bg,.nd.iucn-NT .img-ring{stroke:#65a30d!important}
/* ── ツールチップ ── */
#tt{position:absolute;background:var(--bg2);border:1px solid var(--brd);
  border-radius:10px;padding:0;pointer-events:auto;display:none;
  width:var(--tt-w,280px);z-index:50;overflow:hidden;
  box-shadow:0 8px 28px rgba(0,0,0,.35);transition:width .1s}
#tt-img{width:100%;height:auto;aspect-ratio:16/10;object-fit:cover;
  display:block;background:var(--bg3)}
#tt-img.hidden{display:none}
#tt-ph{width:100%;aspect-ratio:16/10;display:flex;align-items:center;
  justify-content:center;font-size:30px;background:var(--bg3)}
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
/* IUCN バッジ（ツールチップ内） */
#tt-iucn{display:none;margin-top:6px;padding:3px 8px;border-radius:4px;
  font-size:10px;font-weight:700;text-align:center;letter-spacing:.05em}
/* ── メタデータフッター ── */
#foot{position:absolute;bottom:7px;left:9px;font-size:10px;color:var(--txt3);
  background:var(--foot-bg);padding:4px 8px;border-radius:5px;
  border:1px solid var(--brd);line-height:1.8;pointer-events:none}
/* 一覧に戻るボタン（SPA 専用） */
#btn-back{position:fixed;bottom:42px;left:9px;z-index:2500;display:none;
  background:var(--bg2);border:1px solid var(--brd);color:var(--txt2);
  border-radius:13px;padding:4px 12px;font-size:11px;cursor:pointer;
  transition:border-color .15s,color .15s}
#btn-back:hover{border-color:var(--hl);color:var(--hl)}
/* ── オーバーレイ（解析中） ── */
#ov{position:fixed;inset:0;background:rgba(13,17,23,.97);display:flex;
  flex-direction:column;align-items:center;justify-content:center;
  gap:11px;z-index:999}
#ov h2{font-size:16px}
#ov p{font-size:12px;color:var(--txt2);text-align:center;max-width:320px}
.pb{width:240px;height:3px;background:var(--bg3);border-radius:2px;overflow:hidden}
.pi{height:100%;background:var(--hl);border-radius:2px;width:0;transition:width .3s}
/* ── ローディング（web モード） ── */
#loading{position:fixed;inset:0;background:var(--bg);display:flex;
  flex-direction:column;align-items:center;justify-content:center;
  gap:14px;z-index:2000;font-size:13px;color:var(--txt2)}
#loading-bar-outer{width:220px;height:4px;background:var(--bg3);border-radius:2px}
#loading-bar{height:4px;width:0%;background:var(--hl);border-radius:2px;
  transition:width .3s}
/* ── モバイル専用 ── */
@media (pointer: coarse) {
  #tt{position:fixed !important;left:50% !important;transform:translateX(-50%);
    bottom:12px !important;top:auto !important;
    width:min(320px, calc(100vw - 24px)) !important;
    max-height:75vh;overflow-y:auto;box-shadow:0 -4px 24px rgba(0,0,0,.5)}
  #tt-close{display:flex !important}
  .nd circle.bg{stroke-width:2}
  .nd.pressing circle.bg{stroke:var(--hl)!important;stroke-width:3!important;
    transition:stroke .1s,stroke-width .1s}
  #tt-img,#tt-ph{width:100% !important;height:160px !important}
  #tt-wiki-btn{padding:10px 0 !important;font-size:13px !important}
  .hb,.tb{padding:5px 10px !important;font-size:12px !important}
}
</style></head>
<body style="display:flex;flex-direction:column">
<div id="ov"><h2>🌿 系統図を準備中…</h2>
  <p id="om">データ解析中</p>
  <div class="pb"><div class="pi" id="pi"></div></div>
</div>
<div id="hdr">
  <div id="ttl"><em>__TITLE__</em> 系統図</div>
  <input id="srch" placeholder="検索…"
    onkeydown="if(event.key==='Enter')doSrch(document.getElementById('srch').value)">
  <button id="srch-btn" onclick="doSrch(document.getElementById('srch').value)">🔍</button>
  <button id="srch-clr" onclick="clearSrch()" title="検索をクリア">✕</button>
  <button class="hb" onclick="expandTo('family')">科まで</button>
  <button class="hb" onclick="expandTo('genus')">属まで</button>
  <button class="hb" onclick="expandTo('species')">全展開</button>
  <button class="hb" onclick="collapseAll()">折りたたむ</button>
  <button class="hb" onclick="fitV(false)">全体表示</button>
  <div class="ctrl">
    <button class="tb" id="btn-theme" onclick="toggleTheme()" title="テーマ切り替え">🌙</button>
  </div>
  <div class="ctrl">
    <button class="tb active" id="btn-ja" onclick="setLang('ja')">JA</button>
    <button class="tb"        id="btn-en" onclick="setLang('en')">EN</button>
  </div>
  <div class="ctrl">
    <button class="tb active" id="btn-lr" onclick="setLayout('lr')">LR</button>
    <button class="tb"        id="btn-tb" onclick="setLayout('tb')">TB</button>
    <button class="tb"        id="btn-rd" onclick="setLayout('rd')" title="円形レイアウト">RD</button>
  </div>
  <div class="ctrl">
    <button class="tb active" id="btn-icon" onclick="toggleIcons()" title="画像アイコン ON/OFF">🖼</button>
  </div>
  <div class="ctrl">
    <button class="tb active" id="btn-iucn-all"     onclick="setIucnFilter('all')"         title="全て表示">全</button>
    <button class="tb"        id="btn-iucn-no-ex"   onclick="setIucnFilter('no-extinct')"  title="絶滅種を除外">絶滅除外</button>
    <button class="tb"        id="btn-iucn-only-ex" onclick="setIucnFilter('only-extinct')" title="絶滅種のみ表示">絶滅のみ</button>
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
  <span id="leg-hint" style="margin-left:7px">▶クリックで展開 ／ ドラッグ・ホイールでナビ</span>
  <div id="iucn-leg">
    <span style="color:var(--txt3)">IUCN:</span>
    <span class="li" style="color:#dc2626">&#9632; CR</span>
    <span class="li" style="color:#ea580c">&#9632; EN</span>
    <span class="li" style="color:#d97706">&#9632; VU</span>
    <span class="li" style="color:#65a30d">&#9632; NT</span>
    <span class="li" style="color:#16a34a">&#9632; LC</span>
    <span class="li" style="color:#6b7280">&#9632; EX</span>
  </div>
  <button id="iucn-leg-toggle"
    style="background:transparent;border:1px solid var(--brd);color:var(--txt3);
      border-radius:8px;padding:1px 6px;font-size:9px;cursor:pointer;
      white-space:nowrap;margin-left:4px"
    onclick="(function(){
      const el  = document.getElementById('iucn-leg');
      const btn = document.getElementById('iucn-leg-toggle');
      const show = el.style.display === 'none' || el.style.display === '';
      el.style.display  = show ? 'flex' : 'none';
      btn.textContent   = show ? 'IUCN \u25b2' : 'IUCN \u25bc';
    })()">IUCN &#9660;</button>
  <div id="leg-sizer">
    <label>&#8596; TT</label>
    <input type="range" id="tt-size-slider"
      min="180" max="420" step="10" value="280"
      oninput="setTTWidth(+this.value)">
  </div>
</div>
<div id="main">
  <svg id="tree"></svg>
  <div id="tt">
    <div id="tt-close"
      style="display:none;justify-content:flex-end;padding:6px 8px 0;cursor:pointer"
      onclick="tt.style.display='none'">
      <span style="font-size:18px;line-height:1;color:var(--txt3)">&#10005;</span>
    </div>
    <img id="tt-img" src="" alt="" crossorigin="anonymous"
         onerror="this.classList.add('hidden');
           document.getElementById('tt-ph').classList.remove('hidden')">
    <div id="tt-ph" class="hidden">&#127807;</div>
    <div id="tt-body">
      <div id="tt-rank"></div>
      <div id="tt-name"></div>
      <div id="tt-ja"></div>
      <div id="tt-meta">
        <span id="tt-cnt"></span>
        <span id="tt-credit"></span>
      </div>
      <div id="tt-iucn"></div>
      <div id="tt-wiki" style="display:none;margin-top:6px">
        <button id="tt-wiki-btn"
          style="width:100%;padding:4px 0;font-size:10px;cursor:pointer;
            background:transparent;border:1px solid var(--brd);
            border-radius:6px;color:var(--hl);pointer-events:all"
          onclick="openWiki(currentTTNode)"></button>
      </div>
    </div>
  </div>
  <div id="foot">QID: __QID__ &nbsp;|&nbsp; 画像: Wikimedia Commons &nbsp;|&nbsp; 生成: __DATE__</div>
</div>
<script>
__DATA_BLOCK__

// ─── 定数 ─────────────────────────────────────────────────────────
const RANK_ORD = [
  "domain","kingdom","subkingdom","phylum","subphylum","superclass",
  "class","subclass","infraclass","superorder","order","suborder","infraorder",
  "superfamily","family","subfamily","tribe","subtribe","genus","subgenus",
  "species","subspecies","variety","form"
];
const RC = {
  domain:"var(--c-domain)",kingdom:"var(--c-kingdom)",phylum:"var(--c-phylum)",
  subphylum:"var(--c-phylum)",superclass:"var(--c-class)",class:"var(--c-class)",
  subclass:"var(--c-class)",infraclass:"var(--c-class)",
  superorder:"var(--c-order)",order:"var(--c-order)",suborder:"var(--c-suborder)",
  infraorder:"var(--c-infraorder)",superfamily:"var(--c-superfamily)",
  family:"var(--c-family)",subfamily:"var(--c-subfamily)",
  tribe:"var(--c-tribe)",subtribe:"var(--c-tribe)",
  genus:"var(--c-genus)",subgenus:"var(--c-genus)",
  species:"var(--c-species)",subspecies:"var(--c-subspecies)",
  variety:"var(--c-variety)",form:"var(--c-variety)",unknown:"var(--c-unknown)"
};
const RR_BASE = {
  domain:10,kingdom:9,phylum:8,subphylum:7,superclass:7,class:7,
  subclass:6,infraclass:6,superorder:6,order:6,suborder:5,infraorder:5,
  superfamily:5,family:4.5,subfamily:4,tribe:3.5,subtribe:3.5,
  genus:3,subgenus:3,species:2,subspecies:1.8,variety:1.8,form:1.8,unknown:2
};
const RJ = {
  domain:"域",kingdom:"界",subkingdom:"亜界",phylum:"門",subphylum:"亜門",
  superclass:"上綱",class:"綱",subclass:"亜綱",infraclass:"下綱",
  superorder:"上目",order:"目",suborder:"亜目",infraorder:"下目",
  superfamily:"上科",family:"科",subfamily:"亜科",tribe:"族",subtribe:"亜族",
  genus:"属",subgenus:"亜属",species:"種",subspecies:"亜種",
  variety:"変種",form:"品種",unknown:"?"
};
const IMG_R = 11;   // 画像アイコン半径(px)

// ─── 状態変数 ────────────────────────────────────────────────────
let langMode   = localStorage.getItem("taxa_lang")   || "ja";
let layoutMode = localStorage.getItem("taxa_layout") || "lr";
let showIcons  = localStorage.getItem("taxa_icons")  !== "0";

// ─── ノードサイズ・テキスト位置 ──────────────────────────────────
function nodeR(d) {
  if (showIcons && d.data.image_url &&
      ["species","subspecies","variety","form"].includes(d.data.rank))
    return IMG_R;
  return RR_BASE[d.data.rank] || 2;
}
function textX(d) {
  const r = nodeR(d);
  return hk(d) ? -(r + 5) : (r + 5);
}

// ─── 言語ヘルパー ────────────────────────────────────────────────
function getLabels(d) {
  const sci = d.data.name || "";
  const ja  = d.data.ja   || "";
  return langMode === "ja"
    ? { primary: ja || sci, secondary: ja ? sci : "" }
    : { primary: sci,       secondary: ja };
}

// ─── テキスト属性 ────────────────────────────────────────────────
function applyPrimaryAttrs(sel) {
  if (layoutMode === "rd") {
    sel.attr("transform", d => {
          const angle = d.x * 180 / Math.PI - 90;
          const flip  = d.x > Math.PI;  // 左半分は反転
          const r     = nodeR(d) + 5;
          return `rotate(${angle}) translate(${hk(d) ? -r : r},0)${flip ? " rotate(180)" : ""}`;
        })
       .attr("writing-mode", null)
       .attr("x", 0).attr("y", 0).attr("dy", "0.35em")
       .attr("text-anchor", d => {
          const flip = d.x > Math.PI;
          return (hk(d) ? (flip ? "start" : "end") : (flip ? "end" : "start"));
        });
    return;
  }
  sel.attr("transform",    d => tbEnTransform(d, false))
     .attr("writing-mode", () => tbJaWritingMode())
     .attr("x", d => layoutMode === "lr" ? textX(d)
       : (langMode === "ja" ? (hk(d) ? -4 : 4) : 0))
     .attr("y", d => layoutMode !== "tb" ? null
       : (langMode === "ja" ? (hk(d) ? -nodeR(d)-3 : nodeR(d)+3) : nodeR(d)+2))
     .attr("dy",          () => layoutMode === "lr" ? "0em" : null)
     .attr("text-anchor", d => primaryAnchor(d));
}
function applySecondaryAttrs(sel) {
  if (layoutMode === "rd") {
    sel.attr("transform", d => {
          const angle = d.x * 180 / Math.PI - 90;
          const flip  = d.x > Math.PI;
          const r     = nodeR(d) + 5;
          return `rotate(${angle}) translate(${hk(d) ? -r : r},0)${flip ? " rotate(180)" : ""}`;
        })
       .attr("writing-mode", null)
       .attr("x", 0).attr("y", 0).attr("dy", "1.5em")
       .attr("text-anchor", d => {
          const flip = d.x > Math.PI;
          return (hk(d) ? (flip ? "start" : "end") : (flip ? "end" : "start"));
        });
    return;
  }
  sel.attr("transform",    d => tbEnTransform(d, true))
     .attr("writing-mode", () => tbJaWritingMode())
     .attr("x", d => layoutMode === "lr" ? textX(d)
       : (langMode === "ja" ? (hk(d) ? -14 : 14) : 0))
     .attr("y", d => layoutMode !== "tb" ? null
       : (langMode === "ja" ? (hk(d) ? -nodeR(d)-3 : nodeR(d)+3) : nodeR(d)+14))
     .attr("dy",          () => layoutMode === "lr" ? "1.5em" : null)
     .attr("text-anchor", d => primaryAnchor(d));
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

// ─── テーマ・言語・レイアウト・アイコン ─────────────────────────
function toggleTheme() {
  const next = document.documentElement.getAttribute("data-theme") === "dark"
    ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  document.getElementById("btn-theme").textContent = next === "dark" ? "🌙" : "☀️";
  localStorage.setItem("taxa_theme", next);
}
function setLang(mode) {
  langMode = mode;
  localStorage.setItem("taxa_lang", mode);
  document.getElementById("btn-ja").classList.toggle("active", mode === "ja");
  document.getElementById("btn-en").classList.toggle("active", mode === "en");
  document.getElementById("srch").placeholder = mode === "ja" ? "検索…" : "Search…";
  if (layoutMode === "tb" || layoutMode === "rd") update(root); else applyLangOnly();
}
function applyLangOnly() {
  g.selectAll(".nd").each(function(d) {
    const lb = getLabels(d);
    d3.select(this).select(".primary-lbl").text(lb.primary);
    d3.select(this).select(".secondary-lbl").text(lb.secondary);
  });
}
function setLayout(mode) {
  layoutMode = mode;
  localStorage.setItem("taxa_layout", mode);
  document.getElementById("btn-lr").classList.toggle("active", mode === "lr");
  document.getElementById("btn-tb").classList.toggle("active", mode === "tb");
  const btnRd = document.getElementById("btn-rd");
  if (btnRd) btnRd.classList.toggle("active", mode === "rd");
  // radial は size() で全体角度と半径を指定する（nodeSize ではなく）
  if (mode === "rd") {
    lay.size([2 * Math.PI, 420]).nodeSize(null);
  } else {
    lay.nodeSize(layoutNodeSize()).size(null);
  }
  update(root);
  setTimeout(() => fitV(false), 260);
}
function layoutNodeSize() {
  if (layoutMode === "rd") return null;  // radial は lay.size() で制御
  return layoutMode === "lr" ? [18, 200] : [110, 75];
}
function toggleIcons() {
  showIcons = !showIcons;
  localStorage.setItem("taxa_icons", showIcons ? "1" : "0");
  document.getElementById("btn-icon").classList.toggle("active", showIcons);
  update(root);
}

// ─── D3 セットアップ ────────────────────────────────────────────
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
  const pi = document.getElementById("pi");
  const om = document.getElementById("om");
  if (pi) pi.style.width = p + "%";
  if (om && m) om.textContent = m;
};

// ─── 初期化 ─────────────────────────────────────────────────────
function init() {
  const savedTheme = localStorage.getItem("taxa_theme") || "dark";
  langMode   = localStorage.getItem("taxa_lang")   || "ja";
  layoutMode = localStorage.getItem("taxa_layout") || "lr";
  showIcons  = localStorage.getItem("taxa_icons")  !== "0";

  document.documentElement.setAttribute("data-theme", savedTheme);
  document.getElementById("btn-theme").textContent = savedTheme === "dark" ? "🌙" : "☀️";
  document.getElementById("btn-ja").classList.toggle("active", langMode === "ja");
  document.getElementById("btn-en").classList.toggle("active", langMode === "en");
  document.getElementById("btn-lr").classList.toggle("active", layoutMode === "lr");
  document.getElementById("btn-tb").classList.toggle("active", layoutMode === "tb");
  const _btnRd = document.getElementById("btn-rd");
  if (_btnRd) _btnRd.classList.toggle("active", layoutMode === "rd");
  if (layoutMode === "rd") lay.size([2 * Math.PI, 420]).nodeSize(null);
  else lay.nodeSize(layoutNodeSize()).size(null);
  document.getElementById("btn-icon").classList.toggle("active", showIcons);
  document.getElementById("srch").placeholder = langMode === "ja" ? "検索…" : "Search…";
  lay.nodeSize(layoutNodeSize());

  // ツールチップ幅を復元
  const storedW = parseInt(localStorage.getItem("taxa_tt_w") || "280");
  document.documentElement.style.setProperty("--tt-w", storedW + "px");
  const sl = document.getElementById("tt-size-slider");
  if (sl) sl.value = storedW;

  if (isTouchDev) {
    const hint = document.getElementById("leg-hint");
    if (hint) hint.textContent = "▶タップで展開 ／ 長押しで詳細";
  }

  prog(20, "ツリー解析中…");
  root = d3.hierarchy(DATA);
  root.x0 = 0; root.y0 = 0;
  const genusIdx = RANK_ORD.indexOf("genus");
  root.descendants().forEach(d => {
    const ri = RANK_ORD.indexOf(d.data.rank);
    if (ri >= genusIdx && d.children) { d._children = d.children; d.children = null; }
  });
  prog(50, "描画中…");
  update(root);
  prog(85, "調整中…");
  setTimeout(() => {
    fitV(true);
    prog(100, "完了");
    setTimeout(() => {
      const ov = document.getElementById("ov");
      if (ov) ov.style.display = "none";
    }, 250);
    updStat();
  }, 80);
}

// ─── clipPath プール ─────────────────────────────────────────────
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
  const W  = mainEl.clientWidth, H = mainEl.clientHeight;
  const tr = d3.transition().duration(220);
  const sx = layoutMode === "rd" ? src.x : (layoutMode === "lr" ? src.x : src.y);
  const sy = layoutMode === "rd" ? src.y : (layoutMode === "lr" ? src.y : src.x);

  svg.attr("width", W).attr("height", H);
  lay(root);

  // リンク
  const lk = g.selectAll(".lk").data(root.links(), d => d.target.data.id);
  lk.enter().append("path").attr("class","lk")
    .attr("d", () => dO(sx, sy))
    .merge(lk).transition(tr)
    .attr("d", d => linkPath(d.source, d.target));
  lk.exit().transition(tr).attr("d", () => dO(sx, sy)).remove();

  // ノード
  const nd = g.selectAll(".nd").data(root.descendants(), d => d.data.id);
  const ne = nd.enter().append("g")
    .attr("class", d => {
      const parts = ["nd"];
      const s = d.data.fetch_strategy;
      if (s === "prefix")          parts.push("strategy-prefix");
      else if (s === "gbif")       parts.push("strategy-gbif");
      else if (s === "incomplete") parts.push("strategy-incomplete");
      if (d.data.iucn) parts.push("iucn-" + d.data.iucn);
      return parts.join(" ");
    })
    .attr("transform", _ => `translate(${sy},${sx})`)
    .on("click", (e, d) => {
      if (isTouchDev) return;
      const isLeaf = ["species","subspecies","variety","form"].includes(d.data.rank);
      if (isLeaf && !d.children && !d._children) { openWiki(d); }
      else { tog(d); update(d); }
      e.stopPropagation();
    })
    .on("mouseover", (e, d) => { if (!isTouchDev) showTT(e, d); })
    .on("mousemove", (e, d) => { if (!isTouchDev) movTT(e); })
    .on("mouseout",  ()     => { if (!isTouchDev) schedulHide(); })
    .on("touchstart", (e, d) => { e.stopPropagation(); startLongPress(e, d); }, {passive:true})
    .on("touchend",   (e, d) => { e.stopPropagation(); endTouch(e, d); })
    .on("touchmove",  ()     => { cancelLongPress(); }, {passive:true});

  ne.append("circle").attr("class","bg").attr("r", 0)
    .attr("fill",         d => RC[d.data.rank] || RC.unknown)
    .attr("stroke",       d => RC[d.data.rank] || RC.unknown)
    .attr("fill-opacity", d => d._children ? .35 : 1);

  ne.each(function(d) {
    if (!d.data.image_url) return;
    const sel = d3.select(this);
    const cid = ensureClip(d.data.id);
    sel.append("image").attr("class","species-img")
      .attr("href","").attr("data-src", d.data.image_url)
      .attr("crossOrigin","anonymous")
      .attr("x", -IMG_R).attr("y", -IMG_R)
      .attr("width", IMG_R*2).attr("height", IMG_R*2)
      .attr("clip-path", `url(#${cid})`)
      .attr("preserveAspectRatio","xMidYMid slice")
      .attr("opacity", 0);
    sel.append("circle").attr("class","img-ring")
      .attr("r", 0).attr("fill","none")
      .attr("stroke", RC[d.data.rank] || RC.unknown);
  });

  const nePri = ne.append("text").attr("class","primary-lbl")
    .text(d => getLabels(d).primary);
  applyPrimaryAttrs(nePri);
  const neSec = ne.filter(d => RANK_ORD.indexOf(d.data.rank) <= RANK_ORD.indexOf("family"))
    .append("text").attr("class","secondary-lbl")
    .text(d => getLabels(d).secondary);
  applySecondaryAttrs(neSec);

  const nm = ne.merge(nd);
  nm.transition(tr).attr("transform", d => nodeTransform(d));
  nm.select("circle.bg").transition(tr)
    .attr("r", d => (showIcons && d.data.image_url) ? 0 : (RR_BASE[d.data.rank] || 2))
    .attr("fill",         d => RC[d.data.rank] || RC.unknown)
    .attr("stroke",       d => RC[d.data.rank] || RC.unknown)
    .attr("fill-opacity", d => d._children ? .35 : 1);
  nm.select("image.species-img").transition(tr)
    .attr("opacity", d => (showIcons && d.data.image_url) ? 1 : 0);
  nm.select("circle.img-ring").transition(tr)
    .attr("r",       d => (showIcons && d.data.image_url) ? IMG_R + 1.5 : 0)
    .attr("opacity", d => (showIcons && d.data.image_url) ? 0.9 : 0);
  applyPrimaryAttrs(nm.select(".primary-lbl").text(d => getLabels(d).primary));
  applySecondaryAttrs(nm.select(".secondary-lbl").text(d => getLabels(d).secondary));

  nd.exit().transition(tr)
    .attr("transform", _ =>
      `translate(${layoutMode==="lr"?src.y:src.x},${layoutMode==="lr"?src.x:src.y})`)
    .style("opacity", 0).remove();
  root.descendants().forEach(d => { d.x0 = d.x; d.y0 = d.y; });

  scheduleImageLoad();
}

// ─── レイアウト補助 ──────────────────────────────────────────────
function nodeTransform(d) {
  if (layoutMode === "rd") {
    const x = d.y * Math.cos(d.x - Math.PI / 2);
    const y = d.y * Math.sin(d.x - Math.PI / 2);
    return `translate(${x},${y})`;
  }
  return layoutMode === "lr"
    ? `translate(${d.y},${d.x})`
    : `translate(${d.x},${d.y})`;
}
function rdXY(d) {
  return [d.y * Math.cos(d.x - Math.PI/2), d.y * Math.sin(d.x - Math.PI/2)];
}
function linkPath(s, t) {
  if (layoutMode === "rd") {
    const [sx, sy] = rdXY(s), [tx, ty] = rdXY(t);
    // 中間点は親の半径で子の角度の点
    const mx = s.y * Math.cos(t.x - Math.PI/2);
    const my = s.y * Math.sin(t.x - Math.PI/2);
    return `M${sx},${sy}C${mx},${my} ${tx},${ty} ${tx},${ty}`;
  }
  if (layoutMode === "lr") {
    const m = (s.y + t.y) / 2;
    return `M${s.y},${s.x}C${m},${s.x} ${m},${t.x} ${t.y},${t.x}`;
  }
  const m = (s.y + t.y) / 2;
  return `M${s.x},${s.y}C${s.x},${m} ${t.x},${m} ${t.x},${t.y}`;
}
function dO(a, b) {
  if (layoutMode === "rd") {
    const x = b * Math.cos(a - Math.PI/2);
    const y = b * Math.sin(a - Math.PI/2);
    return `M${x},${y}C${x},${y} ${x},${y} ${x},${y}`;
  }
  return layoutMode === "lr"
    ? `M${a},${b}C${a},${b} ${a},${b} ${a},${b}`
    : `M${b},${a}C${b},${a} ${b},${a} ${b},${a}`;
}
const hk  = d => d.children || d._children;
const tog = d => {
  if (d.children) { d._children = d.children; d.children = null; }
  else            { d.children = d._children; d._children = null; }
};

// ─── ツリー操作 ─────────────────────────────────────────────────
function expandTo(rank) {
  const ti = RANK_ORD.indexOf(rank);
  if (ti < 0) return;
  root.descendants().forEach(d => {
    const di = RANK_ORD.indexOf(d.data.rank);
    if (di < ti && d._children) { d.children = d._children; d._children = null; }
    if (di >= ti && d.children) { d._children = d.children; d.children = null; }
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
    .translate(W/2 - sc*(bb.x + bb.width/2), H/2 - sc*(bb.y + bb.height/2))
    .scale(sc);
  if (instant) svg.call(zm.transform, t);
  else         svg.transition().duration(500).call(zm.transform, t);
}
function updStat() {
  const d   = root.descendants();
  const sp  = d.filter(x => x.data.rank === "species").length;
  const ge  = d.filter(x => x.data.rank === "genus").length;
  const fa  = d.filter(x => x.data.rank === "family").length;
  const im  = d.filter(x => x.data.image_url).length;
  // IUCN 集計（EX/EW/CR/EN/VU のみ表示、0件は省略）
  const IUCN_STAT = [
    ["EX", "#6b7280"], ["EW", "#9ca3af"],
    ["CR", "#dc2626"], ["EN", "#ea580c"], ["VU", "#d97706"],
  ];
  const iucnHtml = IUCN_STAT
    .map(([code, color]) => {
      const cnt = d.filter(x => x.data.iucn === code).length;
      if (!cnt) return "";
      return `<span style="color:${color};font-size:10px;white-space:nowrap">&#9632; ${code}:${cnt}</span>`;
    }).join("");
  document.getElementById("stat").innerHTML =
    `<span><span class="sd" style="background:var(--c-species)"></span>${sp.toLocaleString()}種</span>` +
    `<span><span class="sd" style="background:var(--c-genus)"></span>${ge.toLocaleString()}属</span>` +
    `<span><span class="sd" style="background:var(--c-family)"></span>${fa.toLocaleString()}科</span>` +
    (iucnHtml ? `<span style="display:flex;gap:5px;align-items:center;margin-left:4px;padding-left:7px;border-left:1px solid var(--brd)">${iucnHtml}</span>` : "") +
    (im ? `<span style="color:var(--txt3);font-size:10px">📷${im.toLocaleString()}</span>` : "");
}

// ─── IUCN フィルター ─────────────────────────────────────────────
let iucnFilter = "all";   // "all" | "no-extinct" | "only-extinct"
const EXTINCT_CODES = new Set(["EX", "EW"]);

function setIucnFilter(mode) {
  iucnFilter = mode;
  [["btn-iucn-all","all"],["btn-iucn-no-ex","no-extinct"],["btn-iucn-only-ex","only-extinct"]]
    .forEach(([id, m]) => {
      const el = document.getElementById(id);
      if (el) el.classList.toggle("active", m === mode);
    });
  applyIucnFilter();
}
function applyIucnFilter() {
  if (iucnFilter === "all") {
    if (!document.getElementById("srch").value.trim()) {
      g.selectAll(".nd").classed("nm", false);
    } else {
      doSrch(document.getElementById("srch").value);
      return;
    }
    updStat();
    return;
  }
  const show = new Set();
  walkAll(root, d => {
    const isExtinct = EXTINCT_CODES.has(d.data.iucn || "");
    const match = (iucnFilter === "no-extinct") ? !isExtinct : isExtinct;
    if (match) {
      show.add(d.data.id);
      let p = d.parent;
      while (p) { show.add(p.data.id); p = p.parent; }
    }
  });
  g.selectAll(".nd").classed("nm", d => !show.has(d.data.id));
  updStat();
}

// ─── 検索 ───────────────────────────────────────────────────────
function walkAll(node, fn) {
  fn(node);
  (node.children || node._children || []).forEach(c => walkAll(c, fn));
}
function clearSrch() {
  document.getElementById("srch").value = "";
  document.getElementById("srch-clr").style.display = "none";
  g.selectAll(".nd").classed("nh", false).classed("nm", false);
  update(root);
}
function doSrch(q) {
  const v = q.trim().toLowerCase();
  document.getElementById("srch-clr").style.display = v ? "inline-block" : "none";
  g.selectAll(".nd").classed("nh", false).classed("nm", false);
  if (!v) { update(root); return; }

  const hit       = new Set();
  const hitDirect = new Set();
  walkAll(root, d => {
    const name = (d.data.name || "").toLowerCase();
    const ja   = (d.data.ja   || "").toLowerCase();
    if (name.includes(v) || ja.includes(v)) {
      hitDirect.add(d.data.id);
      hit.add(d.data.id);
      let p = d.parent;
      while (p) {
        hit.add(p.data.id);
        if (p._children) { p.children = p._children; p._children = null; }
        p = p.parent;
      }
    }
  });
  walkAll(root, d => {
    if (hitDirect.has(d.data.id) && d._children) {
      d.children = d._children; d._children = null;
    }
  });
  update(root);
  g.selectAll(".nd")
    .classed("nh", d => hitDirect.has(d.data.id))
    .classed("nm", d => !hit.has(d.data.id));
  if (hit.size > 0) setTimeout(() => fitV(false), 260);
}

// ─── 画像レイジーロード（ズーム閾値 + デバウンス + レートキュー）
// IMG_ZOOM_MIN:    この倍率未満では画像ロードしない
// IMG_DEBOUNCE_MS: ズーム操作停止後に待つ時間(ms)
// IMG_RATE_PER_SEC: 1秒あたりの最大リクエスト数（Wikimedia 429 対策）
const IMG_ZOOM_MIN     = 0.35;
const IMG_DEBOUNCE_MS  = 1500;
const IMG_RATE_PER_SEC = 4;

const _imgQueue = [];
let   _queueTimer = null;

function _startQueue() {
  if (_queueTimer) return;
  _queueTimer = setInterval(() => {
    if (_imgQueue.length === 0) {
      clearInterval(_queueTimer); _queueTimer = null; return;
    }
    _imgQueue.splice(0, IMG_RATE_PER_SEC).forEach(({el, src}) => {
      if (!el.attr("href")) el.attr("href", src);
    });
  }, 1000);
}
function _enqueueVisible() {
  const t    = d3.zoomTransform(svg.node());
  if (t.k < IMG_ZOOM_MIN) return;
  const svgR = mainEl.getBoundingClientRect();
  g.selectAll("image.species-img").each(function() {
    const el  = d3.select(this);
    const src = el.attr("data-src");
    if (!src || el.attr("href")) return;
    if (_imgQueue.some(q => q.src === src)) return;
    const nd = d3.select(this.parentNode).datum();
    if (!nd) return;
    const sx  = layoutMode === "lr" ? nd.y : nd.x;
    const sy  = layoutMode === "lr" ? nd.x : nd.y;
    const px  = t.applyX(sx), py = t.applyY(sy);
    const m   = 100;
    if (px > -m && px < svgR.width+m && py > -m && py < svgR.height+m) {
      _imgQueue.push({el, src});
    }
  });
  _startQueue();
}
let _imgDebounce = null;
function scheduleImageLoad() {
  clearTimeout(_imgDebounce);
  _imgDebounce = setTimeout(_enqueueVisible, IMG_DEBOUNCE_MS);
}
zm.on("zoom.lazyimg", () => clearTimeout(_imgDebounce));
zm.on("end.lazyimg",  scheduleImageLoad);

// ─── デバイス判定 ────────────────────────────────────────────────
const isTouchDev = window.matchMedia("(pointer: coarse)").matches;

// ─── Wikipedia リンク ────────────────────────────────────────────
function openWiki(d) {
  const sci   = d.data.name || "";
  const ja    = d.data.ja   || "";
  const enUrl = `https://en.wikipedia.org/wiki/${encodeURIComponent(sci)}`;
  const jaUrl = `https://ja.wikipedia.org/wiki/${encodeURIComponent(ja)}`;
  if (langMode === "ja" && ja) {
    const api = `https://ja.wikipedia.org/w/api.php?action=query`
              + `&titles=${encodeURIComponent(ja)}&prop=info&format=json&origin=*`;
    fetch(api)
      .then(r => r.json())
      .then(data => {
        const page = Object.values(data.query?.pages || {})[0];
        window.open(page?.missing !== undefined ? enUrl : jaUrl, "_blank", "noopener");
      })
      .catch(() => window.open(jaUrl, "_blank", "noopener"));
  } else {
    window.open(enUrl, "_blank", "noopener");
  }
}

// ─── ツールチップ ────────────────────────────────────────────────
// hide delay  : 300ms → ノードを離れてから消えるまでの猶予
// 近傍マージン: 15px  → ツールチップ周囲をこの距離移動中は hide をキャンセル
const tt = document.getElementById("tt");
let currentTTNode = null;
let _hideTimer    = null;

// ツールチップ幅（凡例バーのスライダーで調整、localStorage に保存）
let _ttW = parseInt(localStorage.getItem("taxa_tt_w") || "280");
function setTTWidth(w) {
  _ttW = w;
  document.documentElement.style.setProperty("--tt-w", w + "px");
  localStorage.setItem("taxa_tt_w", w);
}

function schedulHide() {
  _hideTimer = setTimeout(() => { tt.style.display = "none"; }, 450);
}
function cancelHide() {
  if (_hideTimer) { clearTimeout(_hideTimer); _hideTimer = null; }
}
tt.addEventListener("mouseenter", cancelHide);
tt.addEventListener("mouseleave", schedulHide);

// 近傍ガード: ノードとツールチップ間の移動中に消えにくくする
mainEl.addEventListener("mousemove", e => {
  if (tt.style.display === "none" || !_hideTimer) return;
  const tr = tt.getBoundingClientRect();
  const m  = 15;
  if (e.clientX >= tr.left-m && e.clientX <= tr.right+m &&
      e.clientY >= tr.top-m  && e.clientY <= tr.bottom+m) {
    cancelHide();
  }
});

// ─── 長押し（タッチ） ────────────────────────────────────────────
// LP_MS: 長押し判定時間(ms)
let _lpTimer = null, _lpFired = false, _lpNode = null;
const LP_MS  = 480;

function startLongPress(e, d) {
  cancelLongPress();
  _lpFired = false; _lpNode = d;
  d3.select(e.currentTarget).classed("pressing", true);
  _lpTimer = setTimeout(() => {
    _lpFired = true;
    d3.select(e.currentTarget).classed("pressing", false);
    showTTTouch(d);
  }, LP_MS);
}
function cancelLongPress() {
  if (_lpTimer) { clearTimeout(_lpTimer); _lpTimer = null; }
  g.selectAll(".nd").classed("pressing", false);
}
function endTouch(e, d) {
  cancelLongPress();
  if (_lpFired) return;
  const isLeaf = ["species","subspecies","variety","form"].includes(d.data.rank);
  if (isLeaf && !d.children && !d._children) { openWiki(d); }
  else { tog(d); update(d); }
}
function showTTTouch(d) {
  showTT({ clientX: 0, clientY: 0 }, d);
  tt.style.left = "";
  tt.style.top  = "";
}
mainEl.addEventListener("touchstart", e => {
  if (!tt.contains(e.target) && !e.target.closest(".nd")) {
    tt.style.display = "none";
  }
}, {passive: true});

// ─── ツールチップ表示 ────────────────────────────────────────────
const IUCN_META = {
  EX: ["絶滅 EX",       "#6b7280", "rgba(107,114,128,.15)"],
  EW: ["野生絶滅 EW",   "#9ca3af", "rgba(156,163,175,.15)"],
  CR: ["深刻な危機 CR", "#dc2626", "rgba(220,38,38,.15)"],
  EN: ["危機 EN",       "#ea580c", "rgba(234,88,12,.15)"],
  VU: ["危急 VU",       "#d97706", "rgba(217,119,6,.15)"],
  NT: ["準危急 NT",     "#65a30d", "rgba(101,163,13,.15)"],
  LC: ["低危険 LC",     "#16a34a", "rgba(22,163,74,.15)"],
  DD: ["情報不足 DD",   "#64748b", "rgba(100,116,139,.15)"],
};

function showTT(e, d) {
  const lb = getLabels(d);
  const ch = (d.children ?? d._children ?? []).length;
  const strategyBadge = {
    "prefix":     " 🔤 [A補完]",
    "gbif":       " 🌐 [B補完]",
    "incomplete": " ⚠ [データ不完全]",
  }[d.data.fetch_strategy] || "";

  document.getElementById("tt-rank").textContent =
    (RJ[d.data.rank] || d.data.rank) + strategyBadge;
  document.getElementById("tt-name").textContent = lb.primary;
  document.getElementById("tt-ja").textContent   = lb.secondary;
  document.getElementById("tt-cnt").textContent  = ch ? `直下: ${ch}件` : "";

  const imgEl    = document.getElementById("tt-img");
  const phEl     = document.getElementById("tt-ph");
  const creditEl = document.getElementById("tt-credit");

  if (d.data.image_url) {
    const large = d.data.image_url
      .replace(/\/\d+px-/, "/250px-")
      .replace(/[?&]width=\d+/, "?width=250");
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

  // IUCN バッジ
  const iucnEl = document.getElementById("tt-iucn");
  const ic     = d.data.iucn || "";
  if (ic && IUCN_META[ic]) {
    const [label, color, bg] = IUCN_META[ic];
    iucnEl.textContent      = "IUCN: " + label;
    iucnEl.style.display    = "block";
    iucnEl.style.color      = color;
    iucnEl.style.background = bg;
    iucnEl.style.border     = "1px solid " + color;
  } else {
    iucnEl.style.display = "none";
  }

  // Wikipedia ボタン
  const wikiDiv = document.getElementById("tt-wiki");
  const wikiBtn = document.getElementById("tt-wiki-btn");
  wikiBtn.textContent    = langMode === "ja" ? "Wikipedia で開く ↗" : "Open in Wikipedia ↗";
  wikiDiv.style.display  = "block";
  currentTTNode = d;
  tt.style.display = "block";
  movTT(e);
}
function movTT(e) {
  const r    = mainEl.getBoundingClientRect();
  const tx   = e.clientX - r.left;
  const ty   = e.clientY - r.top;
  const w    = _ttW;
  const left = (tx + w + 20 > r.width) ? tx - w - 6 : tx + 14;
  tt.style.left = left + "px";
  const ttH = tt.offsetHeight || (w * 10/16 + 140);
  tt.style.top  = Math.min(ty - 10, r.height - ttH - 10) + "px";
}

// ─── リサイズ / 起動 ─────────────────────────────────────────────
let rsz;
window.addEventListener("resize", () => {
  clearTimeout(rsz);
  rsz = setTimeout(() => {
    svg.attr("width", mainEl.clientWidth).attr("height", mainEl.clientHeight);
  }, 200);
});
window.addEventListener("load", init);
</script></body></html>"""

# ─────────────────────────────────────────────────────────────────
#  SPA ランディング（index.html）用の HEAD テンプレート
#  CSS・DOM の基盤部分のみを含む。
#  ビューワーの CSS と JS は make_index_html() が HTML から抽出して注入する。
#  プレースホルダ: __DATE__ / __VIEWER_CSS__ / __VIEWER_JS__ / __TAXA_JS__
# ─────────────────────────────────────────────────────────────────

_SPA_HEAD = '<!DOCTYPE html>\n<html lang="ja" data-theme="dark"><head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width,initial-scale=1">\n<title>系統図</title>\n<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>\n<style>\n*{box-sizing:border-box;margin:0;padding:0}\n:root{\n  --bg:#0d1117;--bg2:#161b22;--bg3:#21262d;\n  --txt:#e6edf3;--txt2:#8b949e;--txt3:#555d6b;\n  --brd:#30363d;--hl:#f0b429;--grn:#3fb950;\n}\n[data-theme="light"]{\n  --bg:#ffffff;--bg2:#f6f8fa;--bg3:#eaeef2;\n  --txt:#1f2328;--txt2:#444c56;--txt3:#768390;\n  --brd:#d0d7de;--hl:#b45309;--grn:#1a7f37;\n}\nhtml,body{height:100%;background:var(--bg);color:var(--txt);\n  font-family:\'Hiragino Sans\',\'Yu Gothic\',Meiryo,\'Noto Sans JP\',system-ui,sans-serif}\n#view-landing{display:block}\n#view-tree{display:none;position:fixed;inset:0;overflow:hidden}\n#lnd-header{background:var(--bg2);border-bottom:1px solid var(--brd);\n  padding:16px 24px;display:flex;align-items:center;justify-content:space-between;gap:12px}\n#lnd-header h1{font-size:16px;font-weight:700;display:flex;align-items:center;gap:8px}\n#lnd-main{max-width:960px;margin:0 auto;padding:28px 24px}\n.empty{text-align:center;padding:60px 0;color:var(--txt3);font-size:14px}\n.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}\n.card{background:var(--bg2);border:1px solid var(--brd);border-radius:10px;\n  padding:18px;text-decoration:none;color:inherit;cursor:pointer;\n  transition:border-color .15s,box-shadow .15s;display:flex;flex-direction:column;gap:6px}\n.card:hover{border-color:var(--hl);box-shadow:0 4px 16px rgba(0,0,0,.3)}\n.card-rank{font-size:10px;color:var(--txt3);letter-spacing:.05em;text-transform:uppercase}\n.card-title{font-size:15px;font-weight:600}\n.card-sci{font-size:12px;font-style:italic;color:var(--txt2)}\n.card-meta{display:flex;gap:10px;margin-top:4px;flex-wrap:wrap}\n.badge{font-size:10px;padding:2px 7px;border-radius:8px;white-space:nowrap}\n.b-sp{background:rgba(134,239,172,.12);color:#86efac;border:1px solid rgba(134,239,172,.25)}\n.b-fa{background:rgba(96,165,250,.12);color:#60a5fa;border:1px solid rgba(96,165,250,.25)}\n.b-nd{background:rgba(167,139,250,.12);color:#a78bfa;border:1px solid rgba(167,139,250,.25)}\n.b-dt{background:var(--bg3);color:var(--txt3);border:1px solid var(--brd)}\n[data-theme="light"] .b-sp{background:rgba(21,128,61,.1);color:#15803d;border-color:rgba(21,128,61,.3)}\n[data-theme="light"] .b-fa{background:rgba(29,78,216,.1);color:#1d4ed8;border-color:rgba(29,78,216,.3)}\n[data-theme="light"] .b-nd{background:rgba(109,40,217,.1);color:#6d28d9;border-color:rgba(109,40,217,.3)}\n.arrow{margin-top:auto;padding-top:8px;font-size:11px;color:var(--txt3);text-align:right}\n#lnd-footer{text-align:center;padding:24px;font-size:11px;color:var(--txt3);\n  border-top:1px solid var(--brd);margin-top:32px}\n.tb{background:transparent;border:1px solid var(--brd);color:var(--txt2);\n  border-radius:13px;padding:4px 12px;font-size:11px;cursor:pointer;\n  transition:border-color .15s,color .15s}\n.tb:hover{border-color:var(--txt2);color:var(--txt)}\n#loading{position:fixed;inset:0;background:var(--bg);\n  display:none;flex-direction:column;align-items:center;justify-content:center;\n  gap:14px;z-index:3000;font-size:13px;color:var(--txt2)}\n#loading-bar-outer{width:220px;height:4px;background:var(--bg3);border-radius:2px}\n#loading-bar{height:4px;width:0%;background:var(--hl);border-radius:2px;transition:width .3s}\n#btn-back{position:fixed;bottom:42px;left:9px;z-index:2500;display:none;\n  background:var(--bg2);border:1px solid var(--brd);color:var(--txt2);\n  border-radius:13px;padding:4px 12px;font-size:11px;cursor:pointer;\n  transition:border-color .15s,color .15s}\n#btn-back:hover{border-color:var(--hl);color:var(--hl)}\n__VIEWER_CSS__\n</style></head><body>\n<div id="loading">\n  <div>🌿 <strong id="loading-title"></strong></div>\n  <div id="loading-bar-outer"><div id="loading-bar"></div></div>\n  <div id="loading-msg">データを読み込んでいます…</div>\n</div>\n<button id="btn-back" onclick="goLanding()">← 一覧</button>\n<div id="view-landing">\n  <header id="lnd-header">\n    <h1><span>🌿</span> 系統図 一覧</h1>\n    <div style="display:flex;align-items:center;gap:12px">\n      <span style="font-size:11px;color:var(--txt3)">更新: __DATE__</span>\n      <button class="tb" id="btn-theme-lnd" onclick="toggleTheme()">🌙</button>\n    </div>\n  </header>\n  <main id="lnd-main"><div id="lnd-grid"></div></main>\n  <footer id="lnd-footer">データ: Wikidata &nbsp;|&nbsp; 生成: __DATE__</footer>\n</div>\n<div id="view-tree">\n  <div id="ov"><h2>🌿 系統図を準備中…</h2>\n    <p id="om">データ解析中</p>\n    <div class="pb"><div class="pi" id="pi"></div></div>\n  </div>\n  <div id="hdr">\n    <div id="ttl"><em></em> 系統図</div>\n    <input id="srch" placeholder="検索…"\n      onkeydown="if(event.key===\'Enter\')doSrch(document.getElementById(\'srch\').value)">\n    <button id="srch-btn" onclick="doSrch(document.getElementById(\'srch\').value)">🔍</button>\n    <button id="srch-clr" onclick="clearSrch()" title="検索をクリア">✕</button>\n    <button class="hb" onclick="expandTo(\'family\')">科まで</button>\n    <button class="hb" onclick="expandTo(\'genus\')">属まで</button>\n    <button class="hb" onclick="expandTo(\'species\')">全展開</button>\n    <button class="hb" onclick="collapseAll()">折りたたむ</button>\n    <button class="hb" onclick="fitV(false)">全体表示</button>\n    <div class="ctrl">\n      <button class="tb" id="btn-theme" onclick="toggleTheme()">🌙</button>\n    </div>\n    <div class="ctrl">\n      <button class="tb active" id="btn-ja" onclick="setLang(\'ja\')">JA</button>\n      <button class="tb"        id="btn-en" onclick="setLang(\'en\')">EN</button>\n    </div>\n    <div class="ctrl">\n      <button class="tb active" id="btn-lr" onclick="setLayout(\'lr\')">LR</button>\n      <button class="tb"        id="btn-tb" onclick="setLayout(\'tb\')">TB</button>\n      <button class="tb"        id="btn-rd" onclick="setLayout(\'rd\')" title="円形">RD</button>\n    </div>\n    <div class="ctrl">\n      <button class="tb active" id="btn-icon" onclick="toggleIcons()">🖼</button>\n    </div>\n    <div class="ctrl">\n      <button class="tb active" id="btn-iucn-all"     onclick="setIucnFilter(\'all\')"          title="全て表示">全</button>\n      <button class="tb"        id="btn-iucn-no-ex"   onclick="setIucnFilter(\'no-extinct\')"   title="絶滅種を除外">絶滅除外</button>\n      <button class="tb"        id="btn-iucn-only-ex" onclick="setIucnFilter(\'only-extinct\')" title="絶滅種のみ表示">絶滅のみ</button>\n    </div>\n    <div id="stat"></div>\n  </div>\n  <div id="leg">\n    <span>凡例：</span>\n    <div class="li"><div class="ld" style="background:var(--c-order)"></div>目</div>\n    <div class="li"><div class="ld" style="background:var(--c-family)"></div>科</div>\n    <div class="li"><div class="ld" style="background:var(--c-genus)"></div>属</div>\n    <div class="li"><div class="ld" style="background:var(--c-species)"></div>種</div>\n    <div class="li"><div class="ld" style="background:var(--c-subspecies)"></div>亜種</div>\n    <span id="leg-hint" style="margin-left:7px">▶クリックで展開 ／ ドラッグ・ホイールでナビ</span>\n    <div id="iucn-leg" style="display:none;gap:6px;flex-wrap:wrap;align-items:center">\n      <span style="color:var(--txt3)">IUCN:</span>\n      <span class="li" style="color:#dc2626">&#9632; CR</span>\n      <span class="li" style="color:#ea580c">&#9632; EN</span>\n      <span class="li" style="color:#d97706">&#9632; VU</span>\n      <span class="li" style="color:#65a30d">&#9632; NT</span>\n      <span class="li" style="color:#16a34a">&#9632; LC</span>\n      <span class="li" style="color:#6b7280">&#9632; EX</span>\n    </div>\n    <button id="iucn-leg-toggle"\n      style="background:transparent;border:1px solid var(--brd);color:var(--txt3);\n        border-radius:8px;padding:1px 6px;font-size:9px;cursor:pointer;\n        white-space:nowrap;margin-left:4px"\n      onclick="(function(){\n        const el  = document.getElementById(\'iucn-leg\');\n        const btn = document.getElementById(\'iucn-leg-toggle\');\n        const show = el.style.display === \'none\' || el.style.display === \'\';\n        el.style.display  = show ? \'flex\' : \'none\';\n        btn.textContent   = show ? \'IUCN ▲\' : \'IUCN ▼\';\n      })()">IUCN &#9660;</button>\n    <div id="leg-sizer">\n      <label>&#8596; TT</label>\n      <input type="range" id="tt-size-slider"\n        min="180" max="420" step="10" value="280"\n        oninput="setTTWidth(+this.value)">\n    </div>\n  </div>\n  <div id="main">\n    <svg id="tree"></svg>\n    <div id="tt">\n      <div id="tt-close"\n        style="display:none;justify-content:flex-end;padding:6px 8px 0;cursor:pointer"\n        onclick="tt.style.display=\'none\'">\n        <span style="font-size:18px;line-height:1;color:var(--txt3)">&#10005;</span>\n      </div>\n      <img id="tt-img" src="" alt="" crossorigin="anonymous"\n           onerror="this.classList.add(\'hidden\');\n             document.getElementById(\'tt-ph\').classList.remove(\'hidden\')">\n      <div id="tt-ph" class="hidden">&#127807;</div>\n      <div id="tt-body">\n        <div id="tt-rank"></div>\n        <div id="tt-name"></div>\n        <div id="tt-ja"></div>\n        <div id="tt-meta"><span id="tt-cnt"></span><span id="tt-credit"></span></div>\n        <div id="tt-iucn"></div>\n        <div id="tt-wiki" style="display:none;margin-top:6px">\n          <button id="tt-wiki-btn"\n            style="width:100%;padding:4px 0;font-size:10px;cursor:pointer;\n              background:transparent;border:1px solid var(--brd);\n              border-radius:6px;color:var(--hl);pointer-events:all"\n            onclick="openWiki(currentTTNode)"></button>\n        </div>\n      </div>\n    </div>\n    <div id="foot">QID: &nbsp;|&nbsp; 画像: Wikimedia Commons &nbsp;|&nbsp; 生成: __DATE__</div>\n  </div>\n</div>\n<script>\n__VIEWER_JS__\n</script>\n<script>\nconst TAXA_LIST = __TAXA_JS__;\n\nfunction toggleTheme() {\n  const h = document.documentElement;\n  const t = h.getAttribute(\'data-theme\') === \'dark\' ? \'light\' : \'dark\';\n  h.setAttribute(\'data-theme\', t);\n  [\'btn-theme\',\'btn-theme-lnd\'].forEach(id => {\n    const el = document.getElementById(id);\n    if (el) el.textContent = t === \'dark\' ? \'🌙\' : \'☀️\';\n  });\n  localStorage.setItem(\'taxa_theme\', t);\n}\n(function() {\n  const t = localStorage.getItem(\'taxa_theme\') || \'dark\';\n  document.documentElement.setAttribute(\'data-theme\', t);\n  [\'btn-theme\',\'btn-theme-lnd\'].forEach(id => {\n    const el = document.getElementById(id);\n    if (el) el.textContent = t === \'dark\' ? \'🌙\' : \'☀️\';\n  });\n})();\n\nfunction renderLanding() {\n  const grid = document.getElementById(\'lnd-grid\');\n  if (!TAXA_LIST.length) {\n    grid.innerHTML = \'<div class="empty"><p>📂 まだ系統図がありません。</p>\'\n      + \'<p style="margin-top:8px;font-size:12px">python taxa_tree.py --qid Q25341 を実行してください。</p></div>\';\n    return;\n  }\n  grid.innerHTML = \'<div class="grid">\'\n    + TAXA_LIST.map(t => {\n        const title = t.ja || t.name;\n        const sub   = t.ja ? `<div class="card-sci">${t.name}</div>` : \'\';\n        const badges = [\n          t.sp    ? `<span class="badge b-sp">🐦 ${t.sp.toLocaleString()}種</span>` : \'\',\n          t.fa    ? `<span class="badge b-fa">🏷 ${t.fa.toLocaleString()}科</span>` : \'\',\n          t.nodes ? `<span class="badge b-nd">📦 ${t.nodes.toLocaleString()}件</span>` : \'\',\n          `<span class="badge b-dt">📅 ${t.date}</span>`,\n        ].join(\'\');\n        return `<div class="card" onclick="goViewer(\'${t.qid}\')" role="button" tabindex="0"\n            onkeydown="if(event.key===\'Enter\')goViewer(\'${t.qid}\')">\n          <div class="card-rank">${t.rank_ja} ${t.qid}</div>\n          <div class="card-title">${title}</div>\n          ${sub}\n          <div class="card-meta">${badges}</div>\n          <div class="arrow">系統図を開く →</div>\n        </div>`;\n    }).join(\'\') + \'</div>\';\n}\n\nwindow.DATA = null;\nfunction goLanding()   { location.hash = \'\'; }\nfunction goViewer(qid) { location.hash = qid; }\n\nasync function loadViewer(qid) {\n  const taxa = TAXA_LIST.find(t => t.qid === qid);\n  if (!taxa) { alert(\'QID \' + qid + \' のデータが見つかりません\'); return; }\n  document.getElementById(\'view-landing\').style.display = \'none\';\n  document.getElementById(\'view-tree\').style.display    = \'block\';\n  document.getElementById(\'loading\').style.display      = \'flex\';\n  document.getElementById(\'loading-bar\').style.width    = \'0%\';\n  document.getElementById(\'loading-title\').textContent  = taxa.ja || taxa.name;\n  document.getElementById(\'loading-msg\').textContent    = \'データを読み込んでいます…\';\n  document.title = (taxa.ja || taxa.name) + \' 系統図\';\n  const ttlEl = document.getElementById(\'ttl\');\n  if (ttlEl) ttlEl.innerHTML =\n    `<em>${taxa.ja || taxa.name}</em>${taxa.ja ? \' (\' + taxa.name + \')\' : \'\'} 系統図`;\n  const footEl = document.getElementById(\'foot\');\n  if (footEl) footEl.textContent =\n    `QID: ${taxa.qid} | 画像: Wikimedia Commons | 生成: __DATE__`;\n  const bar = document.getElementById(\'loading-bar\');\n  const msg = document.getElementById(\'loading-msg\');\n  try {\n    const resp = await fetch(taxa.json);\n    if (!resp.ok) throw new Error(\'HTTP \' + resp.status);\n    const total  = parseInt(resp.headers.get(\'content-length\') || \'0\');\n    const reader = resp.body.getReader();\n    let received = 0;\n    const chunks = [];\n    while (true) {\n      const {done, value} = await reader.read();\n      if (done) break;\n      chunks.push(value); received += value.length;\n      if (total > 0 && bar) bar.style.width = Math.min(received / total * 90, 90) + \'%\';\n    }\n    if (msg) msg.textContent = \'描画中…\';\n    if (bar) bar.style.width = \'100%\';\n    const size   = chunks.reduce((a, b) => a + b.length, 0);\n    const merged = new Uint8Array(size);\n    let off = 0;\n    for (const c of chunks) { merged.set(c, off); off += c.length; }\n    window.DATA = JSON.parse(new TextDecoder().decode(merged));\n    document.getElementById(\'loading\').style.display = \'none\';\n    if (typeof init === \'function\') init();\n  } catch(e) {\n    if (msg) msg.textContent = \'読み込み失敗: \' + e.message;\n    console.error(\'JSON load error:\', e);\n  }\n}\n\nfunction route() {\n  const qid     = location.hash.slice(1);\n  const backBtn = document.getElementById(\'btn-back\');\n  if (qid) {\n    if (backBtn) backBtn.style.display = \'block\';\n    loadViewer(qid);\n  } else {\n    if (backBtn) backBtn.style.display = \'none\';\n    document.getElementById(\'view-landing\').style.display = \'block\';\n    document.getElementById(\'view-tree\').style.display    = \'none\';\n    document.getElementById(\'loading\').style.display      = \'none\';\n    document.title = \'系統図\';\n    renderLanding();\n  }\n}\n\nwindow.addEventListener(\'hashchange\', route);\nwindow.addEventListener(\'load\', () => { renderLanding(); route(); });\n</script>\n</body></html>'


# ─────────────────────────────────────────────────────────────────
#  HTML 生成関数
# ─────────────────────────────────────────────────────────────────

def make_html(tree: dict, root_qid: str) -> str:
    """standalone モード: JSON を HTML に埋め込む（単体ファイルで動作）。"""
    title = tree.get("name", root_qid)
    if tree.get("ja"):
        title = f"{tree['ja']} ({title})"
    date  = datetime.now().strftime("%Y-%m-%d")
    js    = _json.dumps(tree, ensure_ascii=False, separators=(",", ":"))
    return (HTML
            .replace("__TITLE__",      title)
            .replace("__QID__",        root_qid)
            .replace("__DATE__",       date)
            .replace("__DATA_BLOCK__", f"const DATA={js};"))


def make_web_viewer(tree: dict, root_qid: str, json_filename: str) -> str:
    """web モード: JSON を外部 fetch で読み込む（GitHub Pages 専用）。"""
    title = tree.get("name", root_qid)
    if tree.get("ja"):
        title = f"{tree['ja']} ({title})"
    date = datetime.now().strftime("%Y-%m-%d")
    jf   = json_filename
    data_block = "\n".join([
        "window.DATA = null;",
        "(async () => {",
        '  const bar = document.getElementById("loading-bar");',
        '  const msg = document.getElementById("loading-msg");',
        "  try {",
        f'    const resp = await fetch("{jf}");',
        '    if (!resp.ok) throw new Error("HTTP " + resp.status);',
        '    const total = parseInt(resp.headers.get("content-length") || "0");',
        "    const reader = resp.body.getReader();",
        "    let received = 0; const chunks = [];",
        "    while (true) {",
        "      const {done, value} = await reader.read();",
        "      if (done) break;",
        "      chunks.push(value); received += value.length;",
        "      if (total > 0 && bar)",
        '        bar.style.width = Math.min(received / total * 90, 90) + "%";',
        "    }",
        '    if (msg) msg.textContent = "描画中…";',
        '    if (bar) bar.style.width = "100%";',
        "    const size = chunks.reduce((a,b) => a+b.length, 0);",
        "    const merged = new Uint8Array(size);",
        "    let off = 0;",
        "    for (const c of chunks) { merged.set(c, off); off += c.length; }",
        "    window.DATA = JSON.parse(new TextDecoder().decode(merged));",
        "    init();",
        "  } catch(e) {",
        '    if (msg) msg.textContent = "読み込み失敗: " + e.message;',
        '    console.error("JSON load error:", e);',
        "  }",
        "})();",
    ])
    return (HTML
            .replace("__TITLE__",      title)
            .replace("__QID__",        root_qid)
            .replace("__DATE__",       date)
            .replace("__DATA_BLOCK__", data_block))


def make_index_html(output_dir: Path | str) -> str:
    """
    SPA index.html を生成して返す。

    output_dir 内の taxa_cache_Q*.json を走査してカード一覧を生成する。
    ビューワーの CSS・JS は HTML テンプレートから抽出して注入する。
    """
    output_dir = Path(output_dir)
    date_str   = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── ビューワー CSS・JS を HTML テンプレートから抽出 ──────────
    css_m      = _re.search(r"<style>(.*?)</style>", HTML, _re.DOTALL)
    viewer_css = css_m.group(1) if css_m else ""
    viewer_css = _re.sub(r"#(?:loading|ov)(?:-[a-z-]+)?\{[^}]+\}\n?", "", viewer_css)
    script_m   = _re.search(r"<script(?! src)[^>]*>(.*?)</script>", HTML, _re.DOTALL)
    viewer_js  = script_m.group(1) if script_m else ""
    viewer_js  = viewer_js.replace("__DATA_BLOCK__",
                                   "// DATA injected via window.DATA by SPA router")
    viewer_js  = viewer_js.replace('window.addEventListener("load", init);', "")

    # ── カード用の JSON リストを生成 ─────────────────────────────
    RANK_JA = {
        "domain": "域", "kingdom": "界", "subkingdom": "亜界",
        "phylum": "門", "subphylum": "亜門",
        "superclass": "上綱", "class": "綱", "subclass": "亜綱", "infraclass": "下綱",
        "superorder": "上目", "order": "目", "suborder": "亜目", "infraorder": "下目",
        "superfamily": "上科", "family": "科", "subfamily": "亜科",
        "tribe": "族", "subtribe": "亜族",
        "genus": "属", "subgenus": "亜属",
        "species": "種", "subspecies": "亜種",
        "variety": "変種", "form": "品種",
    }

    taxa_list = []
    for cache_path in sorted(
        output_dir.glob("taxa_cache_Q*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        try:
            with open(cache_path, encoding="utf-8") as f:
                tree = _json.load(f)
            qid          = tree.get("id", "")
            total = sp = fa = 0
            stack = [tree]
            while stack:
                nd = stack.pop()
                total += 1
                r = nd.get("rank", "")
                if r == "species":  sp += 1
                elif r == "family": fa += 1
                stack.extend(nd.get("children", []))
            meta         = tree.get("_meta", {})
            fetched_at   = meta.get("fetched_at", "")
            date_label   = fetched_at[:10] if fetched_at else "?"
            taxa_list.append({
                "qid":     qid,
                "name":    tree.get("name", ""),
                "ja":      tree.get("ja",   ""),
                "rank":    tree.get("rank", ""),
                "rank_ja": RANK_JA.get(tree.get("rank", ""), "?"),
                "nodes":   total,
                "sp":      sp,
                "fa":      fa,
                "date":    date_label,
                "json":    cache_path.name,
            })
        except Exception:
            continue

    taxa_js = _json.dumps(taxa_list, ensure_ascii=False)

    return (_SPA_HEAD
            .replace("__DATE__",       date_str)
            .replace("__VIEWER_CSS__", viewer_css)
            .replace("__TAXA_JS__",    taxa_js)
            .replace("__VIEWER_JS__",  viewer_js))