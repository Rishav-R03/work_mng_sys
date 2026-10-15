// Toggle "start–end" vs "duration" inputs inside any entry form (works for HTMX-swapped forms too).
document.addEventListener('change', (ev) => {
  if (!ev.target.matches('input[name=mode]')) return;
  const form = ev.target.closest('.entry-form');
  const range = ev.target.value === 'range';
  form.querySelector('.mode-range').classList.toggle('d-none', !range);
  form.querySelector('.mode-duration').classList.toggle('d-none', range);
});
