- AI Smart Emotion Interviewer

An intelligent AI-based interview simulation system that analyzes both what a candidate says and how they feel, combining AI-generated questions, real-time facial emotion detection, and voice analysis to give data-driven interview feedback.


- Problem It Solves
Traditional mock interviews rely on subjective, manual feedback and ignore non-verbal cues like micro-expressions, stress, and speech clarity, even though most candidates fail interviews due to poor confidence and communication, not lack of skill.


Features
  
- AI-Generated Questions — dynamic, role-specific question bank via Gemini/GPT API
- Facial Emotion Tracking — real-time emotion detection using OpenCV & DeepFace
- Voice Analysis — speech-to-text transcription with tempo & clarity scoring
- Automated PDF Reports — detailed performance summaries with behavioral insights
- User Dashboard — profile management, interview history, video playback, PDF archive
- Admin Dashboard — candidate overview, question bank management, candidate comparison tool


Tech Stack
- Python
- Streamlit
- Streamlit-Authenticator
- Firebase
- Gemini/GPT API
- OpenCV
- DeepFace/FER
- SpeechRecognition
- PyTTSx3
- FPDF/ReportLab


How It Works
- Auth — User/Admin logs in securely
- Questions: AI generates contextual questions based on job role & experience
- Interview: Live video interface captures responses; AI asks questions audibly
- Detection: Facial expressions scanned in real-time for confidence/stress
- Analysis: Speech transcript reviewed for accuracy; emotion logs analyzed
- Report: Final PDF generated with scores and behavioral insights


Project Structure
- app.py               # Main entry point — Streamlit app
- requirements.txt      # Python dependencies
- .gitignore            # Files/folders excluded from Git

- assets/               # Static assets (images, icons, etc.)
- dashboard/            # User & Admin dashboard pages/components
- interview/            # Interview session logic (questions, video, emotion/voice analysis)
- models/               # ML/AI model files or model-handling logic
- reports/              # PDF report generation logic & saved reports
- utils/                # Helper/utility functions


- License
All Rights Reserved © 2026. This code may not be copied, modified, or distributed without explicit permission.
