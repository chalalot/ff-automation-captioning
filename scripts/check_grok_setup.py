import os
import sys
import logging

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add project root to path
try:
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.append(project_root)
except Exception:
    project_root = os.getcwd()
    sys.path.append(project_root)

# Load env
from dotenv import load_dotenv
load_dotenv()

from src.config import GlobalConfig

def check_grok_setup():
    logger.info("=== Checking Grok Setup for VM ===")
    
    # 1. Check Imports
    logger.info("1. Checking Dependencies...")
    try:
        import crewai
        logger.info(f"✅ CrewAI installed: {crewai.__version__ if hasattr(crewai, '__version__') else 'Unknown version'}")
    except ImportError as e:
        logger.error(f"❌ CrewAI Import Failed: {e}")
        return

    try:
        import litellm
        logger.info(f"✅ LiteLLM installed: {litellm.__version__ if hasattr(litellm, '__version__') else 'Unknown version'}")
        
        # Disable Telemetry for test
        litellm.telemetry = False
        litellm.success_callback = []
        litellm.failure_callback = []
        logger.info("✅ Disabled LiteLLM Telemetry for test")

    except ImportError as e:
        logger.error(f"❌ LiteLLM Import Failed: {e}")
        return

    # 2. Check API Key
    logger.info("2. Checking API Key...")
    api_key = GlobalConfig.GROK_API_KEY
    if not api_key:
        logger.error("❌ GROK_API_KEY is missing in environment/config!")
        return
    else:
        logger.info(f"✅ GROK_API_KEY found (starts with: {api_key[:5]}...)")

    # 3. Simulate Environment Fix
    logger.info("3. Applying Environment Fix...")
    # This is what we are adding to the main code to make it robust
    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["OPENAI_API_BASE"] = "https://api.x.ai/v1"
    logger.info(f"Set OPENAI_API_KEY to Grok Key")
    logger.info(f"Set OPENAI_API_BASE to https://api.x.ai/v1")

    # 4. Initialize LLM
    logger.info("4. Initializing CrewAI LLM...")
    try:
        from crewai import LLM
        # Note: We use the same initialization as in the fixed code
        llm = LLM(
            model="openai/grok-2-vision-1212", 
            # We don't strictly need to pass base_url/api_key here if env vars are set,
            # but passing them is also fine. We'll mirror the code.
            base_url="https://api.x.ai/v1",
            api_key=api_key
        )
        logger.info("✅ LLM Initialized successfully")
    except Exception as e:
        logger.error(f"❌ LLM Initialization Failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # 5. Test Call
    logger.info("5. Testing Generation...")
    try:
        messages = [{"role": "user", "content": "Hello, are you Grok?"}]
        response = llm.call(messages)
        logger.info(f"✅ Response received: {response}")
    except Exception as e:
        logger.error(f"❌ Generation Failed: {e}")
        import traceback
        traceback.print_exc()
        return

    logger.info("=== Setup Verification Complete: SUCCESS ===")

if __name__ == "__main__":
    check_grok_setup()
