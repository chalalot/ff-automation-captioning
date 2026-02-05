from moviepy import VideoFileClip, concatenate_videoclips
import moviepy.video.fx as vfx
import os
from proglog import ProgressBarLogger

class StreamlitLogger(ProgressBarLogger):
    def __init__(self, callback):
        super().__init__()
        self.progress_handler = callback

    def bars_callback(self, bar, attr, value, old_value=None):
        if self.progress_handler and bar in self.bars and 'total' in self.bars[bar]:
            total = self.bars[bar]['total']
            if total > 0:
                progress = value / total
                # Ensure progress is between 0 and 1
                progress = max(0.0, min(1.0, progress))
                self.progress_handler(progress)

def merge_videos(video_paths, output_path, transition_type="Crossfade", duration=0.5, progress_callback=None):
    print(f"Loading videos: {video_paths}")
    clips = []
    try:
        # Load clips
        for path in video_paths:
            clips.append(VideoFileClip(path))
        
        if not clips:
            print("No clips to merge.")
            return

        final_video = None
        
        if transition_type == "Crossfade" and len(clips) > 1:
            # Apply crossfade to clips (except the first one)
            processed_clips = [clips[0]]
            for i in range(1, len(clips)):
                print(f"Applying CrossFadeIn to clip {i}")
                clip = clips[i].with_effects([vfx.CrossFadeIn(duration)])
                processed_clips.append(clip)
                
            print("Concatenating videos with crossfade...")
            final_video = concatenate_videoclips(processed_clips, method="compose", padding=-duration)
            
        elif transition_type == "Fade to Black":
            # Fade Out -> Fade In
            processed_clips = []
            for i, clip in enumerate(clips):
                effects = []
                if i > 0:
                    effects.append(vfx.FadeIn(duration))
                if i < len(clips) - 1:
                    effects.append(vfx.FadeOut(duration))
                
                if effects:
                    print(f"Applying Fade Effects to clip {i}")
                    processed_clips.append(clip.with_effects(effects))
                else:
                    processed_clips.append(clip)
            
            print("Concatenating videos with fade-to-black...")
            final_video = concatenate_videoclips(processed_clips, method="compose") # Sequential
            
        else: # Simple Cut or Default
            print("Concatenating videos (Simple Cut)...")
            final_video = concatenate_videoclips(clips, method="compose")

        print(f"Writing output to {output_path}")
        
        logger = "bar" # Default
        if progress_callback:
            logger = StreamlitLogger(progress_callback)
            
        final_video.write_videofile(output_path, codec="libx264", audio_codec="aac", logger=logger)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        raise e
            
    finally:
        # Close clips to release resources
        for clip in clips:
            try:
                clip.close()
            except:
                pass
