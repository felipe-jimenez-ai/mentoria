# **🧙‍♂️ MentorIA [(Webapp)](https://mentoria-edu.streamlit.app/) | [(Video Demo)](https://www.youtube.com/watch?v=TUeoTym4jAM)**
_Accelerate your learning efficiency!_
_Mentoria is just getting started — powerful tools are on the way. Stay tuned!_
V1.0.0

https://github.com/user-attachments/assets/14694b99-7fe9-44ef-a1bf-9cd89a7a8d77

## YouTube Study Assistant

A tool that helps you extract YouTube video transcripts and generate study materials like summaries, key points, and practice questions using AI.

## Features

- Extract transcripts from any YouTube video
- Generate AI-powered study materials:
  - Concise summaries
  - Key points
  - Practice questions and answers
- Simple web interface
- Download generated materials as text files

## Setup

1. Clone this repository
2. Install the required packages:
   ```
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the project root and add your Groq API key:
   ```
   GROQ_API_KEY=your_groq_api_key_here
   ```
   
   You can get a free API key by signing up at [Groq Cloud](https://console.groq.com/keys)
4. Run the application:
   ```
   streamlit run app.py
   ```
5. Open your browser and navigate to `http://localhost:8501`

## How to Use

1. Paste a YouTube video URL in the input field
2. Click "Get Transcript" to fetch the video transcript
3. Choose the type of study material you want to generate
4. Click the generate button to create your study materials
5. Download the generated content as a text file if desired

## Requirements

- Python 3.7+
- Groq API key (for generating study materials)
- Internet connection (for fetching YouTube transcripts)

## Note

This tool is for educational purposes only. Please respect YouTube's terms of service and copyright laws when using this tool.
