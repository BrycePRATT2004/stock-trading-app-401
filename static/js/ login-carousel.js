(() => {
  const slides = Array.from(document.querySelectorAll('.media-slide'));
  const dots = Array.from(document.querySelectorAll('#mediaDots .dot'));

  if (!slides.length) return;

  let idx = 0;
  const intervalMs = 7000; // <-- change to 5000-10000

  function show(i) {
    slides.forEach((s, n) => s.classList.toggle('is-active', n === i));
    dots.forEach((d, n) => d.classList.toggle('is-active', n === i));
  }

  setInterval(() => {
    idx = (idx + 1) % slides.length;
    show(idx);
  }, intervalMs);

  show(idx);
})();