/**
 * landing.js — Landing page interactivity (Phase 1 slice)
 *
 * Responsibilities:
 *  - Navbar: scroll-darken, hamburger toggle, active link highlight
 *  - Vertical dot nav: track visible sections, click to scroll
 *  - Scroll-reveal: IntersectionObserver for .reveal / .reveal-group
 *  - Scroll arrow: animated down-arrow bounce
 *  - Preview KPI cards: fake animated values for the dashboard preview
 *  - prefers-reduced-motion: all animations respect this flag
 */

// ──────────────────────────────────────────────────────────────────────────────
// CONSTANTS
// ──────────────────────────────────────────────────────────────────────────────
const REDUCED_MOTION = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// ──────────────────────────────────────────────────────────────────────────────
// NAVBAR — scroll darken + hamburger
// ──────────────────────────────────────────────────────────────────────────────
function initNavbar() {
  const navbar     = document.getElementById('navbar');
  const hamburger  = document.getElementById('nav-hamburger');
  const drawer     = document.getElementById('nav-drawer');

  if (!navbar) return;

  // Darken navbar on scroll
  const onScroll = () => {
    navbar.classList.toggle('scrolled', window.scrollY > 24);
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll(); // run immediately in case page loads scrolled

  // Hamburger toggle
  if (hamburger && drawer) {
    hamburger.addEventListener('click', () => {
      const isOpen = hamburger.classList.toggle('open');
      drawer.classList.toggle('open', isOpen);
      hamburger.setAttribute('aria-expanded', String(isOpen));
      drawer.setAttribute('aria-hidden', String(!isOpen));
    });

    // Close drawer on link click
    drawer.querySelectorAll('.navbar__link').forEach(link => {
      link.addEventListener('click', () => {
        hamburger.classList.remove('open');
        drawer.classList.remove('open');
        hamburger.setAttribute('aria-expanded', 'false');
        drawer.setAttribute('aria-hidden', 'true');
      });
    });

    // Close on outside click
    document.addEventListener('click', (e) => {
      if (!navbar.contains(e.target) && !drawer.contains(e.target)) {
        hamburger.classList.remove('open');
        drawer.classList.remove('open');
      }
    });
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// SCROLL-REVEAL — IntersectionObserver
// WHY IntersectionObserver vs scroll events?
//   Scroll events fire on every pixel moved (60+ Hz), requiring debouncing and
//   getBoundingClientRect() calls which force layout reflow.
//   IntersectionObserver is asynchronous, runs off the main thread, and only
//   fires when visibility actually changes — zero jank.
// ──────────────────────────────────────────────────────────────────────────────
function initScrollReveal() {
  if (REDUCED_MOTION) {
    // Immediately make all reveal elements visible
    document.querySelectorAll('.reveal, .reveal-group').forEach(el => {
      el.classList.add('is-visible');
    });
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target); // fire once only
        }
      });
    },
    {
      rootMargin: '-60px 0px',  // trigger 60px before entering viewport
      threshold: 0.1
    }
  );

  document.querySelectorAll('.reveal, .reveal-group').forEach(el => {
    observer.observe(el);
  });
}

// ──────────────────────────────────────────────────────────────────────────────
// VERTICAL DOT NAV
// ──────────────────────────────────────────────────────────────────────────────
function initDotNav() {
  const dotNav   = document.getElementById('dot-nav');
  const sections = document.querySelectorAll('[data-section]');

  if (!dotNav || !sections.length) return;

  // Build dots dynamically from data-section attributes
  dotNav.innerHTML = '';
  sections.forEach((sec, i) => {
    const dot = document.createElement('button');
    dot.className = 'dot-nav__dot';
    dot.setAttribute('aria-label', `Go to ${sec.dataset.section}`);
    dot.setAttribute('title', sec.dataset.section);
    dot.addEventListener('click', () => {
      sec.scrollIntoView({ behavior: REDUCED_MOTION ? 'auto' : 'smooth' });
    });
    dotNav.appendChild(dot);
  });

  const dots = dotNav.querySelectorAll('.dot-nav__dot');

  // Track which section is most visible
  const sectionObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach(entry => {
        const idx = [...sections].indexOf(entry.target);
        if (idx === -1) return;
        dots[idx].classList.toggle('active', entry.isIntersecting);
      });
    },
    { threshold: 0.5 }
  );

  sections.forEach(sec => sectionObserver.observe(sec));
}

// ──────────────────────────────────────────────────────────────────────────────
// PREVIEW KPI ANIMATION (dashboard preview section)
// Animates mock values to make the landing page feel live
// ──────────────────────────────────────────────────────────────────────────────
function initPreviewKPIs() {
  const els = {
    speed:   document.getElementById('preview-speed'),
    rpm:     document.getElementById('preview-rpm'),
    throttle:document.getElementById('preview-throttle'),
    tireWear:document.getElementById('preview-tirewear'),
    speedBar:    document.getElementById('preview-speed-bar'),
    rpmBar:      document.getElementById('preview-rpm-bar'),
    throttleBar: document.getElementById('preview-throttle-bar'),
    tireWearBar: document.getElementById('preview-tirewear-bar'),
  };

  if (!els.speed || REDUCED_MOTION) return;

  let speed    = 287;
  let rpm      = 11850;
  let throttle = 98;
  let tireWear = 41;

  function tick() {
    // Drift values in a realistic range
    speed    = clamp(speed    + (Math.random() - 0.5) * 10, 180, 320);
    rpm      = clamp(rpm      + (Math.random() - 0.5) * 300, 8000, 13500);
    throttle = clamp(throttle + (Math.random() - 0.5) * 5, 0, 100);
    tireWear = clamp(tireWear + Math.random() * 0.05, 0, 100);

    if (els.speed)    els.speed.textContent    = speed.toFixed(0);
    if (els.rpm)      els.rpm.textContent      = (rpm / 1000).toFixed(1) + 'k';
    if (els.throttle) els.throttle.textContent = throttle.toFixed(0);
    if (els.tireWear) els.tireWear.textContent = tireWear.toFixed(1);

    if (els.speedBar)    els.speedBar.style.width    = `${(speed / 320) * 100}%`;
    if (els.rpmBar)      els.rpmBar.style.width      = `${(rpm / 13500) * 100}%`;
    if (els.throttleBar) els.throttleBar.style.width = `${throttle}%`;
    if (els.tireWearBar) els.tireWearBar.style.width = `${tireWear}%`;

    setTimeout(tick, 800);
  }

  tick();
}

function clamp(v, min, max) { return Math.min(max, Math.max(min, v)); }

// ──────────────────────────────────────────────────────────────────────────────
// SMOOTH SCROLL for in-page links
// ──────────────────────────────────────────────────────────────────────────────
function initSmoothScroll() {
  document.querySelectorAll('a[href^="#"]').forEach(link => {
    link.addEventListener('click', (e) => {
      const target = document.querySelector(link.getAttribute('href'));
      if (!target) return;
      e.preventDefault();
      target.scrollIntoView({ behavior: REDUCED_MOTION ? 'auto' : 'smooth' });
    });
  });
}

// ──────────────────────────────────────────────────────────────────────────────
// ARCHITECTURE SVG ANIMATION (draw-on effect for path lines)
// ──────────────────────────────────────────────────────────────────────────────
function initArchAnimation() {
  if (REDUCED_MOTION) return;

  const paths = document.querySelectorAll('.arch-path');
  paths.forEach((path, i) => {
    const len = path.getTotalLength?.() ?? 200;
    path.style.strokeDasharray  = len;
    path.style.strokeDashoffset = len;
    path.style.transition = `stroke-dashoffset 0.8s ${i * 0.2}s ease-out`;
  });

  const archSection = document.querySelector('.arch-diagram');
  if (!archSection) return;

  const obs = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting) {
      paths.forEach(p => { p.style.strokeDashoffset = '0'; });
      obs.disconnect();
    }
  }, { threshold: 0.3 });

  obs.observe(archSection);
}

// ──────────────────────────────────────────────────────────────────────────────
// BOOT
// ──────────────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initNavbar();
  initScrollReveal();
  initDotNav();
  initPreviewKPIs();
  initSmoothScroll();
  initArchAnimation();
});
