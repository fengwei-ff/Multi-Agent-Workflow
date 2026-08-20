const API_BASE = '/api';

const state = {
  todos: [],
};

const todoForm = document.getElementById('todo-form');
const todoInput = document.getElementById('todo-input');
const todoList = document.getElementById('todo-list');
const emptyMessage = document.getElementById('empty-message');

function apiFetch(path, options = {}) {
  return fetch(API_BASE + path, options).then(async (res) => {
    if (res.status === 204) return null;
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      const message = (data && data.error) || '请求失败，请稍后重试';
      throw new Error(message);
    }
    return data;
  });
}

async function loadTodos() {
  try {
    const todos = await apiFetch('/todos');
    state.todos = todos;
    render();
  } catch (err) {
    showToast(err.message);
  }
}

function render() {
  todoList.innerHTML = '';
  const fragment = document.createDocumentFragment();
  state.todos.forEach((todo) => {
    const item = document.createElement('li');
    item.className = 'todo-item';
    item.dataset.id = todo.id;

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.className = 'todo-checkbox';
    checkbox.checked = todo.completed;
    checkbox.setAttribute('aria-label', '完成状态');

    const contentSpan = document.createElement('span');
    contentSpan.className = 'todo-content';
    contentSpan.textContent = todo.content;
    if (todo.completed) {
      contentSpan.classList.add('completed');
    }

    const timeSpan = document.createElement('span');
    timeSpan.className = 'todo-time';
    timeSpan.textContent = new Date(todo.createdAt).toLocaleString();

    const editBtn = document.createElement('button');
    editBtn.className = 'todo-edit-btn';
    editBtn.textContent = '编辑';
    editBtn.setAttribute('aria-label', '编辑待办');

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'todo-delete-btn';
    deleteBtn.textContent = '删除';
    deleteBtn.setAttribute('aria-label', '删除待办');

    item.append(checkbox, contentSpan, timeSpan, editBtn, deleteBtn);

    checkbox.addEventListener('change', () => {
      toggleTodo(todo.id, checkbox.checked);
    });

    editBtn.addEventListener('click', () => {
      enterEditMode(item, todo);
    });

    deleteBtn.addEventListener('click', async () => {
      const confirmed = window.confirm('确定删除该待办？');
      if (!confirmed) return;
      await deleteTodo(todo.id);
    });

    fragment.appendChild(item);
  });
  todoList.appendChild(fragment);
  emptyMessage.style.display = state.todos.length ? 'none' : 'block';
}

function showToast(msg) {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = msg;
  toast.classList.add('show');
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => toast.classList.remove('show'), 2000);
}

function enterEditMode(item, todo) {
  if (item.querySelector('.todo-edit-input')) return;

  const contentSpan = item.querySelector('.todo-content');
  const oldContent = todo.content;

  const editInput = document.createElement('input');
  editInput.type = 'text';
  editInput.className = 'todo-edit-input';
  editInput.value = oldContent;

  const saveBtn = document.createElement('button');
  saveBtn.className = 'todo-save-btn';
  saveBtn.textContent = '保存';

  const cancelBtn = document.createElement('button');
  cancelBtn.className = 'todo-cancel-btn';
  cancelBtn.textContent = '取消';

  const btnContainer = document.createElement('div');
  btnContainer.className = 'edit-btn-group';
  btnContainer.append(saveBtn, cancelBtn);

  contentSpan.replaceWith(editInput);
  item.querySelector('.todo-edit-btn').style.display = 'none';
  item.querySelector('.todo-delete-btn').style.display = 'none';
  editBtnContainerGroup(item, btnContainer);

  editInput.focus();

  saveBtn.addEventListener('click', async () => {
    const newContent = editInput.value.trim();
    if (!newContent) {
      showToast('待办内容不能为空');
      return;
    }
    if (newContent === oldContent) {
      exitEditMode(item, todo);
      return;
    }
    try {
      await updateTodo(todo.id, { content: newContent });
      exitEditMode(item, todo);
    } catch (err) {
      showToast(err.message);
    }
  });

  cancelBtn.addEventListener('click', () => {
    exitEditMode(item, todo);
  });

  editInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      saveBtn.click();
    }
    if (e.key === 'Escape') {
      cancelBtn.click();
    }
  });
}

function editBtnContainerGroup(item, btnContainer) {
  const editBtn = item.querySelector('.todo-edit-btn');
  const deleteBtn = item.querySelector('.todo-delete-btn');
  const btnGroup = item.querySelector('.edit-btn-group');

  if (btnGroup) {
    btnGroup.replaceWith(btnContainer);
  } else {
    editBtn.insertAdjacentElement('afterend', btnContainer);
  }
}

function exitEditMode(item, todo) {
  const editInput = item.querySelector('.todo-edit-input');
  const btnGroup = item.querySelector('.edit-btn-group');
  if (!editInput) return;

  const value = editInput.value.trim();
  const newContent = value || todo.content;

  const contentSpan = document.createElement('span');
  contentSpan.className = 'todo-content';
  contentSpan.textContent = newContent;
  if (todo.completed) {
    contentSpan.classList.add('completed');
  }
  editInput.replaceWith(contentSpan);

  btnGroup.remove();

  item.querySelector('.todo-edit-btn').style.display = '';
  item.querySelector('.todo-delete-btn').style.display = '';
}

async function addTodo(content) {
  try {
    await apiFetch('/todos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    });
    await loadTodos();
  } catch (err) {
    showToast(err.message);
  }
}

async function updateTodo(id, payload) {
  await apiFetch(`/todos/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  await loadTodos();
}

async function deleteTodo(id) {
  try {
    await apiFetch(`/todos/${id}`, { method: 'DELETE' });
    await loadTodos();
  } catch (err) {
    showToast(err.message);
  }
}

async function toggleTodo(id, completed) {
  try {
    await apiFetch(`/todos/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ completed }),
    });
    await loadTodos();
  } catch (err) {
    showToast(err.message);
    await loadTodos();
  }
}

todoForm.addEventListener('submit', (e) => {
  e.preventDefault();
  const content = todoInput.value.trim();
  if (!content) {
    showToast('待办内容不能为空');
    return;
  }
  addTodo(content);
  todoInput.value = '';
});

document.addEventListener('DOMContentLoaded', loadTodos);
