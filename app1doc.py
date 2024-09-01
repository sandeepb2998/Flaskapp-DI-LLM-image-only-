import tempfile
from flask import Flask, request, redirect, url_for, session
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult, ContentFormat
from flask import render_template  # {{ edit_1 }}

app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey'

@app.route('/upload', methods=['GET', 'POST'])
def upload_pdf():
    if request.method == 'POST':
        if 'file' not in request.files:
            return 'No file part'
        file = request.files['file']
        if file.filename == '':
            return 'No selected file'
        
        if file and file.filename.endswith('.pdf'):
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                file.save(temp_file.name)
                
                # Initialize the Azure Document Intelligence client
                document_intelligence_client = DocumentIntelligenceClient(
                    endpoint=session['azure_doc_endpoint'],
                    credential=AzureKeyCredential(session['azure_doc_key'])
                )
                
                # Analyze the document using the file path
                with open(temp_file.name, "rb") as document:
                    poller = document_intelligence_client.begin_analyze_document(
                        "prebuilt-document",
                        document,
                        output_content_format=ContentFormat.MARKDOWN
                    )
                
                result: AnalyzeResult = poller.result()

                # Store the markdown content in the session
                session['markdown_content'] = result.content

                # Redirect to a new route to display the extracted content
                return redirect(url_for('display_extracted_content'))

    if 'azure_doc_endpoint' not in session or 'azure_doc_key' not in session:  # {{ edit_2 }}
        return 'Azure credentials not set in session'
    return render_template('upload.html')

@app.route('/display', methods=['GET'])
def display_extracted_content():
    markdown_content = session.get('markdown_content')
    if not markdown_content:
        return 'No document uploaded or processed'
    return render_template('display.html', content=markdown_content)

if __name__ == '__main__':
    app.run(debug=True)