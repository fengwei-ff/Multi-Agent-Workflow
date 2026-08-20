// 待办事项应用 - 前端逻辑
const STORAGE_KEY = 'todos';
let todos = [];
let editingId = null;

// DOM 元素
const todoForm = document.getElementById('todo-form');
const todoInput = document.getElementById('todo-input');
const todoList = document.getElementById('todo-list');
const errorMsg = document.getElementById('error-msg');

// 从 localStorage 加载数据
function loadTodos() {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (!stored) return;
  try {
    todos = JSON.parse(stored);
    if (!Array.isArray(todos)) {
      todos = [];
    }
  } catch (e) {
    todos = [];
  }
}

// 保存到 localStorage
function saveTodos() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(todos));
}

// 渲染列表
function render() {
  // 按创建时间从旧到新排序
  const sorted = [...todos].sort((a, b) => new Date(a.createdAt) - new Date(b.createdAt));
  todos = sorted;
  todoList.innerHTML = '';
  sorted.forEach((todo) => {
    const li = document.createElement('li');
    li.className = 'todo-item' + (todo.completed ? ' completed' : '');
    li.dataset.id = todo.id;

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = todo.completed;
    checkbox.addEventListener('change', () => toggleTodo(todo.id, checkbox.checked));

    const contentSpan = document.createElement('span');
    contentSpan.className = 'todo-content';
    contentSpan.textContent = todo.content;

    const timeSpan = document.createElement('span');
    timeSpan.className = 'todo-time';
    timeSpan.textContent = formatTime(todo.createdAt);

    li.appendChild(checkbox);
    li.appendChild(contentSpan);
    li.appendChild(timeSpan);

    // 编辑状态
    if (editingId === todo.id) {
      const editInput = document.createElement('input');
      editInput.type = 'text';
      editInput.className = 'edit-input';
      editInput.value = todo.content;

      const saveBtn = document.createElement('button');
      saveBtn.className = 'save-btn';
      saveBtn.textContent = '保存';
      saveBtn.addEventListener('click', () => saveEdit(todo.id, editInput.value));

      const cancelBtn = document.createElement('button');
      cancelBtn.className = 'cancel-btn';
      cancelBtn.textContent = '取消';
      cancelBtn.addEventListener('click', () => {
        editingId = null;
        render();
      });

      li.appendChild(editInput);
      li.appendChild(saveBtn);
      li.appendChild(cancelBtn);
    } else {
      const editBtn = document.createElement('button');
      editBtn.className = 'edit-btn';
      editBtn.textContent = '编辑';
      editBtn.addEventListener('click', () => {
        editingId = todo.id;
        render();
      });

      const deleteBtn = document.createElement('button');
      deleteBtn.className = 'delete-btn';
      deleteBtn.textContent = '删除';
      deleteBtn.addEventListener('click', () => deleteTodo(todo.id));

      li.appendChild(editBtn);
      li.appendChild(deleteBtn);
    }

    todoList.appendChild(li);
  });
}

function formatTime(isoStr) {
  const d = new Date(isoStr);
  if (isNaN(d.getTime())) return '';
  return d.toLocaleString();
}

// 新增待办
function addTodo() {
  const content = todoInput.value.trim();
  if (!content) {
    errorMsg.textContent = '待办内容不能为空';
    return;
  }
  errorMsg.textContent = '';
  const now = new Date().toISOString();
  todos.push({
    id: generateId(),
    content,
    completed: false,
    createdAt: now,
    updatedAt: now
  });
  saveTodos();
  todoInput.value = '';
  render();
}

// 生成 id
function generateId() {
  if (window.crypto && window.crypto.randomUUID) {
    return window.crypto.randomUUID();
  }
  return 'id-' + Date.now() + '-' + Math.random().toString(16).slice(2);
}

// 切换完成状态
function toggleTodo(id, completed) {
  const todo = todos.find((t) => t.id === id);
  if (!todo) return;
  todo.completed = completed;
  todo.updatedAt = new Date().toISOString();
  saveTodos();
  render();
}

// 保存编辑
function saveEdit(id, newContent) {
  const todo = todos.find((t) => t.id === id);
  if (!todo) return;
  const content = newContent.trim();
  if (!content) {
    errorMsg.textContent = '待办内容不能为空';
    return;
  }
  errorMsg.textContent = '';
  todo.content = content;
  todo.updatedAt = new Date().toISOString();
  editingId = null;
  saveTodos();
  render();
}

// 删除待办
function deleteTodo(id) {
  const confirmed = window.confirm('确定删除该待办？');
  if (!confirmed) return;
  todos = todos.filter((t) => t.id !== id);
  saveTodos();
  render();
}

// 事件绑定
// 按下回车/点击添加
function init() {
  todoForm.addEventListener('submit', (e) => {
    e.preventDefault();
    addTodo();
  });

  // 初始化
  loadTodos();
  render();
}

init();
