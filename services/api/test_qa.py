import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.llm.qa import qa  # noqa: E402
from app.llm.retriever import CHROMA_DIR  # noqa: E402

# ── Check Chroma store ──────────────────────────────────────────────
chroma_path = Path(CHROMA_DIR)
if not chroma_path.exists():
    print("❌ Chroma store not found at:", CHROMA_DIR)
    print("   Run:  poetry run python scripts/rebuild_chroma.py")
    exit(1)

print(f"✅ Chroma store found at: {CHROMA_DIR}")
print(f"   Files: {len(list(chroma_path.rglob('*')))} entries\n")

# ── Ask question ────────────────────────────────────────────────────
question = "Which programs mention Rural Training?"
print(f"🔎 Question: {question}\n")

start = time.time()
result = qa.invoke(question)
elapsed = time.time() - start

# ── Answer ──────────────────────────────────────────────────────────
print("=" * 60)
print("📝 ANSWER")
print("=" * 60)
print(result["result"].strip())
print()

# ── Source documents ────────────────────────────────────────────────
docs = result.get("source_documents", [])
print("=" * 60)
print(f"📚 SOURCE DOCUMENTS  ({len(docs)} retrieved)")
print("=" * 60)

for i, doc in enumerate(docs, 1):
    program_id = doc.metadata.get("program_id", "N/A")
    snippet = doc.page_content[:300].replace("\n", " ").strip()
    print(f"\n  [{i}] Program ID: {program_id}")
    print(f"      {snippet}...")

# ── Stats ───────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"⏱  Response time: {elapsed:.2f}s")
print(f"📊 Documents retrieved: {len(docs)}")
print("=" * 60)
