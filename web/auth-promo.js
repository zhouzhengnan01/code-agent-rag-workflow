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

  const slot = el("div", "promo-ticket-slot");
  const stage = el("div", "promo-ticket-stage");
  stage.tabIndex = 0;
  stage.setAttribute("aria-label", "Codezzn Agent Studio event pass");
  const tilt = el("div", "promo-ticket-tilt");
  const ticket = el("div", "promo-ticket");

  const glowStack = (back = false) => {
    const glow = el("div", `ticket-glow-stack${back ? " ticket-glow-stack--back" : ""}`);
    glow.setAttribute("aria-hidden", "true");
    for (let index = 0; index < 9; index += 1) glow.append(el("span"));
    return glow;
  };
  const detail = (...items) => {
    const row = el("div", "ticket-detail");
    items.forEach((item) => row.append(el("span", "", item)));
    return row;
  };
  const makeFace = (side) => {
    const front = side === "front";
    const face = el("div", `ticket-face ticket-face--${side}`);
    face.append(el("div", "ticket-band", front ? "AGENT STUDIO" : "LOCAL FIRST"));
    const watermark = el("img", "ticket-watermark");
    watermark.src = "/assets/codezzn-mark.svg?v=1";
    watermark.alt = "";
    watermark.setAttribute("aria-hidden", "true");
    face.append(watermark);
    if (front) face.append(el("div", "ticket-holo"));
    face.append(el("div", "ticket-sheen"), el("div", "ticket-pointer-light"));

    const content = el("div", "ticket-content");
    const stamp = el("div", "ticket-stamp");
    stamp.append(el("span", "", front ? "CODEZZN PRESENTS" : "YOUR WORKSPACE"));
    stamp.append(el("span", "", front ? "BUILD / 2026" : "PASS / 001"));
    content.append(stamp);
    content.append(el("strong", "ticket-title", front ? "AGENT\nSTUDIO" : "MAKE\nIT WORK"));
    if (front) {
      content.append(detail("Design, connect and run capable AI agents from one local workspace."));
      content.append(detail("ALWAYS ON", "LOCAL WORKSPACE"));
      content.append(detail("ADMIT ONE"));
    } else {
      content.append(detail("01 MODELS", "02 TOOLS"));
      content.append(detail("03 MEMORY", "04 FLOWS"));
      content.append(detail("ALL ACCESS"));
    }
    const last = detail("ALWAYS ON", "LOCAL WORKSPACE");
    last.classList.add("ticket-detail--last");
    content.append(last, el("div", "ticket-spacer"));
    const barcodeWrap = el("div", "ticket-barcode-wrap");
    const barcode = el("div", "ticket-barcode");
    barcode.setAttribute("aria-hidden", "true");
    const barcodeScan = el("div", "ticket-barcode-scan");
    barcodeScan.setAttribute("aria-hidden", "true");
    barcodeWrap.append(barcode, barcodeScan);
    content.append(barcodeWrap, el("div", "ticket-perforation"));
    content.append(el("div", "ticket-tagline", front ? "CODEZZN PRESENTS" : "YOUR WORKSPACE"));
    content.append(el("div", "ticket-legal", front ? "AGENT STUDIO BUILD / 2026" : "LOCAL FIRST PASS / 001"));
    face.append(content);
    return face;
  };

  ticket.append(glowStack(), makeFace("front"), glowStack(true), makeFace("back"));
  tilt.append(ticket);
  stage.append(tilt);
  slot.append(stage);

  const copy = el("div", "auth-promo__copy");
  copy.append(el("p", "auth-promo__eyebrow", "CODEZZN PRESENTS"));
  copy.append(el("h1", "auth-promo__title", "Build agents that work."));
  copy.append(el("p", "auth-promo__meta", "Models, tools, knowledge and workflows — one local workspace."));
  const cta = el("a", "auth-promo__cta", "Open Workbench →");
  cta.href = "/workbench.html";
  copy.append(cta);

  const motionToggle = el("button", "auth-promo__motion");
  motionToggle.type = "button";
  const motionLabel = el("span", "auth-promo__motion-label");
  motionToggle.append(motionLabel);
  promo.append(video, scrim, slot, copy, motionToggle);
  mount.replaceChildren(promo);

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let paused = reducedMotion.matches;
  let frame = 0;
  let targetX = 0;
  let targetY = 0;
  let currentX = 0;
  let currentY = 0;
  let dragStartX = 0;
  let dragAngle = 0;
  let currentDragAngle = 0;
  let dragBase = 0;
  let dragging = false;

  const animateTilt = () => {
    currentX += (targetX - currentX) * 0.14;
    currentY += (targetY - currentY) * 0.14;
    currentDragAngle += (dragAngle - currentDragAngle) * 0.14;
    tilt.style.transform = `rotateX(${currentX}deg) rotateY(${currentY + currentDragAngle}deg)`;
    if (Math.abs(targetX - currentX) + Math.abs(targetY - currentY) + Math.abs(dragAngle - currentDragAngle) > 0.02 || dragging) {
      frame = requestAnimationFrame(animateTilt);
    } else {
      frame = 0;
    }
  };
  const scheduleTilt = () => {
    if (!frame && !paused) frame = requestAnimationFrame(animateTilt);
  };
  const resetTilt = () => {
    if (dragging) return;
    stage.removeAttribute("data-pointer");
    targetX = 0;
    targetY = 0;
    dragAngle = 0;
    scheduleTilt();
  };

  stage.addEventListener("pointermove", (event) => {
    if (paused) return;
    const rect = stage.getBoundingClientRect();
    const x = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    const y = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height));
    stage.style.setProperty("--vis-px", `${x * 100}%`);
    stage.style.setProperty("--vis-py", `${y * 100}%`);
    stage.setAttribute("data-pointer", "true");
    targetX = -18 * (y - 0.5);
    targetY = 26 * (x - 0.5);
    if (dragging) dragAngle = dragBase + 0.6 * (event.clientX - dragStartX);
    scheduleTilt();
  });
  stage.addEventListener("pointerdown", (event) => {
    if (paused || (event.pointerType === "mouse" && event.button !== 0)) return;
    dragging = true;
    dragStartX = event.clientX;
    dragBase = currentDragAngle;
    stage.setPointerCapture(event.pointerId);
    scheduleTilt();
  });
  const pointerUp = (event) => {
    dragging = false;
    if (stage.hasPointerCapture(event.pointerId)) stage.releasePointerCapture(event.pointerId);
    resetTilt();
  };
  stage.addEventListener("pointerup", pointerUp);
  stage.addEventListener("pointercancel", pointerUp);
  stage.addEventListener("pointerleave", resetTilt);
  stage.addEventListener("blur", resetTilt);

  const syncMotion = () => {
    promo.classList.toggle("is-paused", paused);
    motionToggle.setAttribute("aria-pressed", String(paused));
    motionLabel.textContent = paused ? "Play Animations" : "Pause Animations";
    motionToggle.setAttribute("aria-label", motionLabel.textContent);
    if (paused) {
      video.pause();
      if (frame) cancelAnimationFrame(frame);
      frame = 0;
    } else {
      const play = video.play();
      if (play && typeof play.catch === "function") play.catch(() => {});
    }
  };
  motionToggle.addEventListener("click", () => { paused = !paused; syncMotion(); });
  reducedMotion.addEventListener("change", (event) => { paused = event.matches; syncMotion(); });
  window.addEventListener("pagehide", () => { if (frame) cancelAnimationFrame(frame); video.pause(); }, { once: true });
  syncMotion();
})();
