# AI 网文工作流调研

核查日期为2026年11月4日。GitHub 样本检查了公开说明及列出的流程或代码。视频平台核对了公开视频页面、分集目录和可读摘要。样本能说明做法，作者自述的产量或签约宣传缺少独立结果佐证。

| 来源 | 实际做法 | 本包的采用方式 |
|---|---|---|
| [novel-writing-workflow](https://github.com/ZiffChow/novel-writing-workflow/blob/main/references/setup_and_loop.md) | 正式运行前用3—5章测试流程。逐章推演、成稿、审查、沉淀事实，再版本化备份。 | 把试错再前移。首章写前做两种短开场，冻结前做正文裁定。原有五章回看保留。 |
| [Webnovel Writer 的写前资料](https://github.com/lingfengQAQ/webnovel-writer/blob/master/webnovel-writer/agents/context-agent.md)与[节奏审查](https://github.com/lingfengQAQ/webnovel-writer/blob/master/webnovel-writer/skills/webnovel-review/references/pacing-control.md) | 只把与本章相关的动机、伏笔、边界与节奏交给写作阶段。区分有效剧情变化和重复铺垫。 | 在已有任务书固定行动与结果，在报告定位最弱段落。段落的情绪、人物及线索价值也参与裁定。 |
| [Pagekin 的按意见修稿代码](https://github.com/EthanYoQ/AI-Novel-Writer/blob/master/src/services/workflows/commands/refine-from-review.command.ts) | 按成立的问题定范围，核对前文后修稿。要求该发生的行动与代价在正文中实际发生。 | 引用分别落到行动与结果，阻断影响剧情推进的缺陷。修后复核前后状态，减少无关改写。 |
| [B站 星月写作的全流程分集](https://www.bilibili.com/video/BV1JLpLetErj/) | 公开分集有词条卡、大纲、人设、细纲、正文和开篇修改。 | 采用先细化近章再写正文的分工。开篇样本只研究冲突和兑现机制，独立设计事件。 |
| [B站 二ser的课程目录](https://www.bilibili.com/cheese/play/ep2437348) | 公开目录列出开篇、冲突、节奏、对白和冷读诊断课程。课程付费，核查范围为公开目录。 | 用已有的限信息资料先读正文，再核对大纲。报告如实记录审读模式。 |
| [抖音 AI写网文工作台样板](https://www.douyin.com/video/7443312901470932283) | Obsidian 把构思和正文分开，并整理按场景调用的扩写、改写和润色提示。页面摘要显示 AI 功能依赖另配 API。 | 在原 GitHub 目录保留分层，按已找到的问题调用专项方法。执行依赖为现有 GPT 入口和本包文件工具。 |

样本中的一致性维护与本项目现有流程重合较多。此次新增的重心是每章能否交付读者所期待的变化。角色、物资、时间线都对得上，仍可能几千字只走完手续。为此，题材选择阶段先比较开篇因果，写前说清本章要交付什么，写后用实际原文校验。前三章的短期问题须形成一次完整结果。
