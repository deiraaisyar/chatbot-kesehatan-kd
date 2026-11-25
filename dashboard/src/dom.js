export const $ = (id) => document.getElementById(id);

export function element(tag, className = '', text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

export function icon(name) {
  const node = element('span', 'icon', name);
  node.setAttribute('aria-hidden', 'true');
  return node;
}

export function clearFeedback(node) {
  node.replaceChildren();
  node.hidden = true;
}

export function showFeedback(node, message, { error = false, requestId } = {}) {
  node.textContent = message;
  node.classList.toggle('error', error);
  if (requestId) {
    const detail = element('p', '', 'ID permintaan ');
    detail.append(element('code', '', requestId));
    node.append(detail);
  }
  node.hidden = false;
}
