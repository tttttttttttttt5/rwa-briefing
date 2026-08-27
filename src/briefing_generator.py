"""
RWA 创业信息简报系统
简报生成模块 - 资深投研视角
"""
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any
from collections import Counter

from .data_collector import NewsEvent
from .event_classifier import EventClassifier


class BriefingGenerator:
    """Markdown简报生成器 - 资深投研版"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def generate(
        self,
        events: List[NewsEvent],
        trend_summary: Dict[str, Any],
        mode: str = "daily"
    ) -> str:
        """生成完整的Markdown简报"""
        now = datetime.now(timezone.utc)
        beijing_tz = timezone(timedelta(hours=8))
        now_bj = now.astimezone(beijing_tz)

        lines = []

        # ========== 标题 ==========
        title_suffix = {
            "daily": "每日简报",
            "major_only": "重大事件特报",
            "weekly": "每周汇总"
        }.get(mode, "简报")

        date_str = now_bj.strftime("%Y年%m月%d日")
        lines.append(f"# 📰 RWA创业信息{title_suffix}")
        lines.append("")
        lines.append(f"> **发布时间**: {date_str} {now_bj.strftime('%H:%M')} (北京时间)")
        lines.append(f"> **数据来源**: Cointelegraph / Decrypt / TheDefiant / CoinGape / WebSearch")
        lines.append("")

        # ========== 核心摘要（放最前面，看完就懂） ==========
        lines.append(self._generate_executive_summary(events, trend_summary))

        # ========== 概览统计 ==========
        lines.append(self._generate_overview(events, mode))

        # ========== 头条 ==========
        headlines = [e for e in events if e.is_headline]
        if headlines:
            lines.append(self._generate_headlines_section(headlines))

        # ========== 高优先级事件 ==========
        high_events = [e for e in events if e.importance == "high" and not e.is_headline]
        if high_events:
            lines.append(self._generate_high_priority_section(high_events))

        if mode != "major_only":
            medium_events = [e for e in events if e.importance == "medium"]
            if medium_events:
                lines.append(self._generate_medium_priority_section(medium_events))

            low_events = [e for e in events if e.importance == "low"]
            if low_events:
                lines.append(self._generate_low_priority_section(low_events))

        # ========== 融资速递 ==========
        funding_events = [e for e in events if e.funding_amount is not None]
        if funding_events:
            lines.append(self._generate_funding_section(funding_events))

        # ========== 监管动态 ==========
        policy_events = [
            e for e in events
            if e.matched_regions and ("合规" in e.tags or len(e.matched_regions) > 0)
        ]
        if policy_events:
            lines.append(self._generate_policy_section(policy_events))

        # ========== 关注协议动态 ==========
        protocol_events = [e for e in events if e.matched_protocols]
        if protocol_events:
            lines.append(self._generate_protocol_section(protocol_events))

        # ========== 叙事趋势 ==========
        lines.append(self._generate_trend_section(trend_summary, events))

        # ========== 投研总结（放最后，总结全文） ==========
        lines.append(self._generate_research_summary(events, trend_summary))

        # ========== 页脚 ==========
        lines.append(self._generate_footer())

        return "\n".join(lines)

    # ============== 核心摘要 ==============

    def _generate_executive_summary(
        self,
        events: List[NewsEvent],
        trend_summary: Dict[str, Any]
    ) -> str:
        """生成核心摘要 - 放最前面，3-5句话看完就懂"""
        lines = []
        lines.append("## 📌 核心摘要")
        lines.append("")

        high = [e for e in events if e.importance == "high"]
        funding_events = [e for e in events if e.funding_amount is not None]
        total_funding = sum(e.funding_amount or 0 for e in funding_events)

        # 统计核心信号
        signals = []

        # 1. 融资信号
        if funding_events and total_funding > 0:
            top_funding = max(funding_events, key=lambda e: e.funding_amount or 0)
            signals.append(
                f"💰 **融资活跃**: 本期追踪到 {len(funding_events)} 起融资事件，"
                f"累计约 ${total_funding:,.0f} 万美元。"
                f"最大单笔为「{top_funding.title[:40]}...」(${top_funding.funding_amount:,.0f}万美元)。"
            )

        # 2. 机构动向信号
        big_inst = self.config["IMPORTANCE_RULES"]["BIG_INSTITUTIONS"]
        inst_events = [
            e for e in events
            if any(inst.lower() in e.raw_content.lower() for inst in big_inst)
        ]
        if inst_events:
            inst_names = set()
            for e in inst_events:
                for inst in big_inst:
                    if inst.lower() in e.raw_content.lower():
                        inst_names.add(inst)
            signals.append(
                f"🏦 **机构入场**: 检测到 {len(inst_events)} 条涉及传统金融机构的动态"
                f"（{'/'.join(list(inst_names)[:3])}等），"
                f"机构资本持续进入RWA赛道。"
            )

        # 3. 监管信号
        policy_events = [e for e in events if e.matched_regions]
        if policy_events:
            regions_hit = set()
            for e in policy_events:
                for code in e.matched_regions:
                    regions_hit.add(code)
            signals.append(
                f"🏛️ **监管动态**: {len(policy_events)} 条涉及"
                f"{'、'.join(list(regions_hit)[:4])}等区域的监管/政策信息。"
            )

        # 4. 趋势信号
        trending_up = trend_summary.get("trending_up", [])
        if trending_up:
            top_tag = trending_up[0]
            signals.append(
                f"📈 **叙事趋势**: 「{top_tag[0]}」标签热度上升 {top_tag[1]*100:.0f}%，"
                f"为当前最值得关注的方向。"
            )

        # 5. 整体判断
        if high:
            signals.append(
                f"⚡ **关键判断**: 本期有 {len(high)} 条高优先级事件，"
                f"{'RWA赛道整体处于活跃期，建议加快研究节奏。' if len(high) >= 3 else '需关注个别事件对细分赛道的影响。'}"
            )

        if not signals:
            signals.append(
                "📊 本期整体平稳，建议持续关注关注列表协议的技术迭代和融资进展。"
            )

        for s in signals:
            lines.append(f"- {s}")

        lines.append("")
        return "\n".join(lines)

    # ============== 概览统计 ==============

    def _generate_overview(self, events: List[NewsEvent], mode: str) -> str:
        """生成概览统计"""
        total = len(events)
        high = len([e for e in events if e.importance == "high"])
        medium = len([e for e in events if e.importance == "medium"])
        low = len([e for e in events if e.importance == "low"])
        funding_count = len([e for e in events if e.funding_amount is not None])
        total_funding = sum(e.funding_amount or 0 for e in events if e.funding_amount)

        all_tags = []
        for e in events:
            all_tags.extend(e.tags)
        tag_counter = Counter(all_tags)
        top_tags = tag_counter.most_common(5)

        lines = []
        lines.append("## 📊 本期概览")
        lines.append("")
        lines.append(f"| 指标 | 数值 |")
        lines.append(f"|------|------|")
        lines.append(f"| 📰 动态总数 | **{total}** 条 |")
        lines.append(f"| 🔴 高优先级 | **{high}** 条 |")
        lines.append(f"| 🟡 中优先级 | **{medium}** 条 |")
        lines.append(f"| 🟢 低优先级 | **{low}** 条 |")
        lines.append(f"| 💰 融资事件 | **{funding_count}** 起 |")
        if total_funding > 0:
            lines.append(f"| 💵 融资总额 | **约 ${total_funding:,.0f} 万美元** |")
        lines.append("")

        if top_tags:
            lines.append("**🔥 本期热门标签**: ")
            tag_strs = [f"`{tag}`({cnt})" for tag, cnt in top_tags]
            lines.append(" · ".join(tag_strs))
            lines.append("")

        return "\n".join(lines)

    # ============== 头条 ==============

    def _generate_headlines_section(self, events: List[NewsEvent]) -> str:
        """生成头条板块 - 含投研分析"""
        lines = []
        lines.append("## 🔴 头条关注")
        lines.append("")
        lines.append("> ⚡ AI判定为极度重要的事件，含资深投研分析")
        lines.append("")

        for i, event in enumerate(events, 1):
            lines.append(self._format_headline_news(i, event))

        return "\n".join(lines)

    def _format_headline_news(self, index: int, event: NewsEvent) -> str:
        """格式化单条头条新闻 - 含投研分析"""
        lines = []
        lines.append(f"### {index}. {event.title}")
        lines.append("")
        lines.append(self._format_metadata(event))
        lines.append("")
        lines.append(f"{event.summary}")
        lines.append("")
        lines.append(f"[🔗 阅读原文]({event.url})")
        lines.append("")

        # 投研分析
        analysis = self._generate_event_analysis(event)
        if analysis:
            lines.append(f"**💡 投研分析**:")
            lines.append("")
            lines.append(f"> {analysis}")
            lines.append("")

        lines.append("---")
        lines.append("")
        return "\n".join(lines)

    def _generate_event_analysis(self, event: NewsEvent) -> str:
        """为单个事件生成资深投研分析"""
        analyses = []
        content = event.raw_content.lower()
        title = event.title

        # 融资事件分析
        if event.funding_amount and event.funding_amount > 0:
            amount = event.funding_amount
            if amount >= 5000:
                analyses.append(
                    f"融资规模达 ${amount:,.0f}万美元，属于行业重大融资事件。"
                    f"这一量级的融资通常意味着机构对该方向有长期信心，"
                    f"值得跟踪该项目后续的产品路线图和上币计划。"
                )
            elif amount >= 1000:
                analyses.append(
                    f"融资规模 ${amount:,.0f}万美元处于中高区间，"
                    f"在当前RWA赛道属于有竞争力的轮次。"
                    f"关注投资方背景和资金用途分配。"
                )
            else:
                analyses.append(
                    f"融资 ${amount:,.0f}万美元属于早期/种子轮量级，"
                    f"适合关注团队背景和产品方向，但不宜过度解读短期影响。"
                )

        # 机构动向分析
        big_inst = self.config["IMPORTANCE_RULES"]["BIG_INSTITUTIONS"]
        for inst in big_inst:
            if inst.lower() in content:
                analyses.append(
                    f"涉及传统金融巨头{inst}，机构入场信号明确。"
                    f"大机构的参与通常带来合规背书和资金体量提升，"
                    f"但也可能加速赛道整合，小团队需关注竞争格局变化。"
                )
                break

        # 监管政策分析
        if event.matched_regions:
            region_names = []
            for code in event.matched_regions:
                region_config = next(
                    (r for r in self.config["REGIONS_WATCHLIST"] if r["code"] == code),
                    None
                )
                if region_config:
                    region_names.append(region_config["name"])

            if "合规" in event.tags:
                analyses.append(
                    f"涉及{'、'.join(region_names)}的监管合规动态。"
                    f"政策走向直接影响RWA项目在该区域的合法性和落地速度，"
                    f"建议将相关区域列入合规优先级观察名单。"
                )
            else:
                analyses.append(
                    f"涉及{'、'.join(region_names)}市场动态，"
                    f"关注该区域的监管态度和机构参与度变化。"
                )

        # 叙事标签分析
        if "代币化" in event.tags and "收益产品" in event.tags:
            analyses.append(
                f"同时命中「代币化」和「收益产品」双标签，"
                f"属于RWA赛道中最核心的『生息资产代币化』方向，"
                f"这是目前机构资金最集中的细分领域。"
            )
        elif "流动性" in event.tags:
            analyses.append(
                f"命中「流动性」标签，二级市场流动性是RWA资产定价效率的关键，"
                f"做市深度提升将降低买卖价差，有利于机构大额进出场。"
            )
        elif "定价" in event.tags:
            analyses.append(
                f"命中「定价」标签，资产定价机制是RWA基础设施的核心环节，"
                f"准确的链上定价是后续DeFi组合性的基础。"
            )

        # 协议匹配分析
        if event.matched_protocols:
            proto_names = [p.upper() for p in event.matched_protocols[:3]]
            analyses.append(
                f"命中关注协议: {'/'.join(proto_names)}。"
                f"建议查看该协议官方文档和链上数据，"
                f"验证新闻信息与实际进展是否一致。"
            )

        if not analyses:
            # 默认分析
            if event.importance == "high":
                analyses.append(
                    f"该事件综合评分较高({event.importance_score:.0f}分)，"
                    f"涉及多个重要维度交叉，建议优先阅读原文并跟踪后续发展。"
                )

        return "\n\n".join(analyses[:3])  # 最多3条分析

    # ============== 高优先级 ==============

    def _generate_high_priority_section(self, events: List[NewsEvent]) -> str:
        """生成高优先级事件板块"""
        lines = []
        lines.append("## ⚡ 高优先级事件")
        lines.append("")

        for i, event in enumerate(events, 1):
            lines.append(f"**{i}. [{event.title}]({event.url})**")
            lines.append("")
            lines.append(self._format_metadata(event))
            lines.append("")
            lines.append(f"> {event.summary}")
            lines.append("")

            # 简短投研分析
            analysis = self._generate_event_analysis(event)
            if analysis:
                lines.append(f"> 💡 {analysis[:200]}")
                lines.append("")

        return "\n".join(lines)

    # ============== 中/低优先级 ==============

    def _generate_medium_priority_section(self, events: List[NewsEvent]) -> str:
        """生成中优先级事件板块"""
        lines = []
        lines.append(f"## 🟡 中优先级事件 ({len(events)}条)")
        lines.append("")

        for event in events[:20]:
            title = event.title.replace("|", "\\|")
            tags_str = " ".join([f"`{t}`" for t in event.tags[:3]])
            time_str = self._format_time_short(event)
            lines.append(
                f"- **[{title}]({event.url})** "
                f"| {time_str} | {event.source} | 得分 {event.importance_score:.0f} "
                f"{tags_str}"
            )

        if len(events) > 20:
            lines.append(f"- ... 及其他 {len(events) - 20} 条中优先级事件")

        lines.append("")
        return "\n".join(lines)

    def _generate_low_priority_section(self, events: List[NewsEvent]) -> str:
        """生成低优先级事件板块"""
        lines = []
        lines.append(f"## 🟢 其他动态 ({len(events)}条)")
        lines.append("")
        lines.append("<details>")
        lines.append("<summary>点击展开查看全部</summary>")
        lines.append("")

        for event in events[:30]:
            lines.append(f"- [{event.title}]({event.url}) — {event.source}")

        if len(events) > 30:
            lines.append(f"- ... 及其他 {len(events) - 30} 条")

        lines.append("")
        lines.append("</details>")
        lines.append("")
        return "\n".join(lines)

    # ============== 融资速递 ==============

    def _generate_funding_section(self, events: List[NewsEvent]) -> str:
        """生成融资速递板块"""
        lines = []
        lines.append("## 💰 融资速递")
        lines.append("")

        sorted_events = sorted(
            events,
            key=lambda e: e.funding_amount or 0,
            reverse=True
        )

        lines.append("| 项目/协议 | 融资金额 | 投资方/说明 | 来源 |")
        lines.append("|-----------|----------|-------------|------|")

        for event in sorted_events:
            amount = event.funding_amount or 0
            if amount >= 5000:
                amount_display = f"🔴 **${amount:,.0f}万**"
            elif amount >= 1000:
                amount_display = f"🟠 **${amount:,.0f}万**"
            elif amount >= 300:
                amount_display = f"🟡 ${amount:,.0f}万"
            else:
                amount_display = f"🟢 ${amount:,.0f}万"

            protocol_str = ", ".join(event.matched_protocols) if event.matched_protocols else "-"
            investor_kw = self._extract_investors(event.summary)
            summary_short = investor_kw or event.summary[:40] + "..."

            lines.append(
                f"| **{protocol_str}** | {amount_display} | "
                f"{summary_short} | [{event.source}]({event.url}) |"
            )

        lines.append("")
        return "\n".join(lines)

    # ============== 监管动态 ==============

    def _generate_policy_section(self, events: List[NewsEvent]) -> str:
        """生成监管动态板块"""
        lines = []
        lines.append("## 🏛️ 监管政策动态")
        lines.append("")

        region_events = {}
        for event in events:
            for code in event.matched_regions:
                if code not in region_events:
                    region_events[code] = []
                region_events[code].append(event)

        region_map = {
            r["code"]: r["name"] for r in self.config["REGIONS_WATCHLIST"]
        }

        for code, region_evts in sorted(region_events.items()):
            region_name = region_map.get(code, code)
            lines.append(f"### {region_name} ({code})")
            lines.append("")
            for event in region_evts:
                tags_str = " ".join([f"`{t}`" for t in event.tags[:3]])
                lines.append(f"- **[{event.title}]({event.url})** — {event.summary[:100]}... {tags_str}")
            lines.append("")

        return "\n".join(lines)

    # ============== 关注协议动态 ==============

    def _generate_protocol_section(self, events: List[NewsEvent]) -> str:
        """生成关注协议动态板块"""
        lines = []
        lines.append("## 🔍 关注协议动态")
        lines.append("")

        proto_events = {}
        for event in events:
            for proto in event.matched_protocols:
                if proto not in proto_events:
                    proto_events[proto] = []
                proto_events[proto].append(event)

        for proto_name, proto_evts in proto_events.items():
            proto_detail = next(
                (p for p in self.config["WATCHLIST_PROTOCOLS"] if p["name"].lower() == proto_name),
                {}
            )
            category = proto_detail.get("category", "")
            boost = proto_detail.get("priority_boost", False)
            boost_icon = "⭐" if boost else ""

            lines.append(f"### {boost_icon} **{proto_name.capitalize()}** {category}")
            lines.append("")
            for event in proto_evts:
                imp_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(event.importance, "⚪")
                lines.append(
                    f"- {imp_icon} [{event.title}]({event.url}) — "
                    f"{event.source} · 得分{event.importance_score:.0f}"
                )
            lines.append("")

        return "\n".join(lines)

    # ============== 叙事趋势 ==============

    def _generate_trend_section(
        self,
        trend_summary: Dict[str, Any],
        events: List[NewsEvent]
    ) -> str:
        """生成叙事趋势洞察板块"""
        lines = []
        lines.append("## 📈 叙事趋势洞察")
        lines.append("")

        trending_up = trend_summary.get("trending_up", [])
        if trending_up:
            lines.append("### 🚀 上升趋势标签")
            lines.append("")
            for tag, growth, count in trending_up:
                growth_pct = growth * 100
                bar_length = min(20, int(growth * 5) + 5)
                bar = "█" * bar_length
                lines.append(f"- **{tag}**: {bar} +{growth_pct:.0f}% (本周出现{count}次)")
            lines.append("")

        trending_down = trend_summary.get("trending_down", [])
        if trending_down:
            lines.append("### 📉 下降趋势标签")
            lines.append("")
            for tag, growth, count in trending_down:
                growth_pct = growth * 100
                lines.append(f"- **{tag}**: {growth_pct:.0f}% (本周出现{count}次)")
            lines.append("")

        top_tags = trend_summary.get("top_tags", [])
        if top_tags:
            lines.append("### 📊 近30天标签热度排行")
            lines.append("")
            max_count = max([c for _, c in top_tags]) if top_tags else 1
            for tag, count in top_tags[:8]:
                bar_len = int(count / max(max_count, 1) * 20)
                bar = "▓" * bar_len + "░" * (20 - bar_len)
                lines.append(f"`{tag:<8}` |{bar}| {count}次")
            lines.append("")

        return "\n".join(lines)

    # ============== 投研总结 ==============

    def _generate_research_summary(
        self,
        events: List[NewsEvent],
        trend_summary: Dict[str, Any]
    ) -> str:
        """生成资深投研总结 - 放最后，看完就对用户有帮助"""
        lines = []
        lines.append("## 🎯 投研总结与行动建议")
        lines.append("")

        # 1. 本期核心判断
        lines.append("### 一、本期核心判断")
        lines.append("")

        high = [e for e in events if e.importance == "high"]
        funding_events = [e for e in events if e.funding_amount is not None]
        total_funding = sum(e.funding_amount or 0 for e in funding_events)
        trending_up = trend_summary.get("trending_up", [])

        judgments = []

        # 赛道温度
        if len(high) >= 3 and total_funding > 5000:
            judgments.append(
                f"📊 **赛道温度: 偏热**。本期高优先级事件{len(high)}条、"
                f"融资总额${total_funding:,.0f}万美元，"
                f"RWA赛道处于明显的资金涌入期和叙事升温期。"
            )
        elif len(high) >= 1:
            judgments.append(
                f"📊 **赛道温度: 温和**。有{len(high)}条高优先级事件，"
                f"行业保持正常节奏发展，无异常过热或降温信号。"
            )
        else:
            judgments.append(
                f"📊 **赛道温度: 偏冷**。本期无高优先级事件，"
                f"建议关注是否有重大事件被遗漏，或赛道确实进入平静期。"
            )

        # 叙事方向
        if trending_up:
            top3_tags = [t[0] for t in trending_up[:3]]
            judgments.append(
                f"🎯 **叙事方向**: 当前上升最快的标签是"
                f"{'、'.join(top3_tags)}。"
                f"这些方向可能是下一阶段资金和项目涌入的重点，"
                f"建议优先在这些细分领域寻找机会。"
            )

        # 机构参与度
        big_inst = self.config["IMPORTANCE_RULES"]["BIG_INSTITUTIONS"]
        inst_events = [
            e for e in events
            if any(inst.lower() in e.raw_content.lower() for inst in big_inst)
        ]
        if inst_events:
            judgments.append(
                f"🏦 **机构参与度: 高**。检测到{len(inst_events)}条机构相关动态，"
                f"传统金融资本持续入场RWA，验证了赛道的长期价值判断。"
                f"但需注意机构入场也意味着竞争加剧和合规门槛提高。"
            )

        for j in judgments:
            lines.append(f"- {j}")
        lines.append("")

        # 2. 需要持续跟踪的事项
        lines.append("### 二、需持续跟踪的事项")
        lines.append("")
        track_items = []

        # 跟踪融资项目的后续
        for e in funding_events[:3]:
            track_items.append(
                f"📈 关注「{e.title[:30]}...」的后续进展："
                f"资金到账后的产品迭代、上币计划和社区运营节奏。"
            )

        # 跟踪监管政策
        policy_events = [e for e in events if e.matched_regions and "合规" in e.tags]
        for e in policy_events[:2]:
            track_items.append(
                f"🏛️ 跟踪「{e.title[:30]}...」的落地时间表和实施细则，"
                f"评估对自身项目的合规影响。"
            )

        if not track_items:
            track_items.append(
                "📊 本期无特别需要紧急跟踪的事项，建议持续关注"
                "关注列表中各协议的TVL变化和链上活跃度。"
            )

        for item in track_items:
            lines.append(f"- {item}")
        lines.append("")

        # 3. 行动建议
        lines.append("### 三、行动建议")
        lines.append("")
        actions = []

        if total_funding > 5000:
            actions.append(
                "1. **加快融资节奏**: 赛道融资活跃，机构风险偏好上升，"
                "是启动或加速融资的好时机。建议准备好Deck和数据。"
            )
        else:
            actions.append(
                "1. **打磨产品**: 融资热度一般，建议专注产品打磨和用户增长数据，"
                "等待更好的市场窗口。"
            )

        if trending_up:
            top_tag = trending_up[0][0]
            actions.append(
                f"2. **聚焦热门叙事**: 「{top_tag}」是当前热度最高的方向，"
                f"建议在产品定位和对外PR中强化该标签。"
            )

        if inst_events:
            actions.append(
                "3. **机构合作准备**: 机构入场趋势明确，"
                "建议提前准备机构级API、合规审计报告和托管方案。"
            )

        if policy_events:
            actions.append(
                "4. **合规优先**: 检测到多条监管动态，"
                "建议尽快与法律顾问确认自身业务的合规框架，"
                "优先布局监管明确的区域（如香港、新加坡）。"
            )

        actions.append(
            "5. **信息源扩展**: 建议持续关注 rwa.xyz 链上数据、"
            "各协议官方Discord公告和项目方Medium博客，"
            "获取第一手信息。"
        )

        for a in actions:
            lines.append(f"- {a}")
        lines.append("")

        # 4. 风险提示
        lines.append("### 四、风险提示")
        lines.append("")
        risks = []

        if len(high) >= 5:
            risks.append(
                "⚠️ 本期高优先级事件密集，需警惕信息过载导致的判断偏差，"
                "建议聚焦2-3个核心方向深入研究。"
            )

        if total_funding > 10000:
            risks.append(
                "⚠️ 融资规模偏大，需注意赛道可能出现过热迹象，"
                "估值偏高时不宜追高。"
            )

        risks.append(
            "⚠️ RWA赛道监管政策仍在演变中，特别是中国境内明确禁止RWA代币化活动，"
            "项目方需严格区分境内境外业务。"
        )
        risks.append(
            "⚠️ 以上分析基于公开信息自动生成，不构成投资建议。"
            "实际决策需结合链上数据、团队尽调和法律意见。"
        )

        for r in risks:
            lines.append(f"- {r}")
        lines.append("")

        return "\n".join(lines)

    # ============== 工具方法 ==============

    def _format_metadata(self, event: NewsEvent) -> str:
        """格式化事件元数据行"""
        parts = []

        imp_map = {
            "high": "🔴 高",
            "medium": "🟡 中",
            "low": "🟢 低"
        }
        imp_label = imp_map.get(event.importance, "⚪ 未知")
        parts.append(f"**重要性**: {imp_label} ({event.importance_score:.0f}分)")
        parts.append(f"**时间**: {self._format_time_short(event)}")
        parts.append(f"**来源**: {event.source}")

        if event.funding_amount:
            parts.append(f"**融资**: ${event.funding_amount:,.0f}万")

        line = " · ".join(parts)

        if event.tags:
            tags_str = " ".join([f"`{t}`" for t in event.tags[:5]])
            line += f"\n\n🏷️ {tags_str}"

        matches = []
        if event.matched_protocols:
            matches.append("📋 " + ", ".join(event.matched_protocols))
        if event.matched_regions:
            matches.append("🌍 " + ", ".join(event.matched_regions))
        if matches:
            line += "\n\n" + " · ".join(matches)

        return line

    def _format_time_short(self, event: NewsEvent) -> str:
        """简化的时间格式"""
        now = datetime.now(timezone.utc)
        delta = now - event.published_at
        hours = int(delta.total_seconds() / 3600)
        if hours < 1:
            minutes = max(1, int(delta.total_seconds() / 60))
            return f"{minutes}分钟前"
        elif hours < 24:
            return f"{hours}小时前"
        else:
            days = int(hours / 24)
            return f"{days}天前"

    def _extract_investors(self, text: str) -> str:
        """从文本中提取投资方关键词"""
        investor_keywords = [
            "a16z", "andreessen", "红杉", "sequoia",
            "coinbase ventures", "binance labs", "币安实验室",
            "paradigm", "dragonfly", "蜻蜓", "polychain",
            "pantera", "multicoin", "variant",
            "animoca", "okx ventures", "mh ventures",
            "领投", "跟投", "参投", "seed", "series a", "series b"
        ]
        text_lower = text.lower()
        found = []
        for kw in investor_keywords:
            if kw.lower() in text_lower:
                found.append(kw)
        return "、".join(found[:3]) if found else ""

    def _generate_footer(self) -> str:
        """生成页脚"""
        lines = []
        lines.append("---")
        lines.append("")
        lines.append("### ⚙️ 配置与定制")
        lines.append("")
        lines.append("本简报的分类规则、优先级权重、关注列表均可通过修改 `config.yaml` 定制：")
        lines.append("")
        lines.append("| 配置项 | 说明 |")
        lines.append("|--------|------|")
        lines.append("| WATCHLIST_PROTOCOLS | 关注的协议（命中即高优先级） |")
        lines.append("| FUNDING_THRESHOLD | 融资重大事件阈值 |")
        lines.append("| REGIONS_WATCHLIST | 关注的监管区域 |")
        lines.append("| NARRATIVE_TAGS | 叙事标签与关键词 |")
        lines.append("| IMPORTANCE_RULES | AI重要性评分权重 |")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("*🤖 本简报由 RWA创业信息简报系统 自动生成 | 数据来自公开RSS源和WebSearch | 仅供参考，不构成投资建议*")
        lines.append("")
        return "\n".join(lines)
