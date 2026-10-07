// Vue Planning des Repas & Recettes (Aujourd'hui / Toute la semaine)
import { state } from "../config.js";
import { postInteract, fetchWeekMeals } from "../api.js";
import { sendInteraction } from "./chat_view.js";

const mealContainer = document.getElementById("meal-container");
const tabMealToday = document.getElementById("tab-meal-today");
const tabMealWeek = document.getElementById("tab-meal-week");

export async function fetchMealToday() {
  if (!mealContainer) return;
  mealContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted)">Chargement du repas du jour...</div>';

  try {
    const res = await postInteract("Qu'est-ce qu'on mange aujourd'hui ?");
    if (!res.ok) {
      mealContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--accent-rose)">Impossible de charger le repas.</div>';
      return;
    }

    const payload = await res.json();
    const pData = payload.data || {};
    const plan = pData.plan || pData.meal_plan || {};
    const dateStr = plan.date_str || "Aujourd'hui";
    const dayName = plan.day_name || "Ce jour";
    const lunch = plan.lunch || "Rien de planifié";
    const dinner = plan.dinner || "Rien de planifié";
    const lunchIng = pData.lunch_ingredients || [];
    const dinnerIng = pData.dinner_ingredients || [];

    function renderIngChips(list) {
      if (!list || list.length === 0) return "";
      return `
        <div class="ingredients-section">
          <div class="ingredients-title">🥕 Ingrédients nécessaires :</div>
          <div class="tags-list">
            ${list.map((ing) => `<span class="tag-chip">${ing}</span>`).join("")}
          </div>
        </div>
      `;
    }

    mealContainer.innerHTML = `
      <div class="meal-hero-card">
        <span class="meal-date-badge">${dayName} • ${dateStr}</span>
        <div class="meal-block">
          <div class="meal-time-label">Midi (Déjeuner)</div>
          <div class="meal-dish-name">${lunch}</div>
          ${renderIngChips(lunchIng)}
        </div>
        <div class="meal-block" style="margin-top:20px;">
          <div class="meal-time-label">Soir (Dîner)</div>
          <div class="meal-dish-name">${dinner}</div>
          ${renderIngChips(dinnerIng)}
        </div>
      </div>

      <div style="margin-top:20px;">
        <h3 class="section-title" style="margin-bottom:12px; font-size:1rem;">Questions rapides</h3>
        <div style="display:flex; flex-direction:column; gap:8px;">
          <button class="chip-btn" style="text-align:left; padding:10px 14px;" data-query="Qu'est-ce qu'on mange demain soir ?">
            🌙 Qu'est-ce qu'on mange demain soir ?
          </button>
          <button class="chip-btn" style="text-align:left; padding:10px 14px;" data-query="Quels sont les ingrédients pour la quiche lorraine ?">
            📖 Ingrédients pour la quiche lorraine
          </button>
        </div>
      </div>
    `;

    mealContainer.querySelectorAll(".chip-btn").forEach((chip) => {
      chip.addEventListener("click", () => {
        const q = chip.getAttribute("data-query");
        document.querySelector('.nav-item[data-view="chat"]').click();
        sendInteraction(q);
      });
    });
  } catch (err) {
    mealContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--accent-rose)">Erreur de connexion.</div>';
  }
}

export async function fetchMealWeek() {
  if (!mealContainer) return;
  mealContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted)">Chargement du planning de la semaine...</div>';

  try {
    const data = await fetchWeekMeals();
    const weekPlan = data.week_plan || [];

    if (weekPlan.length === 0) {
      mealContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-muted)">Aucun repas trouvé pour cette semaine.</div>';
      return;
    }

    let html = '<div class="week-cards-list">';
    weekPlan.forEach((day, idx) => {
      const todayClass = day.is_today ? "today" : "";
      const todayBadge = day.is_today ? '<span class="today-tag">AUJOURD\'HUI</span>' : "";
      const hasLunchIng = day.lunch_ingredients && day.lunch_ingredients.length > 0;
      const hasDinnerIng = day.dinner_ingredients && day.dinner_ingredients.length > 0;
      const hasAnyIng = hasLunchIng || hasDinnerIng;

      html += `
        <div class="week-day-card ${todayClass}">
          <div class="week-day-header">
            <span class="week-day-title">${day.day_label}</span>
            ${todayBadge}
          </div>

          <div class="week-meals-summary">
            <div class="week-meal-line">
              <span class="meal-label-pill">Midi</span>
              <span class="week-meal-dish">${day.lunch || "—"}</span>
            </div>
            <div class="week-meal-line">
              <span class="meal-label-pill">Soir</span>
              <span class="week-meal-dish">${day.dinner || "—"}</span>
            </div>
          </div>

          ${hasAnyIng ? `
            <button class="btn-toggle-accordion" data-target="ing-panel-${idx}">
              <span>🥕 Voir les ingrédients</span>
              <svg class="accordion-chevron" viewBox="0 0 24 24" width="16" height="16">
                <path fill="currentColor" d="M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z"/>
              </svg>
            </button>
            <div class="ingredients-collapsible" id="ing-panel-${idx}" style="display:none;">
              ${hasLunchIng ? `
                <div class="accordion-sub">
                  <span class="accordion-sub-title">Midi :</span>
                  <div class="tags-list">
                    ${day.lunch_ingredients.map((ing) => `<span class="tag-chip">${ing}</span>`).join("")}
                  </div>
                </div>
              ` : ""}
              ${hasDinnerIng ? `
                <div class="accordion-sub" style="margin-top:6px;">
                  <span class="accordion-sub-title">Soir :</span>
                  <div class="tags-list">
                    ${day.dinner_ingredients.map((ing) => `<span class="tag-chip">${ing}</span>`).join("")}
                  </div>
                </div>
              ` : ""}
            </div>
          ` : ""}
        </div>
      `;
    });
    html += '</div>';

    mealContainer.innerHTML = html;

    mealContainer.querySelectorAll(".btn-toggle-accordion").forEach((btn) => {
      btn.addEventListener("click", () => {
        const targetId = btn.getAttribute("data-target");
        const targetEl = document.getElementById(targetId);
        if (targetEl) {
          const isHidden = targetEl.style.display === "none";
          targetEl.style.display = isHidden ? "block" : "none";
          btn.classList.toggle("open", isHidden);
          const labelSpan = btn.querySelector("span");
          if (labelSpan) {
            labelSpan.textContent = isHidden ? "🥕 Masquer les ingrédients" : "🥕 Voir les ingrédients";
          }
        }
      });
    });
  } catch (err) {
    mealContainer.innerHTML = '<div style="text-align:center; padding:30px; color:var(--accent-rose)">Erreur de connexion.</div>';
  }
}

export function initMealsView() {
  if (tabMealToday && tabMealWeek) {
    tabMealToday.addEventListener("click", () => {
      state.currentMealSubview = "today";
      tabMealToday.classList.add("active");
      tabMealWeek.classList.remove("active");
      fetchMealToday();
    });

    tabMealWeek.addEventListener("click", () => {
      state.currentMealSubview = "week";
      tabMealWeek.classList.add("active");
      tabMealToday.classList.remove("active");
      fetchMealWeek();
    });
  }
}
