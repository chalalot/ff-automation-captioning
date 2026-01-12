from moviepy import VideoFileClip, concatenate_videoclips
import moviepy.video.fx as vfx
import os

def merge_videos(video_paths, output_path):
    print(f"Loading videos: {video_paths}")
    clips = []
    try:
        # Load clips
        for path in video_paths:
            clips.append(VideoFileClip(path))
        
        # Apply crossfade to clips (except the first one)
        # We need to add CrossFadeIn to the 2nd and subsequent clips
        processed_clips = [clips[0]]
        fade_duration = 0.5
        
        for i in range(1, len(clips)):
            # Apply CrossFadeIn
            print(f"Applying CrossFadeIn to clip {i}")
            # Use vfx.CrossFadeIn class/function
            clip = clips[i].with_effects([vfx.CrossFadeIn(fade_duration)])
            processed_clips.append(clip)
            
        print("Concatenating videos with crossfade...")
        # padding=-fade_duration makes them overlap
        final_video = concatenate_videoclips(processed_clips, method="compose", padding=-fade_duration)
        
        print(f"Writing output to {output_path}")
        final_video.write_videofile(output_path, codec="libx264", audio_codec="aac")
        
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

if __name__ == "__main__":
    video_dir = "video-raw"
    files = [
        "kling_20260105_Image_to_Video_A_cozy__we_4370_0.mp4",
        "kling_20260105_Image_to_Video_A_cozy__we_4381_0.mp4",
        "kling_20260105_Image_to_Video_In_a_cozy__4382_0.mp4"
    ]
    
    input_paths = [os.path.join(video_dir, f) for f in files]
    
    # Ensure output directory exists
    os.makedirs("results", exist_ok=True)
    output_path = os.path.join("results", "merged_video_test.mp4")
    
    merge_videos(input_paths, output_path)
