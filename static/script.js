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

const animateLeaderboard = () => {
  const cards = [...document.querySelectorAll("[data-leaderboard] .leaderboard-card")];
  if (!cards.length) return;

  cards
    .sort((a, b) => Number(a.dataset.rank) - Number(b.dataset.rank))
    .forEach((card) => {
      card.style.order = card.dataset.rank;
    });

  window.setInterval(() => {
    cards.forEach((card, index) => {
      window.setTimeout(() => {
        card.classList.add("refreshing");
        window.setTimeout(() => card.classList.remove("refreshing"), 820);
      }, index * 120);
    });
  }, 7000);
};

document.addEventListener("DOMContentLoaded", () => {
  createParticles();
  attachRipple();
  animateLeaderboard();
});

window.addEventListener("resize", createParticles);
