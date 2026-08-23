"""
RWA 创业信息简报系统
简报生成模块 - 生成Markdown格式的每日简报
"""
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any
from collections import Counter

from .data_collector import NewsEvent
from .event_classifier import EventClassifier


class BriefingGenerator:
    """Markdown简报生成器"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
    
    def generate(
        self,
        events: List[NewsEvent],
        trend_summary: Dict[str, Any],
        mode: str = "daily"
    ) -> str:
        """
        生成完整的Markdown简报
        
        Args:
            events: 处理后的事件列表
            trend_summary: 标签趋势汇总
            mode: daily / major_only / weekly
            
        Returns:
            Markdown格式的简报文本
        """
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
        lines.append(f"")
        lines.append(f"> **发布时间**: {date_str} {now_bj.strftime('%H:%M')} (北京时间)")
        lines.append(f"> **本期涵盖**: 过去48小时RWA行业动态")
        lines.append(f"> **数据来源**: RSS订阅源 + 公开API + 模拟演示数据")
        lines.append(f"")
        
        # ========== 概览统计 ==========
        lines.append(self._generate_overview(events, mode))
        
        # ========== 头条 (仅高优先级) ==========
        headlines = [e for e in events if e.is_headline]
        if headlines:
            lines.append(self._generate_headlines_section(headlines))
        
        # ========== 高优先级事件 ==========
        high_events = [e for e in events if e.importance == "high" and not e.is_headline]
        if high_events:
            lines.append(self._generate_high_priority_section(high_events))
        
        # major_only模式下跳过中低优先级
        if mode != "major_only":
            # ========== 中优先级事件 ==========
            medium_events = [e for e in events if e.importance == "medium"]
            if medium_events:
                lines.append(self._generate_medium_priority_section(medium_events))
            
            # ========== 低优先级事件 (精简列表) ==========
            low_events = [e for e in events if e.importance == "low"]
            if low_events:
                lines.append(self._generate_low_priority_section(low_events))
        
        # ========== 分类板块：融资速递 ==========
        funding_events = [e for e in events if e.funding_amount is not None]
        if funding_events:
            lines.append(self._generate_funding_section(funding_events))
        
        # ========== 分类板块：监管动态 ==========
        policy_events = [
            e for e in events
            if e.matched_regions and ("合规" in e.tags or len(e.matched_regions) > 0)
        ]
        if policy_events:
            lines.append(self._generate_policy_section(policy_events))
        
        # ========== 分类板块：关注协议动态 ==========
        protocol_events = [e for e in events if e.matched_protocols]
        if protocol_events:
            lines.append(self._generate_protocol_section(protocol_events))
        
        # ========== 叙事趋势洞察 ==========
        lines.append(self._generate_trend_section(trend_summary, events))
        
        # ========== 页脚 ==========
        lines.append(self._generate_footer())
        
        return "\n".join(lines)
    
    # ============== 各板块生成 ==============
    
    def _generate_overview(self, events: List[NewsEvent], mode: str) -> str:
        """生成概览统计"""
        total = len(events)
        high = len([e for e in events if e.importance == "high"])
        medium = len([e for e in events if e.importance == "medium"])
        low = len([e for e in events if e.importance == "low"])
        funding_count = len([e for e in events if e.funding_amount is not None])
        total_funding = sum(e.funding_amount or 0 for e in events if e.funding_amount)
        
        # 统计热门标签
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
        lines.append(f"| 💵 融资总额 | **约 ${total_funding:,.0f} 万美元** |")
        lines.append("")
        
        if top_tags:
            lines.append("**🔥 本期热门标签**: ")
            tag_strs = [f"`{tag}`({cnt})" for tag, cnt in top_tags]
            lines.append(" · ".join(tag_strs))
            lines.append("")
        
        return "\n".join(lines)
    
    def _generate_headlines_section(self, events: List[NewsEvent]) -> str:
        """生成头条板块"""
        lines = []
        lines.append("## 🔴 头条关注")
        lines.append("")
        lines.append("> ⚡ AI判定为极度重要的事件，建议优先阅读")
        lines.append("")
        
        for i, event in enumerate(events, 1):
            lines.append(self._format_headline_news(i, event))
        
        return "\n".join(lines)
    
    def _format_headline_news(self, index: int, event: NewsEvent) -> str:
        """格式化单条头条新闻"""
        lines = []
        lines.append(f"### {index}. {event.title}")
        lines.append("")
        lines.append(self._format_metadata(event))
        lines.append("")
        lines.append(f"{event.summary}")
        lines.append("")
        lines.append(f"[🔗 阅读原文]({event.url})")
        lines.append("")
        lines.append("---")
        lines.append("")
        return "\n".join(lines)
    
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
        
        return "\n".join(lines)
    
    def _generate_medium_priority_section(self, events: List[NewsEvent]) -> str:
        """生成中优先级事件板块"""
        lines = []
        lines.append(f"## 🟡 中优先级事件 ({len(events)}条)")
        lines.append("")
        
        for event in events[:20]:  # 最多显示20条
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
        """生成低优先级事件板块（精简）"""
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
    
    def _generate_funding_section(self, events: List[NewsEvent]) -> str:
        """生成融资速递板块"""
        lines = []
        lines.append("## 💰 融资速递")
        lines.append("")
        
        # 按融资规模排序
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
            
            # 从summary提取投资方关键词
            investor_kw = self._extract_investors(event.summary)
            summary_short = investor_kw or event.summary[:30] + "..."
            
            lines.append(
                f"| **{protocol_str}** | {amount_display} | "
                f"{summary_short} | [{event.source}]({event.url}) |"
            )
        
        lines.append("")
        return "\n".join(lines)
    
    def _generate_policy_section(self, events: List[NewsEvent]) -> str:
        """生成监管动态板块"""
        lines = []
        lines.append("## 🏛️ 监管政策动态")
        lines.append("")
        
        # 按区域分组
        region_events = {}
        for event in events:
            for code in event.matched_regions:
                if code not in region_events:
                    region_events[code] = []
                region_events[code].append(event)
        
        # 获取区域中文名
        region_map = {
            r["code"]: r["name"] for r in self.config["REGIONS_WATCHLIST"]
        }
        
        for code, region_evts in sorted(region_events.items()):
            region_name = region_map.get(code, code)
            lines.append(f"### 🇭🇰 {region_name} ({code})")
            lines.append("")
            for event in region_evts:
                tags_str = " ".join([f"`{t}`" for t in event.tags[:3]])
                lines.append(f"- **[{event.title}]({event.url})** — {event.summary[:80]}... {tags_str}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _generate_protocol_section(self, events: List[NewsEvent]) -> str:
        """生成关注协议动态板块"""
        lines = []
        lines.append("## 🔍 关注协议动态")
        lines.append("")
        
        # 按协议分组
        proto_events = {}
        for event in events:
            for proto in event.matched_protocols:
                if proto not in proto_events:
                    proto_events[proto] = []
                proto_events[proto].append(event)
        
        for proto_name, proto_evts in proto_events.items():
            # 获取协议分类
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
    
    def _generate_trend_section(
        self,
        trend_summary: Dict[str, Any],
        events: List[NewsEvent]
    ) -> str:
        """生成叙事趋势洞察板块"""
        lines = []
        lines.append("## 📈 叙事趋势洞察")
        lines.append("")
        
        # 1. 趋势上升
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
        
        # 2. 趋势下降
        trending_down = trend_summary.get("trending_down", [])
        if trending_down:
            lines.append("### 📉 下降趋势标签")
            lines.append("")
            for tag, growth, count in trending_down:
                growth_pct = growth * 100
                lines.append(f"- **{tag}**: {growth_pct:.0f}% (本周出现{count}次)")
            lines.append("")
        
        # 3. 本周Top标签（用ASCII条形图）
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
        
        # 4. AI洞察总结
        lines.append("### 💡 AI洞察")
        lines.append("")
        insight = self._generate_ai_insight(trend_summary, events)
        lines.append(insight)
        lines.append("")
        
        return "\n".join(lines)
    
    def _generate_ai_insight(
        self,
        trend_summary: Dict[str, Any],
        events: List[NewsEvent]
    ) -> str:
        """生成AI洞察摘要（基于规则，可接入LLM增强）"""
        insights = []
        
        trending_up = trend_summary.get("trending_up", [])
        funding_events = [e for e in events if e.funding_amount is not None]
        policy_events = [e for e in events if e.matched_regions]
        big_inst = self.config["IMPORTANCE_RULES"]["BIG_INSTITUTIONS"]
        
        # 检查机构动向
        has_big_institution = any(
            inst.lower() in e.raw_content.lower()
            for e in events
            for inst in big_inst
        )
        
        # 1. 上升趋势提示
        if trending_up:
            top_trend = trending_up[0]
            insights.append(
                f"📈 **「{top_trend[0]}」**叙事热度持续上升(+{top_trend[1]*100:.0f}%)，"
                f"建议重点关注相关项目动态。"
            )
        
        # 2. 融资热度
        total_funding = sum(e.funding_amount or 0 for e in funding_events)
        if total_funding >= 3000:
            insights.append(
                f"💰 本期行业融资活跃，累计融资超过 **${total_funding:,.0f}万美元**，"
                f"显示一级市场对RWA赛道信心充足。"
            )
        
        # 3. 监管信号
        hk_or_sg_policy = any(
            code in ["HK", "SG"] for e in policy_events for code in e.matched_regions
        )
        if hk_or_sg_policy:
            insights.append(
                "🏛️ **香港/新加坡**监管动态频繁，亚洲RWA中心格局正在加速形成，"
                "项目方可考虑优先布局该区域合规框架。"
            )
        elif policy_events:
            insights.append(
                "🏛️ 本期监管动态值得关注，建议跟踪政策走向，提前做好合规准备。"
            )
        
        # 4. 机构入场
        if has_big_institution:
            insights.append(
                "🏦 传统金融机构动作频繁，机构资本持续入场RWA赛道，"
                "可能带动下一阶段的市场情绪和项目估值上升。"
            )
        
        if not insights:
            insights.append(
                "📊 本期行业整体平稳，建议持续关注关注列表协议的技术迭代和融资进展。"
            )
        
        return "\n\n".join(insights)
    
    def _generate_footer(self) -> str:
        """生成页脚"""
        lines = []
        lines.append("---")
        lines.append("")
        lines.append("### ⚙️ 配置与定制")
        lines.append("")
        lines.append("本简报的分类规则、优先级权重、关注列表均可通过修改 `config.yaml` 定制：")
        lines.append("")
        lines.append("| 配置项 | 说明 | 位置 |")
        lines.append("|--------|------|------|")
        lines.append("| WATCHLIST_PROTOCOLS | 关注的协议（命中即高优先级） | config.yaml |")
        lines.append("| FUNDING_THRESHOLD | 融资重大事件阈值 | config.yaml |")
        lines.append("| REGIONS_WATCHLIST | 关注的监管区域 | config.yaml |")
        lines.append("| NARRATIVE_TAGS | 叙事标签与关键词 | config.yaml |")
        lines.append("| IMPORTANCE_RULES | AI重要性评分权重 | config.yaml |")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("*🤖 本简报由 RWA创业信息简报系统 自动生成 | 数据仅供参考，不构成投资建议*")
        lines.append("")
        return "\n".join(lines)
    
    # ============== 工具方法 ==============
    
    def _format_metadata(self, event: NewsEvent) -> str:
        """格式化事件元数据行"""
        parts = []
        
        # 重要程度
        imp_map = {
            "high": ("🔴 高", "red"),
            "medium": ("🟡 中", "yellow"),
            "low": ("🟢 低", "green")
        }
        imp_label, _ = imp_map.get(event.importance, ("⚪ 未知", ""))
        parts.append(f"**重要性**: {imp_label} ({event.importance_score:.0f}分)")
        
        # 发布时间
        parts.append(f"**时间**: {self._format_time_short(event)}")
        
        # 来源
        parts.append(f"**来源**: {event.source}")
        
        # 融资
        if event.funding_amount:
            parts.append(f"**融资**: ${event.funding_amount:,.0f}万")
        
        line = " · ".join(parts)
        
        # 标签
        if event.tags:
            tags_str = " ".join([f"`{t}`" for t in event.tags[:5]])
            line += f"\n\n🏷️ {tags_str}"
        
        # 匹配协议/区域
        matches = []
        if event.matched_protocols:
            matches.append("📋 " + ", ".join(event.matched_protocols))
        if event.matched_regions:
            matches.append("🌍 " + ", ".join(event.matched_regions))
        if matches:
            line += "\n\n" + " · ".join(matches)
        
        return line
    
    def _format_time_short(self, event: NewsEvent) -> str:
        """简化的时间格式（相对时间）"""
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
            "a16z", "a16 z", "andreessen",
            "红杉", "sequoia",
            "coinbase", "coinbase ventures",
            "binance", "币安", "binance labs",
            "paradigm",
            "dragonfly", "蜻蜓",
            "polychain",
            "pantera",
            "multicoin",
            "variant",
            "领投", "跟投", "参投"
        ]
        text_lower = text.lower()
        found = []
        for kw in investor_keywords:
            if kw.lower() in text_lower:
                found.append(kw)
        return "、".join(found[:3]) if found else ""
