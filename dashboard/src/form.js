import { formatNumber, parseNumber } from './assessment.js';
import { $, clearFeedback } from './dom.js';

const template = document.createElement('template');
const form = $('assessment-form');

function fieldMarkup({ name, type, required }) {
  const error = `<p class="field-error" id="error-${name}" hidden></p>`;
  if (type !== 'binary') return `<div class="field"><label id="label-${name}" for="${name}"></label><input id="${name}" name="${name}" type="text" inputmode="${type === 'int' ? 'numeric' : 'decimal'}" aria-describedby="help-${name} error-${name}"><p class="muted text-small" id="help-${name}"></p>${error}</div>`;

  const sex = name === 'male';
  const options = sex ? [['1', 'Laki-laki'], ['0', 'Perempuan']] : [['1', 'Ya'], ['0', 'Tidak'], ['', 'Tidak tahu']];
  const controls = options.map(([value, label]) => `<label><input type="radio" name="${name}" value="${value}" aria-describedby="error-${name}" ${!required && !value ? 'checked' : ''}><span>${label}</span></label>`).join('');
  if (sex) return `<fieldset class="field"><legend id="label-${name}"></legend><div class="sex-choices">${controls}</div>${error}</fieldset>`;
  return `<div class="history-row"><span id="label-${name}"></span><div role="group" aria-labelledby="label-${name}"><div class="segments">${controls}</div>${error}</div></div>`;
}

export function mountFields(schema) {
  const definitions = Object.fromEntries(schema.map((feature) => [feature.name, feature]));
  for (const group of document.querySelectorAll('[data-fields]')) {
    template.innerHTML = group.dataset.fields.split(' ').map((key) => fieldMarkup(definitions[key])).join('');
    group.replaceChildren(template.content.cloneNode(true));
  }
  updateFields(schema);
}

export function updateFields(schema) {
  for (const { name, label, type, required, min, max, unit } of schema) {
    $(`label-${name}`).textContent = `${label}${unit ? ` (${unit})` : ''}${required ? ' *' : ''}`;
    for (const control of form.querySelectorAll(`[name="${name}"]`)) {
      control.required = required;
    }
    if (type !== 'binary') {
      const range = `${formatNumber(min)}–${formatNumber(max)}${unit ? ` ${unit}` : ''}`;
      $(`help-${name}`).textContent = required ? `Rentang ${range}` : `Opsional · Rentang ${range}`;
    }
  }
}

export function clearFieldError(name) {
  if (!$(`error-${name}`)) return;
  clearFeedback($(`error-${name}`));
  for (const control of form.querySelectorAll(`[name="${name}"]`)) control.removeAttribute('aria-invalid');
}

export function showFieldErrors(errors) {
  let first = null;
  for (const control of form.elements) {
    const message = errors[control.name];
    if (typeof message !== 'string' || !$(`error-${control.name}`)) continue;
    const node = $(`error-${control.name}`);
    node.textContent = message;
    node.hidden = false;
    control.setAttribute('aria-invalid', 'true');
    first ??= control;
  }
  first?.focus();
  return Boolean(first);
}

export function setForm(input, schema) {
  form.reset();
  for (const { name, type } of schema) {
    clearFieldError(name);
    if (!input) continue;
    const value = input[name];
    if (type === 'binary') {
      const control = form.querySelector(`[name="${name}"][value="${value ?? ''}"]`);
      if (control) control.checked = true;
    } else if (value != null) $(name).value = formatNumber(value);
  }
  if (input?.age === 19) {
    $('height').value = '160';
    $('weight').value = '63';
  }
  clearFeedback($('bmi-helper-error'));
  clearFeedback($('assessment-error'));
}

$('apply-bmi').addEventListener('click', () => {
  const height = parseNumber($('height').value);
  const weight = parseNumber($('weight').value);
  const message = $('bmi-helper-error');
  if (!(height >= 100 && height <= 240 && weight >= 25 && weight <= 250)) {
    message.textContent = 'Masukkan tinggi 100–240 cm dan berat 25–250 kg.';
    message.hidden = false;
    $(height >= 100 && height <= 240 ? 'weight' : 'height').focus();
    return;
  }
  $('bmi').value = formatNumber(Math.round((weight / (height / 100) ** 2) * 10) / 10);
  clearFeedback(message);
  clearFieldError('bmi');
  $('bmi').focus();
});

form.addEventListener('input', ({ target }) => {
  if (target.name) clearFieldError(target.name);
});
