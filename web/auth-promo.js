(() => {
  "use strict";

  const mount = document.getElementById("authPromo");
  if (!mount) return;

  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  const promo = el("div", "auth-promo");
  const video = el("video", "auth-promo__video");
  video.src = "/assets/sites/app-roboflow-com-f07e3b30/login-7e93fba0/cv-reel.mp4";
  video.poster = "/assets/sites/app-roboflow-com-f07e3b30/login-7e93fba0/cv-reel-poster.jpg";
  video.muted = true;
  video.loop = true;
  video.autoplay = true;
  video.playsInline = true;
  video.setAttribute("aria-hidden", "true");

  const scrim = el("div", "auth-promo__scrim");
  scrim.setAttribute("aria-hidden", "true");

  const stage = el("div", "auth-ticket-stage");
  stage.tabIndex = 0;
  stage.setAttribute("aria-label", "Codezzn Agent Studio event pass");
  const ticket = el("div", "auth-ticket");

  const makeFace = (side) => {
    const face = el("div", `auth-ticket__face auth-ticket__face--${side}`);
    const rail = el("div", "auth-ticket__rail");
    rail.append(el("span", "auth-ticket__rail-mark", "Z"));
    rail.append(el("span", "auth-ticket__rail-text", side === "front" ? "AGENT STUDIO" : "LOCAL FIRST"));
    face.append(rail);

    const body = el("div", "auth-ticket__body");
    const top = el("div", "auth-ticket__topline");
    top.append(el("span", "auth-ticket__edition", side === "front" ? "BUILD / 2026" : "PASS / 001"));
    top.append(el("span", "auth-ticket__admit", side === "front" ? "ADMIT ONE" : "ALL ACCESS"));
    body.append(top);

    if (side === "front") {
      body.append(el("p", "auth-ticket__kicker", "CODEZZN PRESENTS"));
      body.append(el("h2", "auth-ticket__name", "AGENT\nSTUDIO"));
      body.append(el("p", "auth-ticket__summary", "Design, connect and run capable AI agents from one local workspace."));
    } else {
      body.append(el("p", "auth-ticket__kicker", "YOUR WORKSPACE"));
      body.append(el("h2", "auth-ticket__name auth-ticket__name--back", "MAKE\nIT WORK"));
      const grid = el("div", "auth-ticket__feature-grid");
      ["MODELS", "TOOLS", "MEMORY", "FLOWS"].forEach((item, index) => {
        const cell = el("div", "auth-ticket__feature");
        cell.append(el("span", "auth-ticket__feature-no", `0${index + 1}`));
        cell.append(el("span", "auth-ticket__feature-name", item));
        grid.append(cell);
      });
      body.append(grid);
    }

    const footer = el("div", "auth-ticket__footer");
    const date = el("div", "auth-ticket__date");
    date.append(el("strong", "", "ALWAYS ON"));
    date.append(el("span", "", "LOCAL WORKSPACE"));
    footer.append(date);
    const barcode = el("div", "auth-ticket__barcode");
    barcode.setAttribute("aria-hidden", "true");
    footer.append(barcode);
    body.append(footer);
    face.append(body);
    return face;
  };

  ticket.append(makeFace("front"), makeFace("back"));
  stage.append(ticket);

  const copy = el("div", "auth-promo__copy");
  copy.append(el("p", "auth-promo__eyebrow", "CODEZZN PRESENTS"));
  copy.append(el("h1", "auth-promo__title", "Build agents that work."));
  copy.append(el("p", "auth-promo__meta", "Models, tools, knowledge and workflows — one local workspace."));
  const cta = el("a", "auth-promo__cta", "Open Workbench →");
  cta.href = "/workbench.html";
  copy.append(cta);

  const motionToggle = el("button", "auth-promo__motion");
  motionToggle.type = "button";
  const motionIcon = el("span", "auth-promo__motion-icon");
  motionIcon.setAttribute("aria-hidden", "true");
  const motionLabel = el("span", "auth-promo__motion-label");
  motionToggle.append(motionIcon, motionLabel);

  promo.append(video, scrim, stage, copy, motionToggle);
  mount.replaceChildren(promo);

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let paused = reducedMotion.matches;

  const syncMotion = () => {
    promo.classList.toggle("is-paused", paused);
    motionToggle.setAttribute("aria-pressed", String(paused));
    motionLabel.textContent = paused ? "Play Animations" : "Pause Animations";
    motionToggle.setAttribute("aria-label", motionLabel.textContent);
    if (paused) {
      video.pause();
    } else {
      const play = video.play();
      if (play && typeof play.catch === "function") play.catch(() => {});
    }
  };

  motionToggle.addEventListener("click", () => {
    paused = !paused;
    syncMotion();
  });
  reducedMotion.addEventListener("change", (event) => {
    paused = event.matches;
    syncMotion();
  });
  syncMotion();
})();
