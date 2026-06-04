from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from briefing.asset_mapper import map_asset_impact
from briefing.classifier import classify
from briefing.config import default_config
from briefing.delivery.email import EmailDelivery
from briefing.delivery.telegram import _split_message
from briefing.dedupe import dedupe_items
from briefing.event_clusterer import cluster_events
from briefing.guardrails import validate_text
from briefing.models import Briefing, MacroIndicator, MarketPoint, NewsItem, ScoredNews
from briefing.normalizer import normalize_items
from briefing.pipeline import _briefing_window, _include_scored_item, _select_news_for_scoring, run_pipeline
from briefing.price_confirmation import confirm_price_action
from briefing.renderer import render_markdown
from briefing.scoring import score_item
from briefing.storage import FileStorage


class PipelineTests(unittest.TestCase):
    def test_dedupe_removes_similar_titles(self) -> None:
        items = [
            NewsItem(
                title="Treasury yields rise as Fed path is reassessed",
                source="A",
                url="https://example.com/a",
                published_at="2026-06-02T12:00:00+00:00",
            ),
            NewsItem(
                title="Treasury yields rise as Federal Reserve path is reassessed",
                source="B",
                url="https://example.com/b",
                published_at="2026-06-02T12:01:00+00:00",
            ),
        ]
        self.assertEqual(len(dedupe_items(items, title_threshold=0.80)), 1)

    def test_asset_mapper_outputs_transmission_path(self) -> None:
        config = default_config()
        item = NewsItem(
            title="Treasury yields rise as investors reassess Fed path",
            source="Example",
            url="https://example.com",
            published_at="2026-06-02T12:00:00+00:00",
        )
        impact = map_asset_impact(item, config)
        self.assertIn("QQQ", impact.affected_assets)
        self.assertTrue(impact.transmission_path)

    def test_demo_pipeline_outputs_v1_brief(self) -> None:
        config = default_config()
        result = run_pipeline(config, demo=True, dry_run=True, save=False, run_date="2026-06-02")
        self.assertIn("每日投资情报简报", result.markdown)
        self.assertIn("数据窗口", result.markdown)
        self.assertNotIn("至 2026-06-04 08:00", result.markdown)
        self.assertIn("资产影响速览", result.markdown)
        self.assertIn("宏观环境", result.markdown)
        self.assertIn("市场异动", result.markdown)
        self.assertIn("重点事件", result.markdown)
        self.assertIn("信息缺口与系统状态", result.markdown)
        self.assertNotIn("已确认", result.markdown)
        self.assertNotIn("与价格相悖", result.markdown)
        self.assertNotIn("部分确认", result.markdown)
        self.assertNotIn("对降息预期不算友好", result.markdown)
        self.assertGreaterEqual(len(result.briefing.top_news), 5)
        self.assertGreaterEqual(len(result.briefing.event_clusters), 3)
        for forbidden in [
            "risk_factor",
            "primary_assets",
            "secondary_assets",
            "transmission_path",
            "final_score",
            "watch_items",
            "company_specific",
            "semiconductors",
            "oil_supply",
            "AI capex commentary",
        ]:
            self.assertNotIn(forbidden, result.markdown)
        self.assertEqual(validate_text(result.markdown), [])

    def test_manual_window_defaults_to_24_hours(self) -> None:
        config = default_config()
        start, end = _briefing_window(config)
        start_dt = __import__("datetime").datetime.fromisoformat(start)
        end_dt = __import__("datetime").datetime.fromisoformat(end)
        hours = (end_dt - start_dt).total_seconds() / 3600
        self.assertAlmostEqual(hours, 24, delta=0.1)

    def test_outside_window_high_relevance_news_is_retained(self) -> None:
        config = default_config()
        item = NewsItem(
            title="Nvidia shares fall as semiconductor export controls pressure AI chips",
            source="Reuters",
            url="https://example.com/nvda-30h",
            published_at="2026-06-02T06:00:00+00:00",
            summary="NVDA and semiconductor ETFs were in focus.",
        )
        selected, stats = _select_news_for_scoring(
            [item],
            config,
            "2026-06-02T12:00:00+00:00",
            "2026-06-03T12:00:00+00:00",
        )
        self.assertEqual(len(selected), 1)
        self.assertEqual(stats["outside_retained"], 1)
        self.assertEqual(selected[0].metadata["recency_score"], 0.6)

    def test_market_mode_renders_when_no_news_clusters(self) -> None:
        briefing = Briefing(
            date="2026-06-03",
            generated_at="2026-06-03T20:00:00+00:00",
            data_window_start="2026-06-02T20:00:00+00:00",
            data_window_end="2026-06-03T20:00:00+00:00",
            core_view="",
            top_news=[],
            geopolitical_risks=[],
            market_environment=[],
            watchlist=["VOO", "QQQ", "NVDA"],
            assumption_change="暂不改变长期投资假设。",
            disclaimer="",
            raw_counts={
                "raw": 10,
                "in_window": 8,
                "outside_window_retained": 1,
                "filtered_out": 1,
                "body_news": 0,
            },
            market_points=[
                MarketPoint(symbol="SPY", value=100, change_percent=0.1, source="test"),
                MarketPoint(symbol="VOO", value=100, change_percent=0.1, source="test"),
                MarketPoint(symbol="QQQ", value=100, change_percent=-0.6, source="test"),
                MarketPoint(symbol="NVDA", value=100, change_percent=-2.5, source="test"),
                MarketPoint(symbol="TLT", value=100, change_percent=0.02, source="test"),
                MarketPoint(symbol="GLD", value=100, change_percent=0.2, source="test"),
                MarketPoint(symbol="XLE", value=100, change_percent=1.0, source="test"),
                MarketPoint(symbol="USO", value=100, change_percent=1.2, source="test"),
                MarketPoint(symbol="VIX", value=15, change_percent=-1.0, source="test"),
                MarketPoint(symbol="DXY", value=100, change_percent=0.1, source="test"),
                MarketPoint(symbol="WTI", value=80, change_percent=1.5, source="test"),
            ],
            macro_indicators=[],
            market_confidence="medium",
        )
        markdown = render_markdown(briefing)
        self.assertIn("## 05｜市场异动", markdown)
        self.assertIn("NVDA 是否继续明显弱于 QQQ", markdown)
        self.assertIn("### SPY / VOO", markdown)
        self.assertIn("### DXY", markdown)
        self.assertNotIn("暂无明确资产影响", markdown)
        self.assertIn("窗口外但保留新闻数：1 条", markdown)

    def test_inflation_macro_line_uses_yoy_mom_and_data_period(self) -> None:
        observations = [
            {"date": "2026-04-01", "value": "102"},
            {"date": "2026-03-01", "value": "101"},
        ] + [{"date": f"2025-{month:02d}-01", "value": "100"} for month in range(3, 0, -1)]
        observations.extend({"date": f"2025-{month:02d}-01", "value": "100"} for month in range(12, 3, -1))
        briefing = Briefing(
            date="2026-06-03",
            generated_at="2026-06-03T20:00:00+00:00",
            data_window_start="2026-06-02T20:00:00+00:00",
            data_window_end="2026-06-03T20:00:00+00:00",
            core_view="",
            top_news=[],
            geopolitical_risks=[],
            market_environment=[],
            watchlist=[],
            assumption_change="暂不改变长期投资假设。",
            disclaimer="",
            market_points=[],
            macro_indicators=[
                MacroIndicator(
                    indicator="CPI",
                    latest_value=102,
                    previous_value=101,
                    release_date="2026-04-01",
                    source="FRED",
                    interpretation="",
                    raw={"observations": observations},
                )
            ],
        )
        markdown = render_markdown(briefing)
        self.assertIn("CPI：同比", markdown)
        self.assertIn("环比", markdown)
        self.assertIn("数据期 2026-04", markdown)
        self.assertNotIn("发布日期", markdown)

    def test_storage_writes_v1_paths(self) -> None:
        config = default_config()
        result = run_pipeline(config, demo=True, dry_run=True, save=False, run_date="2026-06-02")
        with tempfile.TemporaryDirectory() as tmp:
            path = FileStorage(tmp).save(
                "2026-06-02",
                result.raw_items,
                result.scored_items,
                result.briefing,
                result.markdown,
            )
            root = Path(tmp)
            self.assertEqual(path, root / "briefs" / "2026-06-02-brief.md")
            self.assertTrue((root / "raw" / "2026-06-02-news.json").exists())
            self.assertTrue((root / "processed" / "2026-06-02-events.json").exists())
            self.assertTrue((root / "debug" / "2026-06-02-debug.md").exists())

    def test_email_delivery_configured_from_env(self) -> None:
        env = {
            "EMAIL_SMTP_HOST": "smtp.example.com",
            "EMAIL_SMTP_PORT": "587",
            "EMAIL_SMTP_USERNAME": "sender@example.com",
            "EMAIL_SMTP_PASSWORD": "secret",
            "EMAIL_FROM": "brief@example.com",
            "EMAIL_TO": "one@example.com,two@example.com",
            "EMAIL_USE_TLS": "true",
        }
        with patch.dict("os.environ", env, clear=True):
            delivery = EmailDelivery()
        self.assertTrue(delivery.configured)
        self.assertEqual(delivery.missing_settings, [])
        self.assertEqual(delivery.recipients, ["one@example.com", "two@example.com"])

    def test_email_delivery_reports_missing_settings(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            delivery = EmailDelivery()
        self.assertIn("EMAIL_SMTP_HOST", delivery.missing_settings)
        self.assertFalse(delivery.check_connection().ok)

    def test_gmail_username_must_be_full_email(self) -> None:
        env = {
            "EMAIL_SMTP_HOST": "smtp.gmail.com",
            "EMAIL_SMTP_USERNAME": "sender",
            "EMAIL_SMTP_PASSWORD": "abcdefghijklmnop",
            "EMAIL_FROM": "sender@gmail.com",
            "EMAIL_TO": "receiver@example.com",
        }
        with patch.dict("os.environ", env, clear=True):
            delivery = EmailDelivery()
        check = delivery.check_connection()
        self.assertFalse(check.ok)
        self.assertIn("full Gmail address", check.message)

    def test_email_from_is_required(self) -> None:
        env = {
            "EMAIL_SMTP_HOST": "smtp.gmail.com",
            "EMAIL_SMTP_USERNAME": "sender@gmail.com",
            "EMAIL_SMTP_PASSWORD": "abcdefghijklmnop",
            "EMAIL_TO": "receiver@example.com",
        }
        with patch.dict("os.environ", env, clear=True):
            delivery = EmailDelivery()
        self.assertIn("EMAIL_FROM", delivery.missing_settings)

    def test_email_configured_requires_login_settings(self) -> None:
        env = {
            "EMAIL_SMTP_HOST": "smtp.example.com",
            "EMAIL_FROM": "brief@example.com",
            "EMAIL_TO": "receiver@example.com",
        }
        with patch.dict("os.environ", env, clear=True):
            delivery = EmailDelivery()
        self.assertFalse(delivery.configured)
        self.assertIn("EMAIL_SMTP_USERNAME", delivery.missing_settings)
        self.assertIn("EMAIL_SMTP_PASSWORD", delivery.missing_settings)

    def test_pipeline_uses_email_delivery_channel(self) -> None:
        config = default_config()
        config.delivery.channel = "email"
        config.delivery.email.subject_prefix = "Test Brief"
        with patch("briefing.delivery.EmailDelivery.send_markdown", return_value=True) as send:
            result = run_pipeline(
                config,
                demo=True,
                dry_run=False,
                save=False,
                run_date="2026-06-02",
            )
        self.assertTrue(result.delivered)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[1], "Test Brief：2026-06-02")

    def test_normalizer_parses_compact_provider_datetimes(self) -> None:
        items = [
            NewsItem(
                title="Alpha Vantage date",
                source="Example",
                url="https://example.com/av",
                published_at="20260602T123000",
            ),
            NewsItem(
                title="Compact date",
                source="Example",
                url="https://example.com/compact",
                published_at="20260602123000",
            ),
        ]
        normalized = normalize_items(items)
        self.assertEqual(normalized[0].published_at, "2026-06-02T12:30:00+00:00")
        self.assertEqual(normalized[1].published_at, "2026-06-02T12:30:00+00:00")

    def test_min_score_is_not_bypassed_by_asset_mapping(self) -> None:
        config = default_config()
        config.rules.min_score = 50
        scored = ScoredNews(
            item=NewsItem(
                title="Low score asset mention",
                source="Example",
                url="https://example.com/low",
                published_at="2026-06-02T12:00:00+00:00",
            ),
            category="其他",
            related_assets=["VOO"],
            impact_direction="mixed",
            time_horizon="short-term",
            relevance_score=0.1,
            importance_score=0.1,
            novelty_score=0.1,
            market_impact_score=0.1,
            confidence_score=0.1,
            reasoning="Low score item.",
            watch_items=[],
        )
        self.assertFalse(_include_scored_item(scored, config))

    def test_telegram_split_never_exceeds_limit(self) -> None:
        chunks = _split_message("A" * 8000, limit=3900)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 3900 for chunk in chunks))

    def test_old_news_is_capped_and_excluded_from_daily_brief(self) -> None:
        config = default_config()
        item = NewsItem(
            title="Treasury yields rise sharply in old market report",
            source="Reuters",
            url="https://example.com/old-yields",
            published_at="2025-01-15T12:00:00+00:00",
            summary="Federal Reserve rate cut expectations and Treasury yields drove markets.",
        )
        category = classify(item)
        impact = map_asset_impact(item, config)
        scored = score_item(item, category, impact.affected_assets, config, impact)
        self.assertLessEqual(scored.final_score, 20)
        self.assertFalse(_include_scored_item(scored, config))

    def test_russia_crude_exports_map_to_energy_not_tech(self) -> None:
        config = default_config()
        item = NewsItem(
            title="Russia crude exports remain stable despite sanctions pressure",
            source="Reuters",
            url="https://example.com/russia-crude",
            published_at="2026-06-02T12:00:00+00:00",
            summary="Oil traders watched crude flows and sanctions enforcement.",
        )
        impact = map_asset_impact(item, config)
        self.assertEqual(impact.risk_factor, "oil_supply")
        self.assertIn("WTI", impact.primary_assets)
        self.assertIn("XLE", impact.primary_assets)
        self.assertNotIn("NVDA", impact.affected_assets)
        self.assertNotIn("AAPL", impact.affected_assets)
        self.assertNotIn("TSLA", impact.affected_assets)

    def test_coffee_tariff_does_not_default_to_big_tech(self) -> None:
        config = default_config()
        item = NewsItem(
            title="Coffee tariff dispute lifts consumer price concerns",
            source="Example",
            url="https://example.com/coffee",
            published_at="2026-06-02T12:00:00+00:00",
            summary="Coffee prices may affect food inflation components.",
        )
        impact = map_asset_impact(item, config)
        self.assertEqual(impact.risk_factor, "soft_commodities")
        self.assertIn("Coffee futures", impact.primary_assets)
        for asset in ["QQQ", "NVDA", "AAPL", "TSLA"]:
            self.assertNotIn(asset, impact.affected_assets)

    def test_china_coal_mine_disaster_is_low_relevance_without_supply_shock(self) -> None:
        config = default_config()
        item = NewsItem(
            title="China coal mine disaster prompts local safety investigation",
            source="Example",
            url="https://example.com/coal",
            published_at="2026-06-02T12:00:00+00:00",
            summary="Authorities are investigating a local accident.",
        )
        self.assertEqual(classify(item), "low_relevance")
        impact = map_asset_impact(item, config)
        self.assertEqual(impact.risk_factor, "low_relevance")
        self.assertEqual(impact.affected_assets, [])

    def test_nvidia_marvell_news_is_not_macro_and_has_semiconductor_watch_items(self) -> None:
        config = default_config()
        item = NewsItem(
            title="Nvidia and Marvell launch new AI chip products for data centers",
            source="CNBC",
            url="https://example.com/nvda-mrvl",
            published_at="2026-06-02T12:00:00+00:00",
            summary="Semiconductor investors focused on AI chip demand.",
        )
        category = classify(item)
        impact = map_asset_impact(item, config)
        scored = score_item(item, category, impact.affected_assets, config, impact)
        self.assertIn(category, {"company", "sector"})
        self.assertEqual(impact.risk_factor, "semiconductors")
        self.assertIn("NVDA", impact.primary_assets)
        self.assertIn("SMH", scored.watch_items)
        self.assertNotIn("WTI", scored.watch_items)

    def test_oil_watch_items_do_not_include_ai_capex(self) -> None:
        config = default_config()
        item = NewsItem(
            title="Oil prices climb as Middle East shipping risk rises",
            source="Associated Press",
            url="https://example.com/oil-watch",
            published_at="2026-06-02T12:00:00+00:00",
            summary="Energy markets watched shipping lanes and supply disruption.",
        )
        impact = map_asset_impact(item, config)
        scored = score_item(item, classify(item), impact.affected_assets, config, impact)
        self.assertIn("WTI", scored.watch_items)
        self.assertNotIn("AI capex commentary", scored.watch_items)

    def test_warsh_name_does_not_trigger_war_risk(self) -> None:
        config = default_config()
        item = NewsItem(
            title="Fed Chair Warsh makes first hires at central bank",
            source="CNBC",
            url="https://example.com/warsh",
            published_at="2026-06-02T12:00:00+00:00",
            summary="Central bank staffing changes drew attention from investors.",
        )
        impact = map_asset_impact(item, config)
        self.assertNotEqual(impact.risk_factor, "geopolitics_war")

    def test_hormuz_risk_maps_to_oil_supply(self) -> None:
        config = default_config()
        item = NewsItem(
            title="Iran has mined large segments of Hormuz Strait, officials say",
            source="CNBC",
            url="https://example.com/hormuz",
            published_at="2026-06-02T12:00:00+00:00",
            summary="Shipping disruption risk could affect crude flows.",
        )
        impact = map_asset_impact(item, config)
        self.assertEqual(impact.risk_factor, "oil_supply")
        self.assertIn("WTI", impact.primary_assets)

    def test_oil_price_confirmation_is_unconfirmed_when_wti_falls_but_energy_etfs_rise(self) -> None:
        confirmation = confirm_price_action(
            "oil_supply",
            ["WTI", "USO", "XLE"],
            [
                MarketPoint(symbol="WTI", value=70, change_percent=-1.0, source="test"),
                MarketPoint(symbol="USO", value=80, change_percent=1.0, source="test"),
                MarketPoint(symbol="XLE", value=90, change_percent=1.0, source="test"),
            ],
            [],
        )
        self.assertEqual(confirmation.status, "unconfirmed")
        self.assertEqual(confirmation.status_zh, "价格暂未确认")
        self.assertIn("不代表新闻与价格之间存在因果关系", confirmation.note)

    def test_previous_close_price_does_not_force_short_price_sync(self) -> None:
        confirmation = confirm_price_action(
            "company_specific",
            ["AAPL"],
            [
                MarketPoint(
                    symbol="AAPL",
                    value=200,
                    change_percent=2.0,
                    source="Stooq fallback",
                    raw={"Date": "2026-06-01"},
                )
            ],
            [],
        )
        self.assertEqual(confirmation.status, "unconfirmed")
        self.assertEqual(confirmation.status_zh, "价格暂未确认")
        self.assertIn("前一交易日", confirmation.note)

    def test_spacex_news_maps_to_musk_ecosystem_not_direct_tsla_event(self) -> None:
        config = default_config()
        item = NewsItem(
            title="SpaceX targets fixed IPO roadshow price at high private valuation",
            source="CNBC",
            url="https://example.com/spacex",
            published_at="2026-06-02T12:00:00+00:00",
            summary="The Elon Musk company is discussing private market valuation.",
            symbols=["TSLA"],
        )
        impact = map_asset_impact(item, config)
        self.assertEqual(impact.risk_factor, "musk_ecosystem")
        self.assertEqual(impact.primary_assets, ["SpaceX / 私募估值"])
        self.assertIn("TSLA", impact.secondary_assets)
        self.assertIn("间接", impact.transmission_path)

    def test_us_spy_chief_personnel_story_is_not_geopolitical_war(self) -> None:
        config = default_config()
        item = NewsItem(
            title="Pulte appointment as spy chief would give a Trump attack dog access to intelligence",
            source="CNBC",
            url="https://example.com/spy-chief",
            published_at="2026-06-02T12:00:00+00:00",
            summary="Domestic personnel story without market transmission.",
        )
        self.assertEqual(classify(item), "low_relevance")
        impact = map_asset_impact(item, config)
        self.assertEqual(impact.risk_factor, "low_relevance")

    def test_geopolitical_cluster_separates_unrelated_stories(self) -> None:
        config = default_config()
        items = [
            NewsItem(
                title="Iran nuclear talks remain uncertain as weapons pledge is debated",
                source="Reuters",
                url="https://example.com/iran-nuclear",
                published_at="2026-06-02T12:00:00+00:00",
                summary="Investors watched Middle East risk.",
            ),
            NewsItem(
                title="Russia Ukraine negotiations remain uncertain as sanctions pressure persists",
                source="Reuters",
                url="https://example.com/ukraine",
                published_at="2026-06-02T12:30:00+00:00",
                summary="Sanctions and war risk remained in focus.",
            ),
        ]
        scored = []
        for item in items:
            impact = map_asset_impact(item, config)
            scored.append(score_item(item, classify(item), impact.affected_assets, config, impact))
        clusters, _ = cluster_events(scored, [], [])
        self.assertGreaterEqual(len(clusters), 2)
        titles = [cluster.title for cluster in clusters]
        self.assertNotEqual(titles[0], titles[1])


if __name__ == "__main__":
    unittest.main()
