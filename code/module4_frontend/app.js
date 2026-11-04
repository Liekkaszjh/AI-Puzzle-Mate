"use strict";

const $ = (id) => document.getElementById(id);
const modeInputs = [...document.querySelectorAll('input[name="play-mode"]')];
let state = null;
let busy = false;
let phase = "idle";
let view = "lobby";
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function avatar(actor) {
  const img = element("img", "log-avatar" + (actor === "teammate" ? " ai" : ""));
  img.src = actor === "teammate" ? "/teammate.svg" : "/player.svg";
  img.alt = actor === "teammate" ? "小夏" : "你";
  return img;
}

function selectedMode() {
  return modeInputs.find((input) => input.checked).value;
}

function showView(next) {
  view = next;
  $("lobby").hidden = next !== "lobby";
  $("generation").hidden = next !== "generation";
  $("game-view").hidden = next !== "game";
  $("resume").hidden = !state || !state.puzzle;
  showError("");
}

function renderScore() {
  const report = state.report;
  $("score-again").hidden = !report;
  if (!report) return;
  $("score-value").textContent = report.score;
  $("score-summary").textContent = `完整还原 ${report.matched_count} / ${report.total_facts} 条关键事实`;
  $("score-method").textContent = state.mode === "demo" ? "演示评分：简单关键词匹配，不代表完整语义判断；接入 DeepSeek 后按语义逐条评估。" : "DeepSeek 逐条核对关键事实，程序按等权规则计算总分。";
  const statuses = {matched: "完整命中", partial: "部分命中", missing: "未提及", contradicted: "存在矛盾"};
  $("score-facts").replaceChildren(...report.facts.map((fact, index) => {
    const row = element("article", "fact-row " + fact.status);
    const head = element("div", "fact-header");
    head.append(element("strong", "", `事实 ${index + 1}`), element("span", "", `${statuses[fact.status]} · ${fact.credit} / 1`));
    row.append(head, element("p", "fact-text", fact.fact), element("p", "fact-reason", fact.reason));
    return row;
  }));
  $("submitted-answer").textContent = report.answer;
  $("score-bottom").textContent = state.solution.bottom;
}

function sceneMode() {
  return state && state.status !== "idle" ? state.play_mode : selectedMode();
}

function updateControls() {
  const playing = state && state.status === "playing";
  const capped = state && state.turns >= state.max_turns;
  const aiTurn = playing && state.next_actor === "teammate";
  for (const id of ["ask", "question"]) $(id).disabled = busy || !playing || capped || aiTurn;
  $("final").disabled = busy || !playing || aiTurn;
  $("reveal").disabled = busy || !playing;
  $("new-game").disabled = busy || !state;
  for (const id of ["existing-game", "choose-new", "generation-back", "back-lobby", "resume"]) $(id).disabled = busy || !state;
  $("submit-answer").disabled = busy;
  $("close-answer").disabled = busy;
  $("answer-input").disabled = busy;
  $("submit-answer").textContent = busy ? "正在逐条评估关键事实…" : "提交答案并评分 →";
  $("generation-progress").hidden = !busy || phase !== "new";
  $("theme").disabled = busy || !state || state.mode === "demo";
  $("new-game").disabled = busy || !state || state.mode === "demo";
  $("generation-note").textContent = state && state.mode === "demo" ? "尚未填写 DeepSeek 密钥，暂不能生成新题。请先配置 .env，或返回随机已有题目。" : "新题会包含汤面、汤底和 3～6 条关键事实，生成成功后加入已有题库。";
  for (const input of modeInputs) input.disabled = busy || !state;
  $("teammate").hidden = busy || !aiTurn;
  $("teammate").disabled = busy || !aiTurn;
  $("ask").textContent = busy ? (phase === "teammate" ? "小夏正在提问…" : "汤主正在回答…") : "向汤主提问 ↑";
  $("question").placeholder = !playing ? "开局后，在这里写下你的问题。" : aiTurn ? "这次轮到小夏，等她问完就到你。" : "是不是……？每次问一个是非问题。";
  $("input-hint").textContent = capped ? "互动已达上限，可以揭晓汤底" : "Enter 提问 · Shift + Enter 换行";
  updateScene();
}

function updateScene() {
  const coop = sceneMode() === "coop";
  $("scene").classList.toggle("solo", !coop);
  $("teammate-seat").hidden = !coop;
  $("ai-legend").hidden = !coop;
  $("table-mode").textContent = coop ? "你与 AI 的合作推理" : "一个人的安静推理";
  const playing = state && state.status === "playing";
  let speaker = playing ? state.next_actor : "host";
  let label = "先选好模式，开始一局吧";
  let description = coop ? "你问一次 → 汤主回答 → 小夏问一次 → 汤主回答" : "只有你与汤主，按自己的节奏慢慢问。";
  if (playing) {
    label = state.next_actor === "teammate" ? "轮到小夏了 · 她会接着你的线索问" : "轮到你了 · 问一个是非问题吧";
    if (state.notice) description = state.notice;
    if (state.turns >= state.max_turns) { label = "本局互动已达上限"; description = "可以揭晓汤底，或开始新的一局。"; }
  }
  if (state && state.status === "won") { label = "还原成功 · 这碗汤，你喝明白了！"; description = "完整汤底已收录在右侧对话记录下方。"; }
  if (state && state.status === "revealed") { label = "真相揭晓 · 原来是这样"; description = "在右侧查看汤底，或者再开一桌吧。"; }
  if (state && state.status === "scored") { label = `本局已交卷 · ${state.report.score} 分`; description = "点击“查看本局得分”回顾关键事实的命中情况。"; }
  if (busy) {
    speaker = phase === "teammate" ? "teammate" : "host";
    label = phase === "new" ? "汤主正在准备今天的故事…" : phase === "teammate" ? "小夏正在思考并向汤主提问…" : "汤主正在判断你的想法…";
    description = "稍等一下，当前回合结束后会自动继续。";
  }
  $("scene").dataset.speaker = speaker;
  $("turn-label").textContent = label;
  $("turn-description").textContent = description;
  $("player-caption").textContent = playing ? (speaker === "player" ? "轮到你发言" : "认真听线索中") : "故事的另一半，等你来问";
  $("teammate-caption").textContent = speaker === "teammate" ? "正在寻找新线索" : "你的推理搭子";
}

function render() {
  const demo = state.mode === "demo";
  $("mode").textContent = demo ? "演示模式" : "DeepSeek 已配置";
  $("mode-note").textContent = demo ? "演示版 · 内置题库与简单判题；填入 DeepSeek 密钥可完整体验。" : "由 DeepSeek 驱动 · 小夏只知道汤面和公开对话。";
  $("status").textContent = ({ idle: "等待入座", playing: "推理中", won: "还原成功", scored: "已评分", revealed: "已揭晓" })[state.status];
  $("status").classList.toggle("finished", ["won", "scored", "revealed"].includes(state.status));
  $("fact-count").textContent = state.puzzle ? `本题 ${state.puzzle.fact_count} 条关键事实 · 交卷后逐条评分` : "根据关键事实评分";
  $("title").textContent = state.puzzle ? state.puzzle.title : "一个故事，等你来揭晓";
  $("surface").textContent = state.puzzle ? state.puzzle.surface : "先选好你的推理方式，再点击「入座 · 开始新局」。汤主会端上一则充满反常细节的故事。";
  $("turn-count").textContent = `${state.turns} 次提问`;
  const history = $("history");
  history.replaceChildren();
  if (!state.history.length) {
    const empty = element("div", "empty");
    empty.append(element("span", "empty-illustration", "“"), element("h3", "", "好故事，从一句话开始"), element("p", "", "每一个问题与汤主的回答，\n都会按顺序记在这里。"), element("span", "empty-line"));
    history.append(empty);
  }
  for (const [index, turn] of state.history.entries()) {
    const row = element("article", "turn");
    row.dataset.actor = turn.actor;
    const heading = element("div", "turn-heading");
    heading.append(avatar(turn.actor), element("strong", "", turn.actor === "teammate" ? "小夏 · AI 队友" : "你"));
    if (turn.kind === "final") heading.append(element("span", "final-tag", "最终还原"));
    heading.append(element("span", "turn-number", `#${String(index + 1).padStart(2, "0")}`));
    row.append(heading, element("p", "question-text", turn.question));
    const answer = element("div", "host-answer");
    const host = element("img"); host.src = "/host.svg"; host.alt = "汤主老陈";
    answer.append(host, element("span", "host-label", "汤主"));
    const verdictClass = ({ "是": "yes", "不是": "no", "无关": "neutral" })[turn.verdict];
    answer.append(element("span", "verdict " + verdictClass, turn.verdict));
    if (turn.feedback) answer.append(element("span", "feedback", turn.feedback));
    row.append(answer); history.append(row);
  }
  const lastPlayer = [...state.history].reverse().find((turn) => turn.actor === "player");
  const lastAI = [...state.history].reverse().find((turn) => turn.actor === "teammate");
  const last = state.history[state.history.length - 1];
  $("player-bubble").textContent = lastPlayer ? lastPlayer.question : "让我想一想，从哪里问起呢？";
  $("teammate-bubble").textContent = state.pending_question || (lastAI ? lastAI.question : "你先问，下一个轮到我。");
  $("host-bubble").textContent = state.report ? `本局还原得分：${state.report.score} 分。来看看每条关键事实吧。` : state.status === "revealed" ? "汤底已经揭晓，原来如此吧？" : last ? `「${last.verdict}」${last.actor === "teammate" ? "小夏问完了，现在轮到你。" : state.play_mode === "coop" && last.kind === "question" ? "接下来听听小夏的问题。" : "继续问吧，我听着呢。"}` : "欢迎入座，今天也慢慢想。";
  $("solution").hidden = !state.solution;
  if (state.solution) {
    $("result-title").textContent = state.report ? `还原得分：${state.report.score} / 100` : "原来如此。";
    $("bottom").textContent = state.solution.bottom;
    $("key-points").replaceChildren(...state.solution.key_points.map((point) => element("li", "", point)));
  }
  renderScore();
  updateControls();
  history.scrollTop = history.scrollHeight;
}

function showError(message) { $("error").textContent = message; $("error").hidden = !message; }

async function post(path, data) {
  const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": state.csrf }, body: JSON.stringify(data) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "请求失败，请重试");
  state = result;
  render();
  return result;
}

async function action(path, data = {}) {
  if (busy || !state) return;
  busy = true; phase = path === "/api/new" ? "new" : path === "/api/teammate" ? "teammate" : "host";
  showError(""); updateControls();
  if (path === "/api/question" || path === "/api/final") $("player-bubble").textContent = data.text;
  if (phase === "teammate") $("teammate-bubble").textContent = state.pending_question || "我来试试另一个方向……";
  try {
    await post(path, data);
    if (path === "/api/new") { $("answer-input").value = ""; showView("game"); }
    if (path === "/api/final") { $("answer-dialog").close(); $("score-dialog").showModal(); }
    if (["/api/new", "/api/question", "/api/final"].includes(path)) $("question").value = "";
    if (state.status === "playing" && state.next_actor === "teammate" && path !== "/api/teammate") {
      // 分开请求以先展示玩家的判定，再自动进入队友回合。
      await pause(700);
      phase = "teammate"; updateControls();
      $("teammate-bubble").textContent = "我来试试另一个方向……";
      await post("/api/teammate", {});
    }
    if (state.solution) $("solution").scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (error) {
    showError(error.message || "连接失败，请检查 Python 服务。");
    if ($("answer-dialog").open) { $("answer-error").textContent = error.message; $("answer-error").hidden = false; }
    // 接口已经完成但响应丢失时，以服务端记录为准，避免重复提问。
    try {
      const response = await fetch("/api/state");
      if (response.ok) {
        state = await response.json(); render();
        if (path === "/api/final" && state.report) { $("answer-dialog").close(); if (!$("score-dialog").open) $("score-dialog").showModal(); }
      }
    } catch (_) { /* 保留当前记录与错误提示。 */ }
  } finally { busy = false; phase = "idle"; updateControls(); }
}

$("new-game").addEventListener("click", () => {
  const theme = $("theme").value.trim();
  if (!theme) return showError("请输入一个故事主题，再点击生成。");
  if (state && state.status === "playing" && !window.confirm("生成新题并开局会结束当前游戏，继续吗？")) return;
  action("/api/new", { source: "new", theme, play_mode: selectedMode() });
});
$("existing-game").addEventListener("click", () => {
  if (state && state.status === "playing" && !window.confirm("随机开局会结束当前游戏，继续吗？")) return;
  action("/api/new", {source: "existing", play_mode: selectedMode()});
});
$("choose-new").addEventListener("click", () => showView("generation"));
$("generation-back").addEventListener("click", () => showView("lobby"));
$("back-lobby").addEventListener("click", () => showView("lobby"));
$("resume").addEventListener("click", () => showView("game"));
for (const input of modeInputs) input.addEventListener("change", updateScene);
$("question-form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (busy || !state || state.status !== "playing" || state.next_actor !== "player") return;
  const text = $("question").value.trim();
  if (!text) return showError("先写一个问题吧。");
  if (text.length > 300) return showError("提问请控制在 300 字以内；完整故事请用“我来还原故事”。");
  action("/api/question", { text });
});
$("question").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing && !busy) { event.preventDefault(); $("question-form").requestSubmit(); }
});
$("final").addEventListener("click", () => {
  $("answer-rules").textContent = `本题有 ${state.puzzle.fact_count} 条关键事实。请独立写下你的还原，满分 100 分。`;
  $("answer-error").hidden = true;
  $("answer-dialog").showModal();
  $("answer-input").focus();
});
$("answer-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const text = $("answer-input").value.trim();
  if (!text) { $("answer-error").textContent = "请先写下你的故事还原。"; $("answer-error").hidden = false; return; }
  action("/api/final", {text});
});
$("close-answer").addEventListener("click", () => $("answer-dialog").close());
$("answer-dialog").addEventListener("cancel", (event) => { if (busy) event.preventDefault(); });
$("close-score").addEventListener("click", () => $("score-dialog").close());
$("score-again").addEventListener("click", () => $("score-dialog").showModal());
$("score-home").addEventListener("click", () => { $("score-dialog").close(); showView("lobby"); });
$("teammate").addEventListener("click", () => action("/api/teammate"));
$("reveal").addEventListener("click", () => { if (window.confirm("揭晓后会结束本局，确定现在查看汤底吗？")) action("/api/reveal"); });

(async () => {
  updateControls();
  try {
    const response = await fetch("/api/state");
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "连接失败");
    state = result;
    for (const input of modeInputs) input.checked = input.value === state.play_mode;
    render();
    showView(state.puzzle ? "game" : "lobby");
    // 刷新后仍由服务端记住发言顺序，恢复尚未完成的队友回合。
    if (state.status === "playing" && state.next_actor === "teammate") await action("/api/teammate");
  } catch (error) { $("mode").textContent = "连接中断"; showError(error.message + "。请确认服务已启动，然后刷新页面。"); }
})();
