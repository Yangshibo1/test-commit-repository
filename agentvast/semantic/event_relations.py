"""Fixed Event relation definitions; synchronized with the documented catalog."""

CATALOG_VERSION = "event-relations/0.2"
CATALOG = [
    {
        "type": "PROVIDES_INPUT",
        "meaning": "提供输入：数据/信息/中间结果 → 实际使用者",
        "required": "A 产出可识别对象或信息；B 的记录明确使用该对象、版本或内容",
        "excluded": "只访问相同路径、讨论同一主题、只有计划而无消费证据",
        "example": "A 输出清洗表；B 命令参数读取该版本的清洗表",
    },
    {
        "type": "GUIDES_METHOD",
        "meaning": "指导方法：要求/约束/方案 → 采用该方法的行为",
        "required": "A 给出范围、指标、方法、交付格式等约束；B 明确采纳并落实",
        "excluded": "泛泛背景介绍、未采纳的建议、计划之间没有后续落实",
        "example": "A 要求使用中位数；B 计算中位数并报告",
    },
    {
        "type": "ENABLES_EXECUTION",
        "meaning": "提供执行条件：准备/恢复条件 → 依赖该条件的执行",
        "required": "A 建立必要环境或能力；B 的记录表明确实依赖它",
        "excluded": "常规初始化、仅因安装在执行之前、无法说明必要依赖",
        "example": "A 解决缺失依赖；B 随后成功执行此前被该依赖阻断的脚本",
    },
    {
        "type": "TRIGGERS",
        "meaning": "触发行动：要求/决定 → 具体后续行动",
        "required": "A 明确提出行动；B 对应该行动且关联可核查；更具体类型不适用",
        "excluded": "单纯 tool_use 配对、普通函数调用、时间相邻、笼统“接下来分析”",
        "example": "A 要求补充地区对比；B 新增对应分析",
    },
    {
        "type": "MOTIVATES_INVESTIGATION",
        "meaning": "引出调查：异常/差异/线索 → 定向调查",
        "required": "A 发现具体疑点；B 围绕该疑点追加检查或探索",
        "excluded": "常规探索、A 没有疑点、B 尚未调查就只是复述结果",
        "example": "A 发现某日骤降；B 检查当日缺失记录与采集状态",
    },
    {
        "type": "LEADS_TO_CORRECTION",
        "meaning": "促成修正：问题/错误 → 修正行为",
        "required": "A 暴露可识别问题；B 针对同一问题实际修改代码、数据处理或方法",
        "excluded": "无关修改、仅有失败、相同条件原样重跑、只声称“已修复”",
        "example": "A 日期解析报错；B 修改异常日期处理代码",
    },
    {
        "type": "LEADS_TO_RETRY",
        "meaning": "促成重试：失败/阻断 → 同一目标的重新尝试",
        "required": "A 的失败或阻断明确促成 B 重试；可核查共同目标和重试依据",
        "excluded": "定时运行、普通迭代、两次相似命令但目标不同",
        "example": "A 请求超时；B 保持同一查询目标再次请求",
    },
    {
        "type": "LEADS_TO_VALIDATION",
        "meaning": "引出验证：待检验结果/假设/修改 → 实际检验行为",
        "required": "B 检查 A 对应的准确性、有效性或修改效果，有检验对象和检查记录",
        "excluded": "普通审批、读取但不检查、只计划验证、将任意后续执行称为验证",
        "example": "A 改正计算代码；B 用样本重新计算并核对预期值",
    },
    {
        "type": "AUTHORIZES",
        "meaning": "授权执行：明确批准/确认 → 受该批准约束的行动",
        "required": "A 是可核查的许可或选择；B 明确落实该许可；A 确实决定行动是否或如何进行",
        "excluded": "普通“好的”、系统成功状态、计划提交本身、事后确认",
        "example": "A 批准选定方案；B 按该方案开始此前等待批准的执行",
    },
    {
        "type": "CONTRIBUTES_TO_MERGE",
        "meaning": "汇入综合：分支产出 → 综合分析/汇总",
        "required": "A 是独立分析或子任务产出；B 明确把它纳入多个分支的汇合",
        "excluded": "工具返回就叫汇合、单一输入直接转发、分支结果未被采用",
        "example": "A 子 Agent 给出地区分析；B 联合地区与时间分析形成综合报告",
    },
    {
        "type": "SUPPORTS_RESULT",
        "meaning": "支撑结论：分析/验证证据 → 采用该证据的结论/交付",
        "required": "B 的可识别结论由 A 的结果或检验支撑，关键对象、数值和口径一致",
        "excluded": "单纯生成文件、摘要相似、计划支撑结果、结论没有实际采用证据",
        "example": "A 输出缺失率 30%；B 报告引用该缺失率并给出限制",
    },
    {
        "type": "CHALLENGED_BY",
        "meaning": "被质疑/反驳：原结果/假设 → 后续反证或质疑",
        "required": "B 明确指出 A 的问题、相反证据或失效条件；指向同一对象和口径",
        "excluded": "不同样本/时间/指标的数值差异、普通补充、自动认定所有差异为错误",
        "example": "A 报告全量均值；B 发现该计算漏掉一组数据，质疑此均值",
    },
    {
        "type": "SUPERSEDED_BY",
        "meaning": "被替代：旧方案/结果/要求 → 明确替代版本",
        "required": "B 明确更新或替代 A；可辨别共同对象和版本/范围变化；旧项不再作为当前依据",
        "excluded": "同路径再次写入、增加附录、并存方案、只有差异没有替代声明",
        "example": "A 使用旧筛选口径；B 明确撤销旧口径并确定新的任务口径",
    },
]
LOGICAL_TYPES = [entry["type"] for entry in CATALOG]
