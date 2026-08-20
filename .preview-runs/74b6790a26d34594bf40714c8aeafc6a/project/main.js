const cuisines = [
  {
    id: 'yue',
    name: '粤菜',
    dishes: [
      { name: '白切鸡', intro: '突出食材本味。', ingredients: ['三黄鸡 1只', '姜 20g', '葱 2根'], ratio: ['蘸料：生抽 3 勺', '香油 1 勺', '姜蓉 2 勺'], steps: ['整鸡冷水下锅，小火浸熟。', '捞出冰镇后切块。', '配姜葱蘸料食用。'] },
      { name: '煲仔饭', intro: '锅巴香是关键。', ingredients: ['丝苗米 200g', '腊肠 80g', '青菜 2棵'], ratio: ['酱汁：生抽 2 勺', '蚝油 1 勺', '糖 0.5 勺'], steps: ['米提前泡发后入砂锅。', '七成熟时铺腊肠。', '出锅前淋酱汁焖 2 分钟。'] },
    ],
  },
  {
    id: 'chuan',
    name: '川菜',
    dishes: [
      { name: '宫保鸡丁', intro: '荔枝口要平衡酸甜辣。', ingredients: ['鸡腿肉 250g', '花生米 60g', '干辣椒 10g'], ratio: ['宫保汁：生抽 2 勺', '醋 2 勺', '糖 1.5 勺'], steps: ['鸡丁码味上浆。', '先炸花生再炒辣椒花椒。', '大火收汁后快速翻匀。'] },
      { name: '麻婆豆腐', intro: '麻、辣、烫、香、酥、嫩。', ingredients: ['嫩豆腐 1盒', '牛肉末 80g', '郫县豆瓣 1 勺'], ratio: ['调味：豆瓣 1 勺', '生抽 1 勺', '花椒粉 1 勺'], steps: ['豆腐焯水定型。', '炒香肉末和豆瓣。', '小火烧煮后勾薄芡。'] },
    ],
  },
  {
    id: 'lu',
    name: '鲁菜',
    dishes: [
      { name: '九转大肠', intro: '甜酸香辣兼具层次。', ingredients: ['熟大肠 300g', '香菜 10g', '葱姜适量'], ratio: ['调味：糖 2 勺', '醋 1 勺', '生抽 1 勺'], steps: ['大肠焯洗去异味。', '下锅煸炒至表面紧实。', '分次调味收浓汁。'] },
      { name: '糖醋鲤鱼', intro: '外酥里嫩，汁亮味足。', ingredients: ['鲤鱼 1条', '番茄酱 2 勺', '淀粉适量'], ratio: ['糖醋汁：糖 3 勺', '醋 2 勺', '番茄酱 2 勺'], steps: ['鱼身改刀挂糊定型。', '高温炸至酥脆。', '另起锅熬汁后浇淋。'] },
    ],
  },
];
const tabs = document.getElementById('tabs');
const dishList = document.getElementById('dish-list');
const detail = document.getElementById('detail');
let activeCuisine = cuisines[0];
let activeDish = activeCuisine.dishes[0];
function renderTabs() {
  tabs.innerHTML = cuisines.map((item) => `<button class="tab ${item.id === activeCuisine.id ? 'active' : ''}" data-id="${item.id}">${item.name}</button>`).join('');
  tabs.querySelectorAll('button').forEach((button) => {
    button.addEventListener('click', () => {
      activeCuisine = cuisines.find((item) => item.id === button.dataset.id) || cuisines[0];
      activeDish = activeCuisine.dishes[0];
      render();
    });
  });
}
function renderList() {
  dishList.innerHTML = `<h2>${activeCuisine.name}</h2><div class="dish-grid">${activeCuisine.dishes.map((dish) => `<article class="dish-item"><strong>${dish.name}</strong><p>${dish.intro}</p><button class="tab" data-dish="${dish.name}">查看做法</button><span class="badge">教学步骤</span></article>`).join('')}</div>`;
  dishList.querySelectorAll('[data-dish]').forEach((button) => {
    button.addEventListener('click', () => {
      activeDish = activeCuisine.dishes.find((dish) => dish.name === button.dataset.dish) || activeCuisine.dishes[0];
      renderDetail();
    });
  });
}
function renderDetail() {
  detail.innerHTML = `<h2>${activeDish.name}</h2><p>${activeDish.intro}</p><h3>配菜 / 食材</h3><div class="ingredients">${activeDish.ingredients.map((item) => `<div>- ${item}</div>`).join('')}</div><h3>调料配比</h3><div class="ratio">${activeDish.ratio.map((item) => `<div>- ${item}</div>`).join('')}</div><h3>做法步骤</h3><div class="steps">${activeDish.steps.map((item, index) => `<div>${index + 1}. ${item}</div>`).join('')}</div>`;
}
function render() { renderTabs(); renderList(); renderDetail(); }
render();