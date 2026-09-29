# 项目 Skill 七类盘点与补充建议

核对日期：2026-09-28。

## 核对范围

本次检查用户指定的 OpenCode 项目 Skill 目录，而非 Science Skills Hub 的采集数据库。共发现 33 个一级技能目录，比上次 31 个新增 experimental-design、nsfc-benzi-audit。二者已在目标目录内，均带平台依赖声明；基金生成流水线也已有 2026 面上与青年 C 类模板。

“已有”指本地存在相应技能定义及配套资源，不能据此认定已完成工具注册、依赖安装或端到端运行验收。本次只读检查目标项目，没有安装候选或修改其代码。临床队列建设按用户要求保留缺口记录、暂不列入实施建议。一个技能可能服务多个模块，文末清单按主要用途归组，避免重复计数；内部子步骤不等于独立面向用户的入口。

## 七类覆盖与缺口

| 类别 | 已有能力 | 覆盖不足或缺项 | 补充建议 |
|---|---|---|---|
| 循证文献调研 | OpenAlex；PubMed/Europe PMC/ClinicalTrials.gov 检索；来源溯源、去重、证据卡片及优先级评估；PDF 阅读与论文精读 | 完整稿件参考文献批量核验；全量系统综述的筛选记录、结构化提取与综合 | 优先 verify-refs；完整综述按任务需要补 |
| 临床选题论证 | co-scientist 假说生成、批判、排序、演化和可行性论证；论文卡片也能辅助提出问题 | 基于本单位真实资源的可实施性仍需输入与验证；不属于已确认的独立技能缺项 | 暂不重复加入 brainstorming/hypothesis-generation；优先验证已有流程 |
| 研究设计与统计 | experimental-design 的分组/随机化/区组/DOE；statistical-power 的样本量与效能；申报计划编译器也生成对象/终点/比较/时间点 | 完整临床试验方案文档及面向具体临床研究的统计分析计划流程覆盖待补 | 有临床试验方案需求时评估 clinical-trial-protocol-skill；新增方案流程需核对既有终点/样本量衔接 |
| 临床队列建设 | 未发现专用建表、eCRF、纵向随访流程 | 数据字典、采集表、访视事件与数据质量管理 | 暂缓，不建议本轮加入 |
| 医学统计分析 | 通用检验、回归、诊断、部分时间序列、效应量与科研图表 | 专门的临床生存分析；标志物筛选/预测验证；MR与组学专项流程 | 生存分析优先；LASSO、MR、差异表达按真实业务再加 |
| 论文撰写投稿 | 初稿、润色、模拟审稿、初投材料、逐点回复/修回包；演示和图示 | 医学报告规范逐项检查、系统期刊匹配及独立引用核验 | 优先 check-reporting、verify-refs；其次 find-journal |
| 基金申报与标书 | 假说论证→研究计划→文献证据→模板章节→Word/ZIP；2026 面上/青年 C 模板；nsfc-benzi-audit 初稿诊断/复查 | 目标年度与项目类别的实时政策核实受现有工具能力限制；生成和诊断的调用衔接待运行验证 | 暂不重复加入 nsfc_medicine_all/nsfc-orchestrator；先验证现有生成→诊断→修改流程 |

## 值得补充的候选（未下载、未运行）

| 优先级 | 候选与来源 | 增量价值与边界 |
|---|---|---|
| 第一批 | [check-reporting](https://github.com/Aperivue/medsci-skills/blob/main/skills/check-reporting/SKILL.md) | 对医学报告规范逐项输出已包含/缺失/部分覆盖；补充现有通用审稿。接入时适配其路径与参考文件加载方式。 |
| 第一批 | [verify-refs](https://github.com/Aperivue/medsci-skills/blob/main/skills/verify-refs/SKILL.md) | 核对完整稿件的参考文献元数据、DOI/PMID及不匹配项；有检索来源与标书引用账本，不等于任意稿件都已经批量审计。元数据匹配不等于逐条证明引文支持正文结论。 |
| 第一批 | [survival-analysis-clinical](https://github.com/001TMF/agentic-science) | 临床生存分析专用候选；仓库目录已列出，单技能原文此次网页抓取未成功，接入前需核对具体脚本、统计方法和依赖。 |
| 生存分析备选 | [scikit-survival](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/scikit-survival/SKILL.md) | Python 生存建模、评估及删失相关处理；偏程序实现与预测建模，不能与完整临床研究报告流程直接等同。按任务二选一先验证。 |
| 第二批 | [find-journal](https://github.com/Aperivue/medsci-skills/blob/main/skills/find-journal/SKILL.md) | 根据稿件与期刊信息整理投稿候选；具体要求与费用需按当时刊方资料核实。 |
| 第二批 | [clinical-trial-protocol-skill](https://github.com/anthropics/life-sciences/blob/main/clinical-trial-protocol-skill/SKILL.md) | 药物/器械临床试验方案辅助，现有研究设计和样本量模块的下游候选；原实现含 NIH/FDA 场景，需要适配本地项目模板和工具。 |
| 按需 | [lasso-biomarker-panel](https://github.com/001TMF/agentic-science) | 标志物筛选与建模方向；应核对其数据划分、信息泄漏控制和验证流程，不能只以筛出变量作为完成。 |
| 按需 | [mendelian-randomization-twosamplemr](https://github.com/001TMF/agentic-science) | MR 专项分析方向；仅在实际接到遗传因果推断任务时优先加入。 |
| 按需 | [meta-analysis](https://github.com/Aperivue/medsci-skills/blob/main/skills/meta-analysis/SKILL.md) | 系统综述/Meta 分析流程候选；需检查其依赖的其他技能与工具，不能只复制一个入口文件。 |

推荐先补 check-reporting、verify-refs 和一个生存分析模块。先不扩展队列建设，也不重复引入已覆盖的写作、回复审稿和基金编排入口。

## 判断依据与容易混淆的边界

- clinical-evidence-decision-pipeline 仍声明 24 条候选和最多 12 张入选卡片，适合有界检索，不是完整系统综述。其 valid 标志指来源/产物完整性，不证明临床正确性。
- clinical-evidence-prioritizer 做研究相关性与来源质量解释；未据此认定已有标准化 GRADE 或完整偏倚风险评估流程。
- statistical-analysis 已提及 Cox、Log-rank 和 CONSORT/STROBE/PRISMA；属于已有基础，不应说完全没有。此次未发现独立完整的生存分析及逐项报告规范审计流程。
- nature-writing 已包含初次投稿信、标题页、声明等；nature-response 已包含逐点回复和修回包，所以不建议再加同功能 paper-writer/cover-letter/revise。
- nsfc-benzi-audit 已包含年度、表单、代码等审查表面，但沙箱内注册的 research_lookup 仅查询学术信息，不能将其当作任意官方政策抓取工具。不能因为有政策参考文件就宣称当前年度政策已联网核实。
- variant-explain 明确只规范化七字段 JSON，不做数据库查询或生物学/临床变异解释。
- amp-search 是 AMP 数据库检索，di-an-agent-identity 是平台身份说明；均不应强行当作七类中的完整科研流程。

## 全部 33 项本地清单

以下链接指向此次检查的实际项目文件。分组为便于盘点的主要用途；辅助用途不重复列出。

### 1. 循证文献调研

- [research-lookup](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/research-lookup/SKILL.md)
- [clinical-evidence-decision-pipeline](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/clinical-evidence-decision-pipeline/SKILL.md)
- [clinical-literature-retriever](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/clinical-literature-retriever/SKILL.md)
- [abstract-study-selector](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/abstract-study-selector/SKILL.md)
- [clinical-evidence-prioritizer](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/clinical-evidence-prioritizer/SKILL.md)
- [clinical-reminder-assessor](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/clinical-reminder-assessor/SKILL.md)
- [heme-query-planner](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/heme-query-planner/SKILL.md)
- [heme-treatment-co-scientist](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/heme-treatment-co-scientist/SKILL.md)
- [pdf-reader](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/pdf-reader/SKILL.md)
- [nature-reader](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/nature-reader/SKILL.md)
- [nature-paper-card](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/nature-paper-card/SKILL.md)

### 2. 临床选题论证

- [co-scientist-proposals](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/co-scientist-proposals/SKILL.md)

### 3. 研究设计与统计

- [experimental-design](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/experimental-design/SKILL.md)
- [statistical-power](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/statistical-power/SKILL.md)

### 4. 临床队列建设（按用户要求暂缓）

未发现对应专用 Skill；暂缓补充。

### 5. 医学统计分析

- [statistical-analysis](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/statistical-analysis/SKILL.md)
- [statsmodels](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/statsmodels/SKILL.md)
- [scientific-visualization](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/scientific-visualization/SKILL.md)

### 6. 论文撰写投稿及学术传播

- [nature-writing](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/nature-writing/SKILL.md)
- [nature-polishing](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/nature-polishing/SKILL.md)
- [nature-reviewer](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/nature-reviewer/SKILL.md)
- [nature-response](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/nature-response/SKILL.md)
- [ppt-master](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/ppt-master/SKILL.md)
- [design-to-editable-pptx](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/design-to-editable-pptx/SKILL.md)
- [search-licensed-images](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/search-licensed-images/SKILL.md)

### 7. 基金申报与标书

- [china-grant-research-pipeline](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/china-grant-research-pipeline/SKILL.md)
- [china-proposal-hypothesis-plan-compiler](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/china-proposal-hypothesis-plan-compiler/SKILL.md)
- [china-proposal-literature-evidence](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/china-proposal-literature-evidence/SKILL.md)
- [china-proposal-template-section](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/china-proposal-template-section/SKILL.md)
- [nsfc-benzi-audit](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/nsfc-benzi-audit/SKILL.md)
- [scientific-schematics](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/scientific-schematics/SKILL.md)

### 其他专用与平台辅助

- [amp-search](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/amp-search/SKILL.md)
- [variant-explain](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/variant-explain/SKILL.md)
- [di-an-agent-identity](/Users/chenxizhang/Desktop/gptres/gpt_researcher/sandbox_pool_service/opencode_config/opencode/skills/di-an-agent-identity/SKILL.md)
