#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${OUT_DIR:-./output/douyin-favorites}"
MAX_STEPS="${MAX_STEPS:-2000}"
SLEEP_MS="${SLEEP_MS:-700}"
SLEEP_JITTER_RATIO="${SLEEP_JITTER_RATIO:-0.35}"
SCROLL_RATIO_MIN="${SCROLL_RATIO_MIN:-0.72}"
SCROLL_RATIO_MAX="${SCROLL_RATIO_MAX:-0.93}"
HARD_RETRIES="${HARD_RETRIES:-3}"
FAVORITES_URL="${FAVORITES_URL:-https://www.douyin.com/user/self?from_tab_name=main&showSubTab=video&showTab=favorite_collection}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out-dir)
      OUT_DIR="$2"
      shift 2
      ;;
    --max-steps)
      MAX_STEPS="$2"
      shift 2
      ;;
    --sleep-ms)
      SLEEP_MS="$2"
      shift 2
      ;;
    --sleep-jitter-ratio)
      SLEEP_JITTER_RATIO="$2"
      shift 2
      ;;
    --hard-retries)
      HARD_RETRIES="$2"
      shift 2
      ;;
    --favorites-url)
      FAVORITES_URL="$2"
      shift 2
      ;;
    -h|--help)
      cat <<USAGE
Usage:
  export_douyin_favorites.sh [--out-dir DIR] [--max-steps N] [--sleep-ms MS] [--sleep-jitter-ratio RATIO] [--hard-retries N] [--favorites-url URL]
USAGE
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

if ! command -v osascript >/dev/null 2>&1; then
  echo "osascript not found" >&2
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "node not found" >&2
  exit 1
fi

run_tab_js() {
  local wi="$1"
  local ti="$2"
  local js_code="$3"
  DY_WI="$wi" DY_TI="$ti" DY_JS="$js_code" osascript -l JavaScript <<'JXA' 2>&1
ObjC.import('stdlib');
const wi = Number($.getenv('DY_WI'));
const ti = Number($.getenv('DY_TI'));
const code = ObjC.unwrap($.getenv('DY_JS'));
const chrome = Application('Google Chrome');
const out = chrome.windows[wi].tabs[ti].execute({ javascript: code });
if (out !== undefined && out !== null) {
  console.log(out);
}
JXA
}

ms_to_sec() {
  node -e 'process.stdout.write((Number(process.argv[1]) / 1000).toFixed(3));' "$1"
}

jittered_ms() {
  node -e '
const base = Number(process.argv[1]);
const ratio = Number(process.argv[2]);
const minMs = Math.max(120, Math.floor(base * (1 - ratio)));
const maxMs = Math.max(minMs + 1, Math.floor(base * (1 + ratio)));
const value = Math.floor(Math.random() * (maxMs - minMs + 1)) + minMs;
process.stdout.write(String(value));
' "$1" "$2"
}

sleep_ms_with_jitter() {
  local base_ms="$1"
  local ratio="${2:-$SLEEP_JITTER_RATIO}"
  local wait_ms
  wait_ms="$(jittered_ms "$base_ms" "$ratio")"
  sleep "$(ms_to_sec "$wait_ms")"
}

run_tab_js_retry() {
  local wi="$1"
  local ti="$2"
  local js_code="$3"
  local desc="${4:-run_tab_js}"
  local attempts="${5:-$HARD_RETRIES}"
  local attempt=1
  local out=""
  while (( attempt <= attempts )); do
    if out="$(run_tab_js "$wi" "$ti" "$js_code")"; then
      printf '%s\n' "$out"
      return 0
    fi
    echo "Attempt ${attempt}/${attempts} failed: ${desc}" >&2
    if (( attempt < attempts )); then
      sleep_ms_with_jitter 1200 0.40
    fi
    attempt=$((attempt + 1))
  done
  echo "Failed after ${attempts} attempts: ${desc}" >&2
  return 1
}

run_tab_js_json_retry() {
  local wi="$1"
  local ti="$2"
  local js_code="$3"
  local desc="${4:-run_tab_js_json}"
  local attempts="${5:-$HARD_RETRIES}"
  local attempt=1
  local out=""
  local line=""
  while (( attempt <= attempts )); do
    if out="$(run_tab_js "$wi" "$ti" "$js_code")"; then
      line="$(printf '%s\n' "$out" | tail -n 1)"
      if [[ -n "$line" ]] && node -e 'JSON.parse(process.argv[1]);' "$line" >/dev/null 2>&1; then
        printf '%s\n' "$line"
        return 0
      fi
    fi
    echo "Attempt ${attempt}/${attempts} failed: ${desc}" >&2
    if (( attempt < attempts )); then
      sleep_ms_with_jitter 1200 0.40
    fi
    attempt=$((attempt + 1))
  done
  echo "Failed after ${attempts} attempts: ${desc}" >&2
  return 1
}

find_candidate_tab_json() {
  osascript -l JavaScript <<'JXA' 2>&1
const chrome = Application('Google Chrome');
const wins = chrome.windows();
const favoriteHints = ['favorite_collection', 'showtab=favorite_collection', '/favorite', 'favorite'];
let favoriteTab = null;
let douyinTab = null;
for (let wi = 0; wi < wins.length; wi++) {
  const tabs = wins[wi].tabs();
  for (let ti = 0; ti < tabs.length; ti++) {
    let url = '';
    try { url = tabs[ti].url() || ''; } catch (e) { url = ''; }
    if (!url) continue;
    const low = url.toLowerCase();
    if (!low.includes('douyin.com')) continue;
    if (!douyinTab) douyinTab = { wi, ti, url };
    if (favoriteHints.some((k) => low.includes(k))) {
      favoriteTab = { wi, ti, url };
      break;
    }
  }
  if (favoriteTab) break;
}

let result = favoriteTab || douyinTab;
if (!result) {
  try {
    const wi = 0;
    const ti = chrome.windows[0].activeTabIndex() - 1;
    const url = chrome.windows[0].tabs[ti].url();
    result = { wi, ti, url };
  } catch (e) {
    result = null;
  }
}
console.log(result ? JSON.stringify(result) : '');
JXA
}

find_tab_json="$(find_candidate_tab_json)"

if [[ -z "${find_tab_json// }" ]]; then
  for ((attempt=1; attempt<=HARD_RETRIES; attempt++)); do
    open -a "Google Chrome" "$FAVORITES_URL" >/dev/null 2>&1 || true
    sleep_ms_with_jitter 1800 0.45
    find_tab_json="$(find_candidate_tab_json)"
    if [[ -n "${find_tab_json// }" ]]; then
      break
    fi
    echo "Cannot find usable Chrome tab yet (attempt ${attempt}/${HARD_RETRIES})." >&2
  done
  if [[ -z "${find_tab_json// }" ]]; then
    echo "Cannot find Chrome tab after ${HARD_RETRIES} attempts. Open Google Chrome and retry." >&2
    exit 1
  fi
fi

TAB_WI=$(node -e 'const o=JSON.parse(process.argv[1]);process.stdout.write(String(o.wi));' "$find_tab_json")
TAB_TI=$(node -e 'const o=JSON.parse(process.argv[1]);process.stdout.write(String(o.ti));' "$find_tab_json")
TAB_URL=$(node -e 'const o=JSON.parse(process.argv[1]);process.stdout.write(o.url||"");' "$find_tab_json")

echo "Using tab: window=$TAB_WI tab=$TAB_TI"
echo "URL: $TAB_URL"

tab_check=$(run_tab_js_json_retry "$TAB_WI" "$TAB_TI" "(function(){
  var u = (location.href || '').toLowerCase();
  var onDouyin = u.indexOf('douyin.com') >= 0;
  var onFavorite = /favorite_collection|showtab=favorite_collection|\\/favorite/.test(u);
  return JSON.stringify({ onDouyin: onDouyin, onFavorite: onFavorite, url: location.href || '' });
})()" "check current tab state")

needs_open_favorite=$(node -e '
const o = JSON.parse(process.argv[1]);
process.stdout.write((!o.onDouyin || !o.onFavorite) ? "1" : "0");
' "$tab_check")

if [[ "$needs_open_favorite" == "1" ]]; then
  echo "Detected not on Douyin favorites page, opening favorites page..."
  opened=0
  for ((attempt=1; attempt<=HARD_RETRIES; attempt++)); do
    run_tab_js_retry "$TAB_WI" "$TAB_TI" "(function(){
      try {
        location.href = '$FAVORITES_URL';
        return 'navigating_to_favorites';
      } catch (e) {
        return 'navigate_failed';
      }
    })()" "navigate to favorites page" >/dev/null
    sleep_ms_with_jitter 2600 0.45
    tab_check=$(run_tab_js_json_retry "$TAB_WI" "$TAB_TI" "(function(){
      var u = (location.href || '').toLowerCase();
      var onDouyin = u.indexOf('douyin.com') >= 0;
      var onFavorite = /favorite_collection|showtab=favorite_collection|\\/favorite/.test(u);
      return JSON.stringify({ onDouyin: onDouyin, onFavorite: onFavorite, url: location.href || '' });
    })()" "verify favorites page after navigation")
    needs_open_favorite=$(node -e '
const o = JSON.parse(process.argv[1]);
process.stdout.write((!o.onDouyin || !o.onFavorite) ? "1" : "0");
' "$tab_check")
    if [[ "$needs_open_favorite" == "0" ]]; then
      opened=1
      break
    fi
    echo "Favorites page not ready yet (attempt ${attempt}/${HARD_RETRIES}), retrying..." >&2
  done
  if [[ "$opened" != "1" ]]; then
    echo "Failed to open Douyin favorites page after ${HARD_RETRIES} attempts." >&2
    exit 1
  fi
fi

current_checked_url=$(node -e 'const o=JSON.parse(process.argv[1]);process.stdout.write(o.url||"");' "$tab_check")
echo "URL: $current_checked_url"

# Force one reload to reduce stale favorites list after recent user actions.
run_tab_js_retry "$TAB_WI" "$TAB_TI" '(function(){try{location.reload();return "reloading";}catch(e){return "reload_failed";}})()' "reload favorites page" >/dev/null
sleep_ms_with_jitter 1900 0.35

run_tab_js_retry "$TAB_WI" "$TAB_TI" '(function(){window.__dyMap={};window.scrollTo(0,0);return "ok";})()' "initialize map and scroll top" >/dev/null

stable=0
prev=""
for ((i=1; i<=MAX_STEPS; i++)); do
  step_json=$(run_tab_js_json_retry "$TAB_WI" "$TAB_TI" "(function(){
    window.__dyMap = window.__dyMap || {};
    function toAbs(href){
      try { return new URL(href, location.origin).toString().split('?')[0]; } catch(e){ return ''; }
    }
    function firstText(el){
      if (!el) return '';
      var txt = (el.innerText || '').split('\\n').map(function(s){ return s.trim(); }).filter(Boolean);
      for (var i = 0; i < txt.length; i++) {
        var t = txt[i];
        if (!t) continue;
        if (t.length <= 2) continue;
        if (/^icon$/i.test(t)) continue;
        return t;
      }
      return '';
    }
    function coverFrom(el){
      if (!el) return '';
      var imgs = Array.from(el.querySelectorAll('img'));
      if (imgs.length) {
        for (var i = 0; i < imgs.length; i++) {
          var cand = imgs[i].currentSrc || imgs[i].getAttribute('src') || imgs[i].getAttribute('data-src') || '';
          if (!cand) continue;
          var low = cand.toLowerCase();
          if (low.includes('emblem') || low.includes('avatar') || low.includes('default')) continue;
          if (low.includes('douyinpic.com') || low.includes('cropcenter') || low.includes('tos-cn')) return cand;
        }
        for (var j = 0; j < imgs.length; j++) {
          var fallback = imgs[j].currentSrc || imgs[j].getAttribute('src') || imgs[j].getAttribute('data-src') || '';
          if (fallback && !fallback.toLowerCase().includes('emblem')) return fallback;
        }
      }
      var bgEl = el.querySelector('[style*=\"background-image\"]');
      if (bgEl) {
        var bg = bgEl.style && bgEl.style.backgroundImage ? bgEl.style.backgroundImage : '';
        var m = bg && bg.match(/url\\([\"']?(.*?)[\"']?\\)/i);
        if (m) return m[1];
      }
      return '';
    }

    var anchors = Array.from(document.querySelectorAll('a[href*=\"/video/\"]'));
    for (var ai = 0; ai < anchors.length; ai++) {
      var a = anchors[ai];
      var href = a.getAttribute('href') || '';
      if (!href || href.indexOf('/video/') < 0) continue;
      var block = a.closest('[data-e2e]');
      var blockE2E = (block && block.getAttribute('data-e2e') || '').toLowerCase();
      if (blockE2E === 'page-footer') continue;
      var url = toAbs(href);
      if (!url) continue;

      var card = a.closest('[data-e2e*=\"item\" i]') || a.closest('li') || a.closest('article') || a.closest('div');
      if (!card) card = a.closest('[data-e2e]') || a;
      var title = '';
      title = (a.getAttribute('title') || '').trim();
      if (!title && card) {
        var titleEl = card.querySelector('[data-e2e*=\"title\" i]') ||
          card.querySelector('[data-e2e*=\"desc\" i]') ||
          card.querySelector('h3,h4,[title],[aria-label]');
        if (titleEl) {
          title = (titleEl.getAttribute('title') || titleEl.getAttribute('aria-label') || titleEl.textContent || '').trim();
        }
      }
      if (!title) {
        var img = a.querySelector('img') || (card ? card.querySelector('img') : null);
        if (img) title = (img.getAttribute('alt') || '').trim();
      }
      if (!title) title = firstText(card || a);
      if (/^icon$/i.test(title)) title = '';
      title = title.replace(/[\\r\\n\\t]+/g, ' ').replace(/\\s{2,}/g, ' ').trim();

      var cover = coverFrom(a) || coverFrom(card);
      var mid = url.match(/\\/video\\/(\\d+)/);
      var videoId = mid ? mid[1] : '';
      window.__dyMap[url] = { title: title, url: url, video_id: videoId, cover: cover };
    }

    var y = window.scrollY;
    var h = document.body ? document.body.scrollHeight : 0;
    var minRatio = ${SCROLL_RATIO_MIN};
    var maxRatio = ${SCROLL_RATIO_MAX};
    var ratio = minRatio + Math.random() * (maxRatio - minRatio);
    var delta = Math.max(240, Math.floor(window.innerHeight * ratio));
    window.scrollBy(0, delta);
    return JSON.stringify({ count: Object.keys(window.__dyMap).length, y: y, h: h, delta: delta });
  })()" "collect favorites step #${i}")

  parsed=$(node -e 'const o=JSON.parse(process.argv[1]);process.stdout.write(`${o.count}\t${o.y}\t${o.h}\t${o.delta||0}`);' "$step_json")
  count=$(printf '%s' "$parsed" | cut -f1)
  y=$(printf '%s' "$parsed" | cut -f2)
  h=$(printf '%s' "$parsed" | cut -f3)
  delta=$(printf '%s' "$parsed" | cut -f4)
  key="$count|$y|$h"

  echo "step=$i count=$count y=$y h=$h delta=$delta"

  if [[ "$key" == "$prev" ]]; then
    stable=$((stable + 1))
  else
    stable=0
    prev="$key"
  fi

  if [[ $stable -ge 8 ]]; then
    break
  fi

  sleep_ms_with_jitter "$SLEEP_MS" "$SLEEP_JITTER_RATIO"
done

mkdir -p "$OUT_DIR"
stamp=$(date +"%Y%m%d_%H%M%S")
json_file="$OUT_DIR/douyin_favorites_${stamp}.json"
csv_file="$OUT_DIR/douyin_favorites_${stamp}.csv"
txt_file="$OUT_DIR/douyin_favorites_${stamp}.txt"

all_json=$(run_tab_js_json_retry "$TAB_WI" "$TAB_TI" "(function(){
  var arr = Object.values(window.__dyMap || {});
  arr.sort(function(a,b){ return (a.url||'').localeCompare(b.url||''); });
  return JSON.stringify(arr);
})()" "finalize favorites payload")

printf '%s\n' "$all_json" > "$json_file"

node -e '
const fs=require("fs");
const arr=JSON.parse(fs.readFileSync(process.argv[1],"utf8"));
const csvOut=process.argv[2];
const txtOut=process.argv[3];
const clean=(s)=>String(s ?? "").replace(/[\r\n\t]+/g," ").replace(/\s{2,}/g," ").trim();
const esc=(s)=>`"${clean(s).replace(/"/g, "\"\"")}"`;
const csv=["video_id,title,url,cover"];
for(const it of arr){
  csv.push([it.video_id||"",it.title||"",it.url||"",it.cover||""].map(esc).join(","));
}
fs.writeFileSync(csvOut,csv.join("\n")+"\n","utf8");
fs.writeFileSync(txtOut,arr.map(it=>it.url||"").filter(Boolean).join("\n")+"\n","utf8");
console.log(arr.length);
' "$json_file" "$csv_file" "$txt_file" > /tmp/dy_export_count.txt

count=$(cat /tmp/dy_export_count.txt)

echo "DONE"
echo "count=$count"
echo "json=$json_file"
echo "csv=$csv_file"
echo "txt=$txt_file"
