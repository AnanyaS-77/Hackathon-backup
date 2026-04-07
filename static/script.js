const createParticles = () => {
  const container = document.querySelector(".particles");
  if (!container) return;

  const particleCount = window.innerWidth < 768 ? 18 : 34;
  container.innerHTML = "";

  for (let index = 0; index < particleCount; index += 1) {
    const particle = document.createElement("span");
    particle.className = "particle";
    particle.style.left = `${Math.random() * 100}%`;
    particle.style.animationDuration = `${8 + Math.random() * 10}s`;
    particle.style.animationDelay = `${Math.random() * 8}s`;
    particle.style.opacity = `${0.2 + Math.random() * 0.6}`;
    container.appendChild(particle);
  }
};

const attachRipple = () => {
  document.querySelectorAll(".ripple-target").forEach((button) => {
    button.addEventListener("click", (event) => {
      const ripple = document.createElement("span");
      const rect = button.getBoundingClientRect();
      ripple.className = "ripple";
      ripple.style.left = `${event.clientX - rect.left}px`;
      ripple.style.top = `${event.clientY - rect.top}px`;
      button.appendChild(ripple);

      window.setTimeout(() => ripple.remove(), 750);
    });
  });
};

const applyLeaderboardAnimation = (cards) => {
  cards
    .sort((a, b) => Number(a.dataset.rank) - Number(b.dataset.rank))
    .forEach((card) => {
      card.style.order = card.dataset.rank;
    });

  cards.forEach((card, index) => {
    window.setTimeout(() => {
      card.classList.add("refreshing");
      window.setTimeout(() => card.classList.remove("refreshing"), 820);
    }, index * 120);
  });
};

const leaderboardCardMarkup = (team, index) => {
  const topClass = index === 0 ? "top-gold" : index === 1 ? "top-silver" : index === 2 ? "top-bronze" : "";

  return `
    <article class="leaderboard-card glass-panel ${topClass}" data-rank="${index + 1}" style="--stagger: 0">
      <div class="leader-rank">
        <span class="rank-label">Rank</span>
        <strong>#${index + 1}</strong>
      </div>

      <div class="leader-main">
        <div class="leader-heading">
          <h2>${team.name}</h2>
          <span class="leader-chip">${team.rounds}/4 rounds</span>
        </div>

        <div class="leader-meta">
          <span>Attempts: ${team.attempts}</span>
          <span>${team.status_text}</span>
        </div>

        <div class="progress-track" aria-hidden="true">
          <div class="progress-bar" style="width: ${team.progress_percent}%"></div>
        </div>
      </div>

      <div class="leader-score">
        <span class="score-label">Progress</span>
        <strong>${team.progress_percent}%</strong>
      </div>
    </article>
  `;
};

const refreshLeaderboard = async () => {
  const shell = document.querySelector("[data-leaderboard-endpoint]");
  const list = document.querySelector("[data-leaderboard]");
  const status = document.querySelector("[data-refresh-status]");
  const refreshButton = document.querySelector("[data-refresh-now]");
  if (!shell || !list) return;

  const endpoint = shell.dataset.leaderboardEndpoint;
  if (!endpoint) return;

  try {
    if (refreshButton) {
      refreshButton.disabled = true;
      refreshButton.textContent = "Refreshing...";
    }

    const response = await window.fetch(endpoint, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });

    if (!response.ok) {
      throw new Error(`Refresh failed with status ${response.status}`);
    }

    const payload = await response.json();
    const board = Array.isArray(payload.leaderboard) ? payload.leaderboard : [];

    list.innerHTML = board.map((team, index) => leaderboardCardMarkup(team, index)).join("");
    applyLeaderboardAnimation([...list.querySelectorAll(".leaderboard-card")]);

    if (status) {
      status.textContent = `Leaderboard updated at ${new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })}.`;
    }
  } catch (error) {
    if (status) {
      status.textContent = "Leaderboard refresh failed. Retrying automatically.";
    }
  } finally {
    if (refreshButton) {
      refreshButton.disabled = false;
      refreshButton.textContent = "Refresh Now";
    }
  }
};

const animateLeaderboard = () => {
  const cards = [...document.querySelectorAll("[data-leaderboard] .leaderboard-card")];
  const refreshButton = document.querySelector("[data-refresh-now]");
  if (!cards.length) return;

  applyLeaderboardAnimation(cards);

  if (refreshButton) {
    refreshButton.addEventListener("click", () => {
      refreshLeaderboard();
    });
  }

  window.setInterval(refreshLeaderboard, 10000);
};

document.addEventListener("DOMContentLoaded", () => {
  createParticles();
  attachRipple();
  animateLeaderboard();
});

window.addEventListener("resize", createParticles);
