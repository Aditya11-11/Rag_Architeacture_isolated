import os
import shutil
import uuid
from pathlib import Path
import gradio as gr
import google.generativeai as genai

# Import the core modules from the local app package
from app.config import settings
from app.core.document_processor import process_document
from app.core.pii_masker import mask_pii
from app.core.embeddings import embed_texts, embed_query
from app.db.chroma_client import chroma_manager

# Ensure upload and database persist directories are created
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)


def configure_api_key(api_key: str):
    """Globally configures the google-generativeai package with the user-provided API key."""
    if not api_key or not api_key.strip():
        raise ValueError("Google Gemini API Key is required. Please enter your API key in the Setup section.")
    genai.configure(api_key=api_key.strip())


def verify_api_key(api_key: str):
    """Verifies that the provided API key is valid by listing models."""
    if not api_key or not api_key.strip():
        return "❌ API Key is empty. Please enter your API key."
    try:
        genai.configure(api_key=api_key.strip())
        # Make a quick, lightweight check to verify the key works
        models = genai.list_models()
        next(iter(models))
        return "✅ API Key verified successfully! You are ready to upload files and query."
    except Exception as e:
        return f"❌ Verification failed. Please check your API key. Details: {str(e)}"


def pii_masker_ui(text):
    """Interactive demo of PII masking function."""
    if not text:
        return "", ""
    
    masked_text, findings = mask_pii(text)
    
    badge_map = {
        "[EMAIL]": ("EMAIL", "pii-badge-email"),
        "[PHONE]": ("PHONE", "pii-badge-phone"),
        "[PASSWORD]": ("PASSWORD", "pii-badge-pwd"),
        "[CREDIT_CARD]": ("CREDIT_CARD", "pii-badge-card"),
        "[SSN]": ("SSN", "pii-badge-ssn"),
        "[API_KEY]": ("API_KEY", "pii-badge-key"),
        "[CLIENT_ID]": ("CLIENT_ID", "pii-badge-key"),
        "[JWT_TOKEN]": ("JWT_TOKEN", "pii-badge-key"),
        "[IP_ADDRESS]": ("IP_ADDRESS", "pii-badge-ip")
    }
    
    badges_html = ""
    if findings:
        badges_html = "<div><strong>Detected PII Elements:</strong><br>"
        for finding in set(findings):
            name, css_class = badge_map.get(finding, (finding.strip("[]"), "pii-badge-ip"))
            badges_html += f'<span class="pii-badge {css_class}">{name}</span>'
        badges_html += "</div>"
    else:
        badges_html = "<div>🟢 No PII elements detected.</div>"
        
    return masked_text, badges_html


def upload_and_process_ui(api_key, customer_id, files, chunk_size, overlap):
    """Handles document uploading, local saving, chunking, PII masking, embedding and indexing."""
    if not api_key or not api_key.strip():
        return "❌ Error: Please enter your Gemini API Key in the API Key Setup section above.", ""
    
    if not customer_id or not customer_id.strip():
        return "❌ Error: Customer ID is required.", ""
    
    if not files:
        return "❌ Error: Please select at least one file to upload.", ""
    
    try:
        configure_api_key(api_key)
    except Exception as e:
        return f"❌ Configuration Error: {str(e)}", ""
    
    customer_dir = Path(settings.UPLOAD_DIR) / customer_id.strip()
    customer_dir.mkdir(parents=True, exist_ok=True)
    
    summary_logs = []
    pii_summary_html = ""
    
    for file in files:
        filename = os.path.basename(file.name)
        save_path = customer_dir / filename
        
        # Copy the temporary file to the customer's directory
        shutil.copy(file.name, save_path)
        
        try:
            chunks = process_document(
                str(save_path),
                chunk_size=int(chunk_size),
                overlap=int(overlap),
            )
        except Exception as exc:
            save_path.unlink(missing_ok=True)
            summary_logs.append(f"❌ Failed to parse/process '{filename}': {str(exc)}")
            continue
            
        if not chunks:
            save_path.unlink(missing_ok=True)
            summary_logs.append(f"⚠️ Could not extract text from '{filename}' (file might be empty).")
            continue
            
        texts = [c["text"] for c in chunks]
        
        try:
            embeddings = embed_texts(texts, task_type="retrieval_document")
        except Exception as exc:
            save_path.unlink(missing_ok=True)
            summary_logs.append(f"❌ Gemini Embedding generation failed for '{filename}': {str(exc)}")
            continue
            
        ids = [f"{customer_id}::{filename}::{c['chunk_index']}::{uuid.uuid4().hex[:8]}" for c in chunks]
        metadatas = [
            {
                "filename": filename,
                "chunk_index": c["chunk_index"],
                "customer_id": customer_id,
            }
            for c in chunks
        ]
        
        try:
            chroma_manager.add_documents(
                customer_id=customer_id,
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )
            summary_logs.append(f"✅ Successfully indexed {len(chunks)} chunks from '{filename}'.")
            
            # Formulate PII findings display
            all_findings = []
            for chunk in chunks:
                all_findings.extend(chunk.get("pii_types_masked", []))
            
            if all_findings:
                unique_findings = sorted(list(set(all_findings)))
                pii_summary_html += f"<div style='margin-bottom:15px; border-bottom:1px solid rgba(0,0,0,0.1); padding-bottom:10px;'>"
                pii_summary_html += f"<strong>📄 {filename} (PII Detected)</strong><br>"
                for finding in unique_findings:
                    pii_summary_html += f'<span class="pii-badge pii-badge-card">{finding.strip("[]")}</span> '
                
                # Show first chunk as snippet
                masked_preview = chunks[0]["text"][:250] + "..." if len(chunks[0]["text"]) > 250 else chunks[0]["text"]
                pii_summary_html += f"<pre style='background:rgba(99,102,241,0.03); color:#374151; padding:10px; border-radius:6px; margin-top:5px; font-family:monospace; font-size:0.85rem; border:1px solid rgba(99,102,241,0.1); white-space:pre-wrap;'>{masked_preview}</pre>"
                pii_summary_html += f"</div>"
            else:
                pii_summary_html += f"<div style='margin-bottom:15px; border-bottom:1px solid rgba(0,0,0,0.1); padding-bottom:10px;'>"
                pii_summary_html += f"<strong>📄 {filename}</strong><br>🟢 No PII detected and masked in this document.<br>"
                pii_summary_html += f"</div>"
                
        except Exception as exc:
            summary_logs.append(f"❌ Database Indexing Error for '{filename}': {str(exc)}")
            
    return "\n".join(summary_logs), pii_summary_html


def query_documents_ui(api_key, customer_id, query_str, top_k):
    """Retrieves context and queries Gemini model using user-specified API key."""
    if not api_key or not api_key.strip():
        return "❌ Error: Please enter your Gemini API Key in the Setup section.", "No sources", 0, "No chunks retrieved."
    
    if not customer_id or not customer_id.strip():
        return "❌ Error: Customer ID is required.", "No sources", 0, "No chunks retrieved."
        
    if not query_str or not query_str.strip():
        return "❌ Error: Please enter a query.", "No sources", 0, "No chunks retrieved."
        
    try:
        configure_api_key(api_key)
        
        # Instantiate model dynamically to ensure it uses the newly configured key
        model = genai.GenerativeModel(settings.GEMINI_LLM_MODEL)
        
        query_embedding = embed_query(query_str)
        results = chroma_manager.query(
            customer_id=customer_id,
            query_embedding=query_embedding,
            n_results=int(top_k),
        )
        
        docs = results["documents"][0] if results["documents"] else []
        metas = results["metadatas"][0] if results["metadatas"] else []
        
        if not docs:
            return (
                "🔍 I could not find any documents for this customer ID. Please upload documents first.",
                "No sources found",
                0,
                "No chunks retrieved."
            )
            
        context = "\n\n---\n\n".join(docs)
        sources = sorted({m.get("filename", "unknown") for m in metas})
        
        _SYSTEM_PROMPT = """You are a helpful assistant that answers questions strictly based on the
provided document context. Follow these rules:
1. Answer ONLY from the context below. Do not use outside knowledge.
2. If the context does not contain enough information, say "I could not find relevant information in your documents."
3. Be concise and factual.
4. Never reveal or guess masked PII placeholders (e.g. [EMAIL], [SSN]).

Context:
{context}

Question: {question}

Answer:"""
        
        prompt = _SYSTEM_PROMPT.format(context=context, question=query_str)
        response = model.generate_content(prompt)
        answer = response.text.strip()
        
        # Format the retrieved chunks for viewing
        chunks_display = ""
        for idx, (doc, meta) in enumerate(zip(docs, metas)):
            chunks_display += f"### 🧩 Chunk {idx + 1} (Source: `{meta.get('filename')}`, Chunk Index: {meta.get('chunk_index')})\n"
            chunks_display += f"```text\n{doc}\n```\n\n"
            
        return answer, ", ".join(sources), len(docs), chunks_display
        
    except Exception as exc:
        return f"❌ Error performing query: {str(exc)}", "Error", 0, "No chunks retrieved."


def list_documents_ui(customer_id):
    """Retrieves the list of active indexed files for a customer."""
    if not customer_id or not customer_id.strip():
        return "❌ Error: Customer ID is required.", gr.Dropdown(choices=[])
        
    try:
        info = chroma_manager.list_documents(customer_id)
        files = info["filenames"]
        total_chunks = info["total_chunks"]
        
        if not files:
            return f"ℹ️ No documents found for customer '{customer_id}'.", gr.Dropdown(choices=[])
            
        msg = f"📂 **Active Documents for Customer '{customer_id}'** (Total Chunks: {total_chunks}):\n\n"
        for file in files:
            msg += f"- `{file}`\n"
        return msg, gr.Dropdown(choices=files, value=files[0] if files else None)
    except Exception as e:
        return f"❌ Error listing documents: {str(e)}", gr.Dropdown(choices=[])


def delete_document_ui(customer_id, filename):
    """Deletes a specific document from a customer's index and storage."""
    if not customer_id or not customer_id.strip():
        return "❌ Error: Customer ID is required."
    if not filename:
        return "❌ Error: Please select a file to delete."
        
    try:
        deleted = chroma_manager.delete_by_filename(customer_id, filename)
        disk_path = Path(settings.UPLOAD_DIR) / customer_id.strip() / filename
        disk_path.unlink(missing_ok=True)
        
        return f"✅ Successfully deleted document '{filename}' (removed {deleted} chunks from DB and disk)."
    except Exception as e:
        return f"❌ Error deleting document: {str(e)}"


def purge_customer_ui(customer_id):
    """Deletes all documents and chunks associated with a customer."""
    if not customer_id or not customer_id.strip():
        return "❌ Error: Customer ID is required."
        
    try:
        deleted = chroma_manager.delete_all(customer_id)
        customer_dir = Path(settings.UPLOAD_DIR) / customer_id.strip()
        if customer_dir.exists():
            for f in customer_dir.iterdir():
                f.unlink(missing_ok=True)
            try:
                customer_dir.rmdir()
            except Exception:
                pass
        return f"💥 Customer '{customer_id}' data purged successfully! Removed {deleted} chunks and deleted all files."
    except Exception as e:
        return f"❌ Error purging customer data: {str(e)}"


# Define Custom CSS for a beautiful styling layout
custom_css = """
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Inter:wght@300;400;500;600;700&display=swap');

body, .gradio-container {
    font-family: 'Inter', sans-serif !important;
}

h1, h2, h3, h4, h5, h6 {
    font-family: 'Outfit', sans-serif !important;
    font-weight: 600;
}

.title-container {
    text-align: center;
    padding: 2rem 1.5rem;
    background: linear-gradient(135deg, rgba(99, 102, 241, 0.08) 0%, rgba(139, 92, 246, 0.08) 100%);
    border-radius: 16px;
    margin-bottom: 2rem;
    border: 1px solid rgba(99, 102, 241, 0.15);
    box-shadow: 0 10px 30px -15px rgba(99, 102, 241, 0.1);
}

.title-container h1 {
    font-size: 2.2rem !important;
    background: linear-gradient(90deg, #6366f1, #8b5cf6, #ec4899);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 0.5rem;
}

.subtitle {
    color: #4b5563;
    font-size: 1rem;
    max-width: 800px;
    margin: 0 auto;
}

.dark .subtitle {
    color: #9ca3af;
}

.glass-card {
    background: rgba(255, 255, 255, 0.6);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border: 1px solid rgba(229, 231, 235, 0.5);
    border-radius: 12px;
    padding: 1.5rem;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
}

.dark .glass-card {
    background: rgba(17, 24, 39, 0.6);
    border: 1px solid rgba(75, 85, 99, 0.3);
}

.apikey-container {
    border-left: 4px solid #6366f1 !important;
    background: linear-gradient(90deg, rgba(99, 102, 241, 0.03) 0%, transparent 100%);
}

.primary-btn {
    background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%) !important;
    color: white !important;
    border: none !important;
    transition: all 0.3s ease !important;
    box-shadow: 0 4px 12px rgba(99, 102, 241, 0.2);
}

.primary-btn:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 20px rgba(99, 102, 241, 0.3);
}

.danger-btn {
    background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%) !important;
    color: white !important;
    border: none !important;
    transition: all 0.3s ease !important;
    box-shadow: 0 4px 12px rgba(239, 68, 68, 0.2);
}

.danger-btn:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 20px rgba(239, 68, 68, 0.3);
}

.pii-badge {
    display: inline-block;
    padding: 0.2rem 0.6rem;
    margin: 0.15rem;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
    color: white;
}

.pii-badge-email { background-color: #3b82f6; }
.pii-badge-phone { background-color: #10b981; }
.pii-badge-pwd { background-color: #f59e0b; }
.pii-badge-card { background-color: #ec4899; }
.pii-badge-ssn { background-color: #8b5cf6; }
.pii-badge-key { background-color: #6366f1; }
.pii-badge-ip { background-color: #6b7280; }
"""

# Build Gradio UI
with gr.Blocks() as demo:
    
    # Title Section
    with gr.Group(elem_classes=["title-container"]):
        gr.Markdown(
            "# Secure Document Query System (Secure Doc RAG)\n"
            "An enterprise-grade, privacy-compliant RAG system. Enforces **strict multi-tenant isolation** at the storage layer "
            "and automatically **identifies and masks PII** (emails, phone numbers, credentials, credit cards, IP addresses) "
            "*before* generating embeddings or storing data.",
            elem_id="title-desc"
        )
        
    # API Key Configuration Card
    with gr.Row(elem_classes=["glass-card", "apikey-container"]):
        with gr.Column(scale=4):
            api_key_input = gr.Textbox(
                label="🔑 Enter Your Google Gemini API Key",
                placeholder="Paste your API key here (AIzaSy...)",
                type="password",
                info="Your key is processed locally and never stored permanently."
            )
        with gr.Column(scale=1, min_width=150):
            verify_btn = gr.Button("Verify Key", elem_classes=["primary-btn"])
            verify_status = gr.Markdown("⚠️ API Key not configured")
            
    # Connect verify button
    verify_btn.click(
        fn=verify_api_key,
        inputs=[api_key_input],
        outputs=[verify_status]
    )
    
    # Tabs Section
    with gr.Tabs():
        
        # TAB 1: Document Uploading
        with gr.TabItem("📤 Index & Upload Documents"):
            gr.Markdown("### Upload documents for indexing. PII will be masked automatically before embeddings are saved.")
            with gr.Row():
                with gr.Column(scale=1):
                    upload_cust_id = gr.Textbox(
                        value="customer_001",
                        label="Customer ID",
                        info="Used to partition storage and isolate database collections."
                    )
                    file_input = gr.File(
                        file_count="multiple",
                        label="Select Files",
                        file_types=[".pdf", ".docx", ".txt"]
                    )
                    with gr.Accordion("Advanced Chunking Options", open=False):
                        chunk_size = gr.Slider(
                            minimum=200, maximum=3000, step=100, value=1000,
                            label="Chunk Size (characters)"
                        )
                        chunk_overlap = gr.Slider(
                            minimum=50, maximum=1000, step=50, value=200,
                            label="Chunk Overlap (characters)"
                        )
                    upload_btn = gr.Button("Upload & Index Documents", elem_classes=["primary-btn"])
                    
                with gr.Column(scale=1):
                    upload_status = gr.Textbox(
                        label="Indexing Status Logs",
                        interactive=False,
                        lines=5
                    )
                    pii_summary = gr.HTML(
                        label="PII Masking Summary",
                        value="<div style='color:#6b7280;font-style:italic;'>Upload files to see PII masking reports.</div>"
                    )
            
            upload_btn.click(
                fn=upload_and_process_ui,
                inputs=[api_key_input, upload_cust_id, file_input, chunk_size, chunk_overlap],
                outputs=[upload_status, pii_summary]
            )
            
        # TAB 2: Querying / RAG
        with gr.TabItem("🔍 Query Documents (RAG)"):
            gr.Markdown("### Query indexed documents. Gemini will formulate responses strictly based on the masked document context.")
            with gr.Row():
                with gr.Column(scale=2):
                    query_cust_id = gr.Textbox(
                        value="customer_001",
                        label="Customer ID",
                        info="Queries are isolated to this customer's vector space."
                    )
                    query_input = gr.Textbox(
                        label="Ask a Question",
                        placeholder="e.g., What are the credentials for the database or support email?"
                    )
                    top_k_slider = gr.Slider(
                        minimum=1, maximum=10, step=1, value=5,
                        label="Top K Results",
                        info="Number of relevant document chunks to feed to the LLM context."
                    )
                    query_btn = gr.Button("Retrieve & Answer", elem_classes=["primary-btn"])
                    
                with gr.Column(scale=3):
                    answer_output = gr.Markdown(
                        label="System Answer"
                    )
                    with gr.Row():
                        sources_output = gr.Textbox(
                            label="Source Documents",
                            interactive=False
                        )
                        chunks_used_output = gr.Number(
                            label="Context Chunks Used",
                            precision=0,
                            interactive=False
                        )
                    
                    with gr.Accordion("View Retrieved Context Chunks (Masked PII)", open=False):
                        retrieved_chunks_view = gr.Markdown(
                            value="No chunks retrieved yet."
                        )
                        
            query_btn.click(
                fn=query_documents_ui,
                inputs=[api_key_input, query_cust_id, query_input, top_k_slider],
                outputs=[answer_output, sources_output, chunks_used_output, retrieved_chunks_view]
            )
            
        # TAB 3: Document Management
        with gr.TabItem("🛠️ Manage Documents"):
            gr.Markdown("### View, audit, and clean up customer documents and indexing collections.")
            with gr.Row():
                with gr.Column(scale=2):
                    manage_cust_id = gr.Textbox(
                        value="customer_001",
                        label="Customer ID"
                    )
                    list_btn = gr.Button("List Indexed Documents")
                    
                    dropdown_files = gr.Dropdown(
                        label="Select File to Delete",
                        choices=[],
                        info="List documents first to populate choices."
                    )
                    delete_btn = gr.Button("Delete Selected Document", elem_classes=["danger-btn"])
                    purge_btn = gr.Button("Purge All Customer Data", elem_classes=["danger-btn"])
                    
                with gr.Column(scale=3):
                    manage_status = gr.Markdown(
                        "Click **List Indexed Documents** to view files."
                    )
                    
            list_btn.click(
                fn=list_documents_ui,
                inputs=[manage_cust_id],
                outputs=[manage_status, dropdown_files]
            )
            
            delete_btn.click(
                fn=delete_document_ui,
                inputs=[manage_cust_id, dropdown_files],
                outputs=[manage_status]
            ).then(
                fn=list_documents_ui,
                inputs=[manage_cust_id],
                outputs=[manage_status, dropdown_files]
            )
            
            purge_btn.click(
                fn=purge_customer_ui,
                inputs=[manage_cust_id],
                outputs=[manage_status]
            ).then(
                fn=list_documents_ui,
                inputs=[manage_cust_id],
                outputs=[manage_status, dropdown_files]
            )
            
        # TAB 4: PII Masker Sandbox Demo
        with gr.TabItem("🛡️ PII Masker Demo"):
            gr.Markdown(
                "### PII Masking Sandbox\n"
                "Test how the local PII Masking engine cleans sensitive text. Write or paste anything containing emails, phone numbers, "
                "API keys, credit cards, SSNs, or credentials, and watch them mask in real-time."
            )
            with gr.Row():
                with gr.Column(scale=1):
                    sandbox_input = gr.Textbox(
                        lines=6,
                        label="Input Text (Paste anything sensitive here)",
                        placeholder=(
                            "For example: Use password=admin_pass_99 and contact admin@acme-corp.com. "
                            "Call +1-555-019-2834. Card detail: 4111 2222 3333 4444."
                        )
                    )
                    sandbox_btn = gr.Button("Execute Masking Process", elem_classes=["primary-btn"])
                    
                with gr.Column(scale=1):
                    sandbox_output = gr.Textbox(
                        lines=6,
                        label="PII Masked Output (This is what is embedded and stored)",
                        interactive=False
                    )
                    sandbox_badges = gr.HTML(
                        label="Types Detected"
                    )
                    
            sandbox_btn.click(
                fn=pii_masker_ui,
                inputs=[sandbox_input],
                outputs=[sandbox_output, sandbox_badges]
            )

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        theme=gr.themes.Soft(primary_hue="indigo", secondary_hue="violet", neutral_hue="slate"),
        css=custom_css
    )
