#!/usr/bin/env python3
"""
Export utilities for campaign content.
Handles CSV generation, RecurPost formatting, and export rendering.
"""

import csv
import io
import re
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

import streamlit as st

from utils.constants import PLATFORM_TO_RECURPOST_FIELD, RECURPOST_FIELD_ORDER
from scripts.crewai_trend_workflow import PostDraft, ContentCalendar


# ============================================================================
# Helper Functions
# ============================================================================

def _get_text_content(obj) -> str:
    """Extract primary text content from post/variant objects safely."""
    value = getattr(obj, "content", None)
    if isinstance(value, str):
        return value
    if callable(value):  # guard against BaseModel.copy method
        return ""
    value = getattr(obj, "copy", None)
    if isinstance(value, str):
        return value
    if callable(value):
        return ""
    return value or "" if value else ""


def _extract_media_fields(obj) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return image data, local path, and remote URL regardless of object type."""
    data: Optional[str] = None
    path: Optional[str] = None
    url: Optional[str] = None

    if isinstance(obj, dict):
        data = obj.get("image_data")
        path = obj.get("image_file_path")
        url = obj.get("image_remote_url")
    else:
        data = getattr(obj, "image_data", None)
        path = getattr(obj, "image_file_path", None)
        url = getattr(obj, "image_remote_url", None)

    return data, path, url


def _slugify_filename(value: str) -> str:
    """Return a filesystem-friendly slug for filenames."""
    if not value:
        return "kol"
    slug = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "kol"


def _extract_first_url(text: Optional[str]) -> Optional[str]:
    """Extract the first URL-like token from text."""
    if not text:
        return None
    match = re.search(r"(https?://[^\s]+)", text)
    if not match:
        return None
    url = match.group(1)
    return url.rstrip('.,);!?")')


def _resolve_recurpost_column(platform: Optional[str]) -> Optional[str]:
    """Map internal platform identifiers to RecurPost column names."""
    if not platform:
        return None
    key = platform.strip().lower()
    candidates = [
        key,
        key.replace(" ", "_"),
        key.replace("-", "_"),
        key.replace("_", ""),
    ]
    for candidate in candidates:
        column = PLATFORM_TO_RECURPOST_FIELD.get(candidate)
        if column:
            return column
    return PLATFORM_TO_RECURPOST_FIELD.get(key)


# ============================================================================
# Posts CSV Generation
# ============================================================================

def generate_posts_csv(posts: list[PostDraft]) -> str:
    """Generate CSV for posts (extracted for reuse)."""
    output = io.StringIO()
    fieldnames = [
        "platform", "persona", "scheduled_at",
        "primary_copy", "primary_image", "video_idea",
        "content_category", "content_category_reason"
    ]

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for post in posts:
        row_data = {
            "platform": post.platform,
            "persona": getattr(post, "persona", ""),
            "scheduled_at": post.scheduled_at,
            "primary_copy": _get_text_content(post),
            "primary_image": post.image_prompt,
            "video_idea": post.video_idea or "",
            "content_category": getattr(post, "content_category", ""),
            "content_category_reason": getattr(post, "content_category_reason", ""),
        }

        writer.writerow(row_data)

    return output.getvalue()


# ============================================================================
# RecurPost CSV Generation
# ============================================================================

def generate_recurpost_csv(
    posts: list[PostDraft],
    persona_name: Optional[str],
    default_url: Optional[str] = None,
) -> str:
    """Build a RecurPost-compatible CSV for a single persona/KOL."""
    target = (persona_name or "").strip().lower()

    def _match_persona(post_persona: Optional[str]) -> bool:
        value = (post_persona or "").strip().lower()
        if target:
            return value == target
        return value == ""

    filtered_posts = [post for post in posts if _match_persona(getattr(post, "persona", None))]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=RECURPOST_FIELD_ORDER)
    writer.writeheader()

    if not filtered_posts:
        return output.getvalue()

    filtered_posts.sort(key=lambda post: getattr(post, "scheduled_at", ""))

    for post in filtered_posts:
        row = {field: "" for field in RECURPOST_FIELD_ORDER}

        copy_text = _get_text_content(post).strip()
        if copy_text:
            row["Original Message"] = copy_text

        column_name = _resolve_recurpost_column(getattr(post, "platform", None))
        if column_name and copy_text:
            row[column_name] = copy_text

        post_url = (
            getattr(post, "post_url", None)
            or getattr(post, "link_url", None)
            or getattr(post, "url", None)
            or _extract_first_url(copy_text)
        )
        if not post_url and default_url:
            post_url = default_url
        if post_url:
            row["Post URL"] = post_url

        # Capture any platform-specific comment metadata if present
        if getattr(post, "first_comment", None):
            row["Original First Comment"] = getattr(post, "first_comment")

        if column_name == "Facebook Message" and getattr(post, "facebook_first_comment", None):
            row["Facebook First Comment"] = getattr(post, "facebook_first_comment")

        if column_name == "Linkedin Message":
            if getattr(post, "linkedin_first_comment", None):
                row["Linkedin First Comment"] = getattr(post, "linkedin_first_comment")
            if getattr(post, "linkedin_document", None):
                row["Linkedin Document"] = getattr(post, "linkedin_document")
            if getattr(post, "linkedin_document_title", None):
                row["Linkedin Document Title"] = getattr(post, "linkedin_document_title")

        if column_name == "Instagram Message":
            if getattr(post, "instagram_first_comment", None):
                row["Instagram First Comment"] = getattr(post, "instagram_first_comment")
            if getattr(post, "instagram_post_type", None):
                row["Instagram Post Type"] = getattr(post, "instagram_post_type")

        # Image URLs: capture primary image only
        _, primary_path, primary_url = _extract_media_fields(post)
        primary_candidate = primary_url or primary_path
        if (
            isinstance(primary_candidate, str)
            and primary_candidate
            and primary_candidate.startswith(("http://", "https://"))
        ):
            row["Image URL 1"] = primary_candidate

        video_url = (
            getattr(post, "video_url", None)
            or getattr(post, "video_asset_url", None)
            or getattr(post, "video_link", None)
            or _extract_first_url(getattr(post, "video_idea", None))
        )
        if isinstance(video_url, str) and video_url:
            row["Video Url"] = video_url

        writer.writerow(row)

    return output.getvalue()


def _build_recurpost_filename(
    persona_name: Optional[str],
    product_name: Optional[str],
    period: Optional[str],
) -> str:
    persona_slug = _slugify_filename(persona_name or "kol")
    product_slug = _slugify_filename(product_name or "campaign")
    period_slug = _slugify_filename(period or "period")
    return f"{persona_slug}_{product_slug}_{period_slug}.csv"


def prepare_recurpost_exports(
    posts: Optional[List[PostDraft]],
    *,
    product_name: Optional[str],
    period: Optional[str],
    default_url: Optional[str],
) -> list[tuple[str, str, str]]:
    """Prepare persona-labelled CSV payloads ready for download buttons."""
    if not posts:
        return []

    persona_buckets: Dict[str, List[PostDraft]] = defaultdict(list)
    for post in posts:
        persona_key = (getattr(post, "persona", "") or "").strip()
        persona_buckets[persona_key].append(post)

    if not persona_buckets:
        # Fall back to selected personas (legacy caches) or a single generic bucket
        fallback_personas = st.session_state.get("selected_personas") or []
        if fallback_personas:
            for name in fallback_personas:
                persona_buckets.setdefault(name.strip(), list(posts))
        else:
            persona_buckets[""] = list(posts)

    exports: List[tuple[str, str, str]] = []

    for persona_key, persona_posts in persona_buckets.items():
        persona_label = persona_key.strip() if persona_key else "KOL"
        csv_payload = generate_recurpost_csv(persona_posts, persona_key or None, default_url=default_url)
        if not csv_payload.strip():
            continue
        filename = _build_recurpost_filename(persona_label, product_name, period)
        exports.append((persona_label, csv_payload, filename))

    return exports


# ============================================================================
# PostPackage CSV Generation
# ============================================================================

def generate_post_package_csv(post_package, persona_name: str) -> str:
    """Generate CSV export from PostPackage."""
    from scripts.crewai_trend_workflow import PostPackage

    output = io.StringIO()
    fieldnames = [
        "post_num", "persona", "tier", "category",
        "micro_idea", "caption", "image_prompt"
    ]

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    # Helper functions for PostPackage
    def get_post_package_caption_text(caption) -> str:
        """Extract caption text from PostPackage CaptionContent object."""
        if not caption:
            return ""
        caption_text = caption.caption or ""
        if caption.hashtags:
            caption_text += f"\n\n{' '.join(caption.hashtags)}"
        if caption.cta:
            caption_text += f"\n\n{caption.cta}"
        return caption_text

    def get_post_package_image_prompt(image_prompt) -> str:
        """Extract image prompt from PostPackage ImagePrompt object."""
        if not image_prompt:
            return ""
        return image_prompt.positive_prompt or ""

    for i in range(len(post_package.content_seeds)):
        seed = post_package.content_seeds[i]
        visual = post_package.visual_plans[i] if i < len(post_package.visual_plans) else None
        caption = post_package.captions[i] if i < len(post_package.captions) else None
        image_prompt = post_package.image_prompts[i] if i < len(post_package.image_prompts) else None

        row_data = {
            "post_num": i + 1,
            "persona": persona_name,
            "tier": seed.tier if seed else "",
            "category": seed.content_category if seed else "",
            "micro_idea": seed.micro_idea if seed else "",
            "caption": get_post_package_caption_text(caption),
            "image_prompt": get_post_package_image_prompt(image_prompt)
        }
        writer.writerow(row_data)

    return output.getvalue()


# ============================================================================
# Streamlit Rendering Functions
# ============================================================================

def render_recurpost_downloads(
    posts: Optional[List[PostDraft]],
    *,
    product_name: Optional[str],
    period: Optional[str],
    default_url: Optional[str],
    key_prefix: str,
) -> None:
    """Render RecurPost CSV download buttons, always showing the section."""
    st.markdown("#### 🎯 RecurPost CSV Export")
    current_posts = posts
    if not current_posts:
        campaign_result = st.session_state.get("campaign_result")
        if campaign_result and getattr(campaign_result, "posts", None):
            current_posts = campaign_result.posts

    exports = prepare_recurpost_exports(
        current_posts,
        product_name=product_name,
        period=period,
        default_url=default_url,
    )
    if not exports:
        st.info("No posts available to convert to RecurPost CSV yet.")
        return

    for idx, (persona_label, csv_payload, filename) in enumerate(exports):
        st.download_button(
            label=f"📥 RecurPost CSV • {persona_label}",
            data=csv_payload,
            file_name=filename,
            mime="text/csv",
            key=f"{key_prefix}_recurpost_{idx}_{filename}"
        )


def render_export_center(
    calendar: Optional[ContentCalendar],
    posts: Optional[List[PostDraft]],
    *,
    product_name: Optional[str],
    default_url: Optional[str],
    key_prefix: str,
) -> None:
    """Display aggregated export buttons for calendar, posts, and RecurPost."""
    st.markdown("### 📤 Export Center")

    col1, col2 = st.columns(2)
    with col1:
        if calendar:
            calendar_csv = calendar.to_csv()
            st.download_button(
                label="📅 Download Calendar CSV",
                data=calendar_csv,
                file_name=f"content_calendar_{calendar.period.replace(' ', '_')}.csv" if getattr(calendar, "period", None) else "content_calendar.csv",
                mime="text/csv",
                help="Calendar themes and schedule",
                key=f"{key_prefix}_calendar_csv",
            )
        else:
            st.info("Calendar unavailable for export.")

    with col2:
        if posts:
            posts_csv = generate_posts_csv(posts)
            st.download_button(
                label="📝 Download Posts CSV",
                data=posts_csv,
                file_name=f"posts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                help="Complete post content with variants",
                key=f"{key_prefix}_posts_csv",
            )
        else:
            st.info("No posts available to export yet.")

    render_recurpost_downloads(
        posts,
        product_name=product_name,
        period=getattr(calendar, "period", None) if calendar else None,
        default_url=default_url,
        key_prefix=f"{key_prefix}_recurpost",
    )
