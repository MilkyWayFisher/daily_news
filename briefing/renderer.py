from __future__ import annotations

from collections import defaultdict

from briefing.guardrails import sanitize_text
from briefing.models import Briefing, EventCluster, MacroIndicator, MarketPoint
from briefing.zh_formatter import (
    category_zh,
    confidence_zh,
    direction_zh,
    format_data_window,
    format_local_time,
    risk_factor_zh,
    score_bucket_zh,
    strength_zh,
    watch_item_zh,
)


def render_markdown(briefing: Briefing) -> str:
    clusters = briefing.event_clusters or []
    market_moves = _market_moves(briefing, clusters)
    start, end, tz_label = format_data_window(
        briefing.data_window_start,
        briefing.data_window_end or briefing.generated_at,
        briefing.date,
    )
    lines: list[str] = [
        f"# 每日投资情报简报｜{briefing.date}",
        "",
        f"📅 简报日期：{briefing.date}（美国中部时间）",
        f"🕒 数据窗口：{start} 至 {end} {tz_label}",
        "🌐 新闻时间：已转换为美国中部时间；原始 UTC 时间保留在来源数据中",
        f"📊 市场数据置信度：{confidence_zh(briefing.market_confidence)}",
        "",
        "## 01｜今日一句话",
        "",
        _one_sentence_view(briefing, clusters),
        "",
        "## 02｜核心结论",
        "",
        *(_core_conclusions(briefing, clusters)),
        "",
        "## 03｜事件分层与重点事件",
        "",
    ]

    if not clusters:
        lines.extend(["今日未筛选出达到阈值的重点事件。", ""])
    else:
        for index, cluster in enumerate(clusters, start=1):
            lines.extend(_render_cluster(index, cluster))

    lines.extend(["## 04｜市场价格确认", ""])
    lines.extend(_render_price_confirmation(clusters))
    lines.append("")

    lines.extend(["## 05｜市场异动", ""])
    lines.extend(_render_market_moves(market_moves))
    lines.append("")

    lines.extend(["## 06｜宏观环境", ""])
    lines.extend(_render_macro_environment(briefing))
    lines.append("")

    lines.extend(["## 07｜资产影响速览", ""])
    lines.extend(_render_asset_cards(clusters, briefing))
    lines.append("")

    lines.extend(["## 08｜今日观察清单", ""])
    lines.extend(_render_watch_list(clusters, briefing, market_moves))
    lines.append("")

    lines.extend(["## 09｜系统判断", ""])
    lines.extend(_render_system_view(briefing, clusters))
    lines.append("")

    lines.extend(["## 10｜信息缺口与系统状态", ""])
    lines.extend(_render_info_gaps(briefing, clusters))
    lines.append("")

    lines.extend(
        [
            "## 11｜免责声明",
            "",
            "本简报仅用于信息整理和投资研究辅助，不构成个性化投资建议或交易指令。",
            "",
        ]
    )
    return sanitize_text("\n".join(lines))


def _one_sentence_view(briefing: Briefing, clusters: list[EventCluster]) -> str:
    if not clusters:
        return "今日高质量事件不足，更适合以市场价格和宏观数据作为主要观察对象。"
    leader = clusters[0]
    assets = _assets(leader.primary_assets[:3])
    indirect = _assets(leader.secondary_assets[:3])
    assumption = (
        "暂未改变长期投资假设"
        if briefing.assumption_change.startswith("暂不改变")
        else "需要继续观察长期投资假设是否变化"
    )
    price = leader.price_confirmation.status_zh
    if indirect != "无明确资产":
        return (
            f"今日核心驱动是「{leader.title}」，直接影响 {assets}，间接影响 {indirect}；"
            f"{price}，且{assumption}。"
        )
    return f"今日核心驱动是「{leader.title}」，直接影响 {assets}；{price}，且{assumption}。"


def _core_conclusions(briefing: Briefing, clusters: list[EventCluster]) -> list[str]:
    return [
        f"- 市场风险等级：{_risk_level(clusters, briefing.market_confidence)}",
        f"- 今日最重要变量：{_important_variable(clusters)}",
        f"- 对 VOO：{_asset_view('VOO', clusters)}",
        f"- 对 QQQ：{_asset_view('QQQ', clusters)}",
        f"- 对能源：{_group_view(['WTI', 'Brent', 'USO', 'XLE'], clusters)}",
        f"- 对债券：{_group_view(['TLT', 'IEF'], clusters)}",
        f"- 长期投资假设：{briefing.assumption_change}",
    ]


def _render_cluster(index: int, cluster: EventCluster) -> list[str]:
    lines = [
        f"### {index}. {cluster.title}",
        "",
        "相关报道：",
    ]
    for item in cluster.items[:4]:
        lines.append(f"- {item.item.source}：{item.item.title}（{format_local_time(item.item.published_at)}）")
    lines.extend(
        [
            "",
            f"事件类型：{category_zh(cluster.category)}",
            f"事件层级：{score_bucket_zh(cluster.score_bucket)}",
            f"风险因子：{risk_factor_zh(cluster.risk_factor)}",
            f"主要影响资产：{_assets(cluster.primary_assets)}",
            f"次要影响资产：{_assets(cluster.secondary_assets)}",
            f"影响强度：{strength_zh(cluster.impact_strength)}",
            f"价格确认：{cluster.price_confirmation.status_zh}",
            f"综合评分：{cluster.final_score} / 100｜{score_bucket_zh(cluster.score_bucket)}",
            "",
            "影响拆分：",
            *_impact_breakdown(cluster),
            "",
            "传导路径：",
            cluster.transmission_path,
            "",
            "价格说明：",
            cluster.price_confirmation.note,
            "",
            "需要观察：",
            _watch_items_text(cluster.watch_items[:8]) or "继续观察价格和后续报道",
            "",
            "---",
            "",
        ]
    )
    return lines


def _render_price_confirmation(clusters: list[EventCluster]) -> list[str]:
    if not clusters:
        return ["- 暂无重点事件可做价格确认。"]
    lines: list[str] = ["- 价格确认只表示短期价格同步、背离或未确认，不代表新闻与价格之间存在因果关系。"]
    for cluster in clusters[:5]:
        lines.append(f"- {cluster.title}：{cluster.price_confirmation.status_zh}。{cluster.price_confirmation.note}")
    return lines


def _render_market_moves(moves: list[dict[str, str]]) -> list[str]:
    if not moves:
        return ["- 核心资产暂无明显异动，今日更适合观察相对表现是否延续。"]
    lines: list[str] = []
    for move in moves[:6]:
        lines.extend(
            [
                f"### {move['asset']}",
                f"变化幅度：{move['change']}",
                f"是否显著：{move['significant']}",
                f"可能含义：{move['meaning']}",
                f"后续观察：{move['watch']}",
                "",
            ]
        )
    return lines


def _render_macro_environment(briefing: Briefing) -> list[str]:
    lines = ["### 市场表现"]
    for symbol in ["SPY", "QQQ", "NVDA", "TLT", "GLD", "XLE", "USO", "VIX", "DXY", "WTI"]:
        point = _market_point(symbol, briefing.market_points)
        if point is not None:
            lines.append("- " + _market_line(point))

    lines.extend(["", "### 宏观数据"])
    if not briefing.macro_indicators:
        lines.append("- 宏观数据暂不可用。")
    else:
        for indicator in briefing.macro_indicators:
            lines.append("- " + _macro_line(indicator))
    return lines


def _render_asset_cards(clusters: list[EventCluster], briefing: Briefing) -> list[str]:
    rows = _asset_rows(clusters)
    groups = [
        ("SPY / VOO", ["SPY", "VOO"]),
        ("QQQ", ["QQQ"]),
        ("NVDA", ["NVDA"]),
        ("TLT", ["TLT"]),
        ("GLD", ["GLD"]),
        ("XLE / USO", ["XLE", "USO"]),
        ("VIX", ["VIX"]),
        ("DXY", ["DXY"]),
    ]

    lines: list[str] = []
    for label, assets in groups:
        payloads = [rows[asset] for asset in assets if asset in rows]
        lines.extend(
            [
                f"### {label}",
                f"今日表现：{_assets_performance_line(assets, briefing.market_points)}",
                f"相对表现：{_relative_performance_line(label, briefing.market_points)}",
                f"可能含义：{_asset_market_meaning(label, briefing.market_points, payloads)}",
                f"是否需要继续观察：{_asset_market_watch(label)}",
                "",
            ]
        )
    return lines


def _render_watch_list(clusters: list[EventCluster], briefing: Briefing, market_moves: list[dict[str, str]]) -> list[str]:
    items: list[str] = []
    for cluster in clusters[:5]:
        items.extend(_verifiable_watch_items(cluster, briefing)[:4])
    items.extend(move["watch"] for move in market_moves[:4])
    if not items:
        items = [
            "QQQ 是否继续弱于 SPY",
            "NVDA 是否继续明显弱于 QQQ",
            "WTI 是否延续上涨并带动 XLE",
            "VIX 是否跌破 15 或重新上行至 17",
            "10Y 美债收益率是否重新上行并压制 TLT",
        ]
    return [f"{index}. {item}" for index, item in enumerate(list(dict.fromkeys(items))[:8], start=1)]


def _render_system_view(briefing: Briefing, clusters: list[EventCluster]) -> list[str]:
    return [
        "今日是否适合因为新闻做重大调整：否。",
        f"当前更像是：{_regime_view(clusters)}。",
        f"是否改变长期投资假设：{briefing.assumption_change}",
        "原因：只有综合评分达到 85 分以上、传导路径明确、且出现短期价格同步或明确后续数据验证的中长期事件，才会进入长期假设变化观察。",
    ]


def _asset_rows(clusters: list[EventCluster]) -> dict[str, dict[str, list]]:
    rows: dict[str, dict[str, list]] = defaultdict(
        lambda: {"directions": [], "drivers": [], "watch_items": [], "confirmations": [], "exposures": [], "risk_factors": []}
    )
    for cluster in clusters:
        for asset in cluster.primary_assets:
            rows[asset]["directions"].append(cluster.per_asset_directions.get(asset, cluster.impact_direction))
            rows[asset]["drivers"].append(risk_factor_zh(cluster.risk_factor))
            rows[asset]["watch_items"].extend(cluster.watch_items)
            rows[asset]["confirmations"].append(cluster.price_confirmation.status_zh)
            rows[asset]["exposures"].append("直接")
            rows[asset]["risk_factors"].append(cluster.risk_factor)
        for asset in cluster.secondary_assets:
            rows[asset]["directions"].append(cluster.per_asset_directions.get(asset, "mixed"))
            rows[asset]["drivers"].append(risk_factor_zh(cluster.risk_factor))
            rows[asset]["watch_items"].extend(cluster.watch_items)
            rows[asset]["confirmations"].append(cluster.price_confirmation.status_zh)
            rows[asset]["exposures"].append("间接")
            rows[asset]["risk_factors"].append(cluster.risk_factor)
    return {
        asset: {
            "directions": payload["directions"],
            "drivers": list(dict.fromkeys(payload["drivers"])),
            "watch_items": list(dict.fromkeys(payload["watch_items"])),
            "confirmations": list(dict.fromkeys(payload["confirmations"])),
            "exposures": list(dict.fromkeys(payload["exposures"])),
            "risk_factors": list(dict.fromkeys(payload["risk_factors"])),
        }
        for asset, payload in rows.items()
    }


def _market_moves(briefing: Briefing, clusters: list[EventCluster]) -> list[dict[str, str]]:
    points = briefing.market_points
    moves: list[dict[str, str]] = []
    spy = _change_for("SPY", points)
    qqq = _change_for("QQQ", points)
    nvda = _change_for("NVDA", points)
    tlt = _change_for("TLT", points)
    vix = _change_for("VIX", points)
    wti = _change_for("WTI", points)
    uso = _change_for("USO", points)
    xle = _change_for("XLE", points)

    if nvda is not None and qqq is not None and nvda - qqq <= -1.0:
        moves.append(
            _move(
                "NVDA",
                _format_change(nvda),
                "是，明显弱于 QQQ",
                "半导体龙头承压大于纳指，可能说明 AI/芯片链条风险偏好弱于大盘科技。",
                "NVDA 是否继续明显弱于 QQQ",
            )
        )
    if qqq is not None and spy is not None and qqq - spy <= -0.30:
        moves.append(
            _move(
                "QQQ / SPY",
                f"QQQ {_format_change(qqq)}，SPY {_format_change(spy)}",
                "是，QQQ 弱于 SPY",
                "成长股相对承压，风险偏好没有全面扩散到科技权重。",
                "QQQ 是否继续弱于 SPY",
            )
        )
    energy_changes = [change for change in [wti, uso, xle] if change is not None]
    if len(energy_changes) >= 2 and sum(1 for change in energy_changes if change > 0) >= 2:
        moves.append(
            _move(
                "WTI / USO / XLE",
                _joined_changes([("WTI", wti), ("USO", uso), ("XLE", xle)]),
                "是，能源链条多数同步上涨",
                "能源价格与能源股同步偏强，可能反映供需或地缘风险溢价。",
                "WTI 是否延续上涨并带动 XLE",
            )
        )
    if vix is not None and vix < 0 and not any(cluster.risk_factor == "geopolitics_war" for cluster in clusters):
        moves.append(
            _move(
                "VIX",
                _format_change(vix),
                "一般，波动率下行",
                "风险新闻不足且 VIX 下行，说明市场暂时没有明显避险定价。",
                "VIX 是否跌破 15 或重新上行至 17",
            )
        )
    if tlt is not None and abs(tlt) <= 0.15:
        moves.append(
            _move(
                "TLT",
                _format_change(tlt),
                "否，基本横盘",
                "长债端缺乏方向，利率叙事暂时没有给出强价格信号。",
                "10Y 美债收益率是否重新上行并压制 TLT",
            )
        )

    if len(moves) < 3:
        moves.extend(_fallback_top_market_moves(points, existing={move["asset"] for move in moves}))
    return moves[:6]


def _fallback_top_market_moves(points: list[MarketPoint], *, existing: set[str]) -> list[dict[str, str]]:
    core = ["SPY", "QQQ", "NVDA", "TLT", "GLD", "XLE", "USO", "VIX", "DXY", "WTI"]
    candidates = [
        point
        for symbol in core
        for point in [_market_point(symbol, points)]
        if point is not None and point.available and point.daily_change_pct is not None and point.symbol not in existing
    ]
    candidates.sort(key=lambda point: abs(point.daily_change_pct or 0), reverse=True)
    moves: list[dict[str, str]] = []
    for point in candidates[: 3]:
        change = point.daily_change_pct or 0.0
        significant = "是" if abs(change) >= 1.0 else "否"
        moves.append(
            _move(
                point.symbol,
                _format_change(change),
                significant,
                _generic_market_meaning(point.symbol, change),
                _generic_market_watch(point.symbol),
            )
        )
    return moves


def _move(asset: str, change: str, significant: str, meaning: str, watch: str) -> dict[str, str]:
    return {
        "asset": asset,
        "change": change,
        "significant": significant,
        "meaning": meaning,
        "watch": watch,
    }


def _change_for(symbol: str, points: list[MarketPoint]) -> float | None:
    point = _market_point(symbol, points)
    if point is None or not point.available:
        return None
    return point.daily_change_pct


def _joined_changes(pairs: list[tuple[str, float | None]]) -> str:
    return "，".join(f"{symbol} {_format_change(change)}" for symbol, change in pairs if change is not None)


def _format_change(change: float | None) -> str:
    return "日变动暂不可用" if change is None else f"{change:.2f}%"


def _generic_market_meaning(symbol: str, change: float) -> str:
    if symbol in {"SPY", "QQQ"}:
        return "指数价格变化提供风险偏好线索，需要结合成交和板块扩散确认。"
    if symbol == "NVDA":
        return "NVDA 变化会影响半导体和 AI 链条情绪，但不能单独代表 QQQ 方向。"
    if symbol == "TLT":
        return "TLT 变化反映长端利率定价，需要结合 10Y 收益率确认。"
    if symbol in {"XLE", "USO", "WTI"}:
        return "能源链条价格变化可能反映供需或地缘风险溢价。"
    if symbol in {"VIX", "GLD", "DXY"}:
        return "避险或美元资产变化可用于交叉验证风险情绪。"
    return "该资产出现相对较大变化，适合继续观察是否延续。"


def _generic_market_watch(symbol: str) -> str:
    return {
        "SPY": "SPY 是否继续强于 QQQ",
        "QQQ": "QQQ 是否继续弱于 SPY",
        "NVDA": "NVDA 是否继续明显弱于 QQQ",
        "TLT": "10Y 美债收益率是否重新上行并压制 TLT",
        "GLD": "GLD 是否与 DXY 同步走强",
        "XLE": "XLE 是否继续强于 SPY",
        "USO": "USO 是否跟随 WTI 延续上涨",
        "VIX": "VIX 是否跌破 15 或重新上行至 17",
        "DXY": "DXY 是否继续走强",
        "WTI": "WTI 是否延续上涨并带动 XLE",
    }.get(symbol, f"{symbol} 是否延续当前方向")


def _asset_exposure_text(exposures: list[str]) -> str:
    if "直接" in exposures and "间接" in exposures:
        return "直接 + 间接影响"
    return exposures[0] + "影响" if exposures else "影响路径不明确"


def _asset_direction_text(asset: str, payload: dict[str, list]) -> str:
    risk_factors = set(payload.get("risk_factors", []))
    exposures = set(payload.get("exposures", []))
    if asset in {"QQQ", "VOO", "SPY"} and exposures == {"间接"} and risk_factors <= {"company_specific", "musk_ecosystem"}:
        return "间接影响，不能由单一公司或私募估值新闻推断指数方向"
    return direction_zh(_aggregate_direction(payload["directions"]))


def _asset_price_line(point: MarketPoint | None) -> str:
    if point is None or not point.available:
        return "数据暂不可用"
    price = "价格暂不可用" if point.last_price is None else f"{point.last_price:.2f}"
    change = "日变动暂不可用" if point.daily_change_pct is None else f"日变动 {point.daily_change_pct:.2f}%"
    return f"{price}，{change}，来源 {_source_zh(point.source)}"


def _assets_performance_line(assets: list[str], points: list[MarketPoint]) -> str:
    parts: list[str] = []
    for asset in assets:
        point = _market_point(asset, points)
        if point is None or not point.available:
            parts.append(f"{asset} 数据暂不可用")
            continue
        price = "价格暂不可用" if point.last_price is None else f"{point.last_price:.2f}"
        parts.append(f"{asset} {price}，{_format_change(point.daily_change_pct)}，来源 {_source_zh(point.source)}")
    return "；".join(parts)


def _relative_performance_line(label: str, points: list[MarketPoint]) -> str:
    spy = _change_for("SPY", points)
    qqq = _change_for("QQQ", points)
    nvda = _change_for("NVDA", points)
    xle = _change_for("XLE", points)
    uso = _change_for("USO", points)
    wti = _change_for("WTI", points)
    tlt = _change_for("TLT", points)
    if label == "SPY / VOO":
        return _relative_pair("SPY", spy, "QQQ", qqq)
    if label == "QQQ":
        return _relative_pair("QQQ", qqq, "SPY", spy)
    if label == "NVDA":
        return _relative_pair("NVDA", nvda, "QQQ", qqq)
    if label == "TLT":
        return "TLT 基本横盘" if tlt is not None and abs(tlt) <= 0.15 else "观察 TLT 与 10Y 收益率是否反向同步"
    if label == "XLE / USO":
        return _joined_changes([("WTI", wti), ("USO", uso), ("XLE", xle)]) or "能源链条相对表现暂不可用"
    if label in {"GLD", "VIX", "DXY"}:
        return "用于交叉验证避险、波动率和美元风险偏好"
    return "相对表现暂不可用"


def _relative_pair(left_label: str, left: float | None, right_label: str, right: float | None) -> str:
    if left is None or right is None:
        return f"{left_label} / {right_label} 相对表现暂不可用"
    diff = left - right
    if abs(diff) < 0.20:
        return f"{left_label} 与 {right_label} 接近，差值 {diff:.2f} 个百分点"
    direction = "强于" if diff > 0 else "弱于"
    return f"{left_label} {direction} {right_label} {abs(diff):.2f} 个百分点"


def _asset_market_meaning(label: str, points: list[MarketPoint], payloads: list[dict[str, list]]) -> str:
    drivers = []
    for payload in payloads:
        drivers.extend(payload.get("drivers", []))
    if drivers:
        return "新闻事件关联：" + "、".join(list(dict.fromkeys(str(driver) for driver in drivers))[:3])
    if label == "SPY / VOO":
        return "大盘基准表现，用于判断风险偏好是否扩散。"
    if label == "QQQ":
        return "成长股和科技权重表现，用于判断风险资产内部是否分化。"
    if label == "NVDA":
        return "AI/半导体龙头相对 QQQ 的强弱，是科技叙事是否被价格支持的重要线索。"
    if label == "TLT":
        return "长债表现用于侧面观察长端利率压力。"
    if label == "GLD":
        return "黄金表现用于交叉验证避险需求和实际利率压力。"
    if label == "XLE / USO":
        return "能源链条表现用于观察油价风险是否传导到能源股。"
    if label == "VIX":
        return "波动率变化用于判断市场是否正在定价避险。"
    if label == "DXY":
        return "美元变化会影响风险资产、黄金和海外收入资产的定价环境。"
    return "继续观察价格和相对表现是否延续。"


def _asset_market_watch(label: str) -> str:
    return {
        "SPY / VOO": "SPY / VOO 是否继续强于或弱于 QQQ",
        "QQQ": "QQQ 是否继续弱于 SPY",
        "NVDA": "NVDA 是否继续明显弱于 QQQ",
        "TLT": "10Y 美债收益率是否重新上行并压制 TLT",
        "GLD": "GLD 是否与 DXY 同步走强",
        "XLE / USO": "WTI 是否延续上涨并带动 XLE",
        "VIX": "VIX 是否跌破 15 或重新上行至 17",
        "DXY": "DXY 是否继续走强",
    }.get(label, f"{label} 是否延续当前相对表现")


def _verifiable_watch_items(cluster: EventCluster, briefing: Briefing) -> list[str]:
    if cluster.risk_factor == "rates":
        y10 = _indicator("10Y Treasury Yield", briefing.macro_indicators)
        detail = _indicator_pair_text(y10)
        return [f"10Y 美债收益率是否继续上行{detail}", "TLT 是否继续弱于 SPY", "QQQ / SPY 相对表现是否继续走弱"]
    if cluster.risk_factor == "inflation":
        cpi = _indicator("CPI", briefing.macro_indicators) or _indicator("Core CPI", briefing.macro_indicators)
        detail = _indicator_pair_text(cpi)
        return [f"CPI / Core CPI 是否高于前值{detail}", "TLT 日变动是否继续为负", "DXY 是否继续走强"]
    if cluster.risk_factor == "oil_supply":
        return ["WTI、USO、XLE 是否同向上涨", "WTI 是否继续高于前一日收盘价", "XLE 是否继续强于 SPY"]
    if cluster.risk_factor == "semiconductors":
        return ["SMH / SOXX 是否强于 QQQ", "NVDA 是否继续强于 SOXX", "QQQ 是否收复前一日跌幅"]
    if cluster.risk_factor == "geopolitics_war":
        return ["VIX 是否突破 20 或跌破 15", "GLD 与 DXY 是否同步走强", "相关原油价格是否同步上行"]
    if cluster.risk_factor == "musk_ecosystem":
        return ["TSLA 是否继续强于 QQQ / SPY", "SpaceX 私募估值是否有新一轮可比交易披露", "TSLA 成交量是否明显高于近 20 日均量"]
    if cluster.risk_factor == "company_specific" and cluster.primary_assets:
        asset = cluster.primary_assets[0]
        return [f"{asset} 是否继续强于 QQQ / SPY", f"{asset} 成交量是否高于近 20 日均量", f"{asset} 是否回到事件前价格区间"]
    return [f"{cluster.title} 是否出现第二个高质量来源确认", "相关资产是否出现同向价格变化"]


def _indicator_pair_text(indicator: MacroIndicator | None) -> str:
    if indicator is None or not indicator.available or indicator.latest_value is None:
        return "（当前数据暂不可用）"
    if indicator.previous_value is None:
        return f"（最新 {indicator.latest_value:g}，前值暂不可用）"
    return f"（最新 {indicator.latest_value:g}，前值 {indicator.previous_value:g}）"


def _render_info_gaps(briefing: Briefing, clusters: list[EventCluster]) -> list[str]:
    coverage = _coverage_pct(briefing.market_points, briefing.macro_indicators)
    core_coverage = _core_market_coverage_pct(briefing.market_points)
    missing_market = [point.symbol for point in briefing.market_points if not point.available]
    missing_macro = [indicator.indicator for indicator in briefing.macro_indicators if not indicator.available]
    fallback_sources = sorted(
        {
            f"{point.symbol}:{_source_zh(point.source)}"
            for point in briefing.market_points
            if point.available and "fallback" in point.source.lower()
        }
    )
    raw = briefing.raw_counts.get("raw", 0)
    in_window = briefing.raw_counts.get("in_window", briefing.raw_counts.get("windowed", 0))
    outside_retained = briefing.raw_counts.get("outside_window_retained", 0)
    filtered_out = briefing.raw_counts.get("filtered_out", max(0, raw - briefing.raw_counts.get("selected_for_scoring", 0)))
    body_news = briefing.raw_counts.get("body_news", briefing.raw_counts.get("filtered", 0))
    coverage_note = (
        "核心资产覆盖较好，扩展资产覆盖不足。"
        if core_coverage >= 90 and coverage < 80
        else f"核心资产覆盖率 {core_coverage}%。"
    )
    lines = [
        f"- 市场/宏观数据覆盖率：{coverage}%；置信度：{confidence_zh(briefing.market_confidence)}；{coverage_note}",
        f"- 原始新闻数：{raw} 条。",
        f"- 窗口内新闻数：{in_window} 条。",
        f"- 窗口外但保留新闻数：{outside_retained} 条。",
        f"- 被过滤新闻数：{filtered_out} 条。",
        f"- 正文采用新闻数：{body_news} 条。",
        f"- 事件聚类数量：{len(clusters)} 组。",
        f"- 备用数据源使用：{('；'.join(fallback_sources[:12]) if fallback_sources else '无')}",
        f"- 缺失市场数据：{('、'.join(missing_market) if missing_market else '无')}",
        f"- 缺失宏观数据：{('、'.join(missing_macro) if missing_macro else '无')}",
    ]
    extra_warnings = [warning for warning in _compact_warnings(briefing.warnings) if warning != "运行完成"]
    if extra_warnings:
        lines.append(f"- 系统提示：{'；'.join(extra_warnings)}")
    return lines


def _coverage_pct(market_points: list[MarketPoint], macro_indicators: list[MacroIndicator]) -> int:
    total = len(market_points) + len(macro_indicators)
    if total == 0:
        return 0
    available = sum(1 for point in market_points if point.available) + sum(
        1 for indicator in macro_indicators if indicator.available
    )
    return int(round((available / total) * 100))


def _core_market_coverage_pct(market_points: list[MarketPoint]) -> int:
    core_assets = {"SPY", "QQQ", "NVDA", "TLT", "GLD", "XLE", "VIX", "DXY", "WTI"}
    relevant = [point for point in market_points if point.symbol.upper() in core_assets]
    if not relevant:
        return 0
    available = sum(1 for point in relevant if point.available)
    return int(round((available / len(relevant)) * 100))


def _market_line(point: MarketPoint) -> str:
    if not point.available:
        return f"{point.symbol}：数据暂不可用。"
    price = "暂无价格" if point.last_price is None else f"{point.last_price:.2f}"
    change = "日变动暂不可用" if point.daily_change_pct is None else f"日变动 {point.daily_change_pct:.2f}%"
    return f"{point.symbol}：{price}，{change}，来源 {_source_zh(point.source)}。"


def _macro_line(indicator: MacroIndicator) -> str:
    if not indicator.available or indicator.latest_value is None:
        source = indicator.source or "数据源未知"
        return f"{indicator.indicator}：数据暂不可用，来源 {source}。"
    if indicator.indicator in {"CPI", "Core CPI", "PCE", "Core PCE"}:
        return _inflation_macro_line(indicator)
    previous = "前值暂不可用" if indicator.previous_value is None else f"前值 {indicator.previous_value:g}"
    period = indicator.release_date or "数据期暂不可用"
    return (
        f"{indicator.indicator}：最新值 {indicator.latest_value:g}，{previous}，"
        f"数据期 {period}，来源 {indicator.source}。"
    )


def _inflation_macro_line(indicator: MacroIndicator) -> str:
    latest = indicator.latest_value
    previous = indicator.previous_value
    period = indicator.release_date[:7] if indicator.release_date else "数据期暂不可用"
    observations = _macro_observations(indicator)
    yoy_base = observations[12][1] if len(observations) > 12 else None
    mom = _pct_change(latest, previous)
    yoy = _pct_change(latest, yoy_base)
    if latest is not None and previous is not None and mom is not None and yoy is not None:
        return (
            f"{indicator.indicator}：同比 {yoy:.2f}%，环比 {mom:.2f}%，前值 {previous:g}，"
            f"数据期 {period}，来源 {indicator.source}。"
        )
    previous_text = "前值暂不可用" if previous is None else f"前值 {previous:g}"
    latest_text = "数据暂不可用" if latest is None else f"指数 {latest:g}"
    return (
        f"{indicator.indicator} {latest_text}，{previous_text}，数据期 {period}，来源 {indicator.source}，"
        "当前为指数水平，尚未转换为同比/环比。"
    )


def _macro_observations(indicator: MacroIndicator) -> list[tuple[str, float]]:
    observations = indicator.raw.get("observations", []) if indicator.raw else []
    parsed: list[tuple[str, float]] = []
    if not isinstance(observations, list):
        return parsed
    for row in observations:
        if not isinstance(row, dict):
            continue
        value = _float_value(row.get("value"))
        date_value = row.get("date")
        if value is not None and isinstance(date_value, str):
            parsed.append((date_value, value))
    return parsed


def _float_value(value: object) -> float | None:
    if value in {None, "", "."}:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _pct_change(latest: float | None, previous: float | None) -> float | None:
    if latest is None or previous in (None, 0):
        return None
    return ((latest - previous) / previous) * 100


def _impact_breakdown(cluster: EventCluster) -> list[str]:
    risk_assets = ["VOO", "SPY", "QQQ", "SMH", "SOXX", "NVDA", "AAPL", "MSFT", "TSLA"]
    safe_assets = ["TLT", "IEF", "GLD", "VIX", "DXY"]
    stock_assets = [asset for asset in cluster.primary_assets + cluster.secondary_assets if asset in risk_assets]
    safe_hits = [asset for asset in cluster.primary_assets + cluster.secondary_assets if asset in safe_assets]
    related_stocks = [asset for asset in stock_assets if asset not in {"VOO", "SPY", "QQQ", "SMH", "SOXX"}]
    return [
        f"- 风险方向：{_risk_direction_text(cluster)}",
        f"- 对风险资产影响：{_direction_for_assets(stock_assets, cluster)}",
        f"- 对避险资产影响：{_direction_for_assets(safe_hits, cluster)}",
        f"- 对相关个股影响：{_direction_for_assets(related_stocks, cluster)}",
    ]


def _risk_direction_text(cluster: EventCluster) -> str:
    if cluster.risk_factor in {"rates", "inflation", "geopolitics_war", "trade_policy"}:
        return "风险上行，需看价格是否继续同步"
    if cluster.risk_factor == "oil_supply":
        return "能源供应风险上行，对通胀和风险偏好有间接压力"
    if cluster.risk_factor == "semiconductors":
        return "行业基本面与估值风险并存"
    if cluster.risk_factor == "musk_ecosystem":
        return "私募估值和关联人情绪风险，公开市场传导较弱"
    return "事件风险方向仍需后续信息确认"


def _direction_for_assets(assets: list[str], cluster: EventCluster) -> str:
    if not assets:
        return "暂无直接可验证资产"
    phrases = []
    for asset in list(dict.fromkeys(assets))[:4]:
        direction = cluster.per_asset_directions.get(asset, "mixed")
        exposure = "直接" if asset in cluster.primary_assets else "间接"
        phrases.append(f"{asset}（{exposure}，{direction_zh(direction)}）")
    return "、".join(phrases)


def _market_point(symbol: str, points: list[MarketPoint]) -> MarketPoint | None:
    for point in points:
        if point.symbol.upper() == symbol.upper():
            return point
    return None


def _indicator(name: str, indicators: list[MacroIndicator]) -> MacroIndicator | None:
    for indicator in indicators:
        if indicator.indicator == name:
            return indicator
    return None


def _is_up(indicator: MacroIndicator | None) -> bool:
    return bool(
        indicator
        and indicator.latest_value is not None
        and indicator.previous_value is not None
        and indicator.latest_value > indicator.previous_value
    )


def _risk_level(clusters: list[EventCluster], market_confidence: str) -> str:
    high = sum(1 for cluster in clusters if cluster.final_score >= 80)
    if market_confidence == "low":
        return "中等（市场数据覆盖不足，置信度降低）" if high else "低到中等（市场数据覆盖不足）"
    if high >= 2:
        return "中高"
    if clusters:
        return "中等"
    return "低到中等"


def _important_variable(clusters: list[EventCluster]) -> str:
    factors = [cluster.risk_factor for cluster in clusters[:3]]
    if "oil_supply" in factors:
        return "油价是否确认地缘政治风险"
    if "rates" in factors or "inflation" in factors:
        return "美债收益率与降息预期"
    if "semiconductors" in factors:
        return "半导体板块能否确认 AI 叙事"
    if "trade_policy" in factors:
        return "关税细节和成本传导"
    return "风险偏好是否延续"


def _asset_view(asset: str, clusters: list[EventCluster]) -> str:
    directions = [
        cluster.impact_direction
        for cluster in clusters
        if asset in cluster.primary_assets or asset in cluster.secondary_assets
    ]
    return _direction_summary(directions)


def _group_view(assets: list[str], clusters: list[EventCluster]) -> str:
    directions: list[str] = []
    for cluster in clusters:
        if any(asset in cluster.primary_assets + cluster.secondary_assets for asset in assets):
            directions.append(cluster.impact_direction)
    return _direction_summary(directions)


def _direction_summary(directions: list[str]) -> str:
    if not directions:
        return "暂无明确方向，继续观察价格确认"
    if directions.count("bearish") > directions.count("bullish"):
        return "中性偏谨慎，等待价格确认"
    if directions.count("bullish") > directions.count("bearish"):
        return "短期偏正面，但仍需价格确认"
    return "影响复杂，暂不适合基于单一新闻判断方向"


def _direction_phrase(cluster: EventCluster) -> str:
    if cluster.risk_factor == "oil_supply":
        return "能源资产偏利好；对大盘和成长股影响复杂"
    if cluster.risk_factor == "semiconductors":
        return "基本面叙事偏正面，但需观察价格确认"
    if cluster.risk_factor == "rates":
        return "对长债和成长股偏谨慎"
    return direction_zh(cluster.impact_direction)


def _aggregate_direction(directions: list[str]) -> str:
    values = set(directions)
    if "bearish" in values and "bullish" in values:
        return "mixed"
    if "bearish" in values:
        return "bearish"
    if "bullish" in values:
        return "bullish"
    if "mixed" in values:
        return "mixed"
    return "unclear"


def _asset_price_confirmation(confirmations: list[str], market_confidence: str) -> str:
    if market_confidence == "low":
        return "数据不足"
    if "短期价格背离" in confirmations and "短期价格同步" in confirmations:
        return "信号分化"
    if "短期价格同步" in confirmations:
        return "短期价格同步" if len(confirmations) == 1 else "部分短期同步"
    if "短期价格背离" in confirmations:
        return "短期价格背离"
    if "价格暂未确认" in confirmations:
        return "价格暂未确认"
    return confirmations[0] if confirmations else "数据不足"


def _regime_view(clusters: list[EventCluster]) -> str:
    factors = {cluster.risk_factor for cluster in clusters[:4]}
    if "oil_supply" in factors or "geopolitics_war" in factors:
        return "行业事件和地缘风险驱动的短期扰动"
    if "semiconductors" in factors or "company_specific" in factors:
        return "行业与公司事件驱动"
    if "rates" in factors or "inflation" in factors:
        return "宏观利率与风险偏好驱动"
    return "信息不足，适合继续观察"


def _assets(assets: list[str]) -> str:
    return "、".join(assets) if assets else "无明确资产"


def _compact_warnings(warnings: list[str]) -> list[str]:
    compact: list[str] = []
    for warning in warnings:
        if warning.startswith("系统状态："):
            compact.append(warning.replace("系统状态：", ""))
        elif "市场数据覆盖不足" in warning:
            compact.append("市场数据覆盖不足")
    return compact or ["运行完成"]


def _watch_items_text(items: list[str]) -> str:
    return "、".join(watch_item_zh(item) for item in items)


def _source_zh(source: str) -> str:
    if source == "Stooq fallback":
        return "Stooq 备用数据源"
    if source == "FRED fallback":
        return "FRED 备用数据源"
    return source
