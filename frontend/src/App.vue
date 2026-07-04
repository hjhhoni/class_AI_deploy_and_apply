<template>
    <div class="app">
        <header class="header">
            <h1>知识图谱提取与可视化系统</h1>
            <p>上传 PDF / Word 文档，AI 自动构建 2D 交互式知识图谱 · 悬停查看详情 · 单击高亮邻居</p>
        </header>

        <div class="workspace">
            <div class="sidebar" :class="{ collapsed: graphData }">
                <el-card class="upload-card">
                    <template #header><span>文档上传</span></template>
                    <el-upload
                        class="upload-area"
                        drag
                        :auto-upload="false"
                        :on-change="handleFileChange"
                        :limit="1"
                        accept=".pdf,.docx,.doc"
                    >
                        <el-icon :size="40"><UploadFilled /></el-icon>
                        <div class="upload-text">拖拽文件到此处，或点击上传</div>
                        <div class="upload-hint">支持 PDF / Word (.docx)</div>
                    </el-upload>
                </el-card>

                <el-card v-if="markdownContent" class="preview-card">
                    <template #header>
                        <span>文本预览 ({{ charCount }} 字符)</span>
                        <el-tag v-if="graphData" type="success" size="small" style="margin-left: 8px">已完成</el-tag>
                    </template>
                    <div class="preview-box">
                        {{ markdownContent.slice(0, 800) }}{{ markdownContent.length > 800 ? '...' : '' }}
                    </div>
                </el-card>

                <el-button
                    v-if="markdownContent && !graphData"
                    type="primary"
                    size="large"
                    :loading="extracting"
                    @click="extractGraph"
                    style="width: 100%; margin-top: 8px"
                >
                    {{ extracting ? 'AI 分析中...' : '提取知识图谱' }}
                </el-button>

                <el-card v-if="graphData" class="legend-card">
                    <template #header><span>图例（点击高亮该类）</span></template>
                    <div class="legend">
                        <span
                            v-for="(color, cat) in categoryColors"
                            :key="cat"
                            class="legend-item"
                            :class="{ active: activeCategory === cat, dim: activeCategory && activeCategory !== cat }"
                            @click="toggleCategory(cat)"
                        >
                            <span class="legend-dot" :style="{ background: color }"></span>
                            {{ cat }}
                        </span>
                    </div>
                    <div class="legend-hint">滚轮缩放 · 拖拽平移 · 悬停看详情</div>
                    <el-button class="dl-btn-main" type="primary" :icon="Download" @click="downloadGraphHtml">下载图谱 (HTML)</el-button>
                </el-card>
            </div>

            <div class="graph-wrap">
            <div class="graph-container" ref="graphContainer"></div>
            <div v-if="!markdownContent" class="placeholder">
                <el-icon :size="60"><Document /></el-icon>
                <p>上传文档开始分析</p>
            </div>
            <div v-else-if="extracting" class="loading-overlay">
                <div class="loading-network">
                    <svg class="loading-svg" viewBox="0 0 200 200">
                        <g class="ln-group">
                            <line class="ln" x1="100" y1="100" x2="100" y2="38" />
                            <line class="ln" x1="100" y1="100" x2="158" y2="62" />
                            <line class="ln" x1="100" y1="100" x2="158" y2="138" />
                            <line class="ln" x1="100" y1="100" x2="100" y2="162" />
                            <line class="ln" x1="100" y1="100" x2="42" y2="138" />
                            <line class="ln" x1="100" y1="100" x2="42" y2="62" />
                            <line class="ln ln-ring" x1="100" y1="38" x2="158" y2="62" />
                            <line class="ln ln-ring" x1="158" y1="62" x2="158" y2="138" />
                            <line class="ln ln-ring" x1="158" y1="138" x2="100" y2="162" />
                            <line class="ln ln-ring" x1="100" y1="162" x2="42" y2="138" />
                            <line class="ln ln-ring" x1="42" y1="138" x2="42" y2="62" />
                            <line class="ln ln-ring" x1="42" y1="62" x2="100" y2="38" />
                        </g>
                        <circle class="nd outer" cx="100" cy="38" r="6" style="animation-delay:0s" />
                        <circle class="nd outer" cx="158" cy="62" r="6" style="animation-delay:.25s" />
                        <circle class="nd outer" cx="158" cy="138" r="6" style="animation-delay:.5s" />
                        <circle class="nd outer" cx="100" cy="162" r="6" style="animation-delay:.75s" />
                        <circle class="nd outer" cx="42" cy="138" r="6" style="animation-delay:1s" />
                        <circle class="nd outer" cx="42" cy="62" r="6" style="animation-delay:1.25s" />
                        <circle class="nd center" cx="100" cy="100" r="11" />
                    </svg>
                </div>
                <p class="loading-text">{{ loadingStages[loadingStageIdx] }}</p>
                <div class="loading-bar"><div class="loading-bar-fill"></div></div>
                <p class="loading-sub">本地大模型推理中，长文档可能需要 30–90 秒</p>
            </div>
            <div v-if="graphData" class="graph-toolbar">
                <span class="graph-stats">{{ graphData.nodes.length }} 节点 · {{ graphData.links.length }} 关系</span>
                <el-button class="dl-btn" size="small" :icon="Download" @click="downloadGraphHtml">下载图谱</el-button>
            </div>

            <div v-if="hoveredCard" class="node-detail">
                <div class="node-detail-head">
                    <span class="node-detail-dot" :style="{ background: categoryColors[hoveredCard.category] || '#778ca3' }"></span>
                    <h3>{{ hoveredCard.name }}</h3>
                </div>
                <el-tag size="small">{{ hoveredCard.category }}</el-tag>
                <p v-if="hoveredCard.desc">{{ hoveredCard.desc }}</p>
                <p v-else class="muted">（该节点暂无描述）</p>
            </div>
            </div>
        </div>
    </div>
</template>

<script setup>
import { ref, nextTick, onMounted, onBeforeUnmount } from 'vue';
import { UploadFilled, Document, Download } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import axios from 'axios';
import ForceGraph from 'force-graph';

const markdownContent = ref('');
const charCount = ref(0);
const extracting = ref(false);
const graphData = ref(null);
const hoveredCard = ref(null);
const activeCategory = ref(null);
const graphContainer = ref(null);
const uploadedName = ref('');
let forceGraph = null;

// 加载阶段文字轮播（前端无法拿到分块中间进度，用阶段提示替代真实百分比）
const loadingStages = ['正在读取文档…', '提取实体要素…', '分析实体关系…', '构建知识网络…', '优化图谱结构…'];
const loadingStageIdx = ref(0);
let loadingTimer = null;

// 邻居高亮状态（高频回调用普通变量，避免响应式开销）
let hoverNode = null; // 悬停节点引用（驱动详情卡片 + 节点强化反馈）
let resizeObserver = null;
// 双击高亮：双击节点后固定高亮其邻居与关联边
let pinnedNode = null;
let pinnedNeighbors = new Set();
let pinnedLinks = new Set();

const categoryColors = {
    人物: '#ff6b6b',
    组织: '#4ecdc4',
    概念: '#45b7d1',
    事件: '#f9ca24',
    地点: '#a55eea',
    技术: '#26de81',
    作品: '#fed330',
    领域: '#2bcbba',
    其他: '#778ca3',
};

function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
}

function hexToRgba(hex, alpha) {
    const h = hex.replace('#', '');
    const r = parseInt(h.substring(0, 2), 16);
    const g = parseInt(h.substring(2, 4), 16);
    const b = parseInt(h.substring(4, 6), 16);
    return `rgba(${r},${g},${b},${alpha})`;
}

// ---------- 本地持久化：刷新不丢文档与图谱 ----------
const STORAGE_KEY = 'kg_state_v1';

// 把图谱清洗成可安全序列化的纯数据（剥离 force-graph 运行时附加的 neighbors/links/x/y 等）
function cleanGraph(data) {
    return {
        nodes: (data.nodes || []).map((n) => ({ id: n.id, name: n.name, category: n.category, desc: n.desc || '' })),
        links: (data.links || []).map((l) => ({
            source: l.source && typeof l.source === 'object' ? l.source.id : l.source,
            target: l.target && typeof l.target === 'object' ? l.target.id : l.target,
            label: l.label || '',
        })),
    };
}

function saveState() {
    try {
        localStorage.setItem(
            STORAGE_KEY,
            JSON.stringify({
                markdownContent: markdownContent.value,
                charCount: charCount.value,
                uploadedName: uploadedName.value,
                graphData: graphData.value ? cleanGraph(graphData.value) : null,
            })
        );
    } catch (e) {
        // localStorage 满或被禁用时静默忽略
    }
}

function loadState() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (!raw) return;
        const s = JSON.parse(raw);
        if (s.markdownContent) markdownContent.value = s.markdownContent;
        if (s.charCount) charCount.value = s.charCount;
        if (s.uploadedName) uploadedName.value = s.uploadedName;
        if (s.graphData) graphData.value = s.graphData;
    } catch (e) {
        // 数据损坏时静默忽略
    }
}

async function handleFileChange(file) {
    markdownContent.value = '';
    graphData.value = null;
    hoveredCard.value = null;
    const formData = new FormData();
    formData.append('file', file.raw);
    try {
        const res = await axios.post('/api/upload', formData);
        markdownContent.value = res.data.markdown;
        charCount.value = res.data.char_count;
        uploadedName.value = res.data.filename || file.name;
        ElMessage.success('提取成功，' + charCount.value + ' 个字符');
        saveState();
    } catch (e) {
        ElMessage.error(e.response?.data?.detail || '上传失败');
    }
}

async function extractGraph() {
    extracting.value = true;
    loadingStageIdx.value = 0;
    loadingTimer = setInterval(() => {
        loadingStageIdx.value = (loadingStageIdx.value + 1) % loadingStages.length;
    }, 2600);
    try {
        const res = await axios.post('/api/extract-graph', { content: markdownContent.value });
        graphData.value = res.data;
        ElMessage.success('图谱提取成功: ' + res.data.nodes.length + ' 个节点');
        await nextTick();
        renderGraph();
        saveState();
    } catch (e) {
        ElMessage.error(e.response?.data?.detail || '提取失败');
    } finally {
        extracting.value = false;
        if (loadingTimer) {
            clearInterval(loadingTimer);
            loadingTimer = null;
        }
    }
}

function toggleCategory(cat) {
    activeCategory.value = activeCategory.value === cat ? null : cat;
    // 点击图例时取消节点单击的高亮，避免两类高亮叠加冲突
    pinnedNode = null;
    pinnedNeighbors = new Set();
    pinnedLinks = new Set();
    // 力模拟冷却后 canvas 不再重绘，切换图例需手动 reheat 触发一次重绘，让"聚光灯"生效。
    if (forceGraph) forceGraph.d3ReheatSimulation();
}

// 导出 HTML 中运行的渲染脚本（刻意只用字符串拼接，避免反引号/模板语法污染外层模板）
const RENDER_SCRIPT = `
(function(){
  var el = document.getElementById('graph');
  var cardEl = document.getElementById('node-card');
  var nodes = (DATA.nodes||[]).map(function(n){ return Object.assign({}, n, {neighbors:[], links:[]}); });
  var byId = {}; nodes.forEach(function(n){ byId[n.id]=n; });
  var links = (DATA.links||[]).filter(function(l){
    var s=byId[l.source], t=byId[l.target];
    if(!s||!t||s===t) return false;
    var link=Object.assign({},l);
    s.neighbors.push(t); t.neighbors.push(s);
    s.links.push(link); t.links.push(link);
    return true;
  });
  var hoverNode=null;
  var pinnedNode=null, pinnedNeighbors=new Set();
  var catActive=null;

  function hexToRgba(hex,a){
    var h=String(hex).replace('#','');
    var r=parseInt(h.substring(0,2),16),g=parseInt(h.substring(2,4),16),b=parseInt(h.substring(4,6),16);
    return 'rgba('+r+','+g+','+b+','+a+')';
  }
  function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];}); }
  function endId(end){ return end && typeof end==='object' ? end.id : end; }
  function linkHitPinned(link){ return pinnedNode && (endId(link.source)===pinnedNode.id || endId(link.target)===pinnedNode.id); }
  function linkHitCat(link){ return catActive && (link.source.category===catActive || link.target.category===catActive); }

  function showCard(node){
    if(!node || !cardEl){ if(cardEl) cardEl.style.display='none'; return; }
    var color = CATEGORY_COLORS[node.category]||'#778ca3';
    cardEl.innerHTML = '<div class="card-head"><span class="card-dot" style="background:'+color+';box-shadow:0 0 8px '+color+';"></span><span class="card-name">'+esc(node.name)+'</span></div><div class="card-cat">'+esc(node.category||'')+'</div>'+(node.desc?'<div class="card-desc">'+esc(node.desc)+'</div>':'<div class="card-desc muted">暂无描述</div>');
    cardEl.style.display='block';
  }

  var graph = ForceGraph()(el)
    .graphData({nodes:nodes, links:links})
    .backgroundColor('rgba(0,0,0,0)')
    .nodeRelSize(10)
    .nodeCanvasObjectMode(function(){ return 'replace'; })
    .nodeCanvasObject(function(node, ctx, gs){
      if(!gs||!isFinite(gs)||!isFinite(node.x)||!isFinite(node.y)) return;
      var baseR=11/gs;
      var color=CATEGORY_COLORS[node.category]||'#778ca3';
      var isHover=hoverNode===node;
      var isPinned=pinnedNode===node;
      var isNeighbor=pinnedNeighbors.has(node);
      var catMatch=catActive && node.category===catActive;
      var dim=(pinnedNode && !isPinned && !isNeighbor) || (catActive && !catMatch);
      var boosted=isHover||isPinned||catMatch;
      var r=boosted?baseR*1.4:baseR;
      ctx.globalAlpha=dim?0.1:1;
      var glowR=r*(boosted?3.4:2.3);
      var grad=ctx.createRadialGradient(node.x,node.y,r*0.4,node.x,node.y,glowR);
      grad.addColorStop(0,hexToRgba(color,boosted?0.62:0.4));
      grad.addColorStop(1,hexToRgba(color,0));
      ctx.beginPath(); ctx.arc(node.x,node.y,glowR,0,2*Math.PI);
      ctx.fillStyle=grad; ctx.fill();
      ctx.beginPath(); ctx.arc(node.x,node.y,r,0,2*Math.PI);
      ctx.fillStyle=color; ctx.fill();
      ctx.lineWidth=(boosted?2.6:1.2)/gs;
      ctx.strokeStyle=boosted?'#ffffff':hexToRgba(color,0.7);
      ctx.stroke();
      var fs=13/gs;
      ctx.font='600 '+fs+'px "Microsoft YaHei","PingFang SC",sans-serif';
      ctx.textAlign='center'; ctx.textBaseline='top';
      var ty=node.y+r+4/gs;
      ctx.lineWidth=3.5/gs; ctx.strokeStyle='rgba(5,5,20,0.92)'; ctx.lineJoin='round';
      ctx.strokeText(node.name,node.x,ty);
      ctx.fillStyle=boosted?'#ffffff':'#eaeaf2';
      ctx.fillText(node.name,node.x,ty);
      ctx.globalAlpha=1;
    })
    .onNodeHover(function(node){
      hoverNode=node||null;
      showCard(node);
      el.style.cursor=node?'pointer':'grab';
    })
    .onNodeClick(function(node){
      if(!node) return;
      if(pinnedNode===node){ pinnedNode=null; pinnedNeighbors=new Set(); }
      else { pinnedNode=node; pinnedNeighbors=new Set(node.neighbors||[]); }
      graph.d3ReheatSimulation();
    })
    .linkColor(function(link){
      if(pinnedNode) return linkHitPinned(link)?'rgba(120,210,255,0.95)':'rgba(150,170,210,0.04)';
      if(catActive)  return linkHitCat(link)?'rgba(120,210,255,0.85)':'rgba(150,170,210,0.04)';
      return 'rgba(150,170,210,0.3)';
    })
    .linkWidth(function(link){
      if(pinnedNode && linkHitPinned(link)) return 2.2;
      if(catActive) return linkHitCat(link)?1.8:0.5;
      return 1;
    })
    .linkDirectionalArrowLength(5)
    .linkDirectionalArrowRelPos(1)
    .linkDirectionalArrowColor(function(link){
      if(pinnedNode && linkHitPinned(link)) return 'rgba(120,210,255,0.95)';
      if(catActive) return linkHitCat(link)?'rgba(120,210,255,0.85)':'rgba(150,170,210,0.1)';
      return 'rgba(150,170,210,0.5)';
    })
    .linkLabel(function(link){ return link.label?'<span class="kg-link-tip">'+esc(link.label)+'</span>':''; })
    .linkHoverPrecision(2)
    .cooldownTicks(150);
  graph.d3Force('charge').strength(-320);
  graph.d3Force('link').distance(85).strength(0.5);
  graph.d3Force('center', null);
  // 弹性拖拽：拖时释放非被拖节点让弹簧跟随、松手回弹、稳定后重新锁位防漂移
  graph.onNodeDrag(function(node){
    var ns=graph.graphData().nodes;
    for(var i=0;i<ns.length;i++){ if(ns[i]!==node){ ns[i].fx=null; ns[i].fy=null; } }
  });
  graph.onNodeDragEnd(function(node){ if(node){ node.fx=null; node.fy=null; } });
  graph.onEngineStop(function(){
    var ns=graph.graphData().nodes;
    for(var i=0;i<ns.length;i++){ if(ns[i].x!=null && isFinite(ns[i].x)){ ns[i].fx=ns[i].x; ns[i].fy=ns[i].y; } }
  });
  // 图例点击聚光灯
  var legendItems=document.querySelectorAll('.legend-item');
  legendItems.forEach(function(it){
    it.addEventListener('click', function(){
      var c=it.getAttribute('data-cat');
      catActive = (catActive===c)?null:c;
      legendItems.forEach(function(x){ x.classList.toggle('active', x.getAttribute('data-cat')===catActive); });
      graph.d3ReheatSimulation();
    });
  });
  window.addEventListener('resize', function(){ graph.width(el.clientWidth).height(el.clientHeight); });
})();
`;

function buildGraphHtml(data, title, libSrc) {
    const safeTitle = escapeHtml(title);
    // force-graph 会原地给节点加 neighbors/links/x/y 等，link.source/target 也会被改成对象，
    // 直接 JSON.stringify 会因 neighbors 互相引用而“circular structure”报错。
    // 导出前只挑出干净字段重建，剥离所有运行时附加属性。
    const clean = cleanGraph(data);
    const dataJson = JSON.stringify(clean).replace(/</g, '\\u003c');
    const colorsJson = JSON.stringify(categoryColors).replace(/</g, '\\u003c');
    const legendHtml = Object.entries(categoryColors)
        .filter(([cat]) => data.nodes.some((n) => n.category === cat))
        .map(([cat, color]) => `<span class="legend-item" data-cat="${cat}"><span class="legend-dot" style="background:${color};color:${color}"></span>${cat}</span>`)
        .join('');
    return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>知识图谱 · ${safeTitle}</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;}
body{background:#07071a;font-family:'Microsoft YaHei','PingFang SC',sans-serif;overflow:hidden;}
#graph{width:100vw;height:100vh;}
.info{position:fixed;top:14px;left:16px;color:#9aa;font-size:13px;background:rgba(0,0,0,.35);padding:8px 14px;border-radius:10px;backdrop-filter:blur(6px);border:1px solid rgba(255,255,255,.06);line-height:1.7;z-index:5;}
.info b{color:#d6e6ff;}
.info .sub{font-size:11px;color:#6a6a86;}
.legend{position:fixed;top:14px;right:16px;display:flex;flex-wrap:wrap;gap:6px;max-width:55vw;justify-content:flex-end;z-index:5;}
.legend-item{display:flex;align-items:center;gap:5px;font-size:12px;color:#bbb;padding:4px 9px;border-radius:12px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.06);cursor:pointer;user-select:none;}
.legend-item:hover{background:rgba(255,255,255,.1);color:#ddd;}
.legend-item.active{background:rgba(120,210,255,.15);border-color:rgba(120,210,255,.4);color:#fff;}
.legend-dot{width:10px;height:10px;border-radius:50%;}
#node-card{position:fixed;bottom:16px;left:16px;background:rgba(12,13,32,.96);border:1px solid rgba(120,210,255,.2);border-radius:10px;padding:14px 18px;max-width:280px;backdrop-filter:blur(10px);box-shadow:0 8px 30px rgba(0,0,0,.5);display:none;z-index:10;}
.card-head{display:flex;align-items:center;gap:8px;margin-bottom:6px;}
.card-dot{width:12px;height:12px;border-radius:50%;flex-shrink:0;}
.card-name{font-size:16px;font-weight:600;color:#fff;}
.card-cat{font-size:12px;color:#8ab4ff;margin-bottom:6px;}
.card-desc{font-size:13px;color:#bbb;line-height:1.5;}
.card-desc.muted{color:#555;font-style:italic;}
.kg-link-tip{background:rgba(15,16,38,.9);border:1px solid rgba(120,210,255,.2);border-radius:6px;padding:3px 8px;font-size:12px;color:#b0c8e8;}
.graph-tooltip{background:transparent!important;padding:0!important;}
</style>
</head>
<body>
<div id="graph"></div>
<div class="info">知识图谱 · <b>${data.nodes.length}</b> 节点 · <b>${data.links.length}</b> 关系<br><span class="sub">悬停看详情 · 单击高亮邻居 · 滚轮缩放 · 拖拽平移</span></div>
<div class="legend">${legendHtml}</div>
<div id="node-card"></div>
<script>
${libSrc}
<\/script>
<script>
var DATA = ${dataJson};
var CATEGORY_COLORS = ${colorsJson};
${RENDER_SCRIPT}
<\/script>
</body>
</html>`;
}

let _libCache = null;
async function downloadGraphHtml() {
    if (!graphData.value) return;
    try {
        // force-graph 的 package.json 用 exports 字段封了子路径，无法 ?raw import；
        // 改为把 UMD 包放到 public/，运行时 fetch 取文本，内联进导出的 HTML。
        if (!_libCache) {
            const res = await fetch('/force-graph.min.js');
            if (!res.ok) throw new Error('force-graph 库加载失败 (' + res.status + ')');
            _libCache = await res.text();
        }
        const title = uploadedName.value || '知识图谱';
        const html = buildGraphHtml(graphData.value, title, _libCache);
        const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = title.replace(/[\\/:*?"<>|]/g, '_') + '_知识图谱.html';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(url), 2000);
        ElMessage.success('已下载，双击 HTML 文件即可在浏览器离线打开');
    } catch (e) {
        ElMessage.error('下载失败: ' + (e.message || e));
    }
}

function renderGraph() {
    if (forceGraph) {
        forceGraph._destructor && forceGraph._destructor();
        forceGraph = null;
    }
    const el = graphContainer.value;
    el.querySelector('canvas')?.remove();

    // 预处理：建立邻居索引，并隔离原始数据避免被库改写
    const nodes = (graphData.value.nodes || []).map((n) => ({ ...n, neighbors: [], links: [] }));
    const nodeById = Object.fromEntries(nodes.map((n) => [n.id, n]));
    const links = (graphData.value.links || []).filter((l) => {
        const s = nodeById[l.source];
        const t = nodeById[l.target];
        if (!s || !t || s === t) return false;
        const link = { ...l };
        s.neighbors.push(t);
        t.neighbors.push(s);
        s.links.push(link);
        t.links.push(link);
        return true;
    });

    hoverNode = null;
    pinnedNode = null;
    pinnedNeighbors = new Set();
    pinnedLinks = new Set();
    hoveredCard.value = null;

    forceGraph = ForceGraph()(el)
        .graphData({ nodes, links })
        .backgroundColor('rgba(0,0,0,0)')
        .nodeRelSize(10)
        .nodeCanvasObjectMode(() => 'replace')
        .nodeCanvasObject((node, ctx, globalScale) => {
            // 防御：极端缩放/初始帧/孤立节点时 globalScale 或坐标可能为 NaN/0，
            // 11/globalScale 会得到 Infinity，传给 arc()/createRadialGradient 抛 non-finite。
            if (!globalScale || !isFinite(globalScale) || !isFinite(node.x) || !isFinite(node.y)) return;
            const baseR = 11 / globalScale;
            const color = categoryColors[node.category] || '#778ca3';
            const isHover = hoverNode === node;
            const isPinned = pinnedNode === node;
            const isNeighbor = pinnedNeighbors.has(node);
            const catActive = activeCategory.value;
            const catMatch = catActive && node.category === catActive;
            // 双击高亮 或 图例选中 时，非相关节点淡化
            const dim = (pinnedNode && !isPinned && !isNeighbor) || (catActive && !catMatch);

            // 聚光灯层级：hover / 双击高亮 / 类别选中 都强化；默认收敛；dim 更暗且不画发光
            const boosted = isHover || isPinned || catMatch;
            const r = boosted ? baseR * 1.4 : baseR;

            ctx.globalAlpha = dim ? 0.1 : 1;

            // 外发光（dim 时跳过，既更暗也省渲染）
            if (!dim) {
                const glowR = r * (boosted ? 3.4 : 2.3);
                const glowA = boosted ? 0.62 : 0.4;
                const grad = ctx.createRadialGradient(node.x, node.y, r * 0.4, node.x, node.y, glowR);
                grad.addColorStop(0, hexToRgba(color, glowA));
                grad.addColorStop(1, hexToRgba(color, 0));
                ctx.beginPath();
                ctx.arc(node.x, node.y, glowR, 0, 2 * Math.PI);
                ctx.fillStyle = grad;
                ctx.fill();
            }

            // 主圆
            ctx.beginPath();
            ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
            ctx.fillStyle = color;
            ctx.fill();
            ctx.lineWidth = (boosted ? 2.6 : 1.2) / globalScale;
            ctx.strokeStyle = boosted ? '#ffffff' : hexToRgba(color, 0.7);
            ctx.stroke();

            // 标签（白色描边字，常显）
            const fontSize = 13 / globalScale;
            ctx.font = `600 ${fontSize}px "Microsoft YaHei", "PingFang SC", sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'top';
            const ty = node.y + r + 4 / globalScale;
            ctx.lineWidth = 3.5 / globalScale;
            ctx.strokeStyle = 'rgba(5,5,20,0.92)';
            ctx.lineJoin = 'round';
            ctx.strokeText(node.name, node.x, ty);
            ctx.fillStyle = boosted ? '#ffffff' : '#eaeaf2';
            ctx.fillText(node.name, node.x, ty);

            ctx.globalAlpha = 1;
        })
        .nodeLabel((node) => {
            const color = categoryColors[node.category] || '#778ca3';
            return `
                <div class="kg-tip">
                    <div class="kg-tip-head">
                        <span class="kg-tip-dot" style="background:${color}"></span>
                        <span class="kg-tip-name">${escapeHtml(node.name)}</span>
                    </div>
                    <div class="kg-tip-cat">${escapeHtml(node.category || '')}</div>
                    ${node.desc ? `<div class="kg-tip-desc">${escapeHtml(node.desc)}</div>` : '<div class="kg-tip-desc muted">暂无描述</div>'}
                </div>`;
        })
        .onNodeHover((node) => {
            // 悬停只显示详情卡片（不做邻居高亮，高亮交给双击）
            hoverNode = node || null;
            hoveredCard.value = node
                ? { name: node.name, category: node.category, desc: node.desc }
                : null;
            el.style.cursor = node ? 'pointer' : 'grab';
        })
        .onNodeClick((node) => {
            // 单击节点：toggle 该节点的邻居高亮（canvas 上双击不稳定，改单击）
            if (!node) return;
            if (pinnedNode === node) {
                pinnedNode = null;
                pinnedNeighbors = new Set();
                pinnedLinks = new Set();
            } else {
                pinnedNode = node;
                pinnedNeighbors = new Set(node.neighbors || []);
                pinnedLinks = new Set(node.links || []);
            }
            forceGraph && forceGraph.d3ReheatSimulation();
        })
        .onNodeDrag((node) => {
            // 拖拽中：释放"非被拖节点"的位置锁定，让它们像弹簧一样弹性跟随被拖节点
            forceGraph.graphData().nodes.forEach((n) => {
                if (n !== node) { n.fx = null; n.fy = null; }
            });
        })
        .onNodeDragEnd((node) => {
            // 松手：释放被拖节点，让整图弹性回弹；回弹稳定后 onEngineStop 会重新锁定位置
            if (node) { node.fx = null; node.fy = null; }
        })
        // 注意：不能注册 onBackgroundClick！force-graph 一旦检测到注册了它，
        // 就会启用拖拽判定（pointer 微动即 isPointerDragging=true），导致 pointerup 时
        // 直接 return、onNodeClick 永远不触发。取消高亮改由"再点一次该节点"的 toggle 完成。
        .linkColor((link) => {
            if (pinnedNode) {
                const sId = link.source && typeof link.source === 'object' ? link.source.id : link.source;
                const tId = link.target && typeof link.target === 'object' ? link.target.id : link.target;
                return (sId === pinnedNode.id || tId === pinnedNode.id) ? 'rgba(120,210,255,0.95)' : 'rgba(150,170,210,0.04)';
            }
            const catActive = activeCategory.value;
            if (catActive) {
                const hit = link.source.category === catActive || link.target.category === catActive;
                return hit ? 'rgba(120,210,255,0.85)' : 'rgba(150,170,210,0.04)';
            }
            return 'rgba(150,170,210,0.28)';
        })
        .linkWidth((link) => {
            if (pinnedNode) {
                const sId = link.source && typeof link.source === 'object' ? link.source.id : link.source;
                const tId = link.target && typeof link.target === 'object' ? link.target.id : link.target;
                if (sId === pinnedNode.id || tId === pinnedNode.id) return 2.2;
            }
            const catActive = activeCategory.value;
            if (catActive) {
                const hit = link.source.category === catActive || link.target.category === catActive;
                return hit ? 1.8 : 0.5;
            }
            return 1;
        })
        .linkDirectionalArrowLength(5)
        .linkDirectionalArrowRelPos(1)
        .linkDirectionalArrowColor((link) => {
            if (pinnedNode) {
                const sId = link.source && typeof link.source === 'object' ? link.source.id : link.source;
                const tId = link.target && typeof link.target === 'object' ? link.target.id : link.target;
                if (sId === pinnedNode.id || tId === pinnedNode.id) return 'rgba(120,210,255,0.95)';
            }
            const catActive = activeCategory.value;
            if (catActive) {
                const hit = link.source.category === catActive || link.target.category === catActive;
                return hit ? 'rgba(120,210,255,0.85)' : 'rgba(150,170,210,0.1)';
            }
            return 'rgba(150,170,210,0.5)';
        })
        .linkLabel((link) =>
            link.label ? `<span class="kg-link-tip">${escapeHtml(link.label)}</span>` : ''
        )
        .linkHoverPrecision(2)
        .warmupTicks(120)
        .cooldownTicks(150);

    // 力布局参数：d3Force(name) getter 返回的是 force 对象，不是 graph 实例，
    // 必须脱离链式单独调用，否则后续 graph 方法会报错。
    forceGraph.d3Force('charge').strength(-320);
    forceGraph.d3Force('link').distance(85).strength(0.5);
    forceGraph.d3Force('center', null);

    // 布局稳定后自动适配视野（仅首次；reheat 重绘触发的 stop 不再重置视图）
    let initialZoomDone = false;
    forceGraph.onEngineStop(() => {
        if (!initialZoomDone) {
            forceGraph.zoomToFit(400, 60);
            initialZoomDone = true;
        }
        // 每次 simulation 停止（首次布局后 / 拖拽回弹稳定后）都锁定节点位置，
        // 防止后续点击 reheat（触发高亮重绘）让节点漂移。
        const ns = forceGraph.graphData().nodes;
        for (let i = 0; i < ns.length; i++) {
            if (ns[i].x != null && isFinite(ns[i].x)) {
                ns[i].fx = ns[i].x;
                ns[i].fy = ns[i].y;
            }
        }
    });

    resizeObserver = new ResizeObserver(() => {
        if (forceGraph) forceGraph.width(el.clientWidth).height(el.clientHeight);
    });
    resizeObserver.observe(el);
}

onMounted(() => {
    // 从 localStorage 恢复上次的文档与图谱，刷新不丢
    loadState();
    if (graphData.value) {
        nextTick(() => renderGraph());
    }
});

onBeforeUnmount(() => {
    if (resizeObserver) resizeObserver.disconnect();
    if (forceGraph) {
        forceGraph._destructor && forceGraph._destructor();
    }
});
</script>

<style>
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}
body {
    background: #0a0a1a;
    font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
    overflow: hidden;
}

/* force-graph 创建的 tooltip 挂在容器内，不受 scoped 影响，放全局 */
.graph-tooltip {
    background: transparent !important;
    padding: 0 !important;
}
.kg-tip {
    background: rgba(15, 16, 38, 0.92);
    border: 1px solid rgba(120, 210, 255, 0.25);
    border-radius: 10px;
    padding: 10px 14px;
    backdrop-filter: blur(8px);
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.55);
    min-width: 150px;
    max-width: 280px;
}
.kg-tip-head {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
}
.kg-tip-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
    box-shadow: 0 0 8px currentColor;
}
.kg-tip-name {
    font-size: 15px;
    font-weight: 600;
    color: #fff;
}
.kg-tip-cat {
    font-size: 12px;
    color: #8ab4ff;
    margin-bottom: 6px;
}
.kg-tip-desc {
    font-size: 13px;
    color: #c8c8d4;
    line-height: 1.5;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
    padding-top: 6px;
}
.kg-tip-desc.muted {
    color: #666;
    font-style: italic;
}
.kg-link-tip {
    background: rgba(15, 16, 38, 0.9);
    border: 1px solid rgba(120, 210, 255, 0.2);
    border-radius: 6px;
    padding: 3px 8px;
    font-size: 12px;
    color: #b0c8e8;
}
</style>

<style scoped>
.app {
    display: flex;
    flex-direction: column;
    height: 100vh;
    color: #e0e0e0;
}
.header {
    text-align: center;
    padding: 14px 20px 6px;
    background: linear-gradient(135deg, #0a0a1a, #1a1a3e);
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    flex-shrink: 0;
}
.header h1 {
    font-size: 22px;
    background: linear-gradient(135deg, #4ecdc4, #a55eea);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.header p {
    font-size: 13px;
    color: #888;
    margin-top: 4px;
}
.workspace {
    display: flex;
    flex: 1;
    overflow: hidden;
}
.sidebar {
    width: 340px;
    padding: 12px;
    overflow-y: auto;
    flex-shrink: 0;
    transition: width 0.3s;
    display: flex;
    flex-direction: column;
    gap: 10px;
    background: rgba(255, 255, 255, 0.02);
}
.sidebar.collapsed {
    width: 280px;
}
.upload-card :deep(.el-card__body) {
    padding: 10px;
}
.upload-area :deep(.el-upload) {
    width: 100%;
}
.upload-area :deep(.el-upload-dragger) {
    background: rgba(255, 255, 255, 0.03);
    border-color: rgba(255, 255, 255, 0.1);
    padding: 20px;
}
.upload-text {
    font-size: 14px;
    margin-top: 8px;
    color: #aaa;
}
.upload-hint {
    font-size: 12px;
    color: #666;
    margin-top: 4px;
}
.preview-card :deep(.el-card__body) {
    padding: 6px 10px;
}
.preview-box {
    max-height: 180px;
    overflow-y: auto;
    font-size: 12px;
    color: #999;
    white-space: pre-wrap;
    line-height: 1.6;
    background: rgba(0, 0, 0, 0.3);
    padding: 8px;
    border-radius: 4px;
}
.legend-card :deep(.el-card__body) {
    padding: 8px 10px;
}
.legend {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
}
.legend-item {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    color: #aaa;
    padding: 3px 8px;
    border-radius: 12px;
    cursor: pointer;
    transition: all 0.2s;
    border: 1px solid transparent;
}
.legend-item:hover {
    background: rgba(255, 255, 255, 0.06);
    color: #ddd;
}
.legend-item.active {
    background: rgba(120, 210, 255, 0.15);
    border-color: rgba(120, 210, 255, 0.4);
    color: #fff;
}
.legend-item.dim {
    opacity: 0.4;
}
.legend-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    display: inline-block;
}
.legend-hint {
    margin-top: 8px;
    font-size: 11px;
    color: #555;
    text-align: center;
}
.graph-wrap {
    flex: 1;
    position: relative;
    min-height: 400px;
    min-width: 0;
    display: flex;
}
.graph-container {
    flex: 1;
    position: relative;
    overflow: hidden;
    background:
        radial-gradient(circle at 30% 20%, rgba(78, 205, 196, 0.06), transparent 40%),
        radial-gradient(circle at 75% 80%, rgba(165, 94, 234, 0.07), transparent 45%),
        #07071a;
}
.placeholder {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: #555;
    gap: 12px;
}
.placeholder p {
    font-size: 16px;
}
.rotating {
    animation: spin 1.5s linear infinite;
}
@keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}
/* —— 等待界面：节点网络动画 + 进度条 —— */
.loading-overlay {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 22px;
    background: radial-gradient(circle at center, rgba(78, 205, 196, 0.05), transparent 60%),
        rgba(7, 7, 26, 0.55);
    backdrop-filter: blur(3px);
    z-index: 5;
}
.loading-network {
    width: 190px;
    height: 190px;
}
.loading-svg {
    width: 100%;
    height: 100%;
}
.loading-svg .ln {
    stroke: rgba(120, 210, 255, 0.3);
    stroke-width: 1.5;
    stroke-dasharray: 5 7;
    animation: kg-flow 1.6s linear infinite;
}
.loading-svg .ln-ring {
    stroke: rgba(165, 94, 234, 0.22);
    animation-direction: reverse;
}
@keyframes kg-flow {
    to {
        stroke-dashoffset: -24;
    }
}
.loading-svg .nd {
    fill: #4ecdc4;
    filter: drop-shadow(0 0 6px rgba(78, 205, 196, 0.8));
}
.loading-svg .nd.outer {
    transform-box: fill-box;
    transform-origin: center;
    animation: kg-blink 2s ease-in-out infinite;
}
.loading-svg .nd.center {
    fill: #a55eea;
    filter: drop-shadow(0 0 12px rgba(165, 94, 234, 0.95));
    transform-box: fill-box;
    transform-origin: center;
    animation: kg-pulse 1.6s ease-in-out infinite;
}
@keyframes kg-blink {
    0%,
    100% {
        opacity: 0.35;
        transform: scale(0.8);
    }
    50% {
        opacity: 1;
        transform: scale(1.15);
    }
}
@keyframes kg-pulse {
    0%,
    100% {
        transform: scale(1);
        opacity: 0.9;
    }
    50% {
        transform: scale(1.35);
        opacity: 1;
    }
}
.loading-text {
    font-size: 16px;
    font-weight: 600;
    color: #d6e6ff;
    letter-spacing: 1px;
    min-height: 22px;
}
.loading-bar {
    width: 240px;
    height: 4px;
    background: rgba(255, 255, 255, 0.08);
    border-radius: 4px;
    overflow: hidden;
}
.loading-bar-fill {
    width: 38%;
    height: 100%;
    background: linear-gradient(90deg, #4ecdc4, #a55eea);
    border-radius: 4px;
    box-shadow: 0 0 10px rgba(120, 210, 255, 0.5);
    animation: kg-slide 1.5s ease-in-out infinite;
}
@keyframes kg-slide {
    0% {
        transform: translateX(-110%);
    }
    100% {
        transform: translateX(370%);
    }
}
.loading-sub {
    font-size: 12px;
    color: #6a6a86;
}
.node-detail {
    position: absolute;
    bottom: 16px;
    left: 16px;
    background: rgba(12, 13, 32, 0.96);
    border: 1px solid rgba(120, 210, 255, 0.2);
    border-radius: 10px;
    padding: 14px 18px 14px 16px;
    max-width: 280px;
    backdrop-filter: blur(10px);
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.5);
    z-index: 999;
}
.node-detail-head {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
}
.node-detail-dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    box-shadow: 0 0 8px currentColor;
}
.node-detail h3 {
    font-size: 16px;
    color: #fff;
}
.node-detail p {
    font-size: 13px;
    color: #bbb;
    margin-top: 8px;
    line-height: 1.5;
}
.node-detail p.muted {
    color: #555;
    font-style: italic;
}
.node-detail-close {
    position: absolute;
    top: 8px;
    right: 10px;
    cursor: pointer;
    color: #666;
    font-size: 14px;
}
.node-detail-close:hover {
    color: #fff;
}
.graph-toolbar {
    position: absolute;
    top: 12px;
    right: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
    z-index: 999;
}
.graph-stats {
    font-size: 12px;
    color: #777;
    background: rgba(0, 0, 0, 0.3);
    padding: 4px 10px;
    border-radius: 12px;
    backdrop-filter: blur(4px);
}
.dl-btn {
    --el-button-bg-color: rgba(255, 255, 255, 0.08);
    --el-button-text-color: #d6e6ff;
    --el-button-border-color: rgba(120, 210, 255, 0.3);
    --el-button-hover-bg-color: rgba(120, 210, 255, 0.18);
    --el-button-hover-text-color: #fff;
    --el-button-hover-border-color: rgba(120, 210, 255, 0.5);
    backdrop-filter: blur(4px);
}
.dl-btn-main {
    width: 100%;
    margin-top: 10px;
}
:deep(.el-card) {
    background: rgba(255, 255, 255, 0.04) !important;
    border-color: rgba(255, 255, 255, 0.08) !important;
    color: #e0e0e0 !important;
}
:deep(.el-card__header) {
    color: #ccc !important;
    border-bottom-color: rgba(255, 255, 255, 0.06) !important;
    font-size: 14px !important;
    padding: 10px 14px !important;
}
:deep(.el-button--primary) {
    background: linear-gradient(135deg, #4ecdc4, #a55eea) !important;
    border: none !important;
}
:deep(.el-tag) {
    background: rgba(255, 255, 255, 0.08) !important;
    border-color: rgba(255, 255, 255, 0.12) !important;
    color: #ccc !important;
}
</style>
