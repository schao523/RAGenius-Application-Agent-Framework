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

  const instructionPreviewPanel = document.getElementById('instruction-preview-panel');
  if (instructionPreviewPanel) {
    const tabs = Array.from(document.querySelectorAll('.instruction-preview-tab'));
    const panels = Array.from(document.querySelectorAll('.instruction-preview-mode'));
    const statusEl = document.getElementById('instruction-model-status');
    const summaryEl = document.getElementById('instruction-model-summary');
    const detailsEl = document.getElementById('instruction-model-details');
    const rawEl = document.getElementById('instruction-model-raw');

    const showMode = (mode) => {
      tabs.forEach((tab) => {
        const selected = tab.dataset.previewMode === mode;
        tab.setAttribute('aria-selected', selected ? 'true' : 'false');
        tab.className = selected
          ? 'instruction-preview-tab px-3 py-2 bg-blue-600 text-white'
          : 'instruction-preview-tab px-3 py-2 bg-white text-gray-700';
      });
      panels.forEach((panel) => {
        panel.classList.toggle('hidden', panel.dataset.previewPanel !== mode);
      });
    };

    tabs.forEach((tab) => {
      tab.addEventListener('click', () => showMode(tab.dataset.previewMode || 'runtime'));
    });

    const setStatus = (text, tone = 'neutral') => {
      if (!statusEl) return;
      const toneClass = tone === 'error'
        ? 'border-red-200 bg-red-50 text-red-800'
        : (tone === 'warning'
          ? 'border-amber-200 bg-amber-50 text-amber-800'
          : 'border-gray-200 bg-gray-50 text-gray-700');
      statusEl.className = `rounded border p-3 text-sm ${toneClass}`;
      statusEl.textContent = text;
    };

    const summaryCard = (label, value) => {
      const card = document.createElement('div');
      card.className = 'rounded border border-gray-200 bg-white p-3';
      const labelEl = document.createElement('div');
      labelEl.className = 'text-xs font-semibold text-gray-500 uppercase tracking-wide';
      labelEl.textContent = label;
      const valueEl = document.createElement('div');
      valueEl.className = 'mt-1 text-sm font-semibold text-gray-900 break-all';
      valueEl.textContent = value === null || value === undefined || value === '' ? '-' : String(value);
      card.appendChild(labelEl);
      card.appendChild(valueEl);
      return card;
    };

    const itemLabel = (item) => {
      if (item && typeof item === 'object') {
        return item.label || item.title || item.name || item.id || item.block_id || item.procedure_id || item.step_id || item.resource_id || JSON.stringify(item);
      }
      return String(item ?? '-');
    };

    const section = (title, items) => {
      const wrapper = document.createElement('details');
      wrapper.className = 'rounded border border-gray-200 bg-white p-3';
      wrapper.open = false;
      const summary = document.createElement('summary');
      summary.className = 'cursor-pointer text-sm font-semibold text-gray-800';
      summary.textContent = `${title} (${items.length})`;
      wrapper.appendChild(summary);
      const list = document.createElement('ul');
      list.className = 'mt-2 space-y-1 text-sm text-gray-700';
      items.slice(0, 25).forEach((item, index) => {
        const row = document.createElement('li');
        row.className = 'break-all';
        row.textContent = itemLabel(item) || `item ${index + 1}`;
        list.appendChild(row);
      });
      if (items.length > 25) {
        const more = document.createElement('li');
        more.className = 'text-gray-500';
        more.textContent = `${items.length - 25} more item(s) available in Raw JSON.`;
        list.appendChild(more);
      }
      wrapper.appendChild(list);
      return wrapper;
    };

    const procedureSection = (procedures) => {
      const wrapper = document.createElement('details');
      wrapper.className = 'rounded border border-gray-200 bg-white p-3';
      wrapper.open = true;
      const summary = document.createElement('summary');
      summary.className = 'cursor-pointer text-sm font-semibold text-gray-800';
      summary.textContent = `Procedures (${procedures.length})`;
      wrapper.appendChild(summary);

      const container = document.createElement('div');
      container.className = 'mt-3 space-y-3';
      procedures.slice(0, 25).forEach((procedure) => {
        const procBlock = document.createElement('div');
        procBlock.className = 'rounded border border-gray-100 bg-gray-50 p-3';
        const title = document.createElement('div');
        title.className = 'text-sm font-semibold text-gray-900 break-all';
        title.textContent = itemLabel(procedure);
        procBlock.appendChild(title);

        if (procedure.kind || procedure.id) {
          const meta = document.createElement('div');
          meta.className = 'mt-1 text-xs text-gray-500 break-all';
          meta.textContent = [procedure.kind, procedure.id].filter(Boolean).join(' | ');
          procBlock.appendChild(meta);
        }

        const steps = asArray(procedure.steps);
        if (steps.length > 0) {
          const stepList = document.createElement('ol');
          stepList.className = 'mt-2 space-y-2 text-sm text-gray-700 list-decimal list-inside';
          steps.forEach((step) => {
            const stepRow = document.createElement('li');
            stepRow.className = 'break-all';
            const label = document.createElement('span');
            label.className = 'font-medium text-gray-800';
            label.textContent = itemLabel(step);
            stepRow.appendChild(label);
            if (step.body_text) {
              const body = document.createElement('div');
              body.className = 'ml-5 mt-1 whitespace-pre-wrap text-gray-600';
              body.textContent = step.body_text;
              stepRow.appendChild(body);
            }
            stepList.appendChild(stepRow);
          });
          procBlock.appendChild(stepList);
        } else {
          const empty = document.createElement('div');
          empty.className = 'mt-2 text-sm text-amber-700';
          empty.textContent = 'No procedure steps found for this procedure in the compiled model.';
          procBlock.appendChild(empty);
        }
        container.appendChild(procBlock);
      });
      if (procedures.length > 25) {
        const more = document.createElement('div');
        more.className = 'text-sm text-gray-500';
        more.textContent = `${procedures.length - 25} more procedure(s) available in Raw JSON.`;
        container.appendChild(more);
      }
      wrapper.appendChild(container);
      return wrapper;
    };

    const asArray = (value) => Array.isArray(value) ? value : [];
    const runtimeModel = (payload) => {
      const contract = payload && payload.compiled_contract && typeof payload.compiled_contract === 'object'
        ? payload.compiled_contract
        : {};
      if (contract.instruction_runtime_model && typeof contract.instruction_runtime_model === 'object') {
        return contract.instruction_runtime_model;
      }
      if (contract.hybrid_instruction_runtime_model && typeof contract.hybrid_instruction_runtime_model === 'object') {
        return contract.hybrid_instruction_runtime_model;
      }
      return {};
    };

    const renderModel = (model) => {
      const payload = model.payload || null;
      const summary = model.summary || {};
      if (rawEl) {
        rawEl.textContent = payload ? JSON.stringify(payload, null, 2) : 'Runtime model JSON is not available.';
      }
      if (summaryEl) {
        summaryEl.innerHTML = '';
        [
          ['Status', model.status],
          ['Freshness', model.freshness],
          ['Primary service mode', summary.primary_service_mode],
          ['Default workflow', summary.default_workflow_id],
          ['Service blocks', summary.service_block_count],
          ['Procedures', summary.procedure_count],
          ['Procedure steps', summary.procedure_step_count],
          ['Resources', summary.resource_count],
          ['Semantic attached', summary.semantic_attached],
          ['Semantic valid', summary.semantic_valid],
        ].forEach(([label, value]) => summaryEl.appendChild(summaryCard(label, value)));
      }
      if (detailsEl) {
        const rt = runtimeModel(payload);
        const displayModel = model.display_model || {};
        detailsEl.innerHTML = '';
        detailsEl.appendChild(section('Service Blocks And Workflows', asArray(displayModel.service_blocks).length > 0 ? asArray(displayModel.service_blocks) : asArray(rt.instruction_service_blocks)));
        detailsEl.appendChild(procedureSection(asArray(displayModel.procedures)));
        detailsEl.appendChild(section('Resources', asArray(displayModel.resources).length > 0 ? asArray(displayModel.resources) : asArray(rt.instruction_resources)));
        detailsEl.appendChild(section('Dependency Groups', asArray(displayModel.dependency_groups)));
        detailsEl.appendChild(section('Phase Resource Bindings', asArray(displayModel.phase_resource_bindings)));
        detailsEl.appendChild(section('Policies', asArray(displayModel.policies).length > 0 ? asArray(displayModel.policies) : [
          ...asArray(rt.global_policies),
          ...asArray(rt.progression_rules),
          ...asArray(rt.turn_constraints),
          ...asArray(rt.response_policies),
          ...asArray(rt.clarification_gate_rules),
        ]));
      }

      if (model.status === 'error') {
        setStatus(`Runtime model error: ${(model.errors || []).join('; ') || model.freshness_reason || 'unknown error'}`, 'error');
      } else if (model.status === 'missing') {
        setStatus(`Runtime model unavailable: ${model.freshness_reason || 'no compiled model was found'}`, 'warning');
      } else if (model.freshness === 'stale') {
        setStatus(`Runtime model loaded but stale: ${model.freshness_reason}`, 'warning');
      } else {
        setStatus(`Runtime model loaded. Freshness: ${model.freshness || 'unknown'}.`, 'neutral');
      }
    };

    const url = instructionPreviewPanel.dataset.instructionModelUrl;
    if (url) {
      window.fetch(url, { headers: { Accept: 'application/json' } })
        .then((response) => {
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          return response.json();
        })
        .then(renderModel)
        .catch((err) => {
          setStatus(`Runtime model unavailable: ${err.message}`, 'error');
          if (rawEl) rawEl.textContent = 'Runtime model JSON is not available.';
        });
    }
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
