import os
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

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        session['azure_doc_endpoint'] = request.form['azure_doc_endpoint']
        session['azure_doc_key'] = request.form['azure_doc_key']
        session['openai_api_key'] = request.form['openai_api_key']
        session['openai_endpoint'] = request.form['openai_endpoint']
        return redirect(url_for('upload_pdf'))

    return render_template('index.html')

@app.route('/upload', methods=['GET', 'POST'])
def upload_pdf():
    if request.method == 'POST':
        if 'file' not in request.files:
            return 'No file part'
        file = request.files['file']
        if file.filename == '':
            return 'No selected file'
        
        # Check if the uploaded file is a PDF
        if file and file.filename.endswith('.pdf'):
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(file_path)
            
            # Extract text using Document Intelligence
            document_intelligence_client = DocumentIntelligenceClient(
                endpoint=session['azure_doc_endpoint'], 
                credential=AzureKeyCredential(session['azure_doc_key'])
            )

            with open(file_path, "rb") as document:
                poller = document_intelligence_client.begin_analyze_document(
                    "prebuilt-document",  # Use "prebuilt-document" for PDF files
                    document,
                    content_type="application/pdf",
                    output_content_format="markdown"
                )

            result = poller.result()
            markdown_content = result.content

            # Store the markdown content in the session
            session['markdown_content'] = markdown_content

            # Redirect to a new route to display the extracted content
            return redirect(url_for('display_extracted_content'))

    return render_template('upload.html')

@app.route('/display', methods=['GET'])
def display_extracted_content():
    markdown_content = session.get('markdown_content')

    if not markdown_content:
        return 'No document uploaded or processed'

    # Render the extracted content
    return render_template('display.html', content=markdown_content)

@app.route('/ask', methods=['GET', 'POST'])
def ask_question():
    if request.method == 'POST':
        user_question = request.form['question']

        markdown_content = session.get('markdown_content')

        if not markdown_content:
            return 'No document uploaded or processed'

        # Set up OpenAI client
        openai_client = AzureOpenAI(
            api_key=session['openai_api_key'],
            api_version="2024-06-01",
            azure_endpoint=session['openai_endpoint']
        )

        # Prepare the messages for GPT-4 Turbo
        messages = [
            {"role": "system", "content": "You are provided with OCR-extracted text from medical documents in Markdown format. Your task is to analyze this text and extract relevant information to assist medical professionals."},
            {"role": "user", "content": f"Here's the extracted text content in Markdown format:\n\n{markdown_content}"},
            {"role": "user", "content": user_question}
        ]

        # Make the API call
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0,
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