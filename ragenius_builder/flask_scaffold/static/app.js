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

  const settingsField = document.getElementById('config_settings');
  const schemaField = document.getElementById('config_schema');
  const settingsBody = document.getElementById('settings-list-body');
  const settingsEmpty = document.getElementById('settings-list-empty');
  const rawSettings = document.getElementById('config_settings_raw');
  const llmInputs = Array.from(document.querySelectorAll('[data-llm-path]'));

  const parseJson = (value, fallback) => {
    try {
      return JSON.parse(value);
    } catch (err) {
      return fallback;
    }
  };

  if (settingsField && schemaField && settingsBody) {
    let currentSettings = parseJson(settingsField.value || '{}', {});
    let baseDefaults = JSON.parse(JSON.stringify(currentSettings || {}));

    const hasNested = (obj, path) => {
      let cursor = obj;
      for (let i = 0; i < path.length; i += 1) {
        const key = path[i];
        if (!cursor || typeof cursor !== 'object' || !Object.prototype.hasOwnProperty.call(cursor, key)) {
          return false;
        }
        cursor = cursor[key];
      }
      return true;
    };

    const getNested = (obj, path, fallback = undefined) => {
      let cursor = obj;
      for (let i = 0; i < path.length; i += 1) {
        const key = path[i];
        if (!cursor || typeof cursor !== 'object' || !Object.prototype.hasOwnProperty.call(cursor, key)) {
          return fallback;
        }
        cursor = cursor[key];
      }
      return cursor;
    };

    const setNested = (obj, path, value) => {
      let cursor = obj;
      for (let i = 0; i < path.length - 1; i += 1) {
        const key = path[i];
        if (!cursor[key] || typeof cursor[key] !== 'object' || Array.isArray(cursor[key])) {
          cursor[key] = {};
        }
        cursor = cursor[key];
      }
      cursor[path[path.length - 1]] = value;
    };

    const collectLeafSpecs = (properties, prefix = []) => {
      const rows = [];
      Object.entries(properties || {}).forEach(([key, spec]) => {
        const path = [...prefix, key];
        if (path.length === 1 && path[0] === 'llm') {
          return;
        }
        const specObj = spec || {};
        const type = specObj.type || (specObj.enum ? 'string' : 'unknown');
        const hasChildProps = type === 'object'
          && specObj.properties
          && typeof specObj.properties === 'object'
          && Object.keys(specObj.properties).length > 0;
        if (hasChildProps) {
          rows.push(...collectLeafSpecs(specObj.properties, path));
        } else {
          rows.push({ path, spec: specObj });
        }
      });
      return rows;
    };

    const coerceInputValue = (input) => {
      const raw = input.value;
      if (input.type === 'number') {
        if (raw === '') return '';
        const parsed = parseFloat(raw);
        return Number.isNaN(parsed) ? '' : parsed;
      }
      return raw;
    };

    const syncSettingsJson = () => {
      settingsField.value = JSON.stringify(currentSettings, null, 2);
      if (rawSettings) rawSettings.value = settingsField.value;
    };

    const syncLlmInputsFromSettings = () => {
      llmInputs.forEach((input) => {
        const path = String(input.dataset.llmPath || '').split('.').filter(Boolean);
        if (path.length === 0) return;
        const defaultValue = input.dataset.defaultValue ?? '';
        if (!hasNested(currentSettings, path) && defaultValue !== '') {
          if (input.type === 'number') {
            const parsedDefault = parseFloat(defaultValue);
            setNested(currentSettings, path, Number.isNaN(parsedDefault) ? '' : parsedDefault);
          } else {
            setNested(currentSettings, path, defaultValue);
          }
        }
        const nextValue = hasNested(currentSettings, path) ? getNested(currentSettings, path) : defaultValue;
        if (input.type === 'number') {
          input.value = nextValue === null || nextValue === undefined ? '' : String(nextValue);
          return;
        }
        input.value = nextValue === null || nextValue === undefined ? '' : String(nextValue);
      });
    };

    const bindLlmInputs = () => {
      llmInputs.forEach((input) => {
        const path = String(input.dataset.llmPath || '').split('.').filter(Boolean);
        if (path.length === 0) return;
        const apply = () => {
          setNested(currentSettings, path, coerceInputValue(input));
          syncSettingsJson();
        };
        input.addEventListener('input', apply);
        if (input.tagName === 'SELECT') {
          input.addEventListener('change', apply);
        }
      });
      syncLlmInputsFromSettings();
    };

    const renderSettingRow = (path, spec) => {
      const key = path.join('.');
      const type = spec.type || (spec.enum ? 'string' : 'unknown');
      const hasSchemaDefault = Object.prototype.hasOwnProperty.call(spec, 'default');
      const hasStoredDefault = hasNested(baseDefaults, path);
      const defaultValue = hasSchemaDefault
        ? spec.default
        : (hasStoredDefault ? getNested(baseDefaults, path) : '');
      if (!hasNested(currentSettings, path) && defaultValue !== '') {
        setNested(currentSettings, path, defaultValue);
      }
      const currentValue = hasNested(currentSettings, path)
        ? getNested(currentSettings, path)
        : defaultValue;

      const row = document.createElement('tr');
      row.className = 'border-t border-gray-100';

      const nameCell = document.createElement('td');
      nameCell.className = 'px-3 py-2 font-medium text-gray-900';
      nameCell.textContent = key;

      const typeCell = document.createElement('td');
      typeCell.className = 'px-3 py-2 text-gray-700';
      typeCell.textContent = type;

      const defaultCell = document.createElement('td');
      defaultCell.className = 'px-3 py-2 text-gray-600';
      defaultCell.textContent = defaultValue === '' ? '-' : JSON.stringify(defaultValue);

      const valueCell = document.createElement('td');
      valueCell.className = 'px-3 py-2';

      const onValueChange = (nextValue) => {
        setNested(currentSettings, path, nextValue);
        syncSettingsJson();
      };

      let input;
      if (Array.isArray(spec.enum) && spec.enum.length > 0) {
        input = document.createElement('select');
        input.className = 'w-full rounded border-gray-300 focus:border-blue-600';
        spec.enum.forEach((choice) => {
          const option = document.createElement('option');
          option.value = String(choice);
          option.textContent = String(choice);
          option.selected = String(currentValue) === String(choice);
          input.appendChild(option);
        });
        input.addEventListener('change', () => onValueChange(input.value));
      } else if (type === 'boolean') {
        input = document.createElement('input');
        input.type = 'checkbox';
        input.className = 'h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500';
        input.checked = Boolean(currentValue);
        input.addEventListener('change', () => onValueChange(input.checked));
      } else if (type === 'integer' || type === 'number') {
        input = document.createElement('input');
        input.type = 'number';
        if (typeof spec.minimum === 'number') input.min = String(spec.minimum);
        if (typeof spec.maximum === 'number') input.max = String(spec.maximum);
        input.step = type === 'integer' ? '1' : 'any';
        input.value = currentValue === '' || currentValue === null || currentValue === undefined ? '' : String(currentValue);
        input.className = 'w-full rounded border-gray-300 focus:border-blue-600';
        input.addEventListener('input', () => {
          if (input.value === '') {
            onValueChange('');
            return;
          }
          const parsed = type === 'integer' ? parseInt(input.value, 10) : parseFloat(input.value);
          onValueChange(Number.isNaN(parsed) ? '' : parsed);
        });
      } else if (type === 'object' || type === 'array') {
        input = document.createElement('textarea');
        input.rows = 3;
        input.className = 'w-full rounded border-gray-300 focus:border-blue-600 whitespace-pre-wrap break-all resize-y';
        input.value = currentValue === '' ? '' : JSON.stringify(currentValue);
        input.addEventListener('input', () => {
          try {
            onValueChange(JSON.parse(input.value || (type === 'array' ? '[]' : '{}')));
            input.setCustomValidity('');
          } catch (err) {
            input.setCustomValidity('Must be valid JSON');
          }
        });
      } else {
        input = document.createElement('textarea');
        const textValue = currentValue === null || currentValue === undefined ? '' : String(currentValue);
        input.rows = textValue.length > 120 ? 4 : (textValue.length > 48 ? 2 : 1);
        input.className = 'w-full rounded border-gray-300 focus:border-blue-600 whitespace-pre-wrap break-all resize-y';
        input.value = textValue;
        input.addEventListener('input', () => onValueChange(input.value));
      }

      valueCell.appendChild(input);
      row.appendChild(nameCell);
      row.appendChild(typeCell);
      row.appendChild(defaultCell);
      row.appendChild(valueCell);
      settingsBody.appendChild(row);
    };

    const renderSettingsList = () => {
      const schema = parseJson(schemaField.value || '{}', {});
      const properties = schema.properties || {};
      settingsBody.innerHTML = '';
      const leaves = collectLeafSpecs(properties);
      if (leaves.length === 0) {
        settingsEmpty?.classList.remove('hidden');
        syncLlmInputsFromSettings();
        syncSettingsJson();
        return;
      }
      settingsEmpty?.classList.add('hidden');
      leaves.forEach((entry) => renderSettingRow(entry.path, entry.spec));
      syncLlmInputsFromSettings();
      syncSettingsJson();
    };

    schemaField.addEventListener('input', renderSettingsList);
    if (rawSettings) {
      rawSettings.addEventListener('input', () => {
        const parsed = parseJson(rawSettings.value, null);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          currentSettings = parsed;
          baseDefaults = JSON.parse(JSON.stringify(parsed));
          rawSettings.setCustomValidity('');
          renderSettingsList();
        } else {
          rawSettings.setCustomValidity('Must be valid JSON object');
        }
      });
    }

    bindLlmInputs();
    renderSettingsList();
  }

  const filesInput = document.getElementById('files');
  const filesBody = document.getElementById('selected-files-body');
  const filesPanel = document.getElementById('selected-files-panel');
  const filesEmpty = document.getElementById('selected-files-empty');
  const filenameField = document.getElementById('filename');
  const mimeTypeField = document.getElementById('mime_type');
  const sizeBytesField = document.getElementById('size_bytes');

  if (filesInput && filesBody && filesPanel && filesEmpty) {
    const renderSelectedFiles = () => {
      filesBody.innerHTML = '';
      const selected = Array.from(filesInput.files || []);
      if (selected.length === 0) {
        filesPanel.classList.add('hidden');
        filesEmpty.classList.remove('hidden');
        if (filenameField) filenameField.value = '';
        if (mimeTypeField) mimeTypeField.value = '';
        if (sizeBytesField) sizeBytesField.value = '';
        return;
      }

      filesPanel.classList.remove('hidden');
      filesEmpty.classList.add('hidden');
      selected.forEach((file) => {
        const row = document.createElement('tr');
        row.className = 'border-t border-gray-100';

        const nameCell = document.createElement('td');
        nameCell.className = 'px-3 py-2 text-gray-900';
        nameCell.textContent = file.name || '-';

        const mimeCell = document.createElement('td');
        mimeCell.className = 'px-3 py-2 text-gray-700';
        mimeCell.textContent = file.type || 'application/octet-stream';

        const sizeCell = document.createElement('td');
        sizeCell.className = 'px-3 py-2 text-gray-700';
        sizeCell.textContent = String(file.size || 0);

        row.appendChild(nameCell);
        row.appendChild(mimeCell);
        row.appendChild(sizeCell);
        filesBody.appendChild(row);
      });

      const first = selected[0];
      if (filenameField) filenameField.value = first.name || '';
      if (mimeTypeField) mimeTypeField.value = first.type || 'application/octet-stream';
      if (sizeBytesField) sizeBytesField.value = String(first.size || 0);
    };

    filesInput.addEventListener('change', renderSelectedFiles);
    renderSelectedFiles();
  }

  const uploadProgress = document.getElementById('upload-progress');
  if (uploadProgress && uploadProgress.dataset.hasIngesting === 'true') {
    window.setInterval(() => {
      const activeEl = document.activeElement;
      const isEditing = !!(
        activeEl
        && ['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(activeEl.tagName)
      );
      const hasSelectedFiles = !!(filesInput && filesInput.files && filesInput.files.length > 0);
      if (isEditing || hasSelectedFiles) {
        return;
      }
      window.location.reload();
    }, 3000);
  }
})();
