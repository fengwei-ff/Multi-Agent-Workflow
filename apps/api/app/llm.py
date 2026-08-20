from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncIterator

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import Settings, get_settings

logger = logging.getLogger('workflow_agent.llm')


SYSTEM_PROMPTS = {
    'intent': (
        '你是需求分析助手。根据用户原始需求，用中文输出 JSON：'
        '{"intent":"一句话意图","requirements_doc":"结构化需求草案(markdown)",'
        '"open_questions":["最多3个澄清问题"],"assistant_message":"给用户的说明"}。'
        'open_questions 必须针对该需求的具体缺口（用户/场景/边界/集成/验收），'
        '禁止输出与需求无关的通用模板问题。'
    ),
    'discuss': (
        '你是需求讨论助手。结合已有需求文档、开放问题与用户最新回复，用中文输出 JSON：'
        '{"requirements_doc":"更新后的需求文档(markdown)","open_questions":["剩余澄清问题,最多3个"],'
        '"ready_for_alignment":true/false,"assistant_message":"给用户的回复"}。'
        'open_questions 须结合当前需求上下文，已澄清的不要重复问。'
    ),
    'tech': (
        '你是技术方案设计师。基于已对齐需求，输出 JSON：'
        '{"tech_design":"完整技术方案 markdown(架构/模块/接口/风险/估时)",'
        '"assistant_message":"简要说明"}'
    ),
    'revise_tech': (
        '你是技术方案设计师。根据用户反馈修订技术方案，输出 JSON：'
        '{"tech_design":"修订后的技术方案 markdown","assistant_message":"变更说明"}'
    ),
    'codegen_h5': (
        '你是 H5 页面代码生成助手。基于需求与技术方案，直接输出可运行的单页 H5 代码，'
        '不要输出 JSON，不要解释，不要补充说明。'
        '输出格式必须是 markdown 多文件代码块，且仅包含以下文件：'
        '`## index.html` + ```html```、`## styles.css` + ```css```、`## main.js` + ```js```。'
        '页面必须可直接在浏览器打开运行，适配移动端，内容完整，样式可用。'
        '如果需求是内容型 H5，需要输出真实页面结构、交互、示例数据与基础视觉效果。'
    ),
    'checklist': (
        '你是测试规划助手。基于需求与代码产出功能 checklist，输出 JSON：'
        '{"checklist":[{"id":"c1","title":"检查项","passed":null,"note":""}],'
        '"assistant_message":"说明"}。checklist 4-8 项，并覆盖代码落盘与沙箱执行结果。'
    ),
    'checklist_verify': (
        '你是自检助手。对照 checklist 与代码做静态自检，输出 JSON：'
        '{"checklist":[{"id":"c1","title":"...","passed":true/false,"note":"依据"}],'
        '"checklist_summary":"总结","assistant_message":"给用户的结论"}。'
        '必须结合 sandbox_report 判断通过/失败。'
    ),
}


def _extract_json(text: str) -> dict[str, Any]:
    content = text.strip()
    if content.startswith('```'):
        lines = content.split('\n')
        lines = lines[1:]
        if lines and lines[-1].strip() == '```':
            lines = lines[:-1]
        content = '\n'.join(lines).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find('{')
        end = content.rfind('}')
        if start >= 0 and end > start:
            return json.loads(content[start : end + 1])
        raise


class LLMClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._chat: ChatOpenAI | None = None
        if not self.settings.should_use_mock:
            self._chat = ChatOpenAI(
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                model=self.settings.openai_model,
                temperature=0.3,
                timeout=90,
                max_retries=1,
            )

    async def acomplete_json(self, mode: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        if self.settings.should_use_mock:
            return self._mock(mode, user_payload)

        assert self._chat is not None
        messages = [
            SystemMessage(content=SYSTEM_PROMPTS[mode]),
            HumanMessage(content=json.dumps(user_payload, ensure_ascii=False)),
        ]
        started_at = time.perf_counter()
        logger.info('LLM request started: mode=%s model=%s', mode, self.settings.openai_model)
        try:
            response = await self._chat.ainvoke(messages)
            content = response.content if isinstance(response.content, str) else str(response.content)
            logger.info(
                'LLM request finished: mode=%s elapsed_ms=%d',
                mode,
                int((time.perf_counter() - started_at) * 1000),
            )
            return _extract_json(content)
        except Exception:
            logger.exception('LLM call failed for mode=%s, falling back to mock', mode)
            if not self.settings.should_use_mock:
                logger.warning(
                    'Real LLM configured but call failed; mock questions may look generic. '
                    'Check API key, base URL, and model name.',
                )
            return self._mock(mode, user_payload)

    async def achat(self, messages: list[dict[str, str]]) -> str:
        """Raw multi-turn chat used by the agent loop. Returns assistant text."""
        if self.settings.should_use_mock:
            return json.dumps(
                {'type': 'message', 'content': 'mock 模式：请使用 MockAgentBackend'},
                ensure_ascii=False,
            )

        assert self._chat is not None
        lc_messages = [
            SystemMessage(content=m['content']) if m.get('role') == 'system'
            else HumanMessage(content=m['content'])
            for m in messages
        ]
        started_at = time.perf_counter()
        logger.info('Agent chat request started: model=%s', self.settings.openai_model)
        response = await self._chat.ainvoke(lc_messages)
        content = response.content if isinstance(response.content, str) else str(response.content)
        logger.info(
            'Agent chat request finished: elapsed_ms=%d',
            int((time.perf_counter() - started_at) * 1000),
        )
        return content

    async def astream_text(self, mode: str, user_payload: dict[str, Any]) -> AsyncIterator[str]:
        if self.settings.should_use_mock:
            text = self._mock(mode, user_payload)
            for index in range(0, len(text), 48):
                yield text[index : index + 48]
            return

        assert self._chat is not None
        messages = [
            SystemMessage(content=SYSTEM_PROMPTS[mode]),
            HumanMessage(content=json.dumps(user_payload, ensure_ascii=False)),
        ]
        started_at = time.perf_counter()
        logger.info('LLM stream started: mode=%s model=%s', mode, self.settings.openai_model)
        try:
            async for chunk in self._chat.astream(messages):
                content = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
                if content:
                    yield content
            logger.info(
                'LLM stream finished: mode=%s elapsed_ms=%d',
                mode,
                int((time.perf_counter() - started_at) * 1000),
            )
        except Exception:
            logger.exception('LLM stream failed for mode=%s, falling back to mock', mode)
            text = self._mock(mode, user_payload)
            for index in range(0, len(text), 48):
                yield text[index : index + 48]

    def _derive_open_questions(self, request: str) -> list[str]:
        """Lightweight contextual questions for mock/fallback only."""
        text = request.strip()
        questions: list[str] = []

        if any(k in text for k in ('工单', 'ticket', '审批', '流程')):
            questions.extend([
                f'「{text[:24]}」的主要使用角色是谁（提交人/处理人/管理员）？',
                '工单状态流转需要哪些节点，是否需要对接现有 OA/IM？',
            ])
        elif any(k in text for k in ('助手', 'Agent', 'agent', 'AI')):
            questions.extend([
                f'「{text[:24]}」面向的内部用户是谁，典型使用场景是什么？',
                '需要接入哪些现有系统或数据源？',
            ])
        else:
            questions.extend([
                f'「{text[:24]}」的核心用户与主要使用场景是什么？',
                '必须满足的验收标准或上线约束有哪些？',
            ])

        questions.append('期望的首期 MVP 范围与非目标是什么？')
        return questions[:3]

    def _mock(self, mode: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = str(payload.get('user_request') or payload.get('requirements_doc') or '未命名需求')
        short = request[:40]
        feedback = str(payload.get('feedback') or '')

        if mode == 'intent':
            open_questions = self._derive_open_questions(request)
            numbered = '\n'.join(f'{index + 1}. {q}' for index, q in enumerate(open_questions))
            return {
                'intent': f'实现：{short}',
                'requirements_doc': (
                    f'# 需求草案\n\n## 背景\n{request}\n\n'
                    '## 目标\n- 交付可用的 MVP\n\n'
                    '## 范围\n- 核心流程\n- 基础界面\n\n'
                    '## 非目标\n- 完整自动化发布\n'
                ),
                'open_questions': open_questions,
                'assistant_message': (
                    f'我理解你的需求是「{short}」。请确认或补充以下问题：\n{numbered}'
                ),
            }

        if mode == 'discuss':
            user_msg = str(payload.get('pending_user_message') or '')
            rounds = int(payload.get('discussion_rounds') or 0)
            ready = bool(user_msg) or rounds >= 2
            doc = str(payload.get('requirements_doc') or '')
            if user_msg:
                doc = f'{doc}\n\n## 用户补充\n{user_msg}\n'
            questions = [] if ready else self._derive_open_questions(request)[-1:]
            return {
                'requirements_doc': doc,
                'open_questions': questions,
                'ready_for_alignment': ready,
                'assistant_message': (
                    '已根据你的补充更新需求文档。'
                    + ('我认为可以进入对齐确认。' if ready else '还需要再澄清一些问题。')
                ),
            }

        if mode in {'tech', 'revise_tech'}:
            return {
                'tech_design': (
                    f'# 技术方案\n\n## 架构\n- 前端 React\n- 后端 FastAPI + LangGraph\n'
                    f'- 存储 SQLite/Postgres\n\n## 模块\n- 会话与工作流编排\n- 人机确认闸门\n'
                    f'- 设计产物管理\n\n## 接口\n- POST /threads\n- POST /threads/{{id}}/runs\n'
                    f'- POST /threads/{{id}}/resume\n\n## 风险\n- LLM 不稳定\n- 长会话状态膨胀\n\n'
                    f'## 估时\n- MVP 1-2 周\n\n## 反馈处理\n{feedback or "无"}\n\n'
                    f'## 对应需求\n{short}\n'
                ),
                'assistant_message': '已生成/更新技术方案。',
            }

        if mode == 'codegen_h5':
            return (
                '## index.html\n\n'
                '```html\n'
                '<!doctype html>\n'
                '<html lang="zh-CN">\n'
                '  <head>\n'
                '    <meta charset="UTF-8" />\n'
                '    <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
                '    <title>中华美食教学</title>\n'
                '    <link rel="stylesheet" href="./styles.css" />\n'
                '  </head>\n'
                '  <body>\n'
                '    <div class="app">\n'
                '      <header class="hero">\n'
                '        <h1>中华美食教学 H5</h1>\n'
                '        <p>按菜系学习经典菜做法、配菜和调料配比。</p>\n'
                '      </header>\n'
                '      <nav class="tabs" id="tabs"></nav>\n'
                '      <section class="card" id="dish-list"></section>\n'
                '      <section class="card detail" id="detail"></section>\n'
                '    </div>\n'
                '    <script src="./main.js"></script>\n'
                '  </body>\n'
                '</html>\n'
                '```\n\n'
                '## styles.css\n\n'
                '```css\n'
                ':root { color-scheme: dark; }\n'
                '* { box-sizing: border-box; }\n'
                'body { margin: 0; font-family: Arial, sans-serif; background: #081120; color: #eaf2ff; }\n'
                '.app { max-width: 960px; margin: 0 auto; padding: 20px; }\n'
                '.hero, .card { background: rgba(18, 28, 46, 0.92); border: 1px solid rgba(120,180,255,.18); border-radius: 20px; padding: 18px; margin-bottom: 16px; }\n'
                '.tabs { display: flex; gap: 10px; overflow: auto; margin: 16px 0; }\n'
                '.tab { border: 1px solid rgba(120,180,255,.18); background: #10203a; color: #dfe9ff; border-radius: 999px; padding: 10px 16px; }\n'
                '.tab.active { background: linear-gradient(135deg, #2fd4a1, #4cc9f0); color: #041018; font-weight: 700; }\n'
                '.dish-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }\n'
                '.dish-item { padding: 14px; border-radius: 16px; background: #0d1b32; border: 1px solid rgba(120,180,255,.14); }\n'
                '.badge { display: inline-block; margin-top: 8px; font-size: 12px; color: #8ed8ff; }\n'
                '.ratio, .steps, .ingredients { line-height: 1.7; }\n'
                '```\n\n'
                '## main.js\n\n'
                '```js\n'
                "const cuisines = [\n"
                "  {\n"
                "    id: 'yue',\n"
                "    name: '粤菜',\n"
                "    dishes: [\n"
                "      { name: '白切鸡', intro: '突出食材本味。', ingredients: ['三黄鸡 1只', '姜 20g', '葱 2根'], ratio: ['蘸料：生抽 3 勺', '香油 1 勺', '姜蓉 2 勺'], steps: ['整鸡冷水下锅，小火浸熟。', '捞出冰镇后切块。', '配姜葱蘸料食用。'] },\n"
                "      { name: '煲仔饭', intro: '锅巴香是关键。', ingredients: ['丝苗米 200g', '腊肠 80g', '青菜 2棵'], ratio: ['酱汁：生抽 2 勺', '蚝油 1 勺', '糖 0.5 勺'], steps: ['米提前泡发后入砂锅。', '七成熟时铺腊肠。', '出锅前淋酱汁焖 2 分钟。'] },\n"
                "    ],\n"
                "  },\n"
                "  {\n"
                "    id: 'chuan',\n"
                "    name: '川菜',\n"
                "    dishes: [\n"
                "      { name: '宫保鸡丁', intro: '荔枝口要平衡酸甜辣。', ingredients: ['鸡腿肉 250g', '花生米 60g', '干辣椒 10g'], ratio: ['宫保汁：生抽 2 勺', '醋 2 勺', '糖 1.5 勺'], steps: ['鸡丁码味上浆。', '先炸花生再炒辣椒花椒。', '大火收汁后快速翻匀。'] },\n"
                "      { name: '麻婆豆腐', intro: '麻、辣、烫、香、酥、嫩。', ingredients: ['嫩豆腐 1盒', '牛肉末 80g', '郫县豆瓣 1 勺'], ratio: ['调味：豆瓣 1 勺', '生抽 1 勺', '花椒粉 1 勺'], steps: ['豆腐焯水定型。', '炒香肉末和豆瓣。', '小火烧煮后勾薄芡。'] },\n"
                "    ],\n"
                "  },\n"
                "  {\n"
                "    id: 'lu',\n"
                "    name: '鲁菜',\n"
                "    dishes: [\n"
                "      { name: '九转大肠', intro: '甜酸香辣兼具层次。', ingredients: ['熟大肠 300g', '香菜 10g', '葱姜适量'], ratio: ['调味：糖 2 勺', '醋 1 勺', '生抽 1 勺'], steps: ['大肠焯洗去异味。', '下锅煸炒至表面紧实。', '分次调味收浓汁。'] },\n"
                "      { name: '糖醋鲤鱼', intro: '外酥里嫩，汁亮味足。', ingredients: ['鲤鱼 1条', '番茄酱 2 勺', '淀粉适量'], ratio: ['糖醋汁：糖 3 勺', '醋 2 勺', '番茄酱 2 勺'], steps: ['鱼身改刀挂糊定型。', '高温炸至酥脆。', '另起锅熬汁后浇淋。'] },\n"
                "    ],\n"
                "  },\n"
                "];\n"
                "const tabs = document.getElementById('tabs');\n"
                "const dishList = document.getElementById('dish-list');\n"
                "const detail = document.getElementById('detail');\n"
                "let activeCuisine = cuisines[0];\n"
                "let activeDish = activeCuisine.dishes[0];\n"
                "function renderTabs() {\n"
                "  tabs.innerHTML = cuisines.map((item) => `<button class=\"tab ${item.id === activeCuisine.id ? 'active' : ''}\" data-id=\"${item.id}\">${item.name}</button>`).join('');\n"
                "  tabs.querySelectorAll('button').forEach((button) => {\n"
                "    button.addEventListener('click', () => {\n"
                "      activeCuisine = cuisines.find((item) => item.id === button.dataset.id) || cuisines[0];\n"
                "      activeDish = activeCuisine.dishes[0];\n"
                "      render();\n"
                "    });\n"
                "  });\n"
                "}\n"
                "function renderList() {\n"
                "  dishList.innerHTML = `<h2>${activeCuisine.name}</h2><div class=\"dish-grid\">${activeCuisine.dishes.map((dish) => `<article class=\"dish-item\"><strong>${dish.name}</strong><p>${dish.intro}</p><button class=\"tab\" data-dish=\"${dish.name}\">查看做法</button><span class=\"badge\">教学步骤</span></article>`).join('')}</div>`;\n"
                "  dishList.querySelectorAll('[data-dish]').forEach((button) => {\n"
                "    button.addEventListener('click', () => {\n"
                "      activeDish = activeCuisine.dishes.find((dish) => dish.name === button.dataset.dish) || activeCuisine.dishes[0];\n"
                "      renderDetail();\n"
                "    });\n"
                "  });\n"
                "}\n"
                "function renderDetail() {\n"
                "  detail.innerHTML = `<h2>${activeDish.name}</h2><p>${activeDish.intro}</p><h3>配菜 / 食材</h3><div class=\"ingredients\">${activeDish.ingredients.map((item) => `<div>- ${item}</div>`).join('')}</div><h3>调料配比</h3><div class=\"ratio\">${activeDish.ratio.map((item) => `<div>- ${item}</div>`).join('')}</div><h3>做法步骤</h3><div class=\"steps\">${activeDish.steps.map((item, index) => `<div>${index + 1}. ${item}</div>`).join('')}</div>`;\n"
                "}\n"
                "function render() { renderTabs(); renderList(); renderDetail(); }\n"
                "render();\n"
                '```\n'
            )

        if mode == 'checklist':
            return {
                'checklist': [
                    {'id': 'c1', 'title': '可创建工单', 'passed': None, 'note': ''},
                    {'id': 'c2', 'title': '可查看工单列表', 'passed': None, 'note': ''},
                    {'id': 'c3', 'title': '提供工单相关 API', 'passed': None, 'note': ''},
                    {'id': 'c4', 'title': '代码已成功落盘到沙箱目录', 'passed': None, 'note': ''},
                    {'id': 'c5', 'title': '沙箱语法/类型检查通过', 'passed': None, 'note': ''},
                    {'id': 'c6', 'title': '页面存在基础占位结构', 'passed': None, 'note': ''},
                ],
                'assistant_message': '已生成功能 checklist，开始自检。',
            }

        if mode == 'checklist_verify':
            items = payload.get('checklist') or []
            sandbox_report = str(payload.get('sandbox_report') or '')
            sandbox_failed = 'exit_code: 0' not in sandbox_report and '未找到可直接执行' not in sandbox_report
            verified = []
            for index, item in enumerate(items):
                title = item.get('title') or f'检查项 {index + 1}'
                passed = not sandbox_failed
                note = '代码骨架中可定位到对应占位实现'
                if '沙箱' in str(title):
                    passed = not sandbox_failed
                    note = '根据 sandbox_report 判断'
                elif '落盘' in str(title):
                    passed = '沙箱目录：' in sandbox_report
                    note = '已生成隔离目录并写入文件'
                verified.append(
                    {
                        'id': item.get('id') or f'c{index + 1}',
                        'title': title,
                        'passed': passed,
                        'note': note,
                    }
                )
            if not verified:
                verified = [
                    {
                        'id': 'c1',
                        'title': '基础骨架存在',
                        'passed': True,
                        'note': '已生成前端与 API 占位代码',
                    }
                ]
            failed = [item for item in verified if item.get('passed') is False]
            summary = (
                f'自检完成：通过 {len(verified) - len(failed)} / {len(verified)}。'
                + ('存在失败项，建议修订代码。' if failed else '全部通过。')
            )
            return {
                'checklist': verified,
                'checklist_summary': summary,
                'assistant_message': summary,
            }

        return {'assistant_message': '已处理。'}


_llm: LLMClient | None = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm
