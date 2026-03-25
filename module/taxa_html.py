#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
module/taxa_html.py  ─  HTML生成・UI モジュール
================================================================
インタラクティブ系統図の HTML テンプレートと生成関数を提供する。
データロジックには依存しない。

公開 API:
    make_html(tree: dict, root_qid: str) -> str
        ツリー辞書から単体配布可能な HTML 文字列を生成して返す。
"""

import json
from datetime import datetime

# HTML・UI モジュールのバージョン
# テンプレート・CSS・JS など UI に変更があるたびにインクリメントする
HTML_VERSION = "1.5"

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
/* 補完取得ノードのバッジ */
.nd.strategy-prefix .bg,.nd.strategy-prefix .img-ring{stroke:#f59e0b!important}
.nd.strategy-gbif    .bg,.nd.strategy-gbif    .img-ring{stroke:#3b82f6!important}
.nd.strategy-incomplete .bg{stroke:#ef4444!important;stroke-dasharray:3,2}
/* ツールチップ */
#tt{position:absolute;background:var(--bg2);border:1px solid var(--brd);
  border-radius:10px;padding:0;pointer-events:auto;display:none;
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
/* ── モバイル専用スタイル ─────────────── */
@media (pointer: coarse) {
  /* ツールチップを画面中央下部に固定 */
  #tt{
    position:fixed !important;
    left:50% !important;
    transform:translateX(-50%);
    bottom:12px !important;
    top:auto !important;
    width:min(320px, calc(100vw - 24px)) !important;
    max-height:75vh;
    overflow-y:auto;
    box-shadow:0 -4px 24px rgba(0,0,0,.5);
  }
  /* 閉じるボタンを表示 */
  #tt-close{ display:flex !important }
  /* ノードのタップ領域を広げる */
  .nd circle.bg{ stroke-width:2 }
  /* 長押しフィードバック */
  .nd.pressing circle.bg{
    stroke:var(--hl) !important;
    stroke-width:3 !important;
    transition:stroke .1s,stroke-width .1s;
  }
  /* モバイルで画像を横幅いっぱいに */
  #tt-img,#tt-ph{
    width:100% !important;
    height:160px !important;
  }
  /* Wikipedia ボタンをタップしやすく */
  #tt-wiki-btn{
    padding:10px 0 !important;
    font-size:13px !important;
  }
  /* ヘッダーボタンを少し大きく */
  .hb,.tb{ padding:5px 10px !important; font-size:12px !important; }
}
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
  <span id="leg-hint" style="margin-left:7px">▶クリックで展開 ／ ドラッグ・ホイールでナビ</span>
</div>
<div id="main">
  <svg id="tree"></svg>
  <div id="tt">
    <!-- 閉じるボタン（モバイルのみ表示） -->
    <div id="tt-close"
      style="display:none;justify-content:flex-end;padding:6px 8px 0;cursor:pointer"
      onclick="tt.style.display='none'">
      <span style="font-size:18px;line-height:1;color:var(--txt3)">✕</span>
    </div>
    <img id="tt-img" src="" alt="" crossorigin="anonymous"
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
      <div id="tt-wiki" style="display:none;margin-top:6px">
        <button id="tt-wiki-btn"
          style="width:100%;padding:4px 0;font-size:10px;cursor:pointer;
            background:transparent;border:1px solid var(--brd);
            border-radius:6px;color:var(--hl);pointer-events:all"
          onclick="openWiki(currentTTNode)">
        </button>
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

  // モバイルは凡例テキストをタッチ向けに変更
  if (isTouchDev) {
    const hint = document.getElementById('leg-hint');
    if (hint) hint.textContent = '▶タップで展開 ／ 長押しで詳細（Wikipedia）';
  }

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
  const ne = nd.enter().append("g")
    .attr("class", d => {
      const s = d.data.fetch_strategy;
      if (s === 'prefix')     return 'nd strategy-prefix';
      if (s === 'gbif')       return 'nd strategy-gbif';
      if (s === 'incomplete') return 'nd strategy-incomplete';
      return 'nd';
    })
    .attr("transform", _ => `translate(${sy},${sx})`)
    .on("click", (e, d) => {
      if (isTouchDev) return; // タッチは touchend で処理
      const isLeaf = ["species","subspecies","variety","form"].includes(d.data.rank);
      if (isLeaf && !d.children && !d._children) {
        openWiki(d);
      } else {
        tog(d); update(d);
      }
      e.stopPropagation();
    })
    // ── マウスイベント（非タッチデバイスのみ有効） ──
    .on("mouseover", (e, d) => { if (!isTouchDev) showTT(e, d); })
    .on("mousemove", (e, d) => { if (!isTouchDev) movTT(e); })
    .on("mouseout",  ()     => { if (!isTouchDev) schedulHide(); })
    // ── タッチイベント（タッチデバイスのみ有効） ──
    .on("touchstart", (e, d) => {
      e.stopPropagation();
      startLongPress(e, d);
    }, {passive: true})
    .on("touchend", (e, d) => {
      e.stopPropagation();
      endTouch(e, d);
    })
    .on("touchmove", (e, d) => {
      cancelLongPress(); // スクロール中は長押し解除
    }, {passive: true});

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
      .attr("href", "")                    // 初期は空→レイジーロード
      .attr("data-src", d.data.image_url)  // 実URLはdata-srcに保持
      .attr("crossOrigin", "anonymous")
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
  // 再描画後: デバウンスタイマー経由で画像ロードをスケジュール
  scheduleImageLoad();
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
// _children を含むツリー全ノードを走査するヘルパー
function walkAll(node, fn) {
  fn(node);
  const kids = node.children || node._children || [];
  kids.forEach(c => walkAll(c, fn));
}

function doSrch(q) {
  const v = q.trim().toLowerCase();
  // ハイライトをリセット
  g.selectAll(".nd").classed("nh", false).classed("nm", false);
  if (!v) {
    // 空文字ならリセットのみ
    update(root);
    return;
  }

  const hit      = new Set(); // ヒットノードおよびその祖先
  const hitDirect = new Set(); // ヒットしたノード自身

  // _children を含む全ノードを走査
  walkAll(root, d => {
    const name = (d.data.name || "").toLowerCase();
    const ja   = (d.data.ja   || "").toLowerCase();
    if (name.includes(v) || ja.includes(v)) {
      hitDirect.add(d.data.id);
      hit.add(d.data.id);
      // 祖先パスをすべて展開してマーク
      let p = d.parent;
      while (p) {
        hit.add(p.data.id);
        // 折りたたまれていたら展開
        if (p._children) {
          p.children  = p._children;
          p._children = null;
        }
        p = p.parent;
      }
    }
  });

  // ヒットしたノードの子孫も展開（ヒットノード自体の下も見せる）
  walkAll(root, d => {
    if (hitDirect.has(d.data.id) && d._children) {
      d.children  = d._children;
      d._children = null;
    }
  });

  // ツリーを再描画してハイライトを適用
  update(root);

  g.selectAll(".nd")
    .classed("nh", d => hitDirect.has(d.data.id))
    .classed("nm", d => !hit.has(d.data.id));

  // ヒットノードが画面内に入るよう自動フィット
  if (hit.size > 0) {
    setTimeout(() => fitV(false), 260);
  }
}

// ─── 画像レイジーロード（ズーム閾値 + デバウンス + レートキュー）─────
//
// 3段構えで Wikimedia CDN への 429 を防ぐ
//
//  段1: ズーム閾値
//       scale < IMG_ZOOM_MIN の場合はリクエストしない
//       （全体俯瞰中にノードが小さすぎる→画像不要）
//
//  段2: デバウンス
//       ズーム倍率が変わってから IMG_DEBOUNCE_MS ms 後に処理開始
//       ドラッグ・ピンチ操作中は何もしない
//
//  段3: レートリミットキュー
//       IMG_RATE_PER_SEC リクエスト/秒 に上限を設ける
//       キューに積んで順次送出

const IMG_ZOOM_MIN    = 0.35;   // この倍率未満では画像ロードしない
const IMG_DEBOUNCE_MS = 1500;   // ズーム操作停止後に待つ時間(ms)
const IMG_RATE_PER_SEC = 4;     // 1秒あたりの最大リクエスト数

// ── キュー本体 ────────────────────────────────────────────────────
const _imgQueue   = [];         // 未ロード URL のキュー [{el, src}]
let   _queueTimer = null;       // キュー処理のインターバルタイマー

function _startQueue() {
  if (_queueTimer) return;
  _queueTimer = setInterval(() => {
    if (_imgQueue.length === 0) {
      clearInterval(_queueTimer);
      _queueTimer = null;
      return;
    }
    // 1 tick に IMG_RATE_PER_SEC 件まで送出
    const batch = _imgQueue.splice(0, IMG_RATE_PER_SEC);
    batch.forEach(({el, src}) => {
      if (!el.attr("href")) el.attr("href", src);
    });
  }, 1000);
}

function _enqueueVisible() {
  const t       = d3.zoomTransform(svg.node());
  const scale   = t.k;
  const svgRect = mainEl.getBoundingClientRect();

  // 段1: ズーム閾値チェック
  if (scale < IMG_ZOOM_MIN) return;

  g.selectAll("image.species-img").each(function() {
    const el  = d3.select(this);
    const src = el.attr("data-src");
    if (!src || el.attr("href")) return; // ロード済み or URL なし
    // 既にキューに入っているか確認
    if (_imgQueue.some(q => q.src === src)) return;

    // ノード座標 → 画面座標に変換
    const parent = this.parentNode;
    if (!parent) return;
    const nd = d3.select(parent).datum();
    if (!nd) return;
    const sx = layoutMode === "lr" ? nd.y : nd.x;
    const sy = layoutMode === "lr" ? nd.x : nd.y;
    const px = t.applyX(sx);
    const py = t.applyY(sy);

    // 画面内（マージン付き）のノードをキューに追加
    const margin = 100;
    if (px > -margin && px < svgRect.width  + margin &&
        py > -margin && py < svgRect.height + margin) {
      _imgQueue.push({el, src});
    }
  });

  _startQueue();
}

// ── デバウンスラッパー ────────────────────────────────────────────
let _imgDebounce = null;

function scheduleImageLoad() {
  clearTimeout(_imgDebounce);
  _imgDebounce = setTimeout(_enqueueVisible, IMG_DEBOUNCE_MS);
}

// zoom 変化時: デバウンスタイマーをリセット
zm.on("zoom.lazyimg",  () => clearTimeout(_imgDebounce));
// zoom 終了時: デバウンス開始
zm.on("end.lazyimg",   scheduleImageLoad);

// ─── デバイス判定 ───────────────────────────────────────────────
const isTouchDev = window.matchMedia('(pointer: coarse)').matches;

// ─── Wikipedia リンク ────────────────────────────────────────────
function openWiki(d) {
  const sci   = d.data.name || "";
  const ja    = d.data.ja   || "";
  const sciE  = encodeURIComponent(sci);
  const jaE   = encodeURIComponent(ja);
  const enUrl = `https://en.wikipedia.org/wiki/${sciE}`;
  const jaUrl = `https://ja.wikipedia.org/wiki/${jaE}`;

  if (langMode === "ja" && ja) {
    // JA モード + 和名あり: 日本語版が実在するか確認してから開く
    // Wikipedia API で pageinfo を取得（missing フィールドで判断）
    const apiUrl = `https://ja.wikipedia.org/w/api.php?action=query`
                 + `&titles=${jaE}&prop=info&format=json&origin=*`;
    fetch(apiUrl)
      .then(r => r.json())
      .then(data => {
        const pages = data.query?.pages || {};
        const page  = Object.values(pages)[0];
        // "missing" プロパティがある場合は記事なし → EN にフォールバック
        if (page && page.missing !== undefined) {
          window.open(enUrl, "_blank", "noopener");
        } else {
          window.open(jaUrl, "_blank", "noopener");
        }
      })
      .catch(() => window.open(jaUrl, "_blank", "noopener")); // fetch失敗時はそのまま開く
  } else {
    // EN モード or 和名なし: 英語版を直接開く
    window.open(enUrl, "_blank", "noopener");
  }
}

// ─── ツールチップ（画像対応） ─────────────────────────────────────
const tt = document.getElementById("tt");
let currentTTNode = null;
let _hideTimer = null;

function schedulHide() {
  _hideTimer = setTimeout(() => { tt.style.display = "none"; }, 220);
}
function cancelHide() {
  if (_hideTimer) { clearTimeout(_hideTimer); _hideTimer = null; }
}
// ツールチップ上にマウスが来たら非表示タイマーをキャンセル
tt.addEventListener("mouseenter", cancelHide);
tt.addEventListener("mouseleave", schedulHide);

// ─── 長押し（タッチデバイス） ────────────────────────────────────
let _lpTimer  = null;   // 長押しタイマー
let _lpFired  = false;  // 長押し発火フラグ
let _lpNode   = null;   // 対象ノード
const LP_MS   = 480;    // 長押し判定時間（ms）

function startLongPress(e, d) {
  cancelLongPress();
  _lpFired = false;
  _lpNode  = d;
  // 長押しフィードバック（ノードにクラス付与）
  d3.select(e.currentTarget).classed('pressing', true);
  _lpTimer = setTimeout(() => {
    _lpFired = true;
    d3.select(e.currentTarget).classed('pressing', false);
    // タッチ座標からツールチップを表示
    const touch = e.touches ? e.touches[0] : e;
    showTTTouch(d);
  }, LP_MS);
}

function cancelLongPress() {
  if (_lpTimer) { clearTimeout(_lpTimer); _lpTimer = null; }
  if (_lpNode) {
    g.selectAll('.nd').classed('pressing', false);
  }
}

function endTouch(e, d) {
  cancelLongPress();
  if (_lpFired) return; // 長押し処理済み → 短タップ扱いにしない
  // 短タップ: 展開 or Wikipedia
  const isLeaf = ['species','subspecies','variety','form'].includes(d.data.rank);
  if (isLeaf && !d.children && !d._children) {
    openWiki(d);
  } else {
    tog(d); update(d);
  }
}

// モバイル用ツールチップ表示（位置は画面下部固定のため座標不要）
function showTTTouch(d) {
  // showTT の座標計算部分を除いて呼び出す
  const fakeEvt = { clientX: 0, clientY: 0 }; // movTT は @media で無視される
  showTT(fakeEvt, d);
  // モバイルではCSSで bottom 固定にするため left/top 上書きをリセット
  tt.style.left = '';
  tt.style.top  = '';
}

// 画面タップでツールチップを閉じる（ノード以外の領域）
mainEl.addEventListener('touchstart', (e) => {
  if (!tt.contains(e.target) && !e.target.closest('.nd')) {
    tt.style.display = 'none';
  }
}, {passive: true});
function showTT(e, d) {
  const lb = getLabels(d);
  const ch = (d.children ?? d._children ?? []).length;
  const strategyBadge = {
    'prefix':     ' 🔤 [A補完]',
    'gbif':       ' 🌐 [B補完]',
    'incomplete': ' ⚠ [データ不完全]',
  }[d.data.fetch_strategy] || '';
  document.getElementById("tt-rank").textContent =
    (RJ[d.data.rank] || d.data.rank) + strategyBadge;
  document.getElementById("tt-name").textContent = lb.primary;
  document.getElementById("tt-ja").textContent   = lb.secondary;
  document.getElementById("tt-cnt").textContent  = ch ? `直下: ${ch}件` : "";

  const imgEl    = document.getElementById("tt-img");
  const phEl     = document.getElementById("tt-ph");
  const creditEl = document.getElementById("tt-credit");

  if (d.data.image_url) {

    // Special:FilePath?width= 方式: width値を220に差し替え
    // Wikimedia API URL の w= パラメータと Special:FilePath の width= 両方に対応
    // 250px は Wikimedia 標準サイズ（220px は非標準で 429 になる）
    const large = d.data.image_url
      .replace(/\/\d+px-/, '/250px-')           // CDN thumb URL
      .replace(/[?&]width=\d+/, '?width=250');  // Special:FilePath URL
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
  // Wikipedia ボタン: 全ランクで表示
  const wikiDiv = document.getElementById("tt-wiki");
  const wikiBtn = document.getElementById("tt-wiki-btn");
  wikiBtn.textContent = langMode === "ja" ? "Wikipedia で開く ↗" : "Open in Wikipedia ↗";
  wikiDiv.style.display = "block";
  currentTTNode = d;
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
#  ランディングページ生成
# ─────────────────────────────────────────────────────────────────

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="ja" data-theme="dark"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>taxa_tree — 系統図一覧</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d1117;--bg2:#161b22;--bg3:#21262d;
  --txt:#e6edf3;--txt2:#8b949e;--txt3:#555d6b;
  --brd:#30363d;--hl:#f0b429;--grn:#3fb950;
}
[data-theme="light"]{
  --bg:#ffffff;--bg2:#f6f8fa;--bg3:#eaeef2;
  --txt:#1f2328;--txt2:#444c56;--txt3:#768390;
  --brd:#d0d7de;--hl:#b45309;--grn:#1a7f37;
}
html,body{min-height:100%;background:var(--bg);color:var(--txt);
  font-family:'Hiragino Sans','Yu Gothic',Meiryo,'Noto Sans JP',system-ui,sans-serif;
  transition:background .2s,color .2s}
header{background:var(--bg2);border-bottom:1px solid var(--brd);
  padding:16px 24px;display:flex;align-items:center;justify-content:space-between;gap:12px}
header h1{font-size:16px;font-weight:700;display:flex;align-items:center;gap:8px}
header h1 span{font-size:20px}
#gen-date{font-size:11px;color:var(--txt3)}
.tb{background:transparent;border:1px solid var(--brd);color:var(--txt2);
  border-radius:13px;padding:4px 12px;font-size:11px;cursor:pointer;
  transition:border-color .15s,color .15s}
.tb:hover{border-color:var(--txt2);color:var(--txt)}
main{max-width:960px;margin:0 auto;padding:28px 24px}
.empty{text-align:center;padding:60px 0;color:var(--txt3);font-size:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}
.card{background:var(--bg2);border:1px solid var(--brd);border-radius:10px;
  padding:18px;text-decoration:none;color:inherit;
  transition:border-color .15s,box-shadow .15s;display:flex;flex-direction:column;gap:6px}
.card:hover{border-color:var(--hl);box-shadow:0 4px 16px rgba(0,0,0,.3)}
.card-rank{font-size:10px;color:var(--txt3);letter-spacing:.05em;text-transform:uppercase}
.card-title{font-size:15px;font-weight:600}
.card-sci{font-size:12px;font-style:italic;color:var(--txt2)}
.card-meta{display:flex;gap:10px;margin-top:4px;flex-wrap:wrap}
.badge{font-size:10px;padding:2px 7px;border-radius:8px;white-space:nowrap}
.b-sp{background:rgba(134,239,172,.12);color:#86efac;border:1px solid rgba(134,239,172,.25)}
.b-fa{background:rgba(96,165,250,.12);color:#60a5fa;border:1px solid rgba(96,165,250,.25)}
.b-nd{background:rgba(167,139,250,.12);color:#a78bfa;border:1px solid rgba(167,139,250,.25)}
.b-dt{background:var(--bg3);color:var(--txt3);border:1px solid var(--brd)}
[data-theme="light"] .b-sp{background:rgba(21,128,61,.1);color:#15803d;border-color:rgba(21,128,61,.3)}
[data-theme="light"] .b-fa{background:rgba(29,78,216,.1);color:#1d4ed8;border-color:rgba(29,78,216,.3)}
[data-theme="light"] .b-nd{background:rgba(109,40,217,.1);color:#6d28d9;border-color:rgba(109,40,217,.3)}
.arrow{margin-top:auto;padding-top:8px;font-size:11px;color:var(--txt3);text-align:right}
footer{text-align:center;padding:24px;font-size:11px;color:var(--txt3);
  border-top:1px solid var(--brd);margin-top:32px}
</style></head>
<body>
<header>
  <h1><span>🌿</span> 系統図 一覧</h1>
  <div style="display:flex;align-items:center;gap:12px">
    <span id="gen-date"></span>
    <button class="tb" id="btn-theme" onclick="toggleTheme()">🌙</button>
  </div>
</header>
<main>
__CARDS__
</main>
<footer>データ: Wikidata &nbsp;|&nbsp; 生成: __DATE__</footer>
<script>
document.getElementById("gen-date").textContent = "更新: __DATE__";
function toggleTheme(){
  const h=document.documentElement,t=h.getAttribute("data-theme")==="dark"?"light":"dark";
  h.setAttribute("data-theme",t);
  document.getElementById("btn-theme").textContent=t==="dark"?"🌙":"☀️";
  localStorage.setItem("taxa_theme",t);
}
(function(){
  const t=localStorage.getItem("taxa_theme")||"dark";
  document.documentElement.setAttribute("data-theme",t);
  document.getElementById("btn-theme").textContent=t==="dark"?"🌙":"☀️";
})();
</script>
</body></html>"""

# ランク日本語表記（index ページ用）
_RANK_JA = {
    "domain": "域", "kingdom": "界", "phylum": "門", "subphylum": "亜門",
    "class": "綱", "subclass": "亜綱", "order": "目", "suborder": "亜目",
    "family": "科", "subfamily": "亜科", "genus": "属", "species": "種",
    "unknown": "?",
}


def make_index_html(output_dir) -> str:
    """
    output_dir 内の taxa_*.html を走査してランディングページ HTML を返す。
    対応する taxa_cache_<QID>.json が存在すれば種数・属数・科数も表示する。

    output_dir: str または Path
    """
    from pathlib import Path as _Path
    import json as _json
    import re as _re

    out_dir = _Path(output_dir)
    date    = datetime.now().strftime("%Y-%m-%d")

    # taxa_*.html を更新日時の新しい順に列挙
    taxa_files = sorted(
        out_dir.glob("taxa_*.html"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not taxa_files:
        cards_html = (
            '<div class="empty">'
            '<p>📂 まだ系統図がありません。</p>'
            '<p style="margin-top:8px;font-size:12px">'
            'python taxa_tree.py --qid Q25341 を実行してください。</p>'
            '</div>'
        )
    else:
        cards = []
        for html_path in taxa_files:
            # ファイル名から QID を抽出: taxa_<name>_<QID>.html
            m = _re.search(r'_(Q\d+)\.html$', html_path.name)
            qid = m.group(1) if m else ""

            # キャッシュ JSON から詳細情報を取得
            sci_name = ja_name = rank = ""
            sp_count = ge_count = fa_count = node_count = 0
            cache_path = out_dir / f"taxa_cache_{qid}.json" if qid else None
            if cache_path and cache_path.exists():
                try:
                    with open(cache_path, encoding="utf-8") as f:
                        tree = _json.load(f)
                    sci_name   = tree.get("name", "")
                    ja_name    = tree.get("ja",   "")
                    rank       = tree.get("rank",  "")
                    # ノード統計
                    stack = [tree]
                    while stack:
                        nd = stack.pop()
                        node_count += 1
                        r = nd.get("rank", "")
                        if r == "species":
                            sp_count += 1
                        elif r == "genus":
                            ge_count += 1
                        elif r == "family":
                            fa_count += 1
                        stack.extend(nd.get("children", []))
                except Exception:
                    pass

            # キャッシュがない場合はファイル名から推測
            if not sci_name:
                stem    = html_path.stem          # taxa_スズメ目_Q25341
                parts   = stem.split("_")
                sci_name = parts[-2] if len(parts) >= 3 else stem

            rank_ja   = _RANK_JA.get(rank, rank)
            file_date = datetime.fromtimestamp(
                html_path.stat().st_mtime
            ).strftime("%Y-%m-%d")
            rel_path  = html_path.name

            # バッジ HTML
            badges = []
            if sp_count:
                badges.append(f'<span class="badge b-sp">🐦 {sp_count:,}種</span>')
            if fa_count:
                badges.append(f'<span class="badge b-fa">🏷 {fa_count:,}科</span>')
            if node_count:
                badges.append(f'<span class="badge b-nd">📦 {node_count:,}件</span>')
            badges.append(f'<span class="badge b-dt">📅 {file_date}</span>')

            title_html = ja_name if ja_name else sci_name
            sub_html   = f'<div class="card-sci">{sci_name}</div>' if ja_name else ""

            cards.append(
                f'<a class="card" href="{rel_path}">\n'
                f'  <div class="card-rank">{rank_ja} {qid}</div>\n'
                f'  <div class="card-title">{title_html}</div>\n'
                f'  {sub_html}\n'
                f'  <div class="card-meta">{"".join(badges)}</div>\n'
                f'  <div class="arrow">系統図を開く →</div>\n'
                f'</a>'
            )

        grid_html = '<div class="grid">\n' + "\n".join(cards) + "\n</div>"
        cards_html = grid_html

    return (INDEX_HTML
            .replace("__CARDS__", cards_html)
            .replace("__DATE__",  date))