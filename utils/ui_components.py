#!/usr/bin/env python3
"""
UI Components for campaign content display.
Handles all rendering and display functions for posts, calendars, and content.
"""

import base64
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Dict, List, Optional

import streamlit as st
from agno.utils.log import logger

from scripts.crewai_trend_workflow import PostPackage, PostDraft, ContentCalendar, CalendarEntry
from utils.constants import DEFAULT_NEGATIVE_PROMPT


# ============================================================================
# Helper Functions
# ============================================================================

def _image_preview_key(base_key: str, prompt: str) -> str:
    """Build a stable key for caching generated images per prompt."""
    prompt_hash = f"{abs(hash(prompt)) & 0xFFFFFFFF:08x}"
    return f"{base_key}_{prompt_hash}"


def _resolve_media_indices(base_key: str) -> Optional[int]:
    """Return post_index parsed from a base_key."""
    parts = base_key.split("_")
    try:
        return int(parts[-1])
    except ValueError:
        return None


def _get_image_url_from_database(base_key: str, prompt: str):
    """Get image URL from database based on base_key and prompt."""
    try:
        # Get current campaign result from session state
        campaign_result = st.session_state.get("campaign_result")
        if not campaign_result:
            return None

        post_index = _resolve_media_indices(base_key)
        if post_index is None:
            return None

        # Check if it's a PostPackage (new trend-based workflow)
        if hasattr(campaign_result, 'image_prompts'):
            image_prompts = getattr(campaign_result, 'image_prompts', [])
            if post_index < len(image_prompts):
                image_prompt = image_prompts[post_index]
                return getattr(image_prompt, 'image_remote_url', None)

        # Fallback: Check if it's old PostDraft structure
        posts = getattr(campaign_result, 'posts', [])
        if post_index < len(posts):
            post = posts[post_index]
            return getattr(post, 'image_remote_url', None) or getattr(post, 'image_file_path', None)

        return None

    except Exception as e:
        # Don't show errors to user, just return None
        return None


def _ensure_image_cached(
    prompt: str,
    base_key: str,
    image_data: Optional[str],
    *,
    image_path: Optional[str] = None,
    image_url: Optional[str] = None,
) -> Optional[bytes]:
    cache_seed = prompt or image_path or base_key
    cache_key = _image_preview_key(base_key, cache_seed)
    preview_cache: Dict[str, bytes] = st.session_state.setdefault("image_previews", {})

    if image_data and cache_key not in preview_cache:
        try:
            preview_cache[cache_key] = base64.b64decode(image_data)
            st.session_state["image_previews"] = preview_cache
        except Exception:
            pass

    if image_path and cache_key not in preview_cache:
        try:
            path_obj = Path(image_path)
            if path_obj.exists():
                preview_cache[cache_key] = path_obj.read_bytes()
                st.session_state["image_previews"] = preview_cache
        except Exception:
            logger.debug(f"Failed to load image from {image_path}")

    if image_url and cache_key not in preview_cache:
        try:
            if image_url.startswith("data:image"):
                _, _, payload = image_url.partition(",")
                if payload:
                    preview_cache[cache_key] = base64.b64decode(payload)
                    st.session_state["image_previews"] = preview_cache
            else:
                import httpx

                with httpx.Client(timeout=30.0) as client:
                    response = client.get(image_url)
                    response.raise_for_status()
                    preview_cache[cache_key] = response.content
                    st.session_state["image_previews"] = preview_cache
        except Exception as exc:
            logger.debug(f"Failed to load image from {image_url}: {exc}")

    return preview_cache.get(cache_key)


def _format_caption(text: str) -> str:
    escaped = escape(text or "").strip()
    return escaped.replace("\n", "<br>")


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


# ============================================================================
# Image Display Components
# ============================================================================

def render_image_preview_controls(
    prompt: str,
    base_key: str,
    initial_image: Optional[bytes] = None,
    *,
    display_image: bool = True,
    generate_image_bytes=None,
    generate_image_bytes_comfyui=None,
    update_campaign_database_with_image=None,
):
    """Render image generation model selector and preview for an image prompt.

    Note: Image generation functions must be passed in as parameters.
    """
    cache_key = _image_preview_key(base_key, prompt)
    preview_cache: Dict[str, bytes] = st.session_state.setdefault("image_previews", {})
    if initial_image and cache_key not in preview_cache:
        preview_cache[cache_key] = initial_image
        st.session_state["image_previews"] = preview_cache
    cached_image = preview_cache.get(cache_key)

    # If no cached image, try to load from database URL
    if not cached_image:
        db_image_url = _get_image_url_from_database(base_key, prompt)
        if db_image_url:
            try:
                import httpx
                with httpx.Client(timeout=30.0) as client:
                    response = client.get(db_image_url)
                    response.raise_for_status()
                    cached_image = response.content
                    # Cache the downloaded image
                    preview_cache[cache_key] = cached_image
                    st.session_state["image_previews"] = preview_cache
            except Exception as e:
                st.warning(f"Failed to load image from URL: {e}")

    if cached_image and display_image:
        st.image(cached_image, caption="Generated image preview", width="stretch")

    # Model Selection
    col1, col2 = st.columns([2, 1])

    with col1:
        selected_model = st.selectbox(
            "🤖 Select Image Generation Model:",
            options=["ComfyUI", "GPT-Image-1"],
            index=0,  # Default to ComfyUI
            key=f"model_select_{cache_key}",
            help="Choose the AI model for image generation"
        )

    with col2:
        # Generate button
        generate_clicked = st.button(
            f"🎨 Generate Image",
            key=f"generate_btn_{cache_key}",
            type="primary",
            width='stretch'
        )

    # Advanced options based on selected model
    if selected_model == "ComfyUI":
        with st.expander("🎛️ Advanced Options (ComfyUI)"):
            negative_prompt = st.text_area(
                "Negative Prompt (what to avoid):",
                value=st.session_state.get(f"negative_prompt_{cache_key}", DEFAULT_NEGATIVE_PROMPT),
                key=f"negative_prompt_{cache_key}",
                height=80,
                help="Describe what you DON'T want in the image. This helps ComfyUI avoid unwanted elements."
            )

    else:
        with st.expander("🎛️ Advanced Options (GPT-Image-1)"):
            # GPT-Image-1 specific settings
            image_size = st.selectbox(
                "Image Size:",
                ["1024x1024", "1792x1024", "1024x1792"],
                key=f"gpt_size_{cache_key}"
            )

            style_guidance = st.slider(
                "Style Guidance:",
                min_value=1,
                max_value=10,
                value=7,
                key=f"gpt_guidance_{cache_key}",
                help="Higher values follow the prompt more closely"
            )

    # Handle generation based on selected model
    if generate_clicked:
        if selected_model == "ComfyUI":
            with st.spinner("🎨 Generating image with ComfyUI…"):
                try:
                    # Get settings from session state
                    negative_prompt = st.session_state.get(f"negative_prompt_{cache_key}", DEFAULT_NEGATIVE_PROMPT)
                    workflow_name = st.session_state.get("comfyui_workflow")
                    lora_name = st.session_state.get("comfyui_lora")
                    persona_name = st.session_state.get("selected_persona", "general_influencer")
                    
                    # Make API request to backend
                    import httpx
                    import os
                    
                    backend_url = os.getenv("BACKEND_URL", "http://localhost:8080")
                    api_url = f"{backend_url}/api/images/generate"
                    
                    payload = {
                        "prompt": prompt,
                        "negative_prompt": negative_prompt,
                        "style": "professional",
                        "product_name": "general_product",
                        "kol_persona": persona_name,
                        "upload_to_gcs": True,
                        "workflow_name": workflow_name,
                        "lora_name": lora_name
                    }
                    
                    with httpx.Client(timeout=120.0) as client:
                        response = client.post(api_url, json=payload)
                        response.raise_for_status()
                        result = response.json()
                    
                    if result.get("success") and result.get("url"):
                        # Download and cache the generated image
                        image_url = result.get("url")
                        with httpx.Client(timeout=30.0) as client:
                            img_response = client.get(image_url)
                            img_response.raise_for_status()
                            image_bytes = img_response.content
                        
                        preview_cache[cache_key] = image_bytes
                        st.session_state["image_previews"] = preview_cache
                        if display_image:
                            st.image(image_bytes, caption="✨ ComfyUI Generated", width="stretch")

                        # Update database with generated image URL
                        if update_campaign_database_with_image:
                            update_campaign_database_with_image(image_url, prompt, base_key, image_bytes)

                        st.success(f"✅ Image generated and saved to GCS: {image_url}")
                    else:
                        error_msg = result.get("message", "Unknown error occurred")
                        st.error(f"❌ Image generation failed: {error_msg}")
                        
                except httpx.HTTPStatusError as e:
                    error_detail = "Unknown error"
                    try:
                        error_response = e.response.json()
                        error_detail = error_response.get("detail", str(e))
                    except:
                        error_detail = str(e)
                    st.error(f"❌ API Error: {error_detail}")
                except Exception as e:
                    st.error(f"❌ Generation failed: {str(e)}")

        elif selected_model == "GPT-Image-1" and generate_image_bytes:  # GPT-Image-1
            with st.spinner("🎨 Generating image with GPT-Image-1…"):
                # Get settings from session state
                size = st.session_state.get(f"gpt_size_{cache_key}", "1024x1024")

                image_bytes, error = generate_image_bytes(prompt, size)
                if error:
                    st.error(f"❌ GPT-Image-1 generation failed: {error}")
                elif image_bytes:
                    preview_cache[cache_key] = image_bytes
                    st.session_state["image_previews"] = preview_cache
                    if display_image:
                        st.image(image_bytes, caption="✨ GPT-Image-1 Generated", width="stretch")

                    st.info(
                        "GPT-Image-1 preview stored locally for this session. Use ComfyUI to persist images to GCS."
                    )
        else:
            st.error("❌ No generation method available. Please check your configuration.")

    return preview_cache.get(cache_key)


def display_image_prompt_with_preview(
    prompt: str,
    base_key: str,
    *,
    image_data: Optional[str] = None,
    show_prompt: bool = True,
    display_image: bool = True,
    generate_image_bytes=None,
    generate_image_bytes_comfyui=None,
    update_campaign_database_with_image=None,
):
    """Show the prompt and attach image preview controls.

    Note: Image generation functions must be passed in as parameters.
    """
    initial_image: Optional[bytes] = None
    if image_data:
        try:
            initial_image = base64.b64decode(image_data)
        except Exception as exc:
            st.warning(f"Failed to decode image data: {exc}")

    if show_prompt and prompt:
        st.info(prompt)

    if prompt:
        image_bytes = render_image_preview_controls(
            prompt,
            base_key,
            initial_image=initial_image,
            display_image=display_image,
            generate_image_bytes=generate_image_bytes,
            generate_image_bytes_comfyui=generate_image_bytes_comfyui,
            update_campaign_database_with_image=update_campaign_database_with_image,
        )
        if not display_image and image_bytes and not show_prompt:
            st.image(image_bytes, caption="Image preview", width="stretch")
    elif initial_image:
        st.image(initial_image, caption="Image preview", width="stretch")


def render_instagram_card(
    *,
    copy_text: str,
    persona: Optional[str],
    platform: Optional[str],
    image_prompt: str,
    base_key: str,
    image_data: Optional[str] = None,
    image_path: Optional[str] = None,
    image_url: Optional[str] = None,
    text_meta: Optional[List[str]] = None,
    image_meta: Optional[List[str]] = None,
    show_prompt_controls: bool = True,
    generate_image_bytes=None,
    generate_image_bytes_comfyui=None,
    update_campaign_database_with_image=None,
):
    """Render an Instagram-style card for post content."""
    image_bytes = _ensure_image_cached(
        image_prompt,
        base_key,
        image_data,
        image_path=image_path,
        image_url=image_url,
    )
    creator = persona or platform or "Creator"
    header_html = f"""
        <div class=\"ig-card\">
            <div class=\"ig-header\">
                <span class=\"ig-avatar\">📸</span>
                <span>{escape(creator)}</span>
            </div>
    """

    caption_html = _format_caption(copy_text)

    meta_items: List[str] = []
    if text_meta:
        meta_items.extend(text_meta)
    if image_meta:
        meta_items.extend(image_meta)

    with st.container():
        st.markdown(header_html, unsafe_allow_html=True)
        if image_bytes:
            encoded = base64.b64encode(image_bytes).decode("utf-8")
            st.markdown(
                f"<div class=\"ig-image\"><img src=\"data:image/png;base64,{encoded}\" alt=\"Generated visual\" /></div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div class=\"ig-image ig-missing\">No image yet – use the prompt controls below to generate.</div>",
                unsafe_allow_html=True,
            )

        st.markdown(
            f"<div class=\"ig-caption\"><strong>{escape(creator)}</strong> {caption_html}</div>",
            unsafe_allow_html=True,
        )

        if meta_items:
            st.markdown(
                f"<div class=\"ig-meta\">{' • '.join(escape(str(item)) for item in meta_items if item)}</div>",
                unsafe_allow_html=True,
            )

        if show_prompt_controls:
            with st.expander("Image prompt & regenerate"):
                if image_prompt:
                    st.caption("Image prompt")
                    st.info(image_prompt)
                    render_image_preview_controls(
                        image_prompt,
                        base_key,
                        initial_image=image_bytes,
                        display_image=True,
                        generate_image_bytes=generate_image_bytes,
                        generate_image_bytes_comfyui=generate_image_bytes_comfyui,
                        update_campaign_database_with_image=update_campaign_database_with_image,
                    )
                else:
                    st.warning("No image prompt provided for this post.")

        st.markdown("</div>", unsafe_allow_html=True)


# ============================================================================
# Calendar and Post Display Functions
# ============================================================================

def group_posts_by_date_theme(posts: list[PostDraft], calendar: ContentCalendar) -> dict:
    """Group posts by calendar date and theme for unified display."""
    from datetime import datetime, date

    # Create date -> theme mapping from calendar
    date_theme_map = {}
    for entry in calendar.entries:
        # Normalize date format
        try:
            if entry.date:
                # Try to parse as date, fallback to string
                try:
                    parsed_date = datetime.fromisoformat(entry.date.replace('Z', '+00:00')).date()
                    date_key = parsed_date.strftime('%Y-%m-%d')
                except:
                    date_key = entry.date
                date_theme_map[date_key] = entry
        except:
            continue

    # Group posts by date
    grouped = {}
    for post in posts:
        try:
            # Extract date from scheduled_at
            post_datetime = datetime.fromisoformat(post.scheduled_at.replace('Z', '+00:00'))
            post_date = post_datetime.date().strftime('%Y-%m-%d')

            if post_date not in grouped:
                grouped[post_date] = {
                    'calendar_entry': date_theme_map.get(post_date),
                    'posts': []
                }
            grouped[post_date]['posts'].append(post)
        except:
            # Fallback for posts without proper dates
            if 'unscheduled' not in grouped:
                grouped['unscheduled'] = {
                    'calendar_entry': None,
                    'posts': []
                }
            grouped['unscheduled']['posts'].append(post)

    return grouped


def display_unified_calendar_posts(
    calendar: ContentCalendar,
    posts: list[PostDraft],
    *,
    platforms: Optional[list[str]] = None,
    product_name: Optional[str] = None,
    default_url: Optional[str] = None,
    generate_image_bytes=None,
    generate_image_bytes_comfyui=None,
    update_campaign_database_with_image=None,
):
    """Display unified calendar and posts view."""
    st.markdown("### 📅 Unified Content Calendar & Posts")
    st.markdown(f"**Campaign Period:** {calendar.period}")

    # Group posts by calendar dates/themes
    grouped_content = group_posts_by_date_theme(posts, calendar)

    if not grouped_content:
        st.info("No content to display")
        return

    # Display options
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        view_mode = st.selectbox(
            "View Mode",
            ["Timeline View", "Calendar Grid", "Legacy Separate"],
            help="Choose how to display content"
        )
    with col2:
        compact_mode = st.checkbox("Compact", value=True, help="Compact display")

    if view_mode == "Legacy Separate":
        # Show old separate view
        display_content_calendar_legacy(calendar, platforms=platforms, posts=posts)
        st.divider()
        display_post_drafts(
            posts,
            generate_image_bytes=generate_image_bytes,
            generate_image_bytes_comfyui=generate_image_bytes_comfyui,
            update_campaign_database_with_image=update_campaign_database_with_image,
        )
        return

    # Sort dates for timeline view
    sorted_dates = sorted([d for d in grouped_content.keys() if d != 'unscheduled'])
    if 'unscheduled' in grouped_content:
        sorted_dates.append('unscheduled')

    # Timeline View
    if view_mode == "Timeline View":
        for date_key in sorted_dates:
            date_data = grouped_content[date_key]
            calendar_entry = date_data['calendar_entry']
            posts_for_date = date_data['posts']

            # Date header
            if date_key == 'unscheduled':
                st.markdown("#### 📝 Unscheduled Content")
            else:
                try:
                    formatted_date = datetime.strptime(date_key, '%Y-%m-%d').strftime('%B %d, %Y')
                    st.markdown(f"#### 📅 {formatted_date}")
                except:
                    st.markdown(f"#### 📅 {date_key}")

            # Calendar context
            if calendar_entry:
                col1, col2, col3 = st.columns([2, 2, 1])
                with col1:
                    st.markdown(f"**Theme:** {calendar_entry.theme}")
                with col2:
                    if calendar_entry.goal:
                        st.markdown(f"**Goal:** {calendar_entry.goal}")
                with col3:
                    if calendar_entry.recommended_time:
                        st.markdown(f"**Time:** {calendar_entry.recommended_time}")

            # Posts for this date
            if posts_for_date:
                if compact_mode:
                    # Compact post display
                    for i, post in enumerate(posts_for_date):
                        # Build title
                        title_parts = [f"📱 {post.platform.title()} Post"]
                        if hasattr(post, 'persona') and post.persona:
                            title_parts.append(f"{post.persona}")

                        with st.expander(" - ".join(title_parts), expanded=False):
                            # Build metadata
                            primary_meta = []
                            if getattr(post, "scheduled_at", None):
                                try:
                                    dt = datetime.fromisoformat(post.scheduled_at.replace('Z', '+00:00'))
                                    primary_meta.append(dt.strftime("%b %d • %I:%M %p"))
                                except Exception:
                                    primary_meta.append(post.scheduled_at)
                            if getattr(post, "character_target", None):
                                primary_meta.append(f"~{post.character_target} chars")

                            post_image_data, post_image_path, post_image_url = _extract_media_fields(post)

                            render_instagram_card(
                                copy_text=_get_text_content(post),
                                persona=getattr(post, "persona", None),
                                platform=post.platform,
                                image_prompt=post.image_prompt or "",
                                base_key=f"compact_primary_image_{date_key}_{i}",
                                image_data=post_image_data,
                                image_path=post_image_path,
                                image_url=post_image_url,
                                text_meta=primary_meta,
                                image_meta=[f"{post.platform.title()} post"] if post.platform else None,
                                generate_image_bytes=generate_image_bytes,
                                generate_image_bytes_comfyui=generate_image_bytes_comfyui,
                                update_campaign_database_with_image=update_campaign_database_with_image,
                            )
                else:
                    # Full post display
                    for i, post in enumerate(posts_for_date):
                        display_single_post_with_context(post, date_key, i)
            else:
                st.info("No posts scheduled for this date")

            st.divider()

    # Calendar Grid View (future enhancement)
    elif view_mode == "Calendar Grid":
        st.info("Calendar Grid view coming soon!")
        # Could implement a calendar widget showing posts per day

    if product_name is None or default_url is None:
        package = st.session_state.get("campaign_result")
        if package and getattr(package, "product", None):
            product_name = product_name or getattr(package.product, "name", None)
            default_url = default_url or getattr(package.product, "website", None)

    st.info("Need CSVs? Switch to the 📤 Exports tab for calendar, posts, and RecurPost downloads.")


def display_content_calendar_legacy(calendar: ContentCalendar, *, platforms: Optional[list[str]] = None, posts: Optional[list[PostDraft]] = None):
    """Legacy calendar display function."""
    st.markdown("### 📅 Content Calendar")
    st.markdown(f"**Period:** {calendar.period}")

    if calendar.entries:
        # Create a table view
        calendar_data = []
        # Prefer explicit platforms argument; else infer from posts; else from session; else none
        platforms_for_display: list[str] = []
        if platforms:
            platforms_for_display = platforms
        elif posts:
            platforms_for_display = sorted({(p.platform or 'generic').lower() for p in posts})
        else:
            platforms_for_display = st.session_state.get('selected_platforms', [])

        for entry in calendar.entries:
            calendar_data.append({
                "Date": entry.date,
                "Theme": entry.theme,
                "Goal": entry.goal or "—",
                "Time": entry.recommended_time or "—",
                "Platforms": ", ".join(platforms_for_display) if platforms_for_display else "—",
            })

        st.dataframe(calendar_data, width='stretch')
    else:
        st.info("No calendar entries available")


def display_single_post_with_context(post: PostDraft, date_key: str, post_idx: int):
    """Display a single post with complete details."""
    # Platform and persona header
    platform_label = (post.platform or "generic").title()
    header_parts = [f"📱 {platform_label}"]
    if hasattr(post, 'persona') and post.persona:
        header_parts.append(f"👤 {post.persona}")

    with st.expander(" | ".join(header_parts), expanded=True):
        if post.title:
            st.markdown(f"**{post.title}**")

        # Build metadata
        primary_meta = []
        if getattr(post, "scheduled_at", None):
            try:
                dt = datetime.fromisoformat(post.scheduled_at.replace('Z', '+00:00'))
                primary_meta.append(dt.strftime("%b %d • %I:%M %p"))
            except Exception:
                primary_meta.append(post.scheduled_at)
        if getattr(post, "character_target", None):
            primary_meta.append(f"~{post.character_target} chars")


def display_post_drafts(
    posts: list[PostDraft],
    generate_image_bytes=None,
    generate_image_bytes_comfyui=None,
    update_campaign_database_with_image=None,
):
    """Display the generated post drafts."""
    st.markdown("### 📝 Generated Posts")

    if not posts:
        st.info("No posts generated yet")
        return

    # Build global index for posts for cross-referencing similarity neighbors
    global_index = {id(p): i for i, p in enumerate(st.session_state.campaign_result.posts)} if hasattr(st.session_state, 'campaign_result') and st.session_state.campaign_result and getattr(st.session_state.campaign_result, 'posts', None) else {}
    sim = getattr(st.session_state.campaign_result, 'similarity_report', None) if hasattr(st.session_state, 'campaign_result') else None
    neighbors = getattr(sim, 'neighbors', None) if sim else None

    # Group posts by platform
    platforms = {}
    for post in posts:
        platform = post.platform or "generic"
        if platform not in platforms:
            platforms[platform] = []
        platforms[platform].append(post)

    # Create tabs for each platform
    platform_tabs = st.tabs(list(platforms.keys()))

    global_post_counter = 0  # Global unique counter for keys

    for idx, (platform, platform_posts) in enumerate(platforms.items()):
        with platform_tabs[idx]:
            st.markdown(f"**{len(platform_posts)} posts for {platform.UPPER()}**")

            for post_idx, post in enumerate(platform_posts, 1):
                global_post_counter += 1  # Increment global counter
                label_bits = [f"Post {post_idx}"]
                if getattr(post, "persona", None):
                    label_bits.append(f"{post.persona}")
                date_bit = post.scheduled_at[:10] if post.scheduled_at else "Unscheduled"
                label_bits.append(date_bit)
                with st.expander(" - ".join(label_bits), expanded=True):
                    col1, col2 = st.columns([2, 1])

                    with col1:
                        if post.title:
                            st.markdown(f"**{post.title}**")

                        # Create tabbed interface for content variants
                        if hasattr(post, 'text_variants') and post.text_variants:
                            st.markdown("**📝 Content:**")
                            text_tab_names = ["Primary"] + [v.variant_type.title() for v in post.text_variants]
                            text_tabs = st.tabs(text_tab_names)

                            # Primary content
                            with text_tabs[0]:
                                st.text_area("Content", value=_get_text_content(post), height=150, disabled=True,
                                            key=f"legacy_text_primary_{global_post_counter}")
                                st.caption("💡 Primary/default version")

                            # Display each variant
                            for vi, variant in enumerate(post.text_variants):
                                with text_tabs[vi + 1]:
                                    st.text_area("Content", value=_get_text_content(variant), height=150, disabled=True,
                                                key=f"legacy_text_var_{global_post_counter}_{vi}")

                                    # Show metadata
                                    metadata = []
                                    if variant.mood_applied:
                                        metadata.append(f"💭 Mood: {variant.mood_applied}")
                                    if variant.hook_style:
                                        metadata.append(f"🎣 Hook: {variant.hook_style}")
                                    if metadata:
                                        st.caption(" | ".join(metadata))
                                    else:
                                        st.caption(f"📌 {variant.variant_type.title()} style")
                        else:
                            # No variants, just show primary content
                            st.markdown("**📝 Content:**")
                            st.text_area("Content", value=_get_text_content(post), height=150, disabled=True,
                                        key=f"legacy_text_only_{global_post_counter}")
                            st.info("ℹ️ No text variants available")

                        if post.character_target:
                            st.caption(f"Character target: {post.character_target}")

                        # Similar posts (post-wise similarity)
                        try:
                            if neighbors:
                                gi = global_index.get(id(post), None)
                                if gi is not None and gi < len(neighbors):
                                    items = neighbors[gi] or []
                                    if items:
                                        st.markdown("**🔎 Similar Posts:**")
                                        for nb in items:
                                            # nb might be a dict or pydantic model
                                            j = getattr(nb, 'j', nb.get('j') if isinstance(nb, dict) else None)
                                            simv = getattr(nb, 'sim', nb.get('sim') if isinstance(nb, dict) else 0.0)
                                            plat = getattr(nb, 'platform', nb.get('platform') if isinstance(nb, dict) else '')
                                            persona = getattr(nb, 'persona', nb.get('persona') if isinstance(nb, dict) else '')
                                            snippet = getattr(nb, 'snippet', nb.get('snippet') if isinstance(nb, dict) else '')
                                            st.write(f"• #{j} [{plat or 'generic'}]{' • ' + persona if persona else ''} — cos={float(simv):.3f}")
                                            if snippet:
                                                st.caption(snippet)
                                    else:
                                        st.caption("No similar posts found.")
                        except Exception:
                            pass

                    with col2:
                        # Create tabbed interface for image variants
                        if hasattr(post, 'image_variants') and post.image_variants:
                            st.markdown("**📷 Image:**")
                            image_tab_names = ["Primary"] + [v.variant_type.title() for v in post.image_variants]
                            image_tabs = st.tabs(image_tab_names)

                            # Primary image
                            with image_tabs[0]:
                                display_image_prompt_with_preview(
                                    post.image_prompt,
                                    f"legacy_primary_image_{global_post_counter}",
                                    image_data=getattr(post, "image_data", None),
                                    generate_image_bytes=generate_image_bytes,
                                    generate_image_bytes_comfyui=generate_image_bytes_comfyui,
                                    update_campaign_database_with_image=update_campaign_database_with_image,
                                )
                                st.caption("💡 Primary/default image prompt")

                            # Display each variant
                            for vi, variant in enumerate(post.image_variants):
                                with image_tabs[vi + 1]:
                                    display_image_prompt_with_preview(
                                        variant.image_prompt,
                                        f"legacy_variant_image_{global_post_counter}_{vi}",
                                        image_data=getattr(variant, "image_data", None),
                                        generate_image_bytes=generate_image_bytes,
                                        generate_image_bytes_comfyui=generate_image_bytes_comfyui,
                                        update_campaign_database_with_image=update_campaign_database_with_image,
                                    )

                                    # Show metadata
                                    if variant.aesthetic_focus:
                                        st.caption(f"🎨 Focus: {variant.aesthetic_focus}")
                                    else:
                                        st.caption(f"📌 {variant.variant_type.title()} style")
                        else:
                            # No variants, just show primary image prompt
                            st.markdown("**📷 Image:**")
                            display_image_prompt_with_preview(
                                post.image_prompt,
                                f"legacy_single_image_{global_post_counter}",
                                image_data=getattr(post, "image_data", None),
                                generate_image_bytes=generate_image_bytes,
                                generate_image_bytes_comfyui=generate_image_bytes_comfyui,
                                update_campaign_database_with_image=update_campaign_database_with_image,
                            )
                            st.info("ℹ️ No image variants available")

                        if post.video_idea:
                            st.markdown("**🎥 Video Idea:**")
                            st.success(post.video_idea)

                        st.markdown("**🕐 Schedule:**")
                        if post.scheduled_at:
                            try:
                                dt = datetime.fromisoformat(post.scheduled_at.replace('Z', '+00:00'))
                                st.write(dt.strftime("%B %d, %Y at %I:%M %p"))
                            except:
                                st.write(post.scheduled_at)

                        if post.timezone:
                            st.caption(f"Timezone: {post.timezone}")


# ============================================================================
# PostPackage Display Functions
# ============================================================================

def get_post_package_size(post_package: PostPackage) -> int:
    """Get the number of posts in a PostPackage."""
    return len(post_package.content_seeds)


def iter_post_package_items(post_package: PostPackage, persona_name: str):
    """
    Iterate over PostPackage items, yielding tuples of (index, seed, visual, caption, image_prompt).
    This provides a unified interface for display functions.
    """
    for i in range(len(post_package.content_seeds)):
        seed = post_package.content_seeds[i]
        visual = post_package.visual_plans[i] if i < len(post_package.visual_plans) else None
        caption = post_package.captions[i] if i < len(post_package.captions) else None
        image_prompt = post_package.image_prompts[i] if i < len(post_package.image_prompts) else None
        yield i, seed, visual, caption, image_prompt, persona_name


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


def create_minimal_calendar_from_post_package(post_package: PostPackage) -> ContentCalendar:
    """Create a minimal ContentCalendar from PostPackage for compatibility."""
    from datetime import datetime, timedelta

    num_posts = get_post_package_size(post_package)
    entries = []

    # Create simple daily entries
    for i in range(num_posts):
        seed = post_package.content_seeds[i] if i < len(post_package.content_seeds) else None
        entry = CalendarEntry(
            date=(datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d"),
            theme=f"{seed.tier}: {seed.micro_idea[:50]}..." if seed else f"Post {i+1}",
            goal=seed.content_category if seed else None
        )
        entries.append(entry)

    return ContentCalendar(
        period=f"{num_posts} posts",
        entries=entries
    )


def display_post_package_posts(
    post_package: PostPackage,
    persona_name: str,
    generate_image_bytes=None,
    generate_image_bytes_comfyui=None,
    update_campaign_database_with_image=None,
):
    """Display posts directly from PostPackage structure."""
    st.markdown("### 📝 Generated Posts")

    num_posts = get_post_package_size(post_package)
    if num_posts == 0:
        st.info("No posts generated yet")
        return

    st.markdown(f"**{num_posts} posts for Instagram**")

    # Iterate through all posts
    for idx, seed, visual, caption, image_prompt, persona in iter_post_package_items(post_package, persona_name):
        post_num = idx + 1

        # Build post header
        label_bits = [f"Post {post_num}"]
        if persona:
            label_bits.append(f"{persona}")
        if seed:
            label_bits.append(f"{seed.tier}")

        with st.expander(" - ".join(label_bits), expanded=True):
            # Title from seed
            if seed:
                st.markdown(f"**{seed.tier}: {seed.micro_idea}**")
                st.caption(f"Category: {seed.content_category}")

            # Caption content (AI-generated by CrewAI)
            st.markdown("**📝 AI-Generated Caption:**")
            caption_text = get_post_package_caption_text(caption)

            # Display the AI-generated caption as read-only text
            st.info(caption_text if caption_text else "No caption generated")

            # Optional: Show raw caption components in expander for debugging
            if caption:
                with st.expander("🔍 View Caption Components"):
                    st.markdown(f"**Caption Text:** {caption.caption}")
                    st.markdown(f"**Hashtags:** {' '.join(caption.hashtags) if caption.hashtags else 'None'}")
                    st.markdown(f"**CTA:** {caption.cta if caption.cta else 'None'}")

            # Visual plan details
            if visual and visual.post_spec:
                with st.expander("📋 Visual Plan"):
                    st.write(visual.post_spec)
                    if visual.image_descriptions:
                        st.markdown("**Image Description:**")
                        for desc in visual.image_descriptions:
                            st.info(desc)

            # Image prompt
            st.markdown("**📷 Image:**")

            # Show image URL link if available
            if image_prompt and hasattr(image_prompt, 'image_remote_url') and image_prompt.image_remote_url:
                st.markdown(f"**Image URL:** [{image_prompt.image_remote_url}]({image_prompt.image_remote_url})")

            img_prompt = get_post_package_image_prompt(image_prompt)
            if img_prompt:
                display_image_prompt_with_preview(
                    img_prompt,
                    f"postpkg_image_{idx}",
                    show_prompt=True,
                    display_image=True,
                    generate_image_bytes=generate_image_bytes,
                    generate_image_bytes_comfyui=generate_image_bytes_comfyui,
                    update_campaign_database_with_image=update_campaign_database_with_image,
                )
            else:
                st.warning("No image prompt available")


def display_post_package_overview(post_package: PostPackage, persona_name: str):
    """Display overview of PostPackage content."""
    st.markdown("### Campaign Overview")

    # Persona badge
    st.markdown("### 👥 Activated KOL Persona")
    badge_html = f"<span class='badge'>{escape(persona_name)}</span>"
    st.markdown(f"<div class='badges'>{badge_html}</div>", unsafe_allow_html=True)

    # Content summary
    num_posts = get_post_package_size(post_package)
    if num_posts > 0:
        st.markdown("### 📊 Content Summary")
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Total Posts", num_posts)

        with col2:
            st.metric("Platform", "Instagram")

        with col3:
            # Count categories
            categories = {seed.content_category for seed in post_package.content_seeds if seed.content_category}
            st.metric("Categories", len(categories))

        # Show tier distribution
        st.markdown("**Content Tier Distribution:**")
        tier_counts = {}
        for seed in post_package.content_seeds:
            tier_counts[seed.tier] = tier_counts.get(seed.tier, 0) + 1

        cols = st.columns(len(tier_counts))
        for i, (tier, count) in enumerate(sorted(tier_counts.items())):
            with cols[i]:
                st.metric(tier, count)

    # Export guidance
    st.markdown("### 💾 Export Options")
    col_intro, col_json = st.columns([2, 1])
    with col_intro:
        st.info("Use the 📤 Exports tab to download content. JSON is available below.")
    with col_json:
        json_data = post_package.model_dump_json(indent=2)
        st.download_button(
            label="📥 Download as JSON",
            data=json_data,
            file_name=f"post_package_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            key="overview_json_export",
        )


def display_post_package_calendar(post_package: PostPackage):
    """Display calendar view of PostPackage content."""
    st.markdown("### 📅 Content Calendar")

    calendar = create_minimal_calendar_from_post_package(post_package)
    st.markdown(f"**Period:** {calendar.period}")

    if calendar.entries:
        calendar_data = []
        for entry in calendar.entries:
            calendar_data.append({
                "Date": entry.date,
                "Theme": entry.theme,
                "Category": entry.goal or "—",
                "Platform": "Instagram"
            })

        st.dataframe(calendar_data, width="stretch")
    else:
        st.info("No calendar entries available")
