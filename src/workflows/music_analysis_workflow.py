import os
from crewai import Agent, Task, Crew, Process
from src.tools.audio_tool import AudioTool

class MusicAnalysisWorkflow:
    def __init__(self, verbose=True):
        self.verbose = verbose
        self.audio_tool = AudioTool()

    def process(self, audio_path: str):
        """
        Run the music analysis workflow on the given audio file.
        Returns a dictionary with 'vibe' and 'lyrics'.
        """
        
        # --- Agents ---
        vibe_analyst = Agent(
            role='Music Vibe Analyst',
            goal='Analyze the audio to extract detailed vibe, mood, genre, and instrumentation.',
            backstory=(
                "You are an expert musicologist with decades of experience in analyzing "
                "musical compositions. You can identify genres, moods, instruments, and "
                "stylistic nuances just by listening."
            ),
            tools=[self.audio_tool],
            verbose=self.verbose,
            allow_delegation=False
        )

        lyrics_transcriber = Agent(
            role='Lyrics Transcriber',
            goal='Extract the full and accurate lyrics from the song.',
            backstory=(
                "You are a professional transcriber with perfect pitch and hearing. "
                "You specialize in extracting lyrics from songs, even in difficult audio conditions. "
                "You pay attention to every word and line."
            ),
            tools=[self.audio_tool],
            verbose=self.verbose,
            allow_delegation=False
        )

        # --- Tasks ---
        vibe_task = Task(
            description=(
                f"Analyze the audio file located at `{audio_path}` using the Audio Analysis Tool. "
                "Provide a detailed description of the song's vibe, mood, genre, style, tempo, and instrumentation. "
                "Focus on the emotional and sonic characteristics."
            ),
            expected_output="A detailed paragraph describing the vibe, mood, genre, and instrumentation of the song.",
            agent=vibe_analyst
        )

        lyrics_task = Task(
            description=(
                f"Analyze the audio file located at `{audio_path}` using the Audio Analysis Tool. "
                "Transcribe the FULL lyrics of the song. "
                "Format the lyrics clearly with line breaks. "
                "If the song is instrumental, clearly state that there are no lyrics."
            ),
            expected_output="The full lyrics of the song, formatted clearly.",
            agent=lyrics_transcriber
        )

        # --- Crew ---
        crew = Crew(
            agents=[vibe_analyst, lyrics_transcriber],
            tasks=[vibe_task, lyrics_task],
            process=Process.sequential,
            verbose=self.verbose
        )

        result = crew.kickoff()
        
        # CrewAI returns the final task output by default in `result`.
        # To get individual task outputs, we need to access task.output
        
        return {
            "vibe": vibe_task.output.raw if vibe_task.output else "No vibe analysis available.",
            "lyrics": lyrics_task.output.raw if lyrics_task.output else "No lyrics available.",
            "full_result": result
        }
