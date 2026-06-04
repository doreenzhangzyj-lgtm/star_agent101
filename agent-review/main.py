#!/usr/bin/env python3
"""
MBTI 评委 自动化大逃杀系统 — Streamlit Web 应用

安装依赖:
    pip install streamlit python-dotenv opencv-python openai>=1.0

运行方式:
    streamlit run main.py

要使用请确保配置 doubaomiyao.env，包括 OPENAI_API_KEY
"""

import os
import sys
import base64
import json
from pathlib import Path
import re
import threading
import traceback

import streamlit as st
import requests  # <<<<<<<<<<<<< 新增

def clean_json_str(raw_str):
    if not raw_str:
        return "{}"
    raw_str = raw_str.strip()
    if raw_str.startswith("```json"):
        raw_str = raw_str[7:]
    elif raw_str.startswith("```"):
        raw_str = raw_str[3:]
    if raw_str.endswith("```"):
        raw_str = raw_str[:-3]
    return raw_str.strip()

try:
    import cv2
except ImportError:
    st.error("缺少依赖：请在命令行运行 `pip install opencv-python`")
    st.stop()

try:
    from dotenv import load_dotenv
except ImportError:
    st.error("缺少依赖：请在命令行运行 `pip install python-dotenv`")
    st.stop()

# 配置环境变量
load_dotenv('doubaomiyao.env')

DOUBAO_MODEL_ID = "doubao-seed-2-0-pro-260215"
ARK_API_KEY = os.getenv("OPENAI_API_KEY")

if not ARK_API_KEY:
    st.error("环境变量 OPENAI_API_KEY 未设置。请在 doubaomiyao.env 文件中配置。")
    st.stop()

# 用requests来请求火山方舟chat/completions接口
ARK_CHAT_URL = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"

# 1. 修改页面文案与标题
st.set_page_config(page_title="Agent 大星探 · 寻找下一个帕梅拉", layout="wide")

# ================== 设置 ==================
MBTI_JUDGES = [
    {"mbti": "INTJ", "name": "Neal",   "desc": "战略家",  "emoji": "👓"},
    {"mbti": "ISTP", "name": "Steve",  "desc": "鉴赏家",  "emoji": "🛠️"},
    {"mbti": "ENFJ", "name": "Alice",  "desc": "主人公",  "emoji": "🌟"},
]
JUDGE_TEAM_SIZE = 3

EVAL_CRITERIA = (
    "【留资（Lead Generation）直播间】，高质量内容的共同标准是："
    "1) 高频且自然的观众互动；"
    "2) 画面表现力生动有趣；"
    "3) 有强有力的 CTA（Call To Action）吸引用户留资。"
    "请结合你的 MBTI 视角，重点考察这些维度。"
)

# ================== 工具函数 ==================

@st.cache_data
def extract_mid_keyframe_from_video(video_path):
    """
    从视频中截取中间(50%)的1帧，返回 base64 编码的图片（data:image/jpeg;base64,...）
    如失败返回None
    """
    try:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return None
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if frame_count <= 0:
            cap.release()
            return None
        idx = int(frame_count * 0.5)
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        cap.release()
        if not ret or frame is None:
            return None
        _, buf = cv2.imencode('.jpg', frame)
        b64_bytes = base64.b64encode(buf.tobytes()).decode('utf-8')
        return f"data:image/jpeg;base64,{b64_bytes}"
    except Exception as e:
        return None

@st.cache_data
def get_root_case_dir():
    base = Path(__file__).parent / "Case demo"
    if not base.exists():
        st.error(f"案例主目录不存在：{base}")
        st.stop()
    return base

@st.cache_data
def list_case_folders(case_root):
    # 只选 1,2,3,4 号文件夹
    return sorted([d for d in case_root.iterdir() if d.is_dir() and d.name in {'1', '2', '3', '4'}],
                  key=lambda p: int(p.name))

@st.cache_data
def get_case_as_candidate(case_dir):
    asr = ""
    asr_files = list(case_dir.glob("*.txt"))
    if asr_files:
        try:
            with open(asr_files[0], "r", encoding="utf-8") as fr:
                asr = fr.read().strip()
        except Exception as e:
            st.warning(f"读取 {case_dir} 文本异常: {e}")
    mp4s = list(sorted(case_dir.glob("*.mp4"), key=lambda p: p.name))
    clips = []
    for p in mp4s:
        clips.append({
            "id": p.stem,
            "path": str(p),
            "asr": asr
        })
    return {
        "id": int(case_dir.name),
        "name": case_dir.name,
        "path": str(case_dir),
        "asr": asr,
        "clips": clips
    }

# ====== ！！删除 build_text_input / gen_case_text_content，全面精简传参格式 ======

def run_doubao_api(prompt, case_A, case_B, streaming=False):
    """使用 requests 调用火山方舟 Doubao Seed 标准chat/completions接口"""
    if not case_A.get("asr", "").strip() or not case_B.get("asr", "").strip():
        st.error("案例A/B 的 ASR 文本内容为空，请检查原始输入数据。")
        raise ValueError("ASR文本为空")

    headers = {
        "Authorization": f"Bearer {ARK_API_KEY}",
        "Content-Type": "application/json"
    }
    # 合并为纯文本
    full_text = f"{prompt}\n\n【案例A文本】:\n{case_A.get('asr', '')}\n\n【案例B文本】:\n{case_B.get('asr', '')}"
    payload = {
        "model": DOUBAO_MODEL_ID,
        "messages": [
            {"role": "user", "content": full_text}
        ],
        "temperature": 0.1
    }
    resp = requests.post(ARK_CHAT_URL, headers=headers, json=payload, timeout=120)
    print(f"【硬核Debug】豆包 HTTP状态码: {resp.status_code}")
    print(f"【硬核Debug】豆包 HTTP返回体: {resp.text}")
    resp.raise_for_status()
    return resp.json()

def parse_judge_json(text, caseA, caseB):
    print("【豆包原始返回内容】==== start ====")
    print(text)
    print("【豆包原始返回内容】==== end =====")
    cleaned = clean_json_str(text)
    try:
        obj = json.loads(cleaned)
        # winner模糊提取
        winner_val = None
        for key in ['winner', 'Winner', '胜者', '获胜者', 'winner_case', 'choice']:
            if key in obj:
                winner_val = str(obj[key]).strip()
                break
        # 容忍 A/B
        if winner_val is not None:
            if winner_val in ["A", "案例A"]:
                winner_val = caseA["name"]
            elif winner_val in ["B", "案例B"]:
                winner_val = caseB["name"]
            elif winner_val in [caseA["name"], caseB["name"]]:
                pass  # 直接使用编号
        # reason模糊提取
        reason_val = "未成功提取理由"
        for key in ['reason', 'Reason', '理由', '原因', '点评', 'comment']:
            if key in obj:
                val = obj[key]
                if isinstance(val, (str, int)):
                    reason_val = str(val).strip()
                else:
                    try:
                        reason_val = json.dumps(val, ensure_ascii=False)
                    except Exception:
                        reason_val = str(val)
                break
        if not winner_val:
            reason_val += "（winner字段未能识别）"
        return {"winner": winner_val, "reason": reason_val}
    except Exception as e:
        print(f"JSON解析失败，内容如下：\n{text}")
        error_msg = f"JSON解析失败: {e}\n内容: {text}"
        st.error(error_msg)
        return {"winner": None, "reason": error_msg}

def judge_prompt_text(judge, case_A, case_B):
    a_asr = (case_A['asr'] or "").strip()
    b_asr = (case_B['asr'] or "").strip()
    if not a_asr or not b_asr:
        st.warning("A/B案例ASR文本输入有空值")
    strict_json_require = (
        "\n\n"
        "【重要：你必须严格遵循以下 JSON 格式输出，绝对不能更改键名，不能使用中文键名！】\n"
        "你的输出必须有且仅有以下严格格式：\n"
        "{\n"
        '  "winner": "填 A 或 B",\n'
        '  "reason": "填1到2句话的精炼理由"\n'
        "}\n"
        "绝对不能包含任何其他键名！\n"
    )
    return (
        f"你是大逃杀MBTI评委 {judge['emoji']}{judge['name']} ({judge['mbti']} {judge['desc']})。\n"
        f"{EVAL_CRITERIA}\n"
        f"请你基于上述文本，综合判断哪个案例更优秀，并输出如下严格JSON，理由要精炼，仅1-2句：\n"
        f'{{"winner": "A 或 B", "reason": "简洁理由"}}\n'
        f"winner 只能填 A 或 B，不得输出多余文字或代码块。只输出JSON结果。"
        f"{strict_json_require}"
    )

def host_summary_prompt(caseA, caseB, judge_jsons):
    comments = []
    for idx, judge in enumerate(MBTI_JUDGES):
        j = judge_jsons[idx]
        if j is not None and j.get("winner") and j.get("reason"):
            vote = "案例A" if j.get("winner") == caseA["name"] else "案例B"
            comments.append(f"{judge['emoji']}{judge['name']}：投给{vote}，理由：{j.get('reason','')}")
    full_comment = "\n".join(comments)
    prompt = (
        f"假设你是一档大逃杀综艺节目的主持人。现在有3位MBTI评委投票和点评如下：\n"
        f"{full_comment}\n"
        f"请你从他们的表态和理由中，总结出本场案例A（编号{caseA['name']}）VS案例B（编号{caseB['name']}）的【核心争议点】，50字以内，风格口语、简明。不要输出标题或冗余前缀，只输出总结内容。"
    )
    return prompt

def run_host_summary_agent(caseA, caseB, judge_jsons):
    prompt = host_summary_prompt(caseA, caseB, judge_jsons)
    headers = {
        "Authorization": f"Bearer {ARK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": DOUBAO_MODEL_ID,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.5
    }
    try:
        resp = requests.post(ARK_CHAT_URL, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json().get("choices", [{}])[0].get("message", {}).get("content", "总结提取失败")
    except Exception as e:
        return f"总结调用报错: {e}"

def get_candidate_by_id(all_candidates, id):
    for c in all_candidates:
        if str(c['id']) == str(id):
            return c
    return None

@st.cache_data
def generate_en_summary(asr_text):
    """
    使用大模型生成一句精炼有吸引力的英文介绍 (Under 12 words)
    """
    if not asr_text.strip():
        return ""
    prompt = (
        "请将以下直播 ASR 文本总结为一句简短、有吸引力的英文介绍（Under 12 words）。"
        "只输出这句英文，不要任何多余字符。\n\n"
        f"{asr_text}"
    )
    headers = {
        "Authorization": f"Bearer {ARK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": DOUBAO_MODEL_ID,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.4
    }
    try:
        resp = requests.post(ARK_CHAT_URL, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        txt = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        # 剥离封装的 markdown、引号等杂质
        txt = re.sub(r"^\"|\"$", "", txt.strip())
        txt = re.sub(r"^'+|'+$", "", txt.strip())
        return txt
    except Exception as e:
        # 失败时 fallback 提示
        return "An exciting live broadcast!"

def display_case_block_card(case, label="A"):
    st.subheader(f"🥊 案例 {case['name']}", anchor=False)
    mp4_path = None
    if case.get("clips") and len(case["clips"]) > 0:
        first_clip = case["clips"][0]
        mp4_path = first_clip["path"]
    keyframe_img = None
    if mp4_path and Path(mp4_path).exists():
        keyframe_img = extract_mid_keyframe_from_video(mp4_path)
    # ------- 封面呈现使用稳定的高度和 object-fit: cover -------
    if keyframe_img and keyframe_img.startswith("data:image"):
        st.markdown(
            f'<img src="{keyframe_img}" style="width: 100%; height: 350px; object-fit: cover; border-radius: 12px; margin-bottom: 15px; border: 1px solid #25f4ee;">',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<div style="width: 100%; height: 350px; background: #1a1c23; border-radius: 12px; margin-bottom: 15px; display: flex; align-items: center; justify-content: center; border: 1px solid #333; color: #666;">暂无封面</div>',
            unsafe_allow_html=True
        )
    # ------- 大模型智能英文摘要 ---------
    summary_en = generate_en_summary(case.get("asr", ""))
    st.markdown(f'<div style="font-size: 1.05rem; color: #e0e0e0; margin-bottom: 10px; font-style: italic;">✨ "{summary_en}"</div>', unsafe_allow_html=True)

    with st.expander("🎬 查看完整视频与长文本", expanded=False):
        if case.get("clips"):
            for idx, clip in enumerate(case["clips"]):
                pth = clip.get("path")
                if Path(pth).exists():
                    st.markdown(f"<span style='font-size:1.1rem;'>🎬 切片{clip['id']}</span>", unsafe_allow_html=True)
                    st.video(pth)
                else:
                    st.caption(f"本案例下缺少切片{clip['id']}视频")
        else:
            st.caption("本案例下没有视频切片")
        st.markdown("---")
        st.markdown("**完整ASR文本**：")
        st.markdown(case.get("asr", "") if case.get("asr") else "无")

def render_result_dashboard(win_label, winner_case, summary, judge_jsons, caseA, caseB, match_title=None, show_balloons=True):
    if show_balloons:
        st.balloons()
    if match_title:
        st.markdown(f"<h3 style='margin-bottom:0.3em;color:#25f4ee;text-shadow:0 0 11px #fe2c55,0 0 20px #25f4ee76'>{match_title}</h3>", unsafe_allow_html=True)
    st.success(
        f"🎉 本场胜者: 案例{win_label} (编号{winner_case['name']})",
        icon="🏆"
    )
    st.markdown(
        f"<span style='font-size:2.1rem;font-weight:700;display:none;'>本场胜者: 案例{win_label} (编号{winner_case['name']})</span>",
        unsafe_allow_html=True
    )
    st.markdown(f"<span style='font-size:1.05rem;'>{summary}</span>", unsafe_allow_html=True)
    st.markdown("#### 评委点评墙")
    cols = st.columns(JUDGE_TEAM_SIZE)
    for idx, judge in enumerate(MBTI_JUDGES):
        c = cols[idx]
        with c:
            st.markdown(
                f"""
                <div style='
                    border-radius:12px;
                    background:#15171e;
                    border:1px solid #25f4ee;
                    box-shadow: 0 0 8px rgba(37,244,238,0.2);
                    padding:12px 5px;
                    height:120px;
                    text-align:center;
                    display:flex;
                    flex-direction:column;
                    justify-content:center;
                '>
                    <div style='font-size:2.1rem'>{judge['emoji']}</div>
                    <div style='font-weight:700;color:#fff;font-size:1.12rem;'>{judge['name']}</div>
                    <div style='font-size:0.98rem;color:#c7cbe5;'>{judge['mbti']}<span style='margin-left:4px'>{judge['desc']}</span></div>
                """,
                unsafe_allow_html=True
            )
            j = judge_jsons[idx]
            if j is not None and j.get("winner") is not None and j.get("reason") is not None:
                case_name = j["winner"]
                win_side = "A" if case_name == caseA["name"] else "B"
                badge_color = "#25f4ee" if win_side == "A" else "#fe2c55"
                st.markdown(
                    f"<div style='font-size:1.08rem; margin-top:3px;'>"
                    f"<span style='background:{badge_color};color:#fff;padding:2px 10px;border-radius:7px;box-shadow:0 0 4px {badge_color}88;'>"
                    f"投票：{case_name if case_name else '投票失败'}"
                    f"</span></div>", unsafe_allow_html=True
                )
                st.markdown(
                    f"<div style='font-size:0.97rem;margin-top:6px;color:#e0e0e0;text-shadow:0 0 4px #25f4ee22'>{j['reason']}</div></div>",
                    unsafe_allow_html=True
                )
            else:
                st.markdown("<span style='color:#aaa'>投票数据缺失</span></div>", unsafe_allow_html=True)

def run_match(caseA, caseB, match_title=None):
    with st.spinner("⏳ 3 位评委文本比对中（预计 5-10 秒）..."):
        judge_jsons = [None] * JUDGE_TEAM_SIZE
        thread_errors = [None] * JUDGE_TEAM_SIZE

        def get_vote(idx, judge):
            try:
                prompt = judge_prompt_text(judge, caseA, caseB)
                raw = run_doubao_api(prompt, caseA, caseB, streaming=False)
                # 直接提取标准OpenAI格式中的文本
                txt = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
                print("【终于拿到的文本】==== start ====")
                print(txt)
                print("【终于拿到的文本】==== end =====")
                parsed = parse_judge_json(txt, caseA, caseB)
                judge_jsons[idx] = parsed
            except Exception as e:
                error_reason = f"评委调用失败: {e}"
                judge_jsons[idx] = {"winner": None, "reason": error_reason}

        threads = []
        for idx, judge in enumerate(MBTI_JUDGES):
            t = threading.Thread(target=get_vote, args=(idx, judge))
            t.start()
            threads.append(t)
        for t in threads:
            t.join(timeout=20)

        for idx, judge in enumerate(MBTI_JUDGES):
            j = judge_jsons[idx]
            if isinstance(j, dict) and j.get("winner") is None and j.get("reason") is not None:
                st.error(f"评委 {judge['name']} 投票/解析失败：{j.get('reason')}")

        win_count = {caseA["name"]: 0, caseB["name"]: 0}
        for j in judge_jsons:
            winner_key = j.get("winner") if isinstance(j, dict) else None
            if winner_key in win_count:
                win_count[winner_key] += 1

        if win_count[caseA["name"]] > win_count[caseB["name"]]:
            winner_case = caseA
            loser_case = caseB
            win_label = "A"
            lose_label = "B"
        elif win_count[caseA["name"]] < win_count[caseB["name"]]:
            winner_case = caseB
            loser_case = caseA
            win_label = "B"
            lose_label = "A"
        else:
            winner_case = caseA if int(caseA['name']) < int(caseB['name']) else caseB
            loser_case = caseB if winner_case == caseA else caseA
            win_label = "A" if winner_case == caseA else "B"
            lose_label = "B" if win_label == "A" else "A"

        summary = run_host_summary_agent(caseA, caseB, judge_jsons)

        winning_judges = []
        for idx, judge in enumerate(MBTI_JUDGES):
            j = judge_jsons[idx]
            if isinstance(j, dict) and j.get("winner") == winner_case["name"]:
                winning_judges.append({"judge": judge, "reason": j.get("reason")})
        winner_case['winning_reasons'] = winning_judges
        winner_case['host_summary'] = summary

    render_result_dashboard(win_label, winner_case, summary, judge_jsons, caseA, caseB, match_title=match_title)
    return {
        "winner": winner_case,
        "loser": loser_case,
        "win_label": win_label,
        "lose_label": lose_label,
        "votes": (win_count[caseA["name"]], win_count[caseB["name"]]),
        "judges": judge_jsons,
        "summary": summary,
        "caseA": caseA,
        "caseB": caseB,
    }

def show_top3_results(top1, top2, top3):
    st.markdown("<hr>", unsafe_allow_html=True)
    # 爆改排行榜Title
    st.markdown("""<h1 style='text-align:center; background: -webkit-linear-gradient(45deg, #25f4ee, #fe2c55); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 3.5rem; font-style: italic; font-weight: 900; text-shadow: 0px 4px 15px rgba(254,44,85,0.3); margin-bottom: 30px;'>🌟 你就是下一颗星 🌟</h1>""", unsafe_allow_html=True)
    rows = st.columns([1,1,1])
    info = [
        ("冠军", "🥇", top1),
        ("亚军", "🥈", top2),
        ("季军", "🥉", top3),
    ]
    neons = [
        ("#25f4ee", "#fe2c55"),  # neon blue-pink for champion
        ("#a6ffcb", "#12d8fa"),  # teal-cyan for 2nd
        ("#ff9966", "#ff5e62"),  # orange-pink for 3rd
    ]
    for idx, (rank_name, emoji, item) in enumerate(info):
        border_clr1, border_clr2 = neons[idx]
        with rows[idx]:
            st.markdown(
                f"""
                <div style='
                    background:#101218;
                    border: 2px solid {border_clr2};
                    box-shadow: 0 0 15px {border_clr2}99,0 0 25px {border_clr1}88;
                    border-radius:18px;
                    padding:2em 1em;
                    margin-bottom:8px;
                    text-align:center;
                    color:#fff;
                '>
                    <div style='font-size:2.6rem;text-shadow:0 0 10px {border_clr2}dd'>{emoji} {rank_name}</div>
                    <div style='font-weight:700;font-size:2.4rem;color:#fff;text-shadow:0 0 11px {border_clr1}9c;'>案例{item['name']}</div>
                </div>""", unsafe_allow_html=True)
            display_case_block_card(item, label=rank_name)

def export_showcase_data(top1, top2, top3):
    def get_case_info(case, rank_name):
        return {
            "rank": rank_name,
            "name": case.get("name"),
            "id": case.get("id"),
            "path": case.get("path"),
            "asr": case.get("asr"),
            "clips": [clip["path"] for clip in (case.get("clips") or [])],
            "winning_reasons": case.get("winning_reasons", []),
            "host_summary": case.get("host_summary", ""),
        }
    export_data = [
        get_case_info(top1, "冠军"),
        get_case_info(top2, "亚军"),
        get_case_info(top3, "季军"),
    ]
    save_path = Path("final_showcase_result.json")
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    return save_path, export_data

def run_tournament(all_candidates):
    cands = {str(c['id']): c for c in all_candidates if str(c['id']) in {"1","2","3","4"}}
    if len(cands)!=4:
        st.error("只找到了以下案例，无法进行 4 强赛！请检查文件夹 1,2,3,4 是否都存在并数据完整。")
        st.write("已找到：", list(cands))
        st.stop()

    match_titles = [
        "【半决赛 A】案例1 vs 案例2",
        "【半决赛 B】案例3 vs 案例4",
        "【季军赛】落败者对决",
        "【总决赛】胜者对决"
    ]
    results = []

    with st.status(match_titles[0], expanded=True if len(results)==0 else False) as statusA:
        resA = run_match(cands["1"], cands["2"], match_title=match_titles[0])
        results.append(resA)
        statusA.update(label=f"半决赛A 完成, 胜者: 案例{resA['winner']['name']}", state="complete")

    with st.status(match_titles[1], expanded=True if len(results)==1 else False) as statusB:
        resB = run_match(cands["3"], cands["4"], match_title=match_titles[1])
        results.append(resB)
        statusB.update(label=f"半决赛B 完成, 胜者: 案例{resB['winner']['name']}", state="complete")

    with st.status(match_titles[2], expanded=True if len(results)==2 else False) as statusC:
        resC = run_match(resA['loser'], resB['loser'], match_title=match_titles[2])
        results.append(resC)
        statusC.update(label=f"季军赛完成, 胜者: 案例{resC['winner']['name']} (季军)", state="complete")

    with st.status(match_titles[3], expanded=True if len(results)==3 else False) as statusD:
        resD = run_match(resA["winner"], resB["winner"], match_title=match_titles[3])
        results.append(resD)
        statusD.update(label=f"总决赛完成, 冠军: 案例{resD['winner']['name']}", state="complete")

    top1 = resD['winner']
    top2 = resD['loser']
    top3 = resC['winner']

    show_top3_results(top1, top2, top3)

    save_path, export_data = export_showcase_data(top1, top2, top3)
    st.markdown("<hr>", unsafe_allow_html=True)
    st.success("✅ 数据已成功导出为 final_showcase_result.json，可供下一步使用")
    export_str = json.dumps(export_data, ensure_ascii=False, indent=2)
    st.download_button(
        label="📥 下载最终Showcase JSON",
        data=export_str,
        file_name="final_showcase_result.json",
        mime="application/json"
    )

def main_streamlit():
    # 2. 全局暗黑霓虹 CSS 注入
    st.markdown(
        """
        <style>
            /* 全局暗黑背景与亮色字体 */
            .stApp {
                background-color: #0b0c10 !important;
                color: #ffffff !important;
            }
            /* 强制 Markdown 区域变浅色 */
            .stMarkdown, p, span, div {
                color: #e0e0e0;
            }
            /* 按钮样式：电音粉 */
            .stButton>button {
                background: linear-gradient(45deg, #fe2c55, #ff0050) !important;
                color: white !important;
                border: none !important;
                font-weight: bold !important;
                box-shadow: 0 0 10px rgba(254, 44, 85, 0.5) !important;
                border-radius: 8px !important;
            }
            /* Expander 边框优化 */
            [data-testid="stExpander"] {
                background-color: #1a1c23 !important;
                border: 1px solid #25f4ee !important;
            }
        </style>
        """,
        unsafe_allow_html=True
    )

    # 1. 页面Title升级
    st.title("🌟 Agent 大星探 · 寻找下一个帕梅拉")

    case_root = get_root_case_dir()
    all_case_dirs = list_case_folders(case_root)

    if not all_case_dirs or len(all_case_dirs) < 4:
        st.error(f"未找到编号为 1,2,3,4 的案例文件夹，请检查 {case_root}。")
        st.stop()
    all_candidates = [get_case_as_candidate(case_dir) for case_dir in all_case_dirs]

    with st.expander("参赛案例数据预览", expanded=False):
        for c in all_candidates:
            st.markdown(f"编号 {c['name']}：包含 <b>{len(c['clips'])} 个视频切片</b>", unsafe_allow_html=True)

    run_flag_key = "run_tournament_triggered"
    if run_flag_key not in st.session_state:
        st.session_state[run_flag_key] = False

    if not st.session_state[run_flag_key]:
        if st.button("🏁 开始 4 强淘汰赛", type="primary"):
            st.session_state[run_flag_key] = True
            st.rerun()
    else:
        run_tournament(all_candidates)

if __name__ == "__main__":
    main_streamlit()
