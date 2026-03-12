import asyncio
import logging
from celery_app import celery_app
from src.workflows.image_to_prompt_workflow import ImageToPromptWorkflow
from src.third_parties.comfyui_client import ComfyUIClient
from src.database.image_logs_storage import ImageLogsStorage
from utils.constants import DEFAULT_NEGATIVE_PROMPT

logger = logging.getLogger(__name__)

from scripts.populate_generated_images import main as run_populate_images_async

# Re-use instances if possible, but workflow might be stateful, so we'll instantiate inside the task or setup cleanly

@celery_app.task(name="tasks.run_populate_images")
def run_populate_images():
    """
    Background task to populate generated images via Celery Beat.
    """
    try:
        asyncio.run(run_populate_images_async())
    except Exception as e:
        logger.error(f"Error in run_populate_images: {e}")

@celery_app.task(bind=True, name="tasks.process_image_task")
def process_image_task(self, dest_image_path, persona, workflow_type, vision_model, variation_count, strength_model, seed_strategy, base_seed, width, height, lora_name):
    """
    Celery task to run the CrewAI workflow and queue to ComfyUI.
    This runs asynchronously within an event loop since the core components use asyncio.
    """
    try:
        self.update_state(state='STARTING', meta={'status': f"⏳ Initializing task...", 'progress': 10})
        return asyncio.run(async_process_image(
            dest_image_path=dest_image_path,
            persona=persona,
            workflow_type=workflow_type,
            vision_model=vision_model,
            variation_count=variation_count,
            strength_model=strength_model,
            seed_strategy=seed_strategy,
            base_seed=base_seed,
            width=width,
            height=height,
            lora_name=lora_name,
            task=self
        ))
    except Exception as e:
        logger.error(f"Error in process_image_task for {dest_image_path}: {e}")
        raise e

# Global instances to reuse across task executions
_workflow = None
_client = None
_storage = None

def get_instances():
    global _workflow, _client, _storage
    if _workflow is None:
        _workflow = ImageToPromptWorkflow(verbose=False)
    if _client is None:
        _client = ComfyUIClient()
    if _storage is None:
        _storage = ImageLogsStorage()
    return _workflow, _client, _storage

async def async_process_image(dest_image_path, persona, workflow_type, vision_model, variation_count, strength_model, seed_strategy, base_seed, width, height, lora_name, task):
    workflow, client, storage = get_instances()
    
    logger.info(f"Generating {variation_count} prompt(s) for {dest_image_path}...")
    task.update_state(state='GENERATING_PROMPT', meta={'status': f"🤖 CrewAI analyzing image and writing {variation_count} prompt(s)...", 'progress': 40})
    
    result = await workflow.process(
        image_path=dest_image_path,
        persona_name=persona,
        workflow_type=workflow_type,
        vision_model=vision_model,
        variation_count=variation_count
    )
    
    prompts = result.get('generated_prompts', [result.get('generated_prompt')])
    successful_queues_for_image = 0
    execution_ids = []
    
    for i, prompt_content in enumerate(prompts):
        logger.info(f"Queueing execution for {dest_image_path} (Variation {i+1}/{len(prompts)})...")
        
        # Calculate dynamic progress (between 60% and 90% based on iteration)
        prog = int(60 + (30 * (i / len(prompts))))
        task.update_state(state='QUEUEING_COMFY', meta={'status': f"🎨 Sending variation {i+1}/{len(prompts)} to ComfyUI...", 'progress': prog})
        
        execution_id = await client.generate_image(
            positive_prompt=prompt_content,
            negative_prompt=DEFAULT_NEGATIVE_PROMPT,
            kol_persona=persona,
            workflow_type=workflow_type,
            strength_model=strength_model,
            seed_strategy=seed_strategy,
            base_seed=base_seed,
            width=width,
            height=height,
            lora_name=lora_name
        )
        
        if execution_id:
            logger.info(f"✅ Queued Variation {i+1} - Execution ID: {execution_id}")
            
            storage.log_execution(
                execution_id=execution_id,
                prompt=prompt_content,
                image_ref_path=dest_image_path,
                persona=persona
            )
            successful_queues_for_image += 1
            execution_ids.append(execution_id)
        else:
            logger.error(f"Failed to get execution ID for variation {i+1}.")
            
    task.update_state(state='SUCCESS', meta={'status': f"✅ Finished processing {dest_image_path}", 'progress': 100})
    
    return {
        "success": True,
        "image_path": dest_image_path,
        "queued_variations": successful_queues_for_image,
        "total_variations": len(prompts),
        "execution_ids": execution_ids
    }
