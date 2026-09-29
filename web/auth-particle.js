(() => {
  "use strict";

  const pane = document.querySelector(".auth-pane--particle");
  const canvas = document.getElementById("authParticleField");
  const context = canvas?.getContext("2d", { alpha: true });
  if (!pane || !canvas || !context) return;

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const promoMount = document.getElementById("authPromo");
  const saveData = Boolean(navigator.connection?.saveData);
  const isLowCore = (navigator.hardwareConcurrency || 8) <= 4;
  const baseCount = saveData || isLowCore ? 900 : 1450;
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));
  const colors = [
    [210, 210, 216],
    [162, 162, 173],
    [229, 229, 234],
    [178, 168, 190],
    [194, 154, 246],
  ];

  let width = 0;
  let height = 0;
  let dpr = 1;
  let radius = 0;
  let points = [];
  let raf = 0;
  let lastFrame = 0;
  let elapsed = 0;
  let slowFrames = 0;
  let qualityLevel = 0;
  let pulse = 0;
  let pageVisible = !document.hidden;
  let canvasVisible = true;

  const pointer = {
    x: 0,
    y: 0,
    targetX: 0,
    targetY: 0,
    vx: 0,
    vy: 0,
    targetStrength: 0,
    strength: 0,
  };

  const random = (min, max) => min + Math.random() * (max - min);

  function buildPoints() {
    const count = Math.max(520, Math.floor(baseCount * (qualityLevel >= 2 ? 0.68 : 1)));
    const tailCount = Math.floor(count * 0.14);
    const shellCount = count - tailCount;
    points = new Array(count);

    for (let index = 0; index < count; index += 1) {
      let x;
      let y;
      let z;
      let tail = false;

      if (index < tailCount) {
        const along = index / Math.max(1, tailCount - 1);
        const spread = 0.035 + along * 0.105;
        tail = true;
        x = Math.sin(along * 5.4) * 0.055 + random(-spread, spread);
        y = -0.76 - along * 0.27;
        z = random(-spread, spread);
      } else {
        const shellIndex = index - tailCount;
        const normalY = 1 - ((shellIndex + 0.5) / shellCount) * 2;
        const ring = Math.sqrt(Math.max(0, 1 - normalY * normalY));
        const angle = shellIndex * goldenAngle;
        x = Math.cos(angle) * ring;
        y = normalY;
        z = Math.sin(angle) * ring;
      }

      const color = colors[Math.random() < 0.075 ? 4 : Math.floor(Math.random() * 4)];
      points[index] = {
        x,
        y,
        z,
        tail,
        phase: random(0, Math.PI * 2),
        drift: random(0.008, 0.04),
        size: random(0.48, 1.35),
        alpha: random(0.2, 0.47),
        color,
      };
    }
  }

  function resize() {
    const box = canvas.getBoundingClientRect();
    if (box.width < 1 || box.height < 1) return;

    width = box.width;
    height = box.height;
    const dprCap = qualityLevel >= 1 ? 1 : 1.5;
    dpr = Math.min(window.devicePixelRatio || 1, dprCap);
    canvas.width = Math.max(1, Math.round(width * dpr));
    canvas.height = Math.max(1, Math.round(height * dpr));
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    radius = Math.min(width * 0.31, height * 0.42, 222);
    pointer.x = Math.min(pointer.x || width * 0.5, width);
    pointer.y = Math.min(pointer.y || height * 0.5, height);
    buildPoints();
    draw(elapsed);
  }

  function draw(time) {
    if (!width || !height) return;

    context.clearRect(0, 0, width, height);
    const centerX = width * 0.5;
    const centerY = height * 0.5;
    const breathe = 1 + Math.sin(time * 0.42) * 0.012 + pulse * 0.028;
    const turn = time * 0.115;
    const sine = Math.sin(turn);
    const cosine = Math.cos(turn);
    const projected = [];

    const haze = context.createRadialGradient(centerX, centerY, radius * 0.05, centerX, centerY, radius * 1.22);
    haze.addColorStop(0, `rgba(237,237,244,${0.055 + pulse * 0.035})`);
    haze.addColorStop(0.62, "rgba(171,171,184,0.035)");
    haze.addColorStop(1, "rgba(171,171,184,0)");
    context.fillStyle = haze;
    context.fillRect(centerX - radius * 1.25, centerY - radius * 1.25, radius * 2.5, radius * 2.5);

    for (const point of points) {
      const sway = Math.sin(time * 0.32 + point.phase) * point.drift;
      const worldX = point.x * breathe + sway;
      const worldZ = point.z * breathe;
      const rotatedX = worldX * cosine + worldZ * sine;
      const rotatedZ = -worldX * sine + worldZ * cosine;
      const depth = (rotatedZ + 1) * 0.5;
      const perspective = 0.9 + depth * 0.16;
      let x = centerX + rotatedX * radius * perspective;
      let y = centerY + point.y * radius * perspective;

      if (pointer.strength > 0.01) {
        const dx = x - pointer.x;
        const dy = y - pointer.y;
        const distance = Math.hypot(dx, dy);
        const reach = radius * 0.58;
        if (distance > 0.1 && distance < reach) {
          const influence = ((reach - distance) / reach) ** 2 * pointer.strength;
          const push = 18 * influence * (0.45 + depth * 0.55);
          x += (dx / distance) * push + pointer.vx * influence * 0.32;
          y += (dy / distance) * push + pointer.vy * influence * 0.32;
        }
      }

      const shimmer = 0.72 + Math.sin(time * 1.15 + point.phase) * 0.28;
      const frontLight = 0.34 + depth * 0.66;
      const tailFade = point.tail ? Math.max(0.08, 1 - Math.abs(point.y + 1) * 0.7) : 1;
      projected.push({
        x,
        y,
        depth,
        size: point.size * (0.58 + depth * 0.58),
        alpha: point.alpha * shimmer * frontLight * tailFade * (1 + pulse * 0.28),
        color: point.color,
      });
    }

    projected.sort((left, right) => left.depth - right.depth);
    for (const point of projected) {
      const [red, green, blue] = point.color;
      context.beginPath();
      context.arc(point.x, point.y, point.size, 0, Math.PI * 2);
      context.fillStyle = `rgba(${red},${green},${blue},${point.alpha})`;
      context.fill();
    }

    if (pointer.strength > 0.015) {
      const glow = context.createRadialGradient(pointer.x, pointer.y, 0, pointer.x, pointer.y, radius * 0.62);
      glow.addColorStop(0, `rgba(194,154,246,${pointer.strength * 0.13})`);
      glow.addColorStop(1, "rgba(194,154,246,0)");
      context.fillStyle = glow;
      context.fillRect(pointer.x - radius * 0.62, pointer.y - radius * 0.62, radius * 1.24, radius * 1.24);
    }
  }

  function isPaused() {
    const promo = promoMount?.querySelector(".auth-promo");
    return !pageVisible || !canvasVisible || reducedMotion.matches || promo?.classList.contains("is-paused");
  }

  function stop() {
    if (raf) cancelAnimationFrame(raf);
    raf = 0;
  }

  function schedule() {
    if (!raf && !isPaused()) raf = requestAnimationFrame(tick);
  }

  function degrade() {
    if (qualityLevel >= 2) return;
    qualityLevel += 1;
    if (qualityLevel === 1) {
      resize();
    } else {
      buildPoints();
    }
  }

  function tick(now) {
    raf = 0;
    if (isPaused()) return;

    const delta = lastFrame ? Math.min((now - lastFrame) / 1000, 0.05) : 1 / 60;
    lastFrame = now;
    elapsed += delta;
    pulse = Math.max(0, pulse - delta * 0.72);
    pointer.x += (pointer.targetX - pointer.x) * 0.18;
    pointer.y += (pointer.targetY - pointer.y) * 0.18;
    pointer.strength += (pointer.targetStrength - pointer.strength) * 0.12;
    pointer.vx *= 0.86;
    pointer.vy *= 0.86;
    draw(elapsed);

    if (delta > 0.026) slowFrames += 1;
    else slowFrames = Math.max(0, slowFrames - 1);
    if (slowFrames >= 75) {
      slowFrames = 0;
      degrade();
    }
    schedule();
  }

  function updateMotion() {
    if (isPaused()) {
      stop();
      draw(elapsed);
      return;
    }
    schedule();
  }

  window.addEventListener("pointermove", (event) => {
    if (event.pointerType === "touch" || reducedMotion.matches) return;
    const rect = canvas.getBoundingClientRect();
    const inside = event.clientX >= rect.left && event.clientX <= rect.right && event.clientY >= rect.top && event.clientY <= rect.bottom;
    if (!inside) {
      pointer.targetStrength = 0;
      return;
    }
    const nextX = event.clientX - rect.left;
    const nextY = event.clientY - rect.top;
    pointer.vx += Math.max(-28, Math.min(28, nextX - pointer.targetX)) * 0.22;
    pointer.vy += Math.max(-28, Math.min(28, nextY - pointer.targetY)) * 0.22;
    pointer.targetX = nextX;
    pointer.targetY = nextY;
    pointer.targetStrength = 1;
  }, { passive: true });

  window.addEventListener("pointerleave", () => { pointer.targetStrength = 0; }, { passive: true });
  window.addEventListener("blur", () => { pointer.targetStrength = 0; });
  pane.addEventListener("focusin", () => { pulse = 1; schedule(); });
  pane.addEventListener("submit", () => { pulse = 1; schedule(); }, true);
  document.addEventListener("visibilitychange", () => {
    pageVisible = !document.hidden;
    updateMotion();
  });
  reducedMotion.addEventListener?.("change", updateMotion);
  promoMount?.addEventListener("click", (event) => {
    if (event.target.closest(".auth-promo__motion")) updateMotion();
  });

  if (typeof ResizeObserver !== "undefined") {
    new ResizeObserver(resize).observe(pane);
  } else {
    window.addEventListener("resize", resize, { passive: true });
  }

  if (typeof IntersectionObserver !== "undefined") {
    new IntersectionObserver((entries) => {
      canvasVisible = entries.some((entry) => entry.isIntersecting);
      updateMotion();
    }, { threshold: 0.01 }).observe(canvas);
  }

  const promoObserver = promoMount && new MutationObserver(updateMotion);
  promoObserver?.observe(promoMount, { childList: true, subtree: true, attributes: true, attributeFilter: ["class"] });
  window.addEventListener("pagehide", stop, { once: true });

  resize();
  if (pane.contains(document.activeElement)) pulse = 0.45;
  updateMotion();
})();
