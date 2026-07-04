import os
import json
import re
import tempfile
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import httpx
import pdfplumber
from docx import Document

app = FastAPI(title="知识图谱提取与可视化系统")

# CORS 收紧为白名单（原为 allow_origins=["*"]）。
# 仅允许本地前端访问；如需局域网访问，用环境变量 KG_ALLOWED_ORIGINS 追加。
ALLOWED_ORIGINS = os.environ.get(
    "KG_ALLOWED_ORIGINS",
    "http://127.0.0.1:5173,http://localhost:5173",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LLM_API_URL = os.environ.get("LLM_API_URL", "http://localhost:8000/v1/chat/completions")
# 与 run.sh 的 --alias 保持一致，避免请求里写错模型名
MODEL_NAME = os.environ.get("LLM_MODEL", "gemma-4-12b-uncensored")

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

KG_SYSTEM_PROMPT = """你是一名资深知识图谱工程师。任务：从文档中提取实体及它们之间的【多元关系】，构建一张【网状】知识图谱（而非以一个中心实体为枢纽的星型图）。

【最重要的结构要求 —— 必须遵守】
- 【连通性 · 最高优先级】整图必须是"单一连通分量"——所有节点都能通过关系链互相到达；严禁出现孤立节点（没有任何边相连的节点），严禁出现两个或多个互不相连的子图。输出前必须逐个自检：每个节点是否都已接入主图。若某实体与其他实体缺乏明显的直接关系，要么主动挖掘间接关联（共同所属、同期事件、同类对比、地缘/时序相近、共同影响等）把它连入主图，要么干脆不提取该实体——绝不允许任何节点游离在主图之外。
- 目标是"网"而不是"星"：实体之间要布满横向的直接关系，禁止把大多数实体都挂到同一个中心实体（如文档标题、主题词、机构名）下面。
- 任何单个节点的连接数，不得超过总关系数的 40%。
- 每个实体至少要与 2 个不同实体相连；整图平均每节点关系数 ≥ 2。
- 重点挖掘"非中心"的横向关系：同类实体之间、跨类别实体之间的关联。

【按维度挖掘关系】请对实体两两思考，是否在以下任一维度存在关系，能挖尽挖：
- 归属/组成：属于、包含、是…的一部分、隶属
- 位置：位于、发生在、坐落
- 参与/协作：参与、合作、共同创立、创建、任职于
- 因果/影响：导致、促进、影响、推动
- 时序：早于、之后、演变为、前身是
- 相似/对比：类似、竞争、对立、并列
- 产出/基于：开发、基于、产出、主讲、覆盖

【输出格式】第一个字符必须是 {，直接输出纯 JSON，不要任何 markdown 代码块标记，不要任何解释、思考、分析或前后文：
{
  "nodes": [{"id": "n1", "name": "实体名", "category": "人物", "desc": "≤20字描述"}],
  "links": [{"source": "n1", "target": "n2", "label": "简短中文关系"}]
}

【规则】
- 提取 12-30 个最重要的实体，宁缺毋滥。
- category 必须是：人物、组织、概念、事件、地点、技术、作品、领域、其他。
- 节点 id 唯一连续（n1,n2,…）；link 的 source/target 必须引用已存在的 id。
- label 用简短中文动词/介词且精准（如"创立""位于""合作""基于"），禁止用"相关""有关"这种模糊词。
- desc ≤ 20 字中文。

【示例】文档："张三与李四共同创立了AI实验室（隶属A大学）。实验室开发了系统X，基于技术Z。李四主讲课程Y，课程覆盖技术Z。"
正确输出（注意横向关系：n1与n2直接"合作"，n5与n7通过n6关联，而非全部连到A大学）：
{"nodes":[{"id":"n1","name":"张三","category":"人物"},{"id":"n2","name":"李四","category":"人物"},{"id":"n3","name":"AI实验室","category":"组织"},{"id":"n4","name":"A大学","category":"组织"},{"id":"n5","name":"系统X","category":"作品"},{"id":"n6","name":"技术Z","category":"技术"},{"id":"n7","name":"课程Y","category":"作品"}],"links":[{"source":"n1","target":"n3","label":"共同创立"},{"source":"n2","target":"n3","label":"共同创立"},{"source":"n1","target":"n2","label":"合作"},{"source":"n3","target":"n4","label":"隶属"},{"source":"n3","target":"n5","label":"开发"},{"source":"n5","target":"n6","label":"基于"},{"source":"n2","target":"n7","label":"主讲"},{"source":"n7","target":"n6","label":"覆盖"}]}"""


class ExtractRequest(BaseModel):
    content: str


class UploadResponse(BaseModel):
    filename: str
    markdown: str
    char_count: int


# ---------------------------------------------------------------------------
# 分块提取配置
# 原方案对 >12000 字的文档只取「头 8000 + 尾 2000」，中间实体丢失。
# 现改为分块提取 + 合并去重：每块独立抽取图谱，再按实体名归并、重映射关系。
# ---------------------------------------------------------------------------
SINGLE_CALL_MAX = 3000   # 字符数 <= 该值时单次调用，不分块
CHUNK_SIZE = 2000        # 每块字符数（中文 token 密集，缩小以容纳更丰富的反星型 prompt，并避免输入被截断）
CHUNK_OVERLAP = 200      # 块间重叠，避免实体被切断在边界
MAX_CHUNKS = 6           # 最多块数，超长文档只取前若干块，防止耗时过久


def extract_pdf_text(file_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name
    try:
        text_parts = []
        with pdfplumber.open(tmp_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(f"## 第 {i+1} 页\n\n{page_text.strip()}")
        return "\n\n".join(text_parts) if text_parts else "（未能提取到文字内容）"
    finally:
        os.unlink(tmp_path)


def extract_docx_text(file_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name
    try:
        doc = Document(tmp_path)
        text_parts = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            if para.style.name.startswith("Heading"):
                level = para.style.name.split()[-1]
                prefix = "#" * int(level) if level.isdigit() else "##"
                text_parts.append(f"{prefix} {text}")
            else:
                text_parts.append(text)
        return "\n\n".join(text_parts) if text_parts else "（未能提取到文字内容）"
    finally:
        os.unlink(tmp_path)


@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[-1].lower()
    if ext not in (".pdf", ".docx", ".doc"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 和 Word (.docx) 文件")

    try:
        file_bytes = await file.read()
        if ext == ".pdf":
            md_content = extract_pdf_text(file_bytes)
        else:
            md_content = extract_docx_text(file_bytes)

        if not md_content.strip():
            raise HTTPException(status_code=400, detail="未能从文件中提取到文字内容")

        base_name = os.path.splitext(file.filename)[0]
        md_path = os.path.join(UPLOAD_DIR, f"{base_name}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        return UploadResponse(
            filename=file.filename,
            markdown=md_content,
            char_count=len(md_content),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文档处理失败: {str(e)}")


# ---------------------------------------------------------------------------
# 知识图谱提取（分块 + 合并）
# ---------------------------------------------------------------------------
def _strip_code_fences(s: str) -> str:
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    return s.strip()


def _parse_graph_json(text: str):
    """从模型输出中容错提取知识图谱 JSON。
    模型是 reasoning 型，可能先吐一大段思考链再输出 JSON，或把 JSON 包在代码块里。
    这里先尝试整体解析，失败则用括号匹配抓出第一个完整的 {...} 对象。"""
    text = text.strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start:i + 1])
                    if isinstance(obj, dict):
                        return obj
                except json.JSONDecodeError:
                    # 这段没解析成功，继续往后找下一个平衡的 }
                    pass
    return None


def _chunk_text(text: str) -> list:
    """把长文档切成带重叠的块；短文档直接整段返回。"""
    if len(text) <= SINGLE_CALL_MAX:
        return [text]
    chunks = []
    start = 0
    while start < len(text) and len(chunks) < MAX_CHUNKS:
        end = min(start + CHUNK_SIZE, len(text))
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - CHUNK_OVERLAP
    return chunks


def _validate_graph_dict(data: dict) -> None:
    if "nodes" not in data or "links" not in data:
        raise ValueError("缺少 nodes 或 links 字段")
    if not isinstance(data["nodes"], list) or not isinstance(data["links"], list):
        raise ValueError("nodes/links 必须是数组")


async def _extract_graph_from_text(client: httpx.AsyncClient, content: str, temperature: float = 0.6) -> dict:
    """对单段文本调用 LLM 抽取图谱，返回校验过的 {nodes, links}。"""
    user_prompt = f"请从以下文档中提取知识图谱：\n\n{content}"
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": KG_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        # 采样参数按模型作者(HauhauCS)为该 build 专门调校的推荐值；
        # 其中 repeat_penalty 是防止 reasoning 模型陷入 "Wait..Wait.." 死循环的关键
        "top_k": 64,
        "top_p": 0.9,
        "min_p": 0.05,
        "repeat_penalty": 1.1,
        # reasoning 模型的"思考链"和最终 JSON 共享 max_tokens 预算：
        # 思考链常吃掉 4000-8000 tokens，6144 不够装完整 JSON → finish_reason=length 被砍。
        # 这里给到 12288，思考(≤8000) + 完整JSON(≤3000) 都装得下；ctx 16384 下可用 ~14000，充足。
        "max_tokens": 12288,
    }
    response = await client.post(LLM_API_URL, json=payload, timeout=240.0)
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"模型推理失败: {response.text}")

    choice = response.json()["choices"][0]
    msg = choice.get("message", {}) or {}
    # Gemma4 Balanced 是"先推理再作答"的模型：答案可能在 content，也可能在 reasoning_content
    raw_content = (msg.get("content") or "").strip() or (msg.get("reasoning_content") or "").strip()
    finish_reason = choice.get("finish_reason")
    print(
        f"[llm] finish_reason={finish_reason} | 输出 {len(raw_content)} 字符 | 末尾200字: {raw_content[-200:]!r}",
        flush=True,
    )
    content_str = _strip_code_fences(raw_content)

    if not content_str:
        raise HTTPException(
            status_code=500,
            detail=f"模型返回空内容（finish_reason={finish_reason}），可能上下文不足或输出被截断。",
        )

    data = _parse_graph_json(content_str)
    if data is None:
        print(f"[llm] ❌ 无法从输出中提取 JSON（详情见上一行 [llm] 日志）", flush=True)
        raise HTTPException(
            status_code=500,
            detail=(
                f"无法从模型输出中提取 JSON（finish_reason={finish_reason}，输出长度 {len(content_str)} 字符）。"
                f"{'finish_reason=length 表示输出被 max_tokens 截断、JSON 没写完。' if finish_reason == 'length' else ''}"
                f"\n输出末尾:\n{content_str[-400:]}"
            ),
        )
    _validate_graph_dict(data)
    print(f"[llm] ✓ 解析成功: {len(data.get('nodes', []))} 节点 / {len(data.get('links', []))} 关系", flush=True)
    return data


def _merge_graphs(graphs: list) -> dict:
    """按实体名归并多块图谱，重映射关系，去重。"""
    name_to_id = {}
    merged_nodes = []

    def norm(name):
        return (name or "").strip()

    for g in graphs:
        for n in g.get("nodes", []):
            key = norm(n.get("name"))
            if not key or key in name_to_id:
                continue
            nid = f"n{len(name_to_id) + 1}"
            name_to_id[key] = nid
            merged_nodes.append({
                "id": nid,
                "name": n.get("name", key),
                "category": n.get("category") or "其他",
                "desc": n.get("desc", ""),
            })

    merged_links = []
    seen_links = set()
    for g in graphs:
        # 块内 id -> 规范名，用于把 link 的 source/target 还原成实体名
        local_id_to_name = {n.get("id"): norm(n.get("name")) for n in g.get("nodes", [])}
        for l in g.get("links", []):
            s, t = l.get("source"), l.get("target")
            s_name = local_id_to_name.get(s, norm(s) if isinstance(s, str) else "")
            t_name = local_id_to_name.get(t, norm(t) if isinstance(t, str) else "")
            s_id = name_to_id.get(s_name)
            t_id = name_to_id.get(t_name)
            # 丢弃指向未知实体或自环的关系
            if not s_id or not t_id or s_id == t_id:
                continue
            label = (l.get("label") or "").strip()
            key = (s_id, t_id, label)
            if key in seen_links:
                continue
            seen_links.add(key)
            merged_links.append({"source": s_id, "target": t_id, "label": label})

    return {"nodes": merged_nodes, "links": merged_links}


def _largest_component(data: dict) -> dict:
    """只保留最大连通分量，丢弃离群点与互不相连的小子图，保证整图连通。"""
    nodes = data.get("nodes", [])
    links = data.get("links", [])
    if not nodes:
        return data
    adj = {n["id"]: set() for n in nodes}
    for l in links:
        s, t = l.get("source"), l.get("target")
        if s in adj and t in adj:
            adj[s].add(t)
            adj[t].add(s)
    seen = set()
    components = []
    for n in nodes:
        nid = n["id"]
        if nid in seen:
            continue
        stack = [nid]
        comp = set()
        while stack:
            cur = stack.pop()
            if cur in comp:
                continue
            comp.add(cur)
            seen.add(cur)
            stack.extend(adj[cur] - comp)
        components.append(comp)
    if len(components) <= 1:
        return data
    largest = max(components, key=len)
    if len(largest) == len(nodes):
        return data
    keep_nodes = [n for n in nodes if n["id"] in largest]
    keep_links = [l for l in links if l.get("source") in largest and l.get("target") in largest]
    print(
        f"[extract-graph] 连通性过滤: 丢弃 {len(nodes) - len(keep_nodes)} 个离群节点，"
        f"保留最大连通分量 {len(largest)}/{len(nodes)}",
        flush=True,
    )
    return {"nodes": keep_nodes, "links": keep_links}


@app.post("/api/extract-graph")
async def extract_knowledge_graph(req: ExtractRequest):
    content = req.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="内容不能为空")

    chunks = _chunk_text(content)

    try:
        async with httpx.AsyncClient() as client:
            partial = []
            for idx, chunk in enumerate(chunks):
                print(f"[extract-graph] 第 {idx + 1}/{len(chunks)} 块（{len(chunk)} 字符）开始提取...", flush=True)
                # reasoning 模型偶发陷入思考死循环，失败时提高随机性重试一次跳出循环
                result = None
                for attempt, temp in enumerate([0.6, 0.8]):
                    try:
                        result = await _extract_graph_from_text(client, chunk, temperature=temp)
                        break
                    except HTTPException as e:
                        if attempt == 0:
                            print(f"[extract-graph] 第 {idx + 1} 块失败，提高 temperature 重试一次...", flush=True)
                            continue
                        raise
                partial.append(result)

        graph_data = _merge_graphs(partial) if len(partial) > 1 else partial[0]
        graph_data = _largest_component(graph_data)

        # 超长文档被 MAX_CHUNKS 截断时给出提示，便于排查漏抽
        covered = sum(len(c) for c in chunks)
        if len(content) > covered:
            print(
                f"[extract-graph] 文档 {len(content)} 字，仅覆盖前 {covered} 字 "
                f"(MAX_CHUNKS={MAX_CHUNKS})，建议拆分文档后再提取"
            )
        if len(partial) > 1:
            print(
                f"[extract-graph] 分 {len(partial)} 块提取，合并后 "
                f"{len(graph_data['nodes'])} 节点 / {len(graph_data['links'])} 关系"
            )

        # 结构质量统计：判断是否星型退化（最大节点度数占比 > 40% 视为偏星型）
        n_nodes = len(graph_data["nodes"])
        n_links = len(graph_data["links"])
        deg = {}
        for l in graph_data["links"]:
            deg[l["source"]] = deg.get(l["source"], 0) + 1
            deg[l["target"]] = deg.get(l["target"], 0) + 1
        avg_deg = (2 * n_links / n_nodes) if n_nodes else 0
        max_deg = max(deg.values()) if deg else 0
        isolated = n_nodes - len(deg)
        max_share = (max_deg / (2 * n_links)) if n_links else 0
        verdict = "⚠ 偏星型" if max_share > 0.4 or avg_deg < 2 else "✓ 网状"
        print(
            f"[extract-graph] 结构质量: 平均度数 {avg_deg:.1f} | 最大度数 {max_deg}"
            f"（占 {max_share*100:.0f}%）| 孤立节点 {isolated} | {verdict}"
        )

        return JSONResponse(content=graph_data)

    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=500, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"图谱提取失败: {str(e)}")


@app.get("/api/health")
async def health():
    return {"status": "ok", "model": MODEL_NAME}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=3000, reload=True)
