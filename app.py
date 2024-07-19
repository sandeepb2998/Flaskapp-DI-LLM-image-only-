import os
import base64
from mimetypes import guess_type
from flask import Flask, request, render_template, redirect, url_for, session
from flask_session import Session
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from openai import AzureOpenAI
import markdown2

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SECRET_KEY'] = 'supersecretkey'  # Change this to a random secret key
app.config['SESSION_TYPE'] = 'filesystem'

Session(app)

# Function to encode a local image into data URL 
def local_image_to_data_url(image_path):
    mime_type, _ = guess_type(image_path)
    if mime_type is None:
        mime_type = 'application/octet-stream'
    with open(image_path, "rb") as image_file:
        base64_encoded_data = base64.b64encode(image_file.read()).decode('utf-8')
    return f"data:{mime_type};base64,{base64_encoded_data}"

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        session['azure_doc_endpoint'] = request.form['azure_doc_endpoint']
        session['azure_doc_key'] = request.form['azure_doc_key']
        session['openai_api_key'] = request.form['openai_api_key']
        session['openai_endpoint'] = request.form['openai_endpoint']
        return redirect(url_for('upload_image'))

    return render_template('index.html')

@app.route('/upload', methods=['GET', 'POST'])
def upload_image():
    if request.method == 'POST':
        if 'file' not in request.files:
            return 'No file part'
        file = request.files['file']
        if file.filename == '':
            return 'No selected file'
        if file:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(file_path)
            
            # Extract text using Document Intelligence
            document_intelligence_client = DocumentIntelligenceClient(
                endpoint=session['azure_doc_endpoint'], 
                credential=AzureKeyCredential(session['azure_doc_key'])
            )

            with open(file_path, "rb") as document:
                poller = document_intelligence_client.begin_analyze_document(
                    "prebuilt-layout",
                    document,
                    content_type="image/jpeg",
                    output_content_format="markdown"
                )

            result = poller.result()
            markdown_content = result.content

            # Store the markdown content in the session
            session['markdown_content'] = markdown_content

            # Prepare image for GPT-4 Turbo with Vision
            image_data_url = local_image_to_data_url(file_path)
            session['image_data_url'] = image_data_url

            return redirect(url_for('ask_question'))

    return render_template('upload.html')

@app.route('/ask', methods=['GET', 'POST'])
def ask_question():
    if request.method == 'POST':
        user_question = request.form['question']

        markdown_content = session.get('markdown_content')
        image_data_url = session.get('image_data_url')

        if not markdown_content or not image_data_url:
            return 'No image uploaded'

        # Set up OpenAI client
        openai_client = AzureOpenAI(
            api_key=session['openai_api_key'],
            api_version="2024-02-15-preview",
            azure_endpoint=session['openai_endpoint']
        )

        # Prepare the messages for GPT-4 Turbo with Vision
        messages = [
            {"role": "system", "content": "You are provided with OCR-extracted text from construction document images in Markdown format. Your task is to analyze this text and extract relevant information to assist construction workers. The content is formatted in Markdown, so please interpret and use Markdown syntax appropriately in your responses."},
            {"role": "user", "content": [
                {"type": "text", "text": f"Here's the extracted text content in Markdown format:\n\n{markdown_content}"},
                {"type": "image_url", "image_url": {"url": image_data_url}}
            ]},
            {"role": "user", "content": user_question}
        ]

        # Make the API call
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=800
        )

        formatted_response = response.choices[0].message.content

        # Convert Markdown to HTML
        html_response = markdown2.markdown(formatted_response)

        return render_template('result.html', response=html_response, question=user_question)

    return render_template('ask.html')

if not os.path.exists('uploads'):
    os.makedirs('uploads')

if __name__ == '__main__':
    app.run(debug=True)
