from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HVAC_", extra="ignore")

    app_name: str = "HVAC Duct Detector API"
    data_dir: Path = Path(__file__).resolve().parents[3] / "data"
    max_upload_size_mb: int = 100
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    render_dpi: int = 220
    measurement_mode: str = "centerline"
    min_segment_length_px: int = 38

    # Sample markup PNG used to extract centerlines; aligned to ``refine_expected_png_target_page``.
    expected_annotation_png: Path = Path(__file__).resolve().parents[3] / "Sample annotation.png"
    # Visible PDF page rectangle inside that screenshot: x0,y0,x1,y1 in PNG pixel coordinates.
    refine_screenshot_page_bbox: str = "38,67,1990,1368"
    # 1-based PDF page number the expected PNG maps to. Set to 0 to skip the calibrated overlay.
    refine_expected_png_target_page: int = 1
    # OpenCV BGR stroke color for the calibrated centerline overlay (HVAC_REFINE_OVERLAY_BGR_*).
    refine_overlay_bgr_b: int = 255
    refine_overlay_bgr_g: int = 80
    refine_overlay_bgr_r: int = 0
    # Blue-mask extraction on the expected PNG (HVAC_REFINE_BLUE_* / morph keys below).
    refine_blue_min_b: int = 150
    refine_blue_min_g: int = 35
    refine_blue_max_g: int = 190
    refine_blue_max_r: int = 100
    refine_blue_minus_green: int = 45
    refine_blue_minus_red: int = 90
    refine_morph_open_ksize: int = 2
    refine_morph_close_w: int = 3
    refine_morph_close_h: int = 2
    # When True, draw per-segment labels and summary panel (OpenCV) on the annotated raster.
    refine_draw_measure_labels: bool = True

    low_confidence_threshold: float = 0.45
    annotation_style: str = "centerline"
    annotation_centerline_alpha: float = 0.64
    annotation_centerline_width_scale: float = 0.00345
    annotation_duct_blue_b: int = 186
    annotation_duct_blue_g: int = 74
    annotation_duct_blue_r: int = 36
    annotation_centerline_contour_hint_alpha: float = 0.0
    annotation_metadata_layout: str = "legend"
    annotation_mono_blue: bool = True
    annotation_fill_alpha: float = 0.52
    default_feet_per_drawing_inch: float | None = 4.0

    # Production hardening for public deployments (Render, etc.).
    secure_deployment: bool = False
    viewer_token_secret: str = ""
    viewer_token_ttl_seconds: int = 86_400


settings = Settings()
