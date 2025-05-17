import os
import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi
from groq import Groq
from dotenv import load_dotenv

def extract_video_id(url):
    """Extract video ID from YouTube URL"""
    if 'youtube.com' in url:
        return url.split('v=')[1].split('&')[0]
    elif 'youtu.be' in url:
        return url.split('/')[-1]
    return url

def get_transcript(video_id, language='es'):
    """Fetch transcript for a given YouTube video ID in the specified language"""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # Try to get transcript in the specified language
        try:
            transcript = transcript_list.find_transcript([language])
        except:
            # If specified language not found, try to get any available transcript
            transcript = next(iter(transcript_list), None)
            if transcript:
                transcript = transcript.translate('es').fetch()
                return " ".join([entry['text'] for entry in transcript])
            
        transcript = transcript.fetch()
        return " ".join([entry['text'] for entry in transcript])
        
    except Exception as e:
        return f"Error fetching transcript: {str(e)}"

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

def format_qa(text):
    """Format Q&A text with proper spacing and line breaks"""
    # Split into Q&A pairs
    qa_pairs = []
    current_q = None
    
    # Split by 'Pregunta ' to separate each Q&A
    parts = text.split('Pregunta ')
    
    for part in parts[1:]:  # Skip first empty part
        if 'Respuesta:' in part:
            q_num, rest = part.split(':', 1)
            q, a = rest.split('Respuesta:', 1)
            qa_pairs.append((f'Pregunta {q_num}:{q}', a.strip()))
    
    # Format each Q&A pair with proper spacing
    formatted_lines = []
    for q, a in qa_pairs:
        formatted_lines.append(f'**{q}**')
        formatted_lines.append(f'{a}\n')
    
    return '\n'.join(formatted_lines)

def format_bullet_points(text):
    """Format text with bullet points or Q&A with proper spacing and line breaks"""
    # Check if this is a Q&A format
    if 'Pregunta' in text and 'Respuesta:' in text:
        return format_qa(text)
        
    # Otherwise, handle as bullet points
    parts = text.split('•')
    
    # Process each part
    formatted_parts = []
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
            
        # Add bullet point (except for the first part if it doesn't start with a bullet)
        if i > 0 or text.strip().startswith('•'):
            formatted_parts.append(f'• {part}')
        else:
            formatted_parts.append(part)
    
    # Join with double line breaks between bullet points
    formatted_text = '\n\n'.join(formatted_parts)
    
    # Clean up any triple line breaks
    while '\n\n\n' in formatted_text:
        formatted_text = formatted_text.replace('\n\n\n', '\n\n')
    
    return formatted_text.strip()

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
                'Formato requerido (usa exactamente este formato para cada pregunta y respuesta):\n\n'
                'Pregunta 1: [Tu pregunta aquí]\n'
                'Respuesta: [Tu respuesta aquí]\n\n'
                'Pregunta 2: [Tu pregunta aquí]\n'
                'Respuesta: [Tu respuesta aquí]\n\n'
                'Y así sucesivamente. Asegúrate de que cada pregunta y respuesta estén en líneas separadas y haya una línea en blanco entre cada par pregunta-respuesta.'
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
                'Required format (use exactly this format for each Q&A pair):\n\n'
                'Question 1: [Your question here]\n'
                'Answer: [Your answer here]\n\n'
                'Question 2: [Your question here]\n'
                'Answer: [Your answer here]\n\n'
                'And so on. Make sure each question and answer are on separate lines and there is a blank line between each Q&A pair.'
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

def generate_study_material(transcript, material_type="summary"):
    """Generate study materials using Groq in the same language as the transcript"""
    if not transcript or not transcript.strip():
        return "Error: Empty transcript"
        
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    
    # Detect the language of the transcript
    lang = detect_language(transcript)
    
    if material_type not in ['summary', 'questions', 'key_points']:
        return "Invalid material type"
    
    try:
        # Split the transcript into chunks
        chunks = split_into_chunks(transcript)
        
        if len(chunks) > 1:
            # Process each chunk separately
            results = []
            progress_bar = st.progress(0)
            for i, chunk in enumerate(chunks):
                progress_bar.progress((i + 1) / len(chunks), f"Processing part {i + 1} of {len(chunks)}")
                result = process_chunk(client, chunk, material_type, lang)
                results.append(result)
            
            # Combine the results
            progress_bar.progress(1.0, "Combining results...")
            final_result = combine_results(results, material_type, lang)
            progress_bar.empty()
            return final_result
        else:
            # Process as a single chunk
            return process_chunk(client, transcript, material_type, lang)
            
        
    except Exception as e:
        return f"Error generating content: {str(e)}"
    except Exception as e:
        return f"Error generating content: {str(e)}"

def main():
    st.set_page_config(
        page_title="MentorIA Suite",
        page_icon="🧙‍♂️"
    )
    
    # Header with centered text
    st.markdown("<h1 style='text-align: center;'>🧙‍♂️ MentorIA Suite</h1>", unsafe_allow_html=True)
    st.markdown("<div style='text-align: center; color: #6c757d; margin-top: -1rem; margin-bottom: 2rem; font-style: italic;'>Wait for more tools!</div>", unsafe_allow_html=True)
    
    st.title("🎓 YouTube Study Assistant")
    
    st.write("Paste a YouTube URL to extract the transcript and generate study materials.")
    
    # Add language selection
    language = st.selectbox(
        "Select transcript language:",
        ["es", "en"],
        format_func=lambda x: "Spanish" if x == "es" else "English"
    )
    
    url = st.text_input("YouTube Video URL:")
    
    if url:
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
                material = generate_study_material(st.session_state.transcript, material_type)
                # Store the generated material in session state
                st.session_state.generated_materials[material_type] = material
        
        # Display the selected material if it exists
        if st.session_state.generated_materials[material_type]:
            material = st.session_state.generated_materials[material_type]
            
            # Format the content based on material type
            if material_type == 'summary':
                formatted_content = material
            elif material_type == 'key_points':
                formatted_content = format_bullet_points(material)
            else:  # questions
                formatted_content = format_qa(material)
            
            # Add emoji based on material type
            emoji_map = {
                'summary': '📝',
                'key_points': '🔑',
                'questions': '❓'
            }
            
            # Get the appropriate title
            titles = {
                'summary': 'Summary',
                'key_points': 'Key Points',
                'questions': 'Questions & Answers'
            }
            
            title = titles.get(material_type, material_type.capitalize())
            emoji = emoji_map.get(material_type, '📄')
            
            # Display the formatted content with appropriate title and emoji
            st.subheader(f"{emoji} {title}")
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
        <div>Made with ❤️ in Colombia by <strong>Andrés Felipe Jiménez Pérez</strong></div>
        <div style='margin-bottom: 0.5rem;'>
            <a href='https://www.linkedin.com/in/felipejimenezperez/' target='_blank' style='color: #4a6cf7; text-decoration: none;'>LinkedIn</a>
        </div>
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
