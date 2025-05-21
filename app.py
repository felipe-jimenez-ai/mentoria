import os
import re
from functools import lru_cache
from typing import Optional

import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled, VideoUnavailable
from groq import Groq, GroqError
from dotenv import load_dotenv

def is_valid_youtube_url(url: str) -> bool:
    """Check if the URL is a valid YouTube URL"""
    youtube_patterns = [
        r'^https?://(www\.)?youtube\.com/watch\?v=([^&]+)',
        r'^https?://youtu\.be/([^?]+)',
        r'^https?://(www\.)?youtube\.com/shorts/([^?]+)',
    ]
    return any(re.match(pattern, url) for pattern in youtube_patterns)

def extract_video_id(url: str) -> Optional[str]:
    """Extract video ID from YouTube URL"""
    try:
        if not url or not isinstance(url, str):
            return None
            
        url = url.strip()
        
        # Handle youtu.be links
        if 'youtu.be' in url:
            return url.split('/')[-1].split('?')[0]
            
        # Handle youtube.com links
        if 'youtube.com' in url:
            # Handle different YouTube URL formats
            if 'v=' in url:
                return url.split('v=')[1].split('&')[0]
            elif '/live/' in url:  # For live streams
                return url.split('/live/')[-1].split('?')[0]
                
        return None
    except Exception:
        return None

@lru_cache(maxsize=32)
def get_transcript(video_id: str, language: str = 'es') -> str:
    """
    Fetch and cache transcript for a given YouTube video ID in the specified language.
    
    Args:
        video_id: YouTube video ID
        language: Desired language code (default: 'es' for Spanish)
        
    Returns:
        str: The transcript text or an error message
    """
    if not video_id:
        return "Error: No video ID provided"
    
    # Debug: Print which video we're trying to fetch
    st.sidebar.info(f"Fetching transcript for video ID: {video_id}")
    
    # Try different methods to get the transcript
    methods = [
        ("Direct API", _get_transcript_direct),
        ("With Retry", _get_transcript_with_retry),
    ]
    
    last_error = None
    for method_name, method in methods:
        try:
            st.sidebar.info(f"Trying method: {method_name}")
            result = method(video_id, language)
            if result and not result.startswith("Error:"):
                st.sidebar.success(f"Success with method: {method_name}")
                return result
            last_error = result  # Store the error message
        except Exception as e:
            st.sidebar.error(f"Method {method_name} failed: {str(e)}")
            last_error = str(e)
            continue
    
    error_msg = f"Error: Could not retrieve transcript after multiple attempts. Last error: {last_error}"
    st.sidebar.error(error_msg)
    return error_msg

def _get_transcript_direct(video_id: str, language: str) -> str:
    """Try to get transcript using YouTubeTranscriptApi directly"""
    try:
        st.sidebar.info("Attempting to list available transcripts...")
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        except Exception as e:
            return f"Error listing transcripts: {str(e)}"
        
        st.sidebar.info(f"Available languages: {[t.language_code for t in transcript_list]}")
        
        # Try to get transcript in the specified language
        try:
            st.sidebar.info(f"Looking for transcript in language: {language}")
            transcript = transcript_list.find_transcript([language])
            st.sidebar.info(f"Found transcript in language: {transcript.language_code}")
        except NoTranscriptFound:
            st.sidebar.warning(f"No transcript found in {language}, trying English...")
            try:
                # If specified language not found, try to get any available transcript and translate
                transcript = transcript_list.find_transcript(['en'])  # Try English as fallback
                st.sidebar.info("Found English transcript, translating...")
                transcript = transcript.translate(language).fetch()
            except Exception as e:
                st.sidebar.warning(f"No English transcript found, trying first available: {str(e)}")
                # If no English, get the first available transcript
                try:
                    transcript = next(iter(transcript_list), None)
                    if transcript:
                        st.sidebar.info(f"Translating from {transcript.language_code} to {language}")
                        transcript = transcript.translate(language).fetch()
                    else:
                        return "Error: No transcript available for this video"
                except Exception as trans_e:
                    return f"Error in translation: {str(trans_e)}"
        
        # If we have a transcript object, fetch its contents
        if hasattr(transcript, 'fetch'):
            try:
                transcript = transcript.fetch()
            except Exception as e:
                return f"Error fetching transcript: {str(e)}"
            
        if not transcript:
            return "Error: No transcript content available"
            
        # Join all text entries with spaces
        return " ".join(entry['text'] for entry in transcript)
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        st.sidebar.error(f"Unexpected error in _get_transcript_direct: {error_details}")
        return f"Unexpected error: {str(e)}"
        
    except VideoUnavailable:
        return "Error: This video is not available or is private"
    except TranscriptsDisabled:
        return "Error: Transcripts are disabled for this video"
    except NoTranscriptFound:
        return "Error: No transcript available for this video"
    except Exception as e:
        raise Exception(f"Direct method failed: {str(e)}")

def _get_transcript_with_retry(video_id: str, language: str, max_retries: int = 3) -> str:
    """Try to get transcript with retries and different approaches"""
    import time
    from pytube import YouTube
    
    for attempt in range(max_retries):
        try:
            # Try direct method first
            if attempt == 0:
                return _get_transcript_direct(video_id, language)
                
            # Try with pytube as fallback
            yt = YouTube(f"https://www.youtube.com/watch?v={video_id}")
            captions = yt.captions
            
            # Try to get the caption in the requested language
            caption = captions.get_by_language_code(language[:2])  # Try first 2 chars of language code
            
            # If not found, try English
            if not caption and language != 'en':
                caption = captions.get_by_language_code('en')
                
            if caption:
                return caption.generate_srt_captions()
                
            # If no captions found, try to get the first available caption
            if captions:
                return next(iter(captions)).generate_srt_captions()
                
        except Exception as e:
            if attempt == max_retries - 1:  # Last attempt
                raise Exception(f"All retry attempts failed: {str(e)}")
            time.sleep(1)  # Wait before retrying
            continue
    
    return "Error: Could not retrieve transcript with any method"

def clean_latex(text):
    """Remove LaTeX formatting from text"""
    # Remove LaTeX math mode delimiters
    text = text.replace('$', '').replace('\\', '')
    # Remove common LaTeX commands
    latex_commands = [
        '\n', '\t', '\r', '\f', '\v',
        '\textbf', '\textit', '\emph', '\text',
        '\begin', '\end', '\[', '\]', '\left', '\right'
    ]
    for cmd in latex_commands:
        text = text.replace(cmd, '')
    return text

def format_qa(text, language='en'):
    """Format Q&A text with better readability
    
    Args:
        text (str): The text to format
        language (str): 'en' for English, 'es' for Spanish
    """
    if not text or not isinstance(text, str):
        return "No questions and answers available."
    
    # Clean up the text first - normalize spaces but preserve structure
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Remove any leading/trailing ** or other markdown artifacts
    text = re.sub(r'^[\*\s]+', '', text)
    text = re.sub(r'[\*\s]+$', '', text)
    
    # Handle the specific Spanish format with "Pregunta X: ... Respuesta: ..."
    if language == 'es' and ("Pregunta" in text or "pregunta" in text):
        return format_spanish_qa(text)
    
    # Handle the specific format with Q1: Question X: ... A: Answer: ...
    if language == 'en' and re.search(r'Q\d+:', text) and 'Question \d+:' in text and 'A: Answer:' in text:
        # Extract all Q&A pairs
        qa_pairs = re.findall(r'(Q\d+:.*?)(?=Q\d+:|$)', text, re.DOTALL)
        formatted = []
        
        for i, qa in enumerate(qa_pairs, 1):
            # Clean up the question and answer
            qa = re.sub(r'Question \d+:', '', qa)  # Remove duplicate question number
            if 'A: Answer:' in qa:
                q, a = qa.split('A: Answer:', 1)
                q = q.replace('Q\d+:', '').strip()
                q = re.sub(r'^[:\.\s]+', '', q).strip()
                if not q.endswith('?'):
                    q = q.rstrip('.:') + '?'
                a = a.strip()
                formatted.append(f"**Q{i}:** {q}\n**A:** {a}\n")
        
        if formatted:
            return '\n'.join(formatted)
    
    # Handle the specific format with numbered questions in English
    if language == 'en':
        # Check for patterns like "Q1:", "Question 1:", or numbered lists
        if (re.search(r'(Q\d*:|Question \d+:|\d+\.)', text, re.IGNORECASE)):
            return format_numbered_qa(text, language)
        
        # Handle the case where the model returns a list of questions and answers
        # with "Question X:" and "Answer:" patterns
        if "Question" in text and "Answer:" in text:
            return format_numbered_qa(text, language)
        
        # Handle the case where the model returns a simple Q&A format
        if "Q:" in text and "A:" in text:
            return format_numbered_qa(text, language)
    
    # If we get here and it's English but no specific format was detected,
    # try to format it as a numbered Q&A anyway
    if language == 'en':
        return format_numbered_qa(text, language)
    
    # Default case for other languages or formats
    return text
    
    # Handle the case where we have Q: and A: patterns
    if re.search(r'Q\s*\d*\s*:', text, re.IGNORECASE) and re.search(r'A\s*\d*\s*:', text, re.IGNORECASE):
        return format_numbered_qa(text, language)
    
    # Try to handle as a simple Q&A format
    formatted = []
    
    # Try to split by question patterns (Q1, Q2, etc.)
    q_pattern = r'(Q\d*\s*:)' if language == 'en' else r'(Pregunta \d+\s*:)'
    parts = re.split(q_pattern, text, flags=re.IGNORECASE)
    
    if len(parts) > 1:  # If we found question patterns
        # The first part is typically an intro, add it as is if not empty
        if parts[0].strip():
            formatted.append(parts[0].strip() + '\n')
            
        # Process Q&A pairs
        for i in range(1, len(parts), 2):
            if i + 1 >= len(parts):
                break
                
            q_num = parts[i].strip().rstrip(':')
            content = parts[i+1].strip()
            
            # Split into question and answer
            answer_indicators = ['A:'] if language == 'en' else ['A:', 'Respuesta:']
            answer_found = False
            
            for indicator in answer_indicators:
                if indicator in content:
                    q_part, a_part = content.split(indicator, 1)
                    question = q_part.strip()
                    answer = a_part.strip()
                    
                    # Clean up the question
                    if not question.endswith('?'):
                        # Find the last period that's likely the end of the question
                        last_period = question.rfind('.')
                        if last_period > 0 and len(question) - last_period < 50:  # Heuristic
                            question = question[:last_period] + '?' + question[last_period+1:]
                        else:
                            question = question.rstrip('.:') + '?'
                    
                    # Clean up the answer
                    answer = re.sub(r'\s+', ' ', answer)  # Normalize spaces
                    # Remove any remaining Q: or A: at start of answer
                    answer = re.sub(r'^[QA]\d*\s*:?\s*', '', answer, flags=re.IGNORECASE).strip()
                    # Remove any markdown bold/asterisks
                    answer = re.sub(r'\*+', '', answer).strip()
                    
                    # Format with consistent numbering
                    q_num_clean = re.sub(r'[^\d]', '', q_num) or str(len(formatted) + 1)
                    formatted.append(f"**Q{q_num_clean}:** {question}\n**A:** {answer}\n")
                    answer_found = True
                    break
            
            # If no answer indicator found, try to split by question mark
            if not answer_found and '?' in content:
                q_part, a_part = content.split('?', 1)
                question = q_part.strip() + '?'
                answer = a_part.strip()
                # Clean up the answer
                answer = re.sub(r'^[QA]\d*\s*:?\s*', '', answer, flags=re.IGNORECASE).strip()
                answer = re.sub(r'\*+', '', answer).strip()
                q_num_clean = re.sub(r'[^\d]', '', q_num) or str(len(formatted) + 1)
                formatted.append(f"**Q{q_num_clean}:** {question}\n**A:** {answer}\n")
            elif not answer_found and content.strip():
                # If we can't find a question mark or answer, just add as is
                q_num_clean = re.sub(r'[^\d]', '', q_num) or str(len(formatted) + 1)
                formatted.append(f"**Q{q_num_clean}:** {content.strip()}\n")
    
    if not formatted:
        return "No se pudieron generar preguntas y respuestas a partir del contenido." if language == 'es' else "No questions and answers could be generated from the content."
    
    if not formatted:
        return "No questions and answers could be generated from the content."
        
    return '\n'.join(formatted)

def format_spanish_qa(text):
    """Format Spanish Q&A text in the specific format:
    "Pregunta X: [question]? Respuesta: [answer] Pregunta Y: ..."
    """
    # Split by 'Pregunta X:' pattern
    parts = re.split(r'(Pregunta \d+:)', text)
    formatted = []
    
    # The first part is usually an intro or empty
    if parts and parts[0].strip():
        formatted.append(parts[0].strip() + '\n')
    
    # Process Q&A pairs
    for i in range(1, len(parts), 2):
        if i + 1 >= len(parts):
            break
            
        q_num = parts[i].strip()
        content = parts[i+1].strip()
        
        # Look for answer indicators
        answer_indicators = ['Respuesta:', 'A:']
        answer_found = False
        
        for indicator in answer_indicators:
            if indicator in content:
                q_part, a_part = content.split(indicator, 1)
                question = q_part.strip()
                answer = a_part.strip()
                
                # Handle case where question mark might be missing
                if '?' not in question:
                    # Find the last period that's likely the end of the question
                    last_period = question.rfind('.')
                    if last_period > 0 and len(question) - last_period < 50:  # Heuristic
                        question = question[:last_period] + '?' + question[last_period+1:]
                    else:
                        question = question.rstrip('.:') + '?'
                
                # Clean up the answer
                answer = re.sub(r'\s+', ' ', answer)  # Normalize spaces
                # Remove any remaining Pregunta at the start of answer
                answer = re.sub(r'^Pregunta \d+:', '', answer).strip()
                
                formatted.append(f"**{q_num}**\n**Q:** {question}\n**A:** {answer}\n")
                answer_found = True
                break
        
        # If no answer indicator found, try to split by question mark
        if not answer_found and '?' in content:
            q_part, a_part = content.split('?', 1)
            question = q_part.strip() + '?'
            answer = a_part.strip()
            # Remove any remaining Pregunta at the start of answer
            answer = re.sub(r'^Pregunta \d+:', '', answer).strip()
            formatted.append(f"**{q_num}**\n**Q:** {question}\n**A:** {answer}\n")
        elif not answer_found:
            # If we can't find a question mark or answer, just add as is
            formatted.append(f"**{q_num}** {content}\n")
    
    return '\n'.join(formatted)

def format_numbered_qa(text, language='en'):
    """Format numbered Q&A text with consistent formatting
    
    Args:
        text (str): The text to format
        language (str): 'en' for English, 'es' for Spanish
    """
    import re
    
    # Clean up the text first
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Remove any leading/trailing ** or other markdown artifacts
    text = re.sub(r'^[\*\s]+', '', text)
    text = re.sub(r'[\*\s]+$', '', text)
    
    # Handle Spanish Q&A format
    if language == 'es':
        return format_spanish_qa(text)
    
    # Initialize formatted output list
    formatted = []
    
    # First, handle the specific format from the example
    if 'Here are the' in text and 'most important combined questions and answers' in text:
        # Extract the main content after the introduction
        content = re.sub(r'^.*?Here are the \d+ most important combined questions and answers.*?:', '', text, flags=re.IGNORECASE)
        
        # Split by question markers (Question X: or QX:)
        questions = re.split(r'(?:Question \d+:|Q\d+:)\s*', content, flags=re.IGNORECASE)
        
        # The first part is usually empty or an intro, skip it
        for i, question_text in enumerate(questions[1:], 1):
            # Split into question and answer parts
            if 'Answer:' in question_text:
                q_part, a_part = question_text.split('Answer:', 1)
                question = q_part.strip()
                answer = a_part.strip()
                
                # Clean up question
                question = re.sub(r'^[\d\.\s]+', '', question).strip()
                if not question.endswith('?'):
                    question = question.rstrip('.:') + '?'
                
                # Clean up answer
                answer = re.sub(r'^[\d\.\s]+', '', answer).strip()
                answer = re.sub(r'\s+', ' ', answer)
                
                formatted.append(f"**Q{i}:** {question}\n**A:** {answer}\n")
        
        if formatted:
            return '\n'.join(formatted)
    
    # If the specific format wasn't found, try the general patterns
    qa_pairs = re.findall(r'(?:Q\s*\d*\s*:|Question\s+\d+\s*:)(.*?)(?=Q\s*\d*\s*:|Question\s+\d+\s*:|A\s*\d*\s*:|Answer\s+\d+\s*:|$)', 
                        text, flags=re.IGNORECASE | re.DOTALL)
    
    # If we found Q: patterns, try to match them with A: patterns
    if qa_pairs:
        # Find all answers (A: patterns)
        a_parts = re.findall(r'(?:A\s*\d*\s*:|Answer\s+\d+\s*:)(.*?)(?=Q\s*\d*\s*:|Question\s+\d+\s*:|A\s*\d*\s*:|Answer\s+\d+\s*:|$)', 
                          text, flags=re.IGNORECASE | re.DOTALL)
        
        # If we have matching numbers of Qs and As, pair them up
        if qa_pairs and a_parts and len(qa_pairs) == len(a_parts):
            for i, (q, a) in enumerate(zip(qa_pairs, a_parts), 1):
                question = q.strip()
                answer = a.strip()
                
                # Clean up the question
                if not question.endswith('?'):
                    question = question.rstrip('.:') + '?'
                
                # Clean up the answer
                answer = re.sub(r'\s+', ' ', answer).strip()
                answer = re.sub(r'^[QA]\d*\s*:?\s*', '', answer, flags=re.IGNORECASE).strip()
                answer = re.sub(r'\*+', '', answer).strip()
                
                formatted.append(f"**Q{i}:** {question}\n**A:** {answer}\n")
    
    # If we didn't find explicit Q: A: pairs, try to split by numbered items
    if not formatted:
        # Look for patterns like "1. Question? Answer"
        items = re.split(r'(\d+\.\s*)', text)
        if len(items) > 1:
            for i in range(1, len(items), 2):
                if i + 1 < len(items):
                    content = items[i] + items[i+1]
                else:
                    content = items[i]
                
                # Try to split into question and answer
                if '?' in content:
                    q_part, a_part = content.split('?', 1)
                    question = q_part.strip() + '?'
                    answer = a_part.strip()
                    
                    # Clean up the answer
                    answer = re.sub(r'^[\*\s]+', '', answer)
                    answer = re.sub(r'\s+', ' ', answer).strip()
                    
                    formatted.append(f"**Q{len(formatted) + 1}:** {question}\n**A:** {answer}\n")
    
    # If we still don't have any formatted content, try to split by double newlines
    if not formatted:
        blocks = [b.strip() for b in text.split('\n\n') if b.strip()]
        for i, block in enumerate(blocks, 1):
            if '?' in block:
                q_part, a_part = block.split('?', 1)
                question = q_part.strip() + '?'
                answer = a_part.strip()
                formatted.append(f"**Q{i}:** {question}\n**A:** {answer}\n")
    
    # If we still don't have any formatted content, return the original text with minimal formatting
    if not formatted:
        # Try to add some basic formatting to the original text
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        for i, line in enumerate(lines, 1):
            if '?' in line:
                q_part, a_part = line.split('?', 1)
                question = q_part.strip() + '?'
                answer = a_part.strip()
                formatted.append(f"**Q{i}:** {question}\n**A:** {answer}\n")
            else:
                formatted.append(f"{line}\n")
    
    return '\n'.join(formatted)

def format_bullet_points(text, language='en'):
    """Format text with bullet points or Q&A with proper spacing and line breaks
    
    Args:
        text (str): The text to format
        language (str): 'en' for English, 'es' for Spanish
    """
    # Check if this is a Q&A format
    if '?' in text and (
        ('Answer:' in text or 'Respuesta:' in text or 
         'A:' in text or 'R:' in text or
         'Q:' in text or 'Pregunta:' in text)
    ):
        return format_qa(text, language)
    
    # Otherwise, format as bullet points
    lines = text.split('\n')
    formatted_lines = []
    
    bullet_char = '•'  # Default bullet point
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check for different bullet point formats
        if re.match(r'^\d+[\.\)]', line):  # Numbered lists: 1., 2), etc.
            formatted_lines.append(f"{bullet_char} {line}")
        elif re.match(r'^[•*-]', line):  # Already has a bullet point
            formatted_lines.append(f"{bullet_char} {line[1:].strip()}")
        else:
            formatted_lines.append(f"{bullet_char} {line}")
    
    return '\n'.join(formatted_lines)

def detect_language(text):
    """Detect the language of the text (simplified version)"""
    # Check for common Spanish words
    spanish_words = ['el', 'la', 'los', 'las', 'de', 'que', 'y', 'en', 'a', 'es']
    word_count = sum(1 for word in text.lower().split() if word in spanish_words)
    
    # If we find several Spanish words, assume it's Spanish
    if word_count > len(text.split()) * 0.1:  # At least 10% Spanish words
        return 'es'
    return 'en'  # Default to English

def get_language_instructions(lang):
    """Get instructions in the target language with emojis and formatting"""
    instructions = {
        'es': {
            'summary': (
                'Proporciona un resumen claro y bien estructurado de la siguiente transcripción.\n\n'
                'INSTRUCCIONES DE FORMATO:\n'
                '1. Comienza con un párrafo introductorio que resuma el tema principal.\n'
                '2. Usa párrafos cortos de 2-3 oraciones cada uno.\n'
                '3. Separa cada párrafo con una línea en blanco.\n'
                '4. No uses viñetas ni listas numeradas.\n'
                '5. Asegúrate de que cada idea principal tenga su propio párrafo.\n'
                '6. Usa oraciones completas y puntuación adecuada.\n\n'
                'Ejemplo de formato deseado:\n\n'
                'Este es el primer párrafo que introduce el tema principal. Debe ser conciso pero informativo.\n\n'
                'Este es el segundo párrafo que desarrolla una idea específica. Nota cómo hay una línea en blanco antes y después.\n\n'
                'Este es el tercer párrafo que continúa con la explicación. Cada párrafo debe fluir naturalmente con el siguiente.'
            ),
            'questions': (
                'Genera 5 preguntas importantes y sus respuestas basadas en esta transcripción.\n'
                'IMPORTANTE: Sigue EXACTAMENTE este formato, incluyendo los números de línea y saltos de línea:\n\n'
                'Pregunta 1: [Escribe aquí la primera pregunta terminando con signo de interrogación]\n'
                'Respuesta: [Escribe aquí la respuesta a la primera pregunta]\n\n'
                'Pregunta 2: [Escribe aquí la segunda pregunta terminando con signo de interrogación]\n'
                'Respuesta: [Escribe aquí la respuesta a la segunda pregunta]\n\n'
                'Pregunta 3: [Escribe aquí la tercera pregunta terminando con signo de interrogación]\n'
                'Respuesta: [Escribe aquí la respuesta a la tercera pregunta]\n\n'
                'Pregunta 4: [Escribe aquí la cuarta pregunta terminando con signo de interrogación]\n'
                'Respuesta: [Escribe aquí la respuesta a la cuarta pregunta]\n\n'
                'Pregunta 5: [Escribe aquí la quinta pregunta terminando con signo de interrogación]\n'
                'Respuesta: [Escribe aquí la respuesta a la quinta pregunta]\n\n'
                'REGLAS ESTRICTAS:\n'
                '1. Usa EXACTAMENTE el formato mostrado arriba\n'
                '2. No incluyas ningún otro texto fuera de este formato\n'
                '3. Asegúrate de que cada pregunta termine con "?"\n'
                '4. No incluyas prefijos como "1." o "a)" en las respuestas\n'
                '5. Mantén cada pregunta y respuesta en una sola línea\n'
                '6. Incluye exactamente una línea en blanco entre cada par pregunta-respuesta'
            ),
            'key_points': (
                'Extrae los 5 puntos clave más importantes de esta transcripción.\n'
                'Formato requerido (usa exactamente este formato):\n\n'
                '• [Primer punto clave. Escribe una oración completa que resuma este punto.]\n\n'
                '• [Segundo punto clave. Sé claro y conciso, pero asegúrate de que sea una oración completa.]\n\n'
                '• [Y así sucesivamente para los 5 puntos.]\n\n'
                'Asegúrate de que cada punto esté en su propia línea, comience con un guion (•) y tenga un espacio después.\n'
                'Incluye una línea en blanco entre cada punto para mejor legibilidad.'
            )
        },
        'en': {
            'summary': (
                'Please provide a clear and well-structured summary of the following transcript.\n\n'
                'FORMATTING INSTRUCTIONS:\n'
                '1. Begin with an introductory paragraph summarizing the main topic.\n'
                '2. Use short paragraphs of 2-3 sentences each.\n'
                '3. Separate each paragraph with a blank line.\n'
                '4. Do not use bullet points or numbered lists.\n'
                '5. Ensure each main idea has its own paragraph.\n'
                '6. Use complete sentences and proper punctuation.\n\n'
                'Example of desired format:\n\n'
                'This is the first paragraph introducing the main topic. It should be concise yet informative.\n\n'
                'This is the second paragraph developing a specific point. Note the blank lines before and after.\n\n'
                'This is the third paragraph continuing the explanation. Each paragraph should flow naturally to the next.'
            ),
            'questions': (
                'Generate 5 important questions and answers based on this transcript.\n'
                'IMPORTANT: Follow EXACTLY this format, including line numbers and line breaks:\n\n'
                'Question 1: [Type your first question ending with a question mark]\n'
                'Answer: [Type the answer to the first question]\n\n'
                'Question 2: [Type your second question ending with a question mark]\n'
                'Answer: [Type the answer to the second question]\n\n'
                'Question 3: [Type your third question ending with a question mark]\n'
                'Answer: [Type the answer to the third question]\n\n'
                'Question 4: [Type your fourth question ending with a question mark]\n'
                'Answer: [Type the answer to the fourth question]\n\n'
                'Question 5: [Type your fifth question ending with a question mark]\n'
                'Answer: [Type the answer to the fifth question]\n\n'
                'STRICT RULES:\n'
                '1. Use EXACTLY the format shown above\n'
                '2. Do not include any other text outside this format\n'
                '3. Make sure each question ends with "?"\n'
                '4. Do not include prefixes like "1." or "a)" in the answers\n'
                '5. Keep each question and answer on a single line\n'
                '6. Include exactly one blank line between each Q&A pair'
            ),
            'key_points': (
                'Extract the 5 most important key points from this transcript.\n'
                'Required format (use exactly this format):\n\n'
                '• [First key point. Write a complete sentence that summarizes this point.]\n\n'
                '• [Second key point. Be clear and concise, but make sure it is a complete sentence.]\n\n'
                '• [And so on for all 5 points.]\n\n'
                'Make sure each point is on its own line, starts with a bullet (•) and has a space after it.\n'
                'Include a blank line between each point for better readability.'
            )
        }
    }
    return instructions.get(lang, instructions['en'])  # Default to English if language not found

def split_into_chunks(text, max_chars=4000):
    """Split text into chunks of maximum size, trying to break at sentence boundaries"""
    if len(text) <= max_chars:
        return [text]
    
    # Try to split at sentence boundaries
    mid = len(text) // 2
    for punct in ['. ', '! ', '? ', '\n', ' ', '']:
        pos = text.rfind(punct, 0, mid) + len(punct) if punct else mid
        if pos > max_chars // 4:  # Ensure we don't create a very small chunk
            break
    else:
        pos = mid  # Fallback to middle if no good split point found
    
    # Recursively split both halves
    return split_into_chunks(text[:pos].strip(), max_chars) + \
           split_into_chunks(text[pos:].strip(), max_chars)

def process_chunk(client, chunk, material_type, lang):
    """Process a single chunk of text"""
    instructions = get_language_instructions(lang)
    
    # System message in the detected language
    system_message = {
        'es': 'Eres un asistente de estudio útil. Responde siempre en el mismo idioma que la transcripción.',
        'en': 'You are a helpful study assistant. Always respond in the same language as the transcript.'
    }.get(lang, 'You are a helpful study assistant.')
    
    prompt = f"{instructions[material_type]}\n\nTranscript Chunk:\n{chunk}"
    
    response = client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=2000
    )
    
    return clean_latex(response.choices[0].message.content)

def combine_results(results, material_type, lang):
    """Combine results from multiple chunks"""
    if len(results) == 1:
        return results[0]
    
    # If we have multiple chunks, combine them
    combined = "\n\n".join(results)
    
    # Get instructions for combining results
    combine_instructions = {
        'es': {
            'summary': 'Combina los siguientes resúmenes en uno solo coherente. Mantén solo la información más importante:',
            'questions': 'Combina las siguientes preguntas y respuestas. Elimina duplicados y mantén solo las 5 más importantes:',
            'key_points': 'Combina los siguientes puntos clave. Elimina duplicados y mantén solo los 5 más importantes:'
        },
        'en': {
            'summary': 'Combine the following summaries into one coherent summary. Keep only the most important information:',
            'questions': 'Combine the following questions and answers. Remove duplicates and keep only the 5 most important ones:',
            'key_points': 'Combine the following key points. Remove duplicates and keep only the 5 most important ones:'
        }
    }.get(lang, 'en')
    
    prompt = f"{combine_instructions[material_type]}\n\n{combined}"
    
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    response = client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[
            {"role": "system", "content": "You are a helpful assistant that combines information."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=2000
    )
    
    return clean_latex(response.choices[0].message.content)

@st.cache_data(ttl=3600, show_spinner=False)  # Cache results for 1 hour
def generate_study_material(transcript: str, material_type: str = "summary", language: str = 'en') -> str:
    """
    Generate study materials using Groq API with error handling and caching.
    
    Args:
        transcript: The transcript text to process
        material_type: Type of material to generate (summary, qa, etc.)
        language: Language code for the output
        
    Returns:
        str: Generated content or error message
    """
    if not transcript or not isinstance(transcript, str):
        return "Error: No transcript provided"
        
    if not material_type or not isinstance(material_type, str):
        return "Error: Invalid material type"
        
    try:
        # Get the Groq API key from environment variables
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            return "Error: GROQ_API_KEY not found in environment variables"
            
        client = Groq(api_key=api_key)
        
        # Check if the transcript is too long and needs to be split
        if len(transcript) > 4000:
            # Split the transcript into chunks
            chunks = split_into_chunks(transcript)
            
            if not chunks:
                return "Error: Unable to split transcript into chunks"
                
            # Process each chunk
            results = []
            progress_bar = st.progress(0.0)
            
            for i, chunk in enumerate(chunks):
                progress = float(i) / len(chunks)
                progress_bar.progress(progress, f"Processing part {i+1} of {len(chunks)}...")
                
                result = process_chunk(client, chunk, material_type, language)
                if result:
                    results.append(result)
            
            # Combine the results
            progress_bar.progress(1.0, "Combining results...")
            final_result = combine_results(results, material_type, language)
            progress_bar.empty()
            return final_result
        else:
            # Process as a single chunk
            return process_chunk(client, transcript, material_type, language)
            
    except GroqError as e:
        return f"Groq API Error: {str(e)}"
    except Exception as e:
        return f"Error generating content: {str(e)}"

def main():
    st.set_page_config(
        page_title="MentorIA Suite",
        page_icon="🧙‍♂️"
    )
    
    # Header with centered text
    st.markdown("<h1 style='text-align: center;'>🧙‍♂️ MentorIA Suite</h1>", unsafe_allow_html=True)
    st.markdown("<div style='text-align: center; color: #6c757d; margin-top: -1rem; margin-bottom: 2rem; font-style: italic;'>Mentoria is just getting started — powerful tools are on the way. Stay tuned!</div>", unsafe_allow_html=True)
    
    st.title("🎓 YouTube Study Assistant")
    
    st.write("Paste a YouTube URL to extract the transcript and generate study materials.")
    
    # Add language selection
    language = st.selectbox(
        "Select transcript language:",
        ["es", "en"],
        format_func=lambda x: "Spanish" if x == "es" else "English"
    )
    
    # Create a form to handle both Enter key and button press
    with st.form("youtube_form"):
        st.markdown("<div style='margin-bottom: 6px;'>Paste YouTube Video URL:</div>", unsafe_allow_html=True)
        
        # Main row with input and button
        input_col, button_col = st.columns([5, 1])
        with input_col:
            # Add some custom CSS to align the input field
            st.markdown("""
                <style>
                    div[data-testid="stTextInput"] {
                        margin-bottom: 0;
                    }
                </style>
            """, unsafe_allow_html=True)
            url = st.text_input("Enter YouTube URL", 
                             key="url_input", 
                             label_visibility="collapsed")
        with button_col:
            # Add custom styling to the button container
            st.markdown("<div style='display: flex; align-items: flex-start; height: 100%; padding-top: 0rem;'>", unsafe_allow_html=True)
            submit_button = st.form_submit_button("Enter", type="primary", use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
    
    if (url and submit_button) or (url and not st.session_state.get('url_input_processed', False)):
        video_id = extract_video_id(url)
        st.video(f"https://www.youtube.com/watch?v={video_id}")
        
        col1, col2 = st.columns([2, 1])  # Adjust column widths to reduce spacing
        
        with col1:
            get_transcript_button = st.button("Get Transcript")
        
        if get_transcript_button:
            with st.spinner("Fetching transcript..."):
                transcript = get_transcript(video_id, language=language)
                
            if transcript.startswith("Error"):
                st.error(transcript)
            else:
                st.session_state.transcript = transcript
                st.success("Transcript fetched successfully!")
        
    if 'transcript' in st.session_state:
        st.subheader("Generate Study Materials")

        with st.expander("View Transcript"):
            # Display transcript in a text area
            st.text_area("Transcript", value=st.session_state.transcript, height=300, key="transcript_text_area")

        # Initialize session state for materials if not exists
        if 'generated_materials' not in st.session_state:
            st.session_state.generated_materials = {
                'summary': None,
                'key_points': None,
                'questions': None
            }

        # Map display names to material type values
        material_types = {
            "Summary": "summary",
            "Key Points": "key_points",
            "Questions & Answers": "questions"
        }
        
        # Create radio buttons with display names
        selected_display = st.radio(
            "Select material type:",
            list(material_types.keys())
        )
        
        # Get the corresponding material type value
        material_type = material_types[selected_display]
        
        # Generate or retrieve the selected material
        if st.button(f"Generate {selected_display}"):
            with st.spinner(f"Generating {selected_display.lower()}..."):
                material = generate_study_material(st.session_state.transcript, material_type, language)
                # Store the generated material in session state
                st.session_state.generated_materials[material_type] = material
        
        # Display the selected material if it exists
        if st.session_state.generated_materials[material_type]:
            material = st.session_state.generated_materials[material_type]
            
            # Format the content based on material type
            if material_type == 'summary':
                formatted_content = material
            elif material_type == 'key_points':
                formatted_content = format_bullet_points(material, language)
            else:  # questions
                formatted_content = format_qa(material, language)
            
            # Display the formatted content
            st.markdown(formatted_content)
            
            # Add copy button
            st.download_button(
                label="Copy to Clipboard",
                data=formatted_content,
                file_name=f"youtube_{material_type}.txt",
                mime="text/plain"
            )

def footer():
    st.markdown("""
    <div style='text-align: center; margin-top: 4rem; padding: 1.5rem 0; border-top: 1px solid #e0e0e0; color: #6c757d; font-size: 0.9rem;'>
        <div>Made with ❤️ in Colombia by <strong>AZ Tech</strong> | <a href='https://aztechnologies.web.app/' target='_blank' style='color: #4a6cf7; text-decoration: none;'>Website</a></div>
        <div><strong>Eng. Andrés Felipe Jiménez Pérez</strong> | <a href='https://www.linkedin.com/in/felipejimenezperez/' target='_blank' style='color: #4a6cf7; text-decoration: none;'>LinkedIn</a></div>
        <div>© 2025 AZ Tech. All rights reserved.</div>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    load_dotenv()
    if not os.getenv("GROQ_API_KEY"):
        st.error("Please create a .env file with your GROQ_API_KEY")
    else:
        main()
        footer()
