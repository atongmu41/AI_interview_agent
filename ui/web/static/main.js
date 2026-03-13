const $ = (id) => document.getElementById(id);

// 简单的前端对话历史，用于传给 /api/interview_step（无服务器 session）
const chatHistory = []; // { role: "面试官"|"候选人"|"系统", text: string }
let interviewState = "question"; // 首轮视为 QUESTION，之后为 FOLLOWUP

function appendBubble(role, text) {
  const win = $("chat-window");
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  div.textContent = text;
  win.appendChild(div);
  win.scrollTop = win.scrollHeight;
}

let timerInterval = null;
let seconds = 0;

function startTimer() {
  if (timerInterval) return;
  timerInterval = setInterval(() => {
    seconds += 1;
    const m = String(Math.floor(seconds / 60)).padStart(2, "0");
    const s = String(seconds % 60).padStart(2, "0");
    $("timer-display").textContent = `${m}:${s}`;
  }, 1000);
}

function resetTimer() {
  clearInterval(timerInterval);
  timerInterval = null;
  seconds = 0;
  $("timer-display").textContent = "00:00";
}

function stopTimer() {
  resetTimer();
}

async function handleUpload(e) {
  e.preventDefault();
  const fileInput = $("pdf-file");
  if (!fileInput.files.length) {
    alert("请先选择一个 PDF 简历文件。");
    return;
  }
  const file = fileInput.files[0];
  const role = $("role").value;
  const roleCustom = $("role-custom").value.trim();
  const difficulty = $("difficulty").value;

  const formData = new FormData();
  formData.append("file", file);
  formData.append("role", role);
  formData.append("difficulty", difficulty);
  if (roleCustom) {
    formData.append("role_custom", roleCustom);
  }

  $("resume-preview-content").textContent = "正在解析简历，请稍候...";

  try {
    const res = await fetch("/api/upload_resume", {
      method: "POST",
      body: formData,
    });
    const data = await res.json();
    if (!res.ok || data.error) {
      $("resume-preview-content").textContent = `解析失败: ${data.error || res.statusText}`;
      return;
    }

    const { resume, skills, questions, job_profile: jobProfile } = data;
    const lines = [];
    lines.push(`姓名: ${resume.name || "（未知）"}`);
    lines.push(`邮箱: ${resume.email || "（无）"}`);
    lines.push(`电话: ${resume.phone || "（无）"}`);
    lines.push("");
    lines.push("教育背景（部分）:");
    (resume.education || []).slice(0, 5).forEach((e) => lines.push(`- ${e}`));
    lines.push("");
    lines.push("技能栈:");
    (skills.skills || []).forEach((s) => lines.push(`- ${s}`));
    lines.push("");
    lines.push("匹配问题:");
    (questions || []).forEach((q, i) => {
      lines.push(`${i + 1}. ${q.title || q.prompt} [${(q.tags || []).join(", ")}]`);
    });
    $("resume-preview-content").textContent = lines.join("\n");

    // 岗位要求画像展示
    const jp = jobProfile || "暂无岗位要求信息。";
    $("job-profile-content").textContent = jp;

    const intro =
      "我已经阅读了你的简历，并为你准备了一些个性化问题。你可以先做一个简单的自我介绍。";
    appendBubble("ai", intro);
    chatHistory.length = 0;
    chatHistory.push({ role: "系统", text: "已完成简历解析与问题匹配（前端摘要）。" });
    chatHistory.push({ role: "面试官", text: intro });
    interviewState = "question";
    $("evaluation-report").className = "evaluation-report-placeholder";
    $("evaluation-report").textContent = "暂无评估结果。";
    startTimer();
  } catch (err) {
    console.error(err);
    $("resume-preview-content").textContent = `解析出错: ${err}`;
  }
}

async function handleSend() {
  const input = $("chat-input");
  const text = input.value.trim();
  if (!text) return;
  appendBubble("user", text);
  chatHistory.push({ role: "候选人", text });
  input.value = "";
  try {
    const payload = {
      state: interviewState,
      history: chatHistory,
      candidate_latest: text,
    };
    const res = await fetch("/api/interview_step", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    const reply = data.reply || "（暂无回复）";
    const tag = data.tag || "";
    appendBubble("ai", reply);
    chatHistory.push({ role: "面试官", text: reply });
    interviewState = "followup";

    if (tag.includes("结束面试")) {
      await requestEvaluationAndShowReport("面试流程已结束，已生成评估报告。");
    } else if (tag.includes("进入评估")) {
      await requestEvaluationAndShowReport("当前题目已进入评估阶段，已生成评估报告。");
    }
  } catch (err) {
    appendBubble("system", `面试官暂时无法回复：${err}`);
  }
}

async function requestEvaluationAndShowReport(reasonText) {
  // 至少需要一条候选人发言才有评估意义
  const hasCandidate = chatHistory.some((m) => m.role === "候选人");
  if (!hasCandidate) {
    appendBubble("system", "暂无有效对话，无法生成评估。");
    return;
  }

  try {
    const payload = {
      history: chatHistory,
      role: $("role").value,
      difficulty: $("difficulty").value,
    };
    const res = await fetch("/api/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok || data.error) {
      const msg = data.error || "评估接口调用失败";
      appendBubble("system", msg);
      $("evaluation-report").className = "evaluation-report-placeholder";
      $("evaluation-report").textContent = msg;
      return;
    }
    const evaluation = data.evaluation || {};
    $("evaluation-report").className = "evaluation-report-content";
    $("evaluation-report").innerHTML = renderEvaluationReport(evaluation);
    appendBubble(
      "system",
      reasonText || "面试已终止，已生成评估报告。"
    );
    $("chat-input").disabled = true;
    $("send-btn").disabled = true;
    stopTimer();
  } catch (err) {
    const msg = `评估失败：${err}`;
    appendBubble("system", msg);
    $("evaluation-report").className = "evaluation-report-placeholder";
    $("evaluation-report").textContent = msg;
  }
}

function escapeHtml(s) {
  if (s == null || s === "") return "";
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

function formatConfidence(c) {
  if (c == null || typeof c !== "number") return "—";
  const pct = Math.round(c * 100);
  return pct + "%";
}

function renderEvaluationReport(e) {
  const score = e.overall_score != null ? e.overall_score : "—";
  const overallConf = e.overall_confidence;
  const dimensions = e.dimensions || [];
  const comment = e.overall_comment || "";
  const strengths = e.strengths || [];
  const improvements = e.improvements || [];
  const riskFlags = e.risk_flags || [];

  let html = '<div class="eval-block eval-score-block">';
  html += '<span class="eval-label">总分</span>';
  html += `<span class="eval-score-value">${escapeHtml(String(score))}</span>`;
  if (overallConf != null) {
    html += `<span class="eval-confidence">置信度：${formatConfidence(overallConf)}</span>`;
  }
  html += "</div>";

  if (dimensions.length) {
    html += '<div class="eval-block eval-dimensions">';
    html += '<div class="eval-label">维度评分</div>';
    html += '<div class="eval-dimensions-grid">';
    dimensions.forEach((d) => {
      html += '<div class="eval-dimension-cell">';
      html += `<div class="eval-dimension-name">${escapeHtml(d.name)}</div>`;
      html += `<div class="eval-dimension-score">${escapeHtml(String(d.score != null ? d.score : "—"))}</div>`;
      if (d.confidence != null) {
        html += `<div class="eval-dimension-confidence eval-confidence">置信度：${formatConfidence(d.confidence)}</div>`;
      }
      html += `<div class="eval-dimension-rationale">${escapeHtml(d.rationale || "")}</div>`;
      if (d.evidence && d.evidence.length) {
        html += '<div class="eval-dimension-evidence">';
        d.evidence.slice(0, 2).forEach((ev) => {
          html += `<div class="eval-evidence-item">${escapeHtml(ev)}</div>`;
        });
        html += "</div>";
      }
      html += "</div>";
    });
    html += "</div></div>";
  }

  if (comment) {
    html += '<div class="eval-block eval-comment">';
    html += '<div class="eval-label">综合评语</div>';
    html += `<div class="eval-comment-text">${escapeHtml(comment)}</div>`;
    html += "</div>";
  }

  if (strengths.length) {
    html += '<div class="eval-block eval-list-block">';
    html += '<div class="eval-label">亮点</div>';
    html += '<ul class="eval-list">';
    strengths.forEach((s) => {
      html += `<li>${escapeHtml(s)}</li>`;
    });
    html += "</ul></div>";
  }

  if (improvements.length) {
    html += '<div class="eval-block eval-list-block">';
    html += '<div class="eval-label">改进建议</div>';
    html += '<ul class="eval-list">';
    improvements.forEach((i) => {
      html += `<li>${escapeHtml(i)}</li>`;
    });
    html += "</ul></div>";
  }

  if (riskFlags.length) {
    html += '<div class="eval-block eval-list-block eval-risks">';
    html += '<div class="eval-label">风险提示</div>';
    html += '<ul class="eval-list">';
    riskFlags.forEach((r) => {
      html += `<li>${escapeHtml(r)}</li>`;
    });
    html += "</ul></div>";
  }

  return html;
}

function handleInterrupt() {
  appendBubble("system", "你选择了打断本轮面试（当前仅前端提示，后端控制待接入）。");
}

function handleContinue() {
  appendBubble("system", "你选择了继续面试（当前仅前端提示，后端控制待接入）。");
}

function handleTerminate() {
  requestEvaluationAndShowReport("你主动终止了面试，已生成评估报告。");
}

document.addEventListener("DOMContentLoaded", () => {
  $("resume-form").addEventListener("submit", handleUpload);
  $("send-btn").addEventListener("click", handleSend);
  $("chat-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSend();
    }
  });
  $("interrupt-btn").addEventListener("click", handleInterrupt);
  $("continue-btn").addEventListener("click", handleContinue);
  $("terminate-btn").addEventListener("click", handleTerminate);
});

