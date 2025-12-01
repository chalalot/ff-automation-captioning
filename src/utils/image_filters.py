import io
import logging
import numpy as np
from PIL import Image, ImageEnhance

logger = logging.getLogger(__name__)

def apply_stable_film_look(image_bytes: bytes) -> bytes:
    """
    Apply a stable film look filter to the image bytes.
    
    Args:
        image_bytes: Raw image data in bytes
        
    Returns:
        Processed image data in bytes (PNG format)
    """
    # --- 1. CONFIGURATION (THE RECIPE) ---
    SETTINGS = {
        "seed": 42,             # THE LOCK: Keeps grain pattern identical every time
        "brightness": 0.95,     # +5% Brightness
        "contrast": 0.95,       # +15% Contrast
        "warmth": 0.95,         # 1.10 = +10% Red (Warmer)
        "coolness": 1.05,       # 0.95 = -5% Blue (Less Cold)
        "saturation": 0.90,     # -10% Saturation (Vintage feel)
        "grain_intensity": 0.03,# REDUCED: 0.10 is subtle, 0.18 was heavy
        "black_lift": 10        # Matte shadow strength
    }

    try:
        # LOGGING
        logger.info("-" * 40)
        logger.info("Applying Stable Film Look Settings:")
        for key, val in SETTINGS.items():
            logger.info(f"  [+] {key.ljust(15)} : {val}")
        logger.info("-" * 40)

        # LOAD
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

        # PRESERVE ALPHA
        # Note: We are converting to RGB for processing, alpha channel preservation
        # needs to be handled if the output requires transparency. 
        # The filter logic mainly operates on RGB.
        # Re-attaching alpha at the end if needed, but typical comfy output is opaque.
        # If input has alpha, we might want to keep it.
        has_alpha = 'A' in img.getbands()
        if has_alpha:
            alpha = img.getchannel('A')
        
        rgb_img = img.convert("RGB")

        # --- STEP 1: COLOR TEMP (WARMTH) ---
        logger.info("... Adjusting Color Temperature (Sun Effect)")
        r, g, b = rgb_img.split()
        r = r.point(lambda i: i * SETTINGS["warmth"])
        b = b.point(lambda i: i * SETTINGS["coolness"])
        rgb_img = Image.merge('RGB', (r, g, b))

        # --- STEP 2: STANDARD TUNING ---
        logger.info("... Applying Brightness / Contrast / Saturation")
        rgb_img = ImageEnhance.Color(rgb_img).enhance(SETTINGS["saturation"])
        rgb_img = ImageEnhance.Brightness(rgb_img).enhance(SETTINGS["brightness"])
        rgb_img = ImageEnhance.Contrast(rgb_img).enhance(SETTINGS["contrast"])

        # --- STEP 3: MATTE BLACKS ---
        logger.info(f"... Lifting Blacks by {SETTINGS['black_lift']} units")
        lookup = []
        for i in range(256):
            val = i + SETTINGS["black_lift"] * (1 - (i/255.0))
            lookup.append(int(val))
        rgb_img = rgb_img.point(lookup * 3)

        # --- STEP 4: FIXED GRAIN ---
        logger.info(f"... Generating Fixed Grain Map (Seed: {SETTINGS['seed']})")
        
        # LOCK THE RANDOMNESS
        np.random.seed(SETTINGS["seed"]) 
        
        arr = np.array(rgb_img)
        
        # Generate noise based on the locked seed
        noise = np.random.normal(0, 255 * SETTINGS["grain_intensity"], arr.shape)
        
        # Add noise
        grainy_arr = arr + noise
        grainy_arr = np.clip(grainy_arr, 0, 255).astype('uint8')
        final_rgb = Image.fromarray(grainy_arr)
        
        # Restore alpha if it existed
        if has_alpha:
            final_rgb.putalpha(alpha)

        # Save to bytes
        output_buffer = io.BytesIO()
        final_rgb.save(output_buffer, format="PNG")
        return output_buffer.getvalue()

    except Exception as e:
        logger.error(f"Error applying film look filter: {e}", exc_info=True)
        # Return original bytes if filter fails to avoid breaking the pipeline
        return image_bytes
