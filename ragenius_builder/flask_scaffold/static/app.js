(function () {
  const mdInput = document.getElementById('content');
  const preview = document.getElementById('markdown-preview');
  if (mdInput && preview) {
    const render = () => {
      preview.innerHTML = window.marked.parse(mdInput.value || '');
    };
    mdInput.addEventListener('input', render);
    render();
  }

  const jsonFields = ['config_settings', 'config_schema'];
  jsonFields.forEach((id) => {
    const field = document.getElementById(id);
    if (!field) return;
    field.addEventListener('input', () => {
      field.setCustomValidity('');
      try {
        JSON.parse(field.value);
      } catch (err) {
        field.setCustomValidity('Must be valid JSON');
      }
    });
  });
})();
