"use strict";
const element = (id) => document.getElementById(id);
const number = (value) => value === null ? "N/A" : new Intl.NumberFormat(undefined, {maximumFractionDigits: 2}).format(value);
const rate = (value) => value === null ? "N/A" : `${number(value * 100)}%`;
function node(tag, text) {
  const item = document.createElement(tag);
  item.textContent = text;
  return item;
}
async function refresh() {
  element("refresh").disabled = true;
  element("status").textContent = "Loading local report…";
  // Clear stale success data so a failed refresh cannot look like a fresh snapshot.
  for (const id of ["summary", "mysteries", "coverage", "limitations"]) element(id).replaceChildren();
  try {
    const response = await fetch("/api/report", {cache: "no-store"});
    if (!response.ok) throw new Error("Local report unavailable. Check the database and event limit.");
    const report = await response.json();
    element("status").textContent = `${report.dataset_label} · ${report.environment} / ${report.mode} · as of ${report.as_of} · ${report.events_loaded} stored events`;
    const s = report.summary;
    const cards = [
      ["Game starts", s.game_starts], ["Question attempts", s.question_attempts],
      ["Completed question responses", s.question_responses], ["Average questions per start", s.average_question_attempts],
      ["Solve rate (mature starts)", rate(s.solve_rate)], ["Reveal rate (mature starts)", rate(s.reveal_rate)],
      ["Average hints per start", s.average_hints_delivered], ["Mature starts / rate denominator", s.mature_games],
      ["Unresolved games (not confirmed active)", s.unresolved_games], ["Unclassified games", s.unclassified_games],
    ];
    for (const [label, value] of cards) {
      const card = node("article", "");
      card.append(node("strong", typeof value === "string" ? value : number(value)), node("p", label));
      element("summary").append(card);
    }
    for (const m of report.mysteries) {
      const row = document.createElement("tr");
      for (const value of [`${m.mystery_id} / ${m.content_revision || "unversioned"}`, number(m.game_starts), number(m.mature_games), number(m.question_attempts), number(m.average_question_attempts), rate(m.solve_rate), rate(m.reveal_rate), number(m.average_hints_delivered), m.low_sample ? "Low sample" : "20+ mature starts"]) row.append(node("td", value));
      element("mysteries").append(row);
    }
    if (!report.mysteries.length) {
      const row = document.createElement("tr"); const cell = node("td", "No matching games. Rates and averages are N/A.");
      cell.colSpan = 9; row.append(cell); element("mysteries").append(row);
    }
    for (const [key, value] of Object.entries(report.coverage)) {
      element("coverage").append(node("dt", key.replaceAll("_", " ")), node("dd", number(value)));
    }
    for (const text of report.limitations) element("limitations").append(node("li", text));
  } catch (error) {
    element("status").textContent = error.message;
  } finally {
    element("refresh").disabled = false;
  }
}
element("refresh").addEventListener("click", refresh);
refresh();
