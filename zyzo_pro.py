"""
zyzo_pro — نسخة تجريبية كاملة
تشغيل: python zyzo_pro.py
"""

import json, os, sqlite3, sys, webbrowser, threading, time
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path

# ── تحقق من المكتبات ──────────────────────────────────────────────────────────
try:
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse
    from pydantic import BaseModel
    from typing import List
except ImportError:
    print("📦 جاري تثبيت المكتبات...")
    os.system(f"{sys.executable} -m pip install fastapi uvicorn google-genai")
    print("✅ تم التثبيت! أعد تشغيل البرنامج.")
    sys.exit(0)

try:
    from google import genai
    from google.genai import types
except ImportError:
    os.system(f"{sys.executable} -m pip install google-genai")
    print("✅ تم تثبيت google-genai! أعد تشغيل البرنامج.")
    sys.exit(0)

# ── إعدادات ───────────────────────────────────────────────────────────────────
# ضع مفتاحك هنا مباشرة
GEMINI_API_KEY = "AIzaSyBMeqCgx0Xp7E9NOddArPnQ9e9RQLRzJWU"
GEMINI_MODEL   = "models/gemini-2.5-flash"
DB_PATH        = Path(__file__).parent / "zyzo.db"

# State مشترك
_STATE = {"client": None, "model": GEMINI_MODEL}

# ── قاعدة البيانات ────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            level TEXT NOT NULL,
            goal TEXT NOT NULL,
            interests TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            lesson_date TEXT NOT NULL,
            topic TEXT NOT NULL,
            title TEXT NOT NULL,
            body_text TEXT NOT NULL,
            level TEXT NOT NULL,
            word_count INTEGER DEFAULT 0,
            reading_time_minutes INTEGER DEFAULT 2,
            vocabulary TEXT DEFAULT '[]',
            questions TEXT DEFAULT '[]',
            is_completed INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS user_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            lesson_id INTEGER,
            score_percent REAL,
            answered_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS streak (
            user_id INTEGER PRIMARY KEY,
            current_streak INTEGER DEFAULT 0,
            longest_streak INTEGER DEFAULT 0,
            last_activity_date TEXT,
            total_days INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS skill_radar (
            user_id INTEGER PRIMARY KEY,
            vocabulary REAL DEFAULT 0,
            grammar REAL DEFAULT 0,
            reading REAL DEFAULT 0
        );
    """)
    conn.commit()
    conn.close()
    print("✅ Database ready")

# ── Gemini ────────────────────────────────────────────────────────────────────
LEVEL_DESC = {
    "beginner":           "very simple vocabulary, short sentences, A1-A2",
    "elementary":         "basic vocabulary, simple grammar, A2-B1",
    "intermediate":       "varied vocabulary, compound sentences, B1-B2",
    "upper_intermediate": "rich vocabulary, complex grammar, B2-C1",
    "advanced":           "sophisticated vocabulary, C1-C2",
}
GOAL_CTX = {
    "daily_conversation": "everyday spoken English situations",
    "business":           "professional workplace communication",
    "academic":           "academic reading and writing",
    "travel":             "travelling and tourism",
    "exam_prep":          "IELTS / TOEFL preparation",
}

def init_gemini(api_key: str):
    client = genai.Client(api_key=api_key)
    try:
        models = [m.name for m in client.models.list()]
        print(f"النماذج المتاحة: {models[:5]}...")
        chosen = GEMINI_MODEL
        for name in models:
            if "gemini-2.5-flash" in name and "preview" not in name and "audio" not in name:
                chosen = name
                break
        _STATE["client"] = client
        _STATE["model"]  = chosen
        print(f"✅ Gemini ready: {chosen}")
        return True
    except Exception as e:
        print(f"❌ Gemini error: {e}")
        return False

def generate_lesson_ai(level, goal, interests, recent_topics):
    if _STATE["client"] is None:
        raise RuntimeError("Gemini غير مهيأ — تأكد من صحة GEMINI_API_KEY في الكود")
    interests_s = ", ".join(interests) if interests else "general topics"
    avoid_s     = ", ".join(recent_topics) if recent_topics else "none"
    prompt = f"""You are an expert English teacher. Generate a daily English lesson.

STUDENT: level={level} ({LEVEL_DESC.get(level,'')}), goal={GOAL_CTX.get(goal,'')}, interests={interests_s}
AVOID THESE RECENT TOPICS: {avoid_s}

Respond ONLY with valid JSON (no markdown, no extra text):
{{
  "topic": "short topic tag",
  "title": "engaging article title",
  "body_text": "reading passage 200-350 words",
  "word_count": 280,
  "reading_time_minutes": 2,
  "vocabulary": [
    {{"word":"example","definition":"simple definition","example":"sentence using word","part_of_speech":"noun"}}
  ],
  "questions": [
    {{"question_type":"comprehension","question_text":"...","option_a":"...","option_b":"...","option_c":"...","option_d":"...","correct_answer":"A","explanation":"..."}}
  ]
}}

Rules:
- Exactly 4 vocabulary words
- Exactly 4 questions: 2 comprehension, 1 vocabulary, 1 grammar
- correct_answer must be exactly one of: A, B, C, D"""

    resp = _STATE["client"].models.generate_content(
        model=_STATE["model"],
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.85, max_output_tokens=3000)
    )
    text = resp.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(text)

# ── HTML ──────────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>zyzo_pro</title>
<style>
  :root {
    --primary: #6C63FF; --primary-dark: #5A52D5; --secondary: #FF6584;
    --bg: #0F0E17; --surface: #1A1929; --surface2: #242338;
    --text: #FFFFFE; --text-muted: #A7A9BE;
    --success: #2CB67D; --error: #FF6584; --radius: 16px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', sans-serif; min-height: 100vh; }
  .screen { display: none; min-height: 100vh; padding: 24px 20px; max-width: 480px; margin: auto; }
  .screen.active { display: flex; flex-direction: column; gap: 20px; }
  .logo { font-size: 32px; font-weight: 900; background: linear-gradient(135deg, var(--primary), var(--secondary)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; text-align: center; }
  .subtitle { color: var(--text-muted); text-align: center; font-size: 14px; }
  .card { background: var(--surface); border-radius: var(--radius); padding: 20px; border: 1px solid rgba(108,99,255,0.15); }
  label { font-size: 13px; color: var(--text-muted); margin-bottom: 6px; display: block; }
  input, select { width: 100%; background: var(--surface2); border: 1px solid rgba(108,99,255,0.2); border-radius: 10px; padding: 12px 14px; color: var(--text); font-size: 15px; outline: none; transition: border 0.2s; }
  input:focus, select:focus { border-color: var(--primary); }
  .tags { display: flex; flex-wrap: wrap; gap: 8px; }
  .tag { padding: 8px 14px; border-radius: 20px; background: var(--surface2); border: 1px solid rgba(108,99,255,0.2); cursor: pointer; font-size: 13px; transition: all 0.2s; user-select: none; }
  .tag.selected { background: var(--primary); border-color: var(--primary); color: white; }
  .btn { padding: 14px 24px; border-radius: 12px; border: none; font-size: 16px; font-weight: 600; cursor: pointer; transition: all 0.2s; width: 100%; }
  .btn-primary { background: var(--primary); color: white; }
  .btn-primary:hover { background: var(--primary-dark); transform: translateY(-1px); }
  .btn-outline { background: transparent; color: var(--primary); border: 2px solid var(--primary); }
  .loading { text-align: center; padding: 40px 20px; margin: auto; }
  .spinner { width: 48px; height: 48px; border: 4px solid var(--surface2); border-top-color: var(--primary); border-radius: 50%; animation: spin 0.8s linear infinite; margin: 0 auto 16px; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .loading-text { color: var(--text-muted); font-size: 14px; }
  .lesson-title { font-size: 20px; font-weight: 700; line-height: 1.4; }
  .lesson-meta { display: flex; gap: 12px; flex-wrap: wrap; }
  .badge { padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; }
  .badge-purple { background: rgba(108,99,255,0.2); color: var(--primary); }
  .badge-pink { background: rgba(255,101,132,0.2); color: var(--secondary); }
  .lesson-body { line-height: 1.8; font-size: 15px; color: #E0E0E0; white-space: pre-wrap; }
  .vocab-item { border-bottom: 1px solid rgba(255,255,255,0.06); padding: 14px 0; }
  .vocab-item:last-child { border-bottom: none; }
  .vocab-word { font-weight: 700; color: var(--primary); font-size: 16px; }
  .vocab-pos { font-size: 11px; color: var(--text-muted); margin-right: 6px; }
  .vocab-def { font-size: 14px; color: var(--text-muted); margin-top: 4px; }
  .vocab-ex { font-size: 13px; color: #7c7c9a; font-style: italic; margin-top: 4px; }
  .question-num { font-size: 12px; color: var(--text-muted); margin-bottom: 8px; }
  .question-text { font-size: 16px; font-weight: 600; margin-bottom: 14px; line-height: 1.5; }
  .options { display: flex; flex-direction: column; gap: 10px; }
  .option { padding: 12px 16px; border-radius: 10px; border: 1px solid rgba(108,99,255,0.2); cursor: pointer; transition: all 0.2s; display: flex; align-items: center; gap: 12px; }
  .option:hover { border-color: var(--primary); background: rgba(108,99,255,0.08); }
  .option.selected { border-color: var(--primary); background: rgba(108,99,255,0.15); }
  .option.correct { border-color: var(--success); background: rgba(44,182,125,0.15); }
  .option.wrong { border-color: var(--error); background: rgba(255,101,132,0.15); }
  .option-letter { width: 28px; height: 28px; border-radius: 50%; background: var(--surface2); display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; flex-shrink: 0; }
  .quiz-progress { height: 4px; background: var(--surface2); border-radius: 2px; overflow: hidden; }
  .quiz-progress-bar { height: 100%; background: var(--primary); transition: width 0.3s; }
  .score-circle { width: 120px; height: 120px; border-radius: 50%; border: 6px solid var(--primary); display: flex; flex-direction: column; align-items: center; justify-content: center; margin: 0 auto; }
  .score-num { font-size: 32px; font-weight: 900; color: var(--primary); }
  .score-label { font-size: 12px; color: var(--text-muted); }
  .stat-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
  .stat-row:last-child { border-bottom: none; }
  .stat-label { color: var(--text-muted); font-size: 14px; }
  .skill-bar-row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
  .skill-name { width: 80px; font-size: 13px; color: var(--text-muted); text-align: left; }
  .skill-bar-bg { flex: 1; height: 8px; background: var(--surface2); border-radius: 4px; overflow: hidden; }
  .skill-bar-fill { height: 100%; background: linear-gradient(90deg, var(--primary), var(--secondary)); border-radius: 4px; transition: width 1s ease; }
  .skill-val { width: 36px; font-size: 12px; font-weight: 700; color: var(--primary); text-align: right; }
  .streak-num { font-size: 48px; font-weight: 900; color: var(--secondary); text-align: center; }
  .section-title { font-size: 16px; font-weight: 700; margin-bottom: 4px; }
</style>
</head>
<body>

<!-- شاشة Onboarding -->
<div id="screen-onboarding" class="screen active">
  <div style="margin-top:20px">
    <div class="logo">zyzo_pro</div>
    <div class="subtitle">أخبرنا عنك لنخصص دروسك</div>
  </div>
  <div class="card" style="gap:16px;display:flex;flex-direction:column">
    <div>
      <label>اسمك</label>
      <input type="text" id="ob-name" placeholder="مثال: محمد" />
    </div>
    <div>
      <label>مستواك في الإنجليزية</label>
      <select id="ob-level">
        <option value="beginner">مبتدئ (A1-A2)</option>
        <option value="elementary">أساسي (A2-B1)</option>
        <option value="intermediate" selected>متوسط (B1-B2)</option>
        <option value="upper_intermediate">فوق المتوسط (B2-C1)</option>
        <option value="advanced">متقدم (C1-C2)</option>
      </select>
    </div>
    <div>
      <label>هدفك من التعلم</label>
      <select id="ob-goal">
        <option value="daily_conversation">محادثة يومية</option>
        <option value="business">بيئة العمل</option>
        <option value="academic">أكاديمي</option>
        <option value="travel">السفر</option>
        <option value="exam_prep">IELTS / TOEFL</option>
      </select>
    </div>
    <div>
      <label>اهتماماتك</label>
      <div class="tags" id="interests-tags">
        <div class="tag" onclick="toggleTag(this)">💻 تقنية</div>
        <div class="tag" onclick="toggleTag(this)">⚽ رياضة</div>
        <div class="tag" onclick="toggleTag(this)">🎬 أفلام</div>
        <div class="tag" onclick="toggleTag(this)">🍕 طعام</div>
        <div class="tag" onclick="toggleTag(this)">✈️ سفر</div>
        <div class="tag" onclick="toggleTag(this)">🎮 ألعاب</div>
        <div class="tag" onclick="toggleTag(this)">🎵 موسيقى</div>
        <div class="tag" onclick="toggleTag(this)">📚 علوم</div>
        <div class="tag" onclick="toggleTag(this)">💼 أعمال</div>
        <div class="tag" onclick="toggleTag(this)">🏥 صحة</div>
      </div>
    </div>
  </div>
  <button class="btn btn-primary" onclick="submitOnboarding()">ابدأ التعلم 🚀</button>
</div>

<!-- شاشة التحميل -->
<div id="screen-loading" class="screen">
  <div class="loading">
    <div class="spinner"></div>
    <div style="font-size:20px;font-weight:700;margin-bottom:8px" id="loading-title">جاري توليد درسك اليومي...</div>
    <div class="loading-text">الذكاء الاصطناعي يختار موضوعاً مناسباً لمستواك</div>
  </div>
</div>

<!-- شاشة الدرس -->
<div id="screen-lesson" class="screen">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <div class="logo" style="font-size:22px">zyzo_pro</div>
    <button class="btn btn-outline" style="width:auto;padding:8px 16px;font-size:13px" onclick="showScreen('screen-profile')">الملف الشخصي</button>
  </div>
  <div class="card">
    <div class="lesson-meta" id="lesson-meta"></div>
    <br>
    <div class="lesson-title" id="lesson-title"></div>
  </div>
  <div class="card">
    <div class="section-title">📖 اقرأ النص</div>
    <br>
    <div class="lesson-body" id="lesson-body"></div>
  </div>
  <div class="card">
    <div class="section-title">📝 مفردات جديدة</div>
    <div id="vocab-list"></div>
  </div>
  <button class="btn btn-primary" onclick="startQuiz()">ابدأ الاختبار ←</button>
</div>

<!-- شاشة الاختبار -->
<div id="screen-quiz" class="screen">
  <div>
    <div class="quiz-progress"><div class="quiz-progress-bar" id="quiz-progress-bar" style="width:0%"></div></div>
    <br>
    <div class="question-num" id="q-num"></div>
    <div class="question-text" id="q-text"></div>
    <div class="options" id="q-options"></div>
  </div>
  <button class="btn btn-primary" id="q-next-btn" onclick="nextQuestion()" style="display:none">التالي ←</button>
</div>

<!-- شاشة النتائج -->
<div id="screen-results" class="screen">
  <div class="logo" style="font-size:22px;text-align:right">النتيجة 🎉</div>
  <div class="card" style="text-align:center;gap:12px;display:flex;flex-direction:column">
    <div class="score-circle">
      <div class="score-num" id="res-score"></div>
      <div class="score-label">النتيجة</div>
    </div>
    <div id="res-comment" style="font-size:16px;font-weight:600"></div>
  </div>
  <div class="card">
    <div class="section-title">🔥 الالتزام اليومي</div>
    <div style="font-size:36px;text-align:center">🔥</div>
    <div class="streak-num" id="res-streak"></div>
    <div style="text-align:center;color:var(--text-muted);font-size:14px">يوم متتالي</div>
  </div>
  <div class="card">
    <div class="section-title">📊 مستوى مهاراتك</div>
    <br>
    <div id="res-radar"></div>
  </div>
  <div class="card">
    <div class="section-title">✅ مراجعة الإجابات</div>
    <div id="res-review"></div>
  </div>
  <button class="btn btn-primary" onclick="newLesson()">درس جديد 📅</button>
  <button class="btn btn-outline" onclick="showScreen('screen-profile')">الملف الشخصي</button>
</div>

<!-- شاشة الملف الشخصي -->
<div id="screen-profile" class="screen">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <div class="logo" style="font-size:22px">الملف الشخصي</div>
    <button class="btn btn-outline" style="width:auto;padding:8px 16px;font-size:13px" onclick="goToLesson()">← الدرس</button>
  </div>
  <div class="card">
    <div style="font-size:24px;font-weight:900" id="p-name"></div>
    <div class="lesson-meta" style="margin-top:8px" id="p-badges"></div>
  </div>
  <div class="card">
    <div class="section-title">🔥 الالتزام اليومي</div>
    <div style="font-size:36px;text-align:center">🔥</div>
    <div class="streak-num" id="p-streak"></div>
    <div style="text-align:center;color:var(--text-muted);font-size:13px">أطول سلسلة: <span id="p-longest" style="color:var(--secondary)"></span> يوم</div>
  </div>
  <div class="card">
    <div class="section-title">📊 مستوى مهاراتك</div>
    <br>
    <div id="p-radar"></div>
  </div>
  <div class="card">
    <div class="section-title">📚 سجل الدروس</div>
    <div id="p-lessons"></div>
  </div>
  <button class="btn btn-outline" style="color:var(--error);border-color:var(--error)" onclick="resetApp()">إعادة التعيين</button>
</div>

<script>
const S = { userId: null, lesson: null, answers: [], currentQ: 0 };
const API = 'http://localhost:8000/api';
const LEVEL_AR = { beginner:'مبتدئ', elementary:'أساسي', intermediate:'متوسط', upper_intermediate:'فوق المتوسط', advanced:'متقدم' };

window.onload = () => {
  const saved = localStorage.getItem('zyzo_user');
  if (saved) {
    S.userId = JSON.parse(saved).userId;
    goToLesson();
  } else {
    showScreen('screen-onboarding');
  }
};

function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  window.scrollTo(0,0);
  if (id === 'screen-profile') loadProfile();
}

function toggleTag(el) { el.classList.toggle('selected'); }

async function submitOnboarding() {
  const name = document.getElementById('ob-name').value.trim();
  const level = document.getElementById('ob-level').value;
  const goal = document.getElementById('ob-goal').value;
  const interests = [...document.querySelectorAll('.tag.selected')].map(t => t.textContent.replace(/[^\u0600-\u06FFa-zA-Z ]/g,'').trim()).filter(Boolean);
  if (!name) { alert('أدخل اسمك'); return; }
  if (!interests.length) { alert('اختر اهتماماً واحداً على الأقل'); return; }
  showScreen('screen-loading');
  try {
    const res = await fetch(`${API}/onboarding`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name,level,goal,interests}) });
    const data = await res.json();
    S.userId = data.user_id;
    localStorage.setItem('zyzo_user', JSON.stringify({userId: S.userId}));
    await loadLesson();
  } catch(e) {
    alert('خطأ في الاتصال: ' + e.message);
    showScreen('screen-onboarding');
  }
}

async function goToLesson() { showScreen('screen-loading'); await loadLesson(); }

async function loadLesson() {
  try {
    const res = await fetch(`${API}/lesson/today/${S.userId}`);
    const data = await res.json();
    if (data.detail) throw new Error(data.detail);
    S.lesson = data;
    renderLesson(data);
    showScreen('screen-lesson');
  } catch(e) {
    alert('فشل تحميل الدرس: ' + e.message);
    showScreen('screen-onboarding');
  }
}

function renderLesson(l) {
  document.getElementById('lesson-meta').innerHTML = `
    <span class="badge badge-purple">${LEVEL_AR[l.level]||l.level}</span>
    <span class="badge badge-pink">⏱ ${l.reading_time_minutes} دقيقة</span>
    <span class="badge badge-purple">📝 ${l.word_count} كلمة</span>`;
  document.getElementById('lesson-title').textContent = l.title;
  document.getElementById('lesson-body').textContent = l.body_text;
  document.getElementById('vocab-list').innerHTML = (l.vocabulary||[]).map(v => `
    <div class="vocab-item">
      <div><span class="vocab-word">${v.word}</span><span class="vocab-pos">${v.part_of_speech||''}</span></div>
      <div class="vocab-def">${v.definition}</div>
      ${v.example?`<div class="vocab-ex">"${v.example}"</div>`:''}
    </div>`).join('');
}

function startQuiz() { S.answers=[]; S.currentQ=0; showScreen('screen-quiz'); renderQuestion(); }

function renderQuestion() {
  const qs = S.lesson.questions;
  const q = qs[S.currentQ];
  document.getElementById('quiz-progress-bar').style.width = (S.currentQ/qs.length*100)+'%';
  document.getElementById('q-num').textContent = `سؤال ${S.currentQ+1} من ${qs.length}`;
  document.getElementById('q-text').textContent = q.question_text;
  document.getElementById('q-next-btn').style.display = 'none';
  const labels = [q.option_a, q.option_b, q.option_c, q.option_d];
  document.getElementById('q-options').innerHTML = ['A','B','C','D'].map((o,i) => `
    <div class="option" id="opt-${o}" onclick="selectOption('${o}')">
      <div class="option-letter">${o}</div><div>${labels[i]}</div>
    </div>`).join('');
}

function selectOption(letter) {
  const q = S.lesson.questions[S.currentQ];
  document.querySelectorAll('.option').forEach(el => el.onclick = null);
  const correct = q.correct_answer.toUpperCase();
  document.getElementById('opt-'+correct).classList.add('correct');
  if (letter !== correct) document.getElementById('opt-'+letter).classList.add('wrong');
  S.answers.push({question_index: S.currentQ, chosen_answer: letter});
  const btn = document.getElementById('q-next-btn');
  btn.style.display = 'block';
  btn.textContent = S.currentQ < S.lesson.questions.length-1 ? 'التالي ←' : 'عرض النتائج 🎉';
}

async function nextQuestion() {
  if (S.currentQ < S.lesson.questions.length-1) { S.currentQ++; renderQuestion(); }
  else await submitQuiz();
}

async function submitQuiz() {
  showScreen('screen-loading');
  document.getElementById('loading-title').textContent = 'جاري حساب نتيجتك...';
  try {
    const res = await fetch(`${API}/quiz/submit`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({lesson_id:S.lesson.id, user_id:S.userId, answers:S.answers}) });
    const data = await res.json();
    renderResults(data);
    showScreen('screen-results');
  } catch(e) { alert('خطأ: '+e.message); showScreen('screen-lesson'); }
}

function renderResults(data) {
  const score = data.score;
  document.getElementById('res-score').textContent = score+'%';
  document.getElementById('res-comment').textContent = score>=80?'🎉 ممتاز!':score>=60?'👍 جيد!':score>=40?'💪 واصل':'📖 راجع الدرس';
  document.getElementById('res-streak').textContent = (data.streak||{}).current_streak||1;
  document.getElementById('res-radar').innerHTML = renderRadar(data.radar||{});
  document.getElementById('res-review').innerHTML = (data.results||[]).map((r,i)=>`
    <div class="stat-row">
      <div style="font-size:13px;max-width:80%">${i+1}. ${r.question_text}</div>
      <div style="font-size:20px">${r.is_correct?'✅':'❌'}</div>
    </div>`).join('');
}

function renderRadar(r) {
  return [['المفردات','vocabulary'],['القواعد','grammar'],['القراءة','reading']].map(([n,k])=>`
    <div class="skill-bar-row">
      <div class="skill-name">${n}</div>
      <div class="skill-bar-bg"><div class="skill-bar-fill" style="width:${r[k]||0}%"></div></div>
      <div class="skill-val">${Math.round(r[k]||0)}</div>
    </div>`).join('');
}

async function loadProfile() {
  try {
    const res = await fetch(`${API}/profile/${S.userId}`);
    const data = await res.json();
    const u=data.user, s=data.streak||{}, r=data.radar||{};
    document.getElementById('p-name').textContent = u.name;
    document.getElementById('p-badges').innerHTML = `<span class="badge badge-purple">${LEVEL_AR[u.level]||u.level}</span>`;
    document.getElementById('p-streak').textContent = s.current_streak||0;
    document.getElementById('p-longest').textContent = s.longest_streak||0;
    document.getElementById('p-radar').innerHTML = renderRadar(r);
    document.getElementById('p-lessons').innerHTML = (data.lessons||[]).map(l=>`
      <div class="stat-row">
        <div><div style="font-size:14px;font-weight:600">${l.title}</div><div style="font-size:12px;color:var(--text-muted)">${l.lesson_date}</div></div>
        <div style="font-size:20px">${l.is_completed?'✅':'📖'}</div>
      </div>`).join('') || '<div style="color:var(--text-muted);text-align:center;padding:16px">لا توجد دروس بعد</div>';
  } catch(e) { console.error(e); }
}

function newLesson() { showScreen('screen-loading'); document.getElementById('loading-title').textContent='جاري توليد درسك اليومي...'; loadLesson(); }

function resetApp() {
  if (!confirm('إعادة التعيين الكامل؟')) return;
  localStorage.clear(); S.userId=null; S.lesson=null;
  showScreen('screen-onboarding');
}
</script>
</body>
</html>"""

# ── Schemas ───────────────────────────────────────────────────────────────────
class OnboardingReq(BaseModel):
    name: str
    level: str
    goal: str
    interests: List[str]

class QuizAnswer(BaseModel):
    question_index: int
    chosen_answer: str

class QuizSubmit(BaseModel):
    lesson_id: int
    user_id: int
    answers: List[QuizAnswer]

# ── App ───────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if GEMINI_API_KEY:
        init_gemini(GEMINI_API_KEY)
    else:
        print("⚠️  GEMINI_API_KEY فارغ! أضف مفتاحك في السطر 25 من الكود")
    print("\n" + "="*50)
    print("🚀 zyzo_pro يعمل!")
    print("🌐 افتح المتصفح على: http://localhost:8000")
    print("="*50 + "\n")
    def open_browser():
        time.sleep(1.5)
        webbrowser.open("http://localhost:8000")
    threading.Thread(target=open_browser, daemon=True).start()
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(HTML)

@app.post("/api/onboarding")
def onboarding(data: OnboardingReq):
    conn = get_db()
    row = conn.execute("SELECT id FROM users WHERE name=?", (data.name,)).fetchone()
    if row:
        uid = row["id"]
        conn.execute("UPDATE users SET level=?,goal=?,interests=? WHERE id=?",
                     (data.level, data.goal, json.dumps(data.interests), uid))
    else:
        cur = conn.execute("INSERT INTO users(name,level,goal,interests) VALUES(?,?,?,?)",
                           (data.name, data.level, data.goal, json.dumps(data.interests)))
        uid = cur.lastrowid
        conn.execute("INSERT OR IGNORE INTO streak(user_id) VALUES(?)", (uid,))
        conn.execute("INSERT OR IGNORE INTO skill_radar(user_id) VALUES(?)", (uid,))
    conn.commit()
    conn.close()
    return {"user_id": uid, "name": data.name}

@app.get("/api/lesson/today/{user_id}")
def get_today_lesson(user_id: int):
    conn = get_db()
    today = date.today().isoformat()
    row = conn.execute(
        "SELECT * FROM lessons WHERE user_id=? AND lesson_date=? ORDER BY id DESC LIMIT 1",
        (user_id, today)
    ).fetchone()
    if row:
        r = dict(row)
        r["vocabulary"] = json.loads(r["vocabulary"])
        r["questions"]  = json.loads(r["questions"])
        conn.close()
        return r
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        conn.close()
        raise HTTPException(404, "User not found")
    recent = [r["topic"] for r in conn.execute(
        "SELECT topic FROM lessons WHERE user_id=? ORDER BY id DESC LIMIT 10", (user_id,)
    ).fetchall()]
    try:
        data = generate_lesson_ai(user["level"], user["goal"], json.loads(user["interests"]), recent)
    except Exception as e:
        conn.close()
        raise HTTPException(503, f"AI error: {e}")
    cur = conn.execute(
        "INSERT INTO lessons(user_id,lesson_date,topic,title,body_text,level,word_count,reading_time_minutes,vocabulary,questions) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (user_id, today, data["topic"], data["title"], data["body_text"], user["level"],
         data.get("word_count",0), data.get("reading_time_minutes",2),
         json.dumps(data.get("vocabulary",[])), json.dumps(data.get("questions",[])))
    )
    lid = cur.lastrowid
    conn.commit()
    r = dict(conn.execute("SELECT * FROM lessons WHERE id=?", (lid,)).fetchone())
    r["vocabulary"] = json.loads(r["vocabulary"])
    r["questions"]  = json.loads(r["questions"])
    conn.close()
    return r

@app.post("/api/quiz/submit")
def submit_quiz(data: QuizSubmit):
    conn = get_db()
    lesson = conn.execute("SELECT * FROM lessons WHERE id=?", (data.lesson_id,)).fetchone()
    if not lesson:
        conn.close()
        raise HTTPException(404, "Lesson not found")
    questions = json.loads(lesson["questions"])
    correct = 0
    results = []
    for ans in data.answers:
        idx = ans.question_index
        if idx < len(questions):
            q = questions[idx]
            ok = ans.chosen_answer.upper() == q["correct_answer"].upper()
            if ok: correct += 1
            results.append({"question_text":q["question_text"],"chosen":ans.chosen_answer.upper(),
                            "correct":q["correct_answer"].upper(),"is_correct":ok,"explanation":q.get("explanation","")})
    total = len(data.answers)
    score = round((correct/total)*100, 1) if total else 0
    conn.execute("INSERT INTO user_answers(user_id,lesson_id,score_percent) VALUES(?,?,?)",
                 (data.user_id, data.lesson_id, score))
    conn.execute("UPDATE lessons SET is_completed=1 WHERE id=?", (data.lesson_id,))
    today = date.today().isoformat()
    yesterday = (date.today()-timedelta(days=1)).isoformat()
    s = conn.execute("SELECT * FROM streak WHERE user_id=?", (data.user_id,)).fetchone()
    if s:
        last = s["last_activity_date"]
        new_s = (s["current_streak"]+1) if last==yesterday else (s["current_streak"] if last==today else 1)
        conn.execute("UPDATE streak SET current_streak=?,longest_streak=MAX(longest_streak,?),last_activity_date=?,total_days=total_days+1 WHERE user_id=?",
                     (new_s, new_s, today, data.user_id))
    conn.execute("UPDATE skill_radar SET reading=MIN(100,MAX(0,reading+?)) WHERE user_id=?",
                 (score/25, data.user_id))
    conn.commit()
    streak = dict(conn.execute("SELECT * FROM streak WHERE user_id=?", (data.user_id,)).fetchone() or {})
    radar  = dict(conn.execute("SELECT * FROM skill_radar WHERE user_id=?", (data.user_id,)).fetchone() or {})
    conn.close()
    return {"total":total,"correct":correct,"score":score,"results":results,"streak":streak,"radar":radar}

@app.get("/api/profile/{user_id}")
def get_profile(user_id: int):
    conn = get_db()
    user    = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    streak  = conn.execute("SELECT * FROM streak WHERE user_id=?", (user_id,)).fetchone()
    radar   = conn.execute("SELECT * FROM skill_radar WHERE user_id=?", (user_id,)).fetchone()
    lessons = conn.execute(
        "SELECT id,lesson_date,topic,title,level,is_completed FROM lessons WHERE user_id=? ORDER BY id DESC LIMIT 20",
        (user_id,)
    ).fetchall()
    conn.close()
    if not user: raise HTTPException(404, "Not found")
    return {"user":dict(user),"streak":dict(streak) if streak else {},
            "radar":dict(radar) if radar else {},"lessons":[dict(l) for l in lessons]}

if __name__ == "__main__":
    uvicorn.run("zyzo_pro:app", host="0.0.0.0", port=8000, reload=False)
