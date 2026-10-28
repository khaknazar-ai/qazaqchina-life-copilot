import json
import re
from pathlib import Path

import pytest

from backend.app.demo_contracts.secret_scan import frontend_secret_markers

ROOT = Path("frontend/wechat-miniprogram")
CURATED_SCENARIOS = {
    "lost-passport-emergency",
    "work-contract-risk",
    "payment-scam-warning",
    "hospital-registration",
    "visa-extension-warning",
    "community-misinformation-conflict",
}


def test_miniprogram_path_and_app_json_exist() -> None:
    assert ROOT.exists()
    app_json = json.loads((ROOT / "app.json").read_text(encoding="utf-8"))

    assert "pages/home/index" in app_json["pages"]
    assert "pages/demo-detail/index" in app_json["pages"]


def test_home_case_progress_uses_the_native_progress_component() -> None:
    home = (ROOT / "pages/home/index.wxml").read_text(encoding="utf-8")

    assert "<progress" in home
    assert 'percent="{{recentCase.progress}}"' in home
    assert 'style="width:{{recentCase.progress}}%;"' not in home


def test_grounded_answer_ux_labels_are_present() -> None:
    text = _all_miniprogram_text()

    for label in [
        "Direct answer",
        "Grounded facts",
        "Recommended next steps",
        "Checklist",
        "Escalation",
        "Uncertainty",
        "Source notes",
        "Verifier",
        "Freshness",
        "Demo mode",
        "Not trusted evidence",
    ]:
        assert label in text


def test_loading_error_and_source_coverage_states_are_present() -> None:
    text = _all_miniprogram_text()

    assert "Loading answer" in text
    assert "Loading demo scenarios" in text
    assert "Error" in text
    assert "Backend unavailable" in text
    assert "No trusted source coverage" in text
    assert "Stale" not in text or "Freshness" in text


def test_api_config_has_local_default_and_no_secret_or_provider_urls() -> None:
    text = _all_miniprogram_text().casefold()

    assert "http://127.0.0.1:8000" in text
    assert frontend_secret_markers(text) == []
    assert "openai" not in text
    assert "deepseek" not in text
    assert "openrouter" not in text
    assert "sk-" not in text


def test_demo_scenario_ids_include_curated_subset() -> None:
    text = _all_miniprogram_text()

    assert CURATED_SCENARIOS <= {scenario for scenario in CURATED_SCENARIOS if scenario in text}


def test_native_forms_fill_their_container_without_losing_flex_rows() -> None:
    # DevTools renders wx-form inline by default, unlike an HTML form. Without
    # an explicit block box, padded form backgrounds collapse behind children.
    def declarations(styles: str, selector: str) -> dict[str, str]:
        properties = {}
        for selectors, body in re.findall(r"([^{}]+)\{([^{}]+)\}", styles):
            if selector not in {part.strip() for part in selectors.split(",")}:
                continue
            properties.update(
                (name.strip(), value.strip())
                for name, value in re.findall(r"([\w-]+)\s*:\s*([^;]+);", body)
            )
        return properties

    styles = (ROOT / "app.wxss").read_text(encoding="utf-8")
    form_style = declarations(styles, "form")
    assert form_style.get("display") == "block"
    assert form_style.get("width") == "100%"
    assert form_style.get("box-sizing") == "border-box"

    form_pages = {
        path.parent.name
        for path in (ROOT / "pages").glob("*/index.wxml")
        if re.search(r"<form\b", path.read_text(encoding="utf-8"))
    }
    assert form_pages == {
        "home", "chat", "photo-intake", "explain", "cases", "case-detail",
        "knowledge", "profile", "support", "privacy", "consul",
    }
    # Native wx-form inserts a wrapper: layout its controls in an inner view,
    # rather than assuming flex on the form host reaches the input and button.
    case_styles = (ROOT / "pages/case-detail/index.wxss").read_text(encoding="utf-8")
    assert declarations(case_styles, ".add-action").get("display") != "flex"
    row_style = declarations(case_styles, ".add-action-row")
    assert row_style.get("display") == "flex"
    assert row_style.get("width") == "100%"
    assert declarations(case_styles, ".add-action-field").get("min-width") == "0"
    assert declarations(case_styles, ".add-action-submit").get("width") == "46px"
    case_template = (ROOT / "pages/case-detail/index.wxml").read_text(encoding="utf-8")
    row = re.search(
        r'<form\b[^>]*class="add-action"[^>]*>\s*<view class="add-action-row">(.*?)</form>',
        case_template,
        re.S,
    )
    assert row
    assert re.search(r'<view class="add-action-field">\s*<input\b[^>]*name="title"', row.group(1))
    assert re.search(
        r'<view class="add-action-submit">\s*<button\b[^>]*form-type="submit"', row.group(1)
    )


def test_case_metadata_hides_absent_values_and_conditional_separator() -> None:
    template = (ROOT / "pages/case-detail/index.wxml").read_text(encoding="utf-8")
    metadata = re.search(
        r'<view wx:if="\{\{item.context.city \|\| item.deadline\}\}" '
        r'class="subtitle case-metadata">(.*?)</view>',
        template,
        re.S,
    )
    assert metadata
    assert '<text wx:if="{{item.context.city}}">{{item.context.city}}</text>' in metadata.group(1)
    assert '<text wx:if="{{item.deadline}}">' in metadata.group(1)
    assert "{{item.context.city ? ' · ' : ''}}" in metadata.group(1)


def test_chat_composer_and_content_reserve_the_bottom_safe_area() -> None:
    styles = (ROOT / "pages/chat/index.wxss").read_text(encoding="utf-8")
    composer = re.search(r"(?:^|})\s*\.composer\s*\{([^}]+)\}", styles)
    page = re.search(r"(?:^|})\s*\.chat-page\s*\{([^}]+)\}", styles)
    assert composer and page
    assert re.search(r"\bposition\s*:\s*sticky\s*;", composer.group(1))
    gaps = []
    for body, property_name in ((composer.group(1), "bottom"), (page.group(1), "padding-bottom")):
        values = re.findall(r"(?<![\w-])" + property_name + r"\s*:\s*([^;]+);", body)
        # Keep a positive fallback for engines without env(), before the
        # safe-area rule used on devices with a home indicator.
        assert len(values) == 2
        fallback = re.fullmatch(r"([\d.]+)px", values[0].strip())
        safe_area = re.fullmatch(
            r"calc\(\s*([\d.]+)px\s*\+\s*env\(safe-area-inset-bottom\)\s*\)",
            values[1].strip(),
        )
        assert fallback and safe_area
        gap = float(fallback.group(1))
        assert gap >= 8
        assert float(safe_area.group(1)) == gap
        gaps.append(gap)
    assert gaps[1] >= gaps[0], "normal page flow must reserve the sticky composer's gap"


@pytest.mark.parametrize(
    ("filename", "selector", "backgrounds"),
    [
        ("app.wxss", ".muted,.hint", ("#f7f6f2", "#ffffff", "#edf2ec")),
        ("app.wxss", ".source-id", ("#ffffff",)),
        ("app.wxss", ".eyebrow", ("#f7f6f2",)),
        ("app.wxss", ".loading-line", ("#f7f6f2",)),
        ("app.wxss", ".segment button", ("#eaece5",)),
        ("pages/home/index.wxss", ".language-control", ("#f7f6f2",)),
        ("pages/chat/index.wxss", ".context-button", ("#f7f6f2",)),
        ("pages/chat/index.wxss", ".direct-section .section-title", ("#f7f6f2",)),
        ("pages/chat/index.wxss", ".composer-hint", ("#ffffff",)),
        ("pages/photo-intake/index.wxss", ".photo-progress", ("#f7f6f2",)),
        ("pages/checklist/index.wxss", ".picker-chevron", ("#fafbf8",)),
        ("pages/knowledge/index.wxss", ".entry-title text", ("#f7f6f2",)),
    ],
)
def test_small_secondary_text_has_readable_contrast(
    filename: str, selector: str, backgrounds: tuple[str, ...]
) -> None:
    styles = (ROOT / filename).read_text(encoding="utf-8")
    selector_pattern = r"\s*,\s*".join(re.escape(part.strip()) for part in selector.split(","))
    rule = re.search(r"(?:^|})\s*" + selector_pattern + r"\s*\{([^}]+)\}", styles)
    assert rule, f"Missing style rule: {selector}"
    match = re.search(r"(?:^|;)\s*color\s*:\s*(#[\da-fA-F]{6})", rule.group(1))
    assert match, f"Missing text color: {selector}"

    def luminance(color: str) -> float:
        values = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        channels = [
            value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
            for value in values
        ]
        return sum(
            channel * weight
            for channel, weight in zip(channels, (0.2126, 0.7152, 0.0722), strict=True)
        )

    foreground = luminance(match.group(1))
    for background in backgrounds:
        surface = luminance(background)
        ratio = (max(foreground, surface) + 0.05) / (min(foreground, surface) + 0.05)
        assert ratio >= 4.5, f"{selector} on {background}: contrast {ratio:.2f}:1"


def _all_miniprogram_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in ROOT.rglob("*")
        if path.is_file() and path.suffix in {".js", ".json", ".wxml", ".wxss"}
    )
