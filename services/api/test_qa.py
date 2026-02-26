from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.llm.qa import get_qa_chain

qa = get_qa_chain()

result = qa.invoke("Which programs mention Master Degree?")

print("\nANSWER:\n", result["result"])

print("\nRETRIEVED CONTENT:\n")
for doc in result["source_documents"]:
    print("Program ID:", doc.metadata)
    print(doc.page_content[:300])
    print("------")