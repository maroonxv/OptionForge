from pathlib import Path

from flask import Flask, render_template


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = PROJECT_ROOT / "src" / "web"


def render_monitor_page(**context) -> str:
    app = Flask(
        __name__,
        template_folder=str(WEB_ROOT / "templates"),
        static_folder=str(WEB_ROOT / "static"),
    )
    with app.test_request_context("/"):
        return render_template(
            "index.html",
            strategies=context.get("strategies", ["alpha"]),
            variant=context.get("variant", "alpha"),
            front_poll_ms=context.get("front_poll_ms", 3000),
            front_stale_ms=context.get("front_stale_ms", 5000),
        )


def test_monitor_template_renders_core_regions() -> None:
    html = render_monitor_page(strategies=["alpha", "beta"])

    assert 'class="monitor-terminal"' in html
    assert 'monitor-terminal.css' in html
    assert 'id="strategy-select"' in html
    assert 'id="chart-container"' in html
    assert 'id="decision-timeline"' in html
    assert 'id="variant-name"' in html


def test_monitor_template_preserves_initial_variant_binding() -> None:
    html = render_monitor_page(variant="alpha-01")

    assert 'window.INIT_VARIANT = "alpha-01"' in html
    assert "\u671f\u6743\u7b56\u7565\u76d1\u63a7\u53f0" in html
