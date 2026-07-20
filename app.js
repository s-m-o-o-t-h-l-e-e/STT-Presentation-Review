const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

const state = {
  view: "home",
  tab: "upload",
  analysis: null,
  qaIndex: 0,
  qaAnswers: {},
  qaResults: {},
  selectedFile: null,
  selectedMaterial: null,
  busy: false,
  recognition: null,
  listening: false,
  streamingTranscript: "",
  streamingInterim: "",
  targetLang: "en",
  translation: "",
  translationStatus: "대기",
};

const $ = (id) => document.getElementById(id);
const html = (value = "") => String(value)
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");
const scoreOf = (value) => Math.max(0, Math.min(100, Number(value || 0)));
const ready = () => Boolean(state.analysis);

function asText(value, fallback = "") {
  if (value === null || value === undefined) return fallback;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map((item) => asText(item)).filter(Boolean).join(", ");
  if (typeof value === "object") {
    for (const key of ["title", "question", "detail", "fix", "summary", "text", "value", "name", "category", "reason"]) {
      if (value[key]) return asText(value[key], fallback);
    }
  }
  return fallback;
}

function meaningfulText(value, fallback = "") {
  const text = asText(value, fallback).trim();
  if (!text || /^\d+\.?$/.test(text)) return "";
  return text;
}

function metricCount(value, fallbackList = []) {
  if (typeof value === "number") return value;
  if (typeof value === "string") {
    const match = value.match(/\d+/);
    return match ? Number(match[0]) : 0;
  }
  if (Array.isArray(value)) return value.length;
  if (value && typeof value === "object") return Object.keys(value).length;
  return Array.isArray(fallbackList) ? fallbackList.length : 0;
}

function cleanSpeaker(value) {
  const text = asText(value, "화자 1").trim();
  if (!text || /[\uFFFD?]/.test(text) || text.includes("미상")) return "화자 1";
  return text;
}

function displaySpeakers(items) {
  const rows = Array.isArray(items) ? items : [];
  return rows.map((row) => ({ ...row, speaker: cleanSpeaker(row.speaker) }));
}

function displayTimelineItems(items) {
  const rows = Array.isArray(items) ? items : [];
  return rows.map((row) => ({
    ...row,
    speaker: cleanSpeaker(row.speaker),
  }));
}

function formatGap(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number) || number <= 0) return "0";
  return number < 1 ? number.toFixed(2).replace(/0+$/, "").replace(/\.$/, "") : number.toFixed(1).replace(/\.0$/, "");
}

function displayVoiceScores(analysis) {
  const base = analysis?.voice_scores && typeof analysis.voice_scores === "object" ? analysis.voice_scores : {};
  const keys = ["발표 흐름", "내용 전달력", "Q&A 대응", "시간 관리"];
  const normalized = Object.fromEntries(keys.map((key) => [key, scoreOf(base[key])]));
  if (Object.values(normalized).reduce((sum, value) => sum + value, 0) > 0 || !analysis?.score) return normalized;
  const score = scoreOf(analysis.score);
  const wpm = Number(analysis.wpm || 0);
  const fillers = Number(analysis.filler_total || 0);
  return {
    "발표 흐름": scoreOf(score + (wpm >= 110 && wpm <= 150 ? 3 : -8)),
    "내용 전달력": scoreOf(score - Math.min(14, Math.floor(fillers / 4))),
    "Q&A 대응": scoreOf(score - 8),
    "시간 관리": scoreOf(90 - Math.floor(Math.abs(wpm - 135) / 2)),
  };
}

function cleanVocabItems(items) {
  return (Array.isArray(items) ? items : []).map((item) => {
    if (typeof item === "string") return { original: item, replacement: "", reason: "" };
    return {
      original: asText(item?.original || item?.before || item?.word || item?.expression),
      replacement: asText(item?.replacement || item?.after || item?.suggestion),
      reason: asText(item?.reason || item?.detail),
    };
  }).filter((item) => item.original || item.replacement || item.reason);
}

function cleanProblems(items) {
  return (Array.isArray(items) ? items : []).map((item) => {
    if (typeof item === "string") return { title: meaningfulText(item), level: "확인", fix: "" };
    return {
      title: meaningfulText(item?.title || item?.problem || item?.issue || item?.category),
      level: asText(item?.level || item?.severity, "확인"),
      fix: meaningfulText(item?.fix || item?.solution || item?.detail || item?.reason),
    };
  }).filter((item) => item.title || item.fix);
}

function cleanPriorities(items) {
  return (Array.isArray(items) ? items : []).map((item) => {
    if (typeof item === "string") return { title: meaningfulText(item), impact: "", detail: "" };
    return {
      title: meaningfulText(item?.title || item?.priority || item?.name),
      impact: asText(item?.impact || item?.level),
      detail: meaningfulText(item?.detail || item?.fix || item?.reason),
    };
  }).filter((item) => item.title || item.detail);
}

function cleanQuestions(items) {
  return (Array.isArray(items) ? items : []).map((item) => {
    if (typeof item === "string") return { category: "질문", question: meaningfulText(item), level: "-" };
    return {
      category: asText(item?.category || item?.type, "질문"),
      question: meaningfulText(item?.question || item?.title || item?.text),
      level: asText(item?.level || item?.difficulty, "-"),
    };
  }).filter((item) => item.question);
}

function setView(view, tab = state.tab) {
  state.view = view;
  state.tab = tab;
  render();
}

function setTab(tab) {
  state.view = "demo";
  state.tab = tab;
  render();
}

function bar(label, value, tone = "cyan") {
  const n = scoreOf(value);
  return `<div class="scorebar"><p>${html(label)}<b>${n}점</b></p><span><i class="${tone}" style="width:${n}%"></i></span></div>`;
}

function card(title, body, cls = "") {
  return `<article class="card ${cls}"><h3>${html(title)}</h3>${body}</article>`;
}

function renderHome() {
  const a = state.analysis;
  const voices = ready() ? displayVoiceScores(a) : {
    "발표 흐름": 0,
    "내용 전달력": 0,
    "Q&A 대응": 0,
    "시간 관리": 0,
  };
  $("homeView").innerHTML = `
    <section class="hero">
      <div class="hero-copy">
        <span class="eyebrow">AI 발표평가 사전심사</span>
        <h1>실전 발표 전,<br><em>AI 심사위원</em>과 연습하세요</h1>
        <p>발표 음성을 업로드하면 기존 파일 분석을 진행하고, 음성 파일이 없으면 실시간 STT 전사문으로 대체 분석할 수 있습니다.</p>
        <button class="primary" onclick="setView('demo','upload')">사전심사 시작</button>
        <div class="hero-stats">
          <span><b>${ready() ? html(a.filler_total) : "-"}</b>추임새</span>
          <span><b>${ready() ? html(a.wpm) : "-"}</b>WPM</span>
          <span><b>${ready() ? html(a.document_match?.score ?? "-") : "-"}</b>자료 일치율</span>
        </div>
      </div>
      <div class="hero-report">
        <div class="report-top">
          <span class="iconbox">R</span>
          <div><b>발표평가 결과</b><small>AI 사전심사 리포트</small></div>
          <strong>${ready() ? html(a.score) : "--"}<small>/100점</small></strong>
        </div>
        ${Object.entries(voices).map(([k, v], i) => bar(k, v, i === 3 ? "yellow" : "blue")).join("")}
        <p class="notice">${ready() ? html(a.summary || "분석이 완료되었습니다.") : "파일 또는 실시간 전사문이 생기기 전에는 평가 수치를 표시하지 않습니다."}</p>
      </div>
    </section>
    <section class="section">
      <h2>발표평가 사전심사 프로세스</h2>
      <p>음성 파일 분석, 실시간 STT 대체 입력, 자료 비교, 예상 질문, 종합 리포트까지 한 화면에서 처리합니다.</p>
      <div class="grid4">
        ${[
          ["발표 음성/실시간 STT", "파일이 없으면 실시간 전사문으로 대체"],
          ["PPT/PDF 자료 업로드", "발표자료 텍스트 추출"],
          ["AI 사전 분석", "CLOVA STT + Python + Claude"],
          ["종합 평가 리포트", "점수와 개선점 도출"],
        ].map((item, i) => `<article class="mini"><span>Step ${i + 1}</span><b>${item[0]}</b><small>${item[1]}</small></article>`).join("")}
      </div>
    </section>
    <section class="section">
      <h2>실전과 동일한 심사위원 구성</h2>
      <div class="grid3">
        ${card("투자 심사역 AI", "<span class='badge green'>VC</span><p>투자 매력도, ROI, Exit 전략을 검토합니다.</p>")}
        ${card("기술 전문가 AI", "<span class='badge blue'>TE</span><p>기술 실현 가능성, 특허, R&D 역량을 검토합니다.</p>")}
        ${card("산업 전문가 AI", "<span class='badge sky'>IE</span><p>시장성, 경쟁 환경, 진입 장벽을 검토합니다.</p>")}
      </div>
    </section>
    <section class="section">
      <h2>5대 핵심 평가 항목</h2>
      <div class="grid5">
        ${["문제 정의 명확성", "솔루션 차별성", "시장 기회", "팀 역량", "비즈니스 모델"].map((t, i) => `<article class="mini"><span>${[20, 25, 20, 15, 20][i]}%</span><b>${t}</b><small>IR 심사 기준 기반 평가</small></article>`).join("")}
      </div>
    </section>`;
}

function tabs() {
  const items = [
    ["upload", "등록 발표자료"],
    ["questions", "예상질문준비"],
    ["analysis", "분석결과"],
    ["summary", "종합결과"],
  ];
  return `<div class="tabs">${items.map(([id, label]) => `<button class="${state.tab === id ? "active" : ""}" onclick="setTab('${id}')">${label}</button>`).join("")}</div>`;
}

function renderDemo() {
  $("demoView").innerHTML = `
    <header class="page-head">
      <button class="link" onclick="setView('home')">← 발표평가로 돌아가기</button>
      <div><p>발표 음성 / 실시간 STT</p></div>
      <button class="outline" onclick="downloadReport()">리포트 다운로드</button>
    </header>
    ${tabs()}
    <div id="tabBody"></div>`;
  renderTab();
}

function renderTab() {
  if (state.tab === "upload") renderUpload();
  if (state.tab === "questions") renderQuestions();
  if (state.tab === "analysis") renderAnalysis();
  if (state.tab === "summary") renderSummary();
}

function renderUpload() {
  const a = state.analysis;
  const audioName = state.selectedFile ? state.selectedFile.name : "M4A, MP3, WAV 파일을 선택하세요";
  const materialName = state.selectedMaterial ? state.selectedMaterial.name : "PPTX 또는 PDF 파일을 선택하세요";
  $("tabBody").innerHTML = `
    <section class="upload-layout">
      <div class="slide-preview">
        <div class="brain">AI</div>
        <h1>더플랜AI</h1>
        <p>발표 음성 파일이 있으면 파일 분석을 우선 사용하고, 없으면 아래 실시간 STT 전사문으로 대체 분석합니다.</p>
        <div class="upload-duo">
          <label class="upload-box" for="audioInput">
            <input id="audioInput" type="file" accept=".mp3,.wav,.m4a,.aac,.flac,audio/*" onchange="handleAudioSelected(this)">
            <span>발표 음성 업로드</span><small>${html(audioName)}</small>
          </label>
          <label class="upload-box" for="materialInput">
            <input id="materialInput" type="file" accept=".pptx,.pdf,application/pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation" onchange="handleMaterialSelected(this)">
            <span>PPT/PDF 발표자료 업로드</span><small>${html(materialName)}</small>
          </label>
        </div>
        <button class="primary wide" onclick="analyzePresentation()" ${state.busy ? "disabled" : ""}>${state.busy ? "분석 중..." : "분석 시작하기"}</button>
      </div>
      <aside class="side-panel">
        <h3>${a ? html(a.audio_name) : "발표자료 대기"}</h3>
        <div class="metric3">
          <b>${a ? html(a.score) : "-"}</b><b>${a ? html(a.wpm) : "-"}</b><b>${a?.document_match?.available ? html(a.document_match.score) : "-"}</b>
          <small>종합점수</small><small>WPM</small><small>자료 일치율</small>
        </div>
        ${a ? Object.entries(displayVoiceScores(a)).map(([k, v], i) => bar(k, v, i === 3 ? "purple" : "cyan")).join("") : "<p class='muted'>음성 파일이 있으면 기존 분석, 없으면 실시간 STT 전사문으로 대체 분석합니다.</p>"}
      </aside>
    </section>
    ${renderStreamingPanel()}`;
}

function renderStreamingPanel() {
  return `
    <section class="streaming-panel">
      <div class="panel-head">
        <h2>실시간 한국어 STT</h2>
        <span>${state.listening ? "전사 중" : "대기 중"}</span>
      </div>
      <div class="streaming-actions">
        <button class="primary" onclick="startStreaming()" ${state.listening ? "disabled" : ""}>실시간 STT 시작</button>
        <button class="outline" onclick="stopStreaming()" ${!state.listening ? "disabled" : ""}>중지</button>
        <button class="outline" onclick="clearStreaming()">전사문 지우기</button>
        <label class="streaming-select">번역 언어
          <select onchange="setTargetLang(this.value)">
            ${[
              ["en", "영어"], ["ja", "일본어"], ["zh", "중국어 간체"], ["es", "스페인어"],
              ["fr", "프랑스어"], ["de", "독일어"], ["vi", "베트남어"], ["id", "인도네시아어"],
            ].map(([value, label]) => `<option value="${value}" ${state.targetLang === value ? "selected" : ""}>${label}</option>`).join("")}
          </select>
        </label>
        <button class="outline" onclick="translateStreaming()">번역하기</button>
      </div>
      <div class="streaming-grid">
        <article class="stream-box">
          <h3>한국어 전사문</h3>
          <textarea id="streamingText" oninput="updateStreamingText(this.value)" placeholder="실시간 STT 결과가 여기에 표시됩니다. 직접 입력해도 분석에 사용할 수 있습니다.">${html(state.streamingTranscript)}</textarea>
          <p class="muted">${state.streamingInterim ? `인식 중: ${html(state.streamingInterim)}` : `${state.streamingTranscript.replace(/\s/g, "").length}자`}</p>
        </article>
        <article class="stream-box">
          <h3>번역 결과 <span>${html(state.translationStatus)}</span></h3>
          <div class="translation-box">${html(state.translation)}</div>
        </article>
      </div>
      <p class="muted">음성 파일이 없을 때는 이 전사문이 분석 입력으로 사용됩니다. 음성 파일이 있을 때는 보조 전사/번역 기능으로 사용할 수 있습니다.</p>
    </section>`;
}

function handleAudioSelected(input) {
  state.selectedFile = input.files && input.files.length ? input.files[0] : null;
  renderUpload();
}

function handleMaterialSelected(input) {
  state.selectedMaterial = input.files && input.files.length ? input.files[0] : null;
  renderUpload();
}

function createRecognition() {
  if (!SpeechRecognition) {
    alert("이 브라우저는 실시간 음성 인식을 지원하지 않습니다. Chrome 또는 Edge를 사용해 주세요.");
    return null;
  }
  const recognition = new SpeechRecognition();
  recognition.lang = "ko-KR";
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;
  recognition.onstart = () => {
    state.listening = true;
    renderUpload();
  };
  recognition.onresult = (event) => {
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const text = event.results[i][0].transcript.trim();
      if (event.results[i].isFinal && text) state.streamingTranscript += `${text}\n`;
      else interim += text;
    }
    state.streamingInterim = interim;
    renderUpload();
  };
  recognition.onerror = (event) => {
    state.listening = false;
    alert(event.error || "실시간 음성 인식 오류가 발생했습니다.");
    renderUpload();
  };
  recognition.onend = () => {
    state.listening = false;
    state.streamingInterim = "";
    renderUpload();
  };
  return recognition;
}

function startStreaming() {
  if (!state.recognition) state.recognition = createRecognition();
  if (!state.recognition || state.listening) return;
  state.recognition.start();
}

function stopStreaming() {
  if (state.recognition && state.listening) state.recognition.stop();
}

function clearStreaming() {
  state.streamingTranscript = "";
  state.streamingInterim = "";
  state.translation = "";
  state.translationStatus = "대기";
  renderUpload();
}

function updateStreamingText(value) {
  state.streamingTranscript = value;
}

function setTargetLang(value) {
  state.targetLang = value;
}

async function translateStreaming() {
  const text = state.streamingTranscript.trim();
  if (!text) {
    alert("번역할 한국어 전사문이 없습니다.");
    return;
  }
  state.translationStatus = "번역 중";
  renderUpload();
  try {
    const res = await fetch("/api/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, target: state.targetLang }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "번역 실패");
    state.translation = data.translation;
    state.translationStatus = "완료";
  } catch (err) {
    state.translation = err.message || String(err);
    state.translationStatus = "오류";
  }
  renderUpload();
}

async function analyzePresentation() {
  const transcript = state.streamingTranscript.trim();
  if (!state.selectedFile && !transcript) {
    alert("발표 음성 파일을 선택하거나 실시간 STT 전사문을 입력해 주세요.");
    return;
  }
  state.busy = true;
  renderTab();
  try {
    const form = new FormData();
    if (state.selectedFile) form.append("audio", state.selectedFile);
    if (state.selectedMaterial) form.append("material", state.selectedMaterial);
    if (transcript) form.append("streaming_transcript", transcript);
    const res = await fetch("/api/analyze", { method: "POST", body: form });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "분석 실패");
    state.analysis = data.analysis;
    state.tab = "analysis";
  } catch (err) {
    alert(err.message || String(err));
  } finally {
    state.busy = false;
    render();
  }
}

function questions() {
  const q = cleanQuestions(state.analysis?.questions || []);
  return q.length ? q : [{ category: "대기", question: "발표 음성 또는 전사문을 분석하면 예상 질문이 생성됩니다.", level: "-" }];
}

function renderQuestions() {
  const list = questions();
  const idx = Math.min(state.qaIndex, list.length - 1);
  const item = list[idx];
  const result = state.qaResults[idx];
  $("tabBody").innerHTML = `
    <section class="qa-layout">
      <div>
        <div class="question-stage">
          <span class="pill">예상 질문 #${idx + 1}</span>
          <div class="qicon">Q</div>
          <p>[${html(item.category)}]</p>
          <h1>${html(item.question)}</h1>
          <small>권장 답변 시간: 90초 · ${html(item.level)}</small>
        </div>
        <div class="question-nav">
          <button class="outline" onclick="moveQuestion(-1)">이전 질문</button>
          <div class="dot-nav">${list.map((_, i) => `<button class="dot-btn ${i === idx ? "active" : ""}" onclick="goQuestion(${i})">${i + 1}</button>`).join("")}</div>
          <button class="outline" onclick="moveQuestion(1)">다음 질문</button>
        </div>
        <h2>내 답변 및 AI 분석</h2>
        <textarea id="answerText" placeholder="질문에 대한 답변을 입력하세요.">${html(state.qaAnswers[idx] || "")}</textarea>
        <button class="primary" onclick="evaluateAnswer()">답변 평가하기</button>
        ${result ? renderAnswerResult(result) : ""}
      </div>
      <aside class="side-panel">
        <h3>예상질문 연습</h3>
        <div class="metric2">
          <b>${Object.keys(state.qaResults).length}/${list.length}</b><b>${result?.score || "-"}</b>
          <small>완료한 질문</small><small>현재 점수</small>
        </div>
        ${bar("논리성", result?.logic || 0)}
        ${bar("구체성", result?.specificity || 0, "green")}
        ${bar("자신감", result?.confidence || 0, "purple")}
        ${bar("시간 관리", result?.time_control || 0, "yellow")}
      </aside>
    </section>`;
}

function goQuestion(i) {
  const area = $("answerText");
  if (area) state.qaAnswers[state.qaIndex] = area.value;
  state.qaIndex = i;
  renderQuestions();
}

function moveQuestion(delta) {
  const len = questions().length;
  goQuestion(Math.max(0, Math.min(len - 1, state.qaIndex + delta)));
}

async function evaluateAnswer() {
  if (!ready()) {
    alert("먼저 발표를 분석해 주세요.");
    return;
  }
  const answer = $("answerText").value.trim();
  if (!answer) {
    alert("답변을 입력해 주세요.");
    return;
  }
  const idx = state.qaIndex;
  state.qaAnswers[idx] = answer;
  const res = await fetch("/api/evaluate-answer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question: questions()[idx], answer, transcript: state.analysis.transcript || "" }),
  });
  const data = await res.json();
  state.qaResults[idx] = data.result || {};
  renderQuestions();
}

function renderAnswerResult(r) {
  return `<article class="answer-card"><h3>AI 답변 평가 <span>${scoreOf(r.score)}점</span></h3><div class="two"><div><b>강점</b><ul>${(r.strengths || []).map((x) => `<li>${html(x)}</li>`).join("") || "<li>분석 결과 없음</li>"}</ul></div><div><b>개선점</b><ul>${(r.improvements || []).map((x) => `<li>${html(x)}</li>`).join("") || "<li>분석 결과 없음</li>"}</ul></div></div><p><b>모범 답변 예시</b><br>${html(r.model_answer || "")}</p></article>`;
}

function renderAnalysis() {
  const a = state.analysis;
  if (!a) {
    $("tabBody").innerHTML = `<section class="empty">발표 음성 또는 실시간 전사문을 분석하면 결과가 표시됩니다.</section>`;
    return;
  }
  const matchCard = a.document_match?.available ? card("자료-음성 일치율", renderDocumentMatch(a.document_match), "full") : "";
  $("tabBody").innerHTML = `
    <section class="metrics">
      ${card("종합 점수", `<strong>${html(a.score)}<small>/100</small></strong>`)}
      ${card("평균 발화속도", `<strong>${html(a.wpm)}<small> WPM</small></strong>`)}
      ${card("추임새 단어", `<strong>${html(a.filler_total)}<small>회</small></strong>`)}
      ${card("어휘 문제", `<strong>${metricCount(a.vocab_issues, a.vocab_suggestions)}<small>건</small></strong>`)}
    </section>
    ${matchCard}
    <section class="analysis-grid">
      ${card("발화 속도 분석", `<canvas id="paceChart" width="720" height="360"></canvas><p class="muted">권장 범위: 120-150 WPM</p>`, "chart-card")}
      ${card("음성 품질 분석", Object.entries(displayVoiceScores(a)).map(([k, v], i) => bar(k, v, i === 3 ? "yellow" : "cyan")).join(""))}
      ${card("추임새 단어 분석", renderFillers(a.filler_words || []))}
      ${card("어휘 개선 제안", renderVocab(a.vocab_suggestions || []))}
    </section>
    <section class="analysis-grid">
      ${card("화자별 분석", renderSpeakers(a.speaker_stats || []))}
      ${card("문장별 타임라인", renderTimeline(a.sentence_segments || []))}
    </section>
    ${card("슬라이드별 분석", renderSlideRows(a.slide_rows || []), "full")}`;
  drawPaceChart(a.pace_series || [], a.wpm || 140);
}

function renderDocumentMatch(match) {
  return `<div class="match-icons"><span>문서</span><i>${html(match.score)}%</i><span>발표 음성</span></div><p>${html(match.summary || "")}</p><div class="metric3"><b>${html(match.document_coverage)}%</b><b>${html(match.speech_extra_ratio)}%</b><b>${html(match.sections?.length || 0)}</b><small>자료 반영률</small><small>자료 외 발화 추정</small><small>페이지/슬라이드</small></div><div class="two"><div><b>자료에는 있지만 발표에서 약한 키워드</b><p>${(match.missing_terms || []).map(html).join(", ") || "없음"}</p></div><div><b>발표에는 있지만 자료에 약한 키워드</b><p>${(match.extra_terms || []).map(html).join(", ") || "없음"}</p></div></div>${renderDocumentSections(match.sections || [])}`;
}

function renderDocumentSections(rows) {
  if (!rows.length) return "";
  return `<table><thead><tr><th>자료 구간</th><th>일치율</th><th>상태</th><th>누락 키워드</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${html(r.title || r.page)}</td><td>${html(r.score)}%</td><td>${html(r.status)}</td><td>${(r.missing || []).map(html).join(", ")}</td></tr>`).join("")}</tbody></table>`;
}

function renderFillers(items) {
  if (!items.length) return "<p class='muted'>감지된 추임새 단어가 없습니다.</p>";
  return items.map((x) => `<div class="row"><b>"${html(x.word)}"</b><span class="tag">${html(x.severity)}</span><strong>${html(x.count)}회</strong></div>`).join("");
}

function renderVocab(items) {
  const rows = cleanVocabItems(items);
  if (!rows.length) return "<p class='muted'>감지된 어휘 개선 항목이 없습니다.</p>";
  return rows.map((x) => {
    const original = x.original || "";
    const replacement = x.replacement || "";
    const reason = x.reason || "";
    const body = replacement
      ? `<p class="vocab-pair"><b>${html(original || "-")}</b><span>→</span><em>${html(replacement)}</em></p>`
      : `<p class="vocab-single"><b>${html(original || reason || "-")}</b></p>`;
    return `<div class="vocab"><small>개선 표현</small>${body}${reason && reason !== original ? `<span>${html(reason)}</span>` : ""}</div>`;
  }).join("");
}

function renderSpeakers(items) {
  const rows = displaySpeakers(items);
  if (!rows.length) return "<p class='muted'>스트리밍 전사문 분석에서는 화자 분리 정보가 없을 수 있습니다.</p>";
  return `<table><thead><tr><th>화자</th><th>문장</th><th>발화시간</th><th>WPM</th><th>추임새</th></tr></thead><tbody>${rows.map((s) => `<tr><td>${html(s.speaker)}</td><td>${html(s.sentences)}</td><td>${html(s.seconds)}초</td><td>${html(s.wpm)}</td><td>${html(s.fillers)}회</td></tr>`).join("")}</tbody></table>`;
}

function renderTimeline(items) {
  const rows = displayTimelineItems(items);
  if (!rows.length) return "<p class='muted'>문장별 timestamp가 없습니다.</p>";
  return `<p class="muted">전체 ${rows.length}개 문장</p><div class="timeline-list">${rows.map((x) => `<div class="timeline-item"><b>${html(x.time)}</b><span>${html(x.speaker)} · 구간 ${html(x.section)} · 공백 ${html(formatGap(x.gap_before))}초</span><p>${html(x.text)}</p></div>`).join("")}</div>`;
}

function renderSlideRows(rows) {
  if (!rows.length) return "<p class='muted'>구간별 분석이 없습니다.</p>";
  return `<table><thead><tr><th>슬라이드</th><th>체류시간</th><th>권장시간</th><th>발화속도</th><th>추임새</th><th>피드백</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${html(r.slide)}</td><td>${html(r.duration)}</td><td>${html(r.recommended)}</td><td>${html(r.wpm)}</td><td>${html(r.fillers)}</td><td>${html(r.feedback)}</td></tr>`).join("")}</tbody></table>`;
}

function drawPaceChart(series, fallbackWpm) {
  const canvas = $("paceChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  const pad = { l: 58, r: 24, t: 34, b: 58 };
  const data = (series.length ? series : [{ time: "0:00", wpm: fallbackWpm }]).map((d, i) => ({ time: String(d.time || `${i}:00`), wpm: Number(d.wpm || fallbackWpm || 0) }));
  const values = data.map((d) => d.wpm).filter(Number.isFinite);
  const min = Math.max(0, Math.floor((Math.min(...values, 120) - 20) / 10) * 10);
  const max = Math.max(min + 60, Math.ceil((Math.max(...values, 150) + 20) / 10) * 10);
  const plotW = w - pad.l - pad.r;
  const plotH = h - pad.t - pad.b;
  const yFor = (v) => pad.t + (1 - (v - min) / Math.max(1, max - min)) * plotH;

  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = "#344054";
  ctx.font = "13px Arial";
  ctx.textAlign = "left";
  ctx.fillText("WPM", pad.l, 18);
  const step = Math.max(10, Math.round((max - min) / 4 / 10) * 10);
  for (let t = min; t <= max; t += step) {
    const y = yFor(t);
    ctx.strokeStyle = "#e5e9f2";
    ctx.beginPath();
    ctx.moveTo(pad.l, y);
    ctx.lineTo(w - pad.r, y);
    ctx.stroke();
    ctx.fillStyle = "#667085";
    ctx.textAlign = "right";
    ctx.fillText(String(t), pad.l - 10, y + 4);
  }
  ctx.fillStyle = "rgba(37,99,235,.10)";
  ctx.fillRect(pad.l, yFor(150), plotW, Math.max(1, yFor(120) - yFor(150)));
  ctx.strokeStyle = "#2563eb";
  ctx.lineWidth = 2;
  ctx.beginPath();
  data.forEach((d, i) => {
    const x = pad.l + (i / Math.max(1, data.length - 1)) * plotW;
    const y = yFor(d.wpm);
    if (i) ctx.lineTo(x, y);
    else ctx.moveTo(x, y);
  });
  ctx.stroke();
  data.forEach((d, i) => {
    const x = pad.l + (i / Math.max(1, data.length - 1)) * plotW;
    const y = yFor(d.wpm);
    ctx.fillStyle = "#7c3aed";
    ctx.beginPath();
    ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fill();
    if (i % Math.max(1, Math.ceil(data.length / 6)) === 0 || i === data.length - 1) {
      ctx.fillStyle = "#667085";
      ctx.textAlign = "center";
      ctx.font = "11px Arial";
      ctx.fillText(d.time, x, h - 24);
    }
  });
}

function renderSummary() {
  const a = state.analysis;
  if (!a) {
    $("tabBody").innerHTML = `<section class="empty">분석 후 종합 결과가 표시됩니다.</section>`;
    return;
  }
  const problems = cleanProblems(a.problems || []);
  const priorities = cleanPriorities(a.improvement_priorities || []);
  const summaryQuestions = cleanQuestions(a.questions || []);
  const documentBlock = a.document_match?.available
    ? card("자료 간 매칭 분석", renderDocumentMatch(a.document_match), "full")
    : card("자료 간 매칭 분석", "<p class='muted'>PPT/PDF 발표자료를 함께 업로드하면 음성 전사와 자료 일치율을 비교합니다.</p>", "full");
  $("tabBody").innerHTML = `
    ${documentBlock}
    <section class="analysis-grid">
      ${card("발견된 문제점", problems.map((p) => `<div class="problem"><span class="tag">${html(p.level)}</span><b>${html(p.title)}</b><small>${html(p.fix)}</small></div>`).join("") || "<p class='muted'>문제점 없음</p>")}
      ${card("보완 사항", priorities.map((p, i) => `<div class="priority"><b>${i + 1}. ${html(p.title || p.detail)}</b><span>${html(p.impact)}</span><small>${html(p.title ? p.detail : "")}</small></div>`).join("") || "<p class='muted'>보완 사항 없음</p>")}
    </section>
    ${card("AI 예상 심사위원 질문", summaryQuestions.map((q, i) => `<div class="row"><span>${i + 1}</span><b>${html(q.category)}</b><p>${html(q.question)}</p><em>${html(q.level)}</em></div>`).join("") || "<p class='muted'>예상 질문 없음</p>", "full")}
    ${card("AI 종합 의견", `<p>${html(a.summary || "")}</p><div class="final-score"><b>${html(a.grade || "-")}</b><b>${html(a.score)}/100</b><b>${html(a.status)}</b></div>`, "full glow")}`;
}

async function downloadReport() {
  if (!ready()) {
    alert("먼저 발표를 분석해 주세요.");
    return;
  }
  const res = await fetch("/api/report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ analysis: state.analysis }),
  });
  if (!res.ok) {
    alert("리포트 생성에 실패했습니다.");
    return;
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "presentation-review-report.pdf";
  link.click();
  URL.revokeObjectURL(url);
}

function render() {
  $("homeView").classList.toggle("active", state.view === "home");
  $("demoView").classList.toggle("active", state.view === "demo");
  if (state.view === "home") renderHome();
  if (state.view === "demo") renderDemo();
}

render();
